from copy import deepcopy

from cognee.modules.teleology.sop_context import context_from_snapshot
from cognee.modules.teleology.sop_generator import generate_sop_proposal
from cognee.modules.teleology.sop_validator import validate_sop_proposal

ROOM = "room-rujw4n4j"
NODE = "e1bd00ff-1f82-4a95-946e-7da665876c91"
SOURCE_KEY = f"mindmap:{ROOM}:{NODE}"
TREE_ID = "ct-profit"
REF_UID = "ref-profit-model"
GMV_UID = "file-gmv"
GSV_UID = "file-gsv"
CHILD = "child-fill-profit"


def _tree(node_id: str, room: str, uid: str, name: str = "利润目标") -> dict:
    return {
        "id": node_id,
        "name": name,
        "source_room": room,
        "source_uid": uid,
        "source_key": f"mindmap:{room}:{uid}",
    }


def _goal(goal_id: str, name: str, node_id: str) -> dict:
    return {
        "id": goal_id,
        "name": name,
        "status": "confirmed",
        "parent_candidate_id": "root",
        "source_node_ids": [node_id],
        "evidence": [{"node_id": node_id}],
    }


def _snapshot() -> dict:
    return {
        "run_id": "f7d609ae-4e88-4e4f-b8b3-523e92246bd4",
        "candidates": [
            {"id": "root", "name": "公司目标", "status": "confirmed"},
            _goal("g-profit", "项目利润", TREE_ID),
        ],
        "purposes": [
            {
                "id": "purpose-1",
                "goal_id": "g-profit",
                "name": "提高项目利润",
                "status": "confirmed",
            }
        ],
        "constraints": [
            {
                "id": "constraint-year",
                "goal_id": "g-profit",
                "name": "年度总目标确定后不可修改（季度可复盘一次）",
                "status": "confirmed",
            }
        ],
        "relations": [],
    }


def _mindmap() -> dict:
    return {
        "target": {"uid": NODE, "name": "P：制定项目利润目标"},
        "path": [{"uid": "ancestor-1", "name": "项目经营"}],
        "children": [{"uid": CHILD, "name": "填写项目利润测算"}],
        "notes": [],
        "references": [{"uid": REF_UID, "name": "利润测算模型"}],
        "attachments": [
            {"uid": GMV_UID, "name": "GMV 目标表"},
            {"uid": GSV_UID, "name": "GSV 目标表"},
        ],
    }


def _request(**overrides) -> dict:
    payload = {
        "dataset_id": "dd3aa689-ec26-5887-9730-310eec869d1c",
        "room_key": ROOM,
        "node_uid": NODE,
        "source_uids": [NODE],
        "mindmap_context": _mindmap(),
    }
    payload.update(overrides)
    return payload


def _context(snapshot=None, request=None, nodes=None):
    return context_from_snapshot(
        snapshot if snapshot is not None else _snapshot(),
        request if request is not None else _request(),
        [] if nodes is None else nodes,
    )


def test_mindmap_uid_resolves_exact_source_key_without_caller_conversion():
    snapshot = _snapshot()
    request = _request()
    original_snapshot = deepcopy(snapshot)
    original_mindmap = deepcopy(request["mindmap_context"])
    context = _context(snapshot, request, [_tree(TREE_ID, ROOM, NODE, "其他名称")])
    assert snapshot == original_snapshot
    assert request["mindmap_context"] == original_mindmap
    resolution = context["source_resolution"]
    assert resolution["resolved_count"] > 0
    target = next(ref for ref in context["source_refs"] if ref["mindmap_uid"] == NODE)
    assert target["resolution_status"] == "EXACT"
    assert target["source_key"] == SOURCE_KEY
    assert target["company_tree_node_id"] == TREE_ID
    assert context["primary_goal"]["id"] == "g-profit"
    assert context["related_goals"]
    assert context["goal_resolution_status"] == "RESOLVED"


def test_unresolved_source_is_reported():
    nodes = [_tree("ct-other", ROOM, "someone-else", "P：制定项目利润目标")]
    context = _context(nodes=nodes)
    target = next(ref for ref in context["source_refs"] if ref["mindmap_uid"] == NODE)
    assert target["resolution_status"] == "NOT_FOUND"
    assert target["company_tree_node_id"] is None
    assert target["source_key"] == SOURCE_KEY
    assert context["source_resolution"]["unresolved"]
    assert context["primary_goal"] is None
    assert context["warnings"]
    assert context["goal_resolution_reason"]


