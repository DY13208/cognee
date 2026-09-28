"""In-memory store for tests and a relational store for the API process."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from cognee.modules.teleology.proposal_store import _uuid, database_enabled

LEASE_SECONDS = 15 * 60
_RUN_DATES = frozenset({"created_at", "started_at", "paused_at", "completed_at"})
_STATE_DATES = frozenset({"last_analyzed_at", "last_success_at"})
_ITEM_DATES = frozenset({"lease_expires_at"})


def _priority(item: dict[str, Any]) -> int:
    value = item.get("priority")
    return 3 if value is None else int(value)


def _lease_stamp() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()


def _lease_due(item: dict[str, Any]) -> bool:
    raw = item.get("lease_expires_at")
    if not raw:
        return True
    moment = datetime.fromisoformat(str(raw))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment <= datetime.now(timezone.utc)


def _claimable(item: dict[str, Any]) -> bool:
    if item.get("status") == "pending":
        return True
    return item.get("status") == "analyzing" and _lease_due(item)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank_state(dataset_id: str, goal_id: str) -> dict[str, Any]:
    now = _now()
    return {
        "dataset_id": str(dataset_id),
        "goal_id": str(goal_id),
        "status": "never_analyzed",
        "semantic_context_hash": None,
        "last_context_hash": None,
        "last_analyzed_at": None,
        "last_success_at": None,
        "last_proposal_id": None,
        "last_run_id": None,
        "prompt_version": None,
        "model_version": None,
        "dirty_reason": None,
        "retry_count": 0,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "created_at": now,
        "updated_at": now,
    }


class MemoryCoverageStore:
    """Process-local stand-in. Tests use it to simulate a restart by sharing the object."""

    def __init__(self) -> None:
        self.states: dict[tuple[str, str], dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get_state(self, dataset_id: Any, goal_id: str) -> dict[str, Any] | None:
        return self.states.get((str(dataset_id), str(goal_id)))

    async def upsert_state(self, state: dict[str, Any]) -> dict[str, Any]:
        key = (str(state["dataset_id"]), str(state["goal_id"]))
        current = self.states.get(key) or _blank_state(key[0], key[1])
        current.update(state)
        current["updated_at"] = _now()
        self.states[key] = current
        return dict(current)

    async def mark_dirty(self, dataset_id: Any, goal_ids: list[str], reason: str) -> list[str]:
        marked = []
        for goal_id in goal_ids:
            if not goal_id:
                continue
            key = (str(dataset_id), str(goal_id))
            row = self.states.get(key) or _blank_state(key[0], key[1])
            row["dirty_reason"] = reason
            row["updated_at"] = _now()
            if row["status"] != "analyzing":
                row["status"] = "dirty"
            self.states[key] = row
            marked.append(str(goal_id))
        return marked

    async def list_states(
        self,
        dataset_id: Any,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = [
            dict(row)
            for (dataset, _goal), row in self.states.items()
            if dataset == str(dataset_id) and (not status or row["status"] == status)
        ]
        rows.sort(key=lambda row: row["goal_id"])
        counts: dict[str, int] = {}
        for (_dataset, _goal), row in self.states.items():
            if _dataset == str(dataset_id):
                counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "summary": counts,
        }

    async def create_run(self, run: dict[str, Any]) -> dict[str, Any]:
        run = dict(run)
        run.setdefault("id", str(uuid4()))
        run.setdefault("created_at", _now())
        self.runs[run["id"]] = run
        return dict(run)

    async def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        run = self.runs[str(run_id)]
        run.update(fields)
        return dict(run)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(str(run_id))
        return dict(run) if run else None

    async def active_run(self, dataset_id: Any) -> dict[str, Any] | None:
        for run in self.runs.values():
            if str(run["dataset_id"]) == str(dataset_id) and run["status"] in {
                "pending",
                "running",
                "paused",
                "paused_budget",
            }:
                return dict(run)
        return None

    async def add_items(self, items: list[dict[str, Any]]) -> int:
        added = 0
        existing = {(item["run_id"], item["goal_id"]) for item in self.items.values()}
        for item in items:
            key = (str(item["run_id"]), str(item["goal_id"]))
            if key in existing:
                continue
            row = dict(item)
            row.setdefault("id", str(uuid4()))
            row.setdefault("status", "pending")
            row.setdefault("attempts", 0)
            self.items[row["id"]] = row
            existing.add(key)
            added += 1
        return added

    async def claim_next(self, run_id: str) -> dict[str, Any] | None:
        async with self._lock:
            pending = [
                item
                for item in self.items.values()
                if item["run_id"] == str(run_id) and _claimable(item)
            ]
            pending.sort(key=lambda item: (_priority(item), item["goal_id"]))
            if not pending:
                return None
            item = pending[0]
            item["status"] = "analyzing"
            item["attempts"] = int(item.get("attempts") or 0) + 1
            item["lease_expires_at"] = _lease_stamp()
            return dict(item)

    async def get_item(self, item_id: str) -> dict[str, Any] | None:
        item = self.items.get(str(item_id))
        return dict(item) if item else None

    async def update_item(self, item_id: str, **fields: Any) -> dict[str, Any]:
        item = self.items[str(item_id)]
        item.update(fields)
        return dict(item)

    async def list_items(self, run_id: str, status: str | None = None) -> list[dict[str, Any]]:
        rows = [
            dict(item)
            for item in self.items.values()
            if item["run_id"] == str(run_id) and (not status or item["status"] == status)
        ]
        rows.sort(key=lambda item: (_priority(item), item["goal_id"]))
        return rows

    async def release_expired_leases(self, run_id: str) -> int:
        released = 0
        for item in self.items.values():
            if item["run_id"] == str(run_id) and item["status"] == "analyzing" and _lease_due(item):
                item["status"] = "pending"
                item["lease_expires_at"] = None
                released += 1
        return released

    async def requeue_failed(self, run_id: str) -> int:
        count = 0
        for item in self.items.values():
            if item["run_id"] == str(run_id) and item["status"] == "failed":
                item["status"] = "pending"
                item["attempts"] = 0
                item["error"] = None
                count += 1
        return count


def _as_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_run_record(run: dict[str, Any]):
    """Map a run payload onto the table, including started_at."""
    from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunRecord

    return TeleologyAnalysisRunRecord(
        id=_uuid(run.get("id")) or uuid4(),
        dataset_id=_uuid(run["dataset_id"]),
        mode=run["mode"],
        status=run.get("status") or "pending",
        batch_size=int(run.get("batch_size") or 20),
        concurrency=int(run.get("concurrency") or 3),
        max_goals=run.get("max_goals"),
        token_budget=run.get("token_budget"),
        used_input_tokens=run.get("used_input_tokens"),
        used_output_tokens=run.get("used_output_tokens"),
        total_goals=int(run.get("total_goals") or 0),
        scanned_goals=int(run.get("scanned_goals") or 0),
        eligible_goals=int(run.get("eligible_goals") or 0),
        queued_goals=int(run.get("queued_goals") or 0),
        processed_goals=int(run.get("processed_goals") or 0),
        skipped_goals=int(run.get("skipped_goals") or 0),
        proposal_goals=int(run.get("proposal_goals") or 0),
        no_change_goals=int(run.get("no_change_goals") or 0),
        no_context_goals=int(run.get("no_context_goals") or 0),
        failed_goals=int(run.get("failed_goals") or 0),
        created_at=_as_dt(run.get("created_at")) or datetime.now(timezone.utc),
        started_at=_as_dt(run.get("started_at")),
        paused_at=_as_dt(run.get("paused_at")),
        completed_at=_as_dt(run.get("completed_at")),
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SqlCoverageStore:
    """Durable queue. API restarts continue from these rows."""

    async def _session(self):
        from cognee.modules.teleology.proposal_store import _engine

        if not database_enabled():
            raise RuntimeError("Teleology coverage requires the relational database.")
        return (await _engine()).get_async_session()

    async def get_state(self, dataset_id: Any, goal_id: str) -> dict[str, Any] | None:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisStateRecord

        dataset = _uuid(dataset_id)
        async with await self._session() as session:
            row = (
                await session.execute(
                    select(TeleologyAnalysisStateRecord).where(
                        TeleologyAnalysisStateRecord.dataset_id == dataset,
                        TeleologyAnalysisStateRecord.goal_id == str(goal_id),
                    )
                )
            ).scalar_one_or_none()
            return _state_dict(row) if row else None

    async def upsert_state(self, state: dict[str, Any]) -> dict[str, Any]:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisStateRecord

        dataset = _uuid(state["dataset_id"])
        async with await self._session() as session:
            row = (
                await session.execute(
                    select(TeleologyAnalysisStateRecord).where(
                        TeleologyAnalysisStateRecord.dataset_id == dataset,
                        TeleologyAnalysisStateRecord.goal_id == str(state["goal_id"]),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = TeleologyAnalysisStateRecord(
                    id=uuid4(),
                    dataset_id=dataset,
                    goal_id=str(state["goal_id"]),
                    created_at=datetime.now(timezone.utc),
                )
            _apply_state(row, state)
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            await session.commit()
            return _state_dict(row)

    async def mark_dirty(self, dataset_id: Any, goal_ids: list[str], reason: str) -> list[str]:
        marked = []
        for goal_id in dict.fromkeys(goal_ids):
            if not goal_id:
                continue
            current = await self.get_state(dataset_id, goal_id) or _blank_state(dataset_id, goal_id)
            current["dirty_reason"] = reason
            if current["status"] != "analyzing":
                current["status"] = "dirty"
            await self.upsert_state(current)
            marked.append(str(goal_id))
        return marked

    async def list_states(
        self,
        dataset_id: Any,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        from sqlalchemy import func, select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisStateRecord

        dataset = _uuid(dataset_id)
        async with await self._session() as session:
            filters = [TeleologyAnalysisStateRecord.dataset_id == dataset]
            if status:
                filters.append(TeleologyAnalysisStateRecord.status == status)
            total = (
                await session.execute(
                    select(func.count()).select_from(TeleologyAnalysisStateRecord).where(*filters)
                )
            ).scalar_one()
            rows = (
                (
                    await session.execute(
                        select(TeleologyAnalysisStateRecord)
                        .where(*filters)
                        .order_by(TeleologyAnalysisStateRecord.goal_id)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            grouped = (
                await session.execute(
                    select(
                        TeleologyAnalysisStateRecord.status,
                        func.count(),
                    )
                    .where(TeleologyAnalysisStateRecord.dataset_id == dataset)
                    .group_by(TeleologyAnalysisStateRecord.status)
                )
            ).all()
        return {
            "items": [_state_dict(row) for row in rows],
            "total": int(total or 0),
            "summary": {str(name): int(count) for name, count in grouped},
        }

    async def create_run(self, run: dict[str, Any]) -> dict[str, Any]:
        record = build_run_record(run)
        async with await self._session() as session:
            session.add(record)
            await session.commit()
            return _run_dict(record)

    async def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunRecord

        async with await self._session() as session:
            row = await session.get(TeleologyAnalysisRunRecord, _uuid(run_id))
            if row is None:
                raise KeyError(run_id)
            for key, value in fields.items():
                if not hasattr(row, key):
                    continue
                if key in _RUN_DATES:
                    value = _as_dt(value)
                setattr(row, key, value)
            await session.commit()
            return _run_dict(row)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunRecord

        async with await self._session() as session:
            row = await session.get(TeleologyAnalysisRunRecord, _uuid(run_id))
            return _run_dict(row) if row else None

    async def active_run(self, dataset_id: Any) -> dict[str, Any] | None:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunRecord

        async with await self._session() as session:
            row = (
                await session.execute(
                    select(TeleologyAnalysisRunRecord)
                    .where(
                        TeleologyAnalysisRunRecord.dataset_id == _uuid(dataset_id),
                        TeleologyAnalysisRunRecord.status.in_(
                            ("pending", "running", "paused", "paused_budget")
                        ),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _run_dict(row) if row else None

    async def add_items(self, items: list[dict[str, Any]]) -> int:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        if not items:
            return 0
        added = 0
        async with await self._session() as session:
            for item in items:
                run_id = _uuid(item["run_id"])
                exists = (
                    await session.execute(
                        select(TeleologyAnalysisRunItemRecord.id).where(
                            TeleologyAnalysisRunItemRecord.run_id == run_id,
                            TeleologyAnalysisRunItemRecord.goal_id == str(item["goal_id"]),
                        )
                    )
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                session.add(
                    TeleologyAnalysisRunItemRecord(
                        id=uuid4(),
                        run_id=run_id,
                        goal_id=str(item["goal_id"]),
                        priority=int(item.get("priority") or 3),
                        status="pending",
                        semantic_context_hash=item.get("semantic_context_hash"),
                        attempts=0,
                        action=item.get("action"),
                    )
                )
                added += 1
            await session.commit()
        return added

    @staticmethod
    def claim_statement(run_id: Any, now: datetime | None = None):
        """One row lock. SKIP LOCKED keeps a second worker off this goal."""
        from sqlalchemy import and_, or_, select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        moment = now or datetime.now(timezone.utc)
        item = TeleologyAnalysisRunItemRecord
        return (
            select(item)
            .where(
                item.run_id == _uuid(run_id),
                or_(
                    item.status == "pending",
                    and_(
                        item.status == "analyzing",
                        or_(item.lease_expires_at.is_(None), item.lease_expires_at < moment),
                    ),
                ),
            )
            .order_by(item.priority, item.goal_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def claim_next(self, run_id: str) -> dict[str, Any] | None:
        async with await self._session() as session:
            row = (await session.execute(self.claim_statement(run_id))).scalar_one_or_none()
            if row is None:
                return None
            row.status = "analyzing"
            row.attempts = int(row.attempts or 0) + 1
            row.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)
            await session.commit()
            return _item_dict(row)

    async def get_item(self, item_id: str) -> dict[str, Any] | None:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        async with await self._session() as session:
            row = (
                await session.execute(
                    select(TeleologyAnalysisRunItemRecord).where(
                        TeleologyAnalysisRunItemRecord.id == _uuid(item_id)
                    )
                )
            ).scalar_one_or_none()
            return _item_dict(row) if row else None

    async def update_item(self, item_id: str, **fields: Any) -> dict[str, Any]:
        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        async with await self._session() as session:
            row = await session.get(TeleologyAnalysisRunItemRecord, _uuid(item_id))
            if row is None:
                raise KeyError(item_id)
            for key, value in fields.items():
                if not hasattr(row, key):
                    continue
                if key in _ITEM_DATES:
                    value = _as_dt(value)
                setattr(row, key, value)
            await session.commit()
            return _item_dict(row)

    async def list_items(self, run_id: str, status: str | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        filters = [TeleologyAnalysisRunItemRecord.run_id == _uuid(run_id)]
        if status:
            filters.append(TeleologyAnalysisRunItemRecord.status == status)
        async with await self._session() as session:
            rows = (
                (
                    await session.execute(
                        select(TeleologyAnalysisRunItemRecord)
                        .where(*filters)
                        .order_by(
                            TeleologyAnalysisRunItemRecord.priority,
                            TeleologyAnalysisRunItemRecord.goal_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [_item_dict(row) for row in rows]

    async def release_expired_leases(self, run_id: str) -> int:
        from sqlalchemy import or_, select

        from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord

        moment = datetime.now(timezone.utc)
        item = TeleologyAnalysisRunItemRecord
        async with await self._session() as session:
            rows = (
                (
                    await session.execute(
                        select(item)
                        .where(
                            item.run_id == _uuid(run_id),
                            item.status == "analyzing",
                            or_(item.lease_expires_at.is_(None), item.lease_expires_at < moment),
                        )
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                row.status = "pending"
                row.lease_expires_at = None
            await session.commit()
        return len(rows)

    async def requeue_failed(self, run_id: str) -> int:
        items = await self.list_items(run_id, "failed")
        for item in items:
            await self.update_item(item["id"], status="pending", attempts=0, error=None)
        return len(items)


def _apply_state(row: Any, state: dict[str, Any]) -> None:
    for key in (
        "status",
        "semantic_context_hash",
        "last_context_hash",
        "last_proposal_id",
        "last_run_id",
        "prompt_version",
        "model_version",
        "dirty_reason",
        "retry_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    ):
        if key in state:
            setattr(row, key, state[key])
    for key in _STATE_DATES:
        if key in state:
            setattr(row, key, _as_dt(state[key]))


def _state_dict(row: Any) -> dict[str, Any]:
    return {
        "dataset_id": str(row.dataset_id),
        "goal_id": row.goal_id,
        "status": row.status,
        "semantic_context_hash": row.semantic_context_hash,
        "last_context_hash": row.last_context_hash,
        "last_analyzed_at": _iso(row.last_analyzed_at),
        "last_success_at": _iso(row.last_success_at),
        "last_proposal_id": row.last_proposal_id,
        "last_run_id": row.last_run_id,
        "prompt_version": row.prompt_version,
        "model_version": row.model_version,
        "dirty_reason": row.dirty_reason,
        "retry_count": row.retry_count,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _run_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "dataset_id": str(row.dataset_id),
        "mode": row.mode,
        "status": row.status,
        "batch_size": row.batch_size,
        "concurrency": row.concurrency,
        "max_goals": row.max_goals,
        "token_budget": row.token_budget,
        "used_input_tokens": row.used_input_tokens,
        "used_output_tokens": row.used_output_tokens,
        "total_goals": row.total_goals,
        "scanned_goals": row.scanned_goals,
        "eligible_goals": row.eligible_goals,
        "queued_goals": row.queued_goals,
        "processed_goals": row.processed_goals,
        "skipped_goals": row.skipped_goals,
        "proposal_goals": row.proposal_goals,
        "no_change_goals": row.no_change_goals,
        "no_context_goals": row.no_context_goals,
        "failed_goals": row.failed_goals,
        "created_at": _iso(row.created_at),
        "started_at": _iso(row.started_at),
        "paused_at": _iso(row.paused_at),
        "completed_at": _iso(row.completed_at),
    }


def _item_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "goal_id": row.goal_id,
        "priority": row.priority,
        "status": row.status,
        "semantic_context_hash": row.semantic_context_hash,
        "attempts": row.attempts,
        "lease_expires_at": _iso(row.lease_expires_at),
        "proposal_id": row.proposal_id,
        "error": row.error,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "action": row.action,
    }
