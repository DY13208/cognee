"""The AI Goal Model is derived from dataset evidence. The company tree is not copied."""

from pathlib import Path
from uuid import uuid4

import pytest

from cognee.modules.teleology.coverage_sources import ProductionSources
from cognee.modules.teleology.goal_build import start_teleology_build
from cognee.modules.teleology.goal_model import (
    STAGES,
    STORE,
    build_hierarchy,
    canonicalize,
    classify_source,
    run_goal_build,
    set_candidate_status,
)

ROOT = Path(__file__).resolve().parents[5]


def arencia_sources() -> list[dict]:
    return [
        {
            "id": "resp",
            "name": "责任分工",
            "type": "Goal",
            "layer": "company_tree",
            "tree_parent_id": None,
        },
        {
            "id": "project",
            "name": "Arencia项目",
            "type": "Goal",
            "layer": "company_tree",
            "tree_parent_id": "resp",
        },
        {
            "id": "metric",
            "name": "项目利润分",
            "type": "Goal",
            "layer": "company_tree",
            "tree_parent_id": "resp",
        },
        {
            "id": "accuracy",
            "name": "Arencia利润核算准确性指标",
            "type": "Goal",
            "layer": "company_tree",
            "tree_parent_id": "resp",
        },
        {
            "id": "doc",
            "name": "Arencia 利润说明",
            "type": "Document",
            "layer": "document",
            "text": "Arencia 项目利润分口径",
            "tree_parent_id": None,
        },
    ]


def _candidate(name: str, node_id: str, evidence_name: str | None = None) -> dict:
    shown = evidence_name or name
    return {
        "name": name,
        "description": shown,
        "confidence": 0.6,
        "reason": shown,
        "source_node_ids": [node_id],
        "evidence": [{"node_id": node_id, "name": shown, "source_class": "Metric", "text": shown}],
    }


@pytest.fixture(autouse=True)
def _clear_store():
    STORE.clear()
    yield
    STORE.clear()


@pytest.mark.parametrize(
    ("name", "graph_type", "expected"),
    [
        ("责任分工", "Goal", "Responsibility"),
        ("项目利润分", "Goal", "Metric"),
        ("Arencia项目", "Goal", "Project"),
        ("Arencia 利润说明", "Document", "Document"),
    ],
)
def test_company_tree_nodes_are_classified_by_meaning(name, graph_type, expected):
    assert classify_source({"name": name, "type": graph_type}) == expected


def test_pipeline_builds_goals_from_evidence_not_the_company_tree():
    result = run_goal_build(uuid4(), arencia_sources(), batch_size=2)

    classes = {row["id"]: row["source_class"] for row in result["classifications"]}
    assert classes == {
        "resp": "Responsibility",
        "project": "Project",
        "metric": "Metric",
        "accuracy": "Metric",
        "doc": "Document",
    }
    names = {goal["name"] for goal in result["candidates"]}
    assert names == {"提升 Arencia 项目盈利能力", "提高 Arencia 项目利润核算准确性"}
    assert "责任分工" not in names
    assert "项目利润分" not in names
    assert "Arencia项目" not in names
    profit = next(goal for goal in result["candidates"] if goal["name"].startswith("提升"))
    specific = next(goal for goal in result["candidates"] if "核算" in goal["name"])
    assert set(profit["source_node_ids"]) >= {"project", "metric", "doc"}
    assert "resp" not in profit["source_node_ids"]
    assert "resp" not in specific["source_node_ids"]
    assert specific["parent_candidate_id"] == profit["id"]
    assert profit["parent_candidate_id"] is None
    assert specific["parent_candidate_id"] != "resp"
    for goal in result["candidates"]:
        assert goal["status"] == "proposed"
        assert goal["evidence"]
        assert goal["source_node_ids"]
        assert goal["reason"]
        assert goal["semantic_hash"]
        assert goal["generated_by"] == "dataset_goal_build"
    goal_ids = {goal["id"] for goal in result["candidates"]}
    assert result["teleology"]["purposes"]
    assert result["teleology"]["committed"] is False
    assert result["committed"] is False
    assert result["graph_committed"] is False
    for relation in result["teleology"]["relations"]:
        assert relation["relationship"] == "advances"
        assert relation["source"] in goal_ids
        assert relation["target"] in goal_ids
        assert relation["evidence"]
    assert result["stages"] == list(STAGES)
    assert result["status"] == "completed"
    assert result["max_batch_payload"] <= 2


