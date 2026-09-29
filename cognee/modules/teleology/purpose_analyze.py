"""One-goal purpose analysis. The model sees only get_purpose_context."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from cognee.infrastructure.llm.LLMGateway import LLMGateway
from cognee.modules.teleology.proposal_rules import (
    constraint_overreach,
    min_relation_confidence,
    same_purpose,
    structural_hierarchy_only,
)
from cognee.modules.teleology.purpose_layer import get_purpose_context, propose_teleology
from cognee.modules.users.models import User

_RELATIONS = frozenset({"serves", "advances", "blocks"})
PROMPT_VERSION = "purpose-analyze-v2"

_SYSTEM = """You infer why one company goal exists. The company tree is fact. You only propose a teleology layer.

Allowed node kinds: Purpose, Constraint, Suggested Goal.
Allowed relationships: serves, advances, blocks.
Do not emit has_subgoal or any other relationship.
Company Tree hierarchy is already known fact.
Do not infer serves, advances, or blocks from hierarchy alone.
Parent/child/ancestor/path/name adjacency is NOT semantic evidence.
Do not output a relation merely because:
- A is parent of B
- B is child of A
- goals are adjacent in the path
- one goal appears to belong to another goal structurally
- their names look related
Before emitting a relation, ask: "Is there evidence beyond the company-tree hierarchy?"
If no: DO NOT emit the relation.
Do not emit it as a weak guess either.
Simply omit it.
A real relation needs evidence outside the goal chain, such as a Document, Entity, Purpose, Constraint, or MapReference id from the context.
Open/uncommitted proposals are not evidence.
Never cite, summarize, reinforce, or imitate another open proposal.
Only use the bounded goal context and its graph/document/entity evidence.
Reuse an existing purpose when the meaning matches. Do not create a near-duplicate purpose name.
evidence_node_ids must be ids present in the context. Every item needs a non-empty reason, a confidence from 0 to 1, and at least one evidence id from this context.
Do not invent an owner or a progress value. Do not rewrite the company tree.
Suggested goals stay proposals. Write names and reasons in the same language as the goal.

Purpose must answer why the goal exists, what outcome it should produce, and what value a higher goal receives if it succeeds. Purpose should describe the specific business outcome of this goal. Avoid generic templates such as "支撑 X 项目目标达成" when the context supports a more specific outcome. Do not merge purposes that name different projects. Do not repackage children, tools, dashboards, weekly reports, measurement methods, or processes as a Purpose. Those belong to HOW: direct children, suggested goals, and serves or advances edges.

A Constraint requires explicit evidence of a limit, boundary, precondition, compliance rule, resource limit, risk, dependency, prohibition, or an SLA, time, or cost bound. Do not turn “a tool, process, metric, or dashboard exists” into “this tool must be used”. If that is only a suggestion, leave it out of constraints.

