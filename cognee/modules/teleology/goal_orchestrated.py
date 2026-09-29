"""Accept a WorkBuddy goal model as derived proposals.

Validation finishes in memory. A strict failure writes nothing. A passing
replace snapshot is stored in one save. This module does not call an LLM,
does not confirm or commit, and does not write the company tree or the
formal teleology graph.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.goal_model import (
    GoalBuildError,
    _seal,
    _teleology_item,
    classify_semantics,
)
from cognee.modules.teleology.goal_store import get_goal_store
from cognee.modules.teleology.graph_annotations import _authorized_dataset

_NAMESPACE = uuid5(NAMESPACE_URL, "cognee:teleology:orchestrated-goal")
_RELATIONS = frozenset({"serves", "advances", "blocks"})
_OUTCOME = ("提升", "提高", "达成", "实现", "改善")
_CONSTRAINT_NAME = ("不得超过", "不得高于", "上限", "费比", "约束", "限制")
_CRITICAL = frozenset(
    {
        "identity_collision",
        "self_parent",
        "missing_endpoint",
        "cycle",
        "multiple_parents",
        "invalid_evidence",
    }
)
_EMPTY_COUNTS = {
    "goals": 0,
    "hierarchy": 0,
    "purposes": 0,
    "constraints": 0,
    "relations": 0,
}


def normalize_canonical_name(name: str) -> str:
    """Identity uses the goal name only. Evidence text is not part of it."""
    return " ".join(str(name or "").split()).casefold()


def orchestrated_goal_identity(name: str, scope: str = "") -> str:
    """Canonical name plus an explicit business scope. Evidence cannot change it."""
    base = normalize_canonical_name(name)
    extra = normalize_canonical_name(scope)
    if not extra:
        return base
    return f"{base}\n{extra}"


def orchestrated_semantic_hash(name: str, scope: str = "") -> str:
    """Hash the canonical identity. Shared evidence keywords do not collide."""
    return hashlib.sha256(orchestrated_goal_identity(name, scope).encode("utf-8")).hexdigest()


def orchestrated_candidate_id(dataset_id: Any, name: str, scope: str = "") -> str:
    digest = orchestrated_semantic_hash(name, scope)
    return str(uuid5(_NAMESPACE, f"{dataset_id}:{digest}"))


def normalize_evidence(
    raw: dict[str, Any],
    known: set[str],
    catalog: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], str]:
    """One evidence shape for goals, hierarchy, purposes, constraints, and relations.

    Callers may send evidence objects, evidence_node_ids, or source_node_ids.
    Ids that exist in the dataset are hydrated. Unknown ids are invalid.
    """
    info = catalog or {}
    objects: list[dict[str, Any]] = []
    for entry in raw.get("evidence") or []:
        if isinstance(entry, str):
            objects.append({"node_id": entry})
        elif isinstance(entry, dict):
            objects.append(dict(entry))
    ids = _unique(
        [str(entry.get("node_id") or "") for entry in objects]
        + list(raw.get("evidence_node_ids") or [])
        + list(raw.get("source_node_ids") or [])
    )
    if not ids:
        return [], [], "missing_evidence"
    supplied = {str(entry.get("node_id") or ""): entry for entry in objects}
    evidence: list[dict[str, Any]] = []
    unknown: list[str] = []
    for node_id in ids:
        if node_id not in known:
            unknown.append(node_id)
            continue
        evidence.append(_hydrate(node_id, supplied.get(node_id) or {}, info.get(node_id) or {}))
    if unknown or not evidence:
        return evidence, [entry["node_id"] for entry in evidence], "invalid_evidence"
    source_ids = [entry["node_id"] for entry in evidence]
    return evidence, source_ids, ""


def compose_orchestrated_proposal(
    dataset_id: Any,
    payload: dict[str, Any],
    *,
    known_node_ids: set[str],
    previous: list[dict[str, Any]] | None = None,
    previous_teleology: dict[str, Any] | None = None,
    run_id: str | None = None,
    catalog: dict[str, dict[str, Any]] | None = None,
    submission_mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one snapshot in memory. Nothing here is written."""
    goals = list(payload.get("goals") or [])
    if not goals:
        raise GoalBuildError("goals must not be empty")
    mode = str(submission_mode or payload.get("submission_mode") or "replace")
    if mode not in {"replace", "merge"}:
        raise GoalBuildError("submission_mode must be replace or merge")
    generated_by = str(payload.get("generated_by") or "workbuddy_orchestrated")
    run = run_id or str(uuid4())
    known, info = _known_catalog(known_node_ids, catalog)
    accepted_counts = dict(_EMPTY_COUNTS)
    rejected_counts = dict(_EMPTY_COUNTS)
    issues: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    hierarchy_preview: list[dict[str, Any]] = []
    purpose_preview: list[dict[str, Any]] = []
    constraint_preview: list[dict[str, Any]] = []
    relation_preview: list[dict[str, Any]] = []

    prior = [dict(goal) for goal in previous or []]
    confirmed = {
        _stored_identity(goal): goal for goal in prior if goal.get("status") == "confirmed"
    }
    candidates = [dict(goal) for goal in prior] if mode == "merge" else []
    for goal in candidates:
        if _client_mentioned(goal, goals):
            goal["parent_candidate_id"] = None
    by_identity: dict[str, dict[str, Any]] = {}
    for goal in candidates:
        if goal.get("status") == "rejected":
            continue
        by_identity.setdefault(_stored_identity(goal), goal)
    client_to_id: dict[str, str] = {}
    client_identity: dict[str, str] = {}

    for raw in goals:
        client_id = str(raw.get("client_id") or "")
        sealed, issue = _accept_goal(dataset_id, raw, known, info, generated_by, run)
        if sealed is None:
            _reject("goal", client_id, issue or "invalid", rejected_counts, issues, "goals")
            continue
        identity = str(sealed["orchestrated_identity"])
        current = by_identity.get(identity)
        if current is not None and _stored_identity(current) != identity:
            _reject("goal", client_id, "identity_collision", rejected_counts, issues, "goals")
            continue
        if current is not None:
            if not _same_identity(current, sealed):
                _reject("goal", client_id, "identity_collision", rejected_counts, issues, "goals")
                continue
            owner = _owner_client(client_identity, identity) or client_id
            _merge_duplicate(current, sealed)
            client_to_id[client_id] = str(current["id"])
            client_identity[client_id] = identity
            duplicates.append(
                {
                    "client_id": client_id,
                    "duplicate_of_client_id": owner,
                    "existing_candidate_id": str(current["id"]),
                    "reason": "duplicate",
                }
            )
            issues.append(duplicates[-1] | {"kind": "goal"})
            continue
        prior_confirmed = confirmed.get(identity)
        if prior_confirmed is not None:
            sealed["id"] = str(prior_confirmed.get("id") or sealed["id"])
            sealed["status"] = "confirmed"
            sealed["parent_candidate_id"] = None
        candidates.append(sealed)
        by_identity[identity] = sealed
        client_to_id[client_id] = str(sealed["id"])
        client_identity[client_id] = identity
        accepted_counts["goals"] += 1

    _reject_identity_collisions(client_to_id, client_identity, rejected_counts, issues)
    collision_ids = {
        str(issue.get("client_id") or "")
        for issue in issues
        if issue.get("reason") == "identity_collision"
    }
    for client_id in collision_ids:
        client_to_id.pop(client_id, None)

    if mode == "replace":
        for goal in candidates:
            if goal.get("status") != "legacy_confirmed":
                goal["parent_candidate_id"] = None

    _apply_hierarchy(
        list(payload.get("hierarchy") or []),
        candidates,
        client_to_id,
        known,
        info,
        accepted_counts,
        rejected_counts,
        issues,
        hierarchy_preview,
    )
    purposes = (
        _kept_confirmed(previous_teleology, "purposes")
        if mode == "replace"
        else [dict(item) for item in (previous_teleology or {}).get("purposes") or []]
    )
    constraints = (
        _kept_confirmed(previous_teleology, "constraints")
        if mode == "replace"
        else [dict(item) for item in (previous_teleology or {}).get("constraints") or []]
    )
    relations = (
        _kept_confirmed(previous_teleology, "relations")
        if mode == "replace"
        else [dict(item) for item in (previous_teleology or {}).get("relations") or []]
    )
    if mode == "merge":
        purposes = [dict(item) for item in (previous_teleology or {}).get("purposes") or []]
        constraints = [dict(item) for item in (previous_teleology or {}).get("constraints") or []]
        relations = [dict(item) for item in (previous_teleology or {}).get("relations") or []]
    _apply_bound_items(
        list(payload.get("purposes") or []),
        kind="purpose",
        bucket=purposes,
        count_key="purposes",
        preview=purpose_preview,
        client_to_id=client_to_id,
        known=known,
        catalog=info,
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
        preview=constraint_preview,
        client_to_id=client_to_id,
        known=known,
        catalog=info,
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
        info,
        run,
        accepted_counts,
        rejected_counts,
        issues,
        relation_preview,
    )
    if mode == "replace":
        _attach_legacy_confirmed(candidates, confirmed, by_identity)
        _drop_dangling_parents(candidates)
    active = [goal for goal in candidates if goal.get("status") != "rejected"]
    summary = _summary(
        run,
        accepted_counts,
        rejected_counts,
        issues,
        duplicates,
        client_to_id,
        [goal for goal in active if not goal.get("outside_current_snapshot")],
        hierarchy_preview,
        purpose_preview,
        constraint_preview,
        relation_preview,
        mode,
    )
    model = {
        "run_id": run,
        "dataset_id": str(dataset_id),
        "mode": "orchestrated",
        "status": "completed",
        "stage": "completed",
        "submission_mode": mode,
        "generated_by": generated_by,
        "committed": False,
        "graph_committed": False,
        "source_count": len(
            {node for goal in active for node in goal.get("source_node_ids") or []}
        ),
        "canonical_goal_count": len(
            [goal for goal in active if not goal.get("outside_current_snapshot")]
        ),
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
    catalog: dict[str, dict[str, Any]] | None = None,
    store: Any = None,
    dry_run: bool | None = None,
    strict: bool | None = None,
    submission_mode: str | None = None,
) -> dict[str, Any]:
    """Validate, then persist one snapshot. A strict failure does not write."""
    if not list(payload.get("goals") or []):
        raise GoalBuildError("goals must not be empty")
    preview_only = bool(payload.get("dry_run") if dry_run is None else dry_run)
    enforce = True if strict is None else bool(strict)
    if "strict" in payload and strict is None:
        enforce = bool(payload.get("strict"))
    mode = str(submission_mode or payload.get("submission_mode") or "replace")
    await _authorized_dataset(dataset_id, user, "write")
    if known_node_ids is None:
        loaded = await load_node_catalog(dataset_id, user, collect_node_ids(payload))
        known_node_ids = set(loaded)
        catalog = {**loaded, **(catalog or {})}
    goal_store = store if store is not None else get_goal_store()
    previous_view = None if preview_only else await goal_store.get_dataset(dataset_id)
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
        previous=None if preview_only else previous,
        previous_teleology=None if preview_only else previous_teleology,
        catalog=catalog,
        submission_mode=mode,
    )
    summary["dry_run"] = preview_only
    summary["strict"] = enforce
    summary["saved"] = False
    if preview_only:
        summary["run_id"] = None
        summary["status"] = "validated" if summary["valid"] else "validation_failed"
        return summary
    if enforce and not summary["valid"]:
        summary["run_id"] = None
        summary["status"] = "validation_failed"
        return summary
    await goal_store.save_result(model)
    from cognee.modules.teleology.goal_model import STORE

    STORE.save(model)
    summary["saved"] = True
    summary["status"] = "completed"
    summary["run_id"] = model["run_id"]
    return summary


