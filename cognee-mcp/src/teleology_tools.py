"""Dedicated MCP tools for the purpose/teleology page."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

from mcp import types

logger = logging.getLogger(__name__)


def register_teleology_tools(registry, get_client) -> None:
    async def request(method: str, path: str, *, body=None, params=None):
        try:
            result = await get_client().api_request(method, path, json_body=body, params=params)
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        except Exception as exc:
            logger.exception("Teleology MCP %s %s failed", method, path)
            return [types.TextContent(type="text", text=f"Error: {type(exc).__name__}: {exc}")]

    @registry.tool(tags={"teleology"})
    async def get_teleology(q: str = None, limit: int = 80, offset: int = 0) -> list:
        """Read the active teleology YAML status and paginated goals, purposes and constraints."""
        return await request("GET", "/api/v1/teleology", params={"q": q, "limit": limit, "offset": offset})

    @registry.tool(tags={"teleology"})
    async def create_teleology_node(
        node_type: str, name: str, status: str = "proposed", description: str = "", keywords: list[str] = None
    ) -> list:
        """Create a teleology goal, purpose or constraint in the active YAML."""
        return await request("POST", "/api/v1/teleology/nodes", body={"type": node_type, "name": name, "status": status, "description": description, "keywords": keywords or []})

    @registry.tool(tags={"teleology"})
    async def update_teleology_node(node_id: str, changes_json: str) -> list:
        """Update a teleology node. changes_json is a JSON object of type/name/status/description/keywords."""
        try:
            changes = json.loads(changes_json)
            if not isinstance(changes, dict):
                raise ValueError("changes_json must be a JSON object")
        except (ValueError, TypeError) as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]
        return await request("PUT", f"/api/v1/teleology/nodes/{quote(node_id, safe='')}", body=changes)

    @registry.tool(tags={"teleology"})
    async def delete_teleology_node(node_id: str, node_type: str = None) -> list:
        """Delete a teleology node by ID, optionally specifying goal/purpose/constraint."""
        return await request("DELETE", f"/api/v1/teleology/nodes/{quote(node_id, safe='')}", params={"node_type": node_type})

    @registry.tool(tags={"teleology"})
    async def upload_teleology_yaml(filename: str, yaml_content: str) -> list:
        """Replace the active teleology YAML with supplied UTF-8 content (.yaml or .yml)."""
        try:
            result = await get_client().upload_teleology_yaml(filename, yaml_content)
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]

    @registry.tool(tags={"teleology"})
    async def load_sample_teleology() -> list:
        """Install the bundled sample teleology YAML."""
        return await request("POST", "/api/v1/teleology/sample")

    @registry.tool(tags={"teleology"})
    async def clear_teleology() -> list:
        """Remove the active teleology YAML; graph annotations remain."""
        return await request("DELETE", "/api/v1/teleology")

    @registry.tool(tags={"teleology"})
    async def get_teleology_annotations(
        dataset_id: str, q: str = None, limit: int = 200, goals_limit: int = 120,
        goals_offset: int = 0, goal_id: str = None, parent_id: str = None,
    ) -> list:
        """List purpose edges and annotatable graph nodes for a brain/dataset."""
        return await request("GET", "/api/v1/teleology/annotations", params={
            "dataset_id": dataset_id, "q": q, "limit": limit, "goals_limit": goals_limit,
            "goals_offset": goals_offset, "goal_id": goal_id, "parent_id": parent_id,
        })

    @registry.tool(tags={"teleology"})
    async def sync_teleology_goals(dataset_id: str) -> list:
        """Sync YAML goals, purposes and constraints into a dataset graph."""
        return await request("POST", "/api/v1/teleology/annotations/sync-goals", params={"dataset_id": dataset_id})

    @registry.tool(tags={"teleology"})
    async def sync_teleology_from_company_tree(
        dataset_id: str, link_entities: bool = False, source_room: str = None
    ) -> list:
        """Read the company tree and stamp structural edges. Does not generate teleology."""
        return await request("POST", "/api/v1/teleology/annotations/sync-from-company-tree", params={
            "dataset_id": dataset_id, "link_entities": link_entities, "source_room": source_room,
        })

    @registry.tool(tags={"teleology"})
    async def create_teleology_annotation(
        dataset_id: str, source_id: str, target_id: str, relationship: str
    ) -> list:
        """Attach a serves, advances or blocks edge from a graph node to a goal."""
        return await request("POST", "/api/v1/teleology/annotations", body={
            "dataset_id": dataset_id, "source_id": source_id, "target_id": target_id,
            "relationship": relationship,
        })

    @registry.tool(tags={"teleology"})
    async def delete_teleology_annotation(
        dataset_id: str, source_id: str, target_id: str, relationship: str
    ) -> list:
        """Remove a purpose edge while keeping its endpoint nodes."""
        return await request("DELETE", "/api/v1/teleology/annotations", params={
            "dataset_id": dataset_id, "source_id": source_id, "target_id": target_id,
            "relationship": relationship,
        })

    @registry.tool(tags={"teleology"})
    async def analyze_purpose_relations(dataset_id: str, goal_id: str) -> list:
        """Cognee built-in analysis for one goal. Stores a proposal as purpose-agent and does not commit it. Read-only toward the company tree and the formal graph."""
        return await request("POST", "/api/v1/teleology/analyze", body={
            "dataset_id": dataset_id, "goal_id": goal_id,
        })

    @registry.tool(tags={"teleology"})
    async def get_purpose_context(dataset_id: str, goal_id: str) -> list:
        """Read-only bounded context for one goal. Does not scan the company tree and does not write anything."""
        return await request(
            "GET",
            f"/api/v1/teleology/annotations/goals/{quote(goal_id, safe='')}/purpose-context",
            params={"dataset_id": dataset_id},
        )

    @registry.tool(tags={"teleology"})
    async def propose_teleology(
        dataset_id: str,
        source_goal_id: str,
        proposal_json: str,
        generated_by: str = "workbuddy",
    ) -> list:
        """External agent submits a proposal. Does not commit and does not write the formal graph.

        generated_by is workbuddy or manual. purpose-agent is reserved for Cognee /teleology/analyze.
        Each relation must use this shape:
        {"source": "<goal or new item name>", "relationship": "advances", "target": "<goal or new item name>", "reason": "why", "confidence": 0.8, "evidence_node_ids": ["<id from get_purpose_context>"]}
        source_id and source_ref are accepted aliases of source. target_id and target_ref are aliases of target.
        """
        try:
            proposal = json.loads(proposal_json)
            if not isinstance(proposal, dict):
                raise ValueError("proposal_json must be a JSON object")
            if generated_by not in {"workbuddy", "manual"}:
                raise ValueError("generated_by must be workbuddy or manual")
        except (ValueError, TypeError) as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]
        return await request("POST", "/api/v1/teleology/annotations/purpose-proposals", body={
            "dataset_id": dataset_id,
            "source_goal_id": source_goal_id,
            "proposal": proposal,
            "generated_by": generated_by or "workbuddy",
        })

    @registry.tool(tags={"teleology"})
    async def commit_teleology_proposal(
        proposal_id: str, dataset_id: str, accepted_item_ids: list[str]
    ) -> list:
        """Commit accepted proposal items into the formal teleology graph. This is the only teleology tool that writes purpose nodes and edges."""
        return await request(
            "POST",
            f"/api/v1/teleology/annotations/purpose-proposals/{quote(proposal_id, safe='')}/commit",
            body={"dataset_id": dataset_id, "accepted_item_ids": accepted_item_ids or []},
        )
