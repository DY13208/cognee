"""Small, dataset-scoped goal operations for the teleology workspace."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.infrastructure.databases.provenance import EdgeIdentity
from cognee.modules.teleology.graph_annotations import (
    _authorized_dataset,
    _enrich_goals,
    _node_row,
    _props_type,
)
from cognee.modules.teleology.models import Goal
from cognee.modules.teleology.purpose_relations import edge_properties, select_purpose_relations
from cognee.modules.users.models import User

_UNSET = object()


async def _parent(graph: Any, goal_id: str) -> str | None:
    rows = await graph.query(
        """MATCH (p:Node)-[r:EDGE]->(c:Node)
        WHERE c.id = $id AND r.relationship_name = 'has_subgoal'
        RETURN p.id ORDER BY p.id LIMIT 1""",
        {"id": goal_id},
    )
    return str(rows[0][0]) if rows else None


async def goal_path(dataset_id: UUID, user: User, goal_id: str) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "read")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: str | None = goal_id
        while current and current not in seen and len(result) < 64:
            seen.add(current)
            props = await graph.get_node(current)
            if not props or _props_type(props) != "Goal":
                if not result:
                    raise KeyError("Goal not found in dataset graph")
                break
            result.insert(0, _node_row(current, props))
            current = await _parent(graph, current)
        if current and (current in seen or len(result) >= 64):
            raise ValueError("Goal path has a cycle or exceeds 64 levels")
        result = await _enrich_goals(graph, result)
        return {"dataset_id": str(dataset_id), "goal_id": goal_id, "path": result}


async def goal_detail(dataset_id: UUID, user: User, goal_id: str) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "read")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        props = await graph.get_node(goal_id)
        if not props or _props_type(props) != "Goal":
            raise KeyError("Goal not found in dataset graph")
        row = (await _enrich_goals(graph, [_node_row(goal_id, props)]))[0]
        return {"dataset_id": str(dataset_id), "goal": row}


_PURPOSE_EDGES = """MATCH (s:Node)-[r:EDGE]->(t:Node)
WHERE (s.id = $goal OR t.id = $goal)
  AND r.relationship_name IN ['serves', 'advances', 'blocks']
RETURN s.id, s.name, s.type, t.id, t.name, t.type, r.relationship_name, r.properties"""

_TREE_PAIRS = """MATCH (p:Node)-[h:EDGE]->(c:Node)
WHERE h.relationship_name = 'has_subgoal'
  AND (p.id = $goal OR c.id = $goal)
