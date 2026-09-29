"""Start a dataset teleology build. The run reads sources and stores proposals.

It does not write the company tree and it does not commit a proposal.
Production analysis goes through the LLM adapter and continues after the
client disconnects.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.goal_llm import GoalBuildLLM, LlmUnavailable
from cognee.modules.teleology.goal_model import (
    STAGES,
    GoalBuildError,
    _apply_mode,
    _chunks,
    _compact,
    _count_values,
    _validated,
    apply_candidate_parents,
    clamp_goal_batch,
    infer_teleology,
    source_layer_of,
    stratified_sample,
)
from cognee.modules.teleology.goal_store import get_goal_store
from cognee.modules.teleology.graph_annotations import _authorized_dataset
from cognee.modules.teleology.purpose_layer import _props_dict

_TASKS: dict[str, asyncio.Task[None]] = {}


async def start_teleology_build(
    dataset_id: UUID,
    user: Any,
    *,
    mode: str = "baseline",
    batch_size: int = 20,
    concurrency: int = 1,
    max_sources: int | None = None,
    sources: list[dict[str, Any]] | None = None,
    model: Any = None,
) -> dict[str, Any]:
    """Queue a build and return immediately. The caller does not have to stay connected."""
    if mode not in {"baseline", "incremental"}:
        raise GoalBuildError("mode must be baseline or incremental")
    await _authorized_dataset(dataset_id, user, "write")
    run_id = str(uuid4())
    store = get_goal_store()
    pending = await store.create_pending(
        {
            "run_id": run_id,
            "dataset_id": str(dataset_id),
            "mode": mode,
            "batch_size": clamp_goal_batch(batch_size),
            "concurrency": max(1, int(concurrency or 1)),
            "max_sources": max_sources,
        }
    )
    task = asyncio.create_task(
        _execute(
            run_id,
            dataset_id,
            user,
            mode=mode,
            batch_size=batch_size,
            concurrency=concurrency,
            max_sources=max_sources,
            sources=sources,
            model=model,
        )
    )
    _TASKS[run_id] = task
    task.add_done_callback(lambda _task, key=run_id: _TASKS.pop(key, None))
    return pending


async def list_goal_model_runs(
    dataset_id: UUID,
    user: Any,
    *,
    mode: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read goal-model run history. Candidates are not converted into proposals."""
    await _authorized_dataset(dataset_id, user, "read")
    size = min(200, max(1, int(limit or 50)))
    start = max(0, int(offset or 0))
    runs = await get_goal_store().list_runs(
        dataset_id, mode=mode or None, status=status or None, limit=size, offset=start
    )
    return {"runs": runs, "limit": size, "offset": start}


async def get_build_status(run_id: str, user: Any) -> dict[str, Any]:
    row = await get_goal_store().get_run(run_id)
    if row is None:
        raise GoalBuildError("Teleology build not found", 404)
    await _authorized_dataset(UUID(str(row["dataset_id"])), user, "read")
    return row


async def read_goal_model(dataset_id: UUID, user: Any) -> dict[str, Any]:
    await _authorized_dataset(dataset_id, user, "read")
    saved = await get_goal_store().get_dataset(dataset_id)
    if saved is None:
        from cognee.modules.teleology.goal_model import goal_model_view

        return goal_model_view(dataset_id)
    saved["committed"] = False
    saved["graph_committed"] = False
    return saved


async def review_goal_candidate(dataset_id: UUID, candidate_id: str, status: str) -> dict[str, Any]:
    """Persist a review. This does not write the company tree or commit teleology."""
    return await get_goal_store().set_candidate_status(dataset_id, candidate_id, status)


async def review_teleology_item(
    dataset_id: UUID, item_id: str, status: str, kind: str
) -> dict[str, Any]:
    """Persist a purpose, constraint, or relation review. The graph stays unchanged."""
    return await get_goal_store().set_teleology_status(dataset_id, item_id, status, kind)


def build_tasks() -> dict[str, asyncio.Task[None]]:
    return _TASKS


