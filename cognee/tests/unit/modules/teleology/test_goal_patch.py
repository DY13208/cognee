"""Incremental patches keep the current snapshot except where the payload says otherwise."""

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
from cognee.modules.teleology.goal_patch import (
    PATCH_IMPACT_REPLACE_RATIO,
    analyze_goal_model_impact,
    compose_orchestrated_patch,
    submit_orchestrated_patch,
)
from cognee.modules.teleology.goal_store import (
    MemoryGoalRunStore,
    SqlGoalModelStore,
    use_goal_store,
)
from cognee.tests.unit.modules.teleology.test_goal_orchestrated_contract import (
    PROFIT_NODES,
    golden_payload,
)

KNOWN = set(PROFIT_NODES) | {"ar_repeat", "store_kpi"}


def _names(view: dict) -> dict[str, dict]:
    return {goal["name"]: goal for goal in view["candidates"] if goal.get("status") != "rejected"}


def _upsert(goal: dict, **changes) -> dict:
    return {
        "client_id": goal["id"],
        "name": goal["name"],
        "description": changes.get("description", goal.get("description") or goal["name"]),
        "reason": changes.get("reason", goal["reason"]),
        "confidence": changes.get("confidence", goal["confidence"]),
        "evidence_node_ids": list(changes.get("evidence_node_ids", goal["source_node_ids"])),
    }


def _patch(view: dict, **extra) -> dict:
    body = {
        "submission_mode": "patch",
        "base_run_id": view["current_run_id"],
        "generated_by": "workbuddy_orchestrated",
        "source_revision": "1404",
        "dry_run": False,
        "strict": True,
    }
    body.update(extra)
    return body


def _link(parent: str, child: str, node_id: str, reason: str = "调整受影响目标") -> dict:
    return {
        "parent_client_id": parent,
        "child_client_id": child,
        "reason": reason,
        "confidence": 0.8,
        "evidence_node_ids": [node_id],
    }


async def _install(store):
    dataset_id = uuid4()
    model, summary = compose_orchestrated_proposal(
        dataset_id, golden_payload(), known_node_ids=KNOWN, submission_mode="replace"
    )
    assert summary["valid"] is True
    await store.save_result(model)
    view = await store.get_dataset(dataset_id)
    assert view is not None
    return dataset_id, view


def _parent_name(view: dict, name: str) -> str | None:
    goals = _names(view)
    parent_id = goals[name].get("parent_candidate_id")
    if not parent_id:
        return None
    for goal in view["candidates"]:
        if goal["id"] == parent_id:
            return goal["name"]
    return None


@pytest.fixture
def patch_store(monkeypatch):
    store = MemoryGoalRunStore()
    use_goal_store(store)

    async def allow(*_args, **_kwargs):
        return SimpleNamespace(owner_id="owner")

    monkeypatch.setattr("cognee.modules.teleology.goal_patch._authorized_dataset", allow)
    monkeypatch.setattr("cognee.modules.teleology.goal_orchestrated._authorized_dataset", allow)
    return store