def test_ambiguous_source_is_not_silent():
    nodes = [
        _tree("ct-1", ROOM, NODE, "利润目标"),
        _tree("ct-2", ROOM, NODE, "利润目标"),
    ]
    context = _context(nodes=nodes)
    target = next(ref for ref in context["source_refs"] if ref["mindmap_uid"] == NODE)
    assert target["resolution_status"] == "AMBIGUOUS"
    assert target["company_tree_node_id"] is None
    assert context["source_resolution"]["ambiguous"]
    assert context["source_resolution"]["resolved_count"] == 0
    assert context["primary_goal"] is None
    assert context["warnings"]
    proposal = generate_sop_proposal(context)
    validation = validate_sop_proposal(proposal, context)
    assert validation["source_identity_issues"]
    assert "source identity ambiguity" in validation["source_identity_issues"][0]["reason"]


def test_same_name_in_another_room_does_not_match():
    nodes = [
        _tree(TREE_ID, ROOM, NODE, "利润目标"),
        _tree("ct-b", "room-other", "uid-other", "利润目标"),
    ]
    snapshot = _snapshot()
    snapshot["candidates"].append(_goal("g-other", "利润目标", "ct-b"))
    context = _context(snapshot, nodes=nodes)
    target = next(ref for ref in context["source_refs"] if ref["mindmap_uid"] == NODE)
    assert target["company_tree_node_id"] == TREE_ID
    assert context["primary_goal"]["id"] == "g-profit"
    foreign = context_from_snapshot(
        snapshot,
        _request(
            node_uid="uid-other",
            source_uids=["uid-other"],
            mindmap_context={"target": {"uid": "uid-other", "name": "利润目标"}},
        ),
        nodes,
    )
    missed = next(ref for ref in foreign["source_refs"] if ref["mindmap_uid"] == "uid-other")
    assert missed["resolution_status"] == "NOT_FOUND"
    assert missed["cross_room"] is True
    assert missed["company_tree_node_id"] is None
    assert foreign["primary_goal"] is None
    validation = validate_sop_proposal(generate_sop_proposal(foreign), foreign)
    assert any(
        item["reason"] == "cross-room provenance conflict"
        for item in validation["provenance_conflicts"]
    )


def test_name_equality_does_not_resolve_a_different_node():
    nodes = [_tree("ct-lookalike", ROOM, "other-uid", "P：制定项目利润目标")]
    context = _context(nodes=nodes)
    target = next(ref for ref in context["source_refs"] if ref["mindmap_uid"] == NODE)
    assert target["resolution_status"] == "NOT_FOUND"
    assert target["company_tree_node_id"] is None
    assert context["primary_goal"] is None


def test_explicit_p_and_actionable_descendant_stay_source_plans():
    context = _context(nodes=[_tree(TREE_ID, ROOM, NODE)])
    proposal = generate_sop_proposal(context)
    plans = {item["text"]: item for item in proposal["plan"]}
    parent = plans["制定项目利润目标"]
    child = plans["填写项目利润测算"]
    assert parent["evidence_status"] == "SOURCE"
    assert NODE in parent["source_uids"]
    assert parent["evidence_node_ids"] == [TREE_ID]
    assert child["evidence_status"] == "SOURCE"
    assert CHILD in child["source_uids"]
    assert all(item.get("source_type") != "TELEOLOGY_CONSTRAINT" for item in proposal["plan"])
    assert "年度总目标确定后不可修改" not in " ".join(item["text"] for item in proposal["plan"])


def test_explicit_check_is_source():
    request = _request()
    request["mindmap_context"]["notes"] = [
        {"uid": NODE, "text": "验收标准：项目利润目标必须完成核对"}
    ]
    proposal = generate_sop_proposal(_context(request=request, nodes=[_tree(TREE_ID, ROOM, NODE)]))
    checks = [item for item in proposal["checks"] if item["evidence_status"] == "SOURCE"]
    assert checks
    assert checks[0]["text"] == "验收标准：项目利润目标必须完成核对"
    assert NODE in checks[0]["source_uids"]


