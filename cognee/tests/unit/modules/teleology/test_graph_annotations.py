import pytest

from cognee.modules.teleology.graph_annotations import (
    _attach_known_fields,
    _epoch_ms,
    _index_graph,
    _is_annotatable,
    _token_overlap,
)


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
    assert rows[2]["primary_purpose_id"] == "stored"
    assert rows[2]["created_at"] == 5


def test_token_overlap_matches_chinese_and_substring() -> None:
    assert _token_overlap("提升检索质量", "检索质量目标")
    assert _token_overlap("Hybrid search", "Improve hybrid search ranking")
    assert not _token_overlap("alpha", "beta gamma")
