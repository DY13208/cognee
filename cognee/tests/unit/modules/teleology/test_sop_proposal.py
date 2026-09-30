from copy import deepcopy

from cognee.modules.teleology.sop_context import context_from_snapshot
from cognee.modules.teleology.sop_generator import generate_sop_proposal
from cognee.modules.teleology.sop_validator import _known, validate_sop_proposal

REAL_UID = "e1bd00ff-1f82-4a95-946e-7da665876c91"
REAL_ID = "e7f37cf4-fda6-5856-93e2-c688fc0a1352"


def _real_p1_context():
    context = {
        "mindmap_context": {"target": {"uid": REAL_UID, "name": "<p>P：制定项目利润目标</p>"}},
        "source_refs": [
            {
                "mindmap_uid": REAL_UID,
                "company_tree_node_id": REAL_ID,
                "source_key": f"mindmap:room:{REAL_UID}",
                "resolution_status": "EXACT",
            }
        ],
        "goal_resolution_status": "AMBIGUOUS",
        "goal_resolution_reason": "multiple goals share source provenance",
    }
    proposal = {
        "plan": [{"id": "P1", "text": "制定项目利润目标", "evidence_status": "SOURCE"}],
        "checks": [],
        "goal_resolution_status": "AMBIGUOUS",
    }
    return context, proposal


def test_real_p1_exact_pair_survives_missing_auxiliary_known_id():
    context, proposal = _real_p1_context()
    known_uids, known_ids, _ = _known(context)
    assert REAL_UID in known_uids
    assert REAL_ID in known_ids
    assert (REAL_UID, REAL_ID) in {
        (ref["mindmap_uid"], ref["company_tree_node_id"])
        for ref in context["source_refs"]
        if ref["resolution_status"] == "EXACT"
    }
    # Reproduces a standalone rebuild where the auxiliary ID set omits the tree ID.
    from cognee.modules.teleology.sop_validator import verify_source_provenance

    item = {
        **proposal["plan"][0],
        "source_uid": REAL_UID,
        "source_uids": [REAL_UID],
        "evidence_node_id": REAL_ID,
        "evidence_node_ids": [REAL_ID],
    }
    assert verify_source_provenance(item, context, known_uids, set()) is None
    proposal["plan"] = [item]
    result = validate_sop_proposal(proposal, context)
    assert result["unsupported_claims"] == []
    assert result["goal_resolution_status"] == "AMBIGUOUS"
    assert result["goal_resolution_reason"] == context["goal_resolution_reason"]
    assert result["provenance_conflicts"]


def test_source_provenance_single_plural_and_wrong_pair():
    context, proposal = _real_p1_context()
    base = proposal["plan"][0]
    valid = [
        {"source_uid": REAL_UID},
        {"source_uids": [REAL_UID]},
        {"evidence_node_id": REAL_ID},
        {"evidence_node_ids": [REAL_ID]},
        {"source_uid": REAL_UID, "evidence_node_id": REAL_ID},
        {"source_uids": [REAL_UID], "evidence_node_ids": [REAL_ID]},
        {
            "source_uid": REAL_UID,
            "source_uids": [REAL_UID],
            "evidence_node_id": REAL_ID,
            "evidence_node_ids": [REAL_ID],
        },
    ]
    for fields in valid:
        proposal["plan"] = [{**base, **fields}]
        assert validate_sop_proposal(proposal, context)["unsupported_claims"] == []
    proposal["plan"] = [{**base, "source_uid": REAL_UID, "evidence_node_id": "WRONG-ID"}]
    errors = validate_sop_proposal(proposal, context)["unsupported_claims"]
    assert any("SOURCE_PROVENANCE_MISMATCH" in issue["reason"] for issue in errors)


