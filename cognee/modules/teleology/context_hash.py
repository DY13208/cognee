"""Stable fingerprint of the bounded context one proposal was analyzed against."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _pairs(nodes: list[dict[str, Any]] | None) -> list[list[str]]:
    rows = [
        [str(node.get("id") or ""), str(node.get("name") or "")]
        for node in nodes or []
        if str(node.get("id") or "").strip()
    ]
    rows.sort()
    return rows


def _ids(nodes: list[dict[str, Any]] | None) -> list[str]:
    return sorted({str(node.get("id") or "") for node in nodes or [] if str(node.get("id") or "")})


def context_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    """Canonical, order-independent view of everything that can change an analysis."""
    goal = context.get("goal") or {}
    relations = [
        [
            str(item.get("source_id") or item.get("source") or ""),
            str(item.get("relationship") or ""),
            str(item.get("target_id") or item.get("target") or ""),
        ]
        for item in context.get("relations") or []
    ]
    relations.sort()
    child_evidence = []
    for entry in context.get("child_evidence") or []:
        child_evidence.append(
            [
                str(entry.get("goal_id") or ""),
                _ids(entry.get("entities")),
                _ids(entry.get("documents")),
            ]
        )
    child_evidence.sort(key=lambda row: row[0])
    return {
        "dataset_id": str(context.get("dataset_id") or ""),
        "goal_id": str(goal.get("id") or ""),
        "goal_name": str(goal.get("name") or ""),
        "goal_note": str(context.get("note") or goal.get("description") or ""),
        "ancestors": _pairs(context.get("ancestors")),
        "children": _pairs(context.get("children")),
        "children_total": int(context.get("children_total") or 0),
        "purposes": _ids(context.get("purposes")),
        "constraints": _ids(context.get("constraints")),
        "relations": relations,
        "entities": _ids(context.get("entities")),
        "documents": _ids(context.get("documents")),
        "child_evidence": child_evidence,
    }


def context_hash(context: dict[str, Any]) -> str:
    raw = json.dumps(
        context_fingerprint(context), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
