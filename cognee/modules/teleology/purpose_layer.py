"""Fact layer stays the company tree. Teleology arrives only after review.

``get_purpose_context`` reads one goal's neighbourhood.
``propose_teleology`` stores a candidate. It does not write the graph.
``commit_teleology_proposal`` writes the accepted items as ``ai_inferred``
nodes and edges, never as ``has_subgoal`` children of the company tree.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cognee.base_config import get_base_config
from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.goal_workspace import goal_detail, goal_path, goal_relations
from cognee.modules.teleology.graph_annotations import _authorized_dataset
from cognee.modules.teleology.models import Constraint, Goal, Purpose
from cognee.modules.teleology.purpose_relations import is_structural_advance
from cognee.modules.users.models import User

_RELATIONS = frozenset({"serves", "advances", "blocks"})
_NODE_KINDS = {"purpose": Purpose, "goal": Goal, "constraint": Constraint}
_DOC_TYPES = frozenset({"DocumentChunk", "TextDocument", "Document"})


def _store_path(dataset_id: UUID) -> Path:
    root = Path(get_base_config().system_root_directory) / "teleology_proposals"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{dataset_id}.json"


def _load(dataset_id: UUID) -> dict[str, Any]:
    path = _store_path(dataset_id)
    if not path.is_file():
        return {"proposals": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"proposals": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("proposals"), dict):
        return {"proposals": {}}
    return payload


def _save(dataset_id: UUID, payload: dict[str, Any]) -> None:
    path = _store_path(dataset_id)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _analysis_text(proposal: dict[str, Any]) -> str:
    text = proposal.get("analysis_summary")
    if isinstance(text, str) and text.strip():
        return text.strip()
    summary = proposal.get("summary")
    return summary.strip() if isinstance(summary, str) else ""


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "purposes": 0,
        "goals": 0,
        "constraints": 0,
        "serves": 0,
        "advances": 0,
        "blocks": 0,
        "missing_purpose": 0,
    }
    for item in items:
        kind = item.get("kind")
        if kind == "purpose":
            counts["purposes"] += 1
        elif kind == "goal":
            counts["goals"] += 1
        elif kind == "constraint":
            counts["constraints"] += 1
        elif kind == "gap":
            counts["missing_purpose"] += 1
        elif kind == "relation":
            relation = str(item.get("relationship") or "")
            if relation in counts:
                counts[relation] += 1
    return counts


def _endpoint(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(raw.get(key) or "").strip()
        if text:
            return text
    return ""


def _clean_item(raw: dict[str, Any], *, source_goal_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("Each proposal item must be an object")
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in {"purpose", "goal", "constraint", "relation", "gap"}:
        raise ValueError(f"Unsupported proposal item kind {kind!r}")
    relationship = str(raw.get("relationship") or "").strip().lower() or None
    source = _endpoint(raw, "source", "source_id", "source_ref")
    target = _endpoint(raw, "target", "target_id", "target_ref")
    if kind == "relation":
        if relationship not in _RELATIONS:
            raise ValueError("Relations must be serves, advances, or blocks")
        if not source or not target:
            raise ValueError("A relation needs source and target")
    name = str(raw.get("name") or "").strip()
    if kind in _NODE_KINDS and not name:
        raise ValueError(f"A {kind} needs a name")
    confidence = raw.get("confidence")
    if confidence is not None:
        confidence = float(confidence)
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
    source_goal_ids = [str(item) for item in raw.get("source_goal_ids") or [] if str(item).strip()]
    if source_goal_id not in source_goal_ids:
        source_goal_ids.insert(0, source_goal_id)
    return {
        "id": str(raw.get("id") or uuid4()),
        "kind": kind,
        "name": name,
        "description": str(raw.get("description") or "").strip(),
        "confidence": confidence,
        "reason": str(raw.get("reason") or "").strip(),
        "evidence_node_ids": [
            str(item) for item in raw.get("evidence_node_ids") or [] if str(item).strip()
        ],
        "evidence": [entry for entry in raw.get("evidence") or [] if isinstance(entry, dict)],
        "source_goal_ids": source_goal_ids,
        "relationship": relationship,
        "source": source or None,
        "target": target or None,
        "status": "proposed",
        "review_status": "proposed",
    }


def _clip(value: Any, limit: int = 280) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _linked(items: list[dict[str, Any]], node_type: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        for prefix in ("source", "target"):
            if str(item.get(f"{prefix}_type") or "") != node_type:
                continue
            node_id = str(item.get(f"{prefix}_id") or "")
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            found.append(
                {
                    "id": node_id,
                    "name": item.get(f"{prefix}_name") or node_id,
                    "type": node_type,
                    "description": "",
                }
            )
    return found


_KNOWLEDGE_TYPES = [
    "Entity",
    "Document",
    "DocumentChunk",
    "TextDocument",
    "Project",
    "Metric",
    "KPI",
    "Risk",
]
_CHILD_EVIDENCE_PER_GOAL = 3
_CHILD_EVIDENCE_TOTAL = 30


class ProposalStaleError(Exception):
    """The goal context changed after this proposal was created."""

    code = "proposal_stale"


class ProposalCommitIncomplete(Exception):
    """Some accepted items were written. A retry must continue the rest."""

    code = "commit_incomplete"


def _norm_name(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if not ch.isspace())


def _dedupe_evidence(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate ids and collapse the same name+type in the model view only."""
    kept: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        node_id = str(entry.get("id") or "")
        if not node_id or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        key = (_norm_name(str(entry.get("name") or "")), str(entry.get("type") or ""))
        if key[0] and key in seen_names:
            merged = seen_names[key].setdefault("merged_ids", [])
            merged.append(node_id)
            continue
        if key[0]:
            seen_names[key] = entry
        kept.append(entry)
    return kept


