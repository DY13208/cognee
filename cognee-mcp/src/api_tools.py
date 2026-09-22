"""Extra MCP tools that expose Cognee HTTP API capabilities."""

from __future__ import annotations

import json

from mcp import types

try:
    from .tool_registry import DEFAULT_TAG, ToolRegistry
except ImportError:
    from tool_registry import DEFAULT_TAG, ToolRegistry

# Documented for agents: dedicated tools cover common flows; everything else
# goes through api_request with these prefixes.
_API_CATALOG = """
Common /api/v1 prefixes (use api_request for any of these):
  /api/v1/remember, /recall, /improve, /forget
  /api/v1/add, /cognify, /memify, /search, /update, /delete
  /api/v1/datasets, /datasets/{id}/company-tree, /datasets/{id}/graph
  /api/v1/permissions, /users, /settings, /ontologies, /schema
  /api/v1/skills, /proposals, /agents, /sessions, /activity
  /api/v1/visualize, /sync, /integrations, /slack, /responses, /llm
""".strip()


def _json_result(payload) -> list:
    return [
        types.TextContent(
            type="text",
            text=json.dumps(payload, ensure_ascii=False, default=str, indent=2),
        )
    ]


def _error(exc: Exception) -> list:
    return [types.TextContent(type="text", text=f"Error: {exc}")]


def register_api_surface_tools(registry: ToolRegistry, get_client) -> None:
    """Register company-tree helpers, pipeline helpers, and a generic API proxy."""

    @registry.tool(tags={DEFAULT_TAG})
    async def api_request(
        method: str,
        path: str,
        body: str = None,
        query_json: str = None,
    ) -> list:
        """Call ANY Cognee HTTP API endpoint as the authenticated MCP user.

        This is the full API surface — not limited to the named tools below.
        Requires X-Api-Key on the MCP connection.

        {catalog}

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, PUT, PATCH, DELETE).
        path : str
            Must start with /api/, e.g. /api/v1/datasets or /api/v1/search
        body : str, optional
            JSON string request body.
        query_json : str, optional
            JSON object of query string parameters.
        """.format(catalog=_API_CATALOG)
        client = get_client()
        try:
            json_body = json.loads(body) if body else None
            params = json.loads(query_json) if query_json else None
            if query_json and not isinstance(params, dict):
                return [
                    types.TextContent(
                        type="text",
                        text="Error: query_json must be a JSON object.",
                    )
                ]
            result = await client.api_request(method, path, json_body=json_body, params=params)
            return _json_result(result)
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def list_datasets() -> list:
        """List datasets the authenticated user can access."""
        client = get_client()
        try:
            return _json_result(await client.api_request("GET", "/api/v1/datasets"))
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def search(
        query: str,
        datasets: str = None,
        query_type: str = None,
        top_k: int = 15,
    ) -> list:
        """Low-level knowledge search (POST /api/v1/search).

        Parameters
        ----------
        query : str
            Search / question text.
        datasets : str, optional
            Comma-separated dataset names, or omit for all accessible.
        query_type : str, optional
            e.g. GRAPH_COMPLETION, RAG_COMPLETION, CHUNKS, HYBRID_COMPLETION.
        top_k : int
            Result limit (default 15).
        """
        client = get_client()
        try:
            payload = {"query": query, "top_k": top_k}
            if query_type:
                payload["query_type"] = query_type
            if datasets:
                payload["datasets"] = [d.strip() for d in datasets.split(",") if d.strip()]
            return _json_result(
                await client.api_request("POST", "/api/v1/search", json_body=payload)
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def improve(dataset: str = "main_dataset", session_ids: str = None) -> list:
        """Enrich / index the graph (POST /api/v1/improve).

        Parameters
        ----------
        dataset : str
            Dataset name (default main_dataset).
        session_ids : str, optional
            Comma-separated session ids to bridge into the graph.
        """
        client = get_client()
        try:
            payload = {"dataset": dataset}
            if session_ids:
                payload["session_ids"] = [s.strip() for s in session_ids.split(",") if s.strip()]
            return _json_result(
                await client.api_request("POST", "/api/v1/improve", json_body=payload)
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def cognify(datasets: str = None) -> list:
        """Build / rebuild the knowledge graph (POST /api/v1/cognify).

        Parameters
        ----------
        datasets : str, optional
            Comma-separated dataset names. Omit to cognify all owned datasets.
        """
        client = get_client()
        try:
            payload = {}
            if datasets:
                payload["datasets"] = [d.strip() for d in datasets.split(",") if d.strip()]
            return _json_result(
                await client.api_request("POST", "/api/v1/cognify", json_body=payload or None)
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def get_dataset_graph(dataset_id: str) -> list:
        """Fetch the graph for a dataset (GET /api/v1/datasets/{id}/graph)."""
        client = get_client()
        try:
            return _json_result(
                await client.api_request("GET", f"/api/v1/datasets/{dataset_id}/graph")
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def get_company_tree(dataset_id: str, source_room: str = None) -> list:
        """Read the company goal tree for a dataset."""
        client = get_client()
        try:
            params = {"source_room": source_room} if source_room else None
            return _json_result(
                await client.api_request(
                    "GET",
                    f"/api/v1/datasets/{dataset_id}/company-tree",
                    params=params,
                )
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def put_company_tree(dataset_id: str, payload_json: str) -> list:
        """Upsert the company goal tree (validated batch write)."""
        client = get_client()
        try:
            payload = json.loads(payload_json)
            return _json_result(
                await client.api_request(
                    "PUT",
                    f"/api/v1/datasets/{dataset_id}/company-tree",
                    json_body=payload,
                )
            )
        except Exception as exc:
            return _error(exc)

    @registry.tool(tags={DEFAULT_TAG})
    async def reconcile_company_tree(dataset_id: str, source_room: str = None) -> list:
        """Repair/stamp existing Goal nodes into the company-tree shape."""
        client = get_client()
        try:
            params = {"source_room": source_room} if source_room else None
            return _json_result(
                await client.api_request(
                    "POST",
                    f"/api/v1/datasets/{dataset_id}/company-tree/reconcile",
                    params=params,
                )
            )
        except Exception as exc:
            return _error(exc)