async def load_node_catalog(
    dataset_id: UUID, user: Any, node_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Read node identity from the dataset graph. This does not write it."""
    wanted = _unique(node_ids)
    if not wanted:
        return {}
    dataset = await _authorized_dataset(dataset_id, user, "read")
    found: dict[str, dict[str, Any]] = {}
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        for start in range(0, len(wanted), 200):
            chunk = wanted[start : start + 200]
            rows = await graph.query(
                """MATCH (n:Node) WHERE n.id IN $ids
                RETURN n.id, n.name, n.type, n.properties""",
                {"ids": chunk},
            )
            for row in rows or []:
                parsed = _catalog_row(row)
                if parsed is not None:
                    found[parsed["node_id"]] = parsed
    return found


async def existing_node_ids(dataset_id: UUID, user: Any, node_ids: list[str]) -> set[str]:
    """Read node ids from the dataset graph. This does not write the company tree."""
    return set(await load_node_catalog(dataset_id, user, node_ids))


def collect_node_ids(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    sections = (
        list(payload.get("goals") or [])
        + list(payload.get("purposes") or [])
        + list(payload.get("constraints") or [])
        + list(payload.get("relations") or [])
        + list(payload.get("hierarchy") or [])
    )
    for item in sections:
        found.extend(_unique(item.get("source_node_ids")))
        found.extend(_unique(item.get("evidence_node_ids")))
        for entry in item.get("evidence") or []:
            if isinstance(entry, dict):
                found.append(str(entry.get("node_id") or ""))
            elif isinstance(entry, str):
                found.append(entry)
    return found


def _accept_goal(
    dataset_id: Any,
    raw: dict[str, Any],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    generated_by: str,
    run_id: str,
) -> tuple[dict[str, Any] | None, str]:
    name = str(raw.get("name") or "").strip()
    reason = str(raw.get("reason") or "").strip()
    scope = str(raw.get("business_object") or raw.get("scope") or "")
    if not name:
        return None, "missing_name"
    if not reason:
        return None, "missing_reason"
    confidence = _confidence(raw.get("confidence"))
    if confidence is None:
        return None, "invalid_confidence"
    evidence, source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
    blocked = _blocked_goal(name, evidence)
    if blocked:
        return None, blocked
    if evidence_issue:
        return None, evidence_issue
    sealed = _seal(
        dataset_id,
        name=name,
        description=str(raw.get("description") or ""),
        confidence=confidence,
        reason=reason,
        source_node_ids=source_ids,
        evidence=evidence,
        generated_by=generated_by,
    )
    sealed["id"] = orchestrated_candidate_id(dataset_id, name, scope)
    sealed["semantic_hash"] = orchestrated_semantic_hash(name, scope)
    sealed["orchestrated_identity"] = orchestrated_goal_identity(name, scope)
    sealed["scope"] = scope
    sealed["run_id"] = run_id
    sealed["status"] = "proposed"
    sealed["confidence"] = confidence
    sealed["parent_candidate_id"] = None
    return sealed, ""


def _merge_duplicate(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Keep the canonical name. Only evidence, sources, and confidence combine."""
    if not _same_identity(existing, incoming):
        raise GoalBuildError("identity_collision")
    evidence = list(existing.get("evidence") or [])
    seen = {str(entry.get("node_id") or "") for entry in evidence}
    for entry in incoming.get("evidence") or []:
        node_id = str(entry.get("node_id") or "")
        if node_id and node_id not in seen:
            seen.add(node_id)
            evidence.append(entry)
    source_ids = list(existing.get("source_node_ids") or [])
    for node_id in incoming.get("source_node_ids") or []:
        if node_id not in source_ids:
            source_ids.append(node_id)
    existing["evidence"] = evidence
    existing["source_node_ids"] = source_ids
    existing["confidence"] = max(
        float(existing.get("confidence") or 0), float(incoming.get("confidence") or 0)
    )
    incoming_reason = str(incoming.get("reason") or "").strip()
    if incoming_reason and incoming_reason != str(existing.get("reason") or ""):
        notes = list(existing.get("reason_provenance") or [])
        notes.append(incoming_reason)
        existing["reason_provenance"] = notes
    existing["name"] = existing.get("name")
    existing["description"] = existing.get("description")
    existing["parent_candidate_id"] = None


def _same_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _stored_identity(left) == _stored_identity(right) and normalize_canonical_name(
        str(left.get("name") or "")
    ) == normalize_canonical_name(str(right.get("name") or ""))


def _stored_identity(goal: dict[str, Any]) -> str:
    stored = str(goal.get("orchestrated_identity") or "")
    if stored:
        return stored
    return orchestrated_goal_identity(
        str(goal.get("name") or ""), str(goal.get("scope") or goal.get("business_object") or "")
    )


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
    catalog: dict[str, dict[str, Any]],
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    preview: list[dict[str, Any]],
) -> None:
    by_id = {
        str(goal["id"]): goal
        for goal in candidates
        if goal.get("status") not in {"rejected", "legacy_confirmed"}
        and not goal.get("outside_current_snapshot")
    }
    parents = {
        str(goal["id"]): str(goal["parent_candidate_id"])
        for goal in by_id.values()
        if goal.get("parent_candidate_id")
    }
    for raw in links:
        parent_client = str(raw.get("parent_client_id") or "")
        child_client = str(raw.get("child_client_id") or "")
        reason = _hierarchy_issue(raw, parent_client, child_client, client_to_id, known, catalog)
        parent_id = client_to_id.get(parent_client)
        child_id = client_to_id.get(child_client)
        if reason == "" and parent_id and child_id and parent_id == child_id:
            reason = "self_parent"
        if reason == "" and child_id in parents:
            reason = "multiple_parents"
        if reason == "" and parent_id and child_id and _creates_cycle(parents, parent_id, child_id):
            reason = "cycle"
        if reason:
            _reject(
                "hierarchy",
                child_client or parent_client,
                reason,
                rejected_counts,
                issues,
                "hierarchy",
            )
            preview.append(
                {
                    "parent_client_id": parent_client,
                    "child_client_id": child_client,
                    "parent_candidate_id": parent_id,
                    "child_candidate_id": child_id,
                    "status": "rejected",
                    "reason": reason,
                }
            )
            continue
        assert parent_id is not None and child_id is not None
        by_id[child_id]["parent_candidate_id"] = parent_id
        parents[child_id] = parent_id
        accepted_counts["hierarchy"] += 1
        preview.append(
            {
                "parent_client_id": parent_client,
                "child_client_id": child_client,
                "parent_candidate_id": parent_id,
                "child_candidate_id": child_id,
                "status": "accepted",
                "reason": "",
            }
        )