def _knowledge_entry(row: tuple[Any, ...]) -> dict[str, Any] | None:
    if not row or len(row) < 3:
        return None
    props: dict[str, Any] = {}
    raw_props = row[3] if len(row) > 3 else None
    if isinstance(raw_props, str) and raw_props.strip():
        try:
            parsed = json.loads(raw_props)
            props = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            props = {}
    elif isinstance(raw_props, dict):
        props = raw_props
    return {
        "id": str(row[0]),
        "name": str(row[1] or row[0]),
        "type": str(row[2] or ""),
        "summary": _clip(props.get("description") or props.get("text") or props.get("summary")),
    }


async def _knowledge_rows(graph: Any, node_id: str, *, limit: int) -> tuple[list[Any], int]:
    params = {"id": node_id, "types": _KNOWLEDGE_TYPES, "limit": limit}
    count_query = """MATCH (n:Node)-[r:EDGE]-(m:Node)
        WHERE n.id = $id AND m.type IN $types
        RETURN count(m)"""
    bounded = int(limit)
    fetch_query = f"""MATCH (n:Node)-[r:EDGE]-(m:Node)
        WHERE n.id = $id AND m.type IN $types
        RETURN m.id, m.name, m.type, m.properties
        LIMIT {bounded}"""
    directed_count = """MATCH (n:Node)-[r:EDGE]->(m:Node)
        WHERE n.id = $id AND m.type IN $types
        RETURN count(m)"""
    directed_fetch = f"""MATCH (n:Node)-[r:EDGE]->(m:Node)
        WHERE n.id = $id AND m.type IN $types
        RETURN m.id, m.name, m.type, m.properties
        LIMIT {bounded}"""
    try:
        counts = await graph.query(count_query, params)
        rows = await graph.query(fetch_query, params)
    except Exception:  # noqa: BLE001 - undirected match is not supported by every graph adapter
        counts = await graph.query(directed_count, params)
        rows = await graph.query(directed_fetch, params)
    total = int(counts[0][0]) if counts and counts[0] else len(rows or [])
    return list(rows or []), total