@pytest.mark.asyncio
async def test_arencia_evidence_impacts_only_its_neighborhood(patch_store):
    dataset_id, view = await _install(patch_store)
    impact = analyze_goal_model_impact(view, ["ar_profit"])
    labels = {goal["id"]: goal["name"] for goal in view["candidates"]}
    direct = {labels[goal_id] for goal_id in impact["directly_impacted_goal_ids"]}
    context = {labels[goal_id] for goal_id in impact["context_goal_ids"]}

    assert impact["base_run_id"] == view["current_run_id"]
    assert direct == {"提升 Arencia 项目盈利能力", "提升会员价值贡献"}
    assert context == {"提升单品牌项目盈利能力"}
    assert "提升 WM 项目盈利能力" not in direct | context
    assert "提升 UNOVE 项目盈利能力" not in direct | context
    assert "提升库存周转健康度与资金效率" not in direct | context
    assert impact["recommend_full_replace"] is False
    assert PATCH_IMPACT_REPLACE_RATIO == 0.40

    goals = _names(view)
    arencia = goals["提升 Arencia 项目盈利能力"]
    before = copy.deepcopy(patch_store.runs)
    result = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        _patch(
            view,
            upsert_goals=[_upsert(arencia, description="会员复购证据已更新")],
            affected_goal_ids=[arencia["id"]],
            changed_source_ids=["ar_profit"],
            hierarchy=[
                _link(
                    goals["提升公司整体经营利润"]["id"],
                    goals["提升 WM 项目盈利能力"]["id"],
                    "wm_node",
                    "不应改动 WM",
                )
            ],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
        submission_mode="patch",
    )
    saved = await patch_store.get_dataset(dataset_id)

    assert result["saved"] is True
    assert result["valid"] is True
    assert any(issue["reason"] == "outside_patch_scope" for issue in result["issues"])
    assert _names(saved)["提升 Arencia 项目盈利能力"]["id"] == arencia["id"]
    assert _names(saved)["提升 Arencia 项目盈利能力"]["description"] == "会员复购证据已更新"
    assert _parent_name(saved, "提升 WM 项目盈利能力") == "提升单品牌项目盈利能力"
    assert _parent_name(saved, "提升 UNOVE 项目盈利能力") == "提升单品牌项目盈利能力"
    assert _parent_name(saved, "提升库存周转健康度与资金效率") == "提升公司整体经营利润"
    assert _parent_name(saved, "提升达人种草与直播投放投产比") == "提升渠道经营效率与费比健康度"
    assert len(saved["relations"]) == len(view["relations"])
    assert len(before) + 1 == len(patch_store.runs)


@pytest.mark.asyncio
async def test_evidence_update_keeps_candidate_id_and_review(patch_store):
    dataset_id, view = await _install(patch_store)
    goals = _names(view)
    arencia = goals["提升 Arencia 项目盈利能力"]
    for goal in patch_store.runs[view["run_id"]]["candidates"]:
        if goal["id"] == arencia["id"]:
            goal["status"] = "confirmed"
    view = await patch_store.get_dataset(dataset_id)
    arencia = _names(view)["提升 Arencia 项目盈利能力"]
    preview = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            dry_run=True,
            upsert_goals=[
                _upsert(
                    arencia,
                    description="新增复购 KPI",
                    evidence_node_ids=["ar_profit", "ar_repeat"],
                )
            ],
            affected_goal_ids=[arencia["id"]],
            changed_source_ids=["ar_repeat"],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )

    assert preview["dry_run"] is True
    assert preview["saved"] is False
    assert preview["run_id"] is None
    assert preview["updated_goals"][0]["id"] == arencia["id"]
    assert preview["added_goals"] == []
    assert await patch_store.get_dataset(dataset_id)
    assert patch_store.by_dataset[str(dataset_id)] == view["run_id"]

    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            upsert_goals=[
                _upsert(
                    arencia,
                    description="新增复购 KPI",
                    evidence_node_ids=["ar_profit", "ar_repeat"],
                )
            ],
            affected_goal_ids=[arencia["id"]],
            changed_source_ids=["ar_repeat"],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )
    saved = await patch_store.get_dataset(dataset_id)
    updated = _names(saved)["提升 Arencia 项目盈利能力"]

    assert result["saved"] is True
    assert updated["id"] == arencia["id"]
    assert updated["status"] == "confirmed"
    assert "ar_repeat" in updated["source_node_ids"]
    assert saved["last_source_revision"] == "1404"
    assert saved["model_version"] == 2


@pytest.mark.asyncio
async def test_new_goal_does_not_change_existing_goals(patch_store):
    dataset_id, view = await _install(patch_store)
    before = {
        goal["name"]: (goal["id"], goal.get("parent_candidate_id"), list(goal["source_node_ids"]))
        for goal in view["candidates"]
    }
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            upsert_goals=[
                {
                    "client_id": "g_store",
                    "name": "提升门店会员到店复购",
                    "description": "新的门店复购目标",
                    "reason": "新业务结果",
                    "confidence": 0.7,
                    "evidence_node_ids": ["store_kpi"],
                }
            ],
            changed_source_ids=["store_kpi"],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )
    saved = await patch_store.get_dataset(dataset_id)
    created = _names(saved)["提升门店会员到店复购"]

    assert result["saved"] is True
    assert created["status"] == "proposed"
    assert created["id"] not in {goal["id"] for goal in view["candidates"]}
    for name, (goal_id, parent, sources) in before.items():
        current = _names(saved)[name]
        assert current["id"] == goal_id
        assert current.get("parent_candidate_id") == parent
        assert list(current["source_node_ids"]) == sources


