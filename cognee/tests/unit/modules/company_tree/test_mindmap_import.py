from cognee.modules.company_tree.mindmap_import import expand_company_tree, plain_text
from cognee.modules.company_tree.schema import (
    CompanyTreeEdgeOut,
    CompanyTreeNodeOut,
    CompanyTreeOut,
    validate_write_payload,
)

ROOM = "room-yk3tz4aj"
ROOT = "313047eb-0c98-4abb-a1ce-933b1081e234"


def _node(node_id, name, kind="goal", linked_uri=""):
    return CompanyTreeNodeOut(
        id=node_id,
        name=name,
        kind=kind,
        source_key=f"mindmap:{ROOM}:{node_id}",
        source_uid=node_id,
        linked_uri=linked_uri,
        revision="1314",
        children_complete=True,
        expected_children=0,
    )


def _tree():
    root = _node(ROOT, "公司运营")
    root.expected_children = 1
    link = _node(
        "link",
        "UN项目工程",
        kind="map_reference",
        linked_uri="https://xx.stillgroup.net:8989/?room=room-linked",
    )
    return CompanyTreeOut(
        nodes=[root, link],
        edges=[CompanyTreeEdgeOut(source=ROOT, target="link", label="has_detail_reference")],
        root_id=ROOT,
        revision="1314",
        complete=True,
    )


def _doc(tree, version="2789", truncated=False):
    return {
        "version": version,
        "truncated": truncated,
        "source_uri": "http://xx.stillgroup.net:8990/?room=room-linked",
        "tree": tree,
    }


def test_plain_text_strips_markup():
    assert plain_text("<p>C：UN项目利润分</p>") == "C：UN项目利润分"


def test_expand_grafts_linked_map_as_goals():
    payload = expand_company_tree(
        _tree(),
        {
            "room-linked": _doc(
                {
                    "data": {"uid": "linked-root", "text": "<p>C：UN项目利润分</p>"},
                    "children": [
                        {
                            "data": {
                                "uid": "child",
                                "text": "<p>P：品牌目标</p>",
                                "note": "<p>说明</p>",
                            },
                            "children": [],
                        }
                    ],
                }
            )
        },
    )
    validate_write_payload(payload)
    by_uid = {node.source_uid: node for node in payload.nodes}
    assert by_uid["link"].cpd_kind == "goal"
    assert by_uid["link"].source_child_count == 1
    assert by_uid["linked-root"].source_room == "room-linked"
    assert by_uid["linked-root"].source_parent_uid == "link"
    assert by_uid["linked-root"].name == "C：UN项目利润分"
    assert by_uid["linked-root"].source_revision == "2789"
    assert by_uid["child"].source_note == "说明"
    assert by_uid["child"].source_parent_uid == "linked-root"
    assert payload.allow_incomplete is False


def test_expand_imports_a_room_once():
    tree = _tree()
    second = _node(
        "link-2",
        "另一个入口",
        kind="map_reference",
        linked_uri="https://xx.stillgroup.net:8989/?room=room-linked",
    )
    tree.nodes.append(second)
    tree.edges.append(
        CompanyTreeEdgeOut(source=ROOT, target="link-2", label="has_detail_reference")
    )
    tree.nodes[0].expected_children = 2
    payload = expand_company_tree(
        tree,
        {"room-linked": _doc({"data": {"uid": "linked-root", "text": "利润分"}, "children": []})},
    )
    validate_write_payload(payload)
    by_uid = {node.source_uid: node for node in payload.nodes}
    assert by_uid["link"].cpd_kind == "goal"
    assert by_uid["link-2"].cpd_kind == "map_reference"
    assert by_uid["link-2"].source_child_count == 0
    assert sum(node.source_uid == "linked-root" for node in payload.nodes) == 1