def _split_knowledge(rows: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    for row in rows:
        entry = _knowledge_entry(tuple(row) if not isinstance(row, tuple) else row)
        if entry is None:
            continue
        if entry["type"] in _DOC_TYPES or entry["type"] == "Document":
            documents.append(entry)
        else:
            entities.append(entry)
    return _dedupe_evidence(entities), _dedupe_evidence(documents)


async def get_purpose_context(dataset_id: UUID, user: User, goal_id: str) -> dict[str, Any]:
    """Local context for one goal. Never the whole company tree."""
    goal_id = str(goal_id).strip()
    detail = await goal_detail(dataset_id, user, goal_id)
    path = await goal_path(dataset_id, user, goal_id)
    relations = await goal_relations(dataset_id, user, goal_id, limit=40)
    dataset = await _authorized_dataset(dataset_id, user, "read")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        child_count_rows = await graph.query(
            """MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id = $id AND r.relationship_name = 'has_subgoal'
            RETURN count(c)""",
            {"id": goal_id},
        )
        children_rows = await graph.query(
            """MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id = $id AND r.relationship_name = 'has_subgoal'
            RETURN c.id, c.name, c.type, c.properties
            ORDER BY c.name, c.id
            LIMIT 40""",
            {"id": goal_id},
        )
        missing_rows = await graph.query(
            """MATCH (p:Node)-[h:EDGE]->(c:Node)
            WHERE p.id = $id AND h.relationship_name = 'has_subgoal'
            OPTIONAL MATCH (c)-[r:EDGE]->(t:Node)
            WHERE r.relationship_name IN ['serves', 'advances']
              AND t.type = 'Purpose'
              AND (r.properties IS NULL OR NOT r.properties CONTAINS 'system_derived')
            WITH c, count(t) AS purposes
            WHERE purposes = 0
            RETURN c.id, c.name
            LIMIT 40""",
            {"id": goal_id},
        )
        child_ids = [str(row[0]) for row in children_rows or [] if row]
        child_evidence_rows: list[Any] = []
        if child_ids:
            try:
                child_evidence_rows = await graph.query(
                    """MATCH (n:Node)-[r:EDGE]-(m:Node)
                    WHERE n.id IN $ids AND m.type IN $types
                    RETURN n.id, m.id, m.name, m.type, m.properties
                    LIMIT $limit""",
                    {
                        "ids": child_ids,
                        "types": _KNOWLEDGE_TYPES,
                        "limit": _CHILD_EVIDENCE_TOTAL,
                    },
                )
            except Exception:  # noqa: BLE001 - undirected match is not supported by every graph adapter
                child_evidence_rows = await graph.query(
                    """MATCH (n:Node)-[r:EDGE]->(m:Node)
                    WHERE n.id IN $ids AND m.type IN $types
                    RETURN n.id, m.id, m.name, m.type, m.properties
                    LIMIT $limit""",
                    {
                        "ids": child_ids,
                        "types": _KNOWLEDGE_TYPES,
                        "limit": _CHILD_EVIDENCE_TOTAL,
                    },
                )
        neighbor_rows, knowledge_total = await _knowledge_rows(graph, goal_id, limit=20)
    goal = detail["goal"]
    children = [
        {
            "id": str(row[0]),
            "name": str(row[1] or row[0]),
            "type": str(row[2] or "Goal"),
            "description": "",
        }
        for row in children_rows or []
        if row
    ]
    relation_items = relations.get("items") or []
    purposes = _linked(relation_items, "Purpose")
    entities, documents = _split_knowledge(neighbor_rows)
    child_buckets: dict[str, dict[str, Any]] = {
        child["id"]: {
            "goal_id": child["id"],
            "goal_name": child["name"],
            "entities": [],
            "documents": [],
        }
        for child in children
    }
    for row in child_evidence_rows or []:
        if not row or len(row) < 4:
            continue
        owner = str(row[0])
        bucket = child_buckets.get(owner)
        if bucket is None:
            continue
        entry = _knowledge_entry((row[1], row[2], row[3], row[4] if len(row) > 4 else None))
        if entry is None:
            continue
        slot = "documents" if entry["type"] in _DOC_TYPES or entry["type"] == "Document" else "entities"
        if len(bucket["entities"]) + len(bucket["documents"]) >= _CHILD_EVIDENCE_PER_GOAL:
            continue
        bucket[slot].append(entry)
    child_evidence = []
    for child in children:
        bucket = child_buckets[child["id"]]
        bucket["entities"] = _dedupe_evidence(bucket["entities"])
        bucket["documents"] = _dedupe_evidence(bucket["documents"])
        if bucket["entities"] or bucket["documents"]:
            child_evidence.append(bucket)
    ancestors = path.get("path") or []
    if ancestors and str(ancestors[-1].get("id")) == goal_id:
        ancestors = ancestors[:-1]
    children_total = int(child_count_rows[0][0]) if child_count_rows else len(children)
    result = {
        "dataset_id": str(dataset_id),
        "goal": goal,
        "ancestors": ancestors,
        "children": children,
        "children_total": children_total,
        "children_returned": len(children),
        "children_truncated": children_total > len(children),
        "note": _clip(goal.get("description"), 500),
        "purposes": purposes,
        "constraints": _linked(relation_items, "Constraint"),
        "relations": relation_items,
        "entities": entities,
        "documents": documents,
        "entities_total": knowledge_total,
        "documents_total": knowledge_total,
        "entities_truncated": knowledge_total > len(entities),
        "documents_truncated": knowledge_total > len(documents),
        "child_evidence": child_evidence,
        "children_missing_purpose": [
            {"id": str(row[0]), "name": str(row[1] or row[0])} for row in missing_rows or [] if row
        ],
        "source": goal.get("source") or ("company_tree" if goal.get("cpd_kind") else None),
        "revision": str(goal.get("created_at") or ""),
        "missing_purpose": not purposes,
    }
    from cognee.modules.teleology.context_hash import context_hash

    result["context_hash"] = context_hash(result)
    return result


async def _without_structural_copies(
    dataset_id: UUID,
    user: User,
    items: list[dict[str, Any]],
    *,
    generated_by: str,
) -> list[dict[str, Any]]:
    """Do not store an advances candidate that only repeats a has_subgoal edge."""
    advances = [
        item
        for item in items
        if item.get("kind") == "relation" and item.get("relationship") == "advances"
    ]
    if not advances:
        return items
    node_ids = [
        node_id
        for item in advances
        for node_id in (item.get("source"), item.get("target"))
        if node_id
    ]
    dataset = await _authorized_dataset(dataset_id, user, "read")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        rows = await graph.query(
            """MATCH (p:Node)-[h:EDGE]->(c:Node)
            WHERE h.relationship_name = 'has_subgoal'
              AND p.id IN $ids AND c.id IN $ids
            RETURN p.id, c.id""",
            {"ids": node_ids},
        )
    tree_pairs = {(str(row[0]), str(row[1])) for row in rows or [] if row and len(row) >= 2}
    if not tree_pairs:
        return items
    assumed_origin = "ai_inferred" if generated_by in {"purpose-agent", "workbuddy"} else ""
    kept: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") == "relation" and is_structural_advance(
            str(item.get("relationship") or ""),
            str(item.get("source") or ""),
            str(item.get("target") or ""),
            {
                "origin": assumed_origin,
                "reason": item.get("reason"),
                "evidence_node_ids": item.get("evidence_node_ids"),
            },
            tree_pairs,
        ):
            continue
        kept.append(item)
    return kept


