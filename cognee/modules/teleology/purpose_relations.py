"""Which serves / advances / blocks edges count as real purpose relations.

An ``advances`` edge whose two ends are a direct company-tree parent and child
is structural. ``system_derived`` copies and legacy edges with no origin do
not count. A ``manual`` or ``ai_inferred`` edge counts only when it also has
its own reason or evidence. ``has_subgoal`` itself is never removed.
"""

from __future__ import annotations

import json
from typing import Any

_PURPOSE_RELATIONS = frozenset({"serves", "advances", "blocks"})
_REAL_ORIGINS = frozenset({"manual", "ai_inferred"})


def edge_properties(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        props = dict(raw)
        nested = props.pop("properties", None)
        if isinstance(nested, str) and nested.strip():
            try:
                props.update(json.loads(nested))
            except json.JSONDecodeError:
                pass
        elif isinstance(nested, dict):
            props.update(nested)
        return props
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _evidence_ids(props: dict[str, Any]) -> list[str]:
    raw = props.get("evidence_node_ids") or []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = [text]
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def has_independent_justification(props: dict[str, Any], source_id: str, target_id: str) -> bool:
    """True when a person or the purpose agent justified this edge on its own."""
    origin = str(props.get("origin") or "").strip()
    if origin not in _REAL_ORIGINS:
        return False
    reason = str(props.get("reason") or "").strip()
    endpoints = {source_id, target_id}
    extra = [node_id for node_id in _evidence_ids(props) if node_id not in endpoints]
    if origin == "ai_inferred":
        return bool(reason) and bool(extra)
    return bool(reason or extra)


def is_structural_advance(
    relationship: str,
    source_id: str,
    target_id: str,
    props: dict[str, Any],
    tree_pairs: set[tuple[str, str]],
) -> bool:
    """True when advances only restates a direct has_subgoal parent-child pair."""
    if str(relationship or "").lower() != "advances":
        return False
    forward = (source_id, target_id)
    reverse = (target_id, source_id)
    if forward not in tree_pairs and reverse not in tree_pairs:
        return False
    return not has_independent_justification(props, source_id, target_id)


def _rank(edge: dict[str, Any]) -> tuple[int, int, int]:
    props = edge.get("properties") or {}
    origin = str(props.get("origin") or "")
    reason = 1 if str(props.get("reason") or "").strip() else 0
    endpoints = {str(edge.get("source_id") or ""), str(edge.get("target_id") or "")}
    extra = 1 if any(node_id not in endpoints for node_id in _evidence_ids(props)) else 0
    return (1 if origin in _REAL_ORIGINS else 0, reason, extra)


def select_purpose_relations(
    edges: list[dict[str, Any]],
    tree_pairs: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Drop structural advances and duplicate source + relationship + target."""
    kept: list[dict[str, Any]] = []
    for edge in edges:
        relationship = str(edge.get("relationship") or "").lower()
        if relationship not in _PURPOSE_RELATIONS:
            continue
        source_id = str(edge.get("source_id") or "")
        target_id = str(edge.get("target_id") or "")
        props = edge.get("properties") or {}
        if str(props.get("origin") or "") == "system_derived":
            continue
        if props.get("retrieval_only") in (True, "true", "True", 1):
            continue
        if is_structural_advance(relationship, source_id, target_id, props, tree_pairs):
            continue
        kept.append({**edge, "relationship": relationship, "properties": props})
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for edge in kept:
        key = (str(edge["source_id"]), edge["relationship"], str(edge["target_id"]))
        current = best.get(key)
        if current is None:
            best[key] = edge
            order.append(key)
            continue
        if _rank(edge) > _rank(current):
            best[key] = edge
    return [best[key] for key in order]