def test_real_p1_html_fact_is_supported_by_its_own_source():
    context, proposal = _real_p1_context()
    context["factual_atoms"] = [
        {
            "text": "制定项目利润目标",
            "raw_text": "<p>P：制定项目利润目标</p>",
            "source_uid": REAL_UID,
            "evidence_node_id": REAL_ID,
            "source_type": "NODE",
        }
    ]
    proposal["plan"][0].update(source_uids=[REAL_UID], evidence_node_ids=[REAL_ID])
    fields = [
        "负责人",
        "审批人",
        "时间要求",
        "数值阈值",
        "系统名称",
        "操作路径",
        "责任部门",
        "频率",
    ]
    proposal["missing_details"] = [
        {"field": field, "evidence_status": "MISSING"} for field in fields
    ]
    result = validate_sop_proposal(proposal, context)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["unsupported_claims"] == []
    assert result["missing_fields"] == fields
    assert result["quality_gaps"] == ["缺少可验收的检查标准"]
    proposal["plan"][0]["text"] = "提交年度预算审批"
    result = validate_sop_proposal(proposal, context)
    assert any(
        issue["reason"] == "SOURCE 文本未被引用事实直接支持"
        for issue in result["unsupported_claims"]
    )


def test_source_atom_text_takes_priority_over_raw_html():
    context, proposal = _real_p1_context()
    proposal["plan"][0].update(source_uid=REAL_UID, evidence_node_id=REAL_ID, provenance="target")
    context["factual_atoms"] = [
        {
            "source_uid": REAL_UID,
            "evidence_node_id": REAL_ID,
            "provenance": "target",
            "text": "制定项目利润目标",
            "raw_text": "<p>P：制定项目利润目标</p>",
        }
    ]
    assert validate_sop_proposal(proposal, context)["unsupported_claims"] == []
    context["factual_atoms"][0]["text"] = "另一项业务动作"
    assert any(
        issue["reason"] == "SOURCE 文本未被引用事实直接支持"
        for issue in validate_sop_proposal(proposal, context)["unsupported_claims"]
    )
    context["factual_atoms"][0]["text"] = ""
    assert validate_sop_proposal(proposal, context)["unsupported_claims"] == []


def test_exact_pair_cannot_borrow_same_text_from_another_node():
    context, proposal = _real_p1_context()
    proposal["plan"][0].update(source_uid=REAL_UID, evidence_node_id=REAL_ID)
    context["factual_atoms"] = [
        {"source_uid": REAL_UID, "evidence_node_id": REAL_ID, "text": "填写项目利润测算"},
        {"source_uid": "other-node", "evidence_node_id": REAL_ID, "text": "制定项目利润目标"},
    ]
    assert any(
        issue["reason"] == "SOURCE 文本未被引用事实直接支持"
        for issue in validate_sop_proposal(proposal, context)["unsupported_claims"]
    )


def test_source_text_html_variants_and_node_scope():
    context, proposal = _real_p1_context()
    item = proposal["plan"][0]
    item.update(source_uid=REAL_UID, evidence_node_id=REAL_ID)
    for raw in ("<p>P：制定项目利润目标</p>", "P：制定项目利润目标", "制定项目利润目标"):
        context["factual_atoms"] = [
            {"source_uid": REAL_UID, "evidence_node_id": REAL_ID, "raw_text": raw}
        ]
        assert validate_sop_proposal(proposal, context)["unsupported_claims"] == []
    for raw in ("<div>P：提交审批</div>", "<strong>P：提交审批</strong>"):
        item["text"] = "提交审批"
        context["factual_atoms"] = [
            {"source_uid": REAL_UID, "evidence_node_id": REAL_ID, "raw_text": raw}
        ]
        assert validate_sop_proposal(proposal, context)["unsupported_claims"] == []
    context["factual_atoms"] = [
        {"source_uid": "other-node", "raw_text": "<p>P：提交审批</p>"},
        {"source_uid": REAL_UID, "raw_text": "<p>P：制定项目利润目标</p>"},
    ]
    assert any(
        issue["reason"] == "SOURCE 文本未被引用事实直接支持"
        for issue in validate_sop_proposal(proposal, context)["unsupported_claims"]
    )


