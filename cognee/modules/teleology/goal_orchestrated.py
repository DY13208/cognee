"""Accept a WorkBuddy goal model as derived proposals.

WorkBuddy has already read the mind map and done the analysis. This module
checks that result and stores it. It does not call an LLM, does not confirm or
commit, and does not write the company tree or the formal teleology graph.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID, uuid4

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.goal_model import (
    GoalBuildError,
    _merge_key,
    _seal,
    _teleology_item,
    _union,
    classify_semantics,
)
from cognee.modules.teleology.goal_store import get_goal_store
from cognee.modules.teleology.graph_annotations import _authorized_dataset

_RELATIONS = frozenset({"serves", "advances", "blocks"})
_OUTCOME = ("提升", "提高", "达成", "实现", "改善")
_CONSTRAINT_NAME = ("不得超过", "不得高于", "上限", "费比", "约束", "限制")
_EMPTY_COUNTS = {
    "goals": 0,
    "hierarchy": 0,
    "purposes": 0,
    "constraints": 0,
    "relations": 0,
}


def compose_orchestrated_proposal(
    dataset_id: Any,
    payload: dict[str, Any],
    *,
    known_node_ids: set[str],
    previous: list[dict[str, Any]] | None = None,
    previous_teleology: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one analyzed payload. Invalid items are rejected, not the batch."""
    goals = list(payload.get("goals") or [])
    if not goals:
        raise GoalBuildError("goals must not be empty")
    generated_by = str(payload.get("generated_by") or "workbuddy_orchestrated")
    run = run_id or str(uuid4())
    known = {str(node_id) for node_id in known_node_ids}
    accepted_counts = dict(_EMPTY_COUNTS)
    rejected_counts = dict(_EMPTY_COUNTS)
    issues: list[dict[str, Any]] = []
    candidates = [dict(goal) for goal in previous or []]
    for goal in candidates:
        goal["parent_candidate_id"] = goal.get("parent_candidate_id") or None
    client_to_id: dict[str, str] = {}

    for raw in goals:
        client_id = str(raw.get("client_id") or "")
        sealed, issue = _accept_goal(dataset_id, raw, known, generated_by, run)
        if sealed is None:
            rejected_counts["goals"] += 1
            issues.append({"kind": "goal", "client_id": client_id, "reason": issue})
            continue
        match = _find_same(sealed, candidates)
        if match is not None:
            parent_id = match.get("parent_candidate_id")
            merged = _union(match, sealed)
            merged["generated_by"] = match.get("generated_by") or generated_by
            merged["run_id"] = match.get("run_id") or run
            if parent_id and not merged.get("parent_candidate_id"):
                merged["parent_candidate_id"] = parent_id
            match.clear()
            match.update(merged)
            client_to_id[client_id] = str(match["id"])
            issues.append(
                {
                    "kind": "goal",
                    "client_id": client_id,
                    "reason": "duplicate",
                    "duplicate_of": str(match["id"]),
                    "existing_candidate_id": str(match["id"]),
                }
            )
            continue
        candidates.append(sealed)
        client_to_id[client_id] = str(sealed["id"])
        accepted_counts["goals"] += 1

    _apply_hierarchy(
        list(payload.get("hierarchy") or []),
        candidates,
        client_to_id,
        known,
        accepted_counts,
        rejected_counts,
        issues,
    )
    prior = previous_teleology or {}
    purposes = [dict(item) for item in prior.get("purposes") or []]
    constraints = [dict(item) for item in prior.get("constraints") or []]
    relations = [dict(item) for item in prior.get("relations") or []]
    _apply_bound_items(
        list(payload.get("purposes") or []),
        kind="purpose",
        bucket=purposes,
        count_key="purposes",
        client_to_id=client_to_id,
        known=known,
        run_id=run,
        generated_by=generated_by,
        accepted_counts=accepted_counts,
        rejected_counts=rejected_counts,
        issues=issues,
    )
    _apply_bound_items(
        list(payload.get("constraints") or []),
        kind="constraint",
        bucket=constraints,
        count_key="constraints",
        client_to_id=client_to_id,
        known=known,
        run_id=run,
        generated_by=generated_by,
        accepted_counts=accepted_counts,
        rejected_counts=rejected_counts,
        issues=issues,
    )
    _apply_relations(
        list(payload.get("relations") or []),
        relations,
        client_to_id,
        known,
        run,
        accepted_counts,
        rejected_counts,
        issues,
    )
    active = [goal for goal in candidates if goal.get("status") != "rejected"]
    summary = _summary(run, accepted_counts, rejected_counts, issues)
    model = {
        "run_id": run,
        "dataset_id": str(dataset_id),
        "mode": "orchestrated",
        "status": "completed",
        "stage": "completed",
        "generated_by": generated_by,
        "committed": False,
        "graph_committed": False,
        "source_count": len(
            {node for goal in active for node in goal.get("source_node_ids") or []}
        ),
        "canonical_goal_count": len(active),
        "rejected_count": sum(rejected_counts.values()),
        "candidates": candidates,
        "teleology": {
            "purposes": purposes,
            "constraints": constraints,
            "relations": relations,
            "committed": False,
        },
        "purposes": purposes,
        "constraints": constraints,
        "relations": relations,
        "classifications": _classifications(active),
        "summary": summary,
    }
    return model, summary