async def propose_teleology(
    dataset_id: UUID,
    user: User,
    *,
    source_goal_id: str,
    proposal: dict[str, Any],
    generated_by: str = "purpose-agent",
) -> dict[str, Any]:
    """Store a candidate layer. The company tree and formal graph stay unchanged."""
    source_goal_id = str(source_goal_id).strip()
    if not source_goal_id:
        raise ValueError("source_goal_id is required")
    await goal_detail(dataset_id, user, source_goal_id)
    if not isinstance(proposal, dict):
        raise TypeError("proposal must be an object")
    raw_items: list[dict[str, Any]] = []
    for kind, key in (
        ("purpose", "purposes"),
        ("goal", "goals"),
        ("constraint", "constraints"),
        ("relation", "relations"),
    ):
        for entry in proposal.get(key) or []:
            if isinstance(entry, dict):
                raw_items.append({**entry, "kind": kind})
    for entry in proposal.get("items") or []:
        if isinstance(entry, dict):
            raw_items.append(entry)
    items = [_clean_item(entry, source_goal_id=source_goal_id) for entry in raw_items]
    items = await _without_structural_copies(dataset_id, user, items, generated_by=generated_by)
    context = await get_purpose_context(dataset_id, user, source_goal_id)
    from cognee.modules.teleology.proposal_rules import partition_ai_items
    from cognee.modules.teleology.proposal_store import open_items, save_proposal

    incoming_weak = [
        entry for entry in proposal.get("weak_signals") or [] if isinstance(entry, dict)
    ]
    incoming_conflicts = [
        entry for entry in proposal.get("open_conflicts") or [] if isinstance(entry, dict)
    ]
    items, weak_signals, open_conflicts, warnings = partition_ai_items(
        items,
        generated_by=generated_by,
        context=context,
        open_items=await open_items(dataset_id),
    )
    for item in items:
        if item["kind"] == "goal":
            item["review_status"] = "proposed"
            item["status"] = "proposed"
    stored = {
        "id": str(uuid4()),
        "dataset_id": str(dataset_id),
        "source_goal_id": source_goal_id,
        "status": "open",
        "run_id": str(proposal.get("run_id") or uuid4()),
        "created_at": int(time.time() * 1000),
        "generated_by": generated_by,
        "source_revision": str(proposal.get("source_revision") or context.get("revision") or ""),
        "context_hash": context.get("context_hash") or "",
        "analysis_summary": _analysis_text(proposal),
        "items": items,
        "weak_signals": incoming_weak + weak_signals,
        "open_conflicts": incoming_conflicts + open_conflicts,
        "validation_warnings": warnings,
        "summary": _summary(items),
    }
    await save_proposal(dataset_id, stored, user=user)
    return stored


