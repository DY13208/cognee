"""Derived AI Goal Model. The company tree stays a fact layer and is only evidence.

Dataset content is classified, then goals are extracted, canonicalized, and
arranged by business-result specificity. Purpose, constraint, and
serves/advances/blocks are inferred only for those canonical goals.

Every stage receives a batch. A run stores proposals. It does not write the
company tree and it does not commit teleology.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

SOURCE_CLASSES = (
    "Goal",
    "Project",
    "Metric",
    "Process",
    "Responsibility",
    "Document",
    "Entity",
    "Constraint",
    "Reference",
    "Other",
)
STAGES = (
    "discovering",
    "classifying",
    "extracting_goals",
    "canonicalizing",
    "building_hierarchy",
    "inferring_teleology",
    "completed",
)
CANDIDATE_STATUSES = ("proposed", "confirmed", "rejected")
_ACTIVE = frozenset({"proposed", "confirmed"})
_NAMESPACE = uuid5(NAMESPACE_URL, "cognee:teleology:ai-goal-model")
_BRAND = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_RESPONSIBILITY = ("责任分工", "职责分工", "岗位职责")
_METRIC = ("利润分", "利润率", "指标")
_PROCESS = ("流程", "工序", "审批流")
_OUTCOME = ("提升", "提高", "达成", "实现")
_OUTCOME_OBJECT = ("能力", "目标", "盈利", "利润")
_ACCURACY = ("核算", "准确性")
_PROFIT = ("利润", "盈利")


class GoalBuildError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class MemoryGoalModelStore:
    """Process-local derived layer. Confirming a candidate does not write the graph."""

    def __init__(self) -> None:
        self._by_dataset: dict[str, dict[str, Any]] = {}
        self._by_run: dict[str, dict[str, Any]] = {}

    def save(self, result: dict[str, Any]) -> dict[str, Any]:
        stored = dict(result)
        stored["committed"] = False
        stored["graph_committed"] = False
        self._by_dataset[str(stored["dataset_id"])] = stored
        self._by_run[str(stored["run_id"])] = stored
        return stored

    def get_dataset(self, dataset_id: Any) -> dict[str, Any] | None:
        return self._by_dataset.get(str(dataset_id))

    def get_run(self, run_id: Any) -> dict[str, Any] | None:
        return self._by_run.get(str(run_id))

    def clear(self) -> None:
        self._by_dataset.clear()
        self._by_run.clear()


STORE = MemoryGoalModelStore()


def clamp_goal_batch(value: int | None) -> int:
    try:
        number = int(20 if value is None else value)
    except (TypeError, ValueError):
        number = 20
    return min(100, max(1, number))


def classify_source(node: dict[str, Any]) -> str:
    """Classify one dataset object. A company-tree Goal type is not a Goal."""
    name = str(node.get("name") or "")
    text = " ".join(
        (
            name,
            str(node.get("text") or ""),
            str(node.get("description") or ""),
        )
    )
    graph_type = str(node.get("type") or "")
    layer = str(node.get("layer") or "")
    kind = str(node.get("cpd_kind") or "")
    if any(token in text for token in _RESPONSIBILITY):
        return "Responsibility"
    if any(token in name for token in _METRIC):
        return "Metric"
    if graph_type == "Document" or layer == "document":
        return "Document"
    if graph_type == "Constraint" or "约束" in name or "限制" in name:
        return "Constraint"
    if kind == "map_reference" or "参考" in name:
        return "Reference"
    if graph_type in {"Entity", "Person", "Organization"} or layer == "entity":
        return "Entity"
    if any(token in name for token in _PROCESS):
        return "Process"
    if any(token in text for token in _OUTCOME) and any(token in text for token in _OUTCOME_OBJECT):
        return "Goal"
    if name.endswith("项目") or ("项目" in name and "利润" not in name and "目标" not in name):
        return "Project"
    return "Other"


def semantic_hash(name: str) -> str:
    folded = _fold(name)
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def candidate_id(dataset_id: Any, name: str) -> str:
    return str(uuid5(_NAMESPACE, f"{dataset_id}:{semantic_hash(name)}"))


def run_goal_build(
    dataset_id: Any,
    sources: list[dict[str, Any]],
    *,
    mode: str = "baseline",
    batch_size: int = 20,
    concurrency: int = 1,
    max_sources: int | None = None,
    generated_by: str = "dataset_goal_build",
    model: Any = None,
    previous: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run every stage on batches. The result is proposals only."""
    if mode not in {"baseline", "incremental"}:
        raise GoalBuildError("mode must be baseline or incremental")
    size = clamp_goal_batch(batch_size)
    chosen = list(sources or [])
    if max_sources is not None:
        chosen = chosen[: max(0, int(max_sources))]
    payloads: list[int] = []
    run_id = str(uuid4())

    for batch in _chunks(chosen, size):
        payloads.append(len(batch))

    classified: list[dict[str, Any]] = []
    for batch in _chunks(chosen, size):
        payloads.append(len(batch))
        labels = _classify_batch(batch, model)
        for node, label in zip(batch, labels):
            classified.append(_compact(node, label))

    index = _index(classified)
    extracted: list[dict[str, Any]] = []
    rejected_empty = 0
    for batch in _chunks(index["Project"], size):
        payloads.append(len(batch))
        raw_items = model.extract(batch) if model is not None else extract_candidates(batch, index)
        for raw in raw_items or []:
            valid = _validated(raw, dataset_id, generated_by)
            if valid is None:
                rejected_empty += 1
            else:
                extracted.append(valid)

    canonical = canonicalize(extracted, dataset_id, generated_by)
    combined = _apply_mode(previous or [], canonical, mode)
    hierarchical = build_hierarchy(combined)
    for goal in hierarchical:
        goal["dataset_id"] = str(dataset_id)
        goal["run_id"] = run_id
        goal["generated_by"] = goal.get("generated_by") or generated_by
    teleology = infer_teleology(hierarchical, run_id)
    return {
        "run_id": run_id,
        "dataset_id": str(dataset_id),
        "mode": mode,
        "status": "completed",
        "stage": "completed",
        "stages": list(STAGES),
        "committed": False,
        "graph_committed": False,
        "batch_size": size,
        "concurrency": max(1, int(concurrency or 1)),
        "max_sources": max_sources,
        "max_batch_payload": max(payloads) if payloads else 0,
        "source_count": len(chosen),
        "rejected_empty": rejected_empty,
        "candidates": hierarchical,
        "teleology": teleology,
        "classifications": [
            {
                "id": row["id"],
                "name": row["name"],
                "source_class": row["source_class"],
                "layer": row.get("layer") or "",
            }
            for row in classified
        ],
    }


