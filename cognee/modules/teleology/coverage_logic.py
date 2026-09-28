"""Pure decisions for the coverage engine. No graph and no LLM calls."""

from __future__ import annotations

from typing import Any

from cognee.modules.teleology.semantic_hash import semantic_context_hash

ANALYSIS_STATUSES = (
    "never_analyzed",
    "clean",
    "dirty",
    "queued",
    "analyzing",
    "proposal_open",
    "confirmed",
    "no_supported_proposal",
    "insufficient_context",
    "retry_required",
    "stale",
)
RUN_MODES = ("baseline", "incremental", "force")
RUN_STATUSES = (
    "pending",
    "running",
    "paused",
    "paused_budget",
    "completed",
    "cancelled",
    "failed",
)
MAX_AUTO_RETRIES = 2
MAX_ATTEMPTS = MAX_AUTO_RETRIES + 1
DEFAULT_BATCH_SIZE = 20
DEFAULT_CONCURRENCY = 3


def clamp_concurrency(value: int | None) -> int:
    try:
        number = int(value if value is not None else DEFAULT_CONCURRENCY)
    except (TypeError, ValueError):
        number = DEFAULT_CONCURRENCY
    return min(5, max(1, number))


def clamp_batch_size(value: int | None) -> int:
    try:
        number = int(value if value is not None else DEFAULT_BATCH_SIZE)
    except (TypeError, ValueError):
        number = DEFAULT_BATCH_SIZE
    return min(100, max(1, number))


def _described(context: dict[str, Any]) -> bool:
    goal = context.get("goal") or {}
    return bool(
        str(goal.get("description") or "").strip() or str(context.get("note") or "").strip()
    )


def _meaningful_children(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        child
        for child in context.get("children") or []
        if str(child.get("semantic_role") or "goal") == "goal"
        and str(child.get("name") or "").strip()
    ]


def insufficient_context(context: dict[str, Any]) -> bool:
    """No description, evidence, child evidence, or meaningful child. Do not call the LLM."""
    if _described(context):
        return False
    if context.get("entities") or context.get("documents") or context.get("child_evidence"):
        return False
    return not _meaningful_children(context)


def priority_for(context: dict[str, Any]) -> int:
    """P0 roots and high goals, then described goals, then branching goals."""
    ancestors = context.get("ancestors") or []
    if len(ancestors) <= 1:
        return 0
    if (
        _described(context)
        or context.get("entities")
        or context.get("documents")
        or context.get("child_evidence")
    ):
        return 1
    if len(_meaningful_children(context)) >= 2:
        return 2
    return 3


def _proposal_same(
    proposal: dict[str, Any] | None,
    current_context_hash: str | None,
    current_semantic_hash: str,
) -> bool:
    """Compare each stored hash only with the current hash of the same kind."""
    if not proposal or proposal.get("status") != "open":
        return False
    proposal_context = proposal.get("context_hash")
    proposal_semantic = proposal.get("semantic_context_hash")
    if not proposal_context or not proposal_semantic:
        return False
    return str(proposal_context) == str(current_context_hash or "") and str(
        proposal_semantic
    ) == str(current_semantic_hash)


def decide_coverage(
    mode: str,
    state: dict[str, Any] | None,
    context: dict[str, Any],
    open_proposal: dict[str, Any] | None = None,
    current_hash: str | None = None,
) -> str:
    """Return analyze, stale_analyze, skip, or insufficient."""
    status = str((state or {}).get("status") or "never_analyzed")
    stored = (state or {}).get("semantic_context_hash") or None
    current = current_hash or semantic_context_hash(context)
    changed = bool(stored) and stored != current
    if insufficient_context(context):
        if mode == "baseline" and status != "never_analyzed":
            return "skip"
        if status == "insufficient_context" and not changed and mode != "force":
            return "skip"
        return "insufficient"
    if mode == "baseline":
        return (
            "analyze"
            if status in {"never_analyzed", "queued", "dirty", "retry_required"}
            else "skip"
        )
    if mode == "force":
        if open_proposal and open_proposal.get("status") == "open":
            return "stale_analyze"
        return "analyze"
    if open_proposal and open_proposal.get("status") == "open":
        if _proposal_same(open_proposal, context.get("context_hash"), current):
            return "skip"
        return "stale_analyze"
    if status in {"clean", "confirmed", "proposal_open", "no_supported_proposal"} and not changed:
        return "skip"
    if status in {"never_analyzed", "dirty", "retry_required", "stale", "queued"} or changed:
        return "analyze"
    return "skip"


def dirty_ids_for_text(
    *,
    goal_id: str,
    text_changed: bool,
    parent_id: str | None = None,
) -> list[str]:
    """The goal and its direct parent. A parent's hash includes this child's text."""
    if not text_changed or not goal_id:
        return []
    return dirty_ids_for_child(parent_id=parent_id, child_id=goal_id)


def dirty_ids_for_child(
    *,
    parent_id: str | None,
    child_id: str | None,
    previous_parent_id: str | None = None,
) -> list[str]:
    """Depth 1: the parent and the child. Grandparents stay clean."""
    ordered = [parent_id, previous_parent_id, child_id]
    seen: set[str] = set()
    result = []
    for item in ordered:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def dirty_ids_for_evidence(*, goal_id: str) -> list[str]:
    return [goal_id] if goal_id else []


def dirty_ids_for_relation(*, source_id: str | None, target_id: str | None) -> list[str]:
    return dirty_ids_for_child(parent_id=source_id, child_id=target_id)
