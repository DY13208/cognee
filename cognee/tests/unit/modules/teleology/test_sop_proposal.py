from copy import deepcopy

from cognee.modules.teleology.sop_context import context_from_snapshot
from cognee.modules.teleology.sop_generator import generate_sop_proposal
from cognee.modules.teleology.sop_validator import validate_sop_proposal


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