def test_no_plan_is_insufficient_and_no_check_is_quality_gap():
    context, proposal = _real_p1_context()
    proposal["plan"][0].update(source_uid=REAL_UID, evidence_node_id=REAL_ID)
    result = validate_sop_proposal(proposal, context)
    assert result["status"] == "NEEDS_REVIEW"
    assert "checks" not in result["missing_fields"]
    assert result["quality_gaps"] == ["缺少可验收的检查标准"]
    proposal["plan"] = []
    result = validate_sop_proposal(proposal, context)
    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def _sample():
    snapshot = {
        "run_id": "current",
        "candidates": [
            {"id": "root", "name": "业务目标", "status": "confirmed"},
            {
                "id": "g1",
                "name": "完成交付",
                "status": "confirmed",
                "parent_candidate_id": "root",
                "source_node_ids": ["n1"],
                "evidence": [{"node_id": "n1"}],
            },
            {
                "id": "old",
                "name": "旧目标",
                "status": "legacy_confirmed",
                "source_node_ids": ["n1"],
            },
            {
                "id": "outside",
                "name": "外部目标",
                "outside_current_snapshot": True,
                "source_node_ids": ["n1"],
            },
        ],
        "purposes": [{"id": "p1", "goal_id": "g1", "name": "降低返工", "status": "confirmed"}],
        "constraints": [
            {"id": "c1", "goal_id": "g1", "name": "禁止删除原始记录", "status": "confirmed"}
        ],
        "relations": [],
    }
    request = {
        "dataset_id": "dataset",
        "room_key": "room",
        "node_uid": "n1",
        "source_uids": ["n1"],
        "mindmap_context": {
            "facts": [
                {"source_uid": "n1", "text": "记录交付结果"},
                {"source_uid": "n1", "text": "检查交付结果"},
            ]
        },
    }
    return snapshot, request


def test_snapshot_first_context_and_no_mutation():
    snapshot, request = _sample()
    original = deepcopy(snapshot)
    context = context_from_snapshot(snapshot, request)
    assert context["run_id"] == "current"
    assert context["formal_graph_required"] is False
    assert [g["id"] for g in context["related_goals"]] == ["g1"]
    assert [g["id"] for g in context["goal_path"]] == ["root", "g1"]
    assert context["purposes"][0]["id"] == "p1"
    assert snapshot == original


def test_source_traceability_missing_and_constraint_conflict():
    snapshot, request = _sample()
    context = context_from_snapshot(snapshot, request)
    proposal = generate_sop_proposal(context)
    assert proposal["status"] == "proposal"
    assert all(
        item["evidence_status"] == "SOURCE" and item["source_uids"]
        for item in proposal["checks"] + proposal["plan"]
    )
    assert "负责人" in proposal["gaps"]
    proposal["plan"][0]["text"] = "删除原始记录"
    result = validate_sop_proposal(proposal, context)
    assert result["constraint_conflicts"]
    assert result["unsupported_claims"]


def test_derived_requires_reason_and_unbacked_source_fails():
    snapshot, request = _sample()
    context = context_from_snapshot(snapshot, request)
    proposal = generate_sop_proposal(context)
    proposal["checks"][0].update(evidence_status="DERIVED", reason="")
    proposal["plan"][0]["source_uids"] = ["invented"]
    result = validate_sop_proposal(proposal, context)
    assert any("DERIVED" in item["reason"] for item in result["unsupported_claims"])
    assert any("SOURCE" in item["reason"] for item in result["unsupported_claims"])


def test_existing_sop_conflict_is_reported():
    snapshot, request = _sample()
    request["mindmap_context"]["existing_sops"] = [
        {"id": "s1", "goal_id": "g1", "scope": "room", "plan": [{"text": "发送交付结果"}]}
    ]
    context = context_from_snapshot(snapshot, request)
    proposal = generate_sop_proposal(context)
    assert validate_sop_proposal(proposal, context)["sop_conflicts"][0]["sop_id"] == "s1"


def test_constraint_can_derive_a_check_with_reason():
    snapshot, request = _sample()
    request["mindmap_context"]["facts"] = [{"source_uid": "n1", "text": "记录交付结果"}]
    context = context_from_snapshot(snapshot, request)
    proposal = generate_sop_proposal(context)
    assert proposal["checks"][0]["evidence_status"] == "DERIVED"
    assert proposal["checks"][0]["reason"]