async def submit_orchestrated_goal_model(
    dataset_id: UUID,
    user: Any,
    payload: dict[str, Any],
    *,
    known_node_ids: set[str] | None = None,
    store: Any = None,
) -> dict[str, Any]:
    """Validate, then persist. The company tree and formal graph are not written."""
    if not list(payload.get("goals") or []):
        raise GoalBuildError("goals must not be empty")
    await _authorized_dataset(dataset_id, user, "write")
    if known_node_ids is None:
        known_node_ids = await existing_node_ids(dataset_id, user, collect_node_ids(payload))
    goal_store = store if store is not None else get_goal_store()
    previous_view = await goal_store.get_dataset(dataset_id)
    previous = list((previous_view or {}).get("candidates") or [])
    previous_teleology = {
        "purposes": list((previous_view or {}).get("purposes") or []),
        "constraints": list((previous_view or {}).get("constraints") or []),
        "relations": list((previous_view or {}).get("relations") or []),
    }
    model, summary = compose_orchestrated_proposal(
        dataset_id,
        payload,
        known_node_ids=known_node_ids,
        previous=previous,
        previous_teleology=previous_teleology,
    )
    await goal_store.save_result(model)
    from cognee.modules.teleology.goal_model import STORE

    STORE.save(model)
    return summary


async def existing_node_ids(dataset_id: UUID, user: Any, node_ids: list[str]) -> set[str]:
    """Read node ids from the dataset graph. This does not write the company tree."""
    wanted = [str(node_id) for node_id in node_ids if str(node_id).strip()]
    if not wanted:
        return set()
    dataset = await _authorized_dataset(dataset_id, user, "read")
    found: set[str] = set()
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        for start in range(0, len(wanted), 200):
            chunk = wanted[start : start + 200]
            rows = await graph.query(
                "MATCH (n:Node) WHERE n.id IN $ids RETURN n.id",
                {"ids": chunk},
            )
            for row in rows or []:
                if row and row[0] is not None:
                    found.add(str(row[0]))
    return found