@pytest.mark.asyncio
async def test_omitted_proposed_goal_stays_until_remove_ids(patch_store):
    dataset_id, view = await _install(patch_store)
    goals = _names(view)
    creator_id = goals["提升达人种草与直播投放投产比"]["id"]
    kept = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            upsert_goals=[
                _upsert(goals["提升 Arencia 项目盈利能力"], description="只更新 Arencia")
            ],
            affected_goal_ids=[goals["提升 Arencia 项目盈利能力"]["id"]],
            changed_source_ids=["ar_profit"],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )
    after_omit = await patch_store.get_dataset(dataset_id)
    assert kept["saved"] is True
    assert "提升达人种草与直播投放投产比" in _names(after_omit)

    removed = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(after_omit, remove_goal_ids=[creator_id]),
        known_node_ids=KNOWN,
        store=patch_store,
    )
    after_remove = await patch_store.get_dataset(dataset_id)

    assert removed["saved"] is True
    assert creator_id in removed["retired_goal_ids"]
    assert "提升达人种草与直播投放投产比" not in _names(after_remove)
    assert _parent_name(after_remove, "提升渠道经营效率与费比健康度") == "提升公司整体经营利润"


@pytest.mark.asyncio
async def test_confirmed_goal_is_retired_not_deleted(patch_store):
    dataset_id, view = await _install(patch_store)
    brand_id = _names(view)["提升品牌资产与视觉表达一致性"]["id"]
    for goal in patch_store.runs[view["run_id"]]["candidates"]:
        if goal["id"] == brand_id:
            goal["status"] = "confirmed"
    view = await patch_store.get_dataset(dataset_id)
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(view, remove_goal_ids=[brand_id]),
        known_node_ids=KNOWN,
        store=patch_store,
    )
    saved = await patch_store.get_dataset(dataset_id)
    brand = next(goal for goal in saved["candidates"] if goal["id"] == brand_id)

    assert result["saved"] is True
    assert brand["status"] == "confirmed"
    assert brand["outside_current_snapshot"] is True
    assert brand["retirement_proposed"] is True
    assert _parent_name(saved, "提升 WM 项目盈利能力") == "提升单品牌项目盈利能力"


@pytest.mark.asyncio
async def test_stale_base_writes_nothing(patch_store):
    dataset_id, view = await _install(patch_store)
    before = copy.deepcopy(patch_store.runs)
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            base_run_id=str(uuid4()),
            upsert_goals=[_upsert(_names(view)["提升 Arencia 项目盈利能力"], description="过期")],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )

    assert result["status"] == "stale_base"
    assert result["saved"] is False
    assert result["run_id"] is None
    assert patch_store.runs.keys() == before.keys()


@pytest.mark.asyncio
async def test_identical_patch_replays_one_run(patch_store):
    dataset_id, view = await _install(patch_store)
    payload = _patch(
        view,
        upsert_goals=[_upsert(_names(view)["提升 Arencia 项目盈利能力"], description="同一补丁")],
        affected_goal_ids=[_names(view)["提升 Arencia 项目盈利能力"]["id"]],
        changed_source_ids=["ar_profit"],
    )
    first = await submit_orchestrated_patch(
        dataset_id, object(), payload, known_node_ids=KNOWN, store=patch_store
    )
    second = await submit_orchestrated_patch(
        dataset_id, object(), copy.deepcopy(payload), known_node_ids=KNOWN, store=patch_store
    )
    drifted = copy.deepcopy(payload)
    drifted["upsert_goals"][0]["description"] = "另一份补丁"
    third = await submit_orchestrated_patch(
        dataset_id, object(), drifted, known_node_ids=KNOWN, store=patch_store
    )

    assert first["saved"] is True
    assert second["idempotent_replay"] is True
    assert second["run_id"] == first["run_id"]
    assert second["saved"] is True
    assert third["status"] == "stale_base"
    assert third["saved"] is False
    assert len(patch_store.runs) == 2


