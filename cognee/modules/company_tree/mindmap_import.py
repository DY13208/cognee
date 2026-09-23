"""Turn a linked mind map into company-tree nodes and hang them under the link."""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from cognee.modules.company_tree.schema import (
    CpdKind,
    CompanyTreeNodeIn,
    CompanyTreeNodeOut,
    CompanyTreeOut,
    CompanyTreeWriteRequest,
)

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"</p>|</div>|</li>", re.IGNORECASE)


def room_id_from_uri(uri: str) -> str:
    try:
        return (parse_qs(urlparse(uri).query).get("room") or [""])[0].strip()
    except Exception:
        return ""


def plain_text(value: str) -> str:
    text = _BR_RE.sub("\n", value or "")
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    return unescape(text).strip()


def one_line(value: str) -> str:
    return " ".join(plain_text(value).split())


def linked_room_id(data: Dict[str, Any]) -> str:
    ref = data.get("mapRef")
    if not isinstance(ref, dict) or str(ref.get("type") or "") != "map":
        return ""
    return str(ref.get("mapId") or "").strip()


def iter_map_refs(topic: Dict[str, Any]) -> Iterable[str]:
    data = topic.get("data") if isinstance(topic, dict) else None
    if isinstance(data, dict):
        room = linked_room_id(data)
        if room:
            yield room
    for child in _children(topic):
        yield from iter_map_refs(child)


def _children(topic: Dict[str, Any]) -> List[Dict[str, Any]]:
    kids = topic.get("children") if isinstance(topic, dict) else None
    if not isinstance(kids, list):
        return []
    return [kid for kid in kids if isinstance(kid, dict)]


def _node_room(node: CompanyTreeNodeOut, fallback: str) -> str:
    key = node.source_key or ""
    if key.startswith("mindmap:") and key.count(":") >= 2:
        return key.split(":", 2)[1]
    return fallback


def expand_company_tree(
    tree: CompanyTreeOut,
    documents: Dict[str, Dict[str, Any]],
) -> CompanyTreeWriteRequest:
    """Rebuild one write payload, with each fetched linked map grafted under its entry.

    `documents` is keyed by mind-map room id. A room is attached once. A later
    link to a room already attached stays a reference, and a cycle stops there.
    """
    if tree.root_id is None:
        raise ValueError("company tree has no root")
    by_id = {node.id: node for node in tree.nodes}
    root = by_id[tree.root_id]
    primary_room = _node_room(root, "")
    if not primary_room:
        raise ValueError("company tree root has no mind-map room")
    revision = tree.revision or root.revision
    if not revision:
        raise ValueError("company tree has no revision")

    parent_of = {edge.target: edge.source for edge in tree.edges}
    nodes: List[CompanyTreeNodeIn] = []
    seen_uids = set()
    for node in tree.nodes:
        parent = by_id.get(parent_of.get(node.id, ""))
        item = CompanyTreeNodeIn(
            source_uid=node.source_uid,
            source_room=_node_room(node, primary_room),
            name=node.name,
            cpd_kind=node.kind,
            source_parent_uid=parent.source_uid if parent else None,
            source_child_count=0,
            source_children_complete=node.children_complete,
            source_position=node.position,
            source_note=node.note,
            source_uri=node.source_uri,
            linked_map_uri=node.linked_uri,
            source_revision=node.revision or revision,
        )
        nodes.append(item)
        seen_uids.add(node.source_uid)

    attached = {primary_room}

    def walk(
        topic: Dict[str, Any],
        parent_uid: str,
        room: str,
        room_revision: str,
        source_uri: str,
        truncated: bool,
        position: str,
    ) -> None:
        data = topic.get("data") if isinstance(topic.get("data"), dict) else {}
        uid = str(data.get("uid") or "").strip()
        if not uid or uid in seen_uids:
            return
        seen_uids.add(uid)
        name = one_line(str(data.get("text") or "")) or uid
        ref = linked_room_id(data)
        linked = documents.get(ref) if ref and ref not in attached else None
        if linked and linked.get("tree"):
            attached.add(ref)
        else:
            linked = None
        local_kids = _children(topic)
        kind: CpdKind = "goal" if linked or not ref else "map_reference"
        link_uri = ""
        if ref:
            link_uri = str((documents.get(ref) or {}).get("source_uri") or "")
            if not link_uri:
                link_uri = f"https://xx.stillgroup.net:8989/?room={ref}"
        note = plain_text(str(data.get("note") or ""))[:4000]
        child_truncated = bool(linked and linked.get("truncated"))
        nodes.append(
            CompanyTreeNodeIn(
                source_uid=uid,
                source_room=room,
                name=name,
                cpd_kind=kind,
                source_parent_uid=parent_uid,
                source_child_count=0,
                source_children_complete=not truncated and not child_truncated,
                source_position=position,
                source_note=note,
                source_uri=source_uri,
                linked_map_uri=link_uri,
                source_revision=room_revision,
            )
        )
        for index, child in enumerate(local_kids):
            walk(
                child,
                uid,
                room,
                room_revision,
                source_uri,
                truncated,
                f"{index:06d}",
            )
        if linked:
            walk(
                linked["tree"],
                uid,
                ref,
                str(linked.get("version") or room_revision),
                f"https://xx.stillgroup.net:8989/?room={ref}",
                bool(linked.get("truncated")),
                f"{len(local_kids):06d}",
            )

    for item in list(nodes):
        if item.cpd_kind != "map_reference":
            continue
        room = room_id_from_uri(item.linked_map_uri)
        document = documents.get(room)
        if not room or room in attached or not document or not document.get("tree"):
            continue
        attached.add(room)
        item.cpd_kind = "goal"
        item.source_children_complete = not bool(document.get("truncated"))
        walk(
            document["tree"],
            item.source_uid,
            room,
            str(document.get("version") or revision),
            item.linked_map_uri or f"https://xx.stillgroup.net:8989/?room={room}",
            bool(document.get("truncated")),
            "000000",
        )

    counts: Dict[str, int] = {item.source_uid: 0 for item in nodes}
    for item in nodes:
        if item.source_parent_uid:
            counts[item.source_parent_uid] = counts.get(item.source_parent_uid, 0) + 1
    for item in nodes:
        item.source_child_count = counts.get(item.source_uid, 0)
    return CompanyTreeWriteRequest(
        source_room=primary_room,
        source_revision=revision,
        allow_incomplete=any(not item.source_children_complete for item in nodes),
        nodes=nodes,
    )
