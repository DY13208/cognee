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
from uuid import UUID, uuid4

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


def _clean_item(raw: dict[str, Any], *, source_goal_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("Each proposal item must be an object")
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in {"purpose", "goal", "constraint", "relation", "gap"}:
        raise ValueError(f"Unsupported proposal item kind {kind!r}")
    relationship = str(raw.get("relationship") or "").strip().lower() or None
    if kind == "relation":
        if relationship not in _RELATIONS:
            raise ValueError("Relations must be serves, advances, or blocks")
        if not str(raw.get("source") or "").strip() or not str(raw.get("target") or "").strip():
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
        "source": str(raw.get("source") or "").strip() or None,
        "target": str(raw.get("target") or "").strip() or None,
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
        neighbor_rows = await graph.query(
            """MATCH (n:Node)-[r:EDGE]->(m:Node)
            WHERE n.id = $id AND m.type IN ['Entity', 'DocumentChunk', 'TextDocument', 'Document']
            RETURN m.id, m.name, m.type, m.properties
            LIMIT 20""",
            {"id": goal_id},
        )
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
    documents = []
    entities = []
    for row in neighbor_rows or []:
        if not row:
            continue
        props = {}
        if len(row) > 3 and isinstance(row[3], str) and row[3]:
            try:
                props = json.loads(row[3])
            except json.JSONDecodeError:
                props = {}
        elif len(row) > 3 and isinstance(row[3], dict):
            props = row[3]
        entry = {
            "id": str(row[0]),
            "name": str(row[1] or row[0]),
            "type": str(row[2] or ""),
            "summary": _clip(props.get("description") or props.get("text") or props.get("summary")),
        }
        if entry["type"] in _DOC_TYPES:
            documents.append(entry)
        else:
            entities.append(entry)
    ancestors = path.get("path") or []
    if ancestors and str(ancestors[-1].get("id")) == goal_id:
        ancestors = ancestors[:-1]
    return {
        "dataset_id": str(dataset_id),
        "goal": goal,
        "ancestors": ancestors,
        "children": children,
        "children_total": int(child_count_rows[0][0]) if child_count_rows else len(children),
        "note": _clip(goal.get("description"), 500),
        "purposes": purposes,
        "constraints": _linked(relation_items, "Constraint"),
        "relations": relation_items,
        "entities": entities,
        "documents": documents,
        "children_missing_purpose": [
            {"id": str(row[0]), "name": str(row[1] or row[0])} for row in missing_rows or [] if row
        ],
        "source": goal.get("source") or ("company_tree" if goal.get("cpd_kind") else None),
        "revision": str(goal.get("created_at") or ""),
        "missing_purpose": not purposes,
    }


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
    assumed_origin = "ai_inferred" if generated_by == "purpose-agent" else ""
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
        "source_revision": str(proposal.get("source_revision") or ""),
        "analysis_summary": _analysis_text(proposal),
        "items": items,
        "summary": _summary(items),
    }
    payload = _load(dataset_id)
    payload["proposals"][stored["id"]] = stored
    _save(dataset_id, payload)
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


async def commit_teleology_proposal(
    dataset_id: UUID,
    user: User,
    proposal_id: str,
    accepted_item_ids: list[str],
    *,
    edits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write accepted purpose nodes and edges. Leave the company tree untouched."""
    payload = _load(dataset_id)
    proposal = payload["proposals"].get(proposal_id)
    if not proposal:
        raise KeyError(f"Proposal {proposal_id} was not found")
    if proposal.get("status") == "committed":
        raise ValueError("This proposal is already committed")
    accepted = {str(item) for item in accepted_item_ids}
    dataset = await _authorized_dataset(dataset_id, user, "write")
    created_nodes: list[dict[str, str]] = []
    created_edges: list[dict[str, str]] = []
    skipped: list[str] = []
    id_by_ref: dict[str, str] = {}
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        for raw in proposal["items"]:
            if raw["id"] not in accepted or raw["kind"] not in _NODE_KINDS:
                continue
            item = _apply_edits(raw, edits)
            model = _NODE_KINDS[item["kind"]]
            node = model(
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
            node_id = str(node.id)
            id_by_ref[item["id"]] = node_id
            id_by_ref[raw["id"]] = node_id
            for label in (raw.get("name"), item.get("name")):
                if label:
                    id_by_ref[str(label)] = node_id
            raw["status"] = "accepted"
            raw["review_status"] = "accepted"
            raw["committed_node_id"] = node_id
            created_nodes.append({"id": node_id, "kind": item["kind"], "name": item["name"]})

        for raw in proposal["items"]:
            if raw["kind"] == "gap":
                raw["status"] = "accepted" if raw["id"] in accepted else "ignored"
                raw["review_status"] = raw["status"]
                if raw["id"] in accepted:
                    skipped.append(raw["id"])
                continue
            if raw["id"] not in accepted or raw["kind"] != "relation":
                if raw["id"] not in accepted and raw["status"] == "proposed":
                    raw["status"] = "ignored"
                    raw["review_status"] = "ignored"
                continue
            item = _apply_edits(raw, edits)
            source_id = id_by_ref.get(item["source"] or "") or item["source"]
            target_id = id_by_ref.get(item["target"] or "") or item["target"]
            if not source_id or not target_id or source_id == target_id:
                skipped.append(raw["id"])
                continue
            source_node = id_by_ref.get(item["source"] or "") or await graph.get_node(source_id)
            target_node = id_by_ref.get(item["target"] or "") or await graph.get_node(target_id)
            if source_node is None or target_node is None:
                skipped.append(raw["id"])
                continue
            relation = item["relationship"]
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
                            "run_id": proposal.get("run_id") or "",
                            "source_goal_id": proposal["source_goal_id"],
                            "reason": item["reason"],
                            "confidence": item.get("confidence"),
                            "evidence_node_ids": list(item.get("evidence_node_ids") or []),
                        },
                    )
                ]
            )
            raw["status"] = "accepted"
            raw["review_status"] = "accepted"
            created_edges.append(
                {"source_id": source_id, "target_id": target_id, "relationship": relation}
            )
    proposal["status"] = "committed"
    proposal["summary"] = _summary(proposal["items"])
    _save(dataset_id, payload)
    return {
        "proposal_id": proposal_id,
        "dataset_id": str(dataset_id),
        "committed_nodes": created_nodes,
        "committed_edges": created_edges,
        "skipped_item_ids": skipped,
    }
