from cognee.modules.teleology.purpose_relations import (
    confirmed_counts_for_goals,
    select_purpose_relations,
)

PAIRS = {("parent", "child")}


def _edge(source, target, relationship, properties=None):
    return {
        "source_id": source,
        "target_id": target,
        "relationship": relationship,
        "properties": properties or {},
    }


def test_structural_advances_are_not_purpose_relations():
    selected = select_purpose_relations(
        [
            _edge("child", "parent", "advances", {"origin": "system_derived"}),
            _edge("child", "parent", "advances"),
            _edge("parent", "child", "advances"),
            _edge(
                "child",
                "parent",
                "advances",
                {"origin": "manual", "reason": "子目标在语义上推进父目标"},
            ),
            _edge(
                "child",
                "parent",
                "advances",
                {"origin": "ai_inferred", "evidence_node_ids": ["child", "parent"]},
            ),
            _edge(
                "child",
                "parent",
                "advances",
                {"origin": "ai_inferred", "reason": "只有理由，没有独立证据"},
            ),
            _edge(
                "sibling",
                "parent",
                "advances",
                {"origin": "system_derived", "retrieval_only": "true", "reason": "检索副本"},
            ),
            _edge(
                "other",
                "parent",
                "advances",
                {
                    "origin": "ai_inferred",
                    "reason": "文档说明它推进这个目标",
                    "evidence_node_ids": ["doc-1"],
                },
            ),
        ],
        PAIRS,
    )
    keys = [(edge["source_id"], edge["relationship"], edge["target_id"]) for edge in selected]
    assert ("child", "advances", "parent") in keys
    assert keys.count(("child", "advances", "parent")) == 1
    assert ("parent", "advances", "child") not in keys
    assert ("other", "advances", "parent") in keys


def test_duplicate_real_edges_collapse_and_system_derived_never_counts():
    selected = select_purpose_relations(
        [
            _edge("goal", "purpose", "serves", {"origin": "system_derived", "reason": "结构复制"}),
            _edge("goal", "purpose", "serves", {"origin": "manual", "reason": "服务于稳定经营"}),
            _edge("goal", "purpose", "serves", {"origin": "manual", "reason": "较短"}),
        ],
        set(),
    )
    assert len(selected) == 1
    assert selected[0]["properties"]["reason"] == "服务于稳定经营"


def test_confirmed_counts_ignore_structural_advances_and_include_purpose_nodes():
    counts = confirmed_counts_for_goals(
        [
            _edge("child", "parent", "advances", {"origin": "system_derived"}),
            _edge("goal", "other", "advances", {"origin": "manual", "reason": "推进利润"}),
            {
                "source_id": "goal",
                "source_type": "Goal",
                "target_id": "purpose",
                "target_type": "Purpose",
                "relationship": "serves",
                "properties": {"origin": "manual", "reason": "为了利润"},
            },
        ],
        PAIRS,
        ["goal", "child"],
    )
    assert counts["goal"] == 3
    assert counts["child"] == 0