def _hierarchy_issue(
    raw: dict[str, Any],
    parent_client: str,
    child_client: str,
    client_to_id: dict[str, str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
) -> str:
    relationship = str(raw.get("relationship") or "").strip().lower()
    if relationship == "has_subgoal" or str(raw.get("origin") or "") == "system_derived":
        return "structural_copy"
    if not str(raw.get("reason") or "").strip():
        return "missing_reason"
    _evidence, _source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
    if evidence_issue:
        return evidence_issue
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
    preview: list[dict[str, Any]],
    client_to_id: dict[str, str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    run_id: str,
    generated_by: str,
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
) -> None:
    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("goal_client_id") or "")
        goal_client = str(raw.get("goal_client_id") or "")
        evidence, source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
        reason = _bound_issue(raw, goal_client, client_to_id, evidence_issue)
        if reason:
            _reject(kind, client_id or goal_client, reason, rejected_counts, issues, count_key)
            preview.append(
                {
                    "client_id": client_id,
                    "goal_client_id": goal_client,
                    "status": "rejected",
                    "reason": reason,
                }
            )
            continue
        item = _teleology_item(
            run_id,
            kind=kind,
            goal_id=client_to_id[goal_client],
            name=str(raw.get("name") or "").strip(),
            reason=str(raw.get("reason") or "").strip(),
            confidence=_confidence(raw.get("confidence")),
            evidence=evidence,
            source_node_ids=source_ids,
            generated_by=generated_by,
        )
        bucket.append(item)
        accepted_counts[count_key] += 1
        preview.append(
            {
                "client_id": client_id,
                "goal_client_id": goal_client,
                "id": item["id"],
                "status": "accepted",
                "reason": "",
            }
        )


