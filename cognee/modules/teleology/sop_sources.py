"""Resolve mind-map uids to company-tree identities and read factual atoms.

Matching never uses node text or a brand-name guess. Same names in different
rooms stay distinct.
"""

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser
from typing import Any

from cognee.modules.company_tree.schema import make_source_key, parse_source_key

MINDMAP_SOURCE_TYPES = frozenset({"NODE", "NOTE", "REFERENCE", "ATTACHMENT"})
TELEOLOGY_SOURCE_TYPES = frozenset({"TELEOLOGY_CONSTRAINT", "TELEOLOGY_PURPOSE"})
_TIER_RANK = {"DIRECT_EVIDENCE": 3, "SOURCE_PROVENANCE": 2, "SEMANTIC_MATCH": 1}
_NODE_KEYS = (
    ("target", "NODE", "target", True),
    ("node", "NODE", "target", True),
    ("path", "NODE", "path", True),
    ("children", "NODE", "children", True),
    ("subtree", "NODE", "subtree", True),
    ("siblings", "NODE", "siblings", True),
    ("nodes", "NODE", "nodes", True),
    ("facts", "NODE", "facts", False),
    ("notes", "NOTE", "notes", False),
    ("note", "NOTE", "notes", False),
    ("references", "REFERENCE", "references", False),
    ("refs", "REFERENCE", "references", False),
    ("attachments", "ATTACHMENT", "attachments", False),
    ("files", "ATTACHMENT", "attachments", False),
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    return data if isinstance(data, dict) else {}


def _node_uid(node: dict[str, Any]) -> str:
    for key in ("source_uid", "node_uid", "uid", "id"):
        if _text(node.get(key)):
            return _text(node.get(key))
    return ""


def _label(node: dict[str, Any]) -> str:
    """Read both the simplified fixture shape and build_sop_context nodes.

    Query nodes keep the visible title in ``data.text``. The composed target
    copies that title to ``text``. Attachment names live on ``metadata``.
    """
    data = _node_data(node)
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    for source in (node, data):
        for key in ("name", "title", "label", "topic"):
            if _text(source.get(key)):
                return _text(source.get(key))
    if _text(data.get("text")):
        return _text(data.get("text"))
    for key in ("fileName", "filename", "name", "title"):
        if _text(metadata.get(key)):
            return _text(metadata.get(key))
    for key in ("text", "content"):
        if _text(node.get(key)):
            return _text(node.get(key))
    value = node.get("value")
    if _text(value):
        return _text(value)
    if isinstance(value, dict):
        for key in ("name", "title", "fileName", "url", "mapId"):
            if _text(value.get(key)):
                return _text(value.get(key))
    for source in (node, data):
        if _text(source.get("note")):
            return _text(source.get("note"))
    return ""


class _Catalog:
    def __init__(self) -> None:
        self.nodes: list[dict[str, str]] = []
        self.by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.by_room_uid: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        self.by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)


def index_company_tree(nodes: Any) -> _Catalog:
    """Index company-tree nodes by source_key, room+uid, and node id."""
    catalog = _Catalog()
    for raw in nodes or []:
        data = _mapping(raw)
        if not data:
            continue
        source_key = _text(data.get("source_key"))
        source_uid = _text(data.get("source_uid"))
        source_room = _text(data.get("source_room"))
        parsed = parse_source_key(source_key) if source_key else None
        if parsed:
            source_room = source_room or parsed[0]
            source_uid = source_uid or parsed[1]
        if not source_key and source_room and source_uid:
            source_key = make_source_key(source_room, source_uid)
        node = {
            "id": _text(data.get("id") or data.get("node_id")),
            "source_key": source_key,
            "source_uid": source_uid,
            "source_room": source_room,
            "name": _text(data.get("name")),
        }
        if not node["id"] and not node["source_key"]:
            continue
        catalog.nodes.append(node)
        if node["source_key"]:
            catalog.by_key[node["source_key"]].append(node)
        if node["source_room"] and node["source_uid"]:
            catalog.by_room_uid[(node["source_room"], node["source_uid"])].append(node)
        if node["id"]:
            catalog.by_id[node["id"]].append(node)
        if node["source_uid"]:
            catalog.by_uid[node["source_uid"]].append(node)
    return catalog


