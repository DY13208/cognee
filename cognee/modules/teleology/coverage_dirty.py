"""Mark goals dirty without walking ancestors. Depth stays at the caller."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def mark_teleology_dirty(
    dataset_id: Any,
    goal_ids: list[str],
    reason: str,
    *,
    store: Any | None = None,
) -> list[str]:
    """Persist a depth-1 dirty set. Failures never break the write that caused them."""
    ids = [str(goal_id) for goal_id in goal_ids if goal_id]
    if not ids:
        return []
    try:
        target = store
        if target is None:
            from cognee.modules.teleology.proposal_store import database_enabled

            if not database_enabled():
                return []
            from cognee.modules.teleology.coverage_store import SqlCoverageStore

            target = SqlCoverageStore()
        return await target.mark_dirty(dataset_id, ids, reason)
    except Exception:
        logger.exception("Could not mark teleology goals dirty")
        return []
