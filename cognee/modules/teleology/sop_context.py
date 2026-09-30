"""Read-only, snapshot-first context for a proposed SOP."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.modules.teleology.goal_build import read_goal_model
from cognee.modules.teleology.sop_sources import (
    extract_factual_atoms,
    match_goals,
    resolve_request_sources,
    teleology_atoms,
)


def _current(item: dict[str, Any]) -> bool:
    return not item.get("outside_current_snapshot") and item.get("status") not in {
        "rejected",
        "legacy_confirmed",
    }


def _facts(mindmap_context: Any) -> list[dict[str, Any]]:
    """Legacy shape used by older callers. Prefer factual atoms for new code."""
    if isinstance(mindmap_context, list):
        values = mindmap_context
    elif isinstance(mindmap_context, dict):
        values = mindmap_context.get("facts") or mindmap_context.get("nodes") or []
    else:
        values = []
    return [value for value in values if isinstance(value, dict)]


def _existing_sops(mindmap_context: Any) -> list[Any]:
    if not isinstance(mindmap_context, dict):
        return []
    existing = mindmap_context.get("existing_sops")
    if not existing:
        existing = mindmap_context.get("existing_sop") or []
    if isinstance(existing, dict):
        return [existing]
    return list(existing or [])


def context_from_snapshot(
    snapshot: dict[str, Any],
    request: dict[str, Any],
    company_tree_nodes: Any = None,
) -> dict[str, Any]:
    """Build SOP context from a Goal Model snapshot and raw mind-map identities."""
    goals = [dict(goal) for goal in snapshot.get("candidates") or [] if _current(goal)]
    by_id = {str(goal.get("id")): goal for goal in goals}
    room_key = str(request.get("room_key") or "")
    atoms = extract_factual_atoms(request.get("mindmap_context"), room_key=room_key)
    refs, source_resolution, warnings = resolve_request_sources(request, atoms, company_tree_nodes)
    matched = match_goals(
        goals,
        room_key=room_key,
        refs=refs,
        atoms=atoms,
        company_tree_nodes=company_tree_nodes,
    )
    if matched["status"] != "RESOLVED":
        warnings.append(str(matched["reason"]))
    primary = matched["primary"]
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = by_id.get(str(primary.get("id"))) if primary else None
    while cursor and str(cursor.get("id")) not in seen:
        seen.add(str(cursor.get("id")))
        path.insert(0, {"id": cursor.get("id"), "name": cursor.get("name")})
        cursor = by_id.get(str(cursor.get("parent_candidate_id")))
    teleology = snapshot.get("teleology") or {}
    primary_id = str(primary.get("id")) if primary else ""

    def items(kind: str) -> list[dict[str, Any]]:
        if not primary_id:
            return []
        return [
            dict(item)
            for item in snapshot.get(kind, teleology.get(kind, [])) or []
            if _current(item) and str(item.get("goal_id") or item.get("source")) == primary_id
        ]

    purposes = items("purposes")
    constraints = items("constraints")
    evidence = []
    for goal in matched["related"]:
        evidence.extend(entry for entry in goal.get("evidence") or [] if isinstance(entry, dict))
    factual = atoms + teleology_atoms(purposes, constraints, room_key)
    return {
        "dataset_id": str(request.get("dataset_id") or ""),
        "run_id": snapshot.get("run_id"),
        "room_key": request.get("room_key"),
        "node_uid": request.get("node_uid"),
        "source_uids": sorted({ref["mindmap_uid"] for ref in refs if ref.get("mindmap_uid")}),
        "source_refs": refs,
        "source_resolution": source_resolution,
        "warnings": warnings,
        "goal_resolution_status": matched["status"],
        "goal_resolution_reason": matched["reason"],
        "mindmap_context": request.get("mindmap_context") or {},
        "existing_sops": _existing_sops(request.get("mindmap_context")),
        "related_goals": matched["related"],
        "primary_goal": primary,
        "goal_path": path,
        "purposes": purposes,
        "constraints": constraints,
        "semantic_relations": [
            dict(item)
            for item in snapshot.get("relations", teleology.get("relations", [])) or []
            if _current(item)
            and (str(item.get("source")) == primary_id or str(item.get("target")) == primary_id)
        ],
        "related_evidence": evidence,
        "factual_atoms": factual,
        "snapshot_first": True,
        "formal_graph_required": False,
    }


async def _company_tree_nodes(dataset_id: UUID, user: Any, room_key: str) -> list[dict[str, Any]]:
    from cognee.modules.company_tree.upsert import get_company_tree

    tree = await get_company_tree(dataset_id, user, room_key or None)
    nodes = []
    for node in tree.nodes:
        data = node.model_dump() if hasattr(node, "model_dump") else dict(node)
        nodes.append(data)
    return nodes


async def build_teleology_sop_context(request: dict[str, Any], user: Any) -> dict[str, Any]:
    """Authorize a dataset read and resolve mind-map uids inside Cognee."""
    dataset_id = UUID(str(request["dataset_id"]))
    snapshot = await read_goal_model(dataset_id, user)
    load_warnings: list[str] = []
    try:
        nodes = await _company_tree_nodes(dataset_id, user, str(request.get("room_key") or ""))
    except Exception as exc:  # noqa: BLE001 — context must explain a missed tree, not hide it
        nodes = []
        load_warnings.append(f"读取 company-tree 失败，无法解析 source_key：{type(exc).__name__}")
    context = context_from_snapshot(snapshot, request, nodes)
    if load_warnings:
        context["warnings"] = load_warnings + list(context.get("warnings") or [])
    return context