async def _execute(
    run_id: str,
    dataset_id: UUID,
    user: Any,
    *,
    mode: str,
    batch_size: int,
    concurrency: int,
    max_sources: int | None,
    sources: list[dict[str, Any]] | None,
    model: Any,
) -> None:
    store = get_goal_store()
    try:
        await store.update(run_id, status="running", stage="discovering")
        adapter = model if model is not None else GoalBuildLLM()
        if model is None and not await adapter.available():
            await store.fail(run_id, "llm_unavailable", "LLM is unavailable.")
            return
        if sources is None:
            sources = await load_dataset_sources(
                dataset_id, user, batch_size=batch_size, max_sources=max_sources
            )
        else:
            sources = [ensure_source_context(dict(source)) for source in sources]
        saved = await store.get_dataset(dataset_id)
        result = await run_llm_goal_build(
            dataset_id,
            sources,
            adapter,
            run_id=run_id,
            mode=mode,
            batch_size=batch_size,
            concurrency=concurrency,
            max_sources=max_sources,
            previous=list((saved or {}).get("candidates") or []),
            on_progress=lambda **fields: store.update(run_id, **fields),
        )
        await store.save_result(result)
    except LlmUnavailable as exc:
        await store.fail(run_id, "llm_unavailable", str(exc) or "LLM is unavailable.")
    except Exception as exc:  # noqa: BLE001 - a build failure must be stored, not lost
        await store.fail(run_id, "build_failed", str(exc) or "Build failed.")


