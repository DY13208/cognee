"""Orchestrated snapshots validate first and replace a bad proposal in one write."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from cognee.modules.teleology.goal_model_models import (
    TeleologyBuildRunRecord,
    TeleologyGoalCandidateRecord,
)
from cognee.modules.teleology.goal_orchestrated import (
    compose_orchestrated_proposal,
    submit_orchestrated_goal_model,
)
from cognee.modules.teleology.goal_store import (
    MemoryGoalRunStore,
    SqlGoalModelStore,
    use_goal_store,
)

PROFIT_NODES = {
    "co_profit": "公司整体利润",
    "brand_profit": "单品牌项目利润",
    "price_wm": "WM项目利润分",
    "price_un": "UN项目利润分",
    "ar_profit": "Arencia项目利润分",
    "wm_node": "WM项目",
    "un_node": "UNOVE项目",
    "inventory": "库存周转",
    "channel": "渠道费比",
    "creator": "达人投放",
    "member": "会员价值",
    "compliance": "合规上市",
    "brand_asset": "品牌资产",
    "price_node": "价格体系",
}


def _node(node_id: str, semantic: str = "Metric") -> dict:
    return {
        "node_id": node_id,
        "name": PROFIT_NODES[node_id],
        "semantic_class": semantic,
        "source_layer": "company_tree",
        "text": PROFIT_NODES[node_id],
        "reason": "证据",
    }


def _goal(client_id: str, name: str, node_ids: list[str]) -> dict:
    return {
        "client_id": client_id,
        "name": name,
        "description": name,
        "reason": f"{name}由多类证据归纳",
        "confidence": 0.84,
        "evidence_node_ids": list(node_ids),
    }


def _link(parent: str, child: str, node_id: str) -> dict:
    return {
        "parent_client_id": parent,
        "child_client_id": child,
        "reason": "更具体的业务结果",
        "confidence": 0.8,
        "evidence_node_ids": [node_id],
    }


def _relation(source: str, target: str, relationship: str, node_id: str) -> dict:
    return {
        "source_client_id": source,
        "target_client_id": target,
        "relationship": relationship,
        "reason": f"{source} {relationship} {target}",
        "confidence": 0.82,
        "evidence_node_ids": [node_id],
    }


def golden_payload() -> dict:
    goals = [
        _goal("g_company_profit", "提升公司整体经营利润", ["co_profit"]),
        _goal("g_project_profitability", "提升单品牌项目盈利能力", ["brand_profit"]),
        _goal("g_price_order", "维护全渠道价格体系秩序", ["price_wm", "price_un", "price_node"]),
        _goal("g_arencia_profit", "提升 Arencia 项目盈利能力", ["ar_profit"]),
        _goal("g_wm_profit", "提升 WM 项目盈利能力", ["wm_node", "price_wm"]),
        _goal("g_un_profit", "提升 UNOVE 项目盈利能力", ["un_node", "price_un"]),
        _goal("g_inventory_health", "提升库存周转健康度与资金效率", ["inventory", "co_profit"]),
        _goal("g_channel_efficiency", "提升渠道经营效率与费比健康度", ["channel", "brand_profit"]),
        _goal("g_creator_roi", "提升达人种草与直播投放投产比", ["creator"]),
        _goal("g_member_value", "提升会员价值贡献", ["member", "ar_profit"]),
        _goal("g_compliance_launch", "提升新品合规上市成功率", ["compliance"]),
        _goal("g_brand_asset", "提升品牌资产与视觉表达一致性", ["brand_asset"]),
    ]
    hierarchy = [
        _link("g_company_profit", "g_project_profitability", "brand_profit"),
        _link("g_project_profitability", "g_arencia_profit", "ar_profit"),
        _link("g_project_profitability", "g_wm_profit", "price_wm"),
        _link("g_project_profitability", "g_un_profit", "price_un"),
        _link("g_company_profit", "g_inventory_health", "inventory"),
        _link("g_company_profit", "g_channel_efficiency", "channel"),
        _link("g_channel_efficiency", "g_creator_roi", "creator"),
        _link("g_project_profitability", "g_compliance_launch", "compliance"),
        _link("g_project_profitability", "g_member_value", "member"),
        _link("g_company_profit", "g_brand_asset", "brand_asset"),
        _link("g_channel_efficiency", "g_price_order", "price_node"),
    ]
    relations = [
        _relation("g_compliance_launch", "g_project_profitability", "advances", "compliance"),
        _relation("g_inventory_health", "g_company_profit", "advances", "inventory"),
        _relation("g_creator_roi", "g_channel_efficiency", "advances", "creator"),
        _relation("g_member_value", "g_arencia_profit", "advances", "member"),
        _relation("g_price_order", "g_channel_efficiency", "blocks", "price_node"),
    ]
    purposes = [
        {
            "goal_client_id": "g_company_profit",
            "name": "提高公司经营回报",
            "reason": "公司利润是经营回报",
            "confidence": 0.8,
            "evidence_node_ids": ["co_profit"],
        }
    ]
    constraints = [
        {
            "goal_client_id": "g_channel_efficiency",
            "name": "渠道费比不得超过上限",
            "reason": "费比是渠道约束",
            "confidence": 0.77,
            "evidence_node_ids": ["channel"],
        }
    ]
    return {
        "generated_by": "workbuddy_orchestrated",
        "submission_mode": "replace",
        "goals": goals,
        "hierarchy": hierarchy,
        "purposes": purposes,
        "constraints": constraints,
        "relations": relations,
    }


def _parents(candidates: list[dict]) -> dict[str, str | None]:
    by_id = {goal["id"]: goal for goal in candidates}
    return {
        goal["name"]: (
            by_id[goal["parent_candidate_id"]]["name"] if goal.get("parent_candidate_id") else None
        )
        for goal in candidates
        if goal.get("status") != "legacy_confirmed"
    }


@pytest.fixture
def memory_store(monkeypatch):
    store = MemoryGoalRunStore()
    use_goal_store(store)

    async def allow(*_args, **_kwargs):
        return SimpleNamespace(owner_id="owner")

    monkeypatch.setattr("cognee.modules.teleology.goal_orchestrated._authorized_dataset", allow)
    yield store
    use_goal_store(None)


def test_profit_words_in_evidence_do_not_collapse_three_goals():
    payload = {
        "goals": golden_payload()["goals"][:3],
        "hierarchy": [],
        "relations": [],
    }
    _model, summary = compose_orchestrated_proposal(
        uuid4(), payload, known_node_ids=set(PROFIT_NODES), submission_mode="replace"
    )
    names = [goal["name"] for goal in summary["normalized_goals"]]

    assert names == [
        "提升公司整体经营利润",
        "提升单品牌项目盈利能力",
        "维护全渠道价格体系秩序",
    ]
    assert len({goal["semantic_hash"] for goal in summary["normalized_goals"]}) == 3
    assert summary["duplicates"] == []
    assert summary["critical_errors"] == []


def test_golden_hierarchy_and_five_relations_from_evidence_ids():
    model, summary = compose_orchestrated_proposal(
        uuid4(), golden_payload(), known_node_ids=set(PROFIT_NODES), submission_mode="replace"
    )
    parents = _parents(model["candidates"])

    assert summary["valid"] is True
    assert summary["critical_errors"] == []
    assert summary["accepted"]["goals"] == 12
    assert summary["accepted"]["hierarchy"] == 11
    assert summary["accepted"]["relations"] == 5
    assert summary["accepted"]["purposes"] == 1
    assert summary["accepted"]["constraints"] == 1
    assert summary["relations_preview"] and all(
        item["status"] == "accepted" for item in summary["relations_preview"]
    )
    assert all(item["evidence"] for item in model["relations"])
    assert all(item["source_node_ids"] for item in model["relations"])
    assert parents["提升公司整体经营利润"] is None
    assert parents["提升单品牌项目盈利能力"] == "提升公司整体经营利润"
    assert parents["提升 Arencia 项目盈利能力"] == "提升单品牌项目盈利能力"
    assert parents["提升 WM 项目盈利能力"] == "提升单品牌项目盈利能力"
    assert parents["提升 UNOVE 项目盈利能力"] == "提升单品牌项目盈利能力"
    assert parents["提升库存周转健康度与资金效率"] == "提升公司整体经营利润"
    assert parents["提升渠道经营效率与费比健康度"] == "提升公司整体经营利润"
    assert parents["提升达人种草与直播投放投产比"] == "提升渠道经营效率与费比健康度"
    assert parents["提升新品合规上市成功率"] == "提升单品牌项目盈利能力"
    assert parents["提升会员价值贡献"] == "提升单品牌项目盈利能力"
    assert parents["维护全渠道价格体系秩序"] == "提升渠道经营效率与费比健康度"
    assert all(goal["parent_candidate_id"] != goal["id"] for goal in model["candidates"])
    assert (
        parents["维护全渠道价格体系秩序"] != "提升公司整体经营利润"
        or parents["提升公司整体经营利润"] is None
    )
    company = next(goal for goal in model["candidates"] if goal["name"] == "提升公司整体经营利润")
    price = next(goal for goal in model["candidates"] if goal["name"] == "维护全渠道价格体系秩序")
    assert company["parent_candidate_id"] != price["id"]
    assert {entry["node_id"] for entry in price["evidence"]} == {
        "price_wm",
        "price_un",
        "price_node",
    }
    assert "co_profit" not in {entry["node_id"] for entry in price["evidence"]}


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(memory_store):
    dataset_id = uuid4()
    preview = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        {**golden_payload(), "dry_run": True, "strict": True, "submission_mode": "replace"},
        known_node_ids=set(PROFIT_NODES),
        store=memory_store,
    )

    assert preview["valid"] is True
    assert preview["saved"] is False
    assert preview["dry_run"] is True
    assert preview["run_id"] is None
    assert preview["critical_errors"] == []
    assert preview["accepted"]["relations"] == 5
    assert memory_store.runs == {}
    assert await memory_store.get_dataset(dataset_id) is None


@pytest.mark.asyncio
async def test_replace_removes_the_bad_proposed_snapshot(memory_store):
    dataset_id = uuid4()
    bad_price = {
        "id": "bad-price",
        "dataset_id": str(dataset_id),
        "name": "维护全渠道价格体系秩序",
        "description": "错误总目标",
        "reason": "被错误合并",
        "confidence": 0.4,
        "reason_provenance": [],
        "source_node_ids": ["co_profit", "price_wm"],
        "evidence": [_node("co_profit"), _node("price_wm")],
        "parent_candidate_id": None,
        "status": "proposed",
        "semantic_hash": "bad",
        "orchestrated_identity": "维护全渠道价格体系秩序",
        "generated_by": "workbuddy_orchestrated",
    }
    bad_company = {
        "id": "bad-company",
        "dataset_id": str(dataset_id),
        "name": "提升公司整体经营利润",
        "description": "被挂到控价下面",
        "reason": "错误层级",
        "confidence": 0.4,
        "source_node_ids": ["co_profit"],
        "evidence": [_node("co_profit"), _node("price_wm")],
        "parent_candidate_id": "bad-price",
        "status": "proposed",
        "semantic_hash": "bad-company",
        "generated_by": "workbuddy_orchestrated",
    }
    confirmed = {
        "id": "kept-confirmed",
        "dataset_id": str(dataset_id),
        "name": "提升已确认的服务体验",
        "description": "人工确认",
        "reason": "已确认",
        "confidence": 0.9,
        "source_node_ids": ["member"],
        "evidence": [_node("member")],
        "parent_candidate_id": "bad-price",
        "status": "confirmed",
        "semantic_hash": "confirmed",
        "orchestrated_identity": "提升已确认的服务体验",
        "generated_by": "workbuddy_orchestrated",
    }
    await memory_store.save_result(
        {
            "run_id": str(uuid4()),
            "dataset_id": str(dataset_id),
            "mode": "orchestrated",
            "status": "completed",
            "source_count": 2,
            "canonical_goal_count": 2,
            "committed": False,
            "graph_committed": False,
            "candidates": [bad_price, bad_company, confirmed],
            "purposes": [],
            "constraints": [],
            "relations": [],
            "teleology": {"purposes": [], "constraints": [], "relations": []},
        }
    )
    bad_run_id = next(iter(memory_store.runs))
    saved = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        {**golden_payload(), "dry_run": False, "strict": True, "submission_mode": "replace"},
        known_node_ids=set(PROFIT_NODES),
        store=memory_store,
    )
    view = await memory_store.get_dataset(dataset_id)
    parents = _parents(view["candidates"])
    legacy = next(goal for goal in view["candidates"] if goal["id"] == "kept-confirmed")

    assert saved["saved"] is True
    assert saved["valid"] is True
    assert bad_run_id in memory_store.runs
    assert saved["run_id"] != bad_run_id
    assert parents["提升公司整体经营利润"] is None
    assert "bad-price" not in {goal["id"] for goal in view["candidates"]}
    assert legacy["status"] == "legacy_confirmed"
    assert legacy["outside_current_snapshot"] is True
    assert legacy["parent_candidate_id"] in (None, "")
    assert memory_store.runs[bad_run_id]["candidates"][0]["id"] == "bad-price"


@pytest.mark.asyncio
async def test_strict_critical_hierarchy_does_not_write(memory_store):
    dataset_id = uuid4()
    payload = _atomic_payload()
    before = copy.deepcopy(memory_store.runs)
    result = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        payload,
        known_node_ids=set(PROFIT_NODES) | {f"n{index}" for index in range(12)},
        store=memory_store,
        strict=True,
        dry_run=False,
        submission_mode="replace",
    )

    assert result["saved"] is False
    assert result["status"] == "validation_failed"
    assert result["valid"] is False
    assert result["run_id"] is None
    assert any(issue["reason"] == "missing_endpoint" for issue in result["critical_errors"])
    assert memory_store.runs == before
    assert await memory_store.get_dataset(dataset_id) is None


@pytest.mark.asyncio
async def test_strict_failure_leaves_sql_rows_unchanged(monkeypatch):
    async def allow(*_args, **_kwargs):
        return SimpleNamespace(owner_id="owner")

    monkeypatch.setattr("cognee.modules.teleology.goal_orchestrated._authorized_dataset", allow)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def _create(sync_conn):
        TeleologyBuildRunRecord.__table__.create(sync_conn)
        TeleologyGoalCandidateRecord.__table__.create(sync_conn)

    async with engine.begin() as connection:
        await connection.run_sync(_create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlGoalModelStore(sessions)
    dataset_id = uuid4()
    good, _summary = compose_orchestrated_proposal(
        dataset_id,
        {"goals": golden_payload()["goals"][:1], "hierarchy": [], "relations": []},
        known_node_ids=set(PROFIT_NODES),
    )
    await store.save_result(good)
    async with sessions() as session:
        from sqlalchemy import func, select

        before_runs = (
            await session.execute(select(func.count()).select_from(TeleologyBuildRunRecord))
        ).scalar_one()
        before_goals = (
            await session.execute(select(func.count()).select_from(TeleologyGoalCandidateRecord))
        ).scalar_one()
    result = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        _atomic_payload(),
        known_node_ids=set(PROFIT_NODES) | {f"n{index}" for index in range(12)},
        store=store,
        strict=True,
    )
    async with sessions() as session:
        from sqlalchemy import func, select

        after_runs = (
            await session.execute(select(func.count()).select_from(TeleologyBuildRunRecord))
        ).scalar_one()
        after_goals = (
            await session.execute(select(func.count()).select_from(TeleologyGoalCandidateRecord))
        ).scalar_one()
    view = await store.get_dataset(dataset_id)

    assert result["saved"] is False
    assert before_runs == after_runs == 1
    assert before_goals == after_goals == 1
    assert view["candidates"][0]["name"] == "提升公司整体经营利润"
    await engine.dispose()


def test_orchestrated_duplicate_does_not_use_evidence_merge_key():
    from pathlib import Path

    text = (
        Path(__file__)
        .resolve()
        .parents[5]
        .joinpath("cognee", "modules", "teleology", "goal_orchestrated.py")
        .read_text(encoding="utf-8")
    )
    assert "_merge_key" not in text
    assert "_union" not in text
    assert "commit_teleology_proposal" not in text
    assert "has_subgoal" in text


def _atomic_payload() -> dict:
    goals = []
    for index in range(12):
        goals.append(
            {
                "client_id": f"g{index}",
                "name": f"提升专项结果 {index}",
                "description": f"专项 {index}",
                "reason": "独立业务结果",
                "confidence": 0.7,
                "evidence_node_ids": [f"n{index}"],
            }
        )
    hierarchy = [_link(f"g{index}", f"g{index + 1}", f"n{index + 1}") for index in range(10)]
    hierarchy.append(
        {
            "parent_client_id": "g0",
            "child_client_id": "missing-child",
            "reason": "端点不存在",
            "confidence": 0.7,
            "evidence_node_ids": ["n0"],
        }
    )
    purposes = [
        {
            "goal_client_id": "g0",
            "name": f"目的 {index}",
            "reason": "目的证据",
            "confidence": 0.7,
            "evidence_node_ids": ["n0"],
        }
        for index in range(5)
    ]
    constraints = [
        {
            "goal_client_id": "g1",
            "name": f"费用上限约束 {index}",
            "reason": "约束证据",
            "confidence": 0.7,
            "evidence_node_ids": ["n1"],
        }
        for index in range(8)
    ]
    relations = [
        _relation("g2", "g3", "advances", "n2"),
        _relation("g3", "g4", "advances", "n3"),
        _relation("g4", "g5", "serves", "n4"),
        _relation("g5", "g6", "blocks", "n5"),
        _relation("g6", "g7", "advances", "n6"),
    ]
    return {
        "dry_run": False,
        "strict": True,
        "submission_mode": "replace",
        "goals": goals,
        "hierarchy": hierarchy,
        "purposes": purposes,
        "constraints": constraints,
        "relations": relations,
    }
