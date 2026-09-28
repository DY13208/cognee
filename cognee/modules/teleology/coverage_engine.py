"""Schedule purpose analysis. The model call stays in analyze_goal."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from cognee.modules.teleology.coverage_logic import (
    MAX_ATTEMPTS,
    clamp_batch_size,
    clamp_concurrency,
    decide_coverage,
    insufficient_context,
    priority_for,
)
from cognee.modules.teleology.purpose_analyze import PROMPT_VERSION
from cognee.modules.teleology.semantic_hash import semantic_context_hash

logger = logging.getLogger(__name__)
_DISCOVERY_PAGE = 200
_STOP_STATUSES = frozenset({"paused", "paused_budget", "cancelled", "failed", "completed"})

# TODO: LLMGateway.acreate_structured_output does not return provider token
# usage to analyze_goal. Counts stay null until that hook exists. Do not estimate.


class CoverageSources(Protocol):
    async def goal_page(
        self, dataset_id: Any, user: Any, offset: int, limit: int
    ) -> tuple[list[str], int]: ...

    async def context(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]: ...

    async def analyze(
        self, dataset_id: Any, user: Any, goal_id: str, run_id: str
    ) -> dict[str, Any]: ...

    async def open_proposal(self, dataset_id: Any, goal_id: str) -> dict[str, Any] | None: ...

    async def mark_stale(self, dataset_id: Any, user: Any, proposal: dict[str, Any]) -> None: ...

    async def remember_semantic_hash(
        self, dataset_id: Any, user: Any, proposal: dict[str, Any], semantic_hash: str
    ) -> None: ...


def _utcnow() -> datetime:
    """Timezone-aware timestamp for DateTime columns. API responses serialize it."""
    return datetime.now(timezone.utc)


def _status_after_skip(state: dict[str, Any] | None, proposal: dict[str, Any] | None) -> str:
    if proposal and proposal.get("status") == "open":
        return "proposal_open"
    current = str((state or {}).get("status") or "clean")
    if current in {"confirmed", "clean", "no_supported_proposal", "insufficient_context"}:
        return current
    return "clean"


class _ScanGate:
    """Wakes consumers when a batch is queued, and when the scan stops."""

    def __init__(self) -> None:
        self.scan_done = False
        self.version = 0
        self._wake = asyncio.Event()

    def pulse(self) -> None:
        self.version += 1
        self._wake.set()

    def finish(self) -> None:
        self.scan_done = True
        self.version += 1
        self._wake.set()

    async def wait(self, seen: int) -> int:
        while self.version == seen and not self.scan_done:
            await self._wake.wait()
        self._wake.clear()
        return self.version


def _usage(result: dict[str, Any] | None) -> tuple[int, int] | None:
    raw = result.get("token_usage") if isinstance(result, dict) else None
    if not isinstance(raw, dict):
        return None
    incoming = raw.get("input_tokens")
    outgoing = raw.get("output_tokens")
    if not isinstance(incoming, int) or not isinstance(outgoing, int):
        return None
    return incoming, outgoing


class CoverageEngine:
    """Discover, rank, and persist coverage work. It never commits a proposal."""

    def __init__(
        self,
        store: Any,
        sources: CoverageSources,
        *,
        token_usage_available: bool = False,
    ) -> None:
        self.store = store
        self.sources = sources
        self.token_usage_available = token_usage_available
        self._lock = asyncio.Lock()

    def present(self, run: dict[str, Any] | None) -> dict[str, Any] | None:
        if run is None:
            return None
        shown = dict(run)
        shown["token_usage_available"] = self.token_usage_available
        shown["token_budget_active"] = bool(
            self.token_usage_available and shown.get("token_budget") is not None
        )
        if not self.token_usage_available:
            shown["used_input_tokens"] = None
            shown["used_output_tokens"] = None
        return shown

    async def start(
        self,
        dataset_id: Any,
        user: Any,
        *,
        mode: str,
        batch_size: int | None = None,
        concurrency: int | None = None,
        max_goals: int | None = None,
        token_budget: int | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        if mode not in {"baseline", "incremental", "force"}:
            raise ValueError("mode must be baseline, incremental, or force")
        active = await self.store.active_run(dataset_id)
        if active:
            raise RuntimeError("A coverage run is already active for this dataset.")
        run = await self.store.create_run(
            {
                "id": str(uuid4()),
                "dataset_id": str(dataset_id),
                "mode": mode,
                "status": "running",
                "batch_size": clamp_batch_size(batch_size),
                "concurrency": clamp_concurrency(concurrency),
                "max_goals": max_goals,
                "token_budget": token_budget,
                "used_input_tokens": None,
                "used_output_tokens": None,
                "total_goals": 0,
                "scanned_goals": 0,
                "eligible_goals": 0,
                "queued_goals": 0,
                "processed_goals": 0,
                "skipped_goals": 0,
                "proposal_goals": 0,
                "no_change_goals": 0,
                "no_context_goals": 0,
                "failed_goals": 0,
                "started_at": _utcnow(),
            }
        )
        self.current_run_id = run["id"]
        if wait:
            await self.drive(run["id"], dataset_id, user)
            return self.present(await self.store.get_run(run["id"])) or run
        return self.present(run) or run

    async def drive(self, run_id: str, dataset_id: Any, user: Any) -> None:
        run = await self.store.get_run(run_id)
        if not run:
            return
        workers: list[asyncio.Task[None]] = []
        try:
            if run["status"] in {"pending", "paused", "paused_budget"}:
                fields: dict[str, Any] = {"status": "running"}
                if not run.get("started_at"):
                    fields["started_at"] = _utcnow()
                await self.store.update_run(run_id, **fields)
            await self.store.release_expired_leases(run_id)
            gate = _ScanGate()
            workers = [
                asyncio.create_task(self._produce(run_id, dataset_id, user, gate)),
                asyncio.create_task(self._process(run_id, dataset_id, user, gate)),
            ]
            await asyncio.gather(*workers)
        except Exception:
            logger.exception("Teleology coverage run %s failed", run_id)
            # Stop the sibling before writing failed. Otherwise a consumer that
            # already observed status=running can commit completed afterwards,
            # and the failed write never sticks.
            for task in workers:
                if not task.done():
                    task.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            await self.store.update_run(run_id, status="failed", completed_at=_utcnow())

    async def pause(self, run_id: str) -> dict[str, Any]:
        run = await self._require(run_id)
        if run["status"] != "running":
            raise ValueError("Only a running coverage run can be paused.")
        return (
            self.present(await self.store.update_run(run_id, status="paused", paused_at=_utcnow()))
            or {}
        )

    async def resume(
        self, run_id: str, dataset_id: Any, user: Any, *, wait: bool = False
    ) -> dict[str, Any]:
        run = await self._require(run_id)
        if run["status"] not in {"paused", "paused_budget", "running"}:
            raise ValueError("This coverage run cannot be resumed.")
        updated = await self.store.update_run(run_id, status="running", paused_at=None)
        if wait:
            await self.drive(run_id, dataset_id, user)
            return self.present(await self.store.get_run(run_id)) or updated
        return self.present(updated) or updated

    async def cancel(self, run_id: str) -> dict[str, Any]:
        await self._require(run_id)
        for item in await self.store.list_items(run_id, "pending"):
            await self.store.update_item(item["id"], status="cancelled")
        return (
            self.present(
                await self.store.update_run(run_id, status="cancelled", completed_at=_utcnow())
            )
            or {}
        )

    async def retry_failures(
        self, run_id: str, dataset_id: Any, user: Any, *, wait: bool = False
    ) -> dict[str, Any]:
        await self._require(run_id)
        await self.store.requeue_failed(run_id)
        updated = await self.store.update_run(
            run_id, status="running", completed_at=None, paused_at=None
        )
        if wait:
            await self._process(run_id, dataset_id, user)
            return self.present(await self.store.get_run(run_id)) or updated
        return self.present(updated) or updated

    async def reconcile(self, dataset_id: Any, user: Any) -> dict[str, int]:
        """Page through goals and compare hashes. This never calls the LLM."""
        counts = {"dirty": 0, "clean": 0, "unchanged": 0}
        offset = 0
        total = None
        while total is None or offset < total:
            goal_ids, total = await self.sources.goal_page(dataset_id, user, offset, 200)
            if not goal_ids:
                break
            for goal_id in goal_ids:
                outcome = await self._reconcile_one(dataset_id, user, goal_id)
                counts[outcome] = counts.get(outcome, 0) + 1
            offset += 200
        return counts

    async def _require(self, run_id: str) -> dict[str, Any]:
        run = await self.store.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        return run

    async def _produce(self, run_id: str, dataset_id: Any, user: Any, gate: _ScanGate) -> None:
        try:
            await self._scan(run_id, dataset_id, user, gate)
        finally:
            gate.finish()

    async def _scan(self, run_id: str, dataset_id: Any, user: Any, gate: _ScanGate) -> None:
        run = await self._require(run_id)
        if not self._scan_open(run):
            return
        scanned = int(run.get("scanned_goals") or 0)
        queued = int(run.get("queued_goals") or 0)
        skipped = int(run.get("skipped_goals") or 0)
        no_context = int(run.get("no_context_goals") or 0)
        total = int(run.get("total_goals") or 0) or None
        cap = run.get("max_goals")
        batch = int(run.get("batch_size") or 20)
        offset = scanned
        buffer: list[dict[str, Any]] = []
        discard = False
        try:
            while total is None or offset < total:
                status = await self._run_status(run_id)
                if status in _STOP_STATUSES:
                    discard = status == "cancelled"
                    return
                if cap is not None and queued >= int(cap):
                    return
                goal_ids, total = await self.sources.goal_page(
                    dataset_id, user, offset, _DISCOVERY_PAGE
                )
                if not goal_ids:
                    return
                for goal_id in goal_ids:
                    status = await self._run_status(run_id)
                    if status in _STOP_STATUSES:
                        discard = status == "cancelled"
                        return
                    if cap is not None and queued >= int(cap):
                        return
                    outcome = await self._consider(run, user, goal_id, buffer=buffer)
                    if outcome == "stopped":
                        discard = await self._run_status(run_id) == "cancelled"
                        return
                    scanned += 1
                    offset += 1
                    if outcome == "queued":
                        queued += 1
                    elif outcome == "insufficient":
                        no_context += 1
                    else:
                        skipped += 1
                    await self._publish_scan(
                        run_id,
                        scanned=scanned,
                        total=total,
                        queued=queued,
                        skipped=skipped,
                        no_context=no_context,
                    )
                    if outcome == "queued" and len(buffer) >= batch:
                        await self._flush(buffer, gate, dataset_id)
                    if cap is not None and queued >= int(cap):
                        return
        finally:
            if discard:
                queued -= len(buffer)
                buffer.clear()
                await self._publish_scan(
                    run_id,
                    scanned=scanned,
                    total=total,
                    queued=queued,
                    skipped=skipped,
                    no_context=no_context,
                )
            else:
                await self._flush(buffer, gate, dataset_id)

    def _scan_open(self, run: dict[str, Any]) -> bool:
        cap = run.get("max_goals")
        queued = int(run.get("queued_goals") or 0)
        if cap is not None and queued >= int(cap):
            return False
        total = int(run.get("total_goals") or 0)
        scanned = int(run.get("scanned_goals") or 0)
        return not total or scanned < total

    async def _run_status(self, run_id: str) -> str:
        run = await self.store.get_run(run_id)
        return str((run or {}).get("status") or "failed")

    async def _publish_scan(
        self,
        run_id: str,
        *,
        scanned: int,
        total: int | None,
        queued: int,
        skipped: int,
        no_context: int,
    ) -> None:
        await self.store.update_run(
            run_id,
            scanned_goals=scanned,
            total_goals=int(total or 0),
            eligible_goals=queued,
            queued_goals=queued,
            skipped_goals=skipped,
            no_context_goals=no_context,
        )

    async def _flush(self, buffer: list[dict[str, Any]], gate: _ScanGate, dataset_id: Any) -> None:
        if not buffer:
            return
        staged = list(buffer)
        buffer.clear()
        await self.store.add_items(
            [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in staged
            ]
        )
        for item in staged:
            await self._write_state(
                dataset_id,
                item["goal_id"],
                item.get("_state"),
                status="queued",
                semantic_context_hash=(item.get("_state") or {}).get("semantic_context_hash"),
                last_run_id=item["run_id"],
            )
        gate.pulse()
        await asyncio.sleep(0)

    async def _consider(
        self,
        run: dict[str, Any],
        user: Any,
        goal_id: str,
        buffer: list[dict[str, Any]] | None = None,
    ) -> str:
        dataset_id = run["dataset_id"]
        state = await self.store.get_state(dataset_id, goal_id)
        status = str((state or {}).get("status") or "never_analyzed")
        if run["mode"] == "baseline" and state and status != "never_analyzed":
            return "skip"
        context = await self.sources.context(dataset_id, user, goal_id)
        if run["mode"] == "incremental":
            state = await self._refresh_hash_state(dataset_id, user, goal_id, state, context)
        current = semantic_context_hash(context)
        proposal = await self.sources.open_proposal(dataset_id, goal_id)
        action = decide_coverage(run["mode"], state, context, proposal, current)
        if await self._run_status(run["id"]) in _STOP_STATUSES:
            return "stopped"
        if action == "skip":
            return "skip"
        if action == "insufficient":
            await self._write_state(
                dataset_id,
                goal_id,
                state,
                status="insufficient_context",
                semantic_context_hash=current,
                last_context_hash=context.get("context_hash"),
                last_run_id=run["id"],
            )
            return "insufficient"
        item = {
            "run_id": run["id"],
            "goal_id": goal_id,
            "priority": priority_for(context),
            "semantic_context_hash": current,
            "action": action,
        }
        if buffer is not None:
            buffer.append({**item, "_state": state})
            return "queued"
        await self.store.add_items([item])
        await self._write_state(
            dataset_id,
            goal_id,
            state,
            status="queued",
            semantic_context_hash=(state or {}).get("semantic_context_hash"),
            last_run_id=run["id"],
        )
        return "queued"

    async def _refresh_hash_state(
        self,
        dataset_id: Any,
        user: Any,
        goal_id: str,
        state: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not state or not state.get("semantic_context_hash"):
            return state
        if state.get("status") == "analyzing":
            return state
        current = semantic_context_hash(context)
        stored = state.get("semantic_context_hash")
        if stored == current and state.get("status") == "dirty":
            return await self._write_state(
                dataset_id, goal_id, state, status="clean", dirty_reason=None
            )
        if stored != current and state.get("status") != "queued":
            return await self._write_state(
                dataset_id,
                goal_id,
                state,
                status="dirty",
                dirty_reason="semantic_hash_changed",
            )
        return state

    async def _reconcile_one(self, dataset_id: Any, user: Any, goal_id: str) -> str:
        state = await self.store.get_state(dataset_id, goal_id)
        stored = (state or {}).get("semantic_context_hash")
        context = await self.sources.context(dataset_id, user, goal_id)
        current = semantic_context_hash(context)
        if not stored:
            return "unchanged"
        if stored == current:
            if state and state.get("status") == "dirty":
                await self._write_state(
                    dataset_id, goal_id, state, status="clean", dirty_reason=None
                )
                return "clean"
            return "unchanged"
        await self._write_state(
            dataset_id,
            goal_id,
            state,
            status="dirty",
            dirty_reason="semantic_hash_changed",
        )
        return "dirty"

    async def _process(
        self,
        run_id: str,
        dataset_id: Any,
        user: Any,
        gate: _ScanGate | None = None,
    ) -> None:
        if gate is None:
            gate = _ScanGate()
            gate.scan_done = True
        seen = gate.version
        inflight: set[asyncio.Task[None]] = set()
        while True:
            run = await self.store.get_run(run_id)
            if not run or run["status"] != "running":
                break
            if self._budget_exhausted(run):
                await self.store.update_run(run_id, status="paused_budget", paused_at=_utcnow())
                break
            if len(inflight) >= int(run["concurrency"]):
                await self._wait_some(inflight)
                continue
            item = await self.store.claim_next(run_id)
            if item is None:
                if inflight:
                    await self._wait_some(inflight)
                    continue
                if not gate.scan_done:
                    seen = await gate.wait(seen)
                    continue
                current = await self.store.get_run(run_id)
                if current and current["status"] == "running":
                    await self._complete_queue(run_id)
                break
            inflight.add(asyncio.create_task(self._one(run_id, dataset_id, user, item)))
        if inflight:
            await asyncio.gather(*inflight, return_exceptions=True)

    async def _complete_queue(self, run_id: str) -> None:
        for item in await self.store.list_items(run_id, "pending"):
            await self.store.update_item(item["id"], status="cancelled")
        await self.store.update_run(run_id, status="completed", completed_at=_utcnow())

    async def _wait_some(self, inflight: set[asyncio.Task[None]]) -> None:
        done, _pending = await asyncio.wait(inflight, return_when=asyncio.FIRST_COMPLETED)
        inflight.difference_update(done)

    async def _one(self, run_id: str, dataset_id: Any, user: Any, item: dict[str, Any]) -> None:
        goal_id = item["goal_id"]
        try:
            context = await self.sources.context(dataset_id, user, goal_id)
            current = semantic_context_hash(context)
            state = await self.store.get_state(dataset_id, goal_id)
            proposal = await self.sources.open_proposal(dataset_id, goal_id)
            run = await self.store.get_run(run_id) or {}
            action = decide_coverage(
                run.get("mode") or "incremental", state, context, proposal, current
            )
            if action == "skip":
                await self.store.update_item(
                    item["id"], status="skipped", semantic_context_hash=current
                )
                await self._bump(run_id, skipped_goals=1, processed_goals=1)
                await self._write_state(
                    dataset_id,
                    goal_id,
                    state,
                    status=_status_after_skip(state, proposal),
                    semantic_context_hash=current,
                )
                return
            if action == "insufficient" or insufficient_context(context):
                await self.store.update_item(
                    item["id"], status="skipped", semantic_context_hash=current
                )
                await self._bump(run_id, no_context_goals=1, processed_goals=1)
                await self._write_state(
                    dataset_id,
                    goal_id,
                    state,
                    status="insufficient_context",
                    semantic_context_hash=current,
                    last_context_hash=context.get("context_hash"),
                    last_run_id=run_id,
                )
                return
            if action == "stale_analyze" and proposal:
                await self.sources.mark_stale(dataset_id, user, proposal)
            await self._write_state(
                dataset_id, goal_id, state, status="analyzing", last_run_id=run_id
            )
            result = await self.sources.analyze(dataset_id, user, goal_id, run_id)
            if not await self._still_claimed(item):
                return
            await self._record_usage(run_id, item, result)
            await self.sources.remember_semantic_hash(dataset_id, user, result, current)
            await self._finish_success(
                run_id, dataset_id, goal_id, item, context, current, result, state
            )
        except Exception as exc:  # noqa: BLE001 - one goal must not abort the run
            if await self._still_claimed(item):
                await self._fail(run_id, dataset_id, item, exc)

    async def _finish_success(
        self,
        run_id: str,
        dataset_id: Any,
        goal_id: str,
        item: dict[str, Any],
        context: dict[str, Any],
        current: str,
        result: dict[str, Any],
        state: dict[str, Any] | None,
    ) -> None:
        latest = await self.store.get_state(dataset_id, goal_id)
        items = list(result.get("items") or [])
        supported = bool(items)
        status = "proposal_open" if supported else "no_supported_proposal"
        started_reason = (state or {}).get("dirty_reason")
        if latest and latest.get("dirty_reason") and latest.get("dirty_reason") != started_reason:
            status = "dirty"
        now = _utcnow()
        usage = _usage(result)
        await self._write_state(
            dataset_id,
            goal_id,
            latest or state,
            status=status,
            semantic_context_hash=current,
            last_context_hash=context.get("context_hash"),
            last_analyzed_at=now,
            last_success_at=now,
            last_proposal_id=str(result.get("id") or "") or None,
            last_run_id=run_id,
            prompt_version=PROMPT_VERSION,
            model_version=os.getenv("LLM_MODEL") or None,
            dirty_reason=None
            if status != "dirty"
            else latest.get("dirty_reason")
            if latest
            else None,
            retry_count=0,
            input_tokens=usage[0] if usage else None,
            output_tokens=usage[1] if usage else None,
            total_tokens=(usage[0] + usage[1]) if usage else None,
        )
        await self.store.update_item(
            item["id"],
            status="done",
            semantic_context_hash=current,
            proposal_id=str(result.get("id") or "") or None,
            input_tokens=usage[0] if usage else None,
            output_tokens=usage[1] if usage else None,
        )
        if supported:
            await self._bump(run_id, proposal_goals=1, processed_goals=1)
        else:
            await self._bump(run_id, no_change_goals=1, processed_goals=1)

    async def _fail(
        self, run_id: str, dataset_id: Any, item: dict[str, Any], exc: Exception
    ) -> None:
        logger.warning("Coverage goal %s failed: %s", item.get("goal_id"), exc)
        attempts = int(item.get("attempts") or 1)
        if attempts < MAX_ATTEMPTS:
            await self.store.update_item(item["id"], status="pending", error=str(exc))
            state = await self.store.get_state(dataset_id, item["goal_id"])
            await self._write_state(
                dataset_id,
                item["goal_id"],
                state,
                status="dirty",
                dirty_reason="retry",
                retry_count=attempts,
                last_run_id=run_id,
            )
            return
        await self.store.update_item(item["id"], status="failed", error=str(exc))
        state = await self.store.get_state(dataset_id, item["goal_id"])
        await self._write_state(
            dataset_id,
            item["goal_id"],
            state,
            status="retry_required",
            dirty_reason="retry_exhausted",
            retry_count=attempts,
            last_run_id=run_id,
        )
        await self._bump(run_id, failed_goals=1, processed_goals=1)

    async def _record_usage(
        self, run_id: str, item: dict[str, Any], result: dict[str, Any]
    ) -> None:
        if not self.token_usage_available:
            return
        usage = _usage(result)
        if usage is None:
            return
        async with self._lock:
            run = await self.store.get_run(run_id)
            if not run:
                return
            used_in = int(run.get("used_input_tokens") or 0) + usage[0]
            used_out = int(run.get("used_output_tokens") or 0) + usage[1]
            fields: dict[str, Any] = {"used_input_tokens": used_in, "used_output_tokens": used_out}
            budget = run.get("token_budget")
            if budget is not None and used_in + used_out >= int(budget):
                fields["status"] = "paused_budget"
                fields["paused_at"] = _utcnow()
            await self.store.update_run(run_id, **fields)
        await self.store.update_item(item["id"], input_tokens=usage[0], output_tokens=usage[1])

    async def _bump(self, run_id: str, **deltas: int) -> None:
        async with self._lock:
            run = await self.store.get_run(run_id)
            if not run:
                return
            fields = {key: int(run.get(key) or 0) + value for key, value in deltas.items()}
            await self.store.update_run(run_id, **fields)

    async def _write_state(
        self, dataset_id: Any, goal_id: str, state: dict[str, Any] | None, **fields: Any
    ) -> dict[str, Any]:
        current = dict(state or {})
        current["dataset_id"] = str(dataset_id)
        current["goal_id"] = str(goal_id)
        current.update(fields)
        return await self.store.upsert_state(current)

    async def _still_claimed(self, item: dict[str, Any]) -> bool:
        current = await self.store.get_item(item["id"])
        return bool(
            current
            and current.get("status") == "analyzing"
            and current.get("lease_expires_at") == item.get("lease_expires_at")
        )

    def _budget_exhausted(self, run: dict[str, Any]) -> bool:
        if not self.token_usage_available:
            return False
        budget = run.get("token_budget")
        if budget is None:
            return False
        if run.get("used_input_tokens") is None and run.get("used_output_tokens") is None:
            return False
        used = int(run.get("used_input_tokens") or 0) + int(run.get("used_output_tokens") or 0)
        return used >= int(budget)
