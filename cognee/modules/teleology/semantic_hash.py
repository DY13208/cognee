"""Hash the facts that should trigger another purpose analysis.

This is not ``context_hash``. ``context_hash`` still decides whether an open
proposal is stale at commit time. ``semantic_context_hash`` decides whether a
goal is worth another LLM call.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _text(*parts: Any) -> str:
    return "\n".join(str(part or "") for part in parts)


def evidence_content_hash(entry: dict[str, Any] | None) -> str:
    """Hash evidence content. The node id alone is not enough."""
    entry = entry or {}
    raw = _text(
        entry.get("type"),
        entry.get("name"),
        entry.get("description"),
        entry.get("summary"),
        entry.get("text"),
        entry.get("source_note"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_rows(entries: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    rows = []
    for entry in entries or []:
        node_id = str(entry.get("id") or "").strip()
        if not node_id:
            continue
        rows.append(
            {
                "id": node_id,
                "type": str(entry.get("type") or ""),
                "content_hash": evidence_content_hash(entry),
            }
        )
    rows.sort(key=lambda row: (row["id"], row["type"], row["content_hash"]))
    return rows


def _child_evidence_rows(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = []
    for entry in entries or []:
        rows.append(
            {
                "goal_id": str(entry.get("goal_id") or ""),
                "entities": _evidence_rows(entry.get("entities")),
                "documents": _evidence_rows(entry.get("documents")),
            }
        )
    rows.sort(key=lambda row: row["goal_id"])
    return rows


def semantic_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    """Stable facts for one goal. Timestamps, progress, and UI fields are omitted."""
    goal = context.get("goal") or {}
    children = []
    for child in context.get("children") or []:
        child_id = str(child.get("id") or "").strip()
        if not child_id:
            continue
        children.append(
            {
                "id": child_id,
                "semantic_role": str(child.get("semantic_role") or "goal"),
                "name": str(child.get("name") or ""),
                "description": str(child.get("description") or ""),
            }
        )
    children.sort(key=lambda row: row["id"])
    confirmed = []
    for kind in ("purposes", "constraints"):
        for node in context.get(kind) or []:
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue
            confirmed.append(
                {
                    "kind": kind[:-1],
                    "id": node_id,
                    "name": str(node.get("name") or ""),
                    "description": str(node.get("description") or node.get("summary") or ""),
                }
            )
    confirmed.sort(key=lambda row: (row["kind"], row["id"]))
    relations = []
    for item in context.get("relations") or []:
        if str(item.get("origin") or "") == "system_derived" or item.get("retrieval_only"):
            continue
        relation = str(item.get("relationship") or "")
        if relation not in {"serves", "advances", "blocks"}:
            continue
        relations.append(
            [
                str(item.get("source_id") or item.get("source") or ""),
                relation,
                str(item.get("target_id") or item.get("target") or ""),
            ]
        )
    relations.sort()
    return {
        "goal": {
            "id": str(goal.get("id") or ""),
            "name": str(goal.get("name") or ""),
            "description": str(goal.get("description") or ""),
            "note": str(context.get("note") or ""),
        },
        "children": children,
        "confirmed": confirmed,
        "relations": relations,
        "entities": _evidence_rows(context.get("entities")),
        "documents": _evidence_rows(context.get("documents")),
        "child_evidence": _child_evidence_rows(context.get("child_evidence")),
    }


def semantic_context_hash(context: dict[str, Any]) -> str:
    raw = json.dumps(
        semantic_fingerprint(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