def collect_node_ids(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for goal in list(payload.get("goals") or []) + list(payload.get("purposes") or []):
        found.extend(str(node_id) for node_id in goal.get("source_node_ids") or [])
        found.extend(str(entry.get("node_id") or "") for entry in goal.get("evidence") or [])
    for item in payload.get("constraints") or []:
        found.extend(str(node_id) for node_id in item.get("source_node_ids") or [])
        found.extend(str(entry.get("node_id") or "") for entry in item.get("evidence") or [])
    for item in payload.get("relations") or []:
        found.extend(str(node_id) for node_id in item.get("source_node_ids") or [])
        found.extend(str(entry.get("node_id") or "") for entry in item.get("evidence") or [])
    for link in payload.get("hierarchy") or []:
        found.extend(str(node_id) for node_id in link.get("evidence_node_ids") or [])
    return found


def _accept_goal(
    dataset_id: Any,
    raw: dict[str, Any],
    known: set[str],
    generated_by: str,
    run_id: str,
) -> tuple[dict[str, Any] | None, str]:
    name = str(raw.get("name") or "").strip()
    reason = str(raw.get("reason") or "").strip()
    if not name:
        return None, "missing_name"
    if not reason:
        return None, "missing_reason"
    confidence = _confidence(raw.get("confidence"))
    if confidence is None:
        return None, "invalid_confidence"
    blocked = _blocked_goal(name, raw.get("evidence") or [])
    if blocked:
        return None, blocked
    source_ids = _unique(raw.get("source_node_ids"))
    evidence = [_evidence_row(entry) for entry in raw.get("evidence") or []]
    evidence = [entry for entry in evidence if entry["node_id"]]
    if not source_ids:
        return None, "missing_source_nodes"
    if not evidence:
        return None, "missing_evidence"
    evidence_ids = {entry["node_id"] for entry in evidence}
    if evidence_ids != set(source_ids):
        return None, "evidence_mismatch"
    valid = [entry for entry in evidence if entry["node_id"] in known]
    if not valid:
        return None, "invalid_evidence"
    sealed = _seal(
        dataset_id,
        name=name,
        description=str(raw.get("description") or ""),
        confidence=confidence,
        reason=reason,
        source_node_ids=[entry["node_id"] for entry in valid],
        evidence=valid,
        generated_by=generated_by,
    )
    sealed["run_id"] = run_id
    sealed["status"] = "proposed"
    sealed["confidence"] = confidence
    return sealed, ""


def _blocked_goal(name: str, evidence: list[dict[str, Any]]) -> str:
    label, _detail = classify_semantics({"name": name, "text": name, "description": name})
    outcome = any(token in name for token in _OUTCOME)
    if label == "Responsibility":
        return "responsibility_not_goal"
    if label == "Constraint" or (any(token in name for token in _CONSTRAINT_NAME) and not outcome):
        return "constraint_not_goal"
    if label == "Metric" and not outcome:
        return "metric_only"
    if label == "Project" and not outcome:
        return "project_only"
    classes = {
        str(entry.get("semantic_class") or entry.get("source_class") or "")
        for entry in evidence
        if str(entry.get("semantic_class") or entry.get("source_class") or "")
    }
    if classes == {"Responsibility"}:
        return "responsibility_not_goal"
    if classes == {"Metric"} and not outcome:
        return "metric_only"
    return ""


def _apply_hierarchy(
    links: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    client_to_id: dict[str, str],
    known: set[str],
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
) -> None:
    by_id = {str(goal["id"]): goal for goal in candidates if goal.get("status") != "rejected"}
    parents = {
        str(goal["id"]): str(goal["parent_candidate_id"])
        for goal in by_id.values()
        if goal.get("parent_candidate_id")
    }
    for raw in links:
        parent_client = str(raw.get("parent_client_id") or "")
        child_client = str(raw.get("child_client_id") or "")
        reason = _hierarchy_issue(raw, parent_client, child_client, client_to_id, known)
        if reason:
            rejected_counts["hierarchy"] += 1
            issues.append(
                {
                    "kind": "hierarchy",
                    "client_id": child_client or parent_client,
                    "reason": reason,
                }
            )
            continue
        parent_id = client_to_id[parent_client]
        child_id = client_to_id[child_client]
        if parent_id == child_id:
            rejected_counts["hierarchy"] += 1
            issues.append({"kind": "hierarchy", "client_id": child_client, "reason": "self_parent"})
            continue
        if child_id in parents:
            rejected_counts["hierarchy"] += 1
            issues.append(
                {"kind": "hierarchy", "client_id": child_client, "reason": "multiple_parents"}
            )
            continue
        if _creates_cycle(parents, parent_id, child_id):
            rejected_counts["hierarchy"] += 1
            issues.append({"kind": "hierarchy", "client_id": child_client, "reason": "cycle"})
            continue
        by_id[child_id]["parent_candidate_id"] = parent_id
        parents[child_id] = parent_id
        accepted_counts["hierarchy"] += 1


def _hierarchy_issue(
    raw: dict[str, Any],
    parent_client: str,
    child_client: str,
    client_to_id: dict[str, str],
    known: set[str],
) -> str:
    relationship = str(raw.get("relationship") or "").strip().lower()
    if relationship == "has_subgoal" or str(raw.get("origin") or "") == "system_derived":
        return "structural_copy"
    if not str(raw.get("reason") or "").strip():
        return "missing_reason"
    supplied = _unique(raw.get("evidence_node_ids"))
    if not supplied:
        return "missing_evidence"
    if not any(node_id in known for node_id in supplied):
        return "invalid_evidence"
    if parent_client == child_client:
        return "self_parent"
    if parent_client not in client_to_id or child_client not in client_to_id:
        return "missing_endpoint"
    if raw.get("confidence") is not None and _confidence(raw.get("confidence")) is None:
        return "invalid_confidence"
    return ""


def _apply_bound_items(
    rows: list[dict[str, Any]],
    *,
    kind: str,
    bucket: list[dict[str, Any]],
    count_key: str,
    client_to_id: dict[str, str],
    known: set[str],
    run_id: str,
    generated_by: str,
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
) -> None:
    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("goal_client_id") or "")
        goal_client = str(raw.get("goal_client_id") or "")
        reason = _bound_issue(raw, goal_client, client_to_id, known)
        if reason:
            rejected_counts[count_key] += 1
            issues.append({"kind": kind, "client_id": client_id or goal_client, "reason": reason})
            continue
        evidence = [
            entry
            for entry in (_evidence_row(item) for item in raw.get("evidence") or [])
            if entry["node_id"] in known
        ]
        bucket.append(
            _teleology_item(
                run_id,
                kind=kind,
                goal_id=client_to_id[goal_client],
                name=str(raw.get("name") or "").strip(),
                reason=str(raw.get("reason") or "").strip(),
                confidence=_confidence(raw.get("confidence")),
                evidence=evidence,
                source_node_ids=[entry["node_id"] for entry in evidence],
                generated_by=generated_by,
            )
        )
        accepted_counts[count_key] += 1