If children_truncated is true, you only see some direct children. Do not treat that sample as the whole goal tree, and do not make a global claim from it.
Never claim that the business semantics are fully covered, that no other goal exists, that the company has no other risk, or that this is the complete business structure. Forbidden claims include “已经覆盖全部业务语义”, “不存在其他目标”, “该公司没有其他风险”, and “这是完整业务结构”. The strongest negative claim you may make is that the provided local context does not contain enough evidence to add a Suggested Goal. In the current local context, say “没有足够证据支持新增 Suggested Goal” instead of a global conclusion.
Relations below 0.60 confidence are weak signals, not formal candidates."""


class _Candidate(BaseModel):
    name: str
    description: str = ""
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_node_ids: list[str] = Field(default_factory=list)


class _RelationCandidate(BaseModel):
    source_ref: str
    relationship: str
    target_ref: str
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_node_ids: list[str] = Field(default_factory=list)


class PurposeAnalysis(BaseModel):
    summary: str = ""
    purposes: list[_Candidate] = Field(default_factory=list)
    constraints: list[_Candidate] = Field(default_factory=list)
    suggested_goals: list[_Candidate] = Field(default_factory=list)
    relations: list[_RelationCandidate] = Field(default_factory=list)


def _fold(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if not ch.isspace())


def _same_purpose(left: str, right: str) -> bool:
    return same_purpose(left, right)


def _index(context: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    goal = context.get("goal") or {}
    if goal.get("id"):
        nodes.append(goal)
    for key in ("ancestors", "children", "purposes", "constraints", "entities", "documents"):
        nodes.extend(context.get(key) or [])
    for entry in context.get("child_evidence") or []:
        if not isinstance(entry, dict):
            continue
        nodes.append(
            {
                "id": entry.get("goal_id"),
                "name": entry.get("goal_name"),
                "type": "Goal",
                "_evidence_scope": "child",
            }
        )
        for bucket in ("entities", "documents"):
            for node in entry.get(bucket) or []:
                if isinstance(node, dict):
                    nodes.append({**node, "_evidence_scope": "child"})
    for relation in context.get("relations") or []:
        nodes.append(
            {
                "id": relation.get("source_id"),
                "name": relation.get("source_name"),
                "type": relation.get("source_type"),
            }
        )
        nodes.append(
            {
                "id": relation.get("target_id"),
                "name": relation.get("target_name"),
                "type": relation.get("target_type"),
            }
        )
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str] = {}
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        by_id[node_id] = node
        folded = _fold(str(node.get("name") or ""))
        if folded and folded not in by_name:
            by_name[folded] = node_id
    return by_id, by_name


def _evidence(
    raw_ids: list[Any], by_id: dict[str, dict[str, Any]]
) -> tuple[list[str], list[dict[str, str]]]:
    ids: list[str] = []
    refs: list[dict[str, str]] = []
    for raw in raw_ids or []:
        node_id = str(raw or "").strip()
        if node_id not in by_id or node_id in ids:
            continue
        ids.append(node_id)
        node = by_id[node_id]
        refs.append(
            {
                "id": node_id,
                "name": str(node.get("name") or node_id),
                "type": str(node.get("type") or ""),
                "scope": str(node.get("_evidence_scope") or "goal"),
            }
        )
    return ids, refs


def _existing_keys(
    context: dict[str, Any], open_items: list[dict[str, Any]]
) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for relation in context.get("relations") or []:
        keys.add(
            (
                str(relation.get("source_id") or ""),
                str(relation.get("relationship") or ""),
                str(relation.get("target_id") or ""),
            )
        )
    names = {}
    for item in open_items:
        if item.get("kind") in {"purpose", "goal", "constraint"} and item.get("name"):
            names[_fold(item["name"])] = item.get("id")
        if item.get("kind") != "relation":
            continue
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        relation = str(item.get("relationship") or "")
        if source and target and relation:
            keys.add((source, relation, target))
            keys.add((_fold(source), relation, _fold(target)))
    return keys


def _prompt_context(context: dict[str, Any], open_items: list[dict[str, Any]]) -> dict[str, Any]:
    del open_items  # Open proposals are only used after inference for duplicate/conflict checks.

    def brief(node: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(node.get("id") or ""),
            "name": str(node.get("name") or ""),
            "type": str(node.get("type") or ""),
            "description": str(node.get("description") or node.get("summary") or "")[:180],
        }

    goal = context.get("goal") or {}
    return {
        "goal": brief(goal) | {"note": str(context.get("note") or "")[:500]},
        "ancestors": [brief(node) for node in context.get("ancestors") or []],
        "children": [brief(node) for node in context.get("children") or []],
        "purposes": [brief(node) for node in context.get("purposes") or []],
        "constraints": [brief(node) for node in context.get("constraints") or []],
        "relations": [
            {
                "source_id": relation.get("source_id"),
                "source_name": relation.get("source_name"),
                "relationship": relation.get("relationship"),
                "target_id": relation.get("target_id"),
                "target_name": relation.get("target_name"),
            }
            for relation in context.get("relations") or []
        ],
        "children_total": context.get("children_total"),
        "children_returned": context.get("children_returned"),
        "children_truncated": bool(context.get("children_truncated")),
        "entities_truncated": bool(context.get("entities_truncated")),
        "documents_truncated": bool(context.get("documents_truncated")),
        "entities": [brief(node) for node in context.get("entities") or []],
        "documents": [brief(node) for node in context.get("documents") or []],
        "child_evidence": context.get("child_evidence") or [],
    }


def normalize_analysis(
    context: dict[str, Any],
    draft: dict[str, Any] | PurposeAnalysis,
    open_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn a model draft into a proposal body. Drops anything the context cannot support."""
    payload = draft.model_dump() if isinstance(draft, PurposeAnalysis) else draft
    by_id, by_name = _index(context)
    open_items = open_items or []
    taken = _existing_keys(context, open_items)
    goal_id = str((context.get("goal") or {}).get("id") or "")
    created: dict[str, str] = {}
    purposes: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    goals: list[dict[str, Any]] = []
    weak_signals: list[dict[str, Any]] = []
    open_conflicts: list[dict[str, Any]] = []

    def reuse_purpose(name: str) -> tuple[str | None, bool]:
        for item in open_items:
            if item.get("kind") == "purpose" and _same_purpose(name, str(item.get("name") or "")):
                open_conflicts.append(
                    {
                        "type": "similar_open_proposal",
                        "proposal_id": item.get("proposal_id"),
                        "item_id": item.get("id"),
                        "name": item.get("name") or name,
                    }
                )
                return None, True
        for node in context.get("purposes") or []:
            if _same_purpose(name, str(node.get("name") or "")):
                return str(node.get("id")), False
        for item in purposes:
            if _same_purpose(name, item["name"]):
                return item["id"], False
        return None, False

    def add_node(bucket: list[dict[str, Any]], kind: str, raw: dict[str, Any]) -> None:
        name = str(raw.get("name") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if not name or not reason:
            return
        if kind == "purpose":
            existing, blocked = reuse_purpose(name)
            if blocked:
                return
            if existing:
                created[_fold(name)] = existing
                created[name] = existing
                return
        evidence_ids, evidence = _evidence(raw.get("evidence_node_ids") or [], by_id)
        if not evidence_ids:
            return
        item_id = str(uuid4())
        item = {
            "id": item_id,
            "kind": kind,
            "name": name,
            "description": str(raw.get("description") or "").strip(),
            "reason": reason,
            "confidence": _confidence(raw.get("confidence")),
            "evidence_node_ids": evidence_ids,
            "evidence": evidence,
            "source_goal_ids": [goal_id] if goal_id else [],
        }
        if kind == "constraint" and constraint_overreach(item):
            weak_signals.append({**item, "weak_reason": "constraint_overreach"})
            return
        bucket.append(item)
        created[item_id] = item_id
        created[name] = item_id
        created[_fold(name)] = item_id

    for raw in payload.get("purposes") or []:
        if isinstance(raw, dict):
            add_node(purposes, "purpose", raw)
    for raw in payload.get("constraints") or []:
        if isinstance(raw, dict):
            add_node(constraints, "constraint", raw)
    for raw in payload.get("suggested_goals") or []:
        if isinstance(raw, dict):
            add_node(goals, "goal", raw)

    def resolve(ref: str) -> str | None:
        text = str(ref or "").strip()
        if not text:
            return None
        if text in by_id or text in created:
            return created.get(text, text)
        folded = _fold(text)
        return created.get(folded) or by_name.get(folded)

    relations: list[dict[str, Any]] = []
    for raw in payload.get("relations") or []:
        if not isinstance(raw, dict):
            continue
        relationship = str(raw.get("relationship") or "").strip().lower()
        if relationship not in _RELATIONS:
            continue
        reason = str(raw.get("reason") or "").strip()
        if not reason:
            continue
        source_id = resolve(
            str(raw.get("source") or raw.get("source_id") or raw.get("source_ref") or "")
        )
        target_id = resolve(
            str(raw.get("target") or raw.get("target_id") or raw.get("target_ref") or "")
        )
        if not source_id or not target_id or source_id == target_id:
            continue
        evidence_ids, evidence = _evidence(raw.get("evidence_node_ids") or [], by_id)
        if not evidence_ids:
            continue
        confidence = _confidence(raw.get("confidence"))
        candidate = {
            "kind": "relation",
            "source": source_id,
            "target": target_id,
            "relationship": relationship,
            "reason": reason,
            "evidence_node_ids": evidence_ids,
        }
        if structural_hierarchy_only(candidate, context):
            weak_signals.append(
                {
                    **candidate,
                    "confidence": confidence,
                    "weak_reason": "structural_hierarchy_only",
                }
            )
            continue
        if confidence < min_relation_confidence():
            weak_signals.append(
                {
                    "kind": "relation",
                    "source": source_id,
                    "target": target_id,
                    "relationship": relationship,
                    "reason": reason,
                    "confidence": confidence,
                    "evidence_node_ids": evidence_ids,
                    "weak_reason": "low_confidence",
                }
            )
            continue
        foreign_ids = {
            str(item.get("id") or "")
            for item in open_items
            if item.get("proposal_id") and str(item.get("id") or "") not in created
        }
        if source_id in foreign_ids or target_id in foreign_ids:
            blocked = source_id if source_id in foreign_ids else target_id
            other = next(item for item in open_items if str(item.get("id")) == blocked)
            open_conflicts.append(
                {
                    "type": "similar_open_proposal",
                    "proposal_id": other.get("proposal_id"),
                    "item_id": blocked,
                    "name": other.get("name") or "",
                }
            )
            continue
        key = (source_id, relationship, target_id)
        folded_key = (_fold(source_id), relationship, _fold(target_id))
        if key in taken or folded_key in taken:
            continue
        taken.add(key)
        relations.append(
            {
                "kind": "relation",
                "source": source_id,
                "target": target_id,
                "relationship": relationship,
                "reason": reason,
                "confidence": confidence,
                "evidence_node_ids": evidence_ids,
                "evidence": evidence,
                "source_goal_ids": [goal_id] if goal_id else [],
                "name": f"{source_id} {relationship} {target_id}",
            }
        )
    return {
        "analysis_summary": str(payload.get("summary") or "").strip(),
        "source_revision": str(context.get("revision") or ""),
        "purposes": purposes,
        "constraints": constraints,
        "goals": goals,
        "relations": relations,
        "weak_signals": weak_signals,
        "open_conflicts": open_conflicts,
    }


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, number))


async def _complete(context: dict[str, Any], open_items: list[dict[str, Any]]) -> dict[str, Any]:
    text = json.dumps(_prompt_context(context, open_items), ensure_ascii=False)
    result = await LLMGateway.acreate_structured_output(text, _SYSTEM, PurposeAnalysis)
    return result.model_dump()


async def analyze_goal(
    dataset_id: UUID, user: User, goal_id: str, *, run_id: str | None = None
) -> dict[str, Any]:
    """Read one goal, ask the configured model, and store a proposal. The graph stays unchanged."""
    from cognee.modules.teleology.proposal_store import open_items as load_open_items

    context = await get_purpose_context(dataset_id, user, goal_id)
    open_items = await load_open_items(dataset_id)
    draft = await _complete(context, open_items)
    proposal = normalize_analysis(context, draft, open_items)
    return await propose_teleology(
        dataset_id,
        user,
        source_goal_id=goal_id,
        proposal=proposal,
        generated_by="purpose-agent",
        **({"run_id": run_id} if run_id is not None else {}),
    )