def test_hierarchy_ignores_has_subgoal_even_when_a_caller_passes_it():
    broad = _candidate("提升 Arencia 项目盈利能力", "a")
    broad["tree_parent_id"] = "resp"
    broad["id"] = "broad"
    broad["status"] = "proposed"
    narrow = _candidate("提高 Arencia 项目利润核算准确性", "b")
    narrow["tree_parent_id"] = "resp"
    narrow["id"] = "narrow"
    narrow["status"] = "proposed"
    narrow["source_node_ids"] = ["a", "b"]
    ranked = build_hierarchy([broad, narrow])
    child = next(goal for goal in ranked if goal["id"] == "narrow")
    assert child["parent_candidate_id"] == "broad"
    assert all(goal.get("parent_candidate_id") != "resp" for goal in ranked)
    assert all("tree_parent_id" not in goal for goal in ranked)


def test_canonicalization_merges_synonyms_and_keeps_every_source():
    merged = canonicalize(
        [
            _candidate("Arencia项目利润分", "m1"),
            _candidate("Arencia利润目标", "m2"),
            _candidate("项目盈利", "m3", "Arencia 项目盈利"),
        ],
        uuid4(),
        "test",
    )

    assert len(merged) == 1
    assert merged[0]["name"] == "提升 Arencia 项目盈利能力"
    assert set(merged[0]["source_node_ids"]) == {"m1", "m2", "m3"}
    assert {entry["node_id"] for entry in merged[0]["evidence"]} == {"m1", "m2", "m3"}


def test_a_goal_without_evidence_is_rejected():
    class EmptyModel:
        def classify(self, batch):
            return [classify_source(node) for node in batch]

        def extract(self, _batch):
            return [
                {
                    "name": "幽灵目标",
                    "reason": "没有证据",
                    "confidence": 0.9,
                    "source_node_ids": [],
                    "evidence": [],
                },
                {
                    "name": "只有一个来源",
                    "reason": "不够",
                    "confidence": 0.9,
                    "source_node_ids": ["only"],
                    "evidence": [{"node_id": "only", "name": "Arencia项目"}],
                },
            ]

    result = run_goal_build(uuid4(), arencia_sources(), model=EmptyModel())

    assert result["candidates"] == []
    assert result["rejected_empty"] == 2
    assert result["committed"] is False


def test_a_company_tree_outcome_sentence_is_not_copied_as_a_goal():
    result = run_goal_build(
        uuid4(),
        [
            {
                "id": "tree-goal",
                "name": "提升 Arencia 项目盈利能力",
                "type": "Goal",
                "layer": "company_tree",
            }
        ],
    )

    assert result["candidates"] == []
    assert result["classifications"][0]["source_class"] == "Goal"


def test_large_dataset_never_arrives_in_one_batch():
    sources = [
        {"id": f"n{index}", "name": f"笔记{index}", "type": "Note"} for index in range(12000)
    ]
    sources = arencia_sources() + sources
    result = run_goal_build(uuid4(), sources, batch_size=10)

    assert result["source_count"] == 12005
    assert result["max_batch_payload"] <= 10
    assert result["batch_size"] == 10
    profit = next(goal for goal in result["candidates"] if goal["name"].startswith("提升"))
    assert len(profit["source_node_ids"]) < 10


def test_batch_size_is_capped_before_a_model_would_see_the_dataset():
    sources = [{"id": f"n{index}", "name": f"笔记{index}", "type": "Note"} for index in range(250)]
    result = run_goal_build(uuid4(), sources, batch_size=10000)

    assert result["batch_size"] == 100
    assert result["max_batch_payload"] <= 100