def _bound_issue(
    raw: dict[str, Any],
    goal_client: str,
    client_to_id: dict[str, str],
    known: set[str],
) -> str:
    if goal_client not in client_to_id:
        return "missing_goal"
    if not str(raw.get("name") or "").strip():
        return "missing_name"
    if not str(raw.get("reason") or "").strip():
        return "missing_reason"
    if _confidence(raw.get("confidence")) is None:
        return "invalid_confidence"
    evidence = [_evidence_row(entry) for entry in raw.get("evidence") or []]
    source_ids = _unique(raw.get("source_node_ids"))
    if not evidence or not source_ids:
        return "missing_evidence"
    if {entry["node_id"] for entry in evidence if entry["node_id"]} != set(source_ids):
        return "evidence_mismatch"
    if not any(entry["node_id"] in known for entry in evidence):
        return "invalid_evidence"
    return ""


def _apply_relations(
    rows: list[dict[str, Any]],
    bucket: list[dict[str, Any]],
    client_to_id: dict[str, str],
    known: set[str],
    run_id: str,
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
) -> None:
    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("source_client_id") or "")
        reason = _relation_issue(raw, client_to_id, known)
        if reason:
            rejected_counts["relations"] += 1
            issues.append({"kind": "relation", "client_id": client_id, "reason": reason})
            continue
        source_id = client_to_id[str(raw.get("source_client_id") or "")]
        target_id = client_to_id[str(raw.get("target_client_id") or "")]
        evidence = [
            entry
            for entry in (_evidence_row(item) for item in raw.get("evidence") or [])
            if entry["node_id"] in known
        ]
        relationship = str(raw.get("relationship") or "").strip().lower()
        bucket.append(
            _teleology_item(
                run_id,
                kind="relation",
                relationship=relationship,
                source=source_id,
                target=target_id,
                goal_id=source_id,
                name=relationship,
                reason=str(raw.get("reason") or "").strip(),
                confidence=_confidence(raw.get("confidence")),
                evidence=evidence,
                source_node_ids=[entry["node_id"] for entry in evidence],
            )
        )
        accepted_counts["relations"] += 1