RETURN p.id, c.id"""


async def goal_relations(
    dataset_id: UUID,
    user: User,
    goal_id: str,
    *,
    relationship: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "read")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        goal = await graph.get_node(goal_id)
        if not goal or _props_type(goal) != "Goal":
            raise KeyError("Goal not found in dataset graph")
        rows = await graph.query(_PURPOSE_EDGES, {"goal": goal_id})
        pair_rows = await graph.query(_TREE_PAIRS, {"goal": goal_id})
        tree_pairs = {
            (str(row[0]), str(row[1])) for row in pair_rows or [] if row and len(row) >= 2
        }
        selected = select_purpose_relations(
            [
                {
                    "source_id": str(row[0]),
                    "source_name": str(row[1] or row[0]),
                    "source_type": str(row[2] or ""),
                    "target_id": str(row[3]),
                    "target_name": str(row[4] or row[3]),
                    "target_type": str(row[5] or ""),
                    "relationship": str(row[6]),
                    "properties": edge_properties(row[7] if len(row) > 7 else None),
                }
                for row in rows or []
                if row and len(row) >= 7
            ],
            tree_pairs,
        )
        selected.sort(
            key=lambda edge: (
                edge["relationship"],
                str(edge.get("source_name") or ""),
                str(edge["source_id"]),
                str(edge["target_id"]),
            )
        )
        by_type = {key: 0 for key in ("serves", "advances", "blocks")}
        for edge in selected:
            by_type[edge["relationship"]] += 1
        wanted = relationship or ""
        visible = [edge for edge in selected if not wanted or edge["relationship"] == wanted]
        page = visible[offset : offset + limit]
        items = [
            {
                "source_id": edge["source_id"],
                "source_name": edge.get("source_name") or edge["source_id"],
                "source_type": edge.get("source_type") or "",
                "target_id": edge["target_id"],
                "target_name": edge.get("target_name") or edge["target_id"],
                "target_type": edge.get("target_type") or "",
                "relationship": edge["relationship"],
                "origin": (edge.get("properties") or {}).get("origin"),
                "reason": (edge.get("properties") or {}).get("reason") or "",
                "evidence_node_ids": (edge.get("properties") or {}).get("evidence_node_ids") or [],
            }
            for edge in page
        ]
        total = by_type.get(relationship, 0) if relationship else sum(by_type.values())
        return {
            "dataset_id": str(dataset_id),
            "goal_id": goal_id,
            "items": items,
            "counts": by_type,
            "total": total,
            "offset": offset,
            "limit": limit,
        }


def _editable(props: dict[str, Any] | None) -> bool:
    return bool(
        props
        and _props_type(props) == "Goal"
        and not props.get("cpd_kind")
        and props.get("source") == "teleology_workspace"
    )


async def _mark_dirty(dataset_id: UUID, goal_ids: list[str], reason: str) -> None:
    from cognee.modules.teleology.coverage_dirty import mark_teleology_dirty

    await mark_teleology_dirty(dataset_id, goal_ids, reason)


async def create_goal(
    dataset_id: UUID,
    user: User,
    *,
    parent_id: str,
    name: str,
    description: str = "",
    owner: str | None = None,
) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        parent = await graph.get_node(parent_id)
        if not parent or _props_type(parent) != "Goal":
            raise KeyError("Parent goal not found in dataset graph")
        goal = Goal(
            name=name.strip(),
            description=description,
            owner=owner,
            primary_purpose_id=None,
            primary_purpose_relation=None,
            source="teleology_workspace",
        )
        await graph.add_nodes([goal])
        await graph.add_edges(
            [
                (
                    parent_id,
                    str(goal.id),
                    "has_subgoal",
                    {"edge_text": "has_subgoal", "relationship_name": "has_subgoal"},
                )
            ]
        )
        await _mark_dirty(dataset_id, [parent_id, str(goal.id)], "child_added")
        return {
            "dataset_id": str(dataset_id),
            "goal": _node_row(str(goal.id), goal.model_dump(mode="json")),
            "parent_id": parent_id,
        }


async def update_goal(
    dataset_id: UUID,
    user: User,
    goal_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    owner: str | None | object = _UNSET,
    progress: int | None | object = _UNSET,
    status: str | None = None,
    primary_purpose_id: str | None | object = _UNSET,
    primary_purpose_relation: str | None | object = _UNSET,
) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        props = await graph.get_node(goal_id)
        if not _editable(props):
            raise ValueError("Only goals created in this workspace can be edited")
        if isinstance(primary_purpose_id, str) and primary_purpose_id:
            purpose = await graph.get_node(primary_purpose_id)
            if not purpose or _props_type(purpose) != "Goal":
                raise KeyError("Primary purpose goal not found")
        if primary_purpose_relation not in (_UNSET, None, "serves", "advances"):
            raise ValueError("Primary purpose relation must be serves or advances")
        updated = Goal(
            id=UUID(goal_id),
            **({"created_at": props["created_at"]} if props.get("created_at") else {}),
            name=name if name is not None else props.get("name"),
            description=description if description is not None else props.get("description", ""),
            status=status if status is not None else props.get("status", "proposed"),
            owner=owner if owner is not _UNSET else props.get("owner"),
            progress=progress if progress is not _UNSET else props.get("progress"),
            primary_purpose_id=primary_purpose_id
            if primary_purpose_id is not _UNSET
            else props.get("primary_purpose_id"),
            primary_purpose_relation=primary_purpose_relation
            if primary_purpose_relation is not _UNSET
            else props.get("primary_purpose_relation"),
            source="teleology_workspace",
        )
        await graph.add_nodes([updated])
        text_changed = (name is not None and name != props.get("name")) or (
            description is not None and description != (props.get("description") or "")
        )
        if text_changed:
            await _mark_dirty(dataset_id, [goal_id], "goal_text_changed")
        return {
            "dataset_id": str(dataset_id),
            "goal": _node_row(goal_id, updated.model_dump(mode="json")),
        }


async def move_goal(dataset_id: UUID, user: User, goal_id: str, parent_id: str) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        goal, new_parent = await graph.get_node(goal_id), await graph.get_node(parent_id)
        if not _editable(goal):
            raise ValueError("Only goals created in this workspace can be moved")
        if not new_parent or _props_type(new_parent) != "Goal":
            raise KeyError("New parent goal not found")
        if goal_id == parent_id:
            raise ValueError("A goal cannot be its own parent")
        old_parent = await _parent(graph, goal_id)
        if old_parent == parent_id:
            return {"dataset_id": str(dataset_id), "goal_id": goal_id, "parent_id": parent_id}
        seen: set[str] = set()
        current: str | None = parent_id
        while current and current not in seen and len(seen) < 64:
            if current == goal_id:
                raise ValueError("Moving a goal under its descendant would create a cycle")
            seen.add(current)
            current = await _parent(graph, current)
        if current:
            raise ValueError("New parent path has a cycle or exceeds 64 levels")
        if old_parent:
            await graph.delete_edge_triples(
                [
                    EdgeIdentity(
                        source_id=old_parent, target_id=goal_id, relationship_name="has_subgoal"
                    )
                ]
            )
        await graph.add_edges(
            [
                (
                    parent_id,
                    goal_id,
                    "has_subgoal",
                    {"edge_text": "has_subgoal", "relationship_name": "has_subgoal"},
                )
            ]
        )
        moved = [goal_id, parent_id]
        if old_parent:
            moved.append(old_parent)
        await _mark_dirty(dataset_id, moved, "child_moved")
        return {"dataset_id": str(dataset_id), "goal_id": goal_id, "parent_id": parent_id}


async def delete_goal(dataset_id: UUID, user: User, goal_id: str) -> dict[str, Any]:
    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        props = await graph.get_node(goal_id)
        if not _editable(props):
            raise ValueError("Only goals created in this workspace can be deleted")
        rows = await graph.query(
            """MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id = $id AND r.relationship_name = 'has_subgoal'
            RETURN c.id LIMIT 1""",
            {"id": goal_id},
        )
        if rows:
            raise ValueError("Move or delete direct subgoals before deleting this goal")
        parent = await _parent(graph, goal_id)
        await graph.delete_nodes([goal_id])
        removed = [goal_id]
        if parent:
            removed.append(parent)
        await _mark_dirty(dataset_id, removed, "child_removed")
        return {"dataset_id": str(dataset_id), "goal_id": goal_id, "deleted": True}
