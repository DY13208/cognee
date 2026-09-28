from types import SimpleNamespace
from uuid import uuid4

import pytest

from cognee.modules.teleology import purpose_analyze
from cognee.modules.teleology.purpose_analyze import normalize_analysis


def _context():
    return {
        "revision": "1",
        "goal": {"id": "korea", "name": "韩国公司", "type": "Goal", "description": "税务与外汇"},
        "note": "维持主体可经营",
        "ancestors": [{"id": "finance", "name": "公司财务", "type": "Goal"}],
        "children": [
            {"id": "tax", "name": "税务", "type": "Goal"},
            {"id": "fx", "name": "外汇", "type": "Goal"},
        ],
        "purposes": [{"id": "stable", "name": "保障海外业务稳定经营", "type": "Purpose"}],
        "constraints": [],
        "relations": [
            {
                "source_id": "tax",
                "source_name": "税务",
                "relationship": "serves",
                "target_id": "stable",
                "target_name": "保障海外业务稳定经营",
            }
        ],
        "entities": [{"id": "law", "name": "韩国税法", "type": "Entity"}],
        "documents": [{"id": "doc", "name": "税务备忘", "type": "Document", "summary": "税率变化"}],
    }


def test_normalize_drops_structural_advances_and_unknown_refs():
    body = normalize_analysis(
        _context(),
        {
            "summary": "韩国公司缺一个共同结果。",
            "purposes": [
                {
                    "name": "保障韩国业务长期稳定经营",
                    "description": "税务和外汇共同服务的结果",
                    "reason": "下级都在维持主体可经营",
                    "confidence": 0.91,
                    "evidence_node_ids": ["tax", "doc", "missing"],
                }
            ],
            "constraints": [
                {
                    "name": "韩国税法变化",
                    "reason": "备忘录写了税率会变",
                    "confidence": 0.8,
                    "evidence_node_ids": ["doc"],
                }
            ],
            "suggested_goals": [
                {
                    "name": "确保韩国主体合规运营",
                    "reason": "税务和外汇缺少共同结果目标",
                    "confidence": 0.86,
                    "evidence_node_ids": ["tax", "fx"],
                }
            ],
            "relations": [
                {
                    "source_ref": "税务",
                    "relationship": "advances",
                    "target_ref": "韩国公司",
                    "reason": "它是下级",
                    "confidence": 0.9,
                    "evidence_node_ids": ["tax", "korea"],
                },
                {
                    "source_ref": "税务",
                    "relationship": "advances",
                    "target_ref": "确保韩国主体合规运营",
                    "reason": "税务备忘说明这是合规的一部分",
                    "confidence": 0.88,
                    "evidence_node_ids": ["doc", "tax"],
                },
                {
                    "source_ref": "不存在",
                    "relationship": "blocks",
                    "target_ref": "韩国公司",
                    "reason": "没有这个节点",
                    "confidence": 0.4,
                    "evidence_node_ids": [],
                },
                {
                    "source_ref": "韩国税法变化",
                    "relationship": "contains",
                    "target_ref": "韩国公司",
                    "reason": "非法关系",
                    "confidence": 0.4,
                    "evidence_node_ids": ["law"],
                },
                {
                    "source_ref": "税务",
                    "relationship": "serves",
                    "target_ref": "保障海外业务稳定经营",
                    "reason": "已经有这条正式关系",
                    "confidence": 0.7,
                    "evidence_node_ids": ["doc"],
                },
            ],
        },
    )
    assert [item["name"] for item in body["purposes"]] == ["保障韩国业务长期稳定经营"]
    assert body["purposes"][0]["evidence_node_ids"] == ["tax", "doc"]
    assert body["constraints"][0]["evidence"][0]["name"] == "税务备忘"
    assert len(body["goals"]) == 1
    assert [item["relationship"] for item in body["relations"]] == ["advances"]
    assert body["relations"][0]["target"] == body["goals"][0]["id"]
    assert "doc" in body["relations"][0]["evidence_node_ids"]


def test_similar_purpose_is_reused_instead_of_created():
    body = normalize_analysis(
        _context(),
        {
            "summary": "",
            "purposes": [
                {
                    "name": "保障海外业务稳定经营目标",
                    "reason": "和已有目的是同一件事",
                    "confidence": 0.7,
                    "evidence_node_ids": ["korea"],
                }
            ],
            "relations": [
                {
                    "source_ref": "外汇",
                    "relationship": "serves",
                    "target_ref": "保障海外业务稳定经营目标",
                    "reason": "外汇维持资金可流动，文档里写了",
                    "confidence": 0.66,
                    "evidence_node_ids": ["doc"],
                }
            ],
        },
    )
    assert body["purposes"] == []
    assert body["relations"][0]["target"] == "stable"


