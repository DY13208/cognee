"""Graph and proposal adapters. Analysis still goes through analyze_goal."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.graph_annotations import _authorized_dataset
from cognee.modules.teleology.proposal_store import load_proposal, load_proposals, save_proposal
from cognee.modules.teleology.purpose_analyze import analyze_goal
from cognee.modules.teleology.purpose_layer import _props_dict, get_purpose_context


class ProductionSources:
    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] | None = None
        self._dataset: str | None = None

    async def goal_page(
        self, dataset_id: Any, user: Any, offset: int, limit: int
    ) -> tuple[list[str], int]:
        dataset = await _authorized_dataset(UUID(str(dataset_id)), user, "read")
        async with set_database_global_context_variables(dataset_id, dataset.owner_id):
            graph = await get_graph_engine()
            count_rows = await graph.query(
                "MATCH (n:Node) WHERE n.type = 'Goal' RETURN count(n)",
                {},
            )
            rows = await graph.query(
                """MATCH (n:Node)
                WHERE n.type = 'Goal'
                RETURN n.id, n.properties
                ORDER BY n.id
                SKIP $offset
                LIMIT $limit""",
                {"offset": int(offset), "limit": int(limit)},
            )
        total = int(count_rows[0][0]) if count_rows else 0
        goal_ids = []
        for row in rows or []:
            if not row or row[0] is None:
                continue
            props = _props_dict(row[1] if len(row) > 1 else None)
            if str(props.get("cpd_kind") or "") == "map_reference":
                continue
            goal_ids.append(str(row[0]))
        return goal_ids, total

    async def context(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]:
        return await get_purpose_context(UUID(str(dataset_id)), user, goal_id)

    async def analyze(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]:
        return await analyze_goal(UUID(str(dataset_id)), user, goal_id)

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
