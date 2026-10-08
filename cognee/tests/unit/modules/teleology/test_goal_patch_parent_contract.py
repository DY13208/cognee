"""Parent-binding regression specification. All writes use an isolated memory store.

The original nine scenarios enforce the repaired parent contract.
No application, production database, or global goal cache is written.
"""

import copy
from uuid import UUID, uuid4

import pytest

from cognee.modules.teleology.goal_orchestrated import compose_orchestrated_proposal
from cognee.modules.teleology.goal_patch import submit_orchestrated_patch
from cognee.modules.teleology.goal_store import MemoryGoalRunStore


@pytest.fixture(autouse=True, scope="session")
def _relational_db_for_unit_tests():
    """Override the parent conftest migration fixture: these tests need no SQL."""
    return


def goal(client_id, name):
    return {
        "client_id": client_id,
        "name": name,
        "reason": "business outcome supported by document",
        "confidence": 0.8,
        "evidence_node_ids": ["doc"],
    }


@pytest.fixture
def isolated_store(monkeypatch):
    async def allow(*args, **kwargs):
        pass

    monkeypatch.setattr("cognee.modules.teleology.goal_patch._authorized_dataset", allow)
    monkeypatch.setattr("cognee.modules.teleology.goal_model.STORE.save", lambda result: None)
    return MemoryGoalRunStore()


async def baseline(store):
    dataset_id = uuid4()
    model, summary = compose_orchestrated_proposal(
        dataset_id,
        {
            "goals": [
                goal("old", "Improve company profitability"),
                goal("new", "Improve brand profitability"),
                goal("child", "Improve channel profitability"),
            ],
            "hierarchy": [
                {
                    "parent_client_id": "old",
                    "child_client_id": "child",
                    "reason": "channel belongs to company",
                    "evidence_node_ids": ["doc"],
                }
            ],
        },
        known_node_ids={"doc"},
    )
    assert summary["valid"]
    await store.save_result(model)
    return dataset_id, await store.get_dataset(dataset_id), summary["resolved_client_ids"]


async def submit(store, dataset_id, view, **fields):
    return await submit_orchestrated_patch(
        UUID(str(dataset_id)),
        object(),
        {"submission_mode": "patch", "base_run_id": view["current_run_id"], **fields},
        known_node_ids={"doc"},
        store=store,
        strict=True,
    )


def candidate(view, candidate_id):
    return next(row for row in view["candidates"] if row["id"] == candidate_id)


@pytest.mark.asyncio
async def test_new_goal_parent_candidate_id_saved_and_read_back(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[
            {
                **goal("added", "Improve procurement profitability"),
                "parent_candidate_id": ids["new"],
            }
        ],
    )
    assert result["saved"] and result["valid"]
    saved = await isolated_store.get_dataset(dataset_id)
    child = candidate(saved, result["resolved_client_ids"]["added"])
    assert child["parent_candidate_id"] == ids["new"]


@pytest.mark.asyncio
async def test_existing_candidate_reparent_keeps_id_and_name(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    original = candidate(view, ids["child"])
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[
            {
                "candidate_id": ids["child"],
                "name": original["name"],
                "parent_candidate_id": ids["new"],
            }
        ],
    )
    assert result["saved"] and result["valid"]
    saved = await isolated_store.get_dataset(dataset_id)
    child = candidate(saved, ids["child"])
    assert child["id"] == original["id"] and child["name"] == original["name"]
    assert child["parent_candidate_id"] == ids["new"]


@pytest.mark.asyncio
async def test_parent_only_update_changes_parent_without_duplicate(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[{"candidate_id": ids["child"], "parent_candidate_id": ids["new"]}],
    )
    assert result["saved"] and result["valid"]
    saved = await isolated_store.get_dataset(dataset_id)
    assert {row["id"] for row in saved["candidates"]} == {row["id"] for row in view["candidates"]}
    assert candidate(saved, ids["child"])["parent_candidate_id"] == ids["new"]


@pytest.mark.asyncio
async def test_dry_run_reports_parent_change_without_writes(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    before = copy.deepcopy(isolated_store.runs)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        dry_run=True,
        upsert_goals=[{"candidate_id": ids["child"], "parent_candidate_id": ids["new"]}],
    )
    assert not result["saved"] and isolated_store.runs == before
    assert result["hierarchy_changes"] == [
        {
            "child_id": ids["child"],
            "previous_parent_id": ids["old"],
            "parent_id": ids["new"],
            "reason": candidate(view, ids["child"])["reason"],
        }
    ]


@pytest.mark.asyncio
async def test_invalid_parent_rejected_without_saving(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    before = copy.deepcopy(isolated_store.runs)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[{"candidate_id": ids["child"], "parent_candidate_id": str(uuid4())}],
    )
    assert not result["valid"]
    assert not result["saved"] and isolated_store.runs == before
    assert result["issues"]


@pytest.mark.asyncio
async def test_existing_supported_hierarchy_client_fields_persist(isolated_store):
    dataset_id, view, ids = await baseline(isolated_store)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        upsert_goals=[{"candidate_id": ids["child"]}],
        hierarchy=[
            {
                "child_client_id": ids["child"],
                "parent_client_id": ids["new"],
                "reason": "reparent by canonical ids in supported client fields",
                "evidence_node_ids": ["doc"],
            }
        ],
    )
    assert result["valid"] and result["saved"]
    saved = await isolated_store.get_dataset(dataset_id)
    assert candidate(saved, ids["child"])["parent_candidate_id"] == ids["new"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,expected", [("", "missing_reason"), ("reparent", None)])
async def test_candidate_hierarchy_fields_resolve_without_misleading_error(
    isolated_store, reason, expected
):
    dataset_id, view, ids = await baseline(isolated_store)
    result = await submit(
        isolated_store,
        dataset_id,
        view,
        dry_run=True,
        upsert_goals=[{"candidate_id": ids["child"]}],
        hierarchy=[
            {
                "child_candidate_id": ids["child"],
                "parent_candidate_id": ids["new"],
                "reason": reason,
                "evidence_node_ids": ["doc"],
            }
        ],
    )
    if expected:
        assert any(issue["reason"] == expected for issue in result["issues"])
        assert result["rejected"]["hierarchy"] == 1
    else:
        assert result["valid"] and result["issues"] == []
        assert result["hierarchy_changes"] == [
            {
                "child_id": ids["child"],
                "previous_parent_id": ids["old"],
                "parent_id": ids["new"],
            }
        ]
    assert not any(issue["reason"] == "self_parent" for issue in result["issues"])


def test_request_schema_preserves_parent_fields_and_rejects_unknown():
    from pydantic import ValidationError

    from cognee.api.v1.teleology.routers.get_teleology_router import OrchestratedGoalIn

    payload = {
        "candidate_id": str(uuid4()),
        "parent_candidate_id": str(uuid4()),
        "parent_id": str(uuid4()),
    }
    parsed = OrchestratedGoalIn.model_validate(payload).model_dump(exclude_unset=True)
    assert parsed == payload
    with pytest.raises(ValidationError, match="extra_forbidden"):
        OrchestratedGoalIn.model_validate({**payload, "unsupported_parent": "bad"})
