"""Canonical endpoint resolution shared by hierarchy and inline parent inputs."""

from typing import Any


def resolve_hierarchy_endpoints(
    raw: dict[str, Any], client_to_id: dict[str, str], canonical_ids: set[str]
) -> tuple[dict[str, str], str]:
    resolved = {}
    for side in ("parent", "child"):
        client = str(raw.get(f"{side}_client_id") or "").strip()
        candidate = str(raw.get(f"{side}_candidate_id") or "").strip()
        if client and candidate:
            return {}, "INVALID_HIERARCHY_ENDPOINT"
        if candidate:
            endpoint = candidate if candidate in canonical_ids else None
        elif client:
            endpoint = client if client in canonical_ids else client_to_id.get(client)
        else:
            endpoint = None
        if not endpoint or endpoint not in canonical_ids:
            return {}, "missing_endpoint"
        resolved[f"resolved_{side}_candidate_id"] = endpoint
    return resolved, ""


def inline_parent_link(raw: dict[str, Any], child_id: str) -> dict[str, Any] | None:
    """Normalize both parent aliases without silently choosing conflicting values."""
    fields = [key for key in ("parent_candidate_id", "parent_id") if key in raw]
    if not fields:
        return None
    values = [raw[key] for key in fields]
    return {
        "child_candidate_id": child_id,
        "parent_candidate_id": values[0],
        "reason": raw.get("reason", ""),
        "confidence": raw.get("confidence"),
        "evidence": raw.get("evidence", []),
        "evidence_node_ids": raw.get("evidence_node_ids", []),
        "source_node_ids": raw.get("source_node_ids", []),
        "inline_parent": True,
        "endpoint_error": "INVALID_HIERARCHY_ENDPOINT" if len(set(values)) > 1 else "",
    }
