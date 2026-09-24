"""Manual teleology edges on dataset graphs (serves / advances / blocks).

Cognify can auto-link via YAML keyword matching. These helpers let callers
inspect and edit the same edges on an existing graph so recall/search can
scope by ``goal_id``.
"""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from cognee.modules.teleology.goal_scoped_retrieval import (
    TELEOLOGY_RELATIONSHIPS,
    _unpack_edge,
)
from cognee.modules.teleology.models import Constraint, Goal, Purpose
from cognee.modules.teleology.resolve_teleology_file_path import resolve_teleology_file_path
from cognee.modules.teleology.yaml import YamlTeleologyResolver
from cognee.modules.users.models import User

TeleologyRelationship = Literal["serves", "advances", "blocks"]

_TELEOLOGY_NODE_TYPES = frozenset({"Goal", "Purpose", "Constraint"})
# Structural / pipeline nodes rarely carry purpose; keep the picker focused.
_SKIP_NODE_TYPES = frozenset(
    {
        "Document",
        "TextDocument",
        "PdfDocument",
        "AudioDocument",
        "ImageDocument",
        "UnstructuredDocument",
        "DocumentChunk",
        "TextSummary",
        "CodeFile",
        "CodeSymbol",
        "CodeModule",
        "CodeRepository",
        "CodeInsight",
    }
)


async def _authorized_dataset(dataset_id: UUID, user: User, permission_type: str):
    from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
    from cognee.modules.data.methods import get_authorized_dataset

    dataset = await get_authorized_dataset(user, dataset_id, permission_type)
    if not dataset:
        raise DatasetNotFoundError(message="Dataset not found.")
    return dataset


