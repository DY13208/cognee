"""Goal-aware filtering and reranking for existing retrievers."""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from cognee.infrastructure.databases.graph.graph_db_interface import GraphDBInterface

GoalFilterMode = Literal["filter", "rerank"]
TELEOLOGY_RELATIONSHIPS = frozenset({"serves", "advances", "blocks"})


def normalize_goal_filter_mode(mode: str | None) -> GoalFilterMode:
    normalized = str(mode or "rerank").strip().lower()
    if normalized not in {"filter", "rerank"}:
        raise ValueError("goal_filter_mode must be 'filter' or 'rerank'.")
    return normalized  # type: ignore[return-value]


def _node_id(node: object) -> str | None:
    if isinstance(node, dict):
        value = node.get("id") or node.get("node_id")
    else:
        value = getattr(node, "id", None) or getattr(node, "node_id", None)
    return str(value) if value is not None else None


def _unpack_edge(edge: object) -> tuple[str | None, str, str | None] | None:
    """Normalize adapter edge shapes to ``(source_id, relationship, target_id)``.

    Ladybug/Turso/Postgres return ``(source_dict, relationship, target_dict)``.
    The interface / Neptune style is ``(source_id, target_id, relationship, props)``.
    """
    if not isinstance(edge, (tuple, list)) or len(edge) < 3:
        return None
    if len(edge) >= 4 and isinstance(edge[0], (str, int)) and isinstance(edge[1], (str, int)):
        return str(edge[0]), str(edge[2]), str(edge[1])
    source_id = _node_id(edge[0]) or (str(edge[0]) if edge[0] is not None else None)
    target_id = _node_id(edge[2]) or (str(edge[2]) if edge[2] is not None else None)
    return source_id, str(edge[1]), target_id


async def get_goal_scope_ids(graph_engine: GraphDBInterface, goal_id: str) -> set[str]:
    """Return entity and chunk IDs connected to a Goal through teleology edges."""
    scope_ids: set[str] = set()
    goal_id_str = str(goal_id)
    goal_edges = await graph_engine.get_edges(goal_id_str)
    for edge in goal_edges:
        unpacked = _unpack_edge(edge)
        if unpacked is None:
            continue
        source_id, relationship, target_id = unpacked
        if relationship.lower() not in TELEOLOGY_RELATIONSHIPS:
            continue
        related_id = target_id if source_id == goal_id_str else source_id
        if related_id is None or related_id == goal_id_str:
            continue
        scope_ids.add(related_id)
        for entity_edge in await graph_engine.get_edges(related_id):
            entity_unpacked = _unpack_edge(entity_edge)
            if entity_unpacked is None:
                continue
            entity_source, entity_relationship, entity_target = entity_unpacked
            if entity_relationship.lower() != "contains":
                continue
            for endpoint_id in (entity_source, entity_target):
                if endpoint_id:
                    scope_ids.add(endpoint_id)
    return scope_ids


def _collect_ids(value: object, visited: set[int] | None = None) -> set[str]:
    if visited is None:
        visited = set()
    if value is None or id(value) in visited:
        return set()
    visited.add(id(value))
    if isinstance(value, (str, int, float, bool)):
        return set()
    if isinstance(value, dict):
        ids = {str(item) for key in ("id", "node_id", "chunk_id") if (item := value.get(key))}
        for nested in value.values():
            ids.update(_collect_ids(nested, visited))
        return ids
    if isinstance(value, (list, tuple, set)):
        ids: set[str] = set()
        for nested in value:
            ids.update(_collect_ids(nested, visited))
        return ids
    ids = set()
    direct_id = _node_id(value)
    if direct_id:
        ids.add(direct_id)
    payload = getattr(value, "payload", None)
    if payload is not None:
        ids.update(_collect_ids(payload, visited))
    for attribute in ("node1", "node2", "source", "target"):
        nested = getattr(value, attribute, None)
        if nested is not None:
            ids.update(_collect_ids(nested, visited))
    return ids


def apply_goal_scope(items: object, scope_ids: set[str], mode: GoalFilterMode) -> object:
    """Filter or stably promote list items connected to the selected Goal."""
    if not isinstance(items, list):
        return items
    matching = [item for item in items if _collect_ids(item) & scope_ids]
    if mode == "filter":
        return matching
    matching_object_ids = {id(item) for item in matching}
    return matching + [item for item in items if id(item) not in matching_object_ids]


def wrap_goal_scoped_retrieval(
    retrieve: Callable[..., Awaitable[Any]], scope_ids: set[str], mode: GoalFilterMode
) -> Callable[..., Awaitable[Any]]:
    """Wrap a retriever method so context/completion are built from goal-scoped objects."""

    async def goal_scoped_retrieve(*args, **kwargs) -> Any:
        items = await retrieve(*args, **kwargs)
        return apply_goal_scope(items, scope_ids, mode)

    return goal_scoped_retrieve
