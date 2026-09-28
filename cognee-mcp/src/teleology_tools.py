"""Dedicated MCP tools for the purpose/teleology page."""

from __future__ import annotations

import json
from urllib.parse import quote

from mcp import types


def register_teleology_tools(registry, get_client) -> None:
    async def request(method: str, path: str, *, body=None, params=None):
        try:
            result = await get_client().api_request(method, path, json_body=body, params=params)
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]

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
        dataset_id: str, link_entities: bool = True, source_room: str = None
    ) -> list:
        """Derive purpose goals and edges from a dataset's company goal tree."""
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