def _bound_issue(
    raw: dict[str, Any],
    goal_client: str,
    client_to_id: dict[str, str],
    evidence_issue: str,
) -> str:
    if goal_client not in client_to_id:
        return "missing_goal"
    if not str(raw.get("name") or "").strip():
        return "missing_name"
    if not str(raw.get("reason") or "").strip():
        return "missing_reason"
    if _confidence(raw.get("confidence")) is None:
        return "invalid_confidence"
    return evidence_issue


def _apply_relations(
    rows: list[dict[str, Any]],
    bucket: list[dict[str, Any]],
    client_to_id: dict[str, str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    run_id: str,
    accepted_counts: dict[str, int],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    preview: list[dict[str, Any]],
) -> None:
    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("source_client_id") or "")
        evidence, source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
        reason = _relation_issue(raw, client_to_id, evidence_issue)
        if reason:
            _reject("relation", client_id, reason, rejected_counts, issues, "relations")
            preview.append({"client_id": client_id, "status": "rejected", "reason": reason})
            continue
        source_id = client_to_id[str(raw.get("source_client_id") or "")]
        target_id = client_to_id[str(raw.get("target_client_id") or "")]
        relationship = str(raw.get("relationship") or "").strip().lower()
        item = _teleology_item(
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
            source_node_ids=source_ids,
        )
        bucket.append(item)
        accepted_counts["relations"] += 1
        preview.append(
            {
                "client_id": client_id,
                "source_client_id": raw.get("source_client_id"),
                "target_client_id": raw.get("target_client_id"),
                "relationship": relationship,
                "id": item["id"],
                "status": "accepted",
                "reason": "",
            }
        )