def test_incremental_keeps_a_confirmed_goal_and_still_does_not_commit():
    dataset_id = uuid4()
    first = run_goal_build(dataset_id, arencia_sources())
    profit = next(goal for goal in first["candidates"] if goal["name"].startswith("提升"))
    profit["status"] = "confirmed"
    second = run_goal_build(
        dataset_id,
        arencia_sources(),
        mode="incremental",
        previous=first["candidates"],
    )

    kept = next(
        goal for goal in second["candidates"] if goal["semantic_hash"] == profit["semantic_hash"]
    )
    assert kept["status"] == "confirmed"
    assert kept["evidence"]
    assert second["committed"] is False
    assert len({goal["semantic_hash"] for goal in second["candidates"]}) == len(
        second["candidates"]
    )


def test_review_updates_the_derived_layer_only():
    dataset_id = uuid4()
    result = run_goal_build(dataset_id, arencia_sources())
    STORE.save(result)
    profit = next(goal for goal in result["candidates"] if goal["name"].startswith("提升"))

    reviewed = set_candidate_status(dataset_id, profit["id"], "confirmed")

    assert reviewed["graph_committed"] is False
    assert reviewed["committed"] is False
    assert reviewed["item"]["status"] == "confirmed"
    assert STORE.get_dataset(dataset_id)["graph_committed"] is False


@pytest.mark.asyncio
async def test_coverage_queues_canonical_goals_and_does_not_call_the_old_analyzer(monkeypatch):
    dataset_id = uuid4()
    result = run_goal_build(dataset_id, arencia_sources())
    STORE.save(result)

    async def explode(*_args, **_kwargs):
        raise AssertionError("company-tree analysis was called")

    monkeypatch.setattr("cognee.modules.teleology.coverage_sources.analyze_goal", explode)
    sources = ProductionSources()
    goal_ids, total = await sources.goal_page(dataset_id, object(), 0, 20)
    empty_ids, empty_total = await sources.goal_page(uuid4(), object(), 0, 20)

    assert total == 2
    assert set(goal_ids) == {goal["id"] for goal in result["candidates"]}
    assert empty_ids == []
    assert empty_total == 0
    proposal = await sources.analyze(dataset_id, object(), goal_ids[0], "coverage-run")
    assert proposal["graph_committed"] is False
    assert proposal["source_goal_id"] == goal_ids[0]
    assert proposal["items"]
    context = await sources.context(dataset_id, object(), goal_ids[0])
    assert context["source"] == "ai_goal_model"
    assert context["entities"]


@pytest.mark.asyncio
async def test_start_build_with_sources_does_not_read_the_graph(monkeypatch):
    async def allow(*_args, **_kwargs):
        return object()

    async def explode(*_args, **_kwargs):
        raise AssertionError("dataset graph was loaded")

    monkeypatch.setattr("cognee.modules.teleology.goal_build._authorized_dataset", allow)
    monkeypatch.setattr("cognee.modules.teleology.goal_build.load_dataset_sources", explode)
    view = await start_teleology_build(
        uuid4(),
        object(),
        mode="baseline",
        batch_size=2,
        concurrency=1,
        max_sources=20,
        sources=arencia_sources(),
    )

    assert view["committed"] is False
    assert view["graph_committed"] is False
    assert view["status"] == "completed"
    assert any(goal["name"] == "提升 Arencia 项目盈利能力" for goal in view["candidates"])
    assert any(row["source_class"] == "Responsibility" for row in view["classifications"])


def test_build_modules_do_not_commit_or_copy_the_tree():
    model = (ROOT / "cognee" / "modules" / "teleology" / "goal_model.py").read_text(
        encoding="utf-8"
    )
    build = (ROOT / "cognee" / "modules" / "teleology" / "goal_build.py").read_text(
        encoding="utf-8"
    )
    assert "commit_teleology_proposal" not in model
    assert "commit_teleology_proposal" not in build
    assert "get_graph_engine" not in model
    assert "has_subgoal" not in model
