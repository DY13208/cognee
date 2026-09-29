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

SOURCE_LAYERS = ("company_tree", "document", "entity", "graph", "other")
SEMANTIC_CLASSES = (
    "GoalSignal",
    "Project",
    "Metric",
    "Process",
    "Responsibility",
    "Constraint",
    "Document",
    "Entity",
    "Reference",
    "Other",
)
SOURCE_CLASSES = SEMANTIC_CLASSES
REJECT_REASONS = (
    "insufficient_evidence",
    "responsibility_not_goal",
    "metric_only",
    "project_only",
    "duplicate",
    "low_confidence",
    "unsupported_semantics",
    "other",
)
_LAYER_WEIGHTS = {
    "company_tree": 8,
    "document": 5,
    "entity": 4,
    "graph": 2,
    "other": 1,
}
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
_METRIC = ("利润分", "利润率", "毛利率", "健康度", "周转率", "指标", "达成率")
_PROFIT_TEXT = ("利润", "毛利", "盈利")
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


def source_layer_of(node: dict[str, Any]) -> str:
    """Provenance only. A company-tree node is not a semantic type."""
    explicit = str(node.get("source_layer") or node.get("layer") or "").strip().lower()
    aliases = {
        "company_tree": "company_tree",
        "document": "document",
        "documents": "document",
        "entity": "entity",
        "entities": "entity",
        "graph": "graph",
        "other": "other",
    }
    if explicit in aliases:
        return aliases[explicit]
    graph_type = str(node.get("type") or "")
    if graph_type == "Document":
        return "document"
    if graph_type in {"Entity", "Person", "Organization"}:
        return "entity"
    if graph_type == "Goal":
        return "company_tree"
    if graph_type:
        return "graph"
    return "other"


def classify_semantics(node: dict[str, Any]) -> tuple[str, str]:
    """Semantic class from the text. The source layer is not an input."""
    name = str(node.get("name") or "")
    text = " ".join((name, str(node.get("text") or ""), str(node.get("description") or "")))
    graph_type = str(node.get("type") or "")
    kind = str(node.get("cpd_kind") or "")
    layer = source_layer_of(node)
    if any(token in text for token in _RESPONSIBILITY):
        return "Responsibility", "名称描述的是职责或分工。"
    if any(token in name for token in _METRIC):
        return "Metric", "名称描述的是可度量的业务指标。"
    if any(token in name for token in _PROCESS):
        return "Process", "名称描述的是流程。"
    if graph_type == "Constraint" or "约束" in name or "限制" in name:
        return "Constraint", "名称描述的是约束。"
    if kind == "map_reference" or "参考" in name:
        return "Reference", "名称描述的是参照。"
    if any(token in text for token in _OUTCOME) and any(token in text for token in _OUTCOME_OBJECT):
        return "GoalSignal", "名称包含结果表述，只作为目标信号。"
    if name.endswith("项目") or ("项目" in name and "利润" not in name and "目标" not in name):
        return "Project", "名称描述的是项目。"
    if graph_type == "Document" or layer == "document":
        return "Document", "来源是文档。"
    if graph_type in {"Entity", "Person", "Organization"} or layer == "entity":
        return "Entity", "来源是实体。"
    return "Other", "名称和正文里没有可识别的业务语义。"


def classify_source(node: dict[str, Any]) -> str:
    """Semantic class. Company-tree provenance does not decide it."""
    return classify_semantics(node)[0]