async def start_purpose_review(dataset_id: UUID, user: User, goal_id: str) -> dict[str, Any]:
    """Open a review from the local context. Does not invent a purpose statement."""
    context = await get_purpose_context(dataset_id, user, goal_id)
    items: list[dict[str, Any]] = []
    if context["missing_purpose"]:
        items.append(
            {
                "kind": "gap",
                "name": context["goal"].get("name") or goal_id,
                "reason": "当前目标还没有确认过的目的。",
                "source_goal_ids": [goal_id],
            }
        )
    for child in context["children_missing_purpose"]:
        items.append(
            {
                "kind": "gap",
                "name": child["name"],
                "reason": "这个直接下级还没有指向一个已确认的目的。",
                "source_goal_ids": [child["id"], goal_id],
            }
        )
    return await propose_teleology(
        dataset_id,
        user,
        source_goal_id=goal_id,
        proposal={"items": items, "source_revision": context.get("revision") or ""},
        generated_by="purpose-context",
    )


def _apply_edits(item: dict[str, Any], edits: dict[str, Any] | None) -> dict[str, Any]:
    if not edits:
        return item
    change = edits.get(item["id"])
    if not isinstance(change, dict):
        return item
    updated = dict(item)
    for key in ("name", "description", "reason", "source", "target"):
        if change.get(key) is not None:
            updated[key] = str(change[key]).strip()
    return updated


def _stable_node_id(dataset_id: UUID, proposal_id: str, item_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"cognee:teleology:{dataset_id}:{proposal_id}:{item_id}"))


def _edge_key(proposal_id: str, item_id: str, source: str, relationship: str, target: str) -> str:
    return f"{proposal_id}:{item_id}:{source}:{relationship}:{target}"


async def _edge_exists(graph: Any, source_id: str, target_id: str, relationship: str) -> bool:
    checker = getattr(graph, "has_edge", None)
    if checker is not None:
        found = checker(source_id, target_id, relationship)
        if hasattr(found, "__await__"):
            found = await found
        return bool(found)
    rows = await graph.query(
        """MATCH (a:Node)-[r:EDGE]->(b:Node)
        WHERE a.id = $source AND b.id = $target AND r.relationship_name = $relation
        RETURN r.relationship_name LIMIT 1""",
        {"source": source_id, "target": target_id, "relation": relationship},
    )
    return bool(rows)


def _known_refs(
    prepared: list[tuple[dict[str, Any], dict[str, Any]]], id_by_ref: dict[str, str]
) -> set[str]:
    known = {key for key in id_by_ref if key}
    for raw, item in prepared:
        known.add(str(raw.get("id") or ""))
        known.add(str(item.get("id") or ""))
        for label in (raw.get("name"), item.get("name"), item.get("source"), item.get("target")):
            if label:
                known.add(str(label))
    return known