def _props_name(props: dict[str, Any] | None) -> str:
    if not props:
        return ""
    for key in ("name", "text", "title", "label"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _props_type(props: dict[str, Any] | None) -> str:
    if not props:
        return ""
    return str(props.get("type") or props.get("node_type") or "").strip()


def _node_row(node_id: str, props: dict[str, Any] | None) -> dict[str, Any]:
    props = props or {}
    cpd_kind = str(props.get("cpd_kind") or "").strip() or None
    return {
        "id": str(node_id),
        "name": _props_name(props) or str(node_id),
        "type": _props_type(props),
        "description": str(props.get("description") or props.get("source_note") or "").strip(),
        "status": str(props.get("status") or "").strip() or None,
        "cpd_kind": cpd_kind,
        "source": "company_tree" if cpd_kind else None,
    }


def _is_annotatable(props: dict[str, Any] | None) -> bool:
    node_type = _props_type(props)
    if node_type in _TELEOLOGY_NODE_TYPES or node_type in _SKIP_NODE_TYPES:
        return False
    # Prefer named knowledge nodes; anonymous ids alone are hard to pick in UI.
    return bool(_props_name(props))


def _normalize_relationship(relationship: str) -> TeleologyRelationship:
    rel = str(relationship or "").strip().lower()
    if rel not in TELEOLOGY_RELATIONSHIPS:
        raise ValueError(
            f"Invalid relationship {relationship!r}. "
            f"Valid: {', '.join(sorted(TELEOLOGY_RELATIONSHIPS))}."
        )
    return rel  # type: ignore[return-value]


def _yaml_teleology_nodes() -> list[Goal | Purpose | Constraint]:
    path = resolve_teleology_file_path()
    if not path.is_file():
        return []
    resolver = YamlTeleologyResolver(path)
    return [
        *resolver.get_goals(),
        *resolver.get_purposes(),
        *resolver.get_constraints(),
    ]


def _index_graph(
    nodes: list, edges: list
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw_id, props in nodes:
        node_id = str(raw_id)
        by_id[node_id] = props or {}

    annotations: list[dict[str, Any]] = []
    for edge in edges:
        if isinstance(edge, (tuple, list)) and len(edge) >= 3:
            if len(edge) >= 4 and isinstance(edge[0], (str, int)) and isinstance(edge[1], (str, int)):
                source_id, target_id, relationship = str(edge[0]), str(edge[1]), str(edge[2])
            else:
                unpacked = _unpack_edge(edge)
                if unpacked is None:
                    continue
                source_id, relationship, target_id = unpacked
                if source_id is None or target_id is None:
                    continue
        else:
            continue
        if relationship.lower() not in TELEOLOGY_RELATIONSHIPS:
            continue
        source_props = by_id.get(source_id, {})
        target_props = by_id.get(target_id, {})
        annotations.append(
            {
                "source_id": source_id,
                "source_name": _props_name(source_props) or source_id,
                "source_type": _props_type(source_props),
                "target_id": target_id,
                "target_name": _props_name(target_props) or target_id,
                "target_type": _props_type(target_props),
                "relationship": relationship.lower(),
            }
        )
    annotations.sort(key=lambda row: (row["relationship"], row["source_name"], row["target_name"]))
    return by_id, annotations


def _parse_node_props(raw_props: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if isinstance(raw_props, dict):
        props = dict(raw_props)
        nested = props.pop("properties", None)
        if nested:
            try:
                props.update(json.loads(nested) if isinstance(nested, str) else nested)
            except (TypeError, json.JSONDecodeError, ValueError):
                pass
    elif isinstance(raw_props, str) and raw_props.strip():
        try:
            props.update(json.loads(raw_props))
        except (TypeError, json.JSONDecodeError, ValueError):
            pass
    return props


async def _count_teleology_goals(graph: Any) -> int:
    types = list(_TELEOLOGY_NODE_TYPES)
    try:
        rows = await graph.query(
            """
            MATCH (n:Node)
            WHERE n.type IN $types
            RETURN count(n)
            """,
            {"types": types},
        )
        if rows and rows[0]:
            return int(rows[0][0] or 0)
    except Exception:
        pass
    return -1


async def _fetch_goals_page(
    graph: Any,
    *,
    needle: str,
    limit: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Bounded Goal/Purpose/Constraint listing — never scans the full graph."""
    if limit <= 0:
        return []
    skip = max(0, int(offset or 0))
    types = list(_TELEOLOGY_NODE_TYPES)
    needle = (needle or "").strip()
    rows: list[Any] = []
    try:
        if needle:
            # Push the filter into Cypher when possible — Python post-filter over
            # thousands of CPD goals made the purpose picker feel broken.
            try:
                rows = await graph.query(
                    """
                    MATCH (n:Node)
                    WHERE n.type IN $types AND n.name CONTAINS $needle
                    RETURN n.id, n.name, n.type, n.properties
                    LIMIT $limit
                    """,
                    {
                        "types": types,
                        "needle": needle,
                        "limit": min(skip + limit, 200),
                    },
                )
            except Exception:
                rows = await graph.query(
                    """
                    MATCH (n:Node)
                    WHERE n.type IN $types
                    RETURN n.id, n.name, n.type, n.properties
                    LIMIT $limit
                    """,
                    {"types": types, "limit": min(max((skip + limit) * 8, limit), 800)},
                )
        else:
            rows = await graph.query(
                """
                MATCH (n:Node)
                WHERE n.type IN $types
                RETURN n.id, n.name, n.type, n.properties
                LIMIT $limit
                """,
                {"types": types, "limit": min(skip + limit, 2000)},
            )
    except Exception:
        try:
            nodes, _edges = await graph.get_filtered_graph_data([{"type": types}])
            rows = [
                (nid, (props or {}).get("name"), (props or {}).get("type"), props)
                for nid, props in nodes
            ]
        except Exception:
            return []

    needle_l = needle.lower()
    goals: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        node_id = str(row[0])
        name = str(row[1] or "")
        node_type = str(row[2] or "Goal")
        props = _parse_node_props(row[3] if len(row) > 3 else None)
        props.setdefault("name", name)
        props.setdefault("type", node_type)
        row_out = _node_row(node_id, props)
        if needle_l:
            hay = f"{row_out['name']} {row_out.get('description') or ''} {row_out['id']}".lower()
            hay2 = (
                hay.replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("<p>", " ")
                .replace("</p>", " ")
            )
            # CONTAINS may already have filtered; keep Python filter for fallback path.
            if needle_l not in hay and needle_l not in hay2:
                continue
        goals.append(row_out)

    goals.sort(
        key=lambda row: (
            0 if row.get("cpd_kind") == "goal" else 1 if row.get("cpd_kind") else 2,
            0 if needle_l and row["name"].lower().startswith(needle_l) else 1,
            row["type"],
            row["name"],
        )
    )
    return goals[skip : skip + limit]


async def _list_goal_roots(graph: Any, *, limit: int = 40) -> list[dict[str, Any]]:
    """Top-level CPD goals (no incoming has_subgoal)."""
    if limit <= 0:
        return []
    try:
        rows = await graph.query(
            """
            MATCH (n:Node)
            WHERE n.type = 'Goal'
            OPTIONAL MATCH (p:Node)-[r:EDGE]->(n)
            WHERE r.relationship_name = 'has_subgoal'
            WITH n, count(p) AS parents
            WHERE parents = 0
            RETURN n.id, n.name, n.type, n.properties
            LIMIT $limit
            """,
            {"limit": limit},
        )
    except Exception:
        return await _fetch_goals_page(graph, needle="", limit=limit)
    goals: list[dict[str, Any]] = []
    for row in rows or []:
        if not row:
            continue
        props = _parse_node_props(row[3] if len(row) > 3 else None)
        props.setdefault("name", str(row[1] or ""))
        props.setdefault("type", str(row[2] or "Goal"))
        goals.append(_node_row(str(row[0]), props))
    return goals


async def _list_goal_children(
    graph: Any,
    parent_id: str,
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Direct has_subgoal children of a goal — for tree drill-down in the picker."""
    if limit <= 0 or not parent_id:
        return []
    try:
        rows = await graph.query(
            """
            MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id = $pid AND r.relationship_name = 'has_subgoal'
            RETURN c.id, c.name, c.type, c.properties
            LIMIT $limit
            """,
            {"pid": parent_id, "limit": limit},
        )
    except Exception:
        return []
    goals: list[dict[str, Any]] = []
    for row in rows or []:
        if not row:
            continue
        props = _parse_node_props(row[3] if len(row) > 3 else None)
        props.setdefault("name", str(row[1] or ""))
        props.setdefault("type", str(row[2] or "Goal"))
        goals.append(_node_row(str(row[0]), props))
    return goals


async def _attach_child_counts(
    graph: Any,
    goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add child_count (direct has_subgoal children) for browse drill-down affordances."""
    if not goals:
        return goals
    ids = [g["id"] for g in goals]
    counts: dict[str, int] = {}
    try:
        rows = await graph.query(
            """
            MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE p.id IN $ids AND r.relationship_name = 'has_subgoal'
            RETURN p.id, count(c)
            """,
            {"ids": ids},
        )
        for row in rows or []:
            if not row:
                continue
            counts[str(row[0])] = int(row[1] or 0)
    except Exception:
        pass
    for g in goals:
        g["child_count"] = int(counts.get(g["id"], 0))
    return goals


async def _attach_parent_paths(
    graph: Any,
    goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add parent_name / parent_id so the picker can show where a hit sits."""
    if not goals:
        return goals
    ids = [g["id"] for g in goals]
    parent_by_child: dict[str, tuple[str, str]] = {}
    try:
        rows = await graph.query(
            """
            MATCH (p:Node)-[r:EDGE]->(c:Node)
            WHERE c.id IN $ids AND r.relationship_name = 'has_subgoal'
            RETURN c.id, p.id, p.name
            """,
            {"ids": ids},
        )
        for row in rows or []:
            if not row:
                continue
            parent_by_child[str(row[0])] = (str(row[1]), str(row[2] or ""))
    except Exception:
        pass
    out: list[dict[str, Any]] = []
    for g in goals:
        row = dict(g)
        parent = parent_by_child.get(g["id"])
        if parent:
            row["parent_id"] = parent[0]
            row["parent_name"] = parent[1]
        else:
            row["parent_id"] = None
            row["parent_name"] = None
        out.append(row)
    return out


async def _find_cpd_root(graph: Any) -> str | None:
    """Prefer a company-tree root (no incoming has_subgoal), else any Goal."""
    try:
        named = await graph.query(
            """
            MATCH (n:Node)
            WHERE n.type = 'Goal' AND n.name CONTAINS $needle
            RETURN n.id
            LIMIT 3
            """,
            {"needle": "公司运营"},
        )
        if named and named[0] and named[0][0]:
            return str(named[0][0])
    except Exception:
        pass
    try:
        roots = await graph.query(
            """
            MATCH (n:Node)
            WHERE n.type = 'Goal'
            OPTIONAL MATCH (p:Node)-[r:EDGE]->(n)
            WHERE r.relationship_name = 'has_subgoal'
            WITH n, count(p) AS parents
            WHERE parents = 0
            RETURN n.id
            LIMIT 1
            """,
            {},
        )
        if roots and roots[0] and roots[0][0]:
            return str(roots[0][0])
    except Exception:
        pass
    try:
        any_goal = await graph.query(
            """
            MATCH (n:Node)
            WHERE n.type = 'Goal'
            RETURN n.id
            LIMIT 1
            """,
            {},
        )
        if any_goal and any_goal[0] and any_goal[0][0]:
            return str(any_goal[0][0])
    except Exception:
        pass
    return None


async def _connected_preview(
    graph: Any,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return a connected CPD slice (goals + advances/serves annotations + candidates)."""
    root_id = await _find_cpd_root(graph)
    if not root_id:
        goals = await _fetch_goals_page(graph, needle="", limit=limit)
        return goals, [], []

    try:
        nodes, edges = await graph.get_neighborhood(
            [root_id],
            depth=2,
            edge_types=["has_subgoal", "serves", "advances", "blocks"],
        )
    except Exception:
        goals = await _fetch_goals_page(graph, needle="", limit=limit)
        return goals, [], []

    by_id = {str(nid): (props or {}) for nid, props in nodes}
    if root_id not in by_id:
        try:
            focus_node = await graph.get_node(root_id)
            if focus_node:
                by_id[root_id] = focus_node
        except Exception:
            pass

    goal_rows = [
        _node_row(nid, props)
        for nid, props in by_id.items()
        if _props_type(props) in _TELEOLOGY_NODE_TYPES
    ]
    # Keep root first, then fill up to limit.
    goal_rows.sort(
        key=lambda row: (
            0 if row["id"] == root_id else 1,
            0 if row.get("cpd_kind") == "goal" else 1,
            row["name"],
        )
    )
    goals = goal_rows[: max(1, limit)]
    keep = {g["id"] for g in goals}
    if root_id not in keep and root_id in by_id:
        goals = [_node_row(root_id, by_id[root_id])] + goals
        goals = goals[: max(1, limit)]
        keep = {g["id"] for g in goals}

    annotations: list[dict[str, Any]] = []
    for source_id, target_id, relationship, _props in edges:
        sid, tid = str(source_id), str(target_id)
        if sid not in keep or tid not in keep:
            continue
        rel = str(relationship or "").lower()
        if rel == "has_subgoal":
            child_id, parent_id = tid, sid
            annotations.append(
                {
                    "source_id": child_id,
                    "source_name": _props_name(by_id.get(child_id)) or child_id,
                    "source_type": _props_type(by_id.get(child_id)) or "Goal",
                    "target_id": parent_id,
                    "target_name": _props_name(by_id.get(parent_id)) or parent_id,
                    "target_type": _props_type(by_id.get(parent_id)) or "Goal",
                    "relationship": "advances",
                }
            )
        elif rel in TELEOLOGY_RELATIONSHIPS:
            annotations.append(
                {
                    "source_id": sid,
                    "source_name": _props_name(by_id.get(sid)) or sid,
                    "source_type": _props_type(by_id.get(sid)),
                    "target_id": tid,
                    "target_name": _props_name(by_id.get(tid)) or tid,
                    "target_type": _props_type(by_id.get(tid)),
                    "relationship": rel,
                }
            )

    candidates = [
        _node_row(nid, props)
        for nid, props in by_id.items()
        if nid in keep and _is_annotatable(props)
    ]
    return goals, annotations, candidates


async def _materialize_advances(
    graph: Any,
    annotations: list[dict[str, Any]],
) -> int:
    """Persist synthetic advances so recall(goal_id=...) works without a full-tree sync."""
    created = 0
    for row in annotations:
        if str(row.get("relationship") or "").lower() != "advances":
            continue
        child_id = str(row["source_id"])
        parent_id = str(row["target_id"])
        try:
            if await graph.has_edge(child_id, parent_id, "advances"):
                continue
            await graph.add_edges(
                [
                    (
                        child_id,
                        parent_id,
                        "advances",
                        {"edge_text": "advances", "relationship_name": "advances"},
                    )
                ]
            )
            created += 1
        except Exception:
            continue
    return created


async def _edges_among_ids(
    graph: Any,
    node_ids: list[str],
    *,
    relationship_names: frozenset[str],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    if not node_ids:
        return []
    try:
        rows = await graph.query(
            """
            MATCH (a:Node)-[r:EDGE]->(b:Node)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN a.id, b.id, r.relationship_name, r.properties
            """,
            {"ids": node_ids},
        )
    except Exception:
        return []
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    for row in rows or []:
        if not row:
            continue
        rel = str(row[2] or "").lower()
        if rel not in relationship_names:
            continue
        props = _parse_node_props(row[3] if len(row) > 3 else None)
        out.append((str(row[0]), str(row[1]), rel, props))
    return out


async def list_graph_annotations(
    dataset_id: UUID,
    user: User,
    *,
    q: str | None = None,
    limit: int = 200,
    goals_limit: int = 120,
    goals_offset: int = 0,
    goal_id: str | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Return goals, annotatable nodes, and teleology edges for a dataset graph.

    Uses bounded Cypher queries (LIMIT / neighbourhood) so large CPD trees
    (~10k goals) do not force a full ``get_graph_data()`` scan on every open.

    ``parent_id``: tree drill-down for the purpose picker.
    - ``parent_id="_roots"`` → top-level goals (no incoming has_subgoal)
    - ``parent_id=<uuid>`` → direct children via has_subgoal
    """
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine

    dataset = await _authorized_dataset(dataset_id, user, "read")
    needle = (q or "").strip().lower()
    cap = max(1, min(int(limit or 200), 1000))
    goals_cap = max(0, min(int(goals_limit if goals_limit is not None else 120), 500))
    goals_skip = max(0, int(goals_offset or 0))
    focus = (goal_id or "").strip() or None
    browse_parent = (parent_id or "").strip() or None

    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()

        goals_total = await _count_teleology_goals(graph)
        annotations: list[dict[str, Any]] = []
        goals: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}

        if focus:
            try:
                nodes, edges = await graph.get_neighborhood(
                    [focus],
                    depth=1,
                    edge_types=["serves", "advances", "blocks", "has_subgoal"],
                )
            except Exception:
                nodes, edges = [], []
            by_id = {str(nid): (props or {}) for nid, props in nodes}
            if focus not in by_id:
                try:
                    focus_node = await graph.get_node(focus)
                    if focus_node:
                        by_id[focus] = focus_node
                except Exception:
                    pass
            for source_id, target_id, relationship, props in edges:
                sid, tid = str(source_id), str(target_id)
                rel = str(relationship or "").lower()
                if rel == "has_subgoal":
                    # Tree parent→child becomes teleology advances child→parent.
                    child_id, parent_id = tid, sid
                    annotations.append(
                        {
                            "source_id": child_id,
                            "source_name": _props_name(by_id.get(child_id)) or child_id,
                            "source_type": _props_type(by_id.get(child_id)) or "Goal",
                            "target_id": parent_id,
                            "target_name": _props_name(by_id.get(parent_id)) or parent_id,
                            "target_type": _props_type(by_id.get(parent_id)) or "Goal",
                            "relationship": "advances",
                        }
                    )
                elif rel in TELEOLOGY_RELATIONSHIPS:
                    annotations.append(
                        {
                            "source_id": sid,
                            "source_name": _props_name(by_id.get(sid)) or sid,
                            "source_type": _props_type(by_id.get(sid)),
                            "target_id": tid,
                            "target_name": _props_name(by_id.get(tid)) or tid,
                            "target_type": _props_type(by_id.get(tid)),
                            "relationship": rel,
                        }
                    )
            goals = [
                _node_row(nid, props)
                for nid, props in by_id.items()
                if _props_type(props) in _TELEOLOGY_NODE_TYPES
            ]
            if focus not in {g["id"] for g in goals} and focus in by_id:
                goals.insert(0, _node_row(focus, by_id.get(focus)))
            candidates = [
                _node_row(nid, props)
                for nid, props in by_id.items()
                if _is_annotatable(props)
            ][:cap]
            # Persist advances for this neighbourhood so recall(goal_id) works.
            await _materialize_advances(graph, annotations)
        elif browse_parent is not None and not needle and not focus:
            # Purpose-picker tree drill-down (never dumps 12k flat goals).
            fetch_n = goals_cap if goals_cap > 0 else 40
            if browse_parent in ("_roots", "roots", ""):
                goals = await _list_goal_roots(graph, limit=fetch_n)
            else:
                goals = await _list_goal_children(
                    graph, browse_parent, limit=fetch_n
                )
            goals = await _attach_parent_paths(graph, goals)
            goals = await _attach_child_counts(graph, goals)
            fetch_n = goals_cap if goals_cap > 0 else 24
            if needle or goals_skip > 0:
                # Search / load-more: page of goals only (no full-tree canvas rebuild).
                goals = await _fetch_goals_page(
                    graph, needle=needle, limit=fetch_n, offset=goals_skip
                )
                goals = await _attach_parent_paths(graph, goals)
                goal_ids = [g["id"] for g in goals]
                edge_rows = await _edges_among_ids(
                    graph,
                    goal_ids,
                    relationship_names=TELEOLOGY_RELATIONSHIPS | frozenset({"has_subgoal"}),
                )
                name_by_id = {g["id"]: g["name"] for g in goals}
                type_by_id = {g["id"]: g["type"] for g in goals}
                for sid, tid, rel, _props in edge_rows:
                    if rel == "has_subgoal":
                        child_id, parent_goal_id = tid, sid
                        annotations.append(
                            {
                                "source_id": child_id,
                                "source_name": name_by_id.get(child_id, child_id),
                                "source_type": type_by_id.get(child_id, "Goal"),
                                "target_id": parent_goal_id,
                                "target_name": name_by_id.get(parent_goal_id, parent_goal_id),
                                "target_type": type_by_id.get(parent_goal_id, "Goal"),
                                "relationship": "advances",
                            }
                        )
                    else:
                        annotations.append(
                            {
                                "source_id": sid,
                                "source_name": name_by_id.get(sid, sid),
                                "source_type": type_by_id.get(sid, "Entity"),
                                "target_id": tid,
                                "target_name": name_by_id.get(tid, tid),
                                "target_type": type_by_id.get(tid, "Goal"),
                                "relationship": rel,
                            }
                        )
            else:
                # Default open: connected CPD root slice so the canvas has real lines.
                goals, annotations, candidates = await _connected_preview(
                    graph, limit=fetch_n
                )
                await _materialize_advances(graph, annotations)
                goals = await _attach_parent_paths(graph, goals)

        if goals_total < 0:
            goals_total = len(goals) + goals_skip
        goals_truncated = bool(goals_total > (len(goals) + goals_skip))

        ann_cap = max(cap, 400)
        annotations_total = len(annotations)
        annotations_truncated = annotations_total > ann_cap
        annotations = annotations[:ann_cap]

        # Never dump the full YAML vocab into every annotations response — a
        # prior sync-from-company-tree could have mirrored 10k+ goals there.
        yaml_nodes = _yaml_teleology_nodes()
        yaml_total = len(yaml_nodes)
        yaml_sample = yaml_nodes[: min(40, yaml_total)]

        return {
            "dataset_id": str(dataset_id),
            "dataset_name": getattr(dataset, "name", None),
            "goals": goals,
            "goals_total": goals_total,
            "goals_offset": goals_skip,
            "goals_truncated": goals_truncated,
            "nodes": candidates,
            "nodes_truncated": len(candidates) >= cap,
            "annotations": annotations,
            "annotations_total": annotations_total,
            "annotations_truncated": annotations_truncated,
            "yaml_goals_total": yaml_total,
            "yaml_goals": [
                {
                    "id": str(node.id),
                    "name": node.name,
                    "type": type(node).__name__,
                    "status": node.status,
                    "description": node.description,
                }
                for node in yaml_sample
            ],
        }


async def sync_goals_to_graph(dataset_id: UUID, user: User) -> dict[str, Any]:
    """Upsert YAML Goal / Purpose / Constraint nodes into the dataset graph."""
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine

    dataset = await _authorized_dataset(dataset_id, user, "write")
    yaml_nodes = _yaml_teleology_nodes()
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        if yaml_nodes:
            await graph.add_nodes(list(yaml_nodes))
        nodes, edges = await graph.get_graph_data()
        by_id, annotations = _index_graph(nodes, edges)
        goals = [
            _node_row(node_id, props)
            for node_id, props in by_id.items()
            if _props_type(props) in _TELEOLOGY_NODE_TYPES
        ]
        return {
            "dataset_id": str(dataset_id),
            "synced": len(yaml_nodes),
            "goals": sorted(goals, key=lambda row: (row["type"], row["name"])),
            "annotations": annotations,
        }


def _token_overlap(a: str, b: str) -> bool:
    import re

    stop = {"a", "an", "and", "for", "of", "or", "the", "to", "with", "的", "和", "与"}
    tok = lambda s: {
        t.lower()
        for t in re.findall(r"[\w\u4e00-\u9fff-]{2,}", s or "")
        if t.lower() not in stop
    }
    left, right = tok(a), tok(b)
    if not left or not right:
        return False
    if a.strip() and a.strip().lower() in (b or "").lower():
        return True
    if b.strip() and b.strip().lower() in (a or "").lower():
        return True
    return bool(left & right)


async def sync_from_company_tree(
    dataset_id: UUID,
    user: User,
    *,
    link_entities: bool = True,
    source_room: str | None = None,
) -> dict[str, Any]:
    """CPD goals *are* teleology Goals — reuse the same node ids.

    Company-tree members already persist as graph ``type=Goal`` with
    ``cpd_kind=goal``. This pass only materializes purpose edges:

    - each ``has_subgoal`` parent→child becomes teleology ``advances`` child→parent
    - optionally, knowledge entities whose names overlap a goal get ``serves``

    Does **not** mirror the tree into the teleology YAML — that previously
    wrote 10k+ rows into ``goals.yaml`` and made Manage Goals / get_status
    unusable. Graph nodes are the source of truth for the purpose lens.
    """
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine
    from cognee.modules.company_tree.upsert import get_company_tree

    dataset = await _authorized_dataset(dataset_id, user, "write")
    tree = await get_company_tree(dataset_id, user, source_room)
    goal_nodes = [n for n in tree.nodes if n.kind == "goal"]
    if not goal_nodes:
        return {
            "dataset_id": str(dataset_id),
            "tree_goals": 0,
            "advances_created": 0,
            "serves_created": 0,
            "yaml_upserted": 0,
            "goals": [],
            "annotations": [],
            "message": "No company goal tree on this dataset. Import/build the company tree first.",
        }

    advances_created = 0
    serves_created = 0
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()

        for edge in tree.edges:
            if edge.label != "has_subgoal":
                continue
            # Tree edge is parent → child; teleology advances is child → parent.
            child_id, parent_id = edge.target, edge.source
            if await graph.has_edge(child_id, parent_id, "advances"):
                continue
            await graph.add_edges(
                [
                    (
                        child_id,
                        parent_id,
                        "advances",
                        {"edge_text": "advances", "relationship_name": "advances"},
                    )
                ]
            )
            advances_created += 1

        if link_entities:
            # Cap entity scan — full get_graph_data() on a 12k-goal tree is too
            # expensive for a sync button. Overlap-match against a bounded slice.
            try:
                nodes, _edges = await graph.get_filtered_graph_data(
                    [{"type": ["Entity", "DocumentChunk", "TextDocument"]}]
                )
            except Exception:
                nodes, _edges = await graph.get_graph_data()
            # Soft cap so sync stays interactive on huge graphs.
            if len(nodes) > 4000:
                nodes = nodes[:4000]
            goal_ids = {n.id for n in goal_nodes}
            goal_meta = {n.id: n for n in goal_nodes}
            for raw_id, props in nodes:
                nid = str(raw_id)
                if nid in goal_ids:
                    continue
                if not _is_annotatable(props):
                    continue
                # Skip company-tree structural members (already Goals / refs).
                if (props or {}).get("source_scope") == "company_model_only":
                    continue
                if (props or {}).get("cpd_kind") in ("goal", "map_reference"):
                    continue
                entity_name = _props_name(props)
                entity_text = f"{entity_name} {(props or {}).get('description') or ''}"
                for gid, gnode in goal_meta.items():
                    hay = f"{gnode.name} {gnode.note or ''}"
                    if not _token_overlap(entity_text, hay):
                        continue
                    if await graph.has_edge(nid, gid, "serves"):
                        continue
                    await graph.add_edges(
                        [
                            (
                                nid,
                                gid,
                                "serves",
                                {"edge_text": "serves", "relationship_name": "serves"},
                            )
                        ]
                    )
                    serves_created += 1

        # Sample only — never return the full 10k-goal list in the HTTP body.
        sample_goals = await _fetch_goals_page(graph, needle="", limit=24, offset=0)

    return {
        "dataset_id": str(dataset_id),
        "tree_goals": len(goal_nodes),
        "advances_created": advances_created,
        "serves_created": serves_created,
        "yaml_upserted": 0,
        "goals": sample_goals,
        "annotations": [],
    }


async def add_graph_annotation(
    dataset_id: UUID,
    user: User,
    *,
    source_id: str,
    target_id: str,
    relationship: str,
) -> dict[str, Any]:
    """Persist a serves/advances/blocks edge from a knowledge node to a goal."""
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine

    rel = _normalize_relationship(relationship)
    source_id = str(source_id).strip()
    target_id = str(target_id).strip()
    if not source_id or not target_id:
        raise ValueError("source_id and target_id are required")
    if source_id == target_id:
        raise ValueError("source_id and target_id must differ")

    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        existing = await graph.get_nodes([source_id, target_id])
        found_ids = {str(node.get("id")) for node in existing if node and node.get("id")}
        if source_id not in found_ids:
            raise KeyError(f"Source node '{source_id}' not found in dataset graph")

        if target_id not in found_ids:
            # Auto-materialize a YAML teleology node so annotate does not require a
            # separate sync step when the goal only exists in the YAML file.
            yaml_match = next(
                (node for node in _yaml_teleology_nodes() if str(node.id) == target_id),
                None,
            )
            if yaml_match is None:
                raise KeyError(
                    f"Target node '{target_id}' not found. Sync goals to the graph first."
                )
            await graph.add_nodes([yaml_match])

        if await graph.has_edge(source_id, target_id, rel):
            return {
                "dataset_id": str(dataset_id),
                "created": False,
                "annotation": {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship": rel,
                },
            }

        await graph.add_edges(
            [(source_id, target_id, rel, {"edge_text": rel, "relationship_name": rel})]
        )
        return {
            "dataset_id": str(dataset_id),
            "created": True,
            "annotation": {
                "source_id": source_id,
                "target_id": target_id,
                "relationship": rel,
            },
        }


async def remove_graph_annotation(
    dataset_id: UUID,
    user: User,
    *,
    source_id: str,
    target_id: str,
    relationship: str,
) -> dict[str, Any]:
    """Delete a teleology edge without removing the endpoint nodes."""
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine
    from cognee.infrastructure.databases.provenance import EdgeIdentity

    rel = _normalize_relationship(relationship)
    source_id = str(source_id).strip()
    target_id = str(target_id).strip()
    dataset = await _authorized_dataset(dataset_id, user, "write")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        if not await graph.has_edge(source_id, target_id, rel):
            raise KeyError("Annotation edge not found")
        await graph.delete_edge_triples(
            [EdgeIdentity(source_id=source_id, target_id=target_id, relationship_name=rel)]
        )
        return {
            "dataset_id": str(dataset_id),
            "deleted": True,
            "annotation": {
                "source_id": source_id,
                "target_id": target_id,
                "relationship": rel,
            },
        }
