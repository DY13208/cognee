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

# TODO: LLMGateway.acreate_structured_output does not return provider token
# usage to analyze_goal. Counts stay null until that hook exists. Do not estimate.


class CoverageSources(Protocol):
    async def goal_page(
        self, dataset_id: Any, user: Any, offset: int, limit: int
    ) -> tuple[list[str], int]: ...

    async def context(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]: ...

    async def analyze(self, dataset_id: Any, user: Any, goal_id: str) -> dict[str, Any]: ...

    async def open_proposal(self, dataset_id: Any, goal_id: str) -> dict[str, Any] | None: ...

    async def mark_stale(self, dataset_id: Any, user: Any, proposal: dict[str, Any]) -> None: ...

    async def remember_semantic_hash(
        self, dataset_id: Any, user: Any, proposal: dict[str, Any], semantic_hash: str
    ) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_after_skip(state: dict[str, Any] | None, proposal: dict[str, Any] | None) -> str:
    if proposal and proposal.get("status") == "open":
        return "proposal_open"
    current = str((state or {}).get("status") or "clean")
    if current in {"confirmed", "clean", "no_supported_proposal", "insufficient_context"}:
        return current
    return "clean"


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

    def __init__(self, store: Any, sources: CoverageSources) -> None:
        self.store = store
        self.sources = sources
        self._lock = asyncio.Lock()

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
                "eligible_goals": 0,
                "queued_goals": 0,
                "processed_goals": 0,
                "skipped_goals": 0,
                "proposal_goals": 0,
                "no_change_goals": 0,
                "no_context_goals": 0,
                "failed_goals": 0,
                "started_at": _now(),
            }
        )
        self.current_run_id = run["id"]
        if wait:
            await self.drive(run["id"], dataset_id, user)
            return await self.store.get_run(run["id"]) or run
        return run

    async def drive(self, run_id: str, dataset_id: Any, user: Any) -> None:
        run = await self.store.get_run(run_id)
        if not run:
            return
        try:
            if run["status"] in {"pending", "paused", "paused_budget"}:
                await self.store.update_run(
                    run_id, status="running", started_at=run.get("started_at") or _now()
                )
            await self.store.release_analyzing(run_id)
            if int(run.get("queued_goals") or 0) == 0 and not await self.store.list_items(run_id):
                await self._enqueue(run_id, dataset_id, user)
            await self._process(run_id, dataset_id, user)
        except Exception:
            logger.exception("Teleology coverage run %s failed", run_id)
            await self.store.update_run(run_id, status="failed", completed_at=_now())

    async def pause(self, run_id: str) -> dict[str, Any]:
        run = await self._require(run_id)
        if run["status"] != "running":
            raise ValueError("Only a running coverage run can be paused.")
        return await self.store.update_run(run_id, status="paused", paused_at=_now())

    async def resume(
        self, run_id: str, dataset_id: Any, user: Any, *, wait: bool = False
    ) -> dict[str, Any]:
        run = await self._require(run_id)
        if run["status"] not in {"paused", "paused_budget", "running"}:
            raise ValueError("This coverage run cannot be resumed.")
        updated = await self.store.update_run(run_id, status="running", paused_at=None)
        if wait:
            await self.drive(run_id, dataset_id, user)
            return await self.store.get_run(run_id) or updated
        return updated

    async def cancel(self, run_id: str) -> dict[str, Any]:
        await self._require(run_id)
        for item in await self.store.list_items(run_id, "pending"):
            await self.store.update_item(item["id"], status="cancelled")
        return await self.store.update_run(run_id, status="cancelled", completed_at=_now())

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
            return await self.store.get_run(run_id) or updated
        return updated

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

    async def _enqueue(self, run_id: str, dataset_id: Any, user: Any) -> None:
        run = await self._require(run_id)
        offset = 0
        total = None
        queued = skipped = no_context = 0
        while total is None or offset < total:
            goal_ids, total = await self.sources.goal_page(dataset_id, user, offset, 200)
            if not goal_ids:
                break
            for goal_id in goal_ids:
                outcome = await self._consider(run, user, goal_id)
                if outcome == "queued":
                    queued += 1
                elif outcome == "insufficient":
                    no_context += 1
                else:
                    skipped += 1
            offset += 200
        await self.store.update_run(
            run_id,
            total_goals=int(total or 0),
            eligible_goals=queued,
            queued_goals=queued,
            skipped_goals=skipped,
            no_context_goals=no_context,
        )

    async def _consider(self, run: dict[str, Any], user: Any, goal_id: str) -> str:
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
        await self.store.add_items(
            [
                {
                    "run_id": run["id"],
                    "goal_id": goal_id,
                    "priority": priority_for(context),
                    "semantic_context_hash": current,
                    "action": action,
                }
            ]
        )
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

    async def _process(self, run_id: str, dataset_id: Any, user: Any) -> None:
        inflight: set[asyncio.Task[None]] = set()
        while True:
            run = await self.store.get_run(run_id)
            if not run or run["status"] != "running":
                break
            if self._budget_exhausted(run) or self._goal_cap_reached(run):
                status = "paused_budget" if self._budget_exhausted(run) else "completed"
                await self.store.update_run(
                    run_id,
                    status=status,
                    paused_at=_now() if status == "paused_budget" else None,
                    completed_at=_now() if status == "completed" else None,
                )
                break
            if len(inflight) >= int(run["concurrency"]):
                await self._wait_some(inflight)
                continue
            item = await self.store.claim_next(run_id)
            if item is None:
                if inflight:
                    await self._wait_some(inflight)
                    continue
                await self.store.update_run(run_id, status="completed", completed_at=_now())
                break
            inflight.add(asyncio.create_task(self._one(run_id, dataset_id, user, item)))
        if inflight:
            await asyncio.gather(*inflight, return_exceptions=True)

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
            result = await self.sources.analyze(dataset_id, user, goal_id)
            await self._record_usage(run_id, item, result)
            await self.sources.remember_semantic_hash(dataset_id, user, result, current)
            await self._finish_success(
                run_id, dataset_id, goal_id, item, context, current, result, state
            )
        except Exception as exc:  # noqa: BLE001 - one goal must not abort the run
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
        now = _now()
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
                fields["paused_at"] = _now()
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

    def _budget_exhausted(self, run: dict[str, Any]) -> bool:
        budget = run.get("token_budget")
        if budget is None:
            return False
        if run.get("used_input_tokens") is None and run.get("used_output_tokens") is None:
            return False
        used = int(run.get("used_input_tokens") or 0) + int(run.get("used_output_tokens") or 0)
        return used >= int(budget)

    def _goal_cap_reached(self, run: dict[str, Any]) -> bool:
        cap = run.get("max_goals")
        if cap is None:
            return False
        analyzed = int(run.get("proposal_goals") or 0) + int(run.get("no_change_goals") or 0)
        return analyzed >= int(cap)
