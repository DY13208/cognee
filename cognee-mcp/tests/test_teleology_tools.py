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
async def test_hierarchy_patch_fields_pass_through_without_loss():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)
    upserts = [
        {"candidate_id": "child", "parent_candidate_id": "parent"},
        {"client_id": "new", "parent_id": "parent"},
    ]
    links = [
        {
            "child_candidate_id": "child",
            "parent_candidate_id": "parent",
            "reason": "ownership",
            "evidence_node_ids": ["doc"],
        }
    ]
    for tool in ("validate_teleology_goal_model", "propose_teleology_goal_model"):
        await registry.tools[tool](
            "dataset",
            [],
            submission_mode="patch",
            base_run_id="base",
            upsert_goals=upserts,
            hierarchy=links,
        )
        body = client.calls[-1][2]
        assert body["upsert_goals"] == upserts
        assert body["hierarchy"] == links
        assert body["dry_run"] is (tool == "validate_teleology_goal_model")


@pytest.mark.asyncio
async def test_proposal_review_tools_only_issue_get_requests():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)

    await registry.tools["list_teleology_proposals"]("dataset-1", run_id="run-1")
    await registry.tools["get_teleology_proposal"]("dataset-1", "proposal-1")
    await registry.tools["get_teleology_coverage_items"]("run-1", status="done")

    assert [call[0] for call in client.calls] == ["GET", "GET", "GET"]
    assert client.calls[0][3]["run_id"] == "run-1"
    assert client.calls[1][3] == {"dataset_id": "dataset-1"}
    assert client.calls[2][3]["status"] == "done"


@pytest.mark.asyncio
async def test_sop_validate_uses_explicit_raw_source_context():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)
    raw = {"target": {"uid": "node-1", "name": "<p>P：制定项目利润目标</p>"}}
    proposal = {"plan": [{"id": "P1", "text": "制定项目利润目标"}]}
    await registry.tools["validate_sop_proposal"](
        "dataset-1", "room-1", "node-1", ["node-1"], raw, proposal
    )
    assert client.calls == [
        (
            "POST",
            "/api/v1/teleology/sop/proposals/validate",
            {
                "dataset_id": "dataset-1",
                "proposal": proposal,
                "context": {
                    "room_key": "room-1",
                    "node_uid": "node-1",
                    "source_uids": ["node-1"],
                    "mindmap_context": raw,
                },
            },
            None,
        )
    ]


@pytest.mark.asyncio
async def test_review_tools_omit_absent_filters():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)

    await registry.tools["list_teleology_proposals"]("dataset-1")
    await registry.tools["list_teleology_proposals"](
        "dataset-1", run_id="", source_goal_id=" ", status="open"
    )
    await registry.tools["get_teleology_coverage_items"]("run-1")
    await registry.tools["get_teleology_coverage_items"]("run-1", status="")

    assert client.calls[0][3] == {"dataset_id": "dataset-1", "limit": 50, "offset": 0}
    assert client.calls[1][3] == {
        "dataset_id": "dataset-1",
        "status": "open",
        "limit": 50,
        "offset": 0,
    }
    assert client.calls[2][3] == {"limit": 50, "offset": 0}
    assert client.calls[3][3] == {"limit": 50, "offset": 0}


@pytest.mark.asyncio
async def test_run_commit_tools_are_scoped_to_one_run_and_preview_first():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)

    await registry.tools["preview_teleology_run_commit"]("dataset-1", "run-1")
    await registry.tools["commit_teleology_run"]("dataset-1", "run-1")

    assert client.calls == [
        (
            "POST",
            "/api/v1/teleology/coverage/runs/run-1/commit-all",
            {"dataset_id": "dataset-1", "dry_run": True},
            None,
        ),
        (
            "POST",
            "/api/v1/teleology/coverage/runs/run-1/commit-all",
            {"dataset_id": "dataset-1", "dry_run": False},
            None,
        ),
    ]


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
        (
            "POST",
            "/api/v1/teleology/nodes",
            {
                "type": "goal",
                "name": "Ship",
                "status": "proposed",
                "description": "",
                "keywords": [],
            },
            None,
        ),
        (
            "POST",
            "/api/v1/teleology/annotations/sync-from-company-tree",
            None,
            {
                "dataset_id": "dataset-1",
                "link_entities": False,
                "source_room": "room-1",
            },
        ),
        (
            "POST",
            "/api/v1/teleology/annotations",
            {
                "dataset_id": "dataset-1",
                "source_id": "source",
                "target_id": "goal",
                "relationship": "serves",
            },
            None,
        ),
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


@pytest.mark.asyncio
async def test_goal_network_fields_pass_through_and_loop_read_is_get():
    registry = FakeRegistry()
    client = FakeClient()
    register_teleology_tools(registry, lambda: client)
    goals = [
        {
            "client_id": "d",
            "name": "driver",
            "node_type": "driver",
            "reason": "mechanism",
            "confidence": 0.8,
            "evidence_node_ids": ["doc"],
        }
    ]
    relations = [
        {
            "source_client_id": "d",
            "target_client_id": "g",
            "relationship": "amplifies",
            "condition": {"status": "inactive"},
            "reason": "risk",
            "confidence": 0.7,
            "evidence_node_ids": ["doc"],
        }
    ]
    for tool in ["validate_teleology_goal_model", "propose_teleology_goal_model"]:
        await registry.tools[tool]("dataset", goals, relations=relations)
        body = client.calls[-1][2]
        assert body["goals"] == goals
        assert body["relations"] == relations
    await registry.tools["get_teleology_goal_network_loops"]("dataset")
    assert client.calls[-1] == (
        "GET",
        "/api/v1/teleology/goal-model/loops",
        None,
        {"dataset_id": "dataset"},
    )


@pytest.mark.asyncio
async def test_patch_candidate_endpoints_and_loop_preview_pass_through():
    class PreviewClient(FakeClient):
        async def api_request(self, method, path, *, json_body=None, params=None):
            await super().api_request(method, path, json_body=json_body, params=params)
            return {
                "saved": False,
                "loop_preview": [
                    {
                        "loop_type": "Reinforcing",
                        "nodes": ["canonical", "new"],
                        "conditions": [],
                        "confidence": 0.8,
                    }
                ],
            }

    registry = FakeRegistry()
    client = PreviewClient()
    register_teleology_tools(registry, lambda: client)
    relations = [
        {"source_candidate_id": "canonical", "target_client_id": "new", "relationship": "drives"}
    ]
    upsert = [{"candidate_id": "canonical"}, {"client_id": "new", "node_type": "driver"}]
    output = await registry.tools["validate_teleology_goal_model"](
        "dataset",
        [],
        submission_mode="patch",
        base_run_id="base",
        upsert_goals=upsert,
        relations=relations,
    )
    body = client.calls[-1][2]
    assert body["dry_run"] is True
    assert body["upsert_goals"] == upsert
    assert body["relations"] == relations
    result = json.loads(output[0].text)
    assert result["saved"] is False
    assert result["loop_preview"][0]["loop_type"] == "Reinforcing"