def stratified_sample(
    sources: list[dict[str, Any]], max_sources: int | None
) -> list[dict[str, Any]]:
    """Spend ``max_sources`` across layers. Id order must not fill the budget."""
    rows = list(sources or [])
    if max_sources is None or len(rows) <= max(0, int(max_sources)):
        return rows
    budget = max(0, int(max_sources))
    if budget == 0:
        return []
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        buckets[source_layer_of(source)].append(source)
    available = {layer: len(items) for layer, items in buckets.items() if items}
    quotas = _layer_quotas(budget, available)
    chosen: list[dict[str, Any]] = []
    for layer in list(SOURCE_LAYERS) + [layer for layer in buckets if layer not in SOURCE_LAYERS]:
        chosen.extend(buckets.get(layer, [])[: quotas.get(layer, 0)])
    return chosen


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
    chosen = _prepare_sources(stratified_sample(list(sources or []), max_sources))
    payloads: list[int] = []
    run_id = str(uuid4())
    layer_counts = _count_values(chosen, "source_layer")

    for batch in _chunks(chosen, size):
        payloads.append(len(batch))

    classified: list[dict[str, Any]] = []
    for batch in _chunks(chosen, size):
        payloads.append(len(batch))
        labels = _classify_batch(batch, model)
        for node, label in zip(batch, labels):
            classified.append(_compact(node, label))
    class_counts = _count_values(classified, "semantic_class")

    index = _index(classified)
    extracted: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    rejected_empty = 0
    for batch in _chunks(index["Project"], size):
        payloads.append(len(batch))
        raw_items = model.extract(batch) if model is not None else extract_candidates(batch, index)
        for raw in raw_items or []:
            valid, reason = _validated(raw, dataset_id, generated_by)
            if valid is None:
                rejected_empty += 1
                rejections.append(_rejection(raw, reason or "insufficient_evidence"))
            else:
                extracted.append(valid)
    rejections.extend(_unused_source_rejections(classified, extracted))
    rejections.extend(_duplicate_rejections(extracted))

    canonical = canonicalize(extracted, dataset_id, generated_by)
    merged_count = max(0, len(extracted) - len(canonical))
    combined = _apply_mode(previous or [], canonical, mode)
    hierarchical = build_hierarchy(combined)
    for goal in hierarchical:
        goal["dataset_id"] = str(dataset_id)
        goal["run_id"] = run_id
        goal["generated_by"] = goal.get("generated_by") or generated_by
    teleology = infer_teleology(hierarchical, run_id)
    active_goals = [goal for goal in hierarchical if goal.get("status") in _ACTIVE]
    parent_ids = {
        goal["parent_candidate_id"] for goal in active_goals if goal.get("parent_candidate_id")
    }
    orphan_goals = [
        goal
        for goal in active_goals
        if not goal.get("parent_candidate_id") and goal["id"] not in parent_ids
    ]
    rejected_by_reason = _count_values(rejections, "reject_reason")
    stage_stats = {
        "discovering": {"source_count": len(chosen), "source_layer_counts": layer_counts},
        "classifying": {"semantic_class_counts": class_counts},
        "extracting_goals": {
            "raw_candidate_count": len(extracted),
            "rejected_count": len(rejections),
        },
        "canonicalizing": {
            "canonical_goal_count": len(hierarchical),
            "merged_count": merged_count,
        },
        "building_hierarchy": {
            "hierarchy_edge_count": len(parent_ids),
            "orphan_goal_count": len(orphan_goals),
        },
        "inferring_teleology": {
            "purpose_count": len(teleology["purposes"]),
            "constraint_count": len(teleology["constraints"]),
            "relation_count": len(teleology["relations"]),
        },
    }
    return {
        "run_id": run_id,
        "dataset_id": str(dataset_id),
        "mode": mode,
        "status": "completed",
        "stage": "completed",
        "stages": list(STAGES),
        "stage_stats": stage_stats,
        "committed": False,
        "graph_committed": False,
        "batch_size": size,
        "concurrency": max(1, int(concurrency or 1)),
        "max_sources": max_sources,
        "max_batch_payload": max(payloads) if payloads else 0,
        "source_count": len(chosen),
        "source_layer_counts": layer_counts,
        "semantic_class_counts": class_counts,
        "raw_candidate_count": len(extracted),
        "canonical_goal_count": len(hierarchical),
        "merged_count": merged_count,
        "rejected_empty": rejected_empty,
        "rejected_count": len(rejections),
        "rejected_by_reason": rejected_by_reason,
        "rejections": rejections,
        "candidates": hierarchical,
        "teleology": teleology,
        "classifications": [
            {
                "id": row["id"],
                "name": row["name"],
                "source_layer": row.get("source_layer") or "",
                "semantic_class": row.get("semantic_class") or "",
                "classification_reason": row.get("classification_reason") or "",
                "source_class": row.get("semantic_class") or "",
                "layer": row.get("source_layer") or "",
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
        if _semantic(project) != "Project":
            continue
        related = _related_evidence(project, index)
        profit = [
            row
            for row in related
            if _semantic(row) == "Metric" and _is_profit(row) and not _is_accuracy(row)
        ]
        accuracy = [row for row in related if _semantic(row) == "Metric" and _is_accuracy(row)]
        support = [row for row in related if _semantic(row) in {"Document", "Constraint"}]
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


def apply_candidate_parents(
    goals: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    blocked_ids: set[str],
) -> list[dict[str, Any]]:
    """Parent one canonical goal from another canonical goal.

    Source-node ids are blocked. A directory parent cannot become a goal parent.
    """
    copied = [dict(goal) for goal in goals]
    by_id = {str(goal["id"]): goal for goal in copied}
    for goal in copied:
        goal["parent_candidate_id"] = None
    for link in links or []:
        child_id = str(link.get("id") or "")
        parent_id = link.get("parent_candidate_id")
        parent = None if parent_id in (None, "") else str(parent_id)
        child = by_id.get(child_id)
        if child is None or parent is None:
            continue
        if parent == child_id or parent not in by_id or parent in blocked_ids:
            continue
        child["parent_candidate_id"] = parent
    return copied


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
            if _semantic(entry) != "Constraint":
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
            "source_layer_counts": {},
            "semantic_class_counts": {},
            "raw_candidate_count": 0,
            "canonical_goal_count": 0,
            "rejected_count": 0,
            "rejected_by_reason": {},
            "stage_stats": {},
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
            entry for entry in goal.get("evidence") or [] if _semantic(entry) == "Document"
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
        "source_layer_counts": dict(saved.get("source_layer_counts") or {}),
        "semantic_class_counts": dict(saved.get("semantic_class_counts") or {}),
        "raw_candidate_count": saved.get("raw_candidate_count") or 0,
        "canonical_goal_count": saved.get("canonical_goal_count") or len(candidates),
        "rejected_count": saved.get("rejected_count") or 0,
        "rejected_by_reason": dict(saved.get("rejected_by_reason") or {}),
        "rejections": list(saved.get("rejections") or []),
        "stage_stats": dict(saved.get("stage_stats") or {}),
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


def _prepare_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for source in sources:
        row = dict(source)
        layer = source_layer_of(row)
        row["source_layer"] = layer
        row["layer"] = layer
        prepared.append(row)
    return prepared


def _layer_quotas(budget: int, available: dict[str, int]) -> dict[str, int]:
    if not available or budget <= 0:
        return {layer: 0 for layer in available}
    weights = {layer: _LAYER_WEIGHTS.get(layer, 1) for layer in available}
    weight_total = sum(weights.values()) or 1
    raw = {layer: budget * weights[layer] / weight_total for layer in available}
    floors = {layer: min(available[layer], int(raw[layer])) for layer in available}
    remainder = budget - sum(floors.values())
    order = sorted(
        available,
        key=lambda layer: (raw[layer] - int(raw[layer]), weights[layer]),
        reverse=True,
    )
    while remainder > 0:
        progressed = False
        for layer in order:
            if floors[layer] < available[layer] and remainder > 0:
                floors[layer] += 1
                remainder -= 1
                progressed = True
        if not progressed:
            break
    if budget >= len(available):
        for layer, count in available.items():
            if floors[layer] == 0 and count > 0:
                donor = max(floors, key=lambda item: floors[item])
                if floors[donor] > 1:
                    floors[donor] -= 1
                    floors[layer] = 1
    return floors


def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "other")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _semantic(row: dict[str, Any]) -> str:
    return _normalize_class(str(row.get("semantic_class") or row.get("source_class") or "Other"))


def _normalize_class(label: str) -> str:
    if label == "Goal":
        return "GoalSignal"
    return label if label in SEMANTIC_CLASSES else "Other"


def _rejection(raw: dict[str, Any], reason: str) -> dict[str, Any]:
    code = reason if reason in REJECT_REASONS else "other"
    return {
        "name": str(raw.get("name") or ""),
        "source_node_ids": [
            str(node_id) for node_id in raw.get("source_node_ids") or [] if node_id
        ],
        "reject_reason": code,
    }


def _unused_source_rejections(
    classified: list[dict[str, Any]], extracted: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    used = {
        node_id for candidate in extracted for node_id in candidate.get("source_node_ids") or []
    }
    reasons = {
        "Responsibility": "responsibility_not_goal",
        "Metric": "metric_only",
        "Project": "project_only",
        "GoalSignal": "insufficient_evidence",
    }
    rejections = []
    for row in classified:
        if row.get("id") in used:
            continue
        reason = reasons.get(_semantic(row))
        if reason is None:
            continue
        rejections.append(
            _rejection(
                {"name": row.get("name"), "source_node_ids": [row.get("id")]},
                reason,
            )
        )
    return rejections


def _duplicate_rejections(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in extracted:
        groups[_merge_key(candidate)].append(candidate)
    rejections = []
    for items in groups.values():
        for extra in items[1:]:
            rejections.append(_rejection(extra, "duplicate"))
    return rejections


def _classify_batch(batch: list[dict[str, Any]], model: Any) -> list[tuple[str, str]]:
    if model is None:
        return [classify_semantics(node) for node in batch]
    labels = list(model.classify(batch))
    if len(labels) != len(batch):
        raise GoalBuildError("classifier returned a different batch size")
    normalized = []
    for label in labels:
        if isinstance(label, tuple):
            semantic, reason = label
        else:
            semantic, reason = label, "模型给出的语义类。"
        normalized.append((_normalize_class(str(semantic)), str(reason)))
    return normalized


def _compact(node: dict[str, Any], label: tuple[str, str]) -> dict[str, Any]:
    semantic, reason = label
    layer = source_layer_of(node)
    return {
        "id": str(node.get("id") or ""),
        "name": str(node.get("name") or ""),
        "text": str(node.get("text") or node.get("description") or ""),
        "type": str(node.get("type") or ""),
        "source_layer": layer,
        "layer": layer,
        "tree_parent_id": node.get("tree_parent_id"),
        "semantic_class": semantic,
        "source_class": semantic,
        "classification_reason": reason,
    }


def _index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {label: [] for label in SEMANTIC_CLASSES}
    for row in rows:
        index.setdefault(_semantic(row), []).append(row)
    return index


def _related_evidence(
    project: dict[str, Any], index: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    anchor = _anchor(str(project.get("name") or ""))
    parent = project.get("tree_parent_id")
    projects = index.get("Project") or []
    siblings = [row for row in projects if parent and row.get("tree_parent_id") == parent]
    only_project = len(projects) == 1
    related: list[dict[str, Any]] = []
    for metric in index.get("Metric") or []:
        if _metric_supports(project, metric, anchor, len(siblings) == 1, only_project):
            related.append(metric)
    for row in (index.get("Document") or []) + (index.get("Constraint") or []):
        if _profit_support(row, anchor, only_project):
            related.append(row)
    return related


def _metric_supports(
    project: dict[str, Any],
    metric: dict[str, Any],
    anchor: str,
    only_sibling: bool,
    only_project: bool,
) -> bool:
    blob = f"{metric.get('name') or ''} {metric.get('text') or ''}"
    if anchor and anchor in blob:
        return True
    if metric.get("tree_parent_id") and metric.get("tree_parent_id") == project.get("id"):
        return True
    profit_name = any(token in str(metric.get("name") or "") for token in _PROFIT_TEXT)
    if only_project and profit_name:
        return True
    return bool(
        only_sibling
        and project.get("tree_parent_id")
        and project.get("tree_parent_id") == metric.get("tree_parent_id")
        and profit_name
    )


def _profit_support(row: dict[str, Any], anchor: str, only_project: bool) -> bool:
    blob = f"{row.get('name') or ''} {row.get('text') or ''}"
    if not any(token in blob for token in ("利润", "毛利", "盈利", "目标")):
        return False
    if anchor and anchor in blob:
        return True
    return only_project


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
    semantic = _semantic(row)
    layer = str(row.get("source_layer") or row.get("layer") or "")
    return {
        "node_id": str(row.get("id") or row.get("node_id") or ""),
        "name": str(row.get("name") or ""),
        "semantic_class": semantic,
        "source_class": semantic,
        "source_layer": layer,
        "layer": layer,
        "text": str(row.get("text") or ""),
    }


def _validated(
    raw: dict[str, Any], dataset_id: Any, generated_by: str
) -> tuple[dict[str, Any] | None, str]:
    evidence = []
    for entry in raw.get("evidence") or []:
        node_id = str(entry.get("node_id") or "")
        if node_id:
            evidence.append(
                {
                    "node_id": node_id,
                    "name": str(entry.get("name") or ""),
                    "semantic_class": _semantic(entry),
                    "source_class": _semantic(entry),
                    "source_layer": entry.get("source_layer") or entry.get("layer") or "",
                    "layer": entry.get("source_layer") or entry.get("layer") or "",
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
        return None, "insufficient_evidence"
    if _unit(raw.get("confidence")) < 0.4:
        return None, "low_confidence"
    name = str(raw.get("name") or "").strip()
    reason = str(raw.get("reason") or "").strip()
    if not name or not reason:
        return None, "unsupported_semantics"
    return (
        _seal(
            dataset_id,
            name=name,
            description=str(raw.get("description") or ""),
            confidence=_unit(raw.get("confidence")),
            reason=reason,
            source_node_ids=source_ids,
            evidence=evidence,
            generated_by=generated_by,
        ),
        "",
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