@pytest.mark.asyncio
async def test_wide_impact_recommends_full_replace(patch_store):
    dataset_id, view = await _install(patch_store)
    before = set(patch_store.runs)
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            changed_source_ids=["co_profit", "brand_profit", "creator", "compliance"],
            upsert_goals=[
                _upsert(_names(view)["提升 Arencia 项目盈利能力"], description="不该写入")
            ],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
    )

    assert result["recommend_full_replace"] is True
    assert result["status"] == "replace_required"
    assert result["saved"] is False
    assert set(patch_store.runs) == before
    assert (
        _names(await patch_store.get_dataset(dataset_id))["提升 Arencia 项目盈利能力"][
            "description"
        ]
        != "不该写入"
    )


@pytest.mark.asyncio
async def test_patch_cycle_is_atomic(patch_store):
    dataset_id, view = await _install(patch_store)
    goals = _names(view)
    before = set(patch_store.runs)
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(
            view,
            affected_goal_ids=[
                goals["提升 Arencia 项目盈利能力"]["id"],
                goals["提升会员价值贡献"]["id"],
            ],
            hierarchy=[
                _link(
                    goals["提升会员价值贡献"]["id"],
                    goals["提升 Arencia 项目盈利能力"]["id"],
                    "ar_profit",
                ),
                _link(
                    goals["提升 Arencia 项目盈利能力"]["id"],
                    goals["提升会员价值贡献"]["id"],
                    "member",
                ),
            ],
        ),
        known_node_ids=KNOWN,
        store=patch_store,
        strict=True,
    )
    saved = await patch_store.get_dataset(dataset_id)

    assert result["saved"] is False
    assert result["status"] == "validation_failed"
    assert any(issue["reason"] == "cycle" for issue in result["critical_errors"])
    assert set(patch_store.runs) == before
    assert _parent_name(saved, "提升 Arencia 项目盈利能力") == "提升单品牌项目盈利能力"
    assert _parent_name(saved, "提升会员价值贡献") == "提升单品牌项目盈利能力"


@pytest.mark.asyncio
async def test_replace_snapshot_still_installs_the_full_model(patch_store):
    dataset_id = uuid4()
    result = await submit_orchestrated_goal_model(
        dataset_id,
        object(),
        golden_payload(),
        known_node_ids=KNOWN,
        store=patch_store,
        dry_run=False,
        strict=True,
        submission_mode="replace",
    )
    saved = await patch_store.get_dataset(dataset_id)

    assert result["saved"] is True
    assert result["submission_mode"] == "replace"
    assert saved["submission_mode"] == "replace"
    assert len([goal for goal in saved["candidates"] if goal.get("status") != "rejected"]) == 12