def _ref(
    room: str,
    uid: str,
    source_key: str,
    node_id: str | None,
    status: str,
    reason: str,
    *,
    cross_room: bool = False,
) -> dict[str, Any]:
    return {
        "room_key": room,
        "mindmap_uid": uid,
        "source_key": source_key,
        "company_tree_node_id": node_id,
        "resolution_status": status,
        "reason": reason,
        "cross_room": cross_room,
    }


def _exact(room: str, uid: str, node: dict[str, str], reason: str) -> dict[str, Any]:
    return _ref(room, uid, node["source_key"], node["id"] or None, "EXACT", reason)


def resolve_mindmap_uid(room_key: str, mindmap_uid: str, catalog: _Catalog) -> dict[str, Any]:
    """Map one mind-map uid to a company-tree node, or explain why it is unsafe."""
    raw = _text(mindmap_uid)
    room = _text(room_key)
    parsed = parse_source_key(raw) if raw else None
    if parsed and room and parsed[0] != room:
        return _ref(
            room,
            raw,
            raw,
            None,
            "NOT_FOUND",
            "该 source_key 属于其他 room，禁止跨 room 合并。",
            cross_room=True,
        )
    if parsed:
        room = parsed[0]
        raw = parsed[1]
    source_key = make_source_key(room, raw) if room and raw else ""
    if not raw:
        return _ref(room, raw, source_key, None, "NOT_FOUND", "缺少 mind-map uid。")
    if not room:
        return _ref(
            room, raw, source_key, None, "NOT_FOUND", "缺少 room_key，无法构造 source_key。"
        )

    key_hits = catalog.by_key.get(source_key, [])
    if len(key_hits) > 1:
        return _ref(
            room, raw, source_key, None, "AMBIGUOUS", "source_key 对应多个 company-tree 节点。"
        )
    if len(key_hits) == 1:
        return _exact(room, raw, key_hits[0], "exact source_key。")

    room_hits = catalog.by_room_uid.get((room, raw), [])
    if len(room_hits) > 1:
        return _ref(
            room,
            raw,
            source_key,
            None,
            "AMBIGUOUS",
            "room_key 与 source uid 对应多个 company-tree 节点。",
        )
    if len(room_hits) == 1:
        return _exact(room, raw, room_hits[0], "exact room_key + source uid。")

    id_hits = [node for node in catalog.by_id.get(raw, []) if node["source_room"] == room]
    if len(id_hits) > 1:
        return _ref(
            room, raw, source_key, None, "AMBIGUOUS", "该 room 内 company-tree node id 不唯一。"
        )
    if len(id_hits) == 1:
        return _exact(room, raw, id_hits[0], "标识本身是该 room 的 company-tree node id。")

    other_rooms = [node for node in catalog.by_uid.get(raw, []) if node["source_room"] != room]
    if other_rooms:
        return _ref(
            room,
            raw,
            source_key,
            None,
            "NOT_FOUND",
            "同一 uid 只存在于其他 room，禁止跨 room 合并。",
            cross_room=True,
        )
    if not catalog.nodes:
        return _ref(
            room,
            raw,
            source_key,
            None,
            "NOT_FOUND",
            "未加载 company-tree，无法解析 source_key。",
        )
    return _ref(room, raw, source_key, None, "NOT_FOUND", "company-tree 中不存在该 source_key。")