def test_constraint_derives_check_and_references_become_inputs():
    context = _context(nodes=[_tree(TREE_ID, ROOM, NODE)])
    proposal = generate_sop_proposal(context)
    derived = [item for item in proposal["checks"] if item["evidence_status"] == "DERIVED"]
    assert derived
    assert derived[0]["derived_from_constraint_id"] == "constraint-year"
    assert derived[0]["reason"]
    assert "未被随意修改" in derived[0]["text"]
    input_text = {item["text"] for item in proposal["inputs"]}
    assert {"利润测算模型", "GMV 目标表", "GSV 目标表"} <= input_text
    assert all(
        item["evidence_status"] == "SOURCE" and item["source_uids"] for item in proposal["inputs"]
    )
    mindmap_text = {
        atom["text"]
        for atom in context["factual_atoms"]
        if atom["source_type"] in {"NODE", "NOTE", "REFERENCE", "ATTACHMENT"}
    }
    assert {item["text"] for item in proposal["plan"]} <= mindmap_text
    banned = {"收集信息", "分析数据", "执行方案", "持续优化", "及时复盘"}
    assert not any(item["text"] in banned for item in proposal["plan"] + proposal["checks"])


def test_missing_fields_do_not_erase_source_plan_or_derived_check():
    context = _context(nodes=[_tree(TREE_ID, ROOM, NODE)])
    proposal = generate_sop_proposal(context)
    assert proposal["plan"]
    assert proposal["checks"]
    assert proposal["overall_confidence"] > 0
    owner = next(item for item in proposal["missing_details"] if item["field"] == "负责人")
    assert owner["evidence_status"] == "MISSING"
    assert "责任人" in owner["reason"]
    assert "负责人" in proposal["gaps"]
    assert not any("负责人" in item["text"] for item in proposal["plan"] + proposal["checks"])
    validation = validate_sop_proposal(proposal, context)
    assert validation["status"] == "NEEDS_REVIEW"
    assert validation["status"] != "INSUFFICIENT_EVIDENCE"
    assert not validation["unsupported_claims"]


def test_brand_tie_and_cross_scope_semantic_leave_primary_empty():
    snapshot = _snapshot()
    snapshot["candidates"].extend(
        [
            _goal("g-wm", "WM 利润目标", TREE_ID),
            _goal("g-apieu", "APIEU 利润目标", TREE_ID),
        ]
    )
    tied = _context(snapshot, nodes=[_tree(TREE_ID, ROOM, NODE)])
    assert tied["primary_goal"] is None
    assert tied["goal_resolution_status"] == "AMBIGUOUS"
    assert {goal["id"] for goal in tied["related_goals"]} >= {"g-profit", "g-wm", "g-apieu"}
    assert tied["constraints"] == []
    assert tied["warnings"]

    foreign_snapshot = {
        "run_id": "current",
        "candidates": [
            {
                "id": "g-foreign",
                "name": "制定项目利润目标",
                "status": "confirmed",
                "source_node_ids": ["ct-foreign"],
                "evidence": [{"node_id": "ct-foreign", "source_room": "room-other"}],
            }
        ],
        "constraints": [],
        "purposes": [],
        "relations": [],
    }
    nodes = [
        _tree(TREE_ID, ROOM, NODE, "本地节点"),
        _tree("ct-foreign", "room-other", "foreign-uid", "制定项目利润目标"),
    ]
    foreign = context_from_snapshot(foreign_snapshot, _request(), nodes)
    assert foreign["primary_goal"] is None
    assert foreign["goal_resolution_status"] == "AMBIGUOUS"
    validation = validate_sop_proposal(generate_sop_proposal(foreign), foreign)
    assert validation["provenance_conflicts"]
    assert validation["status"] == "NEEDS_REVIEW"


def test_source_provenance_matches_when_evidence_carries_source_key():
    snapshot = _snapshot()
    snapshot["candidates"] = [
        {"id": "root", "name": "公司目标", "status": "confirmed"},
        {
            "id": "g-alias",
            "name": "别名目标",
            "status": "confirmed",
            "parent_candidate_id": "root",
            "source_node_ids": ["alias-id"],
            "evidence": [{"node_id": "alias-id", "source_key": SOURCE_KEY}],
        },
    ]
    context = _context(snapshot, nodes=[_tree(TREE_ID, ROOM, NODE)])
    assert context["primary_goal"]["id"] == "g-alias"
    assert context["primary_goal"]["match_tier"] == "SOURCE_PROVENANCE"
    assert context["primary_goal"]["match_reason"]
    assert context["primary_goal"]["match_confidence"] == 0.8


def test_empty_facts_are_insufficient_without_invented_steps():
    snapshot = _snapshot()
    request = _request(mindmap_context={})
    context = _context(snapshot, request, [_tree(TREE_ID, ROOM, NODE)])
    proposal = generate_sop_proposal(context)
    assert proposal["plan"] == []
    assert proposal["checks"] == []
    assert proposal["overall_confidence"] == 0
    assert validate_sop_proposal(proposal, context)["status"] == "INSUFFICIENT_EVIDENCE"