def _validate_commit_item(
    item: dict[str, Any],
    *,
    generated_by: str,
    visible: set[str],
    known: set[str],
    tree_pairs: set[tuple[str, str]],
    formal: set[tuple[str, str, str]],
    id_by_ref: dict[str, str],
) -> None:
    if item["kind"] == "relation":
        relation = str(item.get("relationship") or "")
        if relation not in _RELATIONS:
            raise ValueError("Relations must be serves, advances, or blocks")
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if not source or not target or source == target:
            raise ValueError("A relation cannot point at itself")
        if source not in known and source not in visible:
            raise ValueError(f"Relation source {source} is not in the formal graph or this proposal")
        if target not in known and target not in visible:
            raise ValueError(f"Relation target {target} is not in the formal graph or this proposal")
        evidence = [str(node_id) for node_id in item.get("evidence_node_ids") or []]
        if generated_by in {"purpose-agent", "workbuddy"}:
            if not str(item.get("reason") or "").strip() or not evidence:
                raise ValueError("AI relations need a reason and at least one evidence id")
            if any(node_id not in visible for node_id in evidence):
                raise ValueError("AI relation evidence must come from the current context")
        resolved_source = id_by_ref.get(source, source)
        resolved_target = id_by_ref.get(target, target)
        if (resolved_source, relation, resolved_target) in formal or (source, relation, target) in formal:
            raise ValueError("This relation already exists")
        endpoints = {source, target, resolved_source, resolved_target}
        parent_child = (resolved_target, resolved_source) in tree_pairs or (target, source) in tree_pairs
        if relation == "advances" and parent_child and not any(
            node_id not in endpoints for node_id in evidence
        ):
            raise ValueError("A parent-child advances edge needs evidence beyond its endpoints")
        return
    if generated_by in {"purpose-agent", "workbuddy"}:
        evidence = [str(node_id) for node_id in item.get("evidence_node_ids") or []]
        if not str(item.get("reason") or "").strip() or item.get("confidence") is None or not evidence:
            raise ValueError("AI candidates need a reason, confidence, and evidence")
        if any(node_id not in visible for node_id in evidence):
            raise ValueError("AI evidence must come from the current context")


