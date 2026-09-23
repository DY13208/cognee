"""Read mind-map rooms from the mind-map MCP so linked maps can become CPD nodes."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from cognee.modules.company_tree.exceptions import CompanyTreeWriteError
from cognee.modules.company_tree.mindmap_import import (
    expand_company_tree,
    iter_map_refs,
    room_id_from_uri,
)
from cognee.shared.logging_utils import get_logger

logger = get_logger("company_tree.mindmap_mcp")

_MAX_NODES = 5000


def _parse_sse(body: str) -> Dict[str, Any]:
    for line in body.splitlines():
        if line.startswith("data: "):
            parsed = json.loads(line[6:])
            if isinstance(parsed, dict):
                return parsed
    parsed = json.loads(body or "{}")
    return parsed if isinstance(parsed, dict) else {}


class MindMapMcpClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._session_id: Optional[str] = None
        self._rpc_id = 0
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def from_env(cls) -> "MindMapMcpClient":
        url = (os.environ.get("MINDMAP_MCP_URL") or "").strip()
        token = (os.environ.get("MINDMAP_MCP_TOKEN") or "").strip()
        if not url or not token:
            raise CompanyTreeWriteError(
                "Mind-map MCP is not configured.",
                missing=["mindmap_mcp_not_configured"],
            )
        return cls(url, token)

    async def __aenter__(self) -> "MindMapMcpClient":
        self._client = httpx.AsyncClient(timeout=120, verify=False)
        await self._initialize()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _initialize(self) -> None:
        await self._rpc(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "cognee", "version": "1"},
                },
            }
        )
        await self._rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def _rpc(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Mind-map MCP client is not open.")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        response = await self._client.post(self._url, headers=headers, json=payload)
        response.raise_for_status()
        session = response.headers.get("mcp-session-id")
        if session:
            self._session_id = session
        if not response.content:
            return {}
        return _parse_sse(response.text)

    async def get_map(self, room_key: str) -> Dict[str, Any]:
        message = await self._rpc(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {
                    "name": "get_map",
                    "arguments": {
                        "room_key": room_key,
                        "format": "full",
                        "max_nodes": _MAX_NODES,
                    },
                },
            }
        )
        result = message.get("result") or {}
        if result.get("isError"):
            detail = ""
            content = result.get("content") or []
            if content and isinstance(content[0], dict):
                detail = str(content[0].get("text") or "")
            raise RuntimeError(detail or f"get_map failed for {room_key}")
        content = result.get("content") or []
        text = content[0].get("text") if content and isinstance(content[0], dict) else ""
        document = json.loads(text or "{}")
        tree = document.get("tree")
        if not isinstance(tree, dict):
            raise RuntimeError(f"get_map returned no tree for {room_key}")
        source_uri = str(document.get("share_url") or "")
        if not source_uri:
            source_uri = f"https://xx.stillgroup.net:8989/?room={room_key}"
        return {
            "tree": tree,
            "version": str(document.get("version") or ""),
            "source_uri": source_uri,
            "truncated": bool(document.get("truncated")),
        }

    async def load_linked_documents(
        self, rooms: Iterable[str], primary_room: str
    ) -> Dict[str, Dict[str, Any]]:
        documents: Dict[str, Dict[str, Any]] = {}
        queue = [room for room in rooms if room and room != primary_room]
        while queue:
            room = queue.pop(0)
            if room in documents or room == primary_room:
                continue
            try:
                document = await self.get_map(room)
            except Exception as exc:
                logger.warning("Skipped linked mind map %s: %s", room, exc)
                continue
            documents[room] = document
            for ref in iter_map_refs(document["tree"]):
                if ref and ref not in documents and ref != primary_room:
                    queue.append(ref)
        return documents


def _primary_room(tree) -> str:
    root = next((node for node in tree.nodes if node.id == tree.root_id), None)
    key = (root.source_key if root else "") or ""
    if key.startswith("mindmap:") and key.count(":") >= 2:
        return key.split(":", 2)[1]
    return ""


async def import_linked_mindmaps(dataset_id: UUID, user) -> Any:
    """Fetch each linked mind map and write its nodes into the company tree."""
    from cognee.modules.company_tree.upsert import get_company_tree, upsert_company_tree

    tree = await get_company_tree(dataset_id, user)
    if tree.root_id is None:
        return tree
    primary = _primary_room(tree)
    rooms = [
        room_id_from_uri(node.linked_uri)
        for node in tree.nodes
        if node.kind == "map_reference" and room_id_from_uri(node.linked_uri)
    ]
    if not rooms:
        return tree
    async with MindMapMcpClient.from_env() as client:
        documents = await client.load_linked_documents(rooms, primary)
    if not documents:
        return tree
    payload = expand_company_tree(tree, documents)
    return await upsert_company_tree(dataset_id, user, payload)