@pytest.mark.asyncio
async def test_analyze_stores_proposal_without_writing_the_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cognee.modules.teleology.proposal_store.database_enabled", lambda: False
    )

    async def context(*_args, **_kwargs):
        return _context() | {"dataset_id": "d"}

    async def complete(_context, _open):
        return {
            "summary": "需要一个合规结果。",
            "purposes": [
                {
                    "name": "保障韩国业务长期稳定经营",
                    "reason": "税务和外汇都在维持主体",
                    "confidence": 0.9,
                    "evidence_node_ids": ["doc"],
                }
            ],
            "constraints": [],
            "suggested_goals": [],
            "relations": [],
        }

    stored = {}

    async def propose(dataset_id, user, *, source_goal_id, proposal, generated_by):
        stored["proposal"] = proposal
        stored["generated_by"] = generated_by
        stored["source_goal_id"] = source_goal_id
        return {"id": "proposal-1", **proposal, "generated_by": generated_by}

    monkeypatch.setattr(purpose_analyze, "get_purpose_context", context)
    monkeypatch.setattr(purpose_analyze, "_complete", complete)
    monkeypatch.setattr(purpose_analyze, "propose_teleology", propose)
    result = await purpose_analyze.analyze_goal(uuid4(), SimpleNamespace(), "korea")
    assert result["id"] == "proposal-1"
    assert stored["generated_by"] == "purpose-agent"
    assert stored["proposal"]["purposes"][0]["evidence_node_ids"] == ["doc"]
    assert "owner" not in stored["proposal"]["purposes"][0]


def test_ai_purpose_without_evidence_or_outside_context_is_dropped():
    body = normalize_analysis(
        _context(),
        {
            "purposes": [
                {
                    "name": "没有证据的目的",
                    "reason": "听起来合理",
                    "confidence": 0.8,
                    "evidence_node_ids": [],
                },
                {
                    "name": "引用了上下文外的证据",
                    "reason": "证据不在本次上下文",
                    "confidence": 0.8,
                    "evidence_node_ids": ["missing-doc"],
                },
            ]
        },
    )
    assert body["purposes"] == []


def test_weak_relation_and_constraint_overreach_stay_out_of_formal_items():
    body = normalize_analysis(
        _context(),
        {
            "constraints": [
                {
                    "name": "必须使用看板",
                    "reason": "因为存在利润看板，所以必须使用看板",
                    "confidence": 0.8,
                    "evidence_node_ids": ["doc"],
                }
            ],
            "relations": [
                {
                    "source": "tax",
                    "relationship": "advances",
                    "target": "fx",
                    "reason": "线索很弱",
                    "confidence": 0.4,
                    "evidence_node_ids": ["doc"],
                }
            ],
        },
    )
    assert body["constraints"] == []
    assert body["relations"] == []
    assert body["weak_signals"][0]["weak_reason"] == "constraint_overreach"
    assert body["weak_signals"][1]["weak_reason"] == "low_confidence"


def test_cross_proposal_purpose_is_a_conflict_not_an_endpoint():
    body = normalize_analysis(
        _context(),
        {
            "purposes": [
                {
                    "name": "保障韩国业务长期稳定经营",
                    "reason": "和另一份待审候选相同",
                    "confidence": 0.8,
                    "evidence_node_ids": ["doc"],
                }
            ],
            "relations": [
                {
                    "source_id": "fx",
                    "target_id": "open-item-1",
                    "relationship": "serves",
                    "reason": "不应指向别的提案",
                    "confidence": 0.8,
                    "evidence_node_ids": ["doc"],
                }
            ],
        },
        open_items=[
            {
                "id": "open-item-1",
                "proposal_id": "proposal-a",
                "kind": "purpose",
                "name": "保障韩国业务长期稳定经营",
            }
        ],
    )
    assert body["relations"] == []
    assert body["open_conflicts"]
    assert body["open_conflicts"][0]["proposal_id"] == "proposal-a"
    assert all(item["target"] != "open-item-1" for item in body["relations"])
    assert body["purposes"][0]["id"] != "open-item-1"


def test_relation_aliases_normalize_to_source_and_target():
    body = normalize_analysis(
        _context(),
        {
            "relations": [
                {
                    "source_ref": "外汇",
                    "target_id": "stable",
                    "relationship": "blocks",
                    "reason": "别名也能解析",
                    "confidence": 0.7,
                    "evidence_node_ids": ["doc"],
                }
            ]
        },
    )
    assert body["relations"][0]["source"] == "fx"
    assert body["relations"][0]["target"] == "stable"
