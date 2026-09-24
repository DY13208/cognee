from pathlib import Path

import pytest

from cognee.infrastructure.engine.models.Edge import Edge
from cognee.modules.engine.models import Entity
from cognee.modules.graph.utils import get_graph_from_model
from cognee.modules.teleology.base_teleology_resolver import BaseTeleologyResolver
from cognee.modules.teleology.goal_scoped_retrieval import (
    apply_goal_scope,
    get_goal_scope_ids,
)
from cognee.modules.teleology.link_data_points_to_goals import link_data_points_to_goals
from cognee.modules.teleology.models import Constraint, Goal, Purpose
from cognee.modules.teleology.teleology_env_config import normalize_teleology_mode
from cognee.modules.teleology.yaml import YamlTeleologyResolver
from cognee.tasks.teleology.link_to_active_goals import link_to_active_goals


class MockTeleologyResolver(BaseTeleologyResolver):
    def __init__(self, goals: list[Goal]):
        self.goals = goals

    def get_goals(self) -> list[Goal]:
        return self.goals

    def get_purposes(self) -> list[Purpose]:
        return []

    def get_constraints(self) -> list[Constraint]:
        return []


def test_yaml_resolver_loads_goals_and_constraints(tmp_path: Path) -> None:
    teleology_file = tmp_path / "goals.yaml"
    teleology_file.write_text(
        """
goals:
  - id: 11111111-1111-4111-8111-111111111111
    name: Improve retrieval quality
    status: active
    keywords: [retrieval, relevance]
constraints:
  - id: 22222222-2222-4222-8222-222222222222
    name: Preserve isolation
    status: active
""".strip(),
        encoding="utf-8",
    )

    resolver = YamlTeleologyResolver(teleology_file)

    assert [goal.name for goal in resolver.get_active_goals()] == ["Improve retrieval quality"]
    assert [constraint.name for constraint in resolver.get_constraints()] == ["Preserve isolation"]


def test_annotate_adds_goal_edge_without_removing_existing_nodes() -> None:
    existing_target = Entity(name="Vector index", description="Existing node")
    source = Entity(
        name="Hybrid search",
        description="Improves retrieval relevance",
        relations=[(Edge(relationship_type="uses"), existing_target)],
    )
    goal = Goal(
        id="11111111-1111-4111-8111-111111111111",
        name="Improve retrieval quality",
        status="active",
        keywords=["retrieval", "relevance"],
    )

    result = link_data_points_to_goals([source, existing_target], [goal])

    assert result == [source, existing_target]
    assert (source.relations[0][0].relationship_type, source.relations[0][1]) == (
        "uses",
        existing_target,
    )
    assert any(
        edge.relationship_type in {"serves", "advances"} and target.id == goal.id
        for edge, target in source.relations
    )


@pytest.mark.asyncio
async def test_unconfigured_task_is_noop() -> None:
    nodes = [Entity(name="Unchanged", description="No teleology configured")]

    result = await link_to_active_goals(nodes, config={"teleology_config": {}})

    assert result is nodes
    assert nodes[0].relations == []


def test_mock_resolver_only_returns_active_goals() -> None:
    resolver = MockTeleologyResolver(
        [
            Goal(name="Active", status="active"),
            Goal(name="Later", status="proposed"),
        ]
    )

    assert [goal.name for goal in resolver.get_active_goals()] == ["Active"]


def test_annotation_is_idempotent_and_ignores_inactive_goals() -> None:
    source = Entity(name="Search", description="Retrieval relevance")
    active = Goal(name="Retrieval", status="active", keywords=["retrieval"])
    inactive = Goal(name="Search launch", status="achieved", keywords=["search"])
    resolver = MockTeleologyResolver([active, inactive])

    link_data_points_to_goals([source], resolver.get_active_goals())
    link_data_points_to_goals([source], resolver.get_active_goals())

    teleology_relations = [
        relation
        for relation in source.relations
        if relation[0].relationship_type in {"serves", "advances", "blocks"}
    ]
    assert len(teleology_relations) == 1
    assert teleology_relations[0][1].id == active.id