def extract_candidates(
    projects: list[dict[str, Any]], index: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Create outcome goals from project and metric evidence. Directories are not goals."""
    found: list[dict[str, Any]] = []
    for project in projects:
        if project.get("source_class") != "Project":
            continue
        related = _related_evidence(project, index)
        profit = [
            row
            for row in related
            if row.get("source_class") == "Metric" and _is_profit(row) and not _is_accuracy(row)
        ]
        accuracy = [
            row for row in related if row.get("source_class") == "Metric" and _is_accuracy(row)
        ]
        support = [row for row in related if row.get("source_class") in {"Document", "Constraint"}]
        anchor = _anchor(str(project.get("name") or "")) or "项目"
        if profit:
            found.append(
                _draft(
                    name=f"提升 {anchor} 项目盈利能力",
                    description="由项目与利润指标综合得到的业务结果。",
                    confidence=0.72,
                    reason=(
                        f"项目「{project.get('name')}」与利润指标"
                        f"「{'、'.join(str(row.get('name') or '') for row in profit)}」"
                        "一起指向盈利结果。目录节点没有进入目标树。"
                    ),
                    rows=[project, *profit, *support],
                )
            )
        if accuracy:
            found.append(
                _draft(
                    name=f"提高 {anchor} 项目利润核算准确性",
                    description="盈利结果下更具体的核算结果。",
                    confidence=0.68,
                    reason=(
                        f"指标「{'、'.join(str(row.get('name') or '') for row in accuracy)}」"
                        f"把「{project.get('name')}」收窄到利润核算。"
                    ),
                    rows=[project, *accuracy],
                )
            )
    return found


def canonicalize(
    candidates: list[dict[str, Any]], dataset_id: Any, generated_by: str
) -> list[dict[str, Any]]:
    """Merge near-synonym goals and keep every source id."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        groups[_merge_key(candidate)].append(candidate)
    merged: list[dict[str, Any]] = []
    for items in groups.values():
        evidence: list[dict[str, Any]] = []
        source_ids: list[str] = []
        seen: set[str] = set()
        reasons: list[str] = []
        confidence = 0.0
        for item in items:
            confidence = max(confidence, float(item.get("confidence") or 0))
            reason = str(item.get("reason") or "").strip()
            if reason and reason not in reasons:
                reasons.append(reason)
            for entry in item.get("evidence") or []:
                node_id = str(entry.get("node_id") or "")
                if not node_id or node_id in seen:
                    continue
                seen.add(node_id)
                source_ids.append(node_id)
                evidence.append(entry)
        if not source_ids or not evidence:
            continue
        name = _canonical_name(items, evidence)
        merged.append(
            _seal(
                dataset_id,
                name=name,
                description=str(items[0].get("description") or ""),
                confidence=confidence,
                reason=" ".join(reasons),
                source_node_ids=source_ids,
                evidence=evidence,
                generated_by=generated_by,
            )
        )
    return merged


def build_hierarchy(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parent a goal only when another goal is the broader business result.

    A company-tree directory parent is not a goal parent.
    """
    copied = [_without_tree_parent(dict(goal)) for goal in goals]
    active = [goal for goal in copied if goal.get("status") in _ACTIVE]
    for goal in copied:
        goal["parent_candidate_id"] = None
    for child in active:
        parent = _broader(child, active)
        if parent is not None:
            child["parent_candidate_id"] = parent["id"]
    return copied


def infer_teleology(goals: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    """Purpose, constraint, and relations for canonical goals only."""
    by_id = {goal["id"]: goal for goal in goals if goal.get("status") in _ACTIVE}
    purposes: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for goal in by_id.values():
        if not goal.get("evidence") or not goal.get("source_node_ids"):
            continue
        purposes.append(
            _teleology_item(
                run_id,
                kind="purpose",
                goal_id=goal["id"],
                name=f"实现「{goal['name']}」",
                reason=str(goal.get("reason") or ""),
                confidence=min(float(goal.get("confidence") or 0), 0.7),
                evidence=list(goal["evidence"]),
                source_node_ids=list(goal["source_node_ids"]),
            )
        )
        for entry in goal["evidence"]:
            if entry.get("source_class") != "Constraint":
                continue
            constraints.append(
                _teleology_item(
                    run_id,
                    kind="constraint",
                    goal_id=goal["id"],
                    name=str(entry.get("name") or "约束"),
                    reason=f"约束来自证据节点 {entry.get('node_id')}。",
                    confidence=0.66,
                    evidence=[entry],
                    source_node_ids=[str(entry.get("node_id") or "")],
                )
            )
        parent_id = goal.get("parent_candidate_id")
        parent = by_id.get(parent_id)
        if parent is None:
            continue
        beyond = [
            node_id
            for node_id in goal.get("source_node_ids") or []
            if node_id not in set(parent.get("source_node_ids") or [])
        ]
        if not beyond:
            continue
        relations.append(
            _teleology_item(
                run_id,
                kind="relation",
                relationship="advances",
                source=goal["id"],
                target=parent["id"],
                goal_id=goal["id"],
                name="advances",
                reason="更具体的业务结果推进上一级业务结果，依据超出两端目标自身的证据。",
                confidence=0.64,
                evidence=[
                    entry for entry in goal["evidence"] if entry.get("node_id") in set(beyond)
                ],
                source_node_ids=beyond,
            )
        )
    return {
        "purposes": purposes,
        "constraints": constraints,
        "relations": relations,
        "committed": False,
    }


def goal_model_view(dataset_id: Any) -> dict[str, Any]:
    saved = STORE.get_dataset(dataset_id)
    if saved is None:
        return {
            "dataset_id": str(dataset_id),
            "run_id": None,
            "status": "empty",
            "stage": "empty",
            "committed": False,
            "graph_committed": False,
            "candidates": [],
            "hierarchy": [],
            "purposes": [],
            "constraints": [],
            "relations": [],
            "classifications": [],
        }
    return _public(saved)


def set_candidate_status(dataset_id: Any, candidate_id: str, status: str) -> dict[str, Any]:
    """Record a review decision on the derived layer. This does not commit."""
    return _set_status(dataset_id, candidate_id, status, bucket="candidates")


def set_teleology_status(dataset_id: Any, item_id: str, status: str, kind: str) -> dict[str, Any]:
    bucket = {"purpose": "purposes", "constraint": "constraints", "relation": "relations"}.get(kind)
    if bucket is None:
        raise GoalBuildError("kind must be purpose, constraint, or relation")
    return _set_status(dataset_id, item_id, status, bucket=bucket)


def list_canonical_goal_ids(dataset_id: Any) -> list[str]:
    saved = STORE.get_dataset(dataset_id)
    if saved is None:
        return []
    return [
        str(goal["id"])
        for goal in saved.get("candidates") or []
        if goal.get("status") in _ACTIVE and goal.get("evidence") and goal.get("source_node_ids")
    ]


def canonical_context(dataset_id: Any, goal_id: str) -> dict[str, Any] | None:
    goal = _find_candidate(dataset_id, goal_id)
    if goal is None:
        return None
    return {
        "goal": {
            "id": goal["id"],
            "name": goal["name"],
            "description": goal.get("description") or "",
        },
        "entities": list(goal.get("evidence") or []),
        "documents": [
            entry for entry in goal.get("evidence") or [] if entry.get("source_class") == "Document"
        ],
        "note": goal.get("reason") or "",
        "context_hash": goal.get("semantic_hash"),
        "source": "ai_goal_model",
    }


def incremental_teleology_proposal(
    dataset_id: Any, goal_id: str, run_id: str
) -> dict[str, Any] | None:
    """Coverage reads an existing canonical goal and only refreshes proposals."""
    saved = STORE.get_dataset(dataset_id)
    goal = _find_candidate(dataset_id, goal_id)
    if saved is None or goal is None:
        return None
    teleology = saved.setdefault(
        "teleology",
        {"purposes": [], "constraints": [], "relations": [], "committed": False},
    )
    if not _items_for_goal(teleology, goal_id):
        fresh = infer_teleology([goal], str(saved.get("run_id") or run_id))
        for bucket in ("purposes", "constraints", "relations"):
            teleology.setdefault(bucket, []).extend(fresh[bucket])
        teleology["committed"] = False
        saved["committed"] = False
        saved["graph_committed"] = False
    items = _items_for_goal(teleology, goal_id)
    return {
        "id": str(uuid5(_NAMESPACE, f"coverage:{dataset_id}:{goal_id}")),
        "dataset_id": str(dataset_id),
        "source_goal_id": goal_id,
        "status": "open",
        "run_id": run_id,
        "items": items,
        "generated_by": "coverage_on_goal_model",
        "graph_committed": False,
    }


def _public(saved: dict[str, Any]) -> dict[str, Any]:
    candidates = list(saved.get("candidates") or [])
    teleology = saved.get("teleology") or {}
    return {
        "dataset_id": saved.get("dataset_id"),
        "run_id": saved.get("run_id"),
        "mode": saved.get("mode"),
        "status": saved.get("status"),
        "stage": saved.get("stage"),
        "stages": list(saved.get("stages") or []),
        "committed": False,
        "graph_committed": False,
        "batch_size": saved.get("batch_size"),
        "source_count": saved.get("source_count"),
        "max_batch_payload": saved.get("max_batch_payload"),
        "candidates": candidates,
        "hierarchy": [
            {
                "id": goal["id"],
                "name": goal["name"],
                "parent_candidate_id": goal.get("parent_candidate_id"),
                "status": goal.get("status"),
                "confidence": goal.get("confidence"),
                "evidence_count": len(goal.get("evidence") or []),
            }
            for goal in candidates
            if goal.get("status") != "rejected"
        ],
        "purposes": list(teleology.get("purposes") or []),
        "constraints": list(teleology.get("constraints") or []),
        "relations": list(teleology.get("relations") or []),
        "classifications": _classification_sample(saved),
    }


def _classification_sample(saved: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(saved.get("classifications") or [])
    referenced = {
        node_id
        for goal in saved.get("candidates") or []
        for node_id in goal.get("source_node_ids") or []
    }
    kept = [row for row in rows if row.get("id") in referenced]
    if len(kept) < 40:
        for row in rows:
            if row in kept:
                continue
            kept.append(row)
            if len(kept) >= 40:
                break
    return kept


def _set_status(dataset_id: Any, item_id: str, status: str, *, bucket: str) -> dict[str, Any]:
    if status not in CANDIDATE_STATUSES:
        raise GoalBuildError("status must be proposed, confirmed, or rejected")
    saved = STORE.get_dataset(dataset_id)
    if saved is None:
        raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
    if bucket == "candidates":
        items = saved.get("candidates") or []
    else:
        items = (saved.get("teleology") or {}).get(bucket) or []
    found = next((item for item in items if str(item.get("id")) == str(item_id)), None)
    if found is None:
        raise GoalBuildError("Review item not found", 404)
    found["status"] = status
    saved["committed"] = False
    saved["graph_committed"] = False
    if bucket == "candidates":
        prior = _status_index(saved.get("teleology") or {})
        saved["candidates"] = build_hierarchy(list(saved.get("candidates") or []))
        saved["teleology"] = infer_teleology(saved["candidates"], str(saved.get("run_id") or ""))
        _restore_status(saved["teleology"], prior)
        found = next(item for item in saved["candidates"] if str(item.get("id")) == str(item_id))
    return {"item": found, "graph_committed": False, "committed": False}


def _status_index(teleology: dict[str, Any]) -> dict[str, str]:
    indexed = {}
    for bucket in ("purposes", "constraints", "relations"):
        for item in teleology.get(bucket) or []:
            indexed[str(item.get("id"))] = str(item.get("status") or "proposed")
    return indexed


def _restore_status(teleology: dict[str, Any], prior: dict[str, str]) -> None:
    for bucket in ("purposes", "constraints", "relations"):
        for item in teleology.get(bucket) or []:
            previous = prior.get(str(item.get("id")))
            if previous in CANDIDATE_STATUSES:
                item["status"] = previous


def _find_candidate(dataset_id: Any, goal_id: str) -> dict[str, Any] | None:
    saved = STORE.get_dataset(dataset_id)
    if saved is None:
        return None
    return next(
        (
            goal
            for goal in saved.get("candidates") or []
            if str(goal.get("id")) == str(goal_id) and goal.get("status") in _ACTIVE
        ),
        None,
    )


def _items_for_goal(teleology: dict[str, Any], goal_id: str) -> list[dict[str, Any]]:
    items = []
    for bucket in ("purposes", "constraints", "relations"):
        for item in teleology.get(bucket) or []:
            if goal_id in {item.get("goal_id"), item.get("source"), item.get("target")}:
                items.append(item)
    return items


def _classify_batch(batch: list[dict[str, Any]], model: Any) -> list[str]:
    if model is None:
        return [classify_source(node) for node in batch]
    labels = list(model.classify(batch))
    if len(labels) != len(batch):
        raise GoalBuildError("classifier returned a different batch size")
    return [label if label in SOURCE_CLASSES else "Other" for label in labels]


def _compact(node: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "id": str(node.get("id") or ""),
        "name": str(node.get("name") or ""),
        "text": str(node.get("text") or node.get("description") or ""),
        "type": str(node.get("type") or ""),
        "layer": str(node.get("layer") or ""),
        "tree_parent_id": node.get("tree_parent_id"),
        "source_class": label,
    }


def _index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {label: [] for label in SOURCE_CLASSES}
    for row in rows:
        index.setdefault(str(row.get("source_class") or "Other"), []).append(row)
    return index


def _related_evidence(
    project: dict[str, Any], index: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    anchor = _anchor(str(project.get("name") or ""))
    parent = project.get("tree_parent_id")
    siblings = [
        row for row in index.get("Project") or [] if parent and row.get("tree_parent_id") == parent
    ]
    related: list[dict[str, Any]] = []
    for metric in index.get("Metric") or []:
        if _metric_supports(project, metric, anchor, len(siblings) == 1):
            related.append(metric)
    for row in (index.get("Document") or []) + (index.get("Constraint") or []):
        blob = f"{row.get('name') or ''} {row.get('text') or ''}"
        if anchor and anchor in blob:
            related.append(row)
    return related


def _metric_supports(
    project: dict[str, Any], metric: dict[str, Any], anchor: str, only_sibling: bool
) -> bool:
    blob = f"{metric.get('name') or ''} {metric.get('text') or ''}"
    if anchor and anchor in blob:
        return True
    if metric.get("tree_parent_id") and metric.get("tree_parent_id") == project.get("id"):
        return True
    return bool(
        only_sibling
        and project.get("tree_parent_id")
        and project.get("tree_parent_id") == metric.get("tree_parent_id")
        and "利润" in str(metric.get("name") or "")
    )


def _draft(
    *,
    name: str,
    description: str,
    confidence: float,
    reason: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = [_evidence(row) for row in rows if row.get("id")]
    return {
        "name": name,
        "description": description,
        "confidence": confidence,
        "reason": reason,
        "source_node_ids": [entry["node_id"] for entry in evidence],
        "evidence": evidence,
    }


def _evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": str(row.get("id") or row.get("node_id") or ""),
        "name": str(row.get("name") or ""),
        "source_class": row.get("source_class") or "",
        "layer": row.get("layer") or "",
        "text": str(row.get("text") or ""),
    }


def _validated(raw: dict[str, Any], dataset_id: Any, generated_by: str) -> dict[str, Any] | None:
    evidence = []
    for entry in raw.get("evidence") or []:
        node_id = str(entry.get("node_id") or "")
        if node_id:
            evidence.append(
                {
                    "node_id": node_id,
                    "name": str(entry.get("name") or ""),
                    "source_class": entry.get("source_class") or "",
                    "layer": entry.get("layer") or "",
                    "text": str(entry.get("text") or ""),
                }
            )
    source_ids = []
    for node_id in raw.get("source_node_ids") or [entry["node_id"] for entry in evidence]:
        text = str(node_id or "").strip()
        if text and text not in source_ids:
            source_ids.append(text)
    evidence = [entry for entry in evidence if entry["node_id"] in source_ids]
    if len(source_ids) < 2 or len(evidence) < 2:
        return None
    name = str(raw.get("name") or "").strip()
    reason = str(raw.get("reason") or "").strip()
    if not name or not reason:
        return None
    return _seal(
        dataset_id,
        name=name,
        description=str(raw.get("description") or ""),
        confidence=_unit(raw.get("confidence")),
        reason=reason,
        source_node_ids=source_ids,
        evidence=evidence,
        generated_by=generated_by,
    )


def _seal(
    dataset_id: Any,
    *,
    name: str,
    description: str,
    confidence: float,
    reason: str,
    source_node_ids: list[str],
    evidence: list[dict[str, Any]],
    generated_by: str,
) -> dict[str, Any]:
    digest = semantic_hash(name)
    return {
        "id": candidate_id(dataset_id, name),
        "dataset_id": str(dataset_id),
        "name": name,
        "description": description,
        "confidence": _unit(confidence),
        "reason": reason,
        "source_node_ids": list(source_node_ids),
        "evidence": list(evidence),
        "parent_candidate_id": None,
        "status": "proposed",
        "run_id": "",
        "generated_by": generated_by,
        "semantic_hash": digest,
    }


def _apply_mode(
    previous: list[dict[str, Any]], candidates: list[dict[str, Any]], mode: str
) -> list[dict[str, Any]]:
    prior = {str(goal.get("semantic_hash")): goal for goal in previous if goal.get("semantic_hash")}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        digest = str(candidate.get("semantic_hash"))
        old = prior.get(digest)
        if old is not None:
            candidate = _union(old, candidate)
            seen.add(digest)
        merged.append(candidate)
    leftovers = []
    for old in prior.values():
        if str(old.get("semantic_hash")) in seen:
            continue
        if mode == "incremental" or old.get("status") in {"confirmed", "rejected"}:
            leftovers.append(_without_tree_parent(dict(old)))
    return merged + leftovers


def _union(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    combined = dict(new)
    source_ids = list(old.get("source_node_ids") or [])
    evidence = list(old.get("evidence") or [])
    seen = {str(entry.get("node_id")) for entry in evidence}
    for entry in new.get("evidence") or []:
        node_id = str(entry.get("node_id") or "")
        if node_id and node_id not in seen:
            seen.add(node_id)
            evidence.append(entry)
    for node_id in new.get("source_node_ids") or []:
        if node_id not in source_ids:
            source_ids.append(node_id)
    combined["source_node_ids"] = source_ids
    combined["evidence"] = evidence
    if old.get("status") in {"confirmed", "rejected"}:
        combined["status"] = old["status"]
    combined["id"] = old.get("id") or new.get("id")
    combined["confidence"] = max(
        float(old.get("confidence") or 0), float(new.get("confidence") or 0)
    )
    return combined


def _broader(child: dict[str, Any], goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    child_brand = _brand(_blob(child))
    best: dict[str, Any] | None = None
    for other in goals:
        if other["id"] == child["id"]:
            continue
        other_name = str(other.get("name") or "")
        broader = (
            _brand(_blob(other)) == child_brand
            and child_brand
            and _is_accuracy_name(str(child.get("name") or ""))
            and not _is_accuracy_name(other_name)
            and _is_profit_name(other_name)
        )
        if broader and (best is None or len(other_name) < len(str(best.get("name") or ""))):
            best = other
    return best


def _without_tree_parent(goal: dict[str, Any]) -> dict[str, Any]:
    goal.pop("tree_parent_id", None)
    return goal


def _teleology_item(run_id: str, **fields: Any) -> dict[str, Any]:
    identity = "|".join(
        str(fields.get(key) or "")
        for key in ("kind", "goal_id", "relationship", "source", "target", "name")
    )
    item = {
        "id": str(uuid5(_NAMESPACE, f"{run_id}:{identity}")),
        "status": "proposed",
        "run_id": run_id,
        "relationship": fields.get("relationship"),
        "source": fields.get("source"),
        "target": fields.get("target"),
    }
    item.update(fields)
    item["status"] = "proposed"
    item["run_id"] = run_id
    return item


def _canonical_name(items: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    blob = " ".join(
        [str(item.get("name") or "") for item in items]
        + [str(entry.get("name") or "") for entry in evidence]
        + [str(entry.get("text") or "") for entry in evidence]
    )
    brand = _brand(blob)
    if (
        brand
        and any(token in blob for token in _PROFIT)
        and not all(_is_accuracy_name(str(item.get("name") or "")) for item in items)
    ):
        return f"提升 {brand} 项目盈利能力"
    if brand and any(token in blob for token in _ACCURACY):
        return f"提高 {brand} 项目利润核算准确性"
    return str(items[0].get("name") or "")


def _merge_key(candidate: dict[str, Any]) -> str:
    blob = _blob(candidate)
    brand = (_brand(blob) or "").lower()
    accuracy = _is_accuracy_name(str(candidate.get("name") or "")) or any(
        token in blob for token in _ACCURACY
    )
    if accuracy and any(token in blob for token in _PROFIT):
        return f"profit-accuracy:{brand}"
    if any(token in blob for token in _PROFIT):
        return f"profit:{brand}"
    return f"name:{_fold(str(candidate.get('name') or ''))}"


def _blob(candidate: dict[str, Any]) -> str:
    return " ".join(
        [str(candidate.get("name") or "")]
        + [str(entry.get("name") or "") for entry in candidate.get("evidence") or []]
        + [str(entry.get("text") or "") for entry in candidate.get("evidence") or []]
    )


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _anchor(name: str) -> str:
    return name.replace("项目", "").strip()


def _brand(text: str) -> str:
    match = _BRAND.search(text)
    return match.group(0) if match else ""


def _fold(name: str) -> str:
    text = name
    for token in ("提升", "提高", "达成", "实现", "目标", "项目", " "):
        text = text.replace(token, "")
    return text.casefold()


def _is_profit(row: dict[str, Any]) -> bool:
    return any(token in str(row.get("name") or "") for token in _PROFIT)


def _is_accuracy(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or "")
    return any(token in name for token in _ACCURACY)


def _is_profit_name(name: str) -> bool:
    return any(token in name for token in _PROFIT)


def _is_accuracy_name(name: str) -> bool:
    return any(token in name for token in _ACCURACY)


def _unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return min(1.0, max(0.0, number))
