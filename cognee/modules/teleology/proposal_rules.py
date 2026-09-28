"""Validation shared by proposal creation and commit."""

from __future__ import annotations

import os
import re
from typing import Any

_AI_GENERATORS = frozenset({"purpose-agent", "workbuddy"})
_ALLOWED_GENERATED_BY = frozenset({"purpose-agent", "workbuddy", "manual", "purpose-context"})
_CONSTRAINT_MARKERS = (
    "限制",
    "禁止",
    "合规",
    "前置",
    "边界",
    "风险",
    "依赖",
    "不得",
    "sla",
    "截止",
    "成本",
    "预算",
    "时限",
)
_OVERREACH = re.compile(r"必须使用|必须锚定|须锚定|必须通过|must use", re.IGNORECASE)


def min_relation_confidence() -> float:
    raw = os.getenv("TELEOLOGY_PROPOSAL_MIN_RELATION_CONFIDENCE", "0.60")
    try:
        value = float(raw)
    except ValueError:
        return 0.6
    return value if 0 <= value <= 1 else 0.6


def normalize_generated_by(value: str | None, *, external: bool) -> str:
    """External callers may only claim workbuddy or manual."""
    text = str(value or "").strip()
    if external:
        if text in {"", "workbuddy"}:
            return "workbuddy"
        if text == "manual":
            return "manual"
        raise ValueError("generated_by must be workbuddy or manual")
    if text not in _ALLOWED_GENERATED_BY:
        raise ValueError("generated_by is not a known teleology source")
    return text


def visible_context_ids(context: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            found.add(text)

    goal = context.get("goal") or {}
    add(goal.get("id"))
    for key in ("ancestors", "children", "purposes", "constraints", "entities", "documents"):
        for node in context.get(key) or []:
            if isinstance(node, dict):
                add(node.get("id"))
    for relation in context.get("relations") or []:
        if isinstance(relation, dict):
            add(relation.get("source_id"))
            add(relation.get("target_id"))
    for entry in context.get("child_evidence") or []:
        if not isinstance(entry, dict):
            continue
        add(entry.get("goal_id"))
        for bucket in ("entities", "documents"):
            for node in entry.get(bucket) or []:
                if isinstance(node, dict):
                    add(node.get("id"))
    return found


def constraint_overreach(item: dict[str, Any]) -> bool:
    text = f"{item.get('name') or ''} {item.get('description') or ''} {item.get('reason') or ''}"
    if not _OVERREACH.search(text):
        return False
    lowered = text.casefold()
    return not any(marker in lowered for marker in _CONSTRAINT_MARKERS)


def partition_ai_items(
    items: list[dict[str, Any]],
    *,
    generated_by: str,
    context: dict[str, Any] | None,
    open_items: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Drop illegal AI evidence and park weak relations outside the formal items."""
    if generated_by not in _AI_GENERATORS:
        return items, [], [], []
    visible = visible_context_ids(context or {})
    current_ids = {str(item.get("id") or "") for item in items}
    foreign = [
        item
        for item in open_items or []
        if str(item.get("proposal_id") or "") and str(item.get("id") or "") not in current_ids
    ]
    foreign_ids = {str(item.get("id") or "") for item in foreign}
    kept: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    warnings: list[str] = []
    threshold = min_relation_confidence()
    for item in items:
        kind = item.get("kind")
        if kind == "gap":
            kept.append(item)
            continue
        reason = str(item.get("reason") or "").strip()
        evidence = [node_id for node_id in item.get("evidence_node_ids") or [] if str(node_id).strip()]
        confidence = item.get("confidence")
        illegal = [node_id for node_id in evidence if node_id not in visible]
        if illegal:
            warnings.append(f"dropped evidence outside the current context: {', '.join(illegal)}")
            evidence = [node_id for node_id in evidence if node_id in visible]
            item = {**item, "evidence_node_ids": evidence}
        if not reason or confidence is None or not evidence:
            warnings.append(f"dropped {kind} without reason, confidence, and context evidence")
            continue
        if kind == "constraint" and constraint_overreach(item):
            weak.append({**item, "weak_reason": "constraint_overreach"})
            continue
        if kind == "relation" and float(confidence) < threshold:
            weak.append({**item, "weak_reason": "low_confidence"})
            continue
        if kind == "relation":
            source = str(item.get("source") or "")
            target = str(item.get("target") or "")
            blocked = next((node_id for node_id in (source, target) if node_id in foreign_ids), "")
            if blocked:
                other = next(entry for entry in foreign if str(entry.get("id")) == blocked)
                conflicts.append(
                    {
                        "type": "similar_open_proposal",
                        "proposal_id": other.get("proposal_id"),
                        "item_id": blocked,
                        "name": other.get("name") or "",
                    }
                )
                continue
        kept.append(item)
    for item in kept:
        if item.get("kind") != "purpose":
            continue
        name = str(item.get("name") or "").casefold()
        for other in foreign:
            if other.get("kind") == "purpose" and str(other.get("name") or "").casefold() == name:
                conflicts.append(
                    {
                        "type": "similar_open_proposal",
                        "proposal_id": other.get("proposal_id"),
                        "item_id": other.get("id"),
                        "name": other.get("name") or "",
                    }
                )
    return kept, weak, conflicts, warnings
