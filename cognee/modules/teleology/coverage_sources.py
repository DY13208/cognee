"""Graph and proposal adapters.

Coverage continues teleology for an existing AI Goal Model. It does not treat
company-tree nodes as goals. Discovery of goals belongs to the dataset build.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.modules.teleology.proposal_store import load_proposal, load_proposals, save_proposal
from cognee.modules.teleology.purpose_analyze import analyze_goal
from cognee.modules.teleology.purpose_layer import get_purpose_context


class ProductionSources:
    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] | None = None
        self._dataset: str | None = None

    async def goal_page(
        self, dataset_id: Any, user: Any, offset: int, limit: int
    ) -> tuple[list[str], int]:
        """Page canonical AI goals. Company-tree Goal nodes are not the queue."""
        del user
        from cognee.modules.teleology.goal_model import list_canonical_goal_ids

        goal_ids = list_canonical_goal_ids(dataset_id)
        start = max(0, int(offset))
        size = max(0, int(limit))
        return goal_ids[start : start + size], len(goal_ids)

    async def context(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model import canonical_context

        derived = canonical_context(dataset_id, goal_id)
        if derived is not None:
            return derived
        return await get_purpose_context(UUID(str(dataset_id)), user, goal_id)

    async def analyze(
        self, dataset_id: Any, user: Any, goal_id: str, run_id: str
    ) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model import incremental_teleology_proposal

        derived = incremental_teleology_proposal(dataset_id, goal_id, run_id)
        if derived is not None:
            return derived
        return await analyze_goal(UUID(str(dataset_id)), user, goal_id, run_id=run_id)

    async def open_proposal(self, dataset_id: Any, goal_id: str) -> dict[str, Any] | None:
        await self._load_open(dataset_id)
        assert self._open is not None
        return self._open.get(str(goal_id))

    async def mark_stale(self, dataset_id: Any, user: Any, proposal: dict[str, Any]) -> None:
        loaded = await load_proposal(UUID(str(dataset_id)), str(proposal["id"])) or dict(proposal)
        loaded["status"] = "stale"
        await save_proposal(UUID(str(dataset_id)), loaded, user=user)
        if self._open is not None:
            self._open.pop(str(loaded.get("source_goal_id") or ""), None)

    async def remember_semantic_hash(
        self,
        dataset_id: Any,
        user: Any,
        proposal: dict[str, Any],
        semantic_hash: str,
    ) -> None:
        if not proposal or not proposal.get("id"):
            return
        loaded = await load_proposal(UUID(str(dataset_id)), str(proposal["id"])) or dict(proposal)
        loaded["semantic_context_hash"] = semantic_hash
        await save_proposal(UUID(str(dataset_id)), loaded, user=user)
        if self._open is not None and loaded.get("status") == "open":
            self._open[str(loaded.get("source_goal_id") or "")] = loaded

    async def _load_open(self, dataset_id: Any) -> None:
        if self._dataset == str(dataset_id) and self._open is not None:
            return
        payload = await load_proposals(UUID(str(dataset_id)))
        found: dict[str, dict[str, Any]] = {}
        for proposal in (payload.get("proposals") or {}).values():
            if proposal.get("status") == "open":
                found[str(proposal.get("source_goal_id") or "")] = proposal
        self._open = found
        self._dataset = str(dataset_id)