@pytest.mark.asyncio
async def test_retirement_flag_survives_sql_reload(monkeypatch):
    async def allow(*_args, **_kwargs):
        return SimpleNamespace(owner_id="owner")

    monkeypatch.setattr("cognee.modules.teleology.goal_patch._authorized_dataset", allow)
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
    use_goal_store(store)
    dataset_id, view = await _install(store)
    brand_id = _names(view)["提升品牌资产与视觉表达一致性"]["id"]
    for goal in view["candidates"]:
        if goal["id"] == brand_id:
            goal["status"] = "confirmed"
    await store.save_result(view)
    current = await store.get_dataset(dataset_id)
    result = await submit_orchestrated_patch(
        dataset_id,
        object(),
        _patch(current, remove_goal_ids=[brand_id], source_revision="1404"),
        known_node_ids=KNOWN,
        store=store,
    )
    reloaded = await store.get_dataset(dataset_id)
    brand = next(goal for goal in reloaded["candidates"] if goal["id"] == brand_id)

    assert result["saved"] is True
    assert brand["status"] == "confirmed"
    assert brand["retirement_proposed"] is True
    assert brand["outside_current_snapshot"] is True
    assert _parent_name(reloaded, "提升库存周转健康度与资金效率") == "提升公司整体经营利润"
    use_goal_store(None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_relation_only_patch_preserves_confirmed_historical_sql_snapshot():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def create_tables(connection):
        TeleologyBuildRunRecord.__table__.create(connection)
        TeleologyGoalCandidateRecord.__table__.create(connection)

    async with engine.begin() as connection:
        await connection.run_sync(create_tables)
    store = SqlGoalModelStore(async_sessionmaker(engine, expire_on_commit=False))
    dataset_id = uuid4()
    model, summary = compose_orchestrated_proposal(
        dataset_id, golden_payload(), known_node_ids=KNOWN, submission_mode="replace"
    )
    assert summary["valid"] is True
    current = model["candidates"][:]
    root = next(goal for goal in current if not goal.get("parent_candidate_id"))
    while len(current) < 27:
        goal = copy.deepcopy(root)
        goal["id"] = str(uuid4())
        goal["name"] = f"补充目标 {len(current)}"
        goal["parent_candidate_id"] = root["id"]
        current.append(goal)
    historical = []
    for index in range(8):
        goal = copy.deepcopy(root)
        goal["id"] = str(uuid4())
        goal["name"] = f"历史目标 {index}"
        goal["status"] = "confirmed"
        goal["outside_current_snapshot"] = True
        goal["parent_candidate_id"] = None
        historical.append(goal)
    model["candidates"] = current + historical
    model["canonical_goal_count"] = 27
    model["purposes"] = [{"id": str(uuid4())} for _ in range(25)]
    model["constraints"] = [{"id": str(uuid4())} for _ in range(28)]
    model["relations"] = [{"id": str(uuid4())} for _ in range(15)]
    await store.save_result(model)
    before = await store.get_dataset(dataset_id)
    assert before["canonical_goal_count"] == 27
    assert sum(goal["outside_current_snapshot"] for goal in before["candidates"]) == 8

    relation_rows = [
        {
            "client_id": f"new-relation-{index}",
            "source_client_id": current[index]["id"],
            "target_client_id": current[index + 1]["id"],
            "relationship": "advances",
            "reason": "相关目标之间存在明确支持关系",
            "confidence": 0.8,
            "evidence_node_ids": ["ar_profit"],
        }
        for index in range(5)
    ]
    patched, patch_summary = compose_orchestrated_patch(
        dataset_id,
        _patch(
            before,
            affected_goal_ids=[goal["id"] for goal in current[:6]],
            relations=relation_rows,
        ),
        known_node_ids=KNOWN,
        current=before,
    )
    assert patch_summary["valid"] is True
    assert len(patch_summary["relation_changes"]) == 5
    assert patch_summary["hierarchy_changes"] == []
    assert patch_summary["purpose_changes"] == []
    assert patch_summary["constraint_changes"] == []
    assert patch_summary["added_goal_ids"] == []
    assert patch_summary["retired_goal_ids"] == []
    await store.save_result(patched)
    after = await store.get_dataset(dataset_id)
    live = [
        goal
        for goal in after["candidates"]
        if goal["status"] not in {"rejected", "legacy_confirmed"}
        and not goal["outside_current_snapshot"]
    ]
    historic = [goal for goal in after["candidates"] if goal["outside_current_snapshot"]]
    assert len(after["candidates"]) == 35
    assert after["canonical_goal_count"] == len(live) == 27
    assert {goal["id"] for goal in live} == {goal["id"] for goal in current}
    assert {goal["id"] for goal in historic} == {goal["id"] for goal in historical}
    assert all(goal["status"] == "confirmed" for goal in historic)
    assert len([goal for goal in live if not goal.get("parent_candidate_id")]) == 1
    assert len([goal for goal in live if goal.get("parent_candidate_id")]) == 26
    assert len(after["purposes"]) == 25
    assert len(after["constraints"]) == 28
    assert len(after["relations"]) == 20
    await engine.dispose()
