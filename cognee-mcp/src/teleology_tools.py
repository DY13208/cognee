"""Dedicated MCP tools for the purpose/teleology page."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

from mcp import types

logger = logging.getLogger(__name__)


def register_teleology_tools(registry, get_client) -> None:
    async def request(method: str, path: str, *, body=None, params=None, safe_error=False):
        try:
            result = await get_client().api_request(method, path, json_body=body, params=params)
            return [
                types.TextContent(
                    type="text", text=json.dumps(result, ensure_ascii=False, default=str)
                )
            ]
        except Exception as exc:
            logger.exception("Teleology MCP %s %s failed", method, path)
            message = "Teleology request failed." if safe_error else f"{type(exc).__name__}: {exc}"
            return [types.TextContent(type="text", text=f"Error: {message}")]

    @registry.tool(tags={"teleology"})
    async def get_teleology(q: str = None, limit: int = 80, offset: int = 0) -> list:
        """Read the active teleology YAML status and paginated goals, purposes and constraints."""
        return await request(
            "GET", "/api/v1/teleology", params={"q": q, "limit": limit, "offset": offset}
        )

    @registry.tool(tags={"teleology"})
    async def create_teleology_node(
        node_type: str,
        name: str,
        status: str = "proposed",
        description: str = "",
        keywords: list[str] = None,
    ) -> list:
        """Create a teleology goal, purpose or constraint in the active YAML."""
        return await request(
            "POST",
            "/api/v1/teleology/nodes",
            body={
                "type": node_type,
                "name": name,
                "status": status,
                "description": description,
                "keywords": keywords or [],
            },
        )

    @registry.tool(tags={"teleology"})
    async def update_teleology_node(node_id: str, changes_json: str) -> list:
        """Update a teleology node. changes_json is a JSON object of type/name/status/description/keywords."""
        try:
            changes = json.loads(changes_json)
            if not isinstance(changes, dict):
                raise ValueError("changes_json must be a JSON object")
        except (ValueError, TypeError) as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]
        return await request(
            "PUT", f"/api/v1/teleology/nodes/{quote(node_id, safe='')}", body=changes
        )

    @registry.tool(tags={"teleology"})
    async def delete_teleology_node(node_id: str, node_type: str = None) -> list:
        """Delete a teleology node by ID, optionally specifying goal/purpose/constraint."""
        return await request(
            "DELETE",
            f"/api/v1/teleology/nodes/{quote(node_id, safe='')}",
            params={"node_type": node_type},
        )

    @registry.tool(tags={"teleology"})
    async def upload_teleology_yaml(filename: str, yaml_content: str) -> list:
        """Replace the active teleology YAML with supplied UTF-8 content (.yaml or .yml)."""
        try:
            result = await get_client().upload_teleology_yaml(filename, yaml_content)
            return [
                types.TextContent(
                    type="text", text=json.dumps(result, ensure_ascii=False, default=str)
                )
            ]
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
        dataset_id: str,
        q: str = None,
        limit: int = 200,
        goals_limit: int = 120,
        goals_offset: int = 0,
        goal_id: str = None,
        parent_id: str = None,
    ) -> list:
        """List purpose edges and annotatable graph nodes for a brain/dataset."""
        return await request(
            "GET",
            "/api/v1/teleology/annotations",
            params={
                "dataset_id": dataset_id,
                "q": q,
                "limit": limit,
                "goals_limit": goals_limit,
                "goals_offset": goals_offset,
                "goal_id": goal_id,
                "parent_id": parent_id,
            },
        )

    @registry.tool(tags={"teleology"})
    async def sync_teleology_goals(dataset_id: str) -> list:
        """Sync YAML goals, purposes and constraints into a dataset graph."""
        return await request(
            "POST", "/api/v1/teleology/annotations/sync-goals", params={"dataset_id": dataset_id}
        )

    @registry.tool(tags={"teleology"})
    async def sync_teleology_from_company_tree(
        dataset_id: str, link_entities: bool = False, source_room: str = None
    ) -> list:
        """Read the company tree and stamp structural edges. Does not generate teleology."""
        return await request(
            "POST",
            "/api/v1/teleology/annotations/sync-from-company-tree",
            params={
                "dataset_id": dataset_id,
                "link_entities": link_entities,
                "source_room": source_room,
            },
        )

    @registry.tool(tags={"teleology"})
    async def create_teleology_annotation(
        dataset_id: str, source_id: str, target_id: str, relationship: str
    ) -> list:
        """Attach a serves, advances or blocks edge from a graph node to a goal."""
        return await request(
            "POST",
            "/api/v1/teleology/annotations",
            body={
                "dataset_id": dataset_id,
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
            },
        )

    @registry.tool(tags={"teleology"})
    async def delete_teleology_annotation(
        dataset_id: str, source_id: str, target_id: str, relationship: str
    ) -> list:
        """Remove a purpose edge while keeping its endpoint nodes."""
        return await request(
            "DELETE",
            "/api/v1/teleology/annotations",
            params={
                "dataset_id": dataset_id,
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
            },
        )

    @registry.tool(tags={"teleology"})
    async def analyze_purpose_relations(dataset_id: str, goal_id: str) -> list:
        """Cognee built-in analysis for one goal. Stores a proposal as purpose-agent and does not commit it. Read-only toward the company tree and the formal graph."""
        return await request(
            "POST",
            "/api/v1/teleology/analyze",
            body={
                "dataset_id": dataset_id,
                "goal_id": goal_id,
            },
        )

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
        return await request(
            "POST",
            "/api/v1/teleology/annotations/purpose-proposals",
            body={
                "dataset_id": dataset_id,
                "source_goal_id": source_goal_id,
                "proposal": proposal,
                "generated_by": generated_by or "workbuddy",
            },
        )

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

    @registry.tool(tags={"teleology"})
    async def list_teleology_proposals(
        dataset_id: str,
        run_id: str = None,
        source_goal_id: str = None,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Read paginated proposal summaries within a dataset, optionally for one coverage run."""
        params = {"dataset_id": dataset_id, "limit": limit, "offset": offset}
        for key, value in (
            ("run_id", run_id),
            ("source_goal_id", source_goal_id),
            ("status", status),
        ):
            if value and value.strip():
                params[key] = value.strip()
        return await request("GET", "/api/v1/teleology/proposals", params=params, safe_error=True)

    @registry.tool(tags={"teleology"})
    async def get_teleology_proposal(dataset_id: str, proposal_id: str) -> list:
        """Read all review items and evidence for one dataset-scoped proposal."""
        return await request(
            "GET",
            f"/api/v1/teleology/proposals/{quote(proposal_id, safe='')}",
            params={"dataset_id": dataset_id},
            safe_error=True,
        )

    @registry.tool(tags={"teleology"})
    async def get_teleology_coverage_items(
        run_id: str,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Read persisted queue items for one coverage run without changing their status."""
        params = {"limit": limit, "offset": offset}
        if status and status.strip():
            params["status"] = status.strip()
        return await request(
            "GET",
            f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/items",
            params=params,
            safe_error=True,
        )

    @registry.tool(tags={"teleology"})
    async def preview_teleology_run_commit(dataset_id: str, run_id: str) -> list:
        """Read-only preview for one reviewed Coverage Run. Equivalent to dry_run. Reports every valid formal proposal item a later commit would write. Weak signals and conflicts are never committed."""
        return await request(
            "POST",
            f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/commit-all",
            body={"dataset_id": dataset_id, "dry_run": True},
        )

    @registry.tool(tags={"teleology"})
    async def commit_teleology_run(dataset_id: str, run_id: str) -> list:
        """Commit every valid formal proposal item for one reviewed Coverage Run.

        Weak signals and conflicts are never committed. This writes the formal teleology graph.
        It never submits every open proposal in the dataset.
        """
        return await request(
            "POST",
            f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/commit-all",
            body={"dataset_id": dataset_id, "dry_run": False},
        )

    @registry.tool(tags={"teleology"})
    async def start_teleology_coverage(
        dataset_id: str,
        mode: str = "incremental",
        batch_size: int = 20,
        concurrency: int = 3,
        max_goals: int | None = None,
        token_budget: int | None = None,
    ) -> list:
        """Continue teleology for an existing AI Goal Model. Modes: baseline, incremental, force.

        Coverage does not discover goals and does not walk the company tree as the goal list.
        Run start_teleology_build first. This only creates proposals. It never commits them.
        Use max_goals for a pilot. Omit it only when a full run is intended.
        """
        body = {
            "dataset_id": dataset_id,
            "mode": mode or "incremental",
            "batch_size": batch_size or 20,
            "concurrency": concurrency or 3,
        }
        if max_goals:
            body["max_goals"] = max_goals
        if token_budget:
            body["token_budget"] = token_budget
        return await request("POST", "/api/v1/teleology/coverage/runs", body=body)

    @registry.tool(tags={"teleology"})
    async def start_teleology_build(
        dataset_id: str,
        mode: str = "baseline",
        batch_size: int = 20,
        concurrency: int = 1,
        max_sources: int | None = None,
    ) -> list:
        """Queue an AI Goal Model build. Returns run_id and status pending immediately.

        Poll get_teleology_build_status until status is completed, then read
        get_teleology_goal_model. Company-tree nodes are evidence, not goals.
        The run stores proposals only. It never commits them and it never writes
        the company tree. A client timeout does not cancel the build.
        """
        body = {
            "dataset_id": dataset_id,
            "mode": mode or "baseline",
            "batch_size": batch_size or 20,
            "concurrency": concurrency or 1,
        }
        if max_sources:
            body["max_sources"] = max_sources
        return await request("POST", "/api/v1/teleology/builds", body=body)

    @registry.tool(tags={"teleology"})
    async def propose_teleology_goal_model(
        dataset_id: str,
        goals: list,
        hierarchy: list | None = None,
        purposes: list | None = None,
        constraints: list | None = None,
        relations: list | None = None,
        generated_by: str = "workbuddy_orchestrated",
    ) -> list:
        """Submit a WorkBuddy mind-map analysis as an AI Goal Model proposal.

        Cognee validates evidence and stores derived proposals only.
        This does not confirm, commit, write the company tree, or write the formal graph.
        """
        return await request(
            "POST",
            "/api/v1/teleology/goal-model/proposals",
            body={
                "dataset_id": dataset_id,
                "generated_by": generated_by or "workbuddy_orchestrated",
                "goals": goals or [],
                "hierarchy": hierarchy or [],
                "purposes": purposes or [],
                "constraints": constraints or [],
                "relations": relations or [],
            },
        )

    @registry.tool(tags={"teleology"})
    async def get_teleology_build_status(run_id: str) -> list:
        """Read one goal build: status, stage, progress, and error.

        Call this after start_teleology_build until status is completed or failed.
        This does not write the graph.
        """
        return await request("GET", f"/api/v1/teleology/builds/{quote(run_id, safe='')}")

    @registry.tool(tags={"teleology"})
    async def get_teleology_goal_model(dataset_id: str) -> list:
        """Read the derived AI Goal Model: hierarchy, purpose, constraint, and relations.

        Every goal carries reason, confidence, evidence, and source nodes.
        This does not write the graph.
        """
        return await request(
            "GET", "/api/v1/teleology/goal-model", params={"dataset_id": dataset_id}
        )

    @registry.tool(tags={"teleology"})
    async def get_teleology_coverage_status(run_id: str) -> list:
        """Read one coverage run. The queue is in the database, so this survives an API restart."""
        return await request("GET", f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}")

    @registry.tool(tags={"teleology"})
    async def pause_teleology_coverage(run_id: str) -> list:
        """Stop claiming new goals. A goal already sent to the model can finish."""
        return await request(
            "POST", f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/pause"
        )

    @registry.tool(tags={"teleology"})
    async def resume_teleology_coverage(run_id: str) -> list:
        """Continue a paused coverage run from the stored queue."""
        return await request(
            "POST", f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/resume"
        )

    @registry.tool(tags={"teleology"})
    async def cancel_teleology_coverage(run_id: str) -> list:
        """Cancel a coverage run. Pending goals are not analyzed. Nothing is committed."""
        return await request(
            "POST", f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/cancel"
        )

    @registry.tool(tags={"teleology"})
    async def retry_teleology_coverage_failures(run_id: str) -> list:
        """Requeue failed goals and continue. Successful goals are not repeated."""
        return await request(
            "POST", f"/api/v1/teleology/coverage/runs/{quote(run_id, safe='')}/retry-failures"
        )
