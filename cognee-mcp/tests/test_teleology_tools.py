"""Teleology MCP tools should follow the HTTP API contract."""

import json
import sys
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from src.teleology_tools import register_teleology_tools  # noqa: E402


class FakeRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self, *, tags):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn

        return register


class FakeClient:
    def __init__(self):
        self.calls = []

    async def api_request(self, method, path, *, json_body=None, params=None):
        self.calls.append((method, path, json_body, params))
        return {"ok": True}

    async def upload_teleology_yaml(self, filename, content):
        self.calls.append(("UPLOAD", filename, content))
        return {"ok": True}


@pytest.mark.asyncio
async def test_teleology_tools_route_to_api():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)

    await registry.tools["create_teleology_node"]("goal", "Ship")
    await registry.tools["sync_teleology_from_company_tree"]("dataset-1", False, "room-1")
    await registry.tools["create_teleology_annotation"]("dataset-1", "source", "goal", "serves")
    await registry.tools["upload_teleology_yaml"]("goals.yaml", "goals: []")

    assert client.calls == [
        ("POST", "/api/v1/teleology/nodes", {
            "type": "goal", "name": "Ship", "status": "proposed",
            "description": "", "keywords": [],
        }, None),
        ("POST", "/api/v1/teleology/annotations/sync-from-company-tree", None, {
            "dataset_id": "dataset-1", "link_entities": False, "source_room": "room-1",
        }),
        ("POST", "/api/v1/teleology/annotations", {
            "dataset_id": "dataset-1", "source_id": "source", "target_id": "goal",
            "relationship": "serves",
        }, None),
        ("UPLOAD", "goals.yaml", "goals: []"),
    ]


@pytest.mark.asyncio
async def test_update_rejects_non_object_payload():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)

    result = await registry.tools["update_teleology_node"]("node-1", json.dumps(["bad"]))

    assert result[0].text.startswith("Error:")
    assert client.calls == []