def test_chinese_keyword_match_and_constraint_blocking() -> None:
    source = Entity(name="检索降级", description="这个改动 weakens 检索隔离")
    goal = Goal(name="提升质量", status="active", keywords=["检索"])
    constraint = Constraint(name="保持隔离", status="active", keywords=["隔离"])

    link_data_points_to_goals([source], [goal], [constraint])

    assert {(edge.relationship_type, target.id) for edge, target in source.relations} == {
        ("serves", goal.id),
        ("blocks", constraint.id),
    }


def test_invalid_yaml_and_strict_mode_fail_explicitly(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("goals: not-a-list", encoding="utf-8")

    with pytest.raises(TypeError, match="entries must be a list"):
        YamlTeleologyResolver(invalid_file)
    with pytest.raises(NotImplementedError, match="not implemented"):
        normalize_teleology_mode("strict")


class MockGraphEngine:
    async def get_edges(self, node_id: str) -> list[tuple[dict, str, dict]]:
        edges = {
            "goal-1": [
                ({"id": "goal-1"}, "serves", {"id": "entity-1"}),
                ({"id": "goal-1"}, "unrelated", {"id": "entity-2"}),
            ],
            "entity-1": [
                ({"id": "entity-1"}, "contains", {"id": "chunk-1"}),
            ],
        }
        return edges.get(node_id, [])


class MockEdgeDataGraphEngine:
    """Neptune / interface-style ``(source_id, target_id, relationship, props)`` edges."""

    async def get_edges(self, node_id: str) -> list[tuple[str, str, str, dict]]:
        edges = {
            "goal-1": [
                ("goal-1", "entity-1", "serves", {}),
                ("goal-1", "entity-2", "unrelated", {}),
            ],
            "entity-1": [
                ("entity-1", "chunk-1", "contains", {}),
            ],
        }
        return edges.get(node_id, [])


@pytest.mark.asyncio
async def test_goal_scope_filters_and_reranks_results() -> None:
    scope_ids = await get_goal_scope_ids(MockGraphEngine(), "goal-1")
    results = [{"id": "chunk-2"}, {"id": "chunk-1"}]

    assert scope_ids == {"entity-1", "chunk-1"}
    assert apply_goal_scope(results, scope_ids, "filter") == [{"id": "chunk-1"}]
    assert apply_goal_scope(results, scope_ids, "rerank") == [
        {"id": "chunk-1"},
        {"id": "chunk-2"},
    ]


@pytest.mark.asyncio
async def test_goal_scope_accepts_interface_edge_tuples() -> None:
    scope_ids = await get_goal_scope_ids(MockEdgeDataGraphEngine(), "goal-1")
    assert scope_ids == {"entity-1", "chunk-1"}


@pytest.mark.asyncio
async def test_annotated_goal_edge_reaches_storage_graph_conversion() -> None:
    source = Entity(name="Semantic search", description="Improves retrieval")
    goal = Goal(name="Improve retrieval", status="active", keywords=["retrieval"])
    link_data_points_to_goals([source], [goal])

    nodes, edges = await get_graph_from_model(source)

    assert {str(node.id) for node in nodes} >= {str(source.id), str(goal.id)}
    assert any(
        str(edge[0]) == str(source.id)
        and str(edge[1]) == str(goal.id)
        and edge[2] in {"serves", "advances"}
        for edge in edges
    )


@pytest.mark.asyncio
async def test_task_annotates_with_yaml_resolver(tmp_path: Path) -> None:
    teleology_file = tmp_path / "goals.yaml"
    teleology_file.write_text(
        """
goals:
  - id: 11111111-1111-4111-8111-111111111111
    name: Improve retrieval quality
    status: active
    keywords: [retrieval]
""".strip(),
        encoding="utf-8",
    )
    source = Entity(name="Hybrid search", description="Improves retrieval relevance")
    resolver = YamlTeleologyResolver(teleology_file)

    result = await link_to_active_goals(
        [source],
        config={"teleology_config": {"teleology_resolver": resolver, "teleology_mode": "annotate"}},
    )

    assert result is not None
    assert any(
        edge.relationship_type in {"serves", "advances"}
        and str(target.id) == "11111111-1111-4111-8111-111111111111"
        for edge, target in source.relations
    )
