from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cognee.modules.teleology import purpose_layer


@asynccontextmanager
async def _context(*_args):
    yield


class FakeGraph:
    def __init__(self):
        self.nodes = {"korea": {"id": "korea", "name": "韩国公司", "type": "Goal"}}
        self.added_nodes = []
        self.added_edges = []
        self.queries = []

    async def get_node(self, node_id):
        return self.nodes.get(node_id)

    async def add_nodes(self, nodes):
        self.added_nodes.extend(nodes)
        for node in nodes:
            self.nodes[str(node.id)] = {"id": str(node.id), "type": node.type}

    async def add_edges(self, edges):
        self.added_edges.extend(edges)

    async def query(self, query, params=None):
        self.queries.append(query)
        if "p.id IN $ids" in query:
            return getattr(self, "tree_pairs", [])
        if "RETURN count(c)" in query:
            return [(1,)]
        if "RETURN c.id, c.name, c.type" in query:
            return [("tax", "税务", "Goal", "{}")]
        if "RETURN c.id, c.name" in query:
            return [("tax", "税务")]
        return []


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        purpose_layer, "_store_path", lambda dataset_id: tmp_path / f"{dataset_id}.json"
    )

    async def detail(*_args, **_kwargs):
        return {
            "goal": {"id": "korea", "name": "韩国公司", "type": "Goal", "description": "税务与外汇"}
        }

    async def path(*_args, **_kwargs):
        return {
            "path": [{"id": "finance", "name": "公司财务"}, {"id": "korea", "name": "韩国公司"}]
        }

    async def relations(*_args, **_kwargs):
        return {"items": [], "counts": {"serves": 0, "advances": 0, "blocks": 0}}

    async def authorized(*_args, **_kwargs):
        return SimpleNamespace(owner_id=uuid4())

    fake = FakeGraph()

    async def engine():
        return fake

    monkeypatch.setattr(purpose_layer, "goal_detail", detail)
    monkeypatch.setattr(purpose_layer, "goal_path", path)
    monkeypatch.setattr(purpose_layer, "goal_relations", relations)
    monkeypatch.setattr(purpose_layer, "_authorized_dataset", authorized)
    monkeypatch.setattr(purpose_layer, "get_graph_engine", engine)
    monkeypatch.setattr(purpose_layer, "set_database_global_context_variables", _context)
    return fake


@pytest.mark.asyncio
async def test_propose_stays_out_of_the_graph(storage):
    dataset_id = uuid4()
    proposal = await purpose_layer.propose_teleology(
        dataset_id,
        SimpleNamespace(),
        source_goal_id="korea",
        proposal={
            "purposes": [
                {
                    "name": "保障韩国业务长期稳定经营",
                    "description": "税务、注册和外汇共同服务的结果",
                    "confidence": 0.9,
                    "reason": "四个下级都在维持主体可经营",
                    "source_goal_ids": ["korea"],
                }
            ],
            "relations": [
                {
                    "source": "税务",
                    "relationship": "advances",
                    "target": "保障韩国业务长期稳定经营",
                    "reason": "税务是合规的一部分",
                    "confidence": 0.8,
                }
            ],
        },
    )
    assert storage.added_nodes == []
    assert storage.added_edges == []
    assert proposal["items"][0]["review_status"] == "proposed"
    assert proposal["summary"]["purposes"] == 1


@pytest.mark.asyncio
async def test_propose_drops_tree_copy_without_its_own_reason(storage):
    storage.tree_pairs = [("korea", "tax")]
    proposal = await purpose_layer.propose_teleology(
        uuid4(),
        SimpleNamespace(),
        source_goal_id="korea",
        proposal={
            "relations": [
                {"source": "tax", "relationship": "advances", "target": "korea"},
                {
                    "source": "tax",
                    "relationship": "advances",
                    "target": "korea",
                    "reason": "税务合规是经营前提",
                    "evidence_node_ids": ["doc-1"],
                },
            ]
        },
    )
    relations = [item for item in proposal["items"] if item["kind"] == "relation"]
    assert len(relations) == 1
    assert relations[0]["evidence_node_ids"] == ["doc-1"]
    assert storage.added_edges == []


@pytest.mark.asyncio
async def test_invalid_relation_is_rejected(storage):
    with pytest.raises(ValueError, match="serves, advances, or blocks"):
        await purpose_layer.propose_teleology(
            uuid4(),
            SimpleNamespace(),
            source_goal_id="korea",
            proposal={"relations": [{"source": "a", "relationship": "contains", "target": "b"}]},
        )


@pytest.mark.asyncio
async def test_commit_writes_only_accepted_inferred_nodes(storage):
    dataset_id = uuid4()
    proposal = await purpose_layer.propose_teleology(
        dataset_id,
        SimpleNamespace(),
        source_goal_id="korea",
        proposal={
            "purposes": [
                {
                    "name": "稳定经营",
                    "reason": "下级缺少共同结果",
                    "confidence": 0.91,
                    "source_goal_ids": ["korea"],
                }
            ],
            "goals": [{"name": "不会写入的建议", "reason": "未接受", "source_goal_ids": ["korea"]}],
            "relations": [
                {
                    "source": "稳定经营",
                    "relationship": "serves",
                    "target": "korea",
                    "reason": "韩国公司服务于这个目的",
                }
            ],
            "items": [
                {
                    "kind": "gap",
                    "name": "韩国公司",
                    "reason": "还没有确认目的",
                    "source_goal_ids": ["korea"],
                }
            ],
        },
    )
    purpose = next(item for item in proposal["items"] if item["kind"] == "purpose")
    relation = next(item for item in proposal["items"] if item["kind"] == "relation")
    gap = next(item for item in proposal["items"] if item["kind"] == "gap")
    result = await purpose_layer.commit_teleology_proposal(
        dataset_id,
        SimpleNamespace(),
        proposal["id"],
        [purpose["id"], relation["id"], gap["id"]],
        edits={purpose["id"]: {"name": "保障韩国业务长期稳定经营"}},
    )
    assert len(result["committed_nodes"]) == 1
    node = storage.added_nodes[0]
    assert node.name == "保障韩国业务长期稳定经营"
    assert node.source == "ai_inferred"
    assert node.review_status == "accepted"
    assert node.proposal_id == proposal["id"]
    assert storage.added_edges[0][2] == "serves"
    assert storage.added_edges[0][3]["origin"] == "ai_inferred"
    assert all(edge[2] != "has_subgoal" for edge in storage.added_edges)
    assert gap["id"] in result["skipped_item_ids"]


@pytest.mark.asyncio
async def test_context_is_local_and_review_does_not_invent_a_purpose(storage):
    context = await purpose_layer.get_purpose_context(uuid4(), SimpleNamespace(), "korea")
    assert context["goal"]["name"] == "韩国公司"
    assert context["children"][0]["name"] == "税务"
    assert context["missing_purpose"] is True
    assert any("LIMIT 40" in query for query in storage.queries)
    assert any("LIMIT 20" in query for query in storage.queries)
    review = await purpose_layer.start_purpose_review(uuid4(), SimpleNamespace(), "korea")
    assert review["summary"]["purposes"] == 0
    assert review["summary"]["missing_purpose"] >= 1
    assert all(item["kind"] == "gap" for item in review["items"])
