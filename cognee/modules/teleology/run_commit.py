"""Preview or commit formal proposal items linked to one Coverage Run."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.modules.teleology.coverage_service import CoverageServiceError, get_coverage_engine
from cognee.modules.teleology.graph_annotations import _authorized_dataset
from cognee.modules.teleology.proposal_store import load_proposal
from cognee.modules.teleology.purpose_layer import (
    ProposalStaleError,
    commit_teleology_proposal,
    get_purpose_context,
)

_FORMAL_KINDS = frozenset({"purpose", "constraint", "goal", "relation"})
_RELATIONS = frozenset({"serves", "advances", "blocks"})
_COUNT_KEYS = {
    "purpose": "purpose_count",
    "constraint": "constraint_count",
    "goal": "goal_count",
    "serves": "serves_count",
    "advances": "advances_count",
    "blocks": "blocks_count",
}


def _accepted_items(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in proposal.get("items") or []
        if isinstance(item, dict)
        and item.get("kind") in _FORMAL_KINDS
        and not item.get("weak_reason")
        and item.get("review_status", item.get("status", "proposed")) != "ignored"
        and (item.get("kind") != "relation" or item.get("relationship") in _RELATIONS)
        and str(item.get("id") or "").strip()
    ]


def _count_key(item: dict[str, Any]) -> str:
    kind = "relationship" if item.get("kind") == "relation" else "kind"
    return _COUNT_KEYS[str(item.get(kind) or "")]


def _tally(result: dict[str, Any], items: list[dict[str, Any]], sign: int) -> None:
    result["proposals_committable"] += sign
    result["items_total"] += sign * len(items)
    for item in items:
        result[_count_key(item)] += sign


async def commit_coverage_run(
    run_id: str, dataset_id: UUID, user: Any, *, dry_run: bool
) -> dict[str, Any]:
    """Use only completed queue items from this run; never scan dataset proposals."""
    try:
        UUID(str(run_id))
    except ValueError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc
    await _authorized_dataset(dataset_id, user, "write")
    store = get_coverage_engine().store
    run = await store.get_run(run_id)
    if not run:
        raise CoverageServiceError(404, "Coverage run not found.")
    if str(run.get("dataset_id")) != str(dataset_id):
        raise CoverageServiceError(403, "Coverage run belongs to another dataset.")
    if run.get("status") != "completed":
        raise CoverageServiceError(409, "Coverage run must be completed before confirmation.")

    rows = await store.list_items(run_id, status="done")
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        proposal_id = str(row.get("proposal_id") or "").strip()
        if row.get("status") == "done" and proposal_id:
            unique.setdefault(proposal_id, row)

    result: dict[str, Any] = {
        "run_id": run_id,
        "dataset_id": str(dataset_id),
        "dry_run": dry_run,
        "proposals_total": len(unique),
        "proposals_committable": 0,
        "empty_proposals": 0,
        "conflict_proposals": 0,
        "items_total": 0,
        "purpose_count": 0,
        "constraint_count": 0,
        "goal_count": 0,
        "serves_count": 0,
        "advances_count": 0,
        "blocks_count": 0,
        "proposal_details": [],
        "committed_proposals": [],
        "failed_proposals": [],
        "skipped_empty": [],
        "stale_proposals": [],
        "already_committed": [],
        "committed_nodes": 0,
        "committed_relations": 0,
        "skipped_items": 0,
    }

    for proposal_id, row in unique.items():
        source_goal_id = str(row.get("goal_id") or "")
        detail = {
            "proposal_id": proposal_id,
            "source_goal_id": source_goal_id,
            "accepted_item_ids": [],
            "would_commit_count": 0,
        }
        result["proposal_details"].append(detail)
        tallied = False
        items: list[dict[str, Any]] = []
        try:
            proposal = await load_proposal(dataset_id, proposal_id)
            if not proposal or str(proposal.get("dataset_id")) != str(dataset_id):
                raise KeyError("Proposal not found in this dataset")
            detail["source_goal_id"] = str(proposal.get("source_goal_id") or source_goal_id)
            if detail["source_goal_id"] != source_goal_id:
                raise ValueError("Proposal source goal does not match the Coverage Run item")
            if proposal.get("status") == "committed":
                detail["status"] = "already_committed"
                result["already_committed"].append(proposal_id)
                continue
            items = _accepted_items(proposal)
            detail["accepted_item_ids"] = [str(item["id"]) for item in items]
            detail["would_commit_count"] = len(items)
            if not items:
                detail["status"] = "skipped_empty"
                result["empty_proposals"] += 1
                result["skipped_empty"].append(proposal_id)
                continue
            if proposal.get("open_conflicts"):
                detail["status"] = "conflict"
                result["conflict_proposals"] += 1
                continue
            context = await get_purpose_context(dataset_id, user, source_goal_id)
            if proposal.get("context_hash") != context.get("context_hash"):
                detail["status"] = "stale"
                result["stale_proposals"].append(proposal_id)
                continue
            detail["status"] = "committable"
            _tally(result, items, 1)
            tallied = True
            if dry_run:
                continue
            committed = await commit_teleology_proposal(
                dataset_id, user, proposal_id, detail["accepted_item_ids"]
            )
            detail["status"] = "committed"
            result["committed_proposals"].append(proposal_id)
            result["committed_nodes"] += len(committed.get("committed_nodes") or [])
            result["committed_relations"] += len(committed.get("committed_edges") or [])
            result["skipped_items"] += len(committed.get("skipped_item_ids") or [])
        except ProposalStaleError:
            if tallied:
                _tally(result, items, -1)
            detail["status"] = "stale"
            result["stale_proposals"].append(proposal_id)
        except Exception as exc:  # noqa: BLE001 - isolate failures per proposal
            if tallied:
                _tally(result, items, -1)
            detail["status"] = "failed"
            result["failed_proposals"].append(
                {
                    "proposal_id": proposal_id,
                    "source_goal_id": detail["source_goal_id"],
                    "error_code": getattr(exc, "code", None) or type(exc).__name__,
                    "error_message": str(exc),
                }
            )

    result["stale_proposals_count"] = len(result["stale_proposals"])
    return result