def _ordered_uids(request: dict[str, Any], atoms: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []

    def add(value: Any) -> None:
        text = _text(value)
        if text and text not in ordered:
            ordered.append(text)

    add(request.get("node_uid"))
    for item in request.get("source_uids") or []:
        add(item)
    for atom in atoms:
        add(atom.get("source_uid"))
    return ordered


def resolve_request_sources(
    request: dict[str, Any],
    atoms: list[dict[str, Any]],
    company_tree_nodes: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Resolve every requested mind-map uid. Ambiguity is reported, not dropped."""
    catalog = index_company_tree(company_tree_nodes)
    room = _text(request.get("room_key"))
    refs = [resolve_mindmap_uid(room, uid, catalog) for uid in _ordered_uids(request, atoms)]
    exact = [ref for ref in refs if ref["resolution_status"] == "EXACT"]
    summary = {
        "resolved_count": len(exact),
        "unresolved": [ref for ref in refs if ref["resolution_status"] == "NOT_FOUND"],
        "ambiguous": [ref for ref in refs if ref["resolution_status"] == "AMBIGUOUS"],
    }
    warnings: list[str] = []
    if summary["ambiguous"]:
        warnings.append("source identity 存在歧义，相关 uid 未用于确定 Goal。")
    if catalog.nodes and summary["unresolved"]:
        warnings.append("部分 mind-map uid 没有唯一的 company-tree source_key，未静默忽略。")
    by_uid = {ref["mindmap_uid"]: ref for ref in refs}
    for atom in atoms:
        ref = by_uid.get(_text(atom.get("source_uid")))
        if ref and ref["resolution_status"] == "EXACT":
            atom["evidence_node_id"] = ref["company_tree_node_id"]
    return refs, summary, warnings


def _atom(
    *,
    text: str,
    raw_text: str,
    source_type: str,
    source_uid: str,
    evidence_node_id: str,
    room_key: str,
    path: list[str],
    provenance: str,
    confidence: float,
    explicit_plan: bool,
) -> dict[str, Any]:
    return {
        "text": text,
        "raw_text": raw_text,
        "source_type": source_type,
        "source_uid": source_uid,
        "evidence_node_id": evidence_node_id or None,
        "room_key": room_key,
        "path": list(path),
        "provenance": provenance,
        "confidence": confidence,
        "explicit_plan": explicit_plan,
    }


class _MindmapTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_mindmap_text(raw: str) -> str:
    """Return visible mind-map text, decoding HTML entities and removing markup."""
    parser = _MindmapTextParser()
    parser.feed(raw)
    parser.close()
    return " ".join("".join(parser.parts).replace("\xa0", " ").split())


def _strip_plan_prefix(text: str) -> tuple[str, bool]:
    for prefix in ("P：", "P:", "计划：", "计划:", "执行：", "执行:", "步骤：", "步骤:"):
        if text.startswith(prefix):
            body = text[len(prefix) :].strip()
            if body:
                return body, True
    return text, False


def _append_atom(
    out: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    raw_text: str,
    source_type: str,
    source_uid: str,
    evidence_node_id: str,
    room_key: str,
    path: list[str],
    provenance: str,
) -> None:
    original = raw_text
    normalized_text = normalize_mindmap_text(original).strip()
    if not normalized_text and not source_uid:
        return
    text, explicit_plan = _strip_plan_prefix(normalized_text)
    key = (source_type, source_uid, text)
    if key in seen:
        return
    seen.add(key)
    out.append(
        _atom(
            text=text or normalized_text,
            raw_text=original,
            source_type=source_type,
            source_uid=source_uid,
            evidence_node_id=evidence_node_id,
            room_key=room_key,
            path=path,
            provenance=provenance,
            confidence=1.0 if explicit_plan else 0.8,
            explicit_plan=explicit_plan,
        )
    )


def _walk(
    value: Any,
    *,
    source_type: str,
    origin: str,
    room_key: str,
    path: list[str],
    recurse: bool,
    out: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
) -> None:
    if isinstance(value, str):
        value = {"text": value}
    if isinstance(value, list):
        for item in value:
            _walk(
                item,
                source_type=source_type,
                origin=origin,
                room_key=room_key,
                path=path,
                recurse=recurse,
                out=out,
                seen=seen,
            )
        return
    if not isinstance(value, dict):
        return
    raw_text = _label(value)
    data = _node_data(value)
    note = _text(value.get("note") or data.get("note"))
    extra_ids = value.get("evidence_node_ids") or []
    evidence_node_id = _text(extra_ids[0]) if extra_ids else _text(value.get("evidence_node_id"))
    current_path = path + ([raw_text] if raw_text else [])
    _append_atom(
        out,
        seen,
        raw_text=raw_text,
        source_type=source_type,
        source_uid=_node_uid(value),
        evidence_node_id=evidence_node_id,
        room_key=room_key,
        path=current_path,
        provenance=origin,
    )
    if note and note != raw_text:
        _append_atom(
            out,
            seen,
            raw_text=note,
            source_type="NOTE",
            source_uid=_node_uid(value),
            evidence_node_id=evidence_node_id,
            room_key=room_key,
            path=current_path,
            provenance=f"{origin}:note",
        )
    if source_type == "ATTACHMENT":
        body = _text(value.get("text"))
        if body and body != raw_text:
            _append_atom(
                out,
                seen,
                raw_text=body,
                source_type="ATTACHMENT",
                source_uid=_node_uid(value),
                evidence_node_id=evidence_node_id,
                room_key=room_key,
                path=current_path,
                provenance=f"{origin}:text",
            )
    if recurse:
        for child_key in ("children", "child_nodes", "subtree"):
            if value.get(child_key):
                _walk(
                    value.get(child_key),
                    source_type="NODE",
                    origin=child_key,
                    room_key=room_key,
                    path=current_path,
                    recurse=True,
                    out=out,
                    seen=seen,
                )


def extract_factual_atoms(mindmap_context: Any, *, room_key: str = "") -> list[dict[str, Any]]:
    """Read target, path, children, subtree, notes, references, and attachments."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(mindmap_context, list):
        _walk(
            mindmap_context,
            source_type="NODE",
            origin="facts",
            room_key=room_key,
            path=[],
            recurse=False,
            out=out,
            seen=seen,
        )
        return out
    if not isinstance(mindmap_context, dict):
        return out
    for key, source_type, origin, recurse in _NODE_KEYS:
        if key not in mindmap_context or mindmap_context.get(key) in (None, "", [], {}):
            continue
        _walk(
            mindmap_context.get(key),
            source_type=source_type,
            origin=origin,
            room_key=room_key,
            path=[],
            recurse=recurse,
            out=out,
            seen=seen,
        )
    return out


def teleology_atoms(
    purposes: list[dict[str, Any]], constraints: list[dict[str, Any]], room_key: str
) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for purpose in purposes:
        name = _text(purpose.get("name") or purpose.get("text"))
        if not name:
            continue
        atoms.append(
            _atom(
                text=name,
                raw_text=name,
                source_type="TELEOLOGY_PURPOSE",
                source_uid="",
                evidence_node_id="",
                room_key=room_key,
                path=[],
                provenance=f"purpose:{_text(purpose.get('id'))}",
                confidence=float(purpose.get("confidence") or 0.6),
                explicit_plan=False,
            )
        )
        atoms[-1]["purpose_id"] = _text(purpose.get("id"))
    for constraint in constraints:
        name = _text(constraint.get("name") or constraint.get("text"))
        if not name:
            continue
        atoms.append(
            _atom(
                text=name,
                raw_text=name,
                source_type="TELEOLOGY_CONSTRAINT",
                source_uid="",
                evidence_node_id="",
                room_key=room_key,
                path=[],
                provenance=f"constraint:{_text(constraint.get('id'))}",
                confidence=float(constraint.get("confidence") or 0.6),
                explicit_plan=False,
            )
        )
        atoms[-1]["constraint_id"] = _text(constraint.get("id"))
    return atoms


def goal_evidence_ids(goal: dict[str, Any]) -> set[str]:
    found = {
        _text(value)
        for key in ("source_node_ids", "evidence_node_ids", "source_uids")
        for value in goal.get(key) or []
        if _text(value)
    }
    found.update(
        _text(entry.get("node_id"))
        for entry in goal.get("evidence") or []
        if isinstance(entry, dict) and _text(entry.get("node_id"))
    )
    return found


def _provenance(goal: dict[str, Any], catalog: _Catalog) -> tuple[set[str], set[str]]:
    keys: set[str] = set()
    rooms: set[str] = set()
    for entry in goal.get("evidence") or []:
        if not isinstance(entry, dict):
            continue
        source_key = _text(entry.get("source_key"))
        if source_key:
            keys.add(source_key)
            parsed = parse_source_key(source_key)
            if parsed:
                rooms.add(parsed[0])
        if _text(entry.get("source_room")):
            rooms.add(_text(entry.get("source_room")))
    for node_id in goal_evidence_ids(goal):
        for node in catalog.by_id.get(node_id, []):
            if node["source_key"]:
                keys.add(node["source_key"])
            if node["source_room"]:
                rooms.add(node["source_room"])
    return keys, rooms


def _scope_conflict(
    goal: dict[str, Any],
    *,
    room: str,
    source_keys: set[str],
    catalog: _Catalog,
    tier: str,
) -> bool:
    """True when selecting this goal would cross a known provenance boundary."""
    keys, rooms = _provenance(goal, catalog)
    shares_key = bool(source_keys and keys and source_keys & keys)
    shares_room = bool(room and rooms and room in rooms)
    if shares_key or shares_room:
        return False
    if keys or rooms:
        return True
    return tier == "SEMANTIC_MATCH" and bool(catalog.nodes) and bool(room or source_keys)


def match_goals(
    goals: list[dict[str, Any]],
    *,
    room_key: str,
    refs: list[dict[str, Any]],
    atoms: list[dict[str, Any]],
    company_tree_nodes: Any,
) -> dict[str, Any]:
    """Rank goals by direct evidence, provenance, then semantic text.

    Semantic matches cannot override a provenance conflict. A tie yields no
    primary goal.
    """
    catalog = index_company_tree(company_tree_nodes)
    exact_refs = [ref for ref in refs if ref["resolution_status"] == "EXACT"]
    exact_ids = {_text(ref.get("company_tree_node_id")) for ref in exact_refs}
    exact_ids.discard("")
    exact_keys = {_text(ref.get("source_key")) for ref in exact_refs}
    exact_keys.discard("")
    if not catalog.nodes:
        exact_ids.update(
            _text(ref.get("mindmap_uid")) for ref in refs if _text(ref.get("mindmap_uid"))
        )
    query = " ".join(_text(atom.get("text")) for atom in atoms).casefold()
    ranked: list[dict[str, Any]] = []
    for goal in goals:
        ids = goal_evidence_ids(goal)
        keys, _rooms = _provenance(goal, catalog)
        tier = ""
        confidence = 0.0
        reason = ""
        if ids and exact_ids and ids & exact_ids:
            tier = "DIRECT_EVIDENCE"
            confidence = 1.0
            reason = (
                "解析后的 company-tree node id 直接出现在 Goal evidence 中。"
                if catalog.nodes
                else "标识与 Goal evidence node id 一致。"
            )
        elif exact_keys and keys and exact_keys & keys:
            tier = "SOURCE_PROVENANCE"
            confidence = 0.8
            reason = "Goal evidence 的 source_key 与请求来源一致。"
        else:
            name = _text(goal.get("name")).casefold()
            if name and len(name) > 3 and name in query:
                tier = "SEMANTIC_MATCH"
                confidence = 0.35
                reason = "仅名称与 mind-map 文本重合，需 provenance 不冲突才可采用。"
        if not tier:
            continue
        conflict = _scope_conflict(
            goal, room=room_key, source_keys=exact_keys, catalog=catalog, tier=tier
        )
        if tier == "SEMANTIC_MATCH" and not exact_refs:
            conflict = True
        elif tier == "DIRECT_EVIDENCE":
            conflict = False
        goal["match_tier"] = tier
        goal["match_confidence"] = confidence
        goal["match_reason"] = reason
        goal["provenance_conflict"] = conflict
        ranked.append(goal)

    def sort_key(goal: dict[str, Any]) -> tuple[Any, ...]:
        return (
            bool(goal.get("provenance_conflict")),
            -_TIER_RANK[str(goal.get("match_tier"))],
            -float(goal.get("match_confidence") or 0),
            str(goal.get("id")),
        )

    ranked.sort(key=sort_key)
    selectable = [goal for goal in ranked if not goal.get("provenance_conflict")]
    status = "NOT_FOUND"
    primary = None
    if selectable:
        best = str(selectable[0].get("match_tier"))
        top = [goal for goal in selectable if goal.get("match_tier") == best]
        if len(top) == 1:
            primary = top[0]
            status = "RESOLVED"
        else:
            status = "AMBIGUOUS"
    elif any(goal.get("provenance_conflict") for goal in ranked):
        status = "AMBIGUOUS"
    if status == "RESOLVED" and primary is not None:
        reason = f"唯一命中“{primary.get('name')}”（{primary.get('match_tier')}）。"
    elif status == "AMBIGUOUS":
        names = "、".join(str(goal.get("name") or goal.get("id")) for goal in ranked) or "无"
        reason = f"无法安全确定唯一 Goal（{names}）。存在并列命中或 provenance 冲突，未选择 primary goal。"
    else:
        reason = "没有与已解析来源安全对应的 current Goal。"
    return {"primary": primary, "related": ranked, "status": status, "reason": reason}
