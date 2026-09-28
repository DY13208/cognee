import pytest

from cognee.modules.teleology.graph_annotations import (
    _attach_known_fields,
    _epoch_ms,
    _index_graph,
    _is_annotatable,
    _token_overlap,
)


def test_index_graph_hides_structural_advances() -> None:
    nodes = [
        ("parent", {"name": "公司运营", "type": "Goal"}),
        ("child", {"name": "韩国公司", "type": "Goal"}),
    ]
    edges = [
        ("parent", "child", "has_subgoal", {}),
        ("child", "parent", "advances", {"origin": "system_derived"}),
        ("child", "parent", "advances", {}),
        (
            "child",
            "parent",
            "advances",
            {
                "origin": "ai_inferred",
                "reason": "文档说明韩国公司推进公司运营",
                "evidence_node_ids": ["doc-1"],
            },
        ),
    ]
    _by_id, annotations = _index_graph(nodes, edges)
    assert len(annotations) == 1
    assert annotations[0]["origin"] == "ai_inferred"


def test_index_graph_finds_teleology_edges() -> None:
    nodes = [
        ("e1", {"name": "Hybrid search", "type": "Entity"}),
        ("g1", {"name": "Improve retrieval", "type": "Goal", "status": "active"}),
        ("chunk", {"name": "chunk-0", "type": "DocumentChunk"}),
    ]
    edges = [
        ("e1", "g1", "serves", {"edge_text": "serves"}),
        ("e1", "chunk", "is_part_of", {}),
    ]

    by_id, annotations = _index_graph(nodes, edges)

    assert "e1" in by_id
    assert len(annotations) == 1
    assert annotations[0]["relationship"] == "serves"
    assert annotations[0]["source_name"] == "Hybrid search"
    assert annotations[0]["target_name"] == "Improve retrieval"


def test_annotatable_skips_goals_and_chunks() -> None:
    assert _is_annotatable({"name": "Hybrid search", "type": "Entity"})
    assert not _is_annotatable({"name": "Improve retrieval", "type": "Goal"})
    assert not _is_annotatable({"name": "chunk-0", "type": "DocumentChunk"})
    assert not _is_annotatable({"type": "Entity"})  # unnamed


def test_epoch_ms_reads_graph_timestamps() -> None:
    assert _epoch_ms(1_700_000_000_000) == 1_700_000_000_000
    assert _epoch_ms("2026-01-02 03:04:05.000000") == 1767323045000


class _Graph:
    def __init__(self, answers: dict[str, list]) -> None:
        self.answers = answers

    async def query(self, statement: str, _params: dict | None = None):
        for needle, rows in self.answers.items():
            if needle in statement:
                return rows
        return []


@pytest.mark.asyncio
async def test_known_fields_fill_created_at_and_purpose() -> None:
    graph = _Graph(
        {
            "n.created_at": [("child", "2026-01-02 03:04:05.000000"), ("root", None)],
            "relationship_name = 'serves'": [("child", "root")],
        }
    )
    rows = await _attach_known_fields(
        graph,
        [
            {"id": "child", "parent_id": "root", "created_at": None, "primary_purpose_id": None},
            {"id": "plain", "parent_id": "root", "created_at": None, "primary_purpose_id": None},
            {"id": "root", "parent_id": None, "created_at": None, "primary_purpose_id": None},
            {
                "id": "kept",
                "parent_id": "other",
                "created_at": 5,
                "primary_purpose_id": "stored",
                "primary_purpose_relation": "advances",
            },
        ],
    )
    assert rows[0]["created_at"] == 1767323045000
    assert rows[0]["primary_purpose_id"] == "root"
    assert rows[0]["primary_purpose_relation"] == "serves"
    assert rows[1]["primary_purpose_id"] is None
    assert rows[2]["primary_purpose_id"] is None
    assert rows[3]["primary_purpose_id"] == "stored"
    assert rows[3]["created_at"] == 5


@pytest.mark.asyncio
async def test_sync_does_not_create_name_overlap_serves(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    from cognee.modules.teleology import graph_annotations

    parent = SimpleNamespace(id="parent", kind="goal", name="检索质量", note="提升检索质量")
    child = SimpleNamespace(id="child", kind="goal", name="周报", note="")
    tree = SimpleNamespace(
        nodes=[parent, child],
        edges=[SimpleNamespace(label="has_subgoal", source="parent", target="child")],
    )

    class Graph:
        def __init__(self):
            self.edges = []

        async def has_edge(self, *_args):
            return False

        async def add_edges(self, edges):
            self.edges.extend(edges)

        async def query(self, *_args, **_kwargs):
            return []

        async def get_filtered_graph_data(self, *_args):
            return ([("entity-1", {"name": "检索质量周报", "type": "Entity"})], [])

    graph = Graph()

    async def company_tree(*_args, **_kwargs):
        return tree

    async def engine():
        return graph

    async def authorized(*_args, **_kwargs):
        return SimpleNamespace(owner_id=uuid4())

    @asynccontextmanager
    async def context(*_args, **_kwargs):
        yield

    monkeypatch.setattr("cognee.modules.company_tree.upsert.get_company_tree", company_tree)
    monkeypatch.setattr(graph_annotations, "_authorized_dataset", authorized)
    monkeypatch.setattr("cognee.infrastructure.databases.graph.get_graph_engine", engine)
    monkeypatch.setattr(
        "cognee.context_global_variables.set_database_global_context_variables", context
    )
    result = await graph_annotations.sync_from_company_tree(
        uuid4(), SimpleNamespace(), link_entities=True
    )
    assert result["serves_created"] == 0
    assert all(edge[2] != "serves" for edge in graph.edges)
    advances = [edge for edge in graph.edges if edge[2] == "advances"]
    assert advances[0][3]["origin"] == "system_derived"
    assert advances[0][3]["retrieval_only"] == "true"


def test_token_overlap_matches_chinese_and_substring() -> None:
    assert _token_overlap("提升检索质量", "检索质量目标")
    assert _token_overlap("Hybrid search", "Improve hybrid search ranking")
    assert not _token_overlap("alpha", "beta gamma")
