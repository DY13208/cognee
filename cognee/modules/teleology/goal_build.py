"""Start a dataset teleology build. The run reads sources and stores proposals.

It does not write the company tree and it does not commit a proposal.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.teleology.goal_model import (
    STORE,
    GoalBuildError,
    clamp_goal_batch,
    goal_model_view,
    run_goal_build,
    source_layer_of,
    stratified_sample,
)
from cognee.modules.teleology.graph_annotations import _authorized_dataset
from cognee.modules.teleology.purpose_layer import _props_dict


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
    if mode not in {"baseline", "incremental"}:
        raise GoalBuildError("mode must be baseline or incremental")
    await _authorized_dataset(dataset_id, user, "write")
    if sources is None:
        sources = await load_dataset_sources(
            dataset_id, user, batch_size=batch_size, max_sources=max_sources
        )
    previous = STORE.get_dataset(dataset_id)
    result = run_goal_build(
        dataset_id,
        sources,
        mode=mode,
        batch_size=batch_size,
        concurrency=concurrency,
        max_sources=max_sources,
        model=model,
        previous=list((previous or {}).get("candidates") or []),
    )
    STORE.save(result)
    return goal_model_view(dataset_id)


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
    return chosen


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
        "cpd_kind": props.get("cpd_kind") or "",
        "tree_parent_id": None,
    }
    layer = source_layer_of(draft)
    draft["source_layer"] = layer
    draft["layer"] = layer
    return draft
