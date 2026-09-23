from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import ConfigDict, Field, field_validator

from cognee.api.DTO import InDTO, OutDTO
from cognee.infrastructure.engine.models.DataPoint import DataPoint
from cognee.modules.company_tree.exceptions import CompanyTreeWriteError

TREE_EDGE_TYPES = frozenset({"has_subgoal", "has_detail_reference"})
COMPANY_SCOPE = "company_model_only"
SOURCE_KEY_PREFIX = "mindmap:"
CpdKind = Literal["goal", "map_reference"]


def make_source_key(source_room: str, source_uid: str) -> str:
    return f"mindmap:{source_room}:{source_uid}"


def parse_source_key(source_key: str) -> Optional[Tuple[str, str]]:
    if not source_key.startswith(SOURCE_KEY_PREFIX):
        return None
    rest = source_key[len(SOURCE_KEY_PREFIX) :]
    if ":" not in rest:
        return None
    room, uid = rest.split(":", 1)
    if not room or not uid:
        return None
    return room, uid


class CompanyTreeNodeIn(InDTO):
    source_uid: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cpd_kind: CpdKind
    source_room: Optional[str] = None
    source_parent_uid: Optional[str] = None
    source_child_count: int = Field(ge=0)
    source_children_complete: bool = True
    source_position: str = ""
    source_note: str = ""
    source_uri: str = ""
    linked_map_uri: str = ""
    source_revision: Optional[str] = None


class CompanyTreeWriteRequest(InDTO):
    source_room: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    source_scope: Literal["company_model_only"] = COMPANY_SCOPE
    allow_incomplete: bool = False
    nodes: List[CompanyTreeNodeIn]

    @field_validator("nodes")
    @classmethod
    def nodes_not_empty(cls, nodes: List[CompanyTreeNodeIn]) -> List[CompanyTreeNodeIn]:
        if not nodes:
            raise ValueError("nodes must not be empty")
        return nodes


class CompanyTreeNodeOut(OutDTO):
    id: str
    name: str
    kind: CpdKind
    source_key: str
    source_uid: str
    source_uri: str = ""
    revision: str = ""
    note: str = ""
    linked_uri: str = ""
    position: str = ""
    expected_children: int = 0
    children_complete: bool = False
    stamped: bool = True


class CompanyTreeEdgeOut(OutDTO):
    source: str
    target: str
    label: str


class CompanyTreeOut(OutDTO):
    nodes: List[CompanyTreeNodeOut] = Field(default_factory=list)
    edges: List[CompanyTreeEdgeOut] = Field(default_factory=list)
    root_id: Optional[str] = None
    revision: str = ""
    complete: bool = False
    missing: List[str] = Field(default_factory=list)


class CompanyTreeNode(DataPoint):
    """Persisted company-tree member. Graph `type` is forced to Goal so the
    business canvas keeps treating these as entities."""

    name: str
    cpd_kind: CpdKind
    source_room: str
    source_scope: str = COMPANY_SCOPE
    source_uid: str
    source_key: str
    source_parent_key: Optional[str] = None
    source_child_count: int = 0
    source_children_complete: bool = False
    source_position: str = ""
    source_note: str = ""
    source_uri: str = ""
    linked_map_uri: str = ""
    source_revision: str = ""
    metadata: dict = {"index_fields": ["name"], "identity_fields": ["source_key"]}
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "type", "Goal")


def validate_write_payload(payload: CompanyTreeWriteRequest) -> None:
    """Fail closed before any graph write. Identity, parent pointers, and
    (unless allow_incomplete) child-count completeness must all hold."""
    missing: List[str] = []
    seen_uids: Dict[str, CompanyTreeNodeIn] = {}
    for node in payload.nodes:
        if node.source_uid in seen_uids:
            missing.append(f"duplicate_source_uid:{node.source_uid}")
        seen_uids[node.source_uid] = node
        node_room = node.source_room or payload.source_room
        if node.source_revision is None:
            node.source_revision = payload.source_revision
        elif node.source_revision != payload.source_revision and node_room == payload.source_room:
            missing.append(f"mixed_revision:{node.source_uid}")

    roots = [n for n in payload.nodes if n.source_parent_uid is None]
    if len(roots) != 1:
        missing.append("root_missing_or_duplicate")

    child_counts: Dict[str, int] = {n.source_uid: 0 for n in payload.nodes}
    for node in payload.nodes:
        parent = node.source_parent_uid
        if parent is None:
            continue
        if parent not in seen_uids:
            missing.append(f"missing_parent:{node.source_uid}")
            continue
        if parent == node.source_uid:
            missing.append(f"self_parent:{node.source_uid}")
            continue
        parent_node = seen_uids[parent]
        if parent_node.cpd_kind != "goal":
            missing.append(f"non_goal_parent:{node.source_uid}")
            continue
        expected_label = "has_subgoal" if node.cpd_kind == "goal" else "has_detail_reference"
        if expected_label == "has_subgoal" and node.cpd_kind != "goal":
            missing.append(f"kind_edge_mismatch:{node.source_uid}")
        child_counts[parent] += 1

    visiting: set[str] = set()
    seen: set[str] = set()

    def walk(uid: str) -> None:
        if uid in visiting:
            missing.append("cycle")
            return
        if uid in seen:
            return
        visiting.add(uid)
        for child in payload.nodes:
            if child.source_parent_uid == uid:
                walk(child.source_uid)
        visiting.remove(uid)
        seen.add(uid)

    if len(roots) == 1:
        walk(roots[0].source_uid)
        if len(seen) != len(payload.nodes) and "cycle" not in missing:
            missing.append("unconnected")

    if not payload.allow_incomplete:
        for node in payload.nodes:
            if (
                node.source_children_complete
                and node.source_child_count != child_counts[node.source_uid]
            ):
                missing.append(f"incomplete_children:{node.source_uid}")
            if not node.source_children_complete:
                missing.append(f"marked_incomplete:{node.source_uid}")

    if missing:
        raise CompanyTreeWriteError(
            "Company tree write rejected: schema or completeness failed.",
            missing=missing,
        )


def edge_label_for(child_kind: CpdKind) -> str:
    return "has_subgoal" if child_kind == "goal" else "has_detail_reference"
