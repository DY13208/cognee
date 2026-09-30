"""Read-only, snapshot-first context for a proposed SOP."""

from __future__ import annotations

from typing import Any

from cognee.modules.teleology.goal_build import read_goal_model


def _ids(item: dict[str, Any]) -> set[str]:
    ids = {
        str(value)
        for key in ("source_node_ids", "evidence_node_ids", "source_uids")
        for value in item.get(key) or []
    }
    ids.update(
        str(e.get("node_id"))
        for e in item.get("evidence") or []
        if isinstance(e, dict) and e.get("node_id")
    )
    return ids


def _current(item: dict[str, Any]) -> bool:
    return not item.get("outside_current_snapshot") and item.get("status") not in {
        "rejected",
        "legacy_confirmed",
    }


def _facts(mindmap_context: Any) -> list[dict[str, Any]]:
    if isinstance(mindmap_context, list):
        values = mindmap_context
    elif isinstance(mindmap_context, dict):
        values = mindmap_context.get("facts") or mindmap_context.get("nodes") or []
    else:
        values = []
    return [value for value in values if isinstance(value, dict)]


def context_from_snapshot(snapshot: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    goals = [dict(g) for g in snapshot.get("candidates") or [] if _current(g)]
    wanted = {str(x) for x in request.get("source_uids") or []}
    node_uid = str(request.get("node_uid") or "")
    if node_uid:
        wanted.add(node_uid)
    facts = _facts(request.get("mindmap_context"))
    for fact in facts:
        for key in ("source_uid", "node_uid", "uid"):
            if fact.get(key):
                wanted.add(str(fact[key]))
    query = " ".join(str(f.get("text") or f.get("name") or "") for f in facts).lower()

    def score(goal: dict[str, Any]) -> int:
        overlap = len(_ids(goal) & wanted)
        name = str(goal.get("name") or "").strip().lower()
        return overlap * 10 + (1 if name and len(name) > 3 and name in query else 0)

    related = sorted(
        (g for g in goals if score(g) > 0), key=lambda g: (-score(g), str(g.get("id")))
    )
    primary = related[0] if related else None
    by_id = {str(g.get("id")): g for g in goals}
    path = []
    seen = set()
    cursor = primary
    while cursor and str(cursor.get("id")) not in seen:
        seen.add(str(cursor.get("id")))
        path.insert(0, {"id": cursor.get("id"), "name": cursor.get("name")})
        cursor = by_id.get(str(cursor.get("parent_candidate_id")))
    related_ids = {str(g.get("id")) for g in related}
    teleology = snapshot.get("teleology") or {}

    def items(kind: str) -> list[dict[str, Any]]:
        return [
            dict(i)
            for i in snapshot.get(kind, teleology.get(kind, [])) or []
            if _current(i) and str(i.get("goal_id") or i.get("source")) in related_ids
        ]

    evidence = []
    for goal in related:
        evidence.extend(e for e in goal.get("evidence") or [] if isinstance(e, dict))
    return {
        "dataset_id": str(request.get("dataset_id") or ""),
        "run_id": snapshot.get("run_id"),
        "room_key": request.get("room_key"),
        "node_uid": request.get("node_uid"),
        "source_uids": sorted(wanted),
        "mindmap_context": request.get("mindmap_context") or {},
        "existing_sops": (request.get("mindmap_context") or {}).get("existing_sops", [])
        if isinstance(request.get("mindmap_context"), dict)
        else [],
        "related_goals": related,
        "primary_goal": primary,
        "goal_path": path,
        "purposes": items("purposes"),
        "constraints": items("constraints"),
        "semantic_relations": [
            dict(i)
            for i in snapshot.get("relations", teleology.get("relations", [])) or []
            if _current(i)
            and (str(i.get("source")) in related_ids or str(i.get("target")) in related_ids)
        ],
        "related_evidence": evidence,
        "snapshot_first": True,
        "formal_graph_required": False,
    }


async def build_teleology_sop_context(request: dict[str, Any], user: Any) -> dict[str, Any]:
    """Authorize a dataset read and use its current Goal Model snapshot."""
    from uuid import UUID

    snapshot = await read_goal_model(UUID(str(request["dataset_id"])), user)
    return context_from_snapshot(snapshot, request)