async def commit_teleology_proposal(
    dataset_id: UUID,
    user: User,
    proposal_id: str,
    accepted_item_ids: list[str],
    *,
    edits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write accepted purpose nodes and edges. Leave the company tree untouched."""
    from cognee.modules.teleology.proposal_rules import visible_context_ids
    from cognee.modules.teleology.proposal_store import load_proposal, save_proposal

    proposal = await load_proposal(dataset_id, proposal_id)
    if not proposal:
        raise KeyError(f"Proposal {proposal_id} was not found")
    if proposal.get("status") == "committed" and proposal.get("commit_result"):
        return proposal["commit_result"]
    context = await get_purpose_context(dataset_id, user, proposal["source_goal_id"])
    if proposal.get("context_hash") != context.get("context_hash"):
        raise ProposalStaleError("proposal_stale")
    accepted = {str(item) for item in accepted_item_ids}
    dataset = await _authorized_dataset(dataset_id, user, "write")
    created_nodes: list[dict[str, str]] = []
    created_edges: list[dict[str, str]] = []
    skipped: list[str] = []
    id_by_ref: dict[str, str] = {proposal["source_goal_id"]: proposal["source_goal_id"]}
    for node in [*(context.get("purposes") or []), *(context.get("constraints") or [])]:
        if node.get("id"):
            id_by_ref[str(node["id"])] = str(node["id"])
    goal = context.get("goal") or {}
    if goal.get("id"):
        id_by_ref[str(goal["id"])] = str(goal["id"])
        if goal.get("name"):
            id_by_ref[str(goal["name"])] = str(goal["id"])
    for child in context.get("children") or []:
        id_by_ref[str(child.get("id"))] = str(child.get("id"))
        if child.get("name"):
            id_by_ref[str(child["name"])] = str(child["id"])
    visible = visible_context_ids(context)
    formal = {
        (str(item.get("source_id")), str(item.get("relationship")), str(item.get("target_id")))
        for item in context.get("relations") or []
    }
    prepared: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for raw in proposal["items"]:
        if raw["id"] not in accepted or raw["kind"] == "gap" or raw.get("weak_reason"):
            raw["review_status"] = "ignored"
            raw["status"] = "ignored"
            skipped.append(raw["id"])
            continue
        prepared.append((raw, _apply_edits(raw, edits)))
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        endpoint_ids = [
            str(item.get(key) or "")
            for _, item in prepared
            if item["kind"] == "relation"
            for key in ("source", "target")
        ]
        tree_rows = (
            await graph.query(
                """MATCH (p:Node)-[r:EDGE]->(c:Node)
                WHERE r.relationship_name = 'has_subgoal' AND p.id IN $ids AND c.id IN $ids
                RETURN p.id, c.id""",
                {"ids": [node_id for node_id in endpoint_ids if node_id]},
            )
            if endpoint_ids
            else []
        )
        tree_pairs = {(str(row[0]), str(row[1])) for row in tree_rows or [] if row}
        for raw, item in prepared:
            if item["kind"] not in _NODE_KINDS:
                continue
            node_id = raw.get("committed_node_id") or _stable_node_id(
                dataset_id, proposal["id"], item["id"]
            )
            id_by_ref[item["id"]] = node_id
            id_by_ref[raw["id"]] = node_id
            for label in (raw.get("name"), item.get("name")):
                if label:
                    id_by_ref[str(label)] = node_id
        known = _known_refs(prepared, id_by_ref)
        for _, item in prepared:
            _validate_commit_item(
                item,
                generated_by=str(proposal.get("generated_by") or ""),
                visible=visible,
                known=known,
                tree_pairs=tree_pairs,
                formal=formal,
                id_by_ref=id_by_ref,
            )
        try:
            for raw, item in prepared:
                if item["kind"] not in _NODE_KINDS:
                    continue
                node_id = id_by_ref[item["id"]]
                existing = await graph.get_node(node_id) if hasattr(graph, "get_node") else None
                if existing is None:
                    model = _NODE_KINDS[item["kind"]]
                    node = model(
                        id=UUID(node_id),
                        name=item["name"],
                        description=item["description"],
                        status="active",
                        source="ai_inferred",
                        source_goal_id=proposal["source_goal_id"],
                        source_goal_ids=item["source_goal_ids"],
                        source_revision=proposal.get("source_revision") or None,
                        generated_by=proposal.get("generated_by") or "purpose-agent",
                        confidence=item.get("confidence"),
                        reason=item["reason"],
                        evidence_node_ids=list(item.get("evidence_node_ids") or []),
                        proposal_id=proposal["id"],
                        run_id=proposal.get("run_id"),
                        review_status="accepted",
                    )
                    await graph.add_nodes([node])
                raw["status"] = "accepted"
                raw["review_status"] = "accepted"
                raw["committed_node_id"] = node_id
                created_nodes.append({"id": node_id, "kind": item["kind"], "name": item["name"]})
            for raw, item in prepared:
                if item["kind"] != "relation":
                    continue
                relation = str(item["relationship"])
                source_id = id_by_ref.get(str(item.get("source") or ""))
                target_id = id_by_ref.get(str(item.get("target") or ""))
                if not source_id or not target_id or source_id == target_id:
                    raise ValueError("Relation endpoints must resolve to different graph nodes")
                edge_key = raw.get("committed_edge_key") or _edge_key(
                    proposal["id"], item["id"], source_id, relation, target_id
                )
                if not await _edge_exists(graph, source_id, target_id, relation):
                    await graph.add_edges(
                        [
                            (
                                source_id,
                                target_id,
                                relation,
                                {
                                    "edge_text": relation,
                                    "relationship_name": relation,
                                    "origin": "ai_inferred",
                                    "generated_by": proposal.get("generated_by") or "purpose-agent",
                                    "proposal_id": proposal["id"],
                                    "proposal_item_id": item["id"],
                                    "edge_key": edge_key,
                                    "run_id": proposal.get("run_id") or "",
                                    "source_goal_id": proposal["source_goal_id"],
                                    "reason": item["reason"],
                                    "confidence": item.get("confidence"),
                                    "evidence_node_ids": list(item.get("evidence_node_ids") or []),
                                },
                            )
                        ]
                    )
                raw["review_status"] = "accepted"
                raw["status"] = "accepted"
                raw["committed_edge_key"] = edge_key
                created_edges.append(
                    {"source_id": source_id, "target_id": target_id, "relationship": relation}
                )
        except Exception as exc:
            done = sum(
                1
                for raw, _item in prepared
                if raw.get("committed_node_id") or raw.get("committed_edge_key")
            )
            proposal["status"] = "open"
            proposal["commit_progress"] = {"done": done, "total": len(prepared)}
            await save_proposal(dataset_id, proposal, user=user)
            raise ProposalCommitIncomplete(
                f"已提交 {done}/{len(prepared)}，请再次确认以继续剩余项。"
            ) from exc
    result = {
        "proposal_id": proposal_id,
        "dataset_id": str(dataset_id),
        "committed_nodes": created_nodes,
        "committed_edges": created_edges,
        "skipped_item_ids": skipped,
    }
    proposal["status"] = "committed"
    proposal["summary"] = _summary(proposal["items"])
    proposal["commit_result"] = result
    await save_proposal(dataset_id, proposal, user=user)
    return result
