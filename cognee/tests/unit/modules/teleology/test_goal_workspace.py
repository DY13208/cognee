from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cognee.modules.teleology import goal_workspace


@asynccontextmanager
async def _context(*_args):
    yield


class FakeGraph:
    def __init__(self):
        self.nodes = {
            "root": {"name": "Company", "type": "Goal"},
            "child": {"name": "Finance", "type": "Goal", "source": "teleology_workspace"},
        }
        self.parents = {"child": "root"}
        self.queries = []
        self.added_nodes = []
        self.added_edges = []
        self.deleted_nodes = []

    async def get_node(self, node_id):
        return self.nodes.get(node_id)

    async def query(self, query, params=None):
        self.queries.append((query, params))
        if "ORDER BY p.id" in query:
            parent = self.parents.get(params["id"])
            return [(parent,)] if parent else []
        if "RETURN p.id, c.id" in query:
            return [("root", "child")]
        if "r.properties" in query:
            return [
                (
                    "child",
                    "Finance",
                    "Goal",
                    "root",
                    "Company",
                    "Goal",
                    "advances",
                    '{"origin": "system_derived"}',
                ),
                ("child", "Finance", "Goal", "root", "Company", "Goal", "advances", None),
                (
                    "child",
                    "Finance",
                    "Goal",
                    "stable",
                    "稳定经营",
                    "Purpose",
                    "serves",
                    '{"origin": "manual", "reason": "财务目标服务于稳定经营"}',
                ),
                (
                    "child",
                    "Finance",
                    "Goal",
                    "stable",
                    "稳定经营",
                    "Purpose",
                    "serves",
                    '{"origin": "manual", "reason": "财务目标服务于稳定经营"}',
                ),
            ]
        return []

    async def add_nodes(self, nodes):
        self.added_nodes.extend(nodes)

    async def add_edges(self, edges):
        self.added_edges.extend(edges)

    async def delete_nodes(self, ids):
        self.deleted_nodes.extend(ids)


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()

    async def authorized(*_args):
        return SimpleNamespace(owner_id=uuid4())

    async def engine():
        return fake

    monkeypatch.setattr(goal_workspace, "_authorized_dataset", authorized)
    monkeypatch.setattr(goal_workspace, "get_graph_engine", engine)
    monkeypatch.setattr(goal_workspace, "set_database_global_context_variables", _context)
    return fake


@pytest.mark.asyncio
async def test_path_reads_only_ancestor_chain(graph):
    result = await goal_workspace.goal_path(uuid4(), SimpleNamespace(), "child")
    assert [item["name"] for item in result["path"]] == ["Company", "Finance"]
    assert sum("ORDER BY p.id" in query for query, _params in graph.queries) == 2


@pytest.mark.asyncio
async def test_relation_counts_drop_structural_and_duplicate_edges(graph):
    result = await goal_workspace.goal_relations(
        uuid4(), SimpleNamespace(), "child", relationship="serves", limit=30, offset=0
    )
    assert result["counts"] == {"serves": 1, "advances": 0, "blocks": 0}
    assert result["total"] == 1
    assert result["items"][0]["target_name"] == "稳定经营"
    assert result["items"][0]["origin"] == "manual"


@pytest.mark.asyncio
async def test_imported_goal_cannot_be_moved(graph):
    with pytest.raises(ValueError, match="Only goals created"):
        await goal_workspace.move_goal(uuid4(), SimpleNamespace(), "root", "child")


@pytest.mark.asyncio
async def test_create_goal_writes_one_child_edge(graph):
    result = await goal_workspace.create_goal(
        uuid4(), SimpleNamespace(), parent_id="root", name="Budget"
    )
    assert result["goal"]["name"] == "Budget"
    assert result["goal"]["source"] == "teleology_workspace"
    assert len(graph.added_nodes) == 1
    assert graph.added_edges[0][0] == "root"
    assert graph.added_edges[0][2] == "has_subgoal"


@pytest.mark.asyncio
async def test_move_rejects_descendant_cycle(graph):
    graph.nodes["grandchild"] = {"name": "Tax", "type": "Goal", "source": "teleology_workspace"}
    graph.parents["grandchild"] = "child"
    with pytest.raises(ValueError, match="cycle"):
        await goal_workspace.move_goal(uuid4(), SimpleNamespace(), "child", "grandchild")


@pytest.mark.asyncio
async def test_delete_native_leaf(graph):
    result = await goal_workspace.delete_goal(uuid4(), SimpleNamespace(), "child")
    assert result["deleted"] is True
    assert graph.deleted_nodes == ["child"]
