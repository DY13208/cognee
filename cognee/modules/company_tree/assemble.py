from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cognee.modules.company_tree.schema import (
    COMPANY_SCOPE,
    TREE_EDGE_TYPES,
    CompanyTreeEdgeOut,
    CompanyTreeNodeOut,
    CompanyTreeOut,
    make_source_key,
    parse_source_key,
)

RawNode = Tuple[Any, Dict[str, Any]]
RawEdge = Tuple[Any, Any, str, Optional[Dict[str, Any]]]


def _node_id(node: RawNode) -> str:
    return str(node[0])


def _props(node: RawNode) -> Dict[str, Any]:
    return node[1] or {}


def infer_source_room(nodes: Iterable[RawNode], requested: Optional[str]) -> Optional[str]:
    if requested:
        return requested

    stamped: List[Tuple[str, Dict[str, Any]]] = []
    for n in nodes:
        props = _props(n)
        room = str(props.get("source_room") or "")
        if (
            props.get("source_scope") == COMPANY_SCOPE
            and room
            and props.get("cpd_kind") in ("goal", "map_reference")
        ):
            stamped.append((_node_id(n), props))

    rooms = {str(props.get("source_room")) for _, props in stamped}
    if len(rooms) == 1:
        return rooms.pop()

    if len(rooms) > 1:
        # Linked-map import stamps many rooms under company_model_only. Prefer the
        # company-model root room so the tree never collapses to "empty".
        for _, props in stamped:
            name = str(props.get("name") or "")
            if props.get("cpd_kind") == "goal" and "公司运营" in name:
                return str(props.get("source_room"))

        link_counts: Dict[str, int] = defaultdict(int)
        for _, props in stamped:
            room = str(props.get("source_room") or "")
            if props.get("cpd_kind") == "map_reference" or str(props.get("linked_map_uri") or ""):
                link_counts[room] += 1
        if link_counts:
            return max(link_counts.items(), key=lambda item: item[1])[0]

        room_counts: Dict[str, int] = defaultdict(int)
        for _, props in stamped:
            room_counts[str(props.get("source_room"))] += 1
        return max(room_counts.items(), key=lambda item: item[1])[0]

    keys = []
    for n in nodes:
        parsed = parse_source_key(str(_props(n).get("source_key") or ""))
        if parsed:
            keys.append(parsed[0])
    unique = set(keys)
    if len(unique) == 1:
        return unique.pop()
    if unique:
        counts: Dict[str, int] = defaultdict(int)
        for room in keys:
            counts[room] += 1
        return max(counts.items(), key=lambda item: item[1])[0]
    return None


def _is_stamped(props: Dict[str, Any], room: str) -> bool:
    return (
        props.get("source_scope") == COMPANY_SCOPE
        and str(props.get("source_room") or "") == room
        and props.get("cpd_kind") in ("goal", "map_reference")
    )


def _is_imported_member(props: Dict[str, Any]) -> bool:
    """A company-tree node from this room or from a mind map imported through a link."""
    return (
        props.get("source_scope") == COMPANY_SCOPE
        and bool(str(props.get("source_room") or ""))
        and props.get("cpd_kind") in ("goal", "map_reference")
    )


def _child_count(props: Dict[str, Any]) -> int:
    raw = props.get("source_child_count")
    if raw is None or raw == "":
        return -1
    text = str(raw)
    return int(text) if text.lstrip("-").isdigit() else -1


def _uid_from_props(props: Dict[str, Any]) -> str:
    uid = str(props.get("source_uid") or "")
    if uid:
        return uid
    parsed = parse_source_key(str(props.get("source_key") or ""))
    return parsed[1] if parsed else ""


