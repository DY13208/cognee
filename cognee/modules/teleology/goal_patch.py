"""Incremental patch for an orchestrated AI Goal Model.

A patch updates only the objects named in the payload. Goals that are not
named stay as they are, including their parent. This module does not write
the company tree or the formal teleology graph.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from cognee.modules.teleology.goal_model import GoalBuildError
from cognee.modules.teleology.goal_network import analyze_feedback_loops, semantic_warnings
from cognee.modules.teleology.goal_orchestrated import (
    _CRITICAL,
    _accept_goal,
    _creates_cycle,
    _hierarchy_issue,
    _known_catalog,
    _reject,
    _relation_issue,
    _relation_polarity_warning,
    _stored_identity,
    _teleology_item,
    collect_node_ids,
    normalize_canonical_name,
    normalize_evidence,
    resolve_relation_endpoints,
)
from cognee.modules.teleology.goal_store import get_goal_store
from cognee.modules.teleology.graph_annotations import _authorized_dataset

PATCH_IMPACT_REPLACE_RATIO = 0.40
_PATCH_MODES = frozenset({"patch"})


def goal_source_ids(goal: dict[str, Any]) -> set[str]:
    found = {str(node_id) for node_id in goal.get("source_node_ids") or [] if str(node_id)}
    for entry in goal.get("evidence") or []:
        if isinstance(entry, dict) and str(entry.get("node_id") or ""):
            found.add(str(entry["node_id"]))
        elif isinstance(entry, str) and entry:
            found.add(entry)
    return found


def _in_snapshot(goal: dict[str, Any]) -> bool:
    if goal.get("status") in {"rejected", "legacy_confirmed"}:
        return False
    return not goal.get("outside_current_snapshot")


def analyze_goal_model_impact(
    model: dict[str, Any],
    changed_source_ids: list[str],
    *,
    impact_ratio: float = PATCH_IMPACT_REPLACE_RATIO,
) -> dict[str, Any]:
    """One hop from evidence hits. Parents and children are context, not a tree walk."""
    changed = {str(node_id) for node_id in changed_source_ids if str(node_id or "")}
    goals = [goal for goal in model.get("candidates") or [] if _in_snapshot(goal)]
    by_id = {str(goal.get("id") or ""): goal for goal in goals}
    direct = [
        str(goal.get("id") or "")
        for goal in goals
        if goal_source_ids(goal) & changed and str(goal.get("id") or "")
    ]
    direct_set = set(direct)
    context: list[str] = []
    for goal_id in direct:
        parent = str((by_id.get(goal_id) or {}).get("parent_candidate_id") or "")
        if parent and parent in by_id and parent not in direct_set and parent not in context:
            context.append(parent)
        for other in goals:
            other_id = str(other.get("id") or "")
            if other.get("parent_candidate_id") != goal_id:
                continue
            if other_id in direct_set or other_id in context:
                continue
            context.append(other_id)
    neighborhood = direct_set

    def touches(item: dict[str, Any]) -> bool:
        linked = {
            str(item.get("goal_id") or ""),
            str(item.get("source") or ""),
            str(item.get("target") or ""),
        }
        linked.discard("")
        return bool(linked & neighborhood)

    active = len(goals)
    ratio = (len(direct_set) / active) if active else 0.0
    return {
        "base_run_id": model.get("current_run_id") or model.get("run_id"),
        "model_version": int(model.get("model_version") or 1),
        "directly_impacted_goal_ids": direct,
        "context_goal_ids": context,
        "affected_purposes": [dict(item) for item in model.get("purposes") or [] if touches(item)],
        "affected_constraints": [
            dict(item) for item in model.get("constraints") or [] if touches(item)
        ],
        "affected_relations": [
            dict(item) for item in model.get("relations") or [] if touches(item)
        ],
        "recommend_full_replace": ratio > impact_ratio,
        "impact_ratio": ratio,
        "impact_goal_count": len(direct_set),
        "goal_count": active,
    }


def patch_idempotency_key(dataset_id: Any, payload: dict[str, Any]) -> str:
    supplied = str(payload.get("idempotency_key") or "").strip()
    if supplied:
        return supplied
    upserts = list(payload.get("upsert_goals") or [])
    if not upserts:
        upserts = list(payload.get("goals") or [])
    body = {
        "dataset_id": str(dataset_id),
        "base_run_id": str(payload.get("base_run_id") or ""),
        "submission_mode": "patch",
        "changed_source_ids": sorted(
            str(node_id) for node_id in payload.get("changed_source_ids") or [] if str(node_id)
        ),
        "remove_goal_ids": sorted(str(item) for item in payload.get("remove_goal_ids") or []),
        "affected_goal_ids": sorted(str(item) for item in payload.get("affected_goal_ids") or []),
        "upsert_goals": upserts,
        "hierarchy": list(payload.get("hierarchy") or []),
        "purposes": list(payload.get("purposes") or []),
        "constraints": list(payload.get("constraints") or []),
        "relations": list(payload.get("relations") or []),
        "source_revision": str(payload.get("source_revision") or ""),
        "generated_by": str(payload.get("generated_by") or "workbuddy_orchestrated"),
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compose_orchestrated_patch(
    dataset_id: Any,
    payload: dict[str, Any],
    *,
    known_node_ids: set[str],
    current: dict[str, Any] | None,
    catalog: dict[str, dict[str, Any]] | None = None,
    impact_ratio: float = PATCH_IMPACT_REPLACE_RATIO,
    run_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply one patch in memory. The caller decides whether to save it."""
    mode = str(payload.get("submission_mode") or "patch")
    if mode not in _PATCH_MODES:
        raise GoalBuildError("submission_mode must be patch")
    base_run_id = str(payload.get("base_run_id") or "")
    current_run_id = str(
        (current or {}).get("current_run_id") or (current or {}).get("run_id") or ""
    )
    if not current or base_run_id != current_run_id:
        summary = _empty_summary(status="stale_base", base_run_id=base_run_id)
        summary["current_run_id"] = current_run_id or None
        return {}, summary

    impact = analyze_goal_model_impact(
        current, list(payload.get("changed_source_ids") or []), impact_ratio=impact_ratio
    )
    if impact["recommend_full_replace"]:
        summary = _empty_summary(status="replace_required", base_run_id=base_run_id)
        summary["recommend_full_replace"] = True
        summary["impact"] = impact
        summary["current_run_id"] = current_run_id
        return {}, summary

    generated_by = str(payload.get("generated_by") or "workbuddy_orchestrated")
    run = run_id or str(uuid4())
    known, info = _known_catalog(known_node_ids, catalog)
    candidates = [copy.deepcopy(goal) for goal in current.get("candidates") or []]
    purposes = [copy.deepcopy(item) for item in current.get("purposes") or []]
    constraints = [copy.deepcopy(item) for item in current.get("constraints") or []]
    relations = [copy.deepcopy(item) for item in current.get("relations") or []]
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rejected_counts = {
        "goals": 0,
        "hierarchy": 0,
        "purposes": 0,
        "constraints": 0,
        "relations": 0,
    }
    added: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    retired: list[dict[str, Any]] = []
    hierarchy_changes: list[dict[str, Any]] = []
    purpose_changes: list[dict[str, Any]] = []
    constraint_changes: list[dict[str, Any]] = []
    relation_changes: list[dict[str, Any]] = []

    client_to_id = {
        str(goal.get("id") or ""): str(goal.get("id") or "")
        for goal in candidates
        if str(goal.get("id") or "")
    }
    upsert_rows = list(payload.get("upsert_goals") or [])
    if not upsert_rows:
        upsert_rows = list(payload.get("goals") or [])
    upserted_ids: list[str] = []
    for raw in upsert_rows:
        client_id = str(raw.get("client_id") or raw.get("candidate_id") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        existing = (
            next(
                (n for n in candidates if str(n.get("id")) == candidate_id and _in_snapshot(n)),
                None,
            )
            if candidate_id
            else None
        )
        if candidate_id and existing is None:
            _reject(
                "goal", client_id, "INVALID_EXISTING_CANDIDATE", rejected_counts, issues, "goals"
            )
            continue
        if existing is not None:
            defaults = {
                key: existing.get(key)
                for key in ("name", "description", "reason", "confidence", "scope", "node_type")
            }
            if not any(key in raw for key in ("evidence", "evidence_node_ids", "source_node_ids")):
                defaults["evidence"] = existing.get("evidence") or []
            raw = {**defaults, **raw}
            if raw.get("node_type") is None:
                raw["node_type"] = existing.get("node_type", "goal")
        sealed, issue = _accept_goal(dataset_id, raw, known, info, generated_by, run)
        if sealed is None:
            _reject("goal", client_id, issue or "invalid", rejected_counts, issues, "goals")
            continue
        collision = next(
            (
                n
                for n in candidates
                if _in_snapshot(n)
                and n is not existing
                and (
                    _stored_identity(n) == str(sealed["orchestrated_identity"])
                    or normalize_canonical_name(str(n.get("name") or ""))
                    == normalize_canonical_name(sealed["name"])
                )
            ),
            None,
        )
        if collision is not None and _in_snapshot(collision) and collision is not existing:
            _reject(
                "goal",
                client_id,
                "EXISTING_CANDIDATE_BINDING_REQUIRED",
                rejected_counts,
                issues,
                "goals",
            )
            continue
        if existing is None and any(str(n.get("id")) == str(sealed["id"]) for n in candidates):
            # A historical deterministic id must never overwrite a retained record.
            sealed["id"] = str(uuid4())
        if existing is None:
            sealed["status"] = "proposed"
            sealed["parent_candidate_id"] = None
            candidates.append(sealed)
            client_to_id[str(sealed["id"])] = str(sealed["id"])
            if client_id:
                client_to_id[client_id] = str(sealed["id"])
            upserted_ids.append(str(sealed["id"]))
            added.append({"id": sealed["id"], "name": sealed["name"]})
            continue
        _overwrite_goal_fields(existing, sealed, raw)
        if client_id:
            client_to_id[client_id] = str(existing["id"])
        client_to_id[str(existing["id"])] = str(existing["id"])
        upserted_ids.append(str(existing["id"]))
        updated.append({"id": existing["id"], "name": existing["name"]})

    removed_ids = _remove_goals(
        candidates,
        purposes,
        constraints,
        relations,
        list(payload.get("remove_goal_ids") or []),
        client_to_id,
        retired,
        issues,
        rejected_counts,
        hierarchy_changes,
    )
    mutable = _mutable_goal_ids(
        payload, impact, candidates, upserted_ids, removed_ids, client_to_id
    )
    _apply_patch_hierarchy(
        list(payload.get("hierarchy") or []),
        candidates,
        client_to_id,
        mutable,
        known,
        info,
        rejected_counts,
        issues,
        hierarchy_changes,
    )
    _apply_patch_bound(
        list(payload.get("purposes") or []),
        kind="purpose",
        bucket=purposes,
        count_key="purposes",
        client_to_id=client_to_id,
        mutable=mutable,
        known=known,
        catalog=info,
        run_id=run,
        generated_by=generated_by,
        rejected_counts=rejected_counts,
        issues=issues,
        changes=purpose_changes,
    )
    _apply_patch_bound(
        list(payload.get("constraints") or []),
        kind="constraint",
        bucket=constraints,
        count_key="constraints",
        client_to_id=client_to_id,
        mutable=mutable,
        known=known,
        catalog=info,
        run_id=run,
        generated_by=generated_by,
        rejected_counts=rejected_counts,
        issues=issues,
        changes=constraint_changes,
    )
    goal_names = {
        client_id: str((_by_id(candidates).get(candidate_id) or {}).get("name") or "")
        for client_id, candidate_id in client_to_id.items()
    }
    _apply_patch_relations(
        resolve_relation_endpoints(
            list(payload.get("relations") or []),
            client_to_id,
            candidates,
            existing_candidate_ids={
                str(n["id"]) for n in current.get("candidates") or [] if _in_snapshot(n)
            },
        ),
        relations,
        client_to_id,
        mutable,
        known,
        info,
        run,
        generated_by,
        rejected_counts,
        issues,
        warnings,
        goal_names,
        relation_changes,
    )
    warnings.extend(semantic_warnings(candidates, relations))
    changed_ids = {item["id"] for item in added + updated + retired}
    unchanged = [
        {"id": goal["id"], "name": goal.get("name")}
        for goal in candidates
        if _in_snapshot(goal) and str(goal.get("id") or "") not in changed_ids
    ]
    critical = [issue for issue in issues if issue.get("reason") in _CRITICAL]
    valid = not critical
    source_revision = str(payload.get("source_revision") or "")
    summary = {
        "run_id": run,
        "status": "completed" if valid else "validation_failed",
        "mode": "orchestrated",
        "submission_mode": "patch",
        "valid": valid,
        "saved": False,
        "base_run_id": base_run_id,
        "previous_run_id": current_run_id,
        "current_run_id": run,
        "model_version": int(current.get("model_version") or 1) + 1,
        "changed_source_ids": list(payload.get("changed_source_ids") or []),
        "affected_goal_ids": sorted(mutable),
        "added_goal_ids": [item["id"] for item in added],
        "updated_goal_ids": [item["id"] for item in updated],
        "retired_goal_ids": [item["id"] for item in retired],
        "unchanged_goal_count": len(unchanged),
        "added_goals": added,
        "updated_goals": updated,
        "retired_goals": retired,
        "unchanged_goals": unchanged,
        "hierarchy_changes": hierarchy_changes,
        "purpose_changes": purpose_changes,
        "constraint_changes": constraint_changes,
        "relation_changes": relation_changes,
        "issues": issues,
        "warnings": warnings,
        "critical_errors": critical,
        "rejected": dict(rejected_counts),
        "recommend_full_replace": False,
        "source_revision": source_revision,
        "generated_by": generated_by,
        "committed": False,
        "graph_committed": False,
        "impact": impact,
    }
    active = [goal for goal in candidates if goal.get("status") != "rejected"]
    model = {
        "run_id": run,
        "dataset_id": str(dataset_id),
        "mode": "orchestrated",
        "status": "completed",
        "stage": "completed",
        "submission_mode": "patch",
        "generated_by": generated_by,
        "current_run_id": run,
        "model_version": summary["model_version"],
        "base_run_id": base_run_id,
        "previous_run_id": current_run_id,
        "changed_source_ids": list(payload.get("changed_source_ids") or []),
        "affected_goal_ids": sorted(mutable),
        "added_goal_ids": summary["added_goal_ids"],
        "updated_goal_ids": summary["updated_goal_ids"],
        "retired_goal_ids": summary["retired_goal_ids"],
        "unchanged_goal_count": len(unchanged),
        "source_revision": source_revision,
        "last_source_revision": source_revision,
        "committed": False,
        "graph_committed": False,
        "source_count": len(
            {node for goal in active for node in goal.get("source_node_ids") or []}
        ),
        "canonical_goal_count": len([goal for goal in active if _in_snapshot(goal)]),
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
        "summary": summary,
    }
    if not valid:
        summary["status"] = "validation_failed"
    summary["resolved_client_ids"] = dict(client_to_id)
    summary["relations_preview"] = [dict(edge) for edge in relations]
    summary["loop_preview"] = analyze_feedback_loops(summary["relations_preview"], nodes=candidates)
    return model, summary


async def submit_orchestrated_patch(
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
    impact_ratio: float = PATCH_IMPACT_REPLACE_RATIO,
) -> dict[str, Any]:
    """Validate one patch. strict failure, stale base, and oversized impact do not write."""
    mode = str(submission_mode or payload.get("submission_mode") or "patch")
    if mode != "patch":
        raise GoalBuildError("submission_mode must be patch")
    preview_only = bool(payload.get("dry_run") if dry_run is None else dry_run)
    enforce = True if strict is None else bool(strict)
    if "strict" in payload and strict is None:
        enforce = bool(payload.get("strict"))
    await _authorized_dataset(dataset_id, user, "write")
    body = dict(payload)
    body["submission_mode"] = "patch"
    if known_node_ids is None:
        loaded = await _load_catalog(dataset_id, user, body)
        known_node_ids = set(loaded)
        catalog = {**loaded, **(catalog or {})}
    goal_store = store if store is not None else get_goal_store()
    current = await goal_store.get_dataset(dataset_id)
    key = patch_idempotency_key(dataset_id, body)
    if not preview_only:
        previous = await goal_store.find_idempotent(dataset_id, key)
        if previous:
            return _replay(previous, key)
    model, summary = compose_orchestrated_patch(
        dataset_id,
        body,
        known_node_ids=known_node_ids,
        current=current,
        catalog=catalog,
        impact_ratio=impact_ratio,
    )
    summary["dry_run"] = preview_only
    summary["strict"] = enforce
    summary["idempotency_key"] = key
    summary["saved"] = False
    if summary["status"] in {"stale_base", "replace_required"}:
        summary["run_id"] = None
        return summary
    if preview_only:
        summary["run_id"] = None
        summary["status"] = "validated" if summary["valid"] else "validation_failed"
        return summary
    if enforce and not summary["valid"]:
        summary["run_id"] = None
        summary["status"] = "validation_failed"
        return summary
    model["idempotency_key"] = key
    model["summary"] = summary
    await goal_store.save_result(model)
    from cognee.modules.teleology.goal_model import STORE

    STORE.save(model)
    summary["saved"] = True
    summary["status"] = "completed"
    summary["run_id"] = model["run_id"]
    return summary


async def read_goal_model_impact(
    dataset_id: UUID,
    user: Any,
    changed_source_ids: list[str],
    *,
    store: Any = None,
    impact_ratio: float = PATCH_IMPACT_REPLACE_RATIO,
) -> dict[str, Any]:
    """Read which goals a source change touches. This does not write."""
    await _authorized_dataset(dataset_id, user, "read")
    goal_store = store if store is not None else get_goal_store()
    current = await goal_store.get_dataset(dataset_id)
    if not current:
        return {
            "base_run_id": None,
            "model_version": None,
            "directly_impacted_goal_ids": [],
            "context_goal_ids": [],
            "affected_purposes": [],
            "affected_constraints": [],
            "affected_relations": [],
            "recommend_full_replace": False,
        }
    return analyze_goal_model_impact(
        current, list(changed_source_ids or []), impact_ratio=impact_ratio
    )


async def _load_catalog(dataset_id: UUID, user: Any, payload: dict[str, Any]) -> dict[str, Any]:
    from cognee.modules.teleology.goal_orchestrated import load_node_catalog

    return await load_node_catalog(dataset_id, user, collect_node_ids(payload))


def _replay(previous: dict[str, Any], key: str) -> dict[str, Any]:
    summary = dict(previous.get("summary") or {})
    summary["saved"] = True
    summary["dry_run"] = False
    summary["run_id"] = previous.get("run_id")
    summary["idempotency_key"] = key
    summary["idempotent_replay"] = True
    summary["status"] = previous.get("status") or summary.get("status") or "completed"
    summary.setdefault("base_run_id", previous.get("base_run_id"))
    summary.setdefault("submission_mode", "patch")
    return summary


def _empty_summary(*, status: str, base_run_id: str) -> dict[str, Any]:
    return {
        "run_id": None,
        "status": status,
        "mode": "orchestrated",
        "submission_mode": "patch",
        "valid": False,
        "saved": False,
        "base_run_id": base_run_id or None,
        "added_goals": [],
        "updated_goals": [],
        "retired_goals": [],
        "unchanged_goals": [],
        "hierarchy_changes": [],
        "purpose_changes": [],
        "constraint_changes": [],
        "relation_changes": [],
        "issues": [],
        "warnings": [],
        "loop_preview": [],
        "critical_errors": [],
        "recommend_full_replace": False,
        "committed": False,
        "graph_committed": False,
    }


def _overwrite_goal_fields(
    existing: dict[str, Any], sealed: dict[str, Any], raw: dict[str, Any]
) -> None:
    status = _kept_status(existing, raw)
    existing["name"] = sealed["name"]
    existing["node_type"] = sealed.get("node_type", "goal")
    existing["evidence_node_ids"] = list(sealed.get("evidence_node_ids") or [])
    existing["description"] = sealed.get("description") or ""
    existing["reason"] = sealed.get("reason") or ""
    existing["confidence"] = sealed.get("confidence")
    existing["evidence"] = list(sealed.get("evidence") or [])
    existing["source_node_ids"] = list(sealed.get("source_node_ids") or [])
    existing["semantic_hash"] = sealed.get("semantic_hash")
    existing["orchestrated_identity"] = sealed.get("orchestrated_identity")
    existing["scope"] = sealed.get("scope") or ""
    existing["status"] = status
    restore = bool(raw.get("reopen")) and str(raw.get("status") or "") == "proposed"
    if restore:
        existing["outside_current_snapshot"] = False
        existing["retirement_proposed"] = False


def _kept_status(existing: dict[str, Any], raw: dict[str, Any]) -> str:
    status = str(existing.get("status") or "proposed")
    reopen = bool(raw.get("reopen")) and str(raw.get("status") or "") == "proposed"
    if reopen and status in {"confirmed", "rejected", "legacy_confirmed"}:
        return "proposed"
    if status == "legacy_confirmed":
        return status
    if status in {"confirmed", "rejected"}:
        return status
    return "proposed"


def _remove_goals(
    candidates: list[dict[str, Any]],
    purposes: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    remove_ids: list[str],
    client_to_id: dict[str, str],
    retired: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    rejected_counts: dict[str, int],
    hierarchy_changes: list[dict[str, Any]],
) -> list[str]:
    removed: list[str] = []
    by_id = _by_id(candidates)
    for token in remove_ids:
        goal_id = client_to_id.get(str(token), str(token))
        goal = by_id.get(goal_id)
        if goal is None:
            _reject("goal", str(token), "missing_goal", rejected_counts, issues, "goals")
            continue
        if goal.get("status") == "confirmed" or goal.get("status") == "legacy_confirmed":
            goal["status"] = "confirmed"
            goal["outside_current_snapshot"] = True
            goal["retirement_proposed"] = True
            retired.append(
                {
                    "id": goal_id,
                    "name": goal.get("name"),
                    "retirement_proposed": True,
                }
            )
            removed.append(goal_id)
            continue
        if not _in_snapshot(goal):
            continue
        candidates[:] = [item for item in candidates if str(item.get("id") or "") != goal_id]
        by_id.pop(goal_id, None)
        _drop_linked(purposes, constraints, relations, goal_id)
        for child in candidates:
            if str(child.get("parent_candidate_id") or "") == goal_id:
                previous = child.get("parent_candidate_id")
                child["parent_candidate_id"] = None
                hierarchy_changes.append(
                    {
                        "child_id": child.get("id"),
                        "previous_parent_id": previous,
                        "parent_id": None,
                        "reason": "removed_parent",
                    }
                )
        retired.append({"id": goal_id, "name": goal.get("name"), "retirement_proposed": False})
        removed.append(goal_id)
    return removed


def _drop_linked(
    purposes: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    goal_id: str,
) -> None:
    def linked(item: dict[str, Any]) -> bool:
        return goal_id in {
            str(item.get("goal_id") or ""),
            str(item.get("source") or ""),
            str(item.get("target") or ""),
        }

    purposes[:] = [item for item in purposes if not linked(item)]
    constraints[:] = [item for item in constraints if not linked(item)]
    relations[:] = [item for item in relations if not linked(item)]


def _mutable_goal_ids(
    payload: dict[str, Any],
    impact: dict[str, Any],
    candidates: list[dict[str, Any]],
    upserted_ids: list[str],
    removed_ids: list[str],
    client_to_id: dict[str, str],
) -> set[str]:
    explicit = [str(item) for item in payload.get("affected_goal_ids") or [] if str(item)]
    if explicit:
        resolved = {client_to_id.get(token, token) for token in explicit}
    else:
        direct = set(impact.get("directly_impacted_goal_ids") or [])
        children = {
            str(goal.get("id") or "")
            for goal in candidates
            if _in_snapshot(goal) and str(goal.get("parent_candidate_id") or "") in direct
        }
        resolved = set(direct) | children
    resolved |= {str(item) for item in upserted_ids}
    resolved |= {str(item) for item in removed_ids}
    resolved.discard("")
    return resolved


def _apply_patch_hierarchy(
    links: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    client_to_id: dict[str, str],
    mutable: set[str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> None:
    by_id = {str(goal["id"]): goal for goal in candidates if _in_snapshot(goal)}
    parents = {
        goal_id: str(goal.get("parent_candidate_id") or "")
        for goal_id, goal in by_id.items()
        if goal.get("parent_candidate_id")
    }
    assigned: set[str] = set()
    for raw in links:
        parent_client = str(raw.get("parent_client_id") or "")
        child_client = str(raw.get("child_client_id") or "")
        reason = _hierarchy_issue(raw, parent_client, child_client, client_to_id, known, catalog)
        parent_id = client_to_id.get(parent_client)
        child_id = client_to_id.get(child_client)
        if reason == "" and (
            not parent_id or not child_id or parent_id not in by_id or child_id not in by_id
        ):
            reason = "missing_endpoint"
        if reason == "" and child_id not in mutable:
            reason = "outside_patch_scope"
        if reason == "" and parent_id and child_id and parent_id == child_id:
            reason = "self_parent"
        if reason == "" and child_id in assigned:
            reason = "multiple_parents"
        if (
            reason == ""
            and parent_id
            and child_id
            and _creates_cycle(
                {key: value for key, value in parents.items() if key != child_id},
                parent_id,
                child_id,
            )
        ):
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
            continue
        assert parent_id is not None and child_id is not None
        previous = by_id[child_id].get("parent_candidate_id")
        by_id[child_id]["parent_candidate_id"] = parent_id
        parents[child_id] = parent_id
        assigned.add(child_id)
        if previous != parent_id:
            changes.append(
                {
                    "child_id": child_id,
                    "previous_parent_id": previous,
                    "parent_id": parent_id,
                }
            )


def _apply_patch_bound(
    rows: list[dict[str, Any]],
    *,
    kind: str,
    bucket: list[dict[str, Any]],
    count_key: str,
    client_to_id: dict[str, str],
    mutable: set[str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    run_id: str,
    generated_by: str,
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> None:
    from cognee.modules.teleology.goal_orchestrated import _bound_issue, _confidence

    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("goal_client_id") or "")
        goal_client = str(raw.get("goal_client_id") or "")
        evidence, source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
        reason = _bound_issue(raw, goal_client, client_to_id, evidence_issue)
        goal_id = client_to_id.get(goal_client)
        if reason == "" and goal_id not in mutable:
            reason = "outside_patch_scope"
        if reason:
            _reject(kind, client_id or goal_client, reason, rejected_counts, issues, count_key)
            continue
        assert goal_id is not None
        name = str(raw.get("name") or "").strip()
        existing = next(
            (
                item
                for item in bucket
                if str(item.get("goal_id") or "") == goal_id and str(item.get("name") or "") == name
            ),
            None,
        )
        if existing is None:
            item = _teleology_item(
                run_id,
                kind=kind,
                goal_id=goal_id,
                name=name,
                reason=str(raw.get("reason") or "").strip(),
                confidence=_confidence(raw.get("confidence")),
                evidence=evidence,
                source_node_ids=source_ids,
                generated_by=generated_by,
            )
            bucket.append(item)
            changes.append({"id": item["id"], "goal_id": goal_id, "name": name, "change": "added"})
            continue
        existing["reason"] = str(raw.get("reason") or "").strip()
        existing["confidence"] = _confidence(raw.get("confidence"))
        existing["evidence"] = evidence
        existing["source_node_ids"] = source_ids
        changes.append(
            {"id": existing.get("id"), "goal_id": goal_id, "name": name, "change": "updated"}
        )


def _apply_patch_relations(
    rows: list[dict[str, Any]],
    bucket: list[dict[str, Any]],
    client_to_id: dict[str, str],
    mutable: set[str],
    known: set[str],
    catalog: dict[str, dict[str, Any]],
    run_id: str,
    generated_by: str,
    rejected_counts: dict[str, int],
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    goal_names: dict[str, str],
    changes: list[dict[str, Any]],
) -> None:
    from cognee.modules.teleology.goal_orchestrated import _confidence

    for raw in rows:
        client_id = str(raw.get("client_id") or raw.get("source_client_id") or "")
        evidence, source_ids, evidence_issue = normalize_evidence(raw, known, catalog)
        reason = _relation_issue(raw, client_to_id, evidence_issue)
        source_client = str(raw.get("source_client_id") or "")
        target_client = str(raw.get("target_client_id") or "")
        source_id = client_to_id.get(source_client)
        target_id = client_to_id.get(target_client)
        if reason == "" and source_id not in mutable and target_id not in mutable:
            reason = "outside_patch_scope"
        if reason:
            _reject("relation", client_id, reason, rejected_counts, issues, "relations")
            continue
        assert source_id is not None and target_id is not None
        relationship = str(raw.get("relationship") or "").strip().lower()
        warning = _relation_polarity_warning(
            relationship,
            goal_names.get(source_client, ""),
            goal_names.get(target_client, ""),
        )
        if warning:
            warnings.append(
                {
                    "kind": "relation",
                    "client_id": client_id,
                    "reason": warning,
                    "relationship": relationship,
                    "source_client_id": source_client,
                    "target_client_id": target_client,
                }
            )
        existing = next(
            (
                item
                for item in bucket
                if str(item.get("source") or "") == source_id
                and str(item.get("target") or "") == target_id
                and str(item.get("relationship") or "") == relationship
            ),
            None,
        )
        if existing is None:
            item = _teleology_item(
                run_id,
                kind="relation",
                relationship=relationship,
                condition=raw.get("condition"),
                evidence_node_ids=source_ids,
                source=source_id,
                target=target_id,
                goal_id=source_id,
                name=relationship,
                reason=str(raw.get("reason") or "").strip(),
                confidence=_confidence(raw.get("confidence")),
                evidence=evidence,
                source_node_ids=source_ids,
                generated_by=generated_by,
            )
            bucket.append(item)
            changes.append(
                {
                    "id": item["id"],
                    "source": source_id,
                    "target": target_id,
                    "relationship": relationship,
                    "change": "added",
                }
            )
            continue
        existing["reason"] = str(raw.get("reason") or "").strip()
        existing["confidence"] = _confidence(raw.get("confidence"))
        existing["evidence"] = evidence
        existing["source_node_ids"] = source_ids
        if "condition" in raw:
            existing["condition"] = raw["condition"]
        existing["evidence_node_ids"] = source_ids
        existing["relationship"] = relationship
        changes.append(
            {
                "id": existing.get("id"),
                "source": source_id,
                "target": target_id,
                "relationship": relationship,
                "change": "updated",
            }
        )


def _by_id(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(goal.get("id") or ""): goal for goal in candidates if str(goal.get("id") or "")}
