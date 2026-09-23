from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.company_tree.assemble import assemble_company_tree
from cognee.modules.company_tree.schema import (
    CompanyTreeNode,
    CompanyTreeOut,
    CompanyTreeWriteRequest,
    edge_label_for,
    make_source_key,
    parse_source_key,
    validate_write_payload,
)
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.modules.data.methods import get_authorized_dataset
from cognee.modules.users.models import User


async def _load_graph(dataset_id: UUID, user: User, permission_type: str):
    dataset = await get_authorized_dataset(user, dataset_id, permission_type)
    if not dataset:
        raise DatasetNotFoundError(message="Dataset not found.")
    async with set_database_global_context_variables(dataset_id, dataset.owner_id):
        graph = await get_graph_engine()
        nodes, edges = await graph.get_graph_data()
        return dataset, graph, nodes, edges


async def get_company_tree(
    dataset_id: UUID,
    user: User,
    source_room: Optional[str] = None,
) -> CompanyTreeOut:
    _dataset, _graph, nodes, edges = await _load_graph(dataset_id, user, "read")
    return assemble_company_tree(nodes, edges, source_room)


def _existing_by_source_key(nodes) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    found: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for node_id, props in nodes:
        key = str((props or {}).get("source_key") or "")
        if key:
            found[key] = (str(node_id), props or {})
    return found


async def upsert_company_tree(
    dataset_id: UUID,
    user: User,
    payload: CompanyTreeWriteRequest,
) -> CompanyTreeOut:
    validate_write_payload(payload)
    _dataset, graph, nodes, _edges = await _load_graph(dataset_id, user, "write")
    existing = _existing_by_source_key(nodes)
    written: List[CompanyTreeNode] = []
    uid_to_id: Dict[str, str] = {}
    room_of = {item.source_uid: item.source_room or payload.source_room for item in payload.nodes}

    for item in payload.nodes:
        room = room_of[item.source_uid]
        source_key = make_source_key(room, item.source_uid)
        parent_key = (
            make_source_key(room_of[item.source_parent_uid], item.source_parent_uid)
            if item.source_parent_uid and item.source_parent_uid in room_of
            else None
        )
        ctor: Dict[str, Any] = {
            "name": item.name,
            "cpd_kind": item.cpd_kind,
            "source_room": room,
            "source_scope": payload.source_scope,
            "source_uid": item.source_uid,
            "source_key": source_key,
            "source_parent_key": parent_key,
            "source_child_count": item.source_child_count,
            "source_children_complete": item.source_children_complete,
            "source_position": item.source_position,
            "source_note": item.source_note,
            "source_uri": item.source_uri,
            "linked_map_uri": item.linked_map_uri,
            "source_revision": item.source_revision or payload.source_revision,
        }
        prior = existing.get(source_key)
        if prior is not None:
            prior_id, prior_props = prior
            skip = {"created_at", "updated_at", "id", "type"}
            merged = {k: v for k, v in prior_props.items() if k not in skip}
            merged.update(ctor)
            ctor = merged
            ctor["id"] = UUID(str(prior_id))
        node = CompanyTreeNode(**ctor)
        object.__setattr__(node, "type", "Goal")
        written.append(node)
        uid_to_id[item.source_uid] = str(node.id)

    await graph.add_nodes(written)
    tree_edges = []
    for item in payload.nodes:
        if item.source_parent_uid is None:
            continue
        tree_edges.append(
            (
                uid_to_id[item.source_parent_uid],
                uid_to_id[item.source_uid],
                edge_label_for(item.cpd_kind),
                {"edge_text": edge_label_for(item.cpd_kind)},
            )
        )
    if tree_edges:
        await graph.add_edges(tree_edges)

    nodes, edges = await graph.get_graph_data()
    return assemble_company_tree(nodes, edges, payload.source_room)


async def reconcile_company_tree(
    dataset_id: UUID,
    user: User,
    source_room: Optional[str] = None,
) -> CompanyTreeOut:
    """Stamp Goal ancestors that belong to the tree but were written without
    company-tree fields. Does not invent nodes; only fills the write contract
    on members assemble_company_tree already includes."""
    _dataset, graph, nodes, edges = await _load_graph(dataset_id, user, "write")
    assembled = assemble_company_tree(nodes, edges, source_room)
    if assembled.root_id is None:
        return assembled
    room = source_room or infer_room_from_tree(assembled)
    if not room:
        return assembled
    by_id = {str(nid): props or {} for nid, props in nodes}
    parent_of = {e.target: e.source for e in assembled.edges}
    to_stamp: List[CompanyTreeNode] = []
    for member in assembled.nodes:
        if member.stamped:
            continue
        props = dict(by_id.get(member.id) or {})
        uid = member.source_uid
        if not uid:
            parsed = parse_source_key(member.source_key)
            uid = parsed[1] if parsed else member.id
        parent_id = parent_of.get(member.id)
        parent_key = None
        if parent_id:
            parent_member = next((n for n in assembled.nodes if n.id == parent_id), None)
            parent_key = parent_member.source_key if parent_member else None
        skip = {"created_at", "updated_at", "id", "type"}
        merged = {k: v for k, v in props.items() if k not in skip}
        merged.update(
            {
                "id": UUID(str(member.id)),
                "name": member.name,
                "cpd_kind": member.kind,
                "source_room": room,
                "source_uid": uid,
                "source_key": member.source_key or make_source_key(room, uid),
                "source_parent_key": parent_key,
                "source_child_count": max(member.expected_children, 0),
                "source_children_complete": member.children_complete,
                "source_position": member.position,
                "source_note": member.note,
                "source_uri": member.source_uri,
                "linked_map_uri": member.linked_uri,
                "source_revision": member.revision or assembled.revision,
            }
        )
        stamped = CompanyTreeNode(**merged)
        object.__setattr__(stamped, "type", "Goal")
        to_stamp.append(stamped)
    if to_stamp:
        await graph.add_nodes(to_stamp)
        nodes, edges = await graph.get_graph_data()
        return assemble_company_tree(nodes, edges, room)
    return assembled


def infer_room_from_tree(tree: CompanyTreeOut) -> Optional[str]:
    for node in tree.nodes:
        parsed = parse_source_key(node.source_key)
        if parsed:
            return parsed[0]
    return None
