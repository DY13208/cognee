"""Manual teleology edges on dataset graphs (serves / advances / blocks).

Cognify can auto-link via YAML keyword matching. These helpers let callers
inspect and edit the same edges on an existing graph so recall/search can
scope by ``goal_id``.
"""

from __future__ import annotations

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


async def list_graph_annotations(
    dataset_id: UUID,
    user: User,
    *,
    q: str | None = None,
    limit: int = 200,
    goals_limit: int = 120,
    goal_id: str | None = None,
) -> dict[str, Any]:
    """Return goals, annotatable nodes, and teleology edges for a dataset graph.

    Large CPD datasets can have 10k+ Goal nodes — always cap ``goals`` /
    ``annotations`` in the payload so the UI stays responsive. Pass ``goal_id``
    to scope purpose edges to that goal's 1-hop neighbourhood.
    """
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine

    dataset = await _authorized_dataset(dataset_id, user, "read")
    needle = (q or "").strip().lower()
    cap = max(1, min(int(limit or 200), 1000))
    goals_cap = max(0, min(int(goals_limit if goals_limit is not None else 120), 500))
    focus = (goal_id or "").strip() or None

    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        nodes, edges = await graph.get_graph_data()
        by_id, annotations = _index_graph(nodes, edges)

        if focus:
            neighbor = {focus}
            scoped = []
            for row in annotations:
                if row["source_id"] == focus or row["target_id"] == focus:
                    neighbor.add(row["source_id"])
                    neighbor.add(row["target_id"])
                    scoped.append(row)
            annotations = scoped
            # Also include company-tree parent/child hops as synthetic advances
            # only when no teleology edges exist yet — cheap structural hint.
            if not annotations:
                for source_id, target_id, relationship, _props in edges:
                    sid, tid = str(source_id), str(target_id)
                    rel = str(relationship or "").lower()
                    if rel != "has_subgoal":
                        continue
                    # parent → child in tree; teleology advances is child → parent
                    if sid == focus or tid == focus:
                        child_id, parent_id = tid, sid
                        neighbor.add(child_id)
                        neighbor.add(parent_id)
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

        goals = [
            _node_row(node_id, props)
            for node_id, props in by_id.items()
            if _props_type(props) in _TELEOLOGY_NODE_TYPES
        ]
        if focus:
            goals = [row for row in goals if row["id"] in neighbor] or [
                _node_row(focus, by_id.get(focus))
            ]
        if needle:
            def _goal_hay(row: dict[str, Any]) -> str:
                return f"{row.get('name') or ''} {row.get('description') or ''} {row.get('id') or ''}".lower()

            goals = [row for row in goals if needle in _goal_hay(row)]
        # CPD company-tree goals first — they are the production purpose source.
        goals.sort(
            key=lambda row: (
                0 if row.get("cpd_kind") == "goal" else 1 if row.get("cpd_kind") else 2,
                row["type"],
                row["name"],
            )
        )
        goals_total = len(goals)
        goals_truncated = goals_total > goals_cap
        goals = goals[:goals_cap]

        candidates = [
            _node_row(node_id, props)
            for node_id, props in by_id.items()
            if _is_annotatable(props)
        ]
        if needle:
            candidates = [
                row
                for row in candidates
                if needle in row["name"].lower()
                or needle in row["type"].lower()
                or needle in row["id"].lower()
            ]
        candidates.sort(key=lambda row: (row["type"], row["name"]))
        truncated = len(candidates) > cap
        candidates = candidates[:cap]

        # Cap purpose-edge payload too — a full CPD sync can create 10k+ advances.
        ann_cap = max(cap, 400)
        annotations_total = len(annotations)
        annotations_truncated = annotations_total > ann_cap
        annotations = annotations[:ann_cap]

        return {
            "dataset_id": str(dataset_id),
            "dataset_name": getattr(dataset, "name", None),
            "goals": goals,
            "goals_total": goals_total,
            "goals_truncated": goals_truncated,
            "nodes": candidates,
            "nodes_truncated": truncated,
            "annotations": annotations,
            "annotations_total": annotations_total,
            "annotations_truncated": annotations_truncated,
            "yaml_goals": [
                {
                    "id": str(node.id),
                    "name": node.name,
                    "type": type(node).__name__,
                    "status": node.status,
                    "description": node.description,
                }
                for node in _yaml_teleology_nodes()
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
    - goals are mirrored into the teleology YAML vocab so the UI / cognify
      keyword path can see them (optional; not required for graph lens/recall)
    """
    from cognee.api.v1.teleology.teleology import TeleologyService
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

    # Mirror into teleology vocabulary (stable graph ids). Optional for UI/cognify.
    yaml_entries = [
        {
            "id": n.id,
            "name": n.name,
            "status": "active" if n.children_complete else "proposed",
            "description": (n.note or "").strip(),
            "keywords": [],
        }
        for n in goal_nodes
    ]
    yaml_upserted = TeleologyService().upsert_goals(yaml_entries)

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
            nodes, _edges = await graph.get_graph_data()
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

        nodes, edges = await graph.get_graph_data()
        by_id, annotations = _index_graph(nodes, edges)
        goals = [
            _node_row(node_id, props)
            for node_id, props in by_id.items()
            if _props_type(props) in _TELEOLOGY_NODE_TYPES
        ]
        goals.sort(
            key=lambda row: (
                0 if row.get("cpd_kind") == "goal" else 1 if row.get("cpd_kind") else 2,
                row["type"],
                row["name"],
            )
        )

    return {
        "dataset_id": str(dataset_id),
        "tree_goals": len(goal_nodes),
        "advances_created": advances_created,
        "serves_created": serves_created,
        "yaml_upserted": yaml_upserted,
        "goals": goals,
        "annotations": annotations,
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
