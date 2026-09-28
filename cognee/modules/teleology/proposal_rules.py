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
_STRUCTURAL_REASON = re.compile(
    r"直接子目标|上级节点|结构上(?:明确)?归属|层级关系|符合\s*goal\s*tree(?:\s*结构)?|"
    r"\bparent\b|\bancestor\b|\bhierarchy\b",
    re.IGNORECASE,
)


def same_purpose(left: str, right: str) -> bool:
    """Match exact normalized names and obvious near duplicates."""
    first = "".join(ch for ch in str(left or "").casefold() if not ch.isspace())
    second = "".join(ch for ch in str(right or "").casefold() if not ch.isspace())
    if len(first) < 4 or len(second) < 4:
        return first == second and len(first) >= 2
    shorter, longer = (first, second) if len(first) <= len(second) else (second, first)
    return shorter in longer


def _context_node_types(context: dict[str, Any]) -> dict[str, str]:
    types: dict[str, str] = {}
    for key, default_type in (
        ("goal", "Goal"),
        ("ancestors", "Goal"),
        ("children", "Goal"),
        ("purposes", "Purpose"),
        ("constraints", "Constraint"),
        ("entities", "Entity"),
        ("documents", "Document"),
    ):
        nodes = [context.get(key)] if key == "goal" else context.get(key) or []
        for node in nodes:
            if isinstance(node, dict) and node.get("id"):
                types[str(node["id"])] = str(node.get("type") or default_type).casefold()
    for entry in context.get("child_evidence") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("goal_id"):
            types[str(entry["goal_id"])] = "goal"
        for bucket, default_type in (("entities", "Entity"), ("documents", "Document")):
            for node in entry.get(bucket) or []:
                if isinstance(node, dict) and node.get("id"):
                    types[str(node["id"])] = str(node.get("type") or default_type).casefold()
    for relation in context.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        for side in ("source", "target"):
            node_id = relation.get(f"{side}_id")
            node_type = relation.get(f"{side}_type")
            if node_id and node_type:
                types.setdefault(str(node_id), str(node_type).casefold())
    return types


def structural_hierarchy_only(item: dict[str, Any], context: dict[str, Any]) -> bool:
    """A hierarchy-aligned semantic relation needs non-Goal evidence and a semantic reason."""
    if item.get("kind") != "relation":
        return False
    current = str((context.get("goal") or {}).get("id") or "")
    ancestors = {str(node.get("id")) for node in context.get("ancestors") or []}
    children = {str(node.get("id")) for node in context.get("children") or []}
    source, target = str(item.get("source") or ""), str(item.get("target") or "")
    aligned = (source == current and target in ancestors) or (
        source in children and target == current
    )
    if not aligned:
        return False
    types = _context_node_types(context)
    evidence = [str(value) for value in item.get("evidence_node_ids") or []]
    independent = any(types.get(node_id) not in {None, "goal"} for node_id in evidence)
    reason = str(item.get("reason") or "").strip()
    structural_reason_only = bool(_STRUCTURAL_REASON.fullmatch(reason.strip("。,. ")))
    return not independent or structural_reason_only


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
    seen_purposes: list[str] = []
    for item in items:
        kind = item.get("kind")
        if kind == "gap":
            kept.append(item)
            continue
        reason = str(item.get("reason") or "").strip()
        evidence = [
            node_id for node_id in item.get("evidence_node_ids") or [] if str(node_id).strip()
        ]
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
        if kind == "purpose":
            matching = next(
                (
                    other
                    for other in foreign
                    if other.get("kind") == "purpose"
                    and same_purpose(str(item.get("name") or ""), str(other.get("name") or ""))
                ),
                None,
            )
            if matching:
                conflicts.append(
                    {
                        "type": "similar_open_proposal",
                        "proposal_id": matching.get("proposal_id"),
                        "item_id": matching.get("id"),
                        "name": matching.get("name") or "",
                    }
                )
                continue
            if any(same_purpose(str(item.get("name") or ""), name) for name in seen_purposes):
                continue
            seen_purposes.append(str(item.get("name") or ""))
        if kind == "relation" and float(confidence) < threshold:
            weak.append({**item, "weak_reason": "low_confidence"})
            continue
        if kind == "relation":
            if structural_hierarchy_only(item, context or {}):
                weak.append({**item, "weak_reason": "structural_hierarchy_only"})
                continue
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
    return kept, weak, conflicts, warnings
