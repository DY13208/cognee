"""Coverage scheduling without a model and without a database."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cognee.modules.teleology.coverage_engine import CoverageEngine
from cognee.modules.teleology.coverage_logic import (
    decide_coverage,
    dirty_ids_for_child,
    dirty_ids_for_text,
    insufficient_context,
)
from cognee.modules.teleology.coverage_store import MemoryCoverageStore
from cognee.modules.teleology.semantic_hash import semantic_context_hash


def _context(goal_id: str, **overrides):
    context = {
        "dataset_id": "dataset",
        "goal": {"id": goal_id, "name": "目标", "description": "说明", "progress": 10},
        "note": "说明",
        "ancestors": [],
        "children": [],
        "entities": [],
        "documents": [],
        "child_evidence": [],
        "purposes": [],
        "constraints": [],
        "relations": [],
        "context_hash": "ctx-" + goal_id,
        "created_at": "ignore-me",
    }
    context.update(overrides)
    return context


class FakeSources:
    def __init__(self, contexts, analyze):
        self.contexts = contexts
        self._analyze = analyze
        self.calls = []
        self.run_ids = []
        self.stale = []

    async def goal_page(self, _dataset_id, _user, offset, limit):
        ids = list(self.contexts)
        return ids[offset : offset + limit], len(ids)

    async def context(self, _dataset_id, _user, goal_id):
        return self.contexts[goal_id]

    async def analyze(self, _dataset_id, _user, goal_id, run_id):
        self.calls.append(goal_id)
        self.run_ids.append(run_id)
        return await self._analyze(goal_id)

    async def open_proposal(self, _dataset_id, goal_id):
        return self.contexts[goal_id].get("_proposal")

    async def mark_stale(self, _dataset_id, _user, proposal):
        self.stale.append(proposal["id"])
        proposal["status"] = "stale"

    async def remember_semantic_hash(self, _dataset_id, _user, proposal, semantic_hash):
        proposal["semantic_context_hash"] = semantic_hash


def _proposal(goal_id):
    return {
        "id": "prop-" + goal_id,
        "items": [{"kind": "purpose", "name": "形成可经营的结果"}],
        "context_hash": "ctx-" + goal_id,
    }


def test_semantic_hash_ignores_progress_and_changes_with_evidence_content():
    original = _context("g", entities=[{"id": "e1", "type": "Entity", "summary": "旧内容"}])
    progress = _context(
        "g",
        goal={
            "id": "g",
            "name": "目标",
            "description": "说明",
            "progress": 90,
            "created_at": "later",
        },
        entities=[{"id": "e1", "type": "Entity", "summary": "旧内容"}],
    )
    changed = _context("g", entities=[{"id": "e1", "type": "Entity", "summary": "新内容"}])
    assert semantic_context_hash(original) == semantic_context_hash(progress)
    assert semantic_context_hash(original) != semantic_context_hash(changed)


def test_description_and_child_dirty_do_not_climb_the_tree():
    assert dirty_ids_for_text(goal_id="child", parent_id="parent", text_changed=True) == [
        "parent",
        "child",
    ]
    assert "grandparent" not in dirty_ids_for_text(
        goal_id="child", parent_id="parent", text_changed=True
    )
    assert dirty_ids_for_text(goal_id="child", text_changed=False) == []
    assert dirty_ids_for_child(parent_id="parent", child_id="child", previous_parent_id=None) == [
        "parent",
        "child",
    ]
    assert "grandparent" not in dirty_ids_for_child(parent_id="parent", child_id="leaf")


def test_child_and_description_change_the_semantic_hash():
    base = _context("g")
    described = _context(
        "g", goal={"id": "g", "name": "目标", "description": "新说明"}, note="新说明"
    )
    with_child = _context(
        "g",
        children=[{"id": "c", "semantic_role": "goal", "name": "子目标", "description": ""}],
    )
    assert semantic_context_hash(base) != semantic_context_hash(described)
    assert semantic_context_hash(base) != semantic_context_hash(with_child)


def test_same_hash_open_proposal_skips_and_changed_hash_reanalyzes():
    context = _context("g")
    current = semantic_context_hash(context)
    proposal = {
        "id": "p",
        "status": "open",
        "context_hash": context["context_hash"],
        "semantic_context_hash": current,
    }
    state = {"status": "proposal_open", "semantic_context_hash": current}
    assert decide_coverage("incremental", state, context, proposal, current) == "skip"
    changed = _context("g", goal={"id": "g", "name": "目标", "description": "变了"}, note="变了")
    changed_hash = semantic_context_hash(changed)
    assert decide_coverage("incremental", state, changed, proposal, changed_hash) == "stale_analyze"
    missing_semantic = {
        "id": "p",
        "status": "open",
        "context_hash": context["context_hash"],
    }
    assert (
        decide_coverage("incremental", state, context, missing_semantic, current) == "stale_analyze"
    )
    swapped = {
        "id": "p",
        "status": "open",
        "context_hash": current,
        "semantic_context_hash": context["context_hash"],
    }
    assert decide_coverage("incremental", state, context, swapped, current) == "stale_analyze"


def test_insufficient_context_does_not_ask_for_analysis():
    empty = _context("g", goal={"id": "g", "name": "空", "description": ""}, note="")
    assert insufficient_context(empty) is True
    assert decide_coverage("incremental", None, empty, None) == "insufficient"
    described = _context("g")
    assert insufficient_context(described) is False


@pytest.mark.asyncio
async def test_same_semantic_hash_does_not_call_llm():
    context = _context("g")
    sources = FakeSources({"g": context}, _boom)
    store = MemoryCoverageStore()
    await store.upsert_state(
        {
            "dataset_id": "dataset",
            "goal_id": "g",
            "status": "clean",
            "semantic_context_hash": semantic_context_hash(context),
        }
    )
    engine = CoverageEngine(store, sources)
    await engine.start("dataset", object(), mode="incremental", wait=True)
    assert sources.calls == []


@pytest.mark.asyncio
async def test_open_proposal_paths_and_insufficient_context():
    same = _context("keep")
    same_hash = semantic_context_hash(same)
    same["_proposal"] = {
        "id": "open-keep",
        "status": "open",
        "context_hash": same["context_hash"],
        "semantic_context_hash": same_hash,
    }
    changed = _context("move", goal={"id": "move", "name": "目标", "description": "新"}, note="新")
    changed["_proposal"] = {
        "id": "open-move",
        "status": "open",
        "context_hash": "old",
        "semantic_context_hash": "old-hash",
    }
    empty = _context("empty", goal={"id": "empty", "name": "空", "description": ""}, note="")
    sources = FakeSources({"keep": same, "move": changed, "empty": empty}, _ok)
    engine = CoverageEngine(MemoryCoverageStore(), sources)
    await engine.start("dataset", object(), mode="incremental", concurrency=1, wait=True)
    assert sources.calls == ["move"]
    assert sources.stale == ["open-move"]
    state = await engine.store.get_state("dataset", "empty")
    assert state["status"] == "insufficient_context"


@pytest.mark.asyncio
async def test_pause_resume_and_restart_do_not_repeat_a_finished_goal():
    contexts = {
        "a": _context("a"),
        "b": _context("b", ancestors=[{"id": "a"}, {"id": "mid"}]),
    }
    sources = FakeSources(contexts, None)
    store = MemoryCoverageStore()
    engine = CoverageEngine(store, sources)

    async def analyze(goal_id):
        if goal_id == "a":
            await engine.pause(engine.current_run_id)
        return _proposal(goal_id)

    sources._analyze = analyze
    run = await engine.start("dataset", object(), mode="baseline", concurrency=1, wait=True)
    assert sources.calls == ["a"]
    assert run["status"] == "paused"

    restarted = CoverageEngine(store, sources)
    resumed = await restarted.resume(run["id"], "dataset", object(), wait=True)
    assert sources.calls == ["a", "b"]
    assert sources.run_ids == [run["id"], run["id"]]
    assert resumed["status"] == "completed"


@pytest.mark.asyncio
async def test_one_goal_error_retries_and_the_run_continues():
    contexts = {
        "bad": _context("bad"),
        "ok": _context("ok", ancestors=[{"id": "bad"}, {"id": "x"}]),
    }

    async def analyze(goal_id):
        if goal_id == "bad":
            raise RuntimeError("down")
        return _proposal(goal_id)

    sources = FakeSources(contexts, analyze)
    engine = CoverageEngine(MemoryCoverageStore(), sources)
    run = await engine.start("dataset", object(), mode="baseline", concurrency=1, wait=True)
    assert sources.calls.count("bad") == 3
    assert "ok" in sources.calls
    assert run["status"] == "completed"
    assert run["failed_goals"] == 1
    assert (await engine.store.get_state("dataset", "bad"))["status"] == "retry_required"


@pytest.mark.asyncio
async def test_token_budget_pauses_and_unknown_usage_is_not_invented():
    contexts = {
        "a": _context("a"),
        "b": _context("b", ancestors=[{"id": "a"}, {"id": "mid"}]),
        "c": _context("c", ancestors=[{"id": "a"}, {"id": "mid"}]),
    }

    async def analyze(goal_id):
        proposal = _proposal(goal_id)
        proposal["token_usage"] = {"input_tokens": 6, "output_tokens": 6}
        return proposal

    sources = FakeSources(contexts, analyze)
    engine = CoverageEngine(MemoryCoverageStore(), sources, token_usage_available=True)
    run = await engine.start(
        "dataset", object(), mode="baseline", concurrency=1, token_budget=10, wait=True
    )
    assert sources.calls == ["a"]
    assert run["status"] == "paused_budget"
    assert run["token_usage_available"] is True
    assert run["token_budget_active"] is True
    assert run["used_input_tokens"] == 6
    assert run["used_output_tokens"] == 6

    quiet = FakeSources({"a": _context("a")}, analyze)
    quiet_engine = CoverageEngine(MemoryCoverageStore(), quiet)
    quiet_run = await quiet_engine.start(
        "dataset", object(), mode="baseline", token_budget=1, wait=True
    )
    assert quiet.calls == ["a"]
    assert quiet_run["used_input_tokens"] is None
    assert quiet_run["token_usage_available"] is False
    assert quiet_run["token_budget_active"] is False
    assert quiet_run["status"] == "completed"


@pytest.mark.asyncio
async def test_duplicate_queue_runs_a_goal_once():
    sources = FakeSources({"g": _context("g")}, _ok)
    engine = CoverageEngine(MemoryCoverageStore(), sources)
    run = await engine.start("dataset", object(), mode="incremental", wait=False)
    await engine._consider(run, object(), "g")
    await engine._consider(run, object(), "g")
    await engine._process(run["id"], "dataset", object())
    assert sources.calls == ["g"]
    assert len(await engine.store.list_items(run["id"])) == 1


@pytest.mark.asyncio
async def test_reconcile_marks_dirty_without_calling_llm():
    context = _context("g", goal={"id": "g", "name": "目标", "description": "新"}, note="新")
    sources = FakeSources({"g": context}, _boom)
    store = MemoryCoverageStore()
    await store.upsert_state(
        {
            "dataset_id": "dataset",
            "goal_id": "g",
            "status": "clean",
            "semantic_context_hash": semantic_context_hash(_context("g")),
        }
    )
    engine = CoverageEngine(store, sources)
    counts = await engine.reconcile("dataset", object())
    assert counts["dirty"] == 1
    assert sources.calls == []
    assert (await store.get_state("dataset", "g"))["status"] == "dirty"


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_only_expired_leases_recover():
    store = MemoryCoverageStore()
    await store.create_run({"id": "run", "dataset_id": "dataset", "status": "running"})
    await store.add_items(
        [
            {"run_id": "run", "goal_id": "a", "priority": 0, "status": "pending"},
            {"run_id": "run", "goal_id": "b", "priority": 1, "status": "pending"},
        ]
    )
    first, second = await asyncio.gather(store.claim_next("run"), store.claim_next("run"))
    assert {first["goal_id"], second["goal_id"]} == {"a", "b"}
    assert await store.claim_next("run") is None
    assert await store.release_expired_leases("run") == 0

    expired = await store.get_item(first["id"])
    expired["lease_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.items[expired["id"]] = expired
    assert await store.release_expired_leases("run") == 1
    reclaimed = await store.claim_next("run")
    assert reclaimed["goal_id"] == first["goal_id"]
    assert reclaimed["attempts"] == 2
    live = await store.get_item(second["id"])
    assert live["status"] == "analyzing"
    assert live["lease_expires_at"] == second["lease_expires_at"]


def test_sql_claim_locks_one_row_and_skips_locked():
    from sqlalchemy.dialects import postgresql

    from cognee.modules.teleology.coverage_store import SqlCoverageStore

    statement = SqlCoverageStore.claim_statement("11111111-1111-1111-1111-111111111111")
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "LEASE_EXPIRES_AT" in sql


def test_run_record_persists_started_at():
    from cognee.modules.teleology.coverage_store import build_run_record

    record = build_run_record(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "dataset_id": "22222222-2222-2222-2222-222222222222",
            "mode": "baseline",
            "status": "running",
            "batch_size": 20,
            "concurrency": 2,
            "max_goals": 100,
            "started_at": "2026-09-28T10:00:00+00:00",
            "scanned_goals": 0,
        }
    )
    assert record.started_at is not None
    assert record.scanned_goals == 0


@pytest.mark.asyncio
async def test_started_at_is_set_when_the_run_is_created():
    engine = CoverageEngine(MemoryCoverageStore(), FakeSources({"g": _context("g")}, _ok))
    run = await engine.start("dataset", object(), mode="baseline", max_goals=1, wait=False)
    assert run["started_at"]


@pytest.mark.asyncio
async def test_max_goals_streams_and_does_not_scan_the_whole_dataset():
    store = MemoryCoverageStore()
    sources = _StreamSources(total=12000, block_second_page=True)
    engine = CoverageEngine(store, sources)
    sources.engine = engine
    original = store.claim_next

    async def claim(run_id):
        item = await original(run_id)
        if item and sources.claimed_at is None:
            current = await store.get_run(run_id)
            sources.claimed_at = int(current["scanned_goals"] or 0)
            sources.claimed.set()
        return item

    store.claim_next = claim
    run = await engine.start(
        "dataset",
        object(),
        mode="baseline",
        batch_size=20,
        concurrency=2,
        max_goals=100,
        wait=True,
    )
    items = await store.list_items(run["id"])
    assert run["status"] == "completed"
    assert run["started_at"]
    assert run["queued_goals"] == 100
    assert run["total_goals"] == 12000
    assert run["scanned_goals"] < 12000
    assert len(items) == 100
    assert not any(item["status"] == "pending" for item in items)
    assert sources.calls == 100
    assert max(sources.offsets) <= 200
    assert sources.claimed_at is not None and sources.claimed_at <= 200
    assert run["scanned_goals"] > sources.claimed_at
    assert any(0 < value < run["scanned_goals"] for value in sources.scans)
    assert any(0 < value < 100 for value in sources.queued_seen)


@pytest.mark.asyncio
async def test_pause_during_scan_stops_enqueue():
    store = MemoryCoverageStore()
    sources = _StreamSources(total=400, pause_at=30)
    engine = CoverageEngine(store, sources)
    sources.engine = engine
    run = await engine.start(
        "dataset",
        object(),
        mode="baseline",
        batch_size=20,
        concurrency=2,
        max_goals=100,
        wait=True,
    )
    items = await store.list_items(run["id"])
    assert run["status"] == "paused"
    assert run["scanned_goals"] <= 30
    assert max(sources.offsets) == 0
    assert items
    assert all(int(item["goal_id"][1:]) < 30 for item in items)


@pytest.mark.asyncio
async def test_cancel_during_scan_adds_no_further_pending():
    store = MemoryCoverageStore()
    sources = _StreamSources(total=400, cancel_at=30)
    engine = CoverageEngine(store, sources)
    sources.engine = engine
    run = await engine.start(
        "dataset",
        object(),
        mode="baseline",
        batch_size=20,
        concurrency=2,
        max_goals=100,
        wait=True,
    )
    items = await store.list_items(run["id"])
    assert run["status"] == "cancelled"
    assert run["scanned_goals"] <= 30
    assert not any(item["status"] == "pending" for item in items)
    assert all(int(item["goal_id"][1:]) < 30 for item in items)


class _StreamSources:
    def __init__(self, total: int, pause_at: int | None = None, cancel_at: int | None = None, block_second_page: bool = False):
        self.total = total
        self.pause_at = pause_at
        self.cancel_at = cancel_at
        self.block_second_page = block_second_page
        self.engine = None
        self.offsets: list[int] = []
        self.scans: list[int] = []
        self.queued_seen: list[int] = []
        self.calls = 0
        self.claimed: asyncio.Event = asyncio.Event()
        self.claimed_at: int | None = None

    async def goal_page(self, _dataset_id, _user, offset, limit):
        self.offsets.append(offset)
        if self.block_second_page and offset >= 200:
            await asyncio.wait_for(self.claimed.wait(), timeout=3)
        stop = min(offset + limit, self.total)
        return [f"g{index}" for index in range(offset, stop)], self.total

    async def context(self, _dataset_id, _user, goal_id):
        index = int(goal_id[1:])
        if self.engine is not None:
            current = await self.engine.store.get_run(self.engine.current_run_id)
            self.scans.append(int(current.get("scanned_goals") or 0))
            self.queued_seen.append(int(current.get("queued_goals") or 0))
            if self.pause_at is not None and index == self.pause_at:
                await self.engine.pause(self.engine.current_run_id)
            if self.cancel_at is not None and index == self.cancel_at:
                await self.engine.cancel(self.engine.current_run_id)
        if index % 3:
            return _context(goal_id, goal={"id": goal_id, "name": "空", "description": ""}, note="")
        return _context(goal_id)

    async def analyze(self, _dataset_id, _user, goal_id, run_id):
        self.calls += 1
        return _proposal(goal_id)

    async def open_proposal(self, _dataset_id, _goal_id):
        return None

    async def mark_stale(self, _dataset_id, _user, _proposal):
        return None

    async def remember_semantic_hash(self, _dataset_id, _user, proposal, semantic_hash):
        proposal["semantic_context_hash"] = semantic_hash


def test_coverage_engine_never_commits():
    root = Path(__file__).resolve().parents[4] / "modules" / "teleology"
    for name in ("coverage_engine.py", "coverage_sources.py", "coverage_service.py"):
        assert "commit_teleology_proposal" not in (root / name).read_text(encoding="utf-8")


async def _ok(goal_id):
    return _proposal(goal_id)


async def _boom(_goal_id):
    raise AssertionError("LLM should not be called")