async def run_llm_goal_build(
    dataset_id: Any,
    sources: list[dict[str, Any]],
    model: Any,
    *,
    run_id: str,
    mode: str,
    batch_size: int,
    concurrency: int,
    max_sources: int | None,
    on_progress: Any = None,
    previous: list[dict[str, Any]] | None = None,
    generated_by: str = "dataset_goal_build",
) -> dict[str, Any]:
    """Analyze with the LLM adapter. Keyword extraction is not called."""
    size = clamp_goal_batch(batch_size)
    workers = max(1, int(concurrency or 1))
    chosen = [
        ensure_source_context(dict(source))
        for source in stratified_sample(list(sources or []), max_sources)
    ]
    layer_counts = _count_values(chosen, "source_layer")
    source_ids = {str(source.get("id") or "") for source in chosen}

    async def progress(**fields: Any) -> None:
        if on_progress is not None:
            await on_progress(**fields)

    await progress(
        stage="discovering",
        source_count=len(chosen),
        processed_sources=0,
        progress=0,
        stage_stats={
            "discovering": {"source_count": len(chosen), "source_layer_counts": layer_counts}
        },
    )
    classified: list[dict[str, Any]] = []
    processed = 0
    for batch in _chunks(chosen, size):
        labels = await model.classify_sources(batch)
        for node, label in zip(batch, labels):
            compacted = _compact(node, label)
            for key in (
                "description",
                "note",
                "parent_name",
                "ancestor_names",
                "child_names",
                "related_documents",
                "related_entities",
                "graph_neighbors",
            ):
                if key in node:
                    compacted[key] = node[key]
            classified.append(compacted)
        processed += len(batch)
        await progress(
            stage="classifying",
            processed_sources=processed,
            progress=_ratio(processed, len(chosen)),
        )
    class_counts = _count_values(classified, "semantic_class")
    await progress(
        stage="extracting_goals",
        stage_stats={
            "discovering": {"source_count": len(chosen), "source_layer_counts": layer_counts},
            "classifying": {"semantic_class_counts": class_counts},
        },
    )
    extracted: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for batch in _chunks(classified, size):
        raw_items = await model.extract_goals(batch)
        for raw in raw_items or []:
            prepared = _with_known_evidence(raw, classified)
            valid, reason = _validated(prepared, dataset_id, generated_by)
            if valid is None:
                rejections.append(
                    {"name": raw.get("name"), "reject_reason": reason or "insufficient_evidence"}
                )
            else:
                extracted.append(valid)
    canonical_raw = await model.canonicalize_goals(extracted)
    canonical: list[dict[str, Any]] = []
    for raw in canonical_raw or []:
        prepared = _with_known_evidence(raw, classified)
        valid, reason = _validated(prepared, dataset_id, generated_by)
        if valid is None:
            rejections.append(
                {"name": raw.get("name"), "reject_reason": reason or "insufficient_evidence"}
            )
        else:
            canonical.append(valid)
    if not canonical and extracted:
        canonical = extracted
    await progress(stage="canonicalizing", raw_candidate_count=len(extracted))
    combined = _apply_mode(list(previous or []), canonical, mode)
    links = await model.build_goal_hierarchy(combined)
    hierarchical = apply_candidate_parents(combined, links, blocked_ids=source_ids)
    for goal in hierarchical:
        goal["dataset_id"] = str(dataset_id)
        goal["run_id"] = run_id
        goal["generated_by"] = goal.get("generated_by") or generated_by
    teleology = infer_teleology(hierarchical, run_id)
    active = [goal for goal in hierarchical if goal.get("status") in {"proposed", "confirmed"}]
    parent_ids = {goal["parent_candidate_id"] for goal in active if goal.get("parent_candidate_id")}
    orphans = [
        goal
        for goal in active
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
            "merged_count": max(0, len(extracted) - len(canonical)),
        },
        "building_hierarchy": {
            "hierarchy_edge_count": len(parent_ids),
            "orphan_goal_count": len(orphans),
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
        "concurrency": workers,
        "max_sources": max_sources,
        "source_count": len(chosen),
        "processed_sources": len(chosen),
        "progress": 1,
        "source_layer_counts": layer_counts,
        "semantic_class_counts": class_counts,
        "raw_candidate_count": len(extracted),
        "canonical_goal_count": len(hierarchical),
        "rejected_count": len(rejections),
        "rejected_by_reason": rejected_by_reason,
        "rejections": rejections,
        "candidates": hierarchical,
        "teleology": teleology,
        "purposes": teleology["purposes"],
        "constraints": teleology["constraints"],
        "relations": teleology["relations"],
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


def ensure_source_context(source: dict[str, Any]) -> dict[str, Any]:
    """Every source sent to the model carries neighborhood context, not only a name."""
    layer = source_layer_of(source)
    source["source_layer"] = layer
    source["layer"] = layer
    source["description"] = str(source.get("description") or "")
    source["note"] = str(source.get("note") or source.get("source_note") or "")
    source["source_note"] = source["note"]
    source["parent_name"] = str(source.get("parent_name") or "")
    source["ancestor_names"] = list(source.get("ancestor_names") or [])
    source["child_names"] = list(
        source.get("child_names") or source.get("direct_child_names") or []
    )
    source["direct_child_names"] = source["child_names"]
    source["related_documents"] = list(source.get("related_documents") or [])
    source["related_entities"] = list(source.get("related_entities") or [])
    source["graph_neighbors"] = list(source.get("graph_neighbors") or [])
    return source


def _with_known_evidence(raw: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(source.get("id") or ""): source for source in sources}
    source_ids = []
    for node_id in raw.get("source_node_ids") or []:
        text = str(node_id or "").strip()
        if text and text in by_id and text not in source_ids:
            source_ids.append(text)
    evidence = []
    for node_id in source_ids:
        source = by_id[node_id]
        evidence.append(
            {
                "node_id": node_id,
                "name": source.get("name") or "",
                "semantic_class": source.get("semantic_class") or "",
                "source_class": source.get("semantic_class") or source.get("source_class") or "",
                "source_layer": source.get("source_layer") or "",
                "layer": source.get("source_layer") or "",
                "text": source.get("text") or source.get("description") or "",
            }
        )
    drafted = dict(raw)
    drafted["source_node_ids"] = source_ids
    drafted["evidence"] = evidence
    return drafted


def _ratio(done: int, total: int) -> float:
    if total <= 0:
        return 1
    return round(min(1, done / total), 4)


async def load_dataset_sources(
    dataset_id: UUID,
    user: Any,
    *,
    batch_size: int,
    max_sources: int | None,
) -> list[dict[str, Any]]:
    """Page every layer, then sample. Id order must not fill ``max_sources``."""
    dataset = await _authorized_dataset(dataset_id, user, "read")
    page = clamp_goal_batch(batch_size)
    sources: list[dict[str, Any]] = []
    offset = 0
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        while True:
            rows = await graph.query(
                """MATCH (n:Node)
                RETURN n.id, n.name, n.type, n.properties
                ORDER BY n.id
                SKIP $offset
                LIMIT $limit""",
                {"offset": offset, "limit": page},
            )
            if not rows:
                break
            for row in rows:
                source = _source_row(row)
                if source is not None:
                    sources.append(source)
            if len(rows) < page:
                break
            offset += page
        chosen = stratified_sample(sources, max_sources)
        parents = await _parent_links(graph, {source["id"] for source in chosen})
        for source in chosen:
            source["tree_parent_id"] = parents.get(source["id"])
        await _enrich_graph_context(graph, chosen, parents)
    return [ensure_source_context(source) for source in chosen]


async def _parent_links(graph: Any, wanted: set[str]) -> dict[str, str]:
    if not wanted:
        return {}
    links: dict[str, str] = {}
    offset = 0
    page = 200
    while True:
        rows = await graph.query(
            """MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE r.relationship_name = 'has_subgoal'
            RETURN c.id, p.id
            ORDER BY c.id
            SKIP $offset
            LIMIT $limit""",
            {"offset": offset, "limit": page},
        )
        if not rows:
            break
        for row in rows:
            if not row or row[0] is None or len(row) < 2:
                continue
            child_id = str(row[0])
            if child_id in wanted and child_id not in links:
                links[child_id] = str(row[1])
        if len(rows) < page:
            break
        offset += page
    return links


async def _enrich_graph_context(
    graph: Any, sources: list[dict[str, Any]], parents: dict[str, str]
) -> None:
    """Attach parent, ancestor, child, document, entity, and neighbor context."""
    names = {source["id"]: str(source.get("name") or "") for source in sources}
    for source in sources:
        children = await _named_targets(
            graph,
            """MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id = $pid AND r.relationship_name = 'has_subgoal'
            RETURN c.name
            LIMIT 20""",
            source["id"],
        )
        neighbors = await _neighbor_rows(graph, source["id"])
        source["child_names"] = children
        source["direct_child_names"] = children
        source["graph_neighbors"] = neighbors
        source["related_documents"] = [
            item["name"] for item in neighbors if item["kind"] == "document"
        ]
        source["related_entities"] = [
            item["name"] for item in neighbors if item["kind"] == "entity"
        ]
        source["ancestor_names"] = await _ancestor_names(graph, source, parents, names)
        source["parent_name"] = source["ancestor_names"][0] if source["ancestor_names"] else ""


async def _named_targets(graph: Any, query: str, node_id: str) -> list[str]:
    rows = await graph.query(query, {"pid": node_id})
    names: list[str] = []
    for row in rows or []:
        if row and row[0]:
            names.append(str(row[0]))
    return names


async def _neighbor_rows(graph: Any, node_id: str) -> list[dict[str, str]]:
    rows = await graph.query(
        """MATCH (n:Node)-[r:EDGE]-(m:Node)
        WHERE n.id = $pid
        RETURN m.name, m.type, r.relationship_name
        LIMIT 24""",
        {"pid": node_id},
    )
    neighbors: list[dict[str, str]] = []
    for row in rows or []:
        if not row or not row[0]:
            continue
        graph_type = str(row[1] or "")
        relation = str(row[2] or "")
        kind = (
            "document"
            if "document" in graph_type.lower() or relation in {"mentions", "contains"}
            else "entity"
        )
        neighbors.append(
            {"name": str(row[0]), "type": graph_type, "relationship": relation, "kind": kind}
        )
    return neighbors[:12]


async def _ancestor_names(
    graph: Any,
    source: dict[str, Any],
    parents: dict[str, str],
    names: dict[str, str],
) -> list[str]:
    ancestors: list[str] = []
    parent_id = parents.get(source["id"]) or source.get("tree_parent_id")
    seen: set[str] = set()
    while parent_id and parent_id not in seen and len(ancestors) < 4:
        seen.add(str(parent_id))
        name = names.get(str(parent_id))
        if not name:
            looked_up = await _named_targets(
                graph,
                "MATCH (n:Node) WHERE n.id = $pid RETURN n.name LIMIT 1",
                str(parent_id),
            )
            name = looked_up[0] if looked_up else ""
        if name:
            ancestors.append(name)
        parent_id = parents.get(str(parent_id))
    return ancestors


def _source_row(row: Any) -> dict[str, Any] | None:
    if not row or row[0] is None:
        return None
    props = _props_dict(row[3] if len(row) > 3 else None)
    graph_type = str(row[2] or "")
    draft = {
        "id": str(row[0]),
        "name": str(row[1] or props.get("name") or row[0]),
        "type": graph_type,
        "text": str(
            props.get("description") or props.get("text") or props.get("source_note") or ""
        ),
        "description": str(props.get("description") or ""),
        "note": str(props.get("source_note") or props.get("note") or ""),
        "source_note": str(props.get("source_note") or props.get("note") or ""),
        "cpd_kind": props.get("cpd_kind") or "",
        "tree_parent_id": None,
    }
    layer = source_layer_of(draft)
    draft["source_layer"] = layer
    draft["layer"] = layer
    return draft