def _relation_issue(raw: dict[str, Any], client_to_id: dict[str, str], known: set[str]) -> str:
    relationship = str(raw.get("relationship") or "").strip().lower()
    source_client = str(raw.get("source_client_id") or "")
    target_client = str(raw.get("target_client_id") or "")
    if relationship not in _RELATIONS:
        return "invalid_relationship" if relationship != "has_subgoal" else "structural_copy"
    if source_client == target_client:
        return "self_loop"
    if source_client not in client_to_id or target_client not in client_to_id:
        return "missing_endpoint"
    if not str(raw.get("reason") or "").strip():
        return "missing_reason"
    if _confidence(raw.get("confidence")) is None:
        return "invalid_confidence"
    evidence = [_evidence_row(entry) for entry in raw.get("evidence") or []]
    source_ids = _unique(raw.get("source_node_ids"))
    if not evidence or not source_ids:
        return "missing_evidence"
    if not any(entry["node_id"] in known for entry in evidence):
        return "invalid_evidence"
    return ""


def _find_same(candidate: dict[str, Any], goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = _merge_key(candidate)
    digest = str(candidate.get("semantic_hash") or "")
    for goal in goals:
        if goal.get("status") == "rejected":
            continue
        if str(goal.get("semantic_hash") or "") == digest or _merge_key(goal) == key:
            return goal
    return None


def _creates_cycle(parents: dict[str, str], parent_id: str, child_id: str) -> bool:
    seen = {child_id}
    cursor: str | None = parent_id
    while cursor:
        if cursor in seen:
            return True
        seen.add(cursor)
        cursor = parents.get(cursor)
    return False


def _summary(
    run_id: str,
    accepted: dict[str, int],
    rejected: dict[str, int],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    duplicates = [issue for issue in issues if issue.get("reason") == "duplicate"]
    return {
        "run_id": run_id,
        "status": "completed",
        "mode": "orchestrated",
        "accepted": dict(accepted),
        "rejected": dict(rejected),
        "duplicates": len(duplicates),
        "issues": issues,
        "committed": False,
        "graph_committed": False,
    }


def _classifications(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for goal in goals:
        for entry in goal.get("evidence") or []:
            node_id = str(entry.get("node_id") or "")
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            rows.append(
                {
                    "id": node_id,
                    "name": entry.get("name") or node_id,
                    "semantic_class": entry.get("semantic_class")
                    or entry.get("source_class")
                    or "",
                    "source_class": entry.get("source_class") or entry.get("semantic_class") or "",
                    "source_layer": entry.get("source_layer") or entry.get("layer") or "",
                    "layer": entry.get("source_layer") or entry.get("layer") or "",
                }
            )
    return rows


def _evidence_row(entry: dict[str, Any]) -> dict[str, Any]:
    semantic = str(entry.get("semantic_class") or entry.get("source_class") or "")
    layer = str(entry.get("source_layer") or entry.get("layer") or "")
    return {
        "node_id": str(entry.get("node_id") or "").strip(),
        "name": str(entry.get("name") or ""),
        "semantic_class": semantic,
        "source_class": str(entry.get("source_class") or semantic or "Other"),
        "source_layer": layer,
        "layer": layer,
        "text": str(entry.get("text") or ""),
        "reason": str(entry.get("reason") or ""),
    }


def _unique(values: Any) -> list[str]:
    found: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in found:
            found.append(text)
    return found


def _confidence(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number < 0 or number > 1:
        return None
    return number
