"""Regression cases from the ten-goal production proposal audit."""

import json

import pytest

from cognee.modules.teleology import purpose_analyze
from cognee.modules.teleology.proposal_rules import partition_ai_items


def _context():
    return {
        "goal": {"id": "current", "name": "Current", "type": "Goal"},
        "ancestors": [
            {"id": "root", "name": "Root", "type": "Goal"},
            {"id": "parent", "name": "Parent", "type": "Goal"},
        ],
        "children": [{"id": "child", "name": "Child", "type": "Goal"}],
        "purposes": [],
        "constraints": [{"id": "constraint", "name": "Legal limit", "type": "Constraint"}],
        "entities": [],
        "documents": [
            {"id": "document", "name": "Decision", "type": "Document"},
            {"id": "map", "name": "Linked map", "type": "MapReference"},
        ],
        "child_evidence": [
            {
                "goal_id": "child",
                "documents": [
                    {
                        "id": "child-document",
                        "name": "Child proof",
                        "type": "Document",
                    }
                ],
            }
        ],
        "relations": [
            {
                "source_id": "other",
                "source_name": "Other branch",
                "source_type": "Goal",
                "target_id": "root",
                "target_name": "Root",
                "target_type": "Goal",
                "relationship": "serves",
            }
        ],
    }


@pytest.mark.parametrize(
    ("source", "relationship", "target", "evidence", "reason", "expected"),
    [
        ("current", "serves", "parent", ["current", "parent"], "业务目标一致", False),
        ("current", "advances", "root", ["root", "parent"], "业务目标一致", False),
        ("child", "serves", "current", ["child", "current"], "业务目标一致", False),
        ("current", "blocks", "parent", ["constraint", "document"], "法规明确限制预算", True),
        ("current", "serves", "parent", ["map"], "关联业务图证明上级价值", True),
        ("child", "serves", "current", ["child-document"], "子项目文档说明业务价值", True),
        ("current", "serves", "other", ["document"], "决策文档证明跨分支贡献", True),
        ("current", "serves", "parent", ["document"], "结构上明确归属", False),
        ("current", "advances", "parent", ["document"], "符合 goal tree 结构", False),
    ],
)
def test_hierarchy_requires_independent_semantic_evidence(
    source, relationship, target, evidence, reason, expected
):
    body = purpose_analyze.normalize_analysis(
        _context(),
        {
            "relations": [
                {
                    "source_ref": source,
                    "relationship": relationship,
                    "target_ref": target,
                    "reason": reason,
                    "confidence": 0.8,
                    "evidence_node_ids": evidence,
                }
            ],
        },
    )
    assert bool(body["relations"]) is expected
    if not expected:
        assert body["weak_signals"][0]["weak_reason"] == "structural_hierarchy_only"


def test_partition_blocks_external_hierarchy_relation_and_open_purpose_echo():
    context = _context()
    relation = {
        "kind": "relation",
        "source": "current",
        "target": "parent",
        "relationship": "blocks",
        "reason": "业务目标一致",
        "confidence": 0.9,
        "evidence_node_ids": ["current", "parent"],
    }
    duplicate = {
        "kind": "purpose",
        "name": "Accurate profit",
        "reason": "document proves it",
        "confidence": 0.9,
        "evidence_node_ids": ["document"],
    }
    kept, weak, conflicts, _ = partition_ai_items(
        [relation, duplicate],
        generated_by="purpose-agent",
        context=context,
        open_items=[
            {
                "id": "open-item",
                "proposal_id": "open-proposal",
                "kind": "purpose",
                "name": "Accurate profit",
            }
        ],
    )
    assert kept == []
    assert weak[0]["weak_reason"] == "structural_hierarchy_only"
    assert len(conflicts) == 1 and conflicts[0]["proposal_id"] == "open-proposal"


def test_open_proposal_is_not_prompt_or_evidence():
    context = _context()
    open_items = [
        {
            "id": "open-item",
            "proposal_id": "open-proposal",
            "kind": "purpose",
            "name": "Secret open Purpose",
            "status": "proposed",
        }
    ]
    prompt = purpose_analyze._prompt_context(context, open_items)
    assert "open_proposal_names" not in prompt
    assert "Secret open Purpose" not in json.dumps(prompt)
    assert "Open/uncommitted proposals are not evidence" in purpose_analyze._SYSTEM
    body = purpose_analyze.normalize_analysis(
        context,
        {
            "purposes": [
                {
                    "name": "New purpose",
                    "reason": "from another proposal",
                    "confidence": 0.8,
                    "evidence_node_ids": ["open-item"],
                }
            ],
        },
        open_items,
    )
    assert body["purposes"] == []