def assemble_company_tree(
    nodes: List[RawNode],
    edges: List[RawEdge],
    source_room: Optional[str] = None,
) -> CompanyTreeOut:
    """Build the company tree from a dataset graph.

    Stamped `company_model_only` nodes are the seed. Goal nodes that share the
    room's source_key prefix, or that parent those seeds via has_subgoal /
    has_detail_reference, are included so a mixed write path still reads as one
    tree. Linked mind maps imported under a seed stay in the tree even when their
    source room differs. Completeness is reported, never inferred as an empty tree.
    """
    missing: List[str] = []
    room = infer_source_room(nodes, source_room)
    if not room:
        return CompanyTreeOut(missing=["empty"])

    by_id = {_node_id(n): n for n in nodes}
    keep: set[str] = set()
    for n in nodes:
        props = _props(n)
        nid = _node_id(n)
        if _is_stamped(props, room):
            keep.add(nid)
            continue
        parsed = parse_source_key(str(props.get("source_key") or ""))
        if parsed and parsed[0] == room and str(props.get("type") or "") == "Goal":
            keep.add(nid)

    added = True
    while added:
        added = False
        for src, tgt, label, _ in edges:
            if label not in TREE_EDGE_TYPES:
                continue
            sid, tid = str(src), str(tgt)
            if tid in keep and sid not in keep:
                parent = by_id.get(sid)
                if parent is not None and str(_props(parent).get("type") or "") == "Goal":
                    keep.add(sid)
                    added = True
            if sid in keep and tid not in keep:
                child = by_id.get(tid)
                if child is not None and _is_imported_member(_props(child)):
                    keep.add(tid)
                    added = True

    if not keep:
        return CompanyTreeOut(missing=["empty"])

    view_nodes: List[CompanyTreeNodeOut] = []
    for nid in keep:
        raw = by_id[nid]
        props = _props(raw)
        source_key = str(props.get("source_key") or "")
        uid = _uid_from_props(props)
        if not source_key and uid:
            source_key = make_source_key(room, uid)
        kind = props.get("cpd_kind")
        if kind not in ("goal", "map_reference"):
            kind = "goal"
        stamped = _is_stamped(props, room) or _is_imported_member(props)
        if not stamped:
            missing.append(f"unstamped:{nid}")
        view_nodes.append(
            CompanyTreeNodeOut(
                id=nid,
                name=str(props.get("name") or "") or f"{props.get('type')}_{nid}",
                kind=kind,
                source_key=source_key,
                source_uid=uid,
                source_uri=str(props.get("source_uri") or ""),
                revision=str(props.get("source_revision") or ""),
                note=str(props.get("source_note") or ""),
                linked_uri=str(props.get("linked_map_uri") or ""),
                position=str(props.get("source_position") or ""),
                expected_children=_child_count(props),
                children_complete=props.get("source_children_complete") is True,
                stamped=stamped,
            )
        )

    by_view = {n.id: n for n in view_nodes}
    by_key = {n.source_key: n for n in view_nodes if n.source_key}
    tree_edges: List[CompanyTreeEdgeOut] = []
    parents: Dict[str, str] = {}
    children: Dict[str, List[str]] = defaultdict(list)
    for src, tgt, label, _ in edges:
        if label not in TREE_EDGE_TYPES:
            continue
        sid, tid = str(src), str(tgt)
        if sid not in by_view or tid not in by_view:
            continue
        parent, child = by_view[sid], by_view[tid]
        if parent.kind != "goal":
            continue
        if (label == "has_subgoal") != (child.kind == "goal"):
            continue
        if tid in parents:
            continue
        parents[tid] = sid
        children[sid].append(tid)
        tree_edges.append(CompanyTreeEdgeOut(source=sid, target=tid, label=label))

    for node in view_nodes:
        if node.id in parents:
            continue
        parent_key = str(_props(by_id[node.id]).get("source_parent_key") or "")
        parent_view = by_key.get(parent_key)
        if parent_view is None:
            continue
        label = "has_subgoal" if node.kind == "goal" else "has_detail_reference"
        parents[node.id] = parent_view.id
        children[parent_view.id].append(node.id)
        tree_edges.append(CompanyTreeEdgeOut(source=parent_view.id, target=node.id, label=label))

    parentless = [n for n in view_nodes if n.id not in parents]
    named = [n for n in parentless if "公司运营" in n.name and n.kind == "goal"]
    if len(named) == 1:
        root = named[0]
    elif len(parentless) == 1:
        root = parentless[0]
    else:
        missing.append("root_missing_or_duplicate")
        root = named[0] if named else (parentless[0] if parentless else None)

    for node in view_nodes:
        kids = children.get(node.id, [])
        if (
            not node.children_complete
            or node.expected_children < 0
            or len(kids) != node.expected_children
        ):
            missing.append(f"incomplete_children:{node.id}")

    if root is not None:
        seen: set[str] = set()
        visiting: set[str] = set()

        def walk(nid: str) -> None:
            if nid in visiting:
                missing.append("cycle")
                return
            visiting.add(nid)
            seen.add(nid)
            for cid in children.get(nid, []):
                walk(cid)
            visiting.remove(nid)

        walk(root.id)
        if len(seen) != len(view_nodes):
            missing.append("unconnected")
            view_nodes = [n for n in view_nodes if n.id in seen]
            tree_edges = [e for e in tree_edges if e.source in seen and e.target in seen]

    revisions = set()
    for node in view_nodes:
        parsed = parse_source_key(node.source_key)
        if node.revision and parsed and parsed[0] == room:
            revisions.add(node.revision)
    if len(revisions) > 1:
        missing.append("mixed_revision")

    keys = [n.source_key for n in view_nodes if n.source_key]
    if len(keys) != len(set(keys)):
        missing.append("duplicate_source_key")

    complete = not missing
    revision = ""
    if root is not None and root.revision:
        revision = root.revision
    elif len(revisions) == 1:
        revision = revisions.pop()

    return CompanyTreeOut(
        nodes=view_nodes,
        edges=tree_edges,
        root_id=root.id if root is not None else None,
        revision=revision,
        complete=complete,
        missing=sorted(set(missing)),
    )
