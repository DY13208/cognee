from cognee.modules.teleology.graph_annotations import _index_graph, _is_annotatable, _token_overlap


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


def test_token_overlap_matches_chinese_and_substring() -> None:
    assert _token_overlap("提升检索质量", "检索质量目标")
    assert _token_overlap("Hybrid search", "Improve hybrid search ranking")
    assert not _token_overlap("alpha", "beta gamma")
