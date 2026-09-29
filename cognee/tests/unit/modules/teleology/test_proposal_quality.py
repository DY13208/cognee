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
        ("current", "serves", "parent", ["document"], "结构上明确归属", True),
        ("current", "advances", "parent", ["document"], "符合 goal tree 结构", True),
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


def _draft(source, relationship, target, evidence, reason, confidence=0.8):
    return {
        "relations": [
            {
                "source_ref": source,
                "relationship": relationship,
                "target_ref": target,
                "reason": reason,
                "confidence": confidence,
                "evidence_node_ids": evidence,
            }
        ]
    }


@pytest.mark.parametrize(
    ("source", "relationship", "target", "evidence"),
    [
        ("current", "serves", "child", ["current", "child"]),
        ("current", "advances", "child", ["current", "child", "parent"]),
        ("current", "blocks", "child", ["current", "child", "parent", "root"]),
        ("child", "serves", "current", ["child", "current"]),
        ("current", "serves", "parent", ["current", "parent"]),
        ("current", "advances", "root", ["current", "root"]),
        ("root", "serves", "current", ["root", "current"]),
        ("parent", "advances", "current", ["parent", "current"]),
    ],
)
def test_hierarchy_chain_is_blocked_in_both_directions(source, relationship, target, evidence):
    body = purpose_analyze.normalize_analysis(
        _context(),
        _draft(source, relationship, target, evidence, "业务上有关联", 0.99),
    )
    assert body["relations"] == []
    assert body["weak_signals"][0]["weak_reason"] == "structural_hierarchy_only"
    assert body["weak_signals"][0]["confidence"] == 0.99


@pytest.mark.parametrize(
    ("evidence",),
    [
        (["document"],),
        (["constraint"],),
    ],
)
def test_hierarchy_relation_survives_with_independent_evidence(evidence):
    body = purpose_analyze.normalize_analysis(
        _context(),
        _draft("current", "serves", "child", evidence, "独立材料说明该子目标承接成交结果"),
    )
    assert len(body["relations"]) == 1
    assert body["weak_signals"] == []


def test_cross_branch_goal_relation_with_independent_evidence_is_kept():
    body = purpose_analyze.normalize_analysis(
        _context(),
        _draft("current", "serves", "other", ["document"], "决策文档证明跨分支贡献"),
    )
    assert body["relations"][0]["target"] == "other"
    assert body["weak_signals"] == []


def test_structural_wording_without_independent_evidence_is_not_formal():
    body = purpose_analyze.normalize_analysis(
        _context(),
        _draft(
            "current",
            "serves",
            "child",
            ["current", "child"],
            "目标命名层级与路径位置构成强结构性证据",
            0.99,
        ),
    )
    assert body["relations"] == []
    assert body["weak_signals"][0]["weak_reason"] == "structural_hierarchy_only"


def test_hierarchy_only_context_prompt_expects_no_relations():
    context = {
        "goal": {"id": "current", "name": "会员成交验证", "type": "Goal"},
        "ancestors": [{"id": "parent", "name": "会员", "type": "Goal"}],
        "children": [{"id": "child", "name": "会员复购率", "type": "Goal"}],
        "purposes": [],
        "constraints": [],
        "entities": [],
        "documents": [],
        "relations": [],
        "child_evidence": [],
    }
    prompt = purpose_analyze._prompt_context(context, [])
    assert prompt["documents"] == []
    assert prompt["entities"] == []
    assert prompt["purposes"] == []
    assert prompt["constraints"] == []
    system = purpose_analyze._SYSTEM
    assert "Company Tree hierarchy is already known fact." in system
    assert "Parent/child/ancestor/path/name adjacency is NOT semantic evidence." in system
    assert "Do not emit it as a weak guess either." in system
    assert "Simply omit it." in system
    obeyed = purpose_analyze.normalize_analysis(context, {"relations": []})
    assert obeyed["relations"] == []
    assert obeyed["weak_signals"] == []


def test_document_context_can_keep_a_semantic_relation():
    context = _context()
    prompt = purpose_analyze._prompt_context(context, [])
    assert prompt["documents"]
    body = purpose_analyze.normalize_analysis(
        context,
        _draft("current", "serves", "other", ["document"], "决策文档说明跨分支业务贡献"),
    )
    assert body["relations"]
    assert "支撑 X 项目目标达成" in purpose_analyze._SYSTEM
    assert "Do not merge purposes that name different projects." in purpose_analyze._SYSTEM


def test_distinct_project_purposes_are_not_collapsed():
    body = purpose_analyze.normalize_analysis(
        _context(),
        {
            "purposes": [
                {
                    "name": "支撑 NUDARA 项目利润目标达成",
                    "reason": "该项目自己的利润结果",
                    "confidence": 0.8,
                    "evidence_node_ids": ["document"],
                },
                {
                    "name": "支撑 ETUDE 项目利润目标达成",
                    "reason": "另一个项目自己的利润结果",
                    "confidence": 0.8,
                    "evidence_node_ids": ["document"],
                },
            ]
        },
    )
    assert [item["name"] for item in body["purposes"]] == [
        "支撑 NUDARA 项目利润目标达成",
        "支撑 ETUDE 项目利润目标达成",
    ]
