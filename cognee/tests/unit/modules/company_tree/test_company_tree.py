from cognee.modules.company_tree.assemble import assemble_company_tree
from cognee.modules.company_tree.exceptions import CompanyTreeWriteError
from cognee.modules.company_tree.schema import (
    CompanyTreeNodeIn,
    CompanyTreeWriteRequest,
    validate_write_payload,
)

ROOM = "room-yk3tz4aj"
ROOT = "313047eb-0c98-4abb-a1ce-933b1081e234"


def _stamped(uid, name, parent=None, kind="goal"):
    props = {
        "type": "Goal",
        "name": name,
        "source_room": ROOM,
        "source_scope": "company_model_only",
        "cpd_kind": kind,
        "source_uid": uid,
        "source_key": f"mindmap:{ROOM}:{uid}",
        "source_parent_key": f"mindmap:{ROOM}:{parent}" if parent else None,
        "source_child_count": 0,
        "source_children_complete": True,
        "source_revision": "1",
    }
    return (uid, props)


def test_assemble_includes_unstamped_goal_ancestors():
    nodes = [
        (
            "ops",
            {
                "type": "Goal",
                "name": "公司运营",
                "source_key": f"mindmap:{ROOM}:{ROOT}",
            },
        ),
        (
            "biz",
            {
                "type": "Goal",
                "name": "公司业务",
                "source_key": f"mindmap:{ROOM}:6e33fd96-e4a0-4eb2-9fb6-595873490fd4",
            },
        ),
        _stamped("ahc", "AHC项目", parent="6e33fd96-e4a0-4eb2-9fb6-595873490fd4"),
        _stamped("narka", "NARKA项目", parent="6e33fd96-e4a0-4eb2-9fb6-595873490fd4"),
    ]
    edges = [
        ("ops", "biz", "has_subgoal", {}),
        ("biz", "ahc", "has_subgoal", {}),
        ("biz", "narka", "has_subgoal", {}),
    ]
    tree = assemble_company_tree(nodes, edges)
    assert tree.root_id == "ops"
    assert {n.name for n in tree.nodes} >= {"公司运营", "公司业务", "AHC项目", "NARKA项目"}
    assert tree.complete is False
    assert any(item.startswith("unstamped:") for item in tree.missing)


def test_assemble_empty_graph_is_not_a_tree():
    tree = assemble_company_tree([], [])
    assert tree.root_id is None
    assert tree.nodes == []
    assert "empty" in tree.missing
    assert tree.complete is False


def test_write_rejects_two_roots():
    payload = CompanyTreeWriteRequest(
        source_room=ROOM,
        source_revision="1",
        nodes=[
            CompanyTreeNodeIn(source_uid="a", name="A", cpd_kind="goal", source_child_count=0),
            CompanyTreeNodeIn(source_uid="b", name="B", cpd_kind="goal", source_child_count=0),
        ],
    )
    try:
        validate_write_payload(payload)
        raise AssertionError("expected CompanyTreeWriteError")
    except CompanyTreeWriteError as exc:
        assert "root_missing_or_duplicate" in exc.missing


def test_write_rejects_incomplete_child_counts():
    payload = CompanyTreeWriteRequest(
        source_room=ROOM,
        source_revision="1",
        nodes=[
            CompanyTreeNodeIn(
                source_uid="root",
                name="公司运营",
                cpd_kind="goal",
                source_child_count=2,
                source_children_complete=True,
            ),
            CompanyTreeNodeIn(
                source_uid="child",
                name="AHC",
                cpd_kind="goal",
                source_parent_uid="root",
                source_child_count=0,
            ),
        ],
    )
    try:
        validate_write_payload(payload)
        raise AssertionError("expected CompanyTreeWriteError")
    except CompanyTreeWriteError as exc:
        assert any(item.startswith("incomplete_children:") for item in exc.missing)


def test_write_accepts_a_complete_single_root_tree():
    payload = CompanyTreeWriteRequest(
        source_room=ROOM,
        source_revision="1",
        nodes=[
            CompanyTreeNodeIn(
                source_uid="root",
                name="公司运营",
                cpd_kind="goal",
                source_child_count=1,
            ),
            CompanyTreeNodeIn(
                source_uid="child",
                name="AHC",
                cpd_kind="goal",
                source_parent_uid="root",
                source_child_count=0,
            ),
        ],
    )
    validate_write_payload(payload)


def test_assemble_keeps_imported_mindmap_under_its_link():
    root = _stamped(ROOT, "公司运营")
    root[1]["source_child_count"] = 1
    link = _stamped("link", "UN项目工程", parent=ROOT)
    link[1]["source_child_count"] = 1
    linked = (
        "linked-root",
        {
            "type": "Goal",
            "name": "C：UN项目利润分",
            "source_room": "room-linked",
            "source_scope": "company_model_only",
            "cpd_kind": "goal",
            "source_uid": "linked-root",
            "source_key": "mindmap:room-linked:linked-root",
            "source_child_count": 0,
            "source_children_complete": True,
            "source_revision": "2789",
        },
    )
    edges = [
        (ROOT, "link", "has_subgoal", {}),
        ("link", "linked-root", "has_subgoal", {}),
    ]
    tree = assemble_company_tree([root, link, linked], edges, ROOM)
    assert {node.name for node in tree.nodes} == {"公司运营", "UN项目工程", "C：UN项目利润分"}
    assert any(edge.source == "link" and edge.target == "linked-root" for edge in tree.edges)
    assert "mixed_revision" not in tree.missing
    assert tree.complete is True


def test_write_allows_another_rooms_revision():
    payload = CompanyTreeWriteRequest(
        source_room=ROOM,
        source_revision="1314",
        nodes=[
            CompanyTreeNodeIn(
                source_uid="root",
                name="公司运营",
                cpd_kind="goal",
                source_child_count=1,
                source_revision="1314",
            ),
            CompanyTreeNodeIn(
                source_uid="linked",
                name="品牌目标",
                cpd_kind="goal",
                source_room="room-linked",
                source_parent_uid="root",
                source_child_count=0,
                source_revision="2789",
            ),
        ],
    )
    validate_write_payload(payload)