def _relation_issue(raw: dict[str, Any], client_to_id: dict[str, str], evidence_issue: str) -> str:
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
    return evidence_issue


def _attach_legacy_confirmed(
    candidates: list[dict[str, Any]],
    confirmed: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> None:
    present = set(current)
    for identity, goal in confirmed.items():
        if identity in present:
            continue
        legacy = dict(goal)
        legacy["status"] = "legacy_confirmed"
        legacy["outside_current_snapshot"] = True
        legacy["parent_candidate_id"] = None
        candidates.append(legacy)


def _drop_dangling_parents(candidates: list[dict[str, Any]]) -> None:
    ids = {str(goal.get("id") or "") for goal in candidates}
    for goal in candidates:
        parent = str(goal.get("parent_candidate_id") or "")
        if parent and parent not in ids:
            goal["parent_candidate_id"] = None


def _reject_identity_collisions(
    client_to_id: dict[str, str],
    client_identity: dict[str, str],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
) -> None:
    owners: dict[str, str] = {}
    for client_id, candidate_id in client_to_id.items():
        identity = client_identity.get(client_id) or ""
        previous = owners.get(candidate_id)
        if previous is None:
            owners[candidate_id] = identity
            continue
        if previous != identity:
            _reject("goal", client_id, "identity_collision", rejected_counts, issues, "goals")


def _summary(
    run_id: str,
    accepted: dict[str, int],
    rejected: dict[str, int],
    issues: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    client_to_id: dict[str, str],
    normalized: list[dict[str, Any]],
    hierarchy_preview: list[dict[str, Any]],
    purpose_preview: list[dict[str, Any]],
    constraint_preview: list[dict[str, Any]],
    relation_preview: list[dict[str, Any]],
    submission_mode: str,
) -> dict[str, Any]:
    critical = [issue for issue in issues if issue.get("reason") in _CRITICAL]
    valid = not critical
    return {
        "run_id": run_id,
        "status": "completed" if valid else "validation_failed",
        "mode": "orchestrated",
        "submission_mode": submission_mode,
        "valid": valid,
        "saved": False,
        "normalized_goals": [
            {
                "id": goal.get("id"),
                "name": goal.get("name"),
                "description": goal.get("description"),
                "reason": goal.get("reason"),
                "confidence": goal.get("confidence"),
                "source_node_ids": list(goal.get("source_node_ids") or []),
                "evidence": list(goal.get("evidence") or []),
                "parent_candidate_id": goal.get("parent_candidate_id"),
                "status": goal.get("status"),
                "semantic_hash": goal.get("semantic_hash"),
            }
            for goal in normalized
        ],
        "resolved_client_ids": dict(client_to_id),
        "duplicates": duplicates,
        "hierarchy_preview": hierarchy_preview,
        "purposes_preview": purpose_preview,
        "constraints_preview": constraint_preview,
        "relations_preview": relation_preview,
        "accepted": dict(accepted),
        "rejected": dict(rejected),
        "issues": issues,
        "critical_errors": critical,
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


def _hydrate(node_id: str, base: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    graph_type = str(info.get("type") or "")
    semantic = str(
        base.get("semantic_class") or base.get("source_class") or _class_from_type(graph_type)
    )
    layer = str(
        base.get("source_layer")
        or base.get("layer")
        or info.get("source_layer")
        or _layer_from_type(graph_type)
    )
    return {
        "node_id": node_id,
        "name": str(base.get("name") or info.get("name") or ""),
        "semantic_class": semantic,
        "source_class": str(base.get("source_class") or semantic or "Other"),
        "source_layer": layer,
        "layer": layer,
        "text": str(
            base.get("text")
            or info.get("text")
            or info.get("description")
            or info.get("note")
            or ""
        ),
        "reason": str(base.get("reason") or ""),
    }


def _catalog_row(row: Any) -> dict[str, Any] | None:
    if not row or row[0] is None:
        return None
    props = row[3] if len(row) > 3 else None
    if isinstance(props, str):
        props = {}
    props = props or {}
    graph_type = str(row[2] or "") if len(row) > 2 else ""
    return {
        "node_id": str(row[0]),
        "name": str((row[1] if len(row) > 1 else "") or props.get("name") or ""),
        "type": graph_type,
        "description": str(props.get("description") or ""),
        "note": str(props.get("source_note") or props.get("note") or ""),
        "text": str(
            props.get("description") or props.get("text") or props.get("source_note") or ""
        ),
        "source_layer": _layer_from_type(graph_type),
    }


def _class_from_type(graph_type: str) -> str:
    if graph_type == "Document":
        return "Document"
    if graph_type in {"Entity", "Person", "Organization"}:
        return "Entity"
    if graph_type == "Goal":
        return "Other"
    return ""


def _layer_from_type(graph_type: str) -> str:
    if graph_type == "Document":
        return "document"
    if graph_type in {"Entity", "Person", "Organization"}:
        return "entity"
    if graph_type == "Goal":
        return "company_tree"
    return ""


def _known_catalog(
    known_node_ids: set[str], catalog: dict[str, dict[str, Any]] | None
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    info = {str(key): dict(value) for key, value in (catalog or {}).items()}
    known = {str(node_id) for node_id in known_node_ids} | set(info)
    for node_id in known:
        info.setdefault(node_id, {"node_id": node_id})
    return known, info


def _kept_confirmed(previous: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    kept = []
    for item in (previous or {}).get(key) or []:
        if item.get("status") != "confirmed":
            continue
        copied = dict(item)
        copied["status"] = "legacy_confirmed"
        copied["outside_current_snapshot"] = True
        kept.append(copied)
    return kept


def _client_mentioned(goal: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    identity = _stored_identity(goal)
    for raw in rows:
        name = str(raw.get("name") or "")
        scope = str(raw.get("business_object") or raw.get("scope") or "")
        if name and orchestrated_goal_identity(name, scope) == identity:
            return True
    return False


def _owner_client(client_identity: dict[str, str], identity: str) -> str:
    for client_id, stored in client_identity.items():
        if stored == identity:
            return client_id
    return ""


def _reject(
    kind: str,
    client_id: str,
    reason: str,
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    count_key: str,
) -> None:
    rejected_counts[count_key] += 1
    issues.append({"kind": kind, "client_id": client_id, "reason": reason})


def _creates_cycle(parents: dict[str, str], parent_id: str, child_id: str) -> bool:
    seen = {child_id}
    cursor: str | None = parent_id
    while cursor:
        if cursor in seen:
            return True
        seen.add(cursor)
        cursor = parents.get(cursor)
    return False


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
