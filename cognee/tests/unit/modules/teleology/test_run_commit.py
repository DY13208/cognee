"""Coverage Run commit-all stays scoped to persisted done queue items."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from cognee.modules.teleology import run_commit
from cognee.modules.teleology.coverage_service import CoverageServiceError
from cognee.modules.teleology.coverage_store import MemoryCoverageStore


def item(item_id="purpose", kind="purpose", **extra):
    return {
        "id": item_id,
        "kind": kind,
        "name": item_id,
        "reason": "document evidence",
        "confidence": 0.9,
        "evidence_node_ids": ["document"],
        "relationship": "serves" if kind == "relation" else None,
        **extra,
    }


async def queue(monkeypatch, count=1, *, kinds=None):
    store = MemoryCoverageStore()
    dataset_id, run_id = uuid4(), str(uuid4())
    await store.create_run({"id": run_id, "dataset_id": str(dataset_id), "status": "completed"})
    proposals = {}
    for index in range(count):
        goal_id, proposal_id = f"goal-{index}", f"proposal-{index}"
        await store.add_items(
            [{"run_id": run_id, "goal_id": goal_id, "status": "done", "proposal_id": proposal_id}]
        )
        proposals[proposal_id] = {
            "id": proposal_id,
            "dataset_id": str(dataset_id),
            "source_goal_id": goal_id,
            "status": "open",
            "context_hash": "same",
            "items": [
                item(f"item-{index}", (kinds or ["purpose"])[index % len(kinds or ["purpose"])])
            ],
        }
    calls = []

    async def authorized(*args):
        calls.append(("auth", args[1]))

    async def load(_dataset_id, proposal_id):
        return proposals.get(proposal_id)

    async def context(*args):
        return {"context_hash": "same"}

    async def commit(_dataset_id, _user, proposal_id, accepted_item_ids):
        calls.append(("commit", proposal_id, accepted_item_ids))
        proposals[proposal_id]["status"] = "committed"
        return {"committed_nodes": [1], "committed_edges": [], "skipped_item_ids": []}

    monkeypatch.setattr(run_commit, "get_coverage_engine", lambda: SimpleNamespace(store=store))
    monkeypatch.setattr(run_commit, "_authorized_dataset", authorized)
    monkeypatch.setattr(run_commit, "load_proposal", load)
    monkeypatch.setattr(run_commit, "get_purpose_context", context)
    monkeypatch.setattr(run_commit, "commit_teleology_proposal", commit)
    return store, dataset_id, run_id, proposals, calls


@pytest.mark.asyncio
async def test_ten_run_proposals_commit_once(monkeypatch):
    _, dataset_id, run_id, _, calls = await queue(monkeypatch, 10)
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["proposals_total"] == 10
    assert result["committed_nodes"] == 10
    assert len(result["committed_proposals"]) == 10
    assert len([call for call in calls if call[0] == "commit"]) == 10


@pytest.mark.asyncio
async def test_empty_proposal_is_skipped(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(monkeypatch)
    proposals["proposal-0"]["items"] = []
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["skipped_empty"] == ["proposal-0"]
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_weak_signals_never_enter_accepted_ids(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(monkeypatch)
    proposals["proposal-0"]["weak_signals"] = [item("weak", "relation")]
    proposals["proposal-0"]["items"].append(item("gap", "gap"))
    proposals["proposal-0"]["items"].append(
        item("weak-in-items", "relation", weak_reason="structural_hierarchy_only")
    )
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["items_total"] == 1
    assert next(call for call in calls if call[0] == "commit")[2] == ["item-0"]


@pytest.mark.asyncio
async def test_open_conflict_is_reported_and_not_committed(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(monkeypatch)
    proposals["proposal-0"]["open_conflicts"] = [{"id": "conflict"}]
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["conflict_proposals"] == 1
    assert result["committed_proposals"] == []
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_stale_proposal_is_reported(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(monkeypatch)
    proposals["proposal-0"]["context_hash"] = "old"
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["stale_proposals"] == ["proposal-0"]
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_committed_proposal_is_idempotent(monkeypatch):
    _, dataset_id, run_id, _, calls = await queue(monkeypatch)
    await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    second = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert second["already_committed"] == ["proposal-0"]
    assert len([call for call in calls if call[0] == "commit"]) == 1


@pytest.mark.asyncio
async def test_dataset_mismatch_is_rejected(monkeypatch):
    _, _, run_id, _, calls = await queue(monkeypatch)
    with pytest.raises(CoverageServiceError) as exc:
        await run_commit.commit_coverage_run(run_id, uuid4(), object(), dry_run=False)
    assert exc.value.status_code == 403
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_dry_run_never_calls_commit(monkeypatch):
    _, dataset_id, run_id, _, calls = await queue(monkeypatch, 2, kinds=["purpose", "constraint"])
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=True)
    assert result["purpose_count"] == 1 and result["constraint_count"] == 1
    assert result["goal_count"] == 0
    assert result["serves_count"] == result["advances_count"] == result["blocks_count"] == 0
    assert result["items_total"] == 2
    assert result["proposals_committable"] == 2
    detail = result["proposal_details"][0]
    assert detail["proposal_id"] == "proposal-0"
    assert detail["source_goal_id"] == "goal-0"
    assert detail["accepted_item_ids"] == ["item-0"]
    assert detail["would_commit_count"] == 1
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_dry_run_counts_each_relation_without_writing(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(
        monkeypatch, 3, kinds=["relation", "relation", "relation"]
    )
    proposals["proposal-1"]["items"][0]["relationship"] = "advances"
    proposals["proposal-2"]["items"][0]["relationship"] = "blocks"
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=True)
    assert result["serves_count"] == 1
    assert result["advances_count"] == 1
    assert result["blocks_count"] == 1
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_unfinished_run_is_rejected(monkeypatch):
    store, dataset_id, run_id, _, calls = await queue(monkeypatch)
    await store.create_run({"id": run_id, "dataset_id": str(dataset_id), "status": "running"})
    with pytest.raises(CoverageServiceError) as exc:
        await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=True)
    assert exc.value.status_code == 409
    assert not any(call[0] == "commit" for call in calls)


@pytest.mark.asyncio
async def test_only_done_run_items_with_proposal_ids_are_considered(monkeypatch):
    store, dataset_id, run_id, proposals, calls = await queue(monkeypatch)
    proposals["historical-open"] = {
        "id": "historical-open",
        "dataset_id": str(dataset_id),
        "source_goal_id": "other",
        "status": "open",
        "context_hash": "same",
        "items": [item("old")],
    }
    await store.add_items(
        [
            {
                "run_id": run_id,
                "goal_id": "pending",
                "status": "pending",
                "proposal_id": "historical-open",
            },
            {"run_id": run_id, "goal_id": "no-proposal", "status": "done", "proposal_id": None},
        ]
    )
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["proposals_total"] == 1
    assert [call[1] for call in calls if call[0] == "commit"] == ["proposal-0"]


@pytest.mark.asyncio
async def test_one_commit_failure_does_not_stop_remaining_proposals(monkeypatch):
    _, dataset_id, run_id, _, calls = await queue(monkeypatch, 3)
    original = run_commit.commit_teleology_proposal

    async def failing(dataset, user, proposal_id, accepted):
        if proposal_id == "proposal-1":
            raise ValueError("commit failed")
        return await original(dataset, user, proposal_id, accepted)

    monkeypatch.setattr(run_commit, "commit_teleology_proposal", failing)
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert len(result["committed_proposals"]) == 2
    assert result["failed_proposals"][0]["proposal_id"] == "proposal-1"
    assert len([call for call in calls if call[0] == "commit"]) == 2


@pytest.mark.asyncio
async def test_relation_is_passed_through_existing_safety_commit(monkeypatch):
    _, dataset_id, run_id, proposals, calls = await queue(monkeypatch, 2)
    proposals["proposal-0"]["items"] = [item("relation-0", "relation")]
    original = run_commit.commit_teleology_proposal

    async def guarded(dataset, user, proposal_id, accepted):
        if proposal_id == "proposal-0":
            assert accepted == ["relation-0"]
            raise ValueError("A parent-child advances edge needs evidence beyond its endpoints")
        return await original(dataset, user, proposal_id, accepted)

    monkeypatch.setattr(run_commit, "commit_teleology_proposal", guarded)
    result = await run_commit.commit_coverage_run(run_id, dataset_id, object(), dry_run=False)
    assert result["failed_proposals"][0]["proposal_id"] == "proposal-0"
    assert result["committed_proposals"] == ["proposal-1"]
    assert next(call for call in calls if call[0] == "commit")[1] == "proposal-1"
