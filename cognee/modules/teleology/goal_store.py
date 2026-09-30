"""Persist a dataset teleology build. Memory is only for isolated tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from cognee.modules.teleology.goal_model import GoalBuildError
from cognee.modules.teleology.goal_tree import move_candidate, ordered_candidates


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def present_run(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    error = payload.get("error")
    return {
        "run_id": str(row.get("id") or row.get("run_id") or ""),
        "dataset_id": str(row.get("dataset_id") or ""),
        "status": row.get("status") or "pending",
        "stage": payload.get("stage") or row.get("status") or "pending",
        "processed_sources": int(payload.get("processed_sources") or 0),
        "source_count": int(row.get("source_count") or payload.get("source_count") or 0),
        "progress": float(payload.get("progress") or 0),
        "raw_candidate_count": int(payload.get("raw_candidate_count") or 0),
        "canonical_goal_count": int(
            payload.get("canonical_goal_count") or row.get("candidate_count") or 0
        ),
        "rejected_count": int(payload.get("rejected_count") or 0),
        "stage_stats": dict(payload.get("stage_stats") or {}),
        "error": error,
        "error_code": payload.get("error_code"),
        "committed": False,
        "graph_committed": False,
    }


def dataset_view(row: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    payload = dict((row or {}).get("payload") or {})
    merged = _merge_candidate_flags(candidates, payload.get("candidates") or [])
    original_ids = {
        str(goal.get("id")): index for index, goal in enumerate(payload.get("candidates") or [])
    }
    merged.sort(key=lambda goal: original_ids.get(str(goal.get("id")), len(original_ids)))
    payload["candidates"] = ordered_candidates(merged)
    payload["canonical_goal_count"] = sum(
        goal.get("status") not in {"rejected", "legacy_confirmed"}
        and not goal.get("outside_current_snapshot")
        for goal in payload["candidates"]
    )
    payload["committed"] = False
    payload["graph_committed"] = False
    payload.setdefault("dataset_id", str((row or {}).get("dataset_id") or ""))
    payload.setdefault("run_id", str((row or {}).get("id") or ""))
    payload.setdefault("status", (row or {}).get("status") or "empty")
    payload.setdefault("stage", payload.get("stage") or payload["status"])
    payload.setdefault(
        "purposes",
        list((payload.get("teleology") or {}).get("purposes") or payload.get("purposes") or []),
    )
    payload.setdefault(
        "constraints",
        list(
            (payload.get("teleology") or {}).get("constraints") or payload.get("constraints") or []
        ),
    )
    payload.setdefault(
        "relations",
        list((payload.get("teleology") or {}).get("relations") or payload.get("relations") or []),
    )
    payload["hierarchy"] = [
        {
            "id": goal.get("id"),
            "name": goal.get("name"),
            "parent_candidate_id": goal.get("parent_candidate_id"),
            "status": goal.get("status"),
            "confidence": goal.get("confidence"),
            "evidence_count": len(goal.get("evidence") or []),
            "sort_order": goal.get("sort_order"),
        }
        for goal in payload["candidates"]
        if goal.get("status") not in {"rejected", "legacy_confirmed"}
        and not goal.get("outside_current_snapshot")
    ]
    payload.setdefault("classifications", list(payload.get("classifications") or []))
    return payload


class MemoryGoalRunStore:
    """Isolated stand-in. Production uses SqlGoalModelStore."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.by_dataset: dict[str, str] = {}

    async def create_pending(self, row: dict[str, Any]) -> dict[str, Any]:
        stored = {
            "id": str(row["run_id"]),
            "dataset_id": str(row["dataset_id"]),
            "mode": row.get("mode") or "baseline",
            "status": "pending",
            "batch_size": row.get("batch_size") or 20,
            "concurrency": row.get("concurrency") or 1,
            "max_sources": row.get("max_sources"),
            "source_count": 0,
            "candidate_count": 0,
            "committed": 0,
            "payload": {"stage": "discovering", "progress": 0, "error": None, "error_code": None},
        }
        self.runs[stored["id"]] = stored
        self.by_dataset[stored["dataset_id"]] = stored["id"]
        return present_run(stored)

    async def update(self, run_id: str, **fields: Any) -> None:
        row = self.runs.get(str(run_id))
        if row is None:
            return
        payload = dict(row.get("payload") or {})
        for key, value in fields.items():
            if key in {"status", "source_count", "candidate_count"}:
                row[key] = value
            else:
                payload[key] = value
        row["payload"] = payload

    async def save_result(self, result: dict[str, Any]) -> None:
        run_id = str(result["run_id"])
        previous_run = self.runs.get(self.by_dataset.get(str(result["dataset_id"]), "")) or {}
        previous = {str(goal["id"]): goal for goal in previous_run.get("candidates") or []}
        candidates = [dict(goal) for goal in result.get("candidates") or []]
        current_ids = {str(goal["id"]) for goal in candidates}
        for goal in candidates:
            prior = previous.get(str(goal["id"])) or {}
            goal["sort_order"] = prior.get("sort_order")
            goal["parent_override"] = bool(prior.get("parent_override"))
            if goal["parent_override"] and (
                not prior.get("parent_candidate_id")
                or str(prior["parent_candidate_id"]) in current_ids
            ):
                goal["parent_candidate_id"] = prior.get("parent_candidate_id")
            elif goal["parent_override"]:
                goal["parent_override"] = False
        row = self.runs.get(run_id) or {
            "id": run_id,
            "dataset_id": str(result["dataset_id"]),
            "mode": result.get("mode") or "baseline",
            "committed": 0,
        }
        payload = dict(result)
        payload["committed"] = False
        payload["graph_committed"] = False
        row.update(
            {
                "status": result.get("status") or "completed",
                "source_count": result.get("source_count") or 0,
                "candidate_count": result.get("canonical_goal_count") or 0,
                "payload": payload,
                "candidates": candidates,
            }
        )
        row.setdefault("created_at", _now())
        row["completed_at"] = _now() if row.get("status") in {"completed", "failed"} else None
        row["mode"] = result.get("mode") or row.get("mode") or "baseline"
        self.runs[run_id] = row
        self.by_dataset[str(result["dataset_id"])] = run_id

    async def fail(self, run_id: str, error_code: str, message: str) -> None:
        await self.update(
            run_id,
            status="failed",
            stage="failed",
            error={"error_code": error_code, "message": message},
            error_code=error_code,
        )
        row = self.runs[str(run_id)]
        row["status"] = "failed"

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.runs.get(str(run_id))
        return None if row is None else present_run(row)

    async def list_runs(
        self,
        dataset_id: Any,
        *,
        mode: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = [
            row for row in self.runs.values() if str(row.get("dataset_id") or "") == str(dataset_id)
        ]
        if mode:
            rows = [row for row in rows if str(row.get("mode") or "") == mode]
        if status:
            rows = [row for row in rows if str(row.get("status") or "") == status]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        start = max(0, int(offset or 0))
        size = max(0, int(limit or 0))
        return [run_history_row(row) for row in rows[start : start + size]]

    async def find_idempotent(self, dataset_id: Any, key: str) -> dict[str, Any] | None:
        if not str(key or "").strip():
            return None
        matches = []
        for row in self.runs.values():
            if str(row.get("dataset_id") or "") != str(dataset_id):
                continue
            if row.get("status") != "completed":
                continue
            payload = row.get("payload") or {}
            if str(payload.get("idempotency_key") or "") == str(key):
                matches.append(row)
        if not matches:
            return None
        matches.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        payload = matches[0].get("payload") or {}
        return payload if isinstance(payload, dict) else None

    async def get_dataset(self, dataset_id: Any) -> dict[str, Any] | None:
        run_id = self.by_dataset.get(str(dataset_id))
        if not run_id:
            return None
        row = self.runs.get(run_id)
        if row is None or row.get("status") not in {"completed", "running", "pending", "failed"}:
            return None
        if row.get("status") != "completed":
            return None
        return dataset_view(row, list(row.get("candidates") or []))

    async def set_candidate_status(
        self, dataset_id: Any, candidate_id: str, status: str
    ) -> dict[str, Any]:
        if status not in {"proposed", "confirmed", "rejected"}:
            raise GoalBuildError("status must be proposed, confirmed, or rejected")
        view = await self.get_dataset(dataset_id)
        if view is None:
            raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
        found = None
        for goal in view.get("candidates") or []:
            if str(goal.get("id")) == str(candidate_id):
                goal["status"] = status
                found = goal
        if found is None:
            raise GoalBuildError("Review item not found", 404)
        run_id = self.by_dataset[str(dataset_id)]
        self.runs[run_id]["candidates"] = list(view["candidates"])
        self.runs[run_id]["payload"]["candidates"] = list(view["candidates"])
        return {"item": found, "graph_committed": False, "committed": False}

    async def move_candidate(
        self, dataset_id: Any, candidate_id: str, target_id: str | None, placement: str
    ) -> dict[str, Any]:
        run_id = self.by_dataset.get(str(dataset_id))
        row = self.runs.get(run_id or "")
        if row is None or row.get("status") != "completed":
            raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
        result = move_candidate(row["candidates"], candidate_id, target_id, placement)
        return {**result, "graph_committed": False, "committed": False}

    async def set_teleology_status(
        self, dataset_id: Any, item_id: str, status: str, kind: str
    ) -> dict[str, Any]:
        run_id = self.by_dataset.get(str(dataset_id))
        row = None if run_id is None else self.runs.get(run_id)
        if row is None or row.get("status") != "completed":
            raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
        found = _mark_review_item(row["payload"], item_id, status, kind)
        return {"item": found, "graph_committed": False, "committed": False}


class SqlGoalModelStore:
    """DB-backed derived layer. Confirming a candidate does not write the graph."""

    def __init__(self, sessionmaker: Any = None) -> None:
        self._sessionmaker = sessionmaker

    async def _session(self):
        if self._sessionmaker is not None:
            async with self._sessionmaker() as session:
                yield session
            return
        from cognee.infrastructure.databases.relational import get_relational_engine

        engine = get_relational_engine()
        async with engine.get_async_session() as session:
            yield session

    async def create_pending(self, row: dict[str, Any]) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        run_uuid = _uuid(row["run_id"])
        dataset_uuid = _uuid(row["dataset_id"])
        if run_uuid is None or dataset_uuid is None:
            raise GoalBuildError("run id and dataset id must be UUIDs")
        payload = {"stage": "discovering", "progress": 0, "error": None, "error_code": None}
        async for session in self._session():
            session.add(
                TeleologyBuildRunRecord(
                    id=run_uuid,
                    dataset_id=dataset_uuid,
                    mode=row.get("mode") or "baseline",
                    status="pending",
                    batch_size=int(row.get("batch_size") or 20),
                    concurrency=int(row.get("concurrency") or 1),
                    max_sources=row.get("max_sources"),
                    source_count=0,
                    candidate_count=0,
                    committed=0,
                    payload=json.dumps(payload),
                    created_at=_now(),
                )
            )
            await session.commit()
        return present_run(
            {
                "id": str(run_uuid),
                "dataset_id": str(dataset_uuid),
                "status": "pending",
                "payload": payload,
            }
        )

    async def update(self, run_id: str, **fields: Any) -> None:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        run_uuid = _uuid(run_id)
        if run_uuid is None:
            return
        async for session in self._session():
            record = await session.get(TeleologyBuildRunRecord, run_uuid)
            if record is None:
                return
            payload = json.loads(record.payload or "{}")
            for key, value in fields.items():
                if key == "status":
                    record.status = value
                elif key == "source_count":
                    record.source_count = int(value or 0)
                elif key == "candidate_count":
                    record.candidate_count = int(value or 0)
                else:
                    payload[key] = value
            record.payload = json.dumps(payload, ensure_ascii=False)
            await session.commit()

    async def save_result(self, result: dict[str, Any]) -> None:
        from cognee.modules.teleology.goal_model_models import (
            TeleologyBuildRunRecord,
            TeleologyGoalCandidateRecord,
        )

        run_uuid = _uuid(result["run_id"])
        dataset_uuid = _uuid(result["dataset_id"])
        if run_uuid is None or dataset_uuid is None:
            raise GoalBuildError("run id and dataset id must be UUIDs")
        payload = dict(result)
        payload["committed"] = False
        payload["graph_committed"] = False
        async for session in self._session():
            record = await session.get(TeleologyBuildRunRecord, run_uuid)
            if record is None:
                record = TeleologyBuildRunRecord(
                    id=run_uuid,
                    dataset_id=dataset_uuid,
                    mode=result.get("mode") or "baseline",
                    created_at=_now(),
                )
                session.add(record)
            record.status = result.get("status") or "completed"
            record.source_count = int(result.get("source_count") or 0)
            record.candidate_count = int(result.get("canonical_goal_count") or 0)
            record.committed = 0
            record.completed_at = _now() if record.status in {"completed", "failed"} else None
            record.payload = json.dumps(payload, ensure_ascii=False)
            existing = (
                (
                    await session.execute(
                        select(TeleologyGoalCandidateRecord).where(
                            TeleologyGoalCandidateRecord.dataset_id == dataset_uuid
                        )
                    )
                )
                .scalars()
                .all()
            )
            kept = {str(goal.get("id")) for goal in result.get("candidates") or []}
            for old in existing:
                if str(old.id) not in kept:
                    await session.delete(old)
            for goal in result.get("candidates") or []:
                current = await session.get(TeleologyGoalCandidateRecord, str(goal["id"]))
                if current is None:
                    current = TeleologyGoalCandidateRecord(id=str(goal["id"]), created_at=_now())
                    session.add(current)
                current.dataset_id = dataset_uuid
                current.name = goal.get("name") or ""
                current.description = goal.get("description")
                current.confidence = float(goal.get("confidence") or 0)
                current.reason = goal.get("reason") or ""
                current.source_node_ids = json.dumps(goal.get("source_node_ids") or [])
                current.evidence = json.dumps(goal.get("evidence") or [], ensure_ascii=False)
                kept_order = current.sort_order
                if current.parent_override and (
                    not current.parent_candidate_id or str(current.parent_candidate_id) in kept
                ):
                    pass
                else:
                    current.parent_candidate_id = goal.get("parent_candidate_id")
                    current.parent_override = bool(goal.get("parent_override"))
                if kept_order is not None:
                    current.sort_order = kept_order
                elif goal.get("sort_order") is not None:
                    current.sort_order = int(goal["sort_order"])
                current.status = goal.get("status") or "proposed"
                current.outside_current_snapshot = bool(
                    goal.get("outside_current_snapshot") or current.status == "legacy_confirmed"
                )
                current.run_id = str(result["run_id"])
                current.generated_by = goal.get("generated_by") or "dataset_goal_build"
                current.semantic_hash = goal.get("semantic_hash") or ""
                current.updated_at = _now()
            await session.commit()

    async def fail(self, run_id: str, error_code: str, message: str) -> None:
        await self.update(
            run_id,
            status="failed",
            stage="failed",
            error={"error_code": error_code, "message": message},
            error_code=error_code,
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        run_uuid = _uuid(run_id)
        if run_uuid is None:
            return None
        async for session in self._session():
            record = await session.get(TeleologyBuildRunRecord, run_uuid)
            if record is None:
                return None
            return present_run(_run_dict(record))
        return None

    async def list_runs(
        self,
        dataset_id: Any,
        *,
        mode: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            return []
        async for session in self._session():
            statement = select(TeleologyBuildRunRecord).where(
                TeleologyBuildRunRecord.dataset_id == dataset_uuid
            )
            if mode:
                statement = statement.where(TeleologyBuildRunRecord.mode == mode)
            if status:
                statement = statement.where(TeleologyBuildRunRecord.status == status)
            statement = statement.order_by(TeleologyBuildRunRecord.created_at.desc())
            statement = statement.offset(max(0, int(offset or 0))).limit(max(0, int(limit or 0)))
            records = (await session.execute(statement)).scalars().all()
            return [run_history_row(_run_dict(record)) for record in records]
        return []

    async def find_idempotent(self, dataset_id: Any, key: str) -> dict[str, Any] | None:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        if not str(key or "").strip():
            return None
        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            return None
        async for session in self._session():
            records = (
                (
                    await session.execute(
                        select(TeleologyBuildRunRecord)
                        .where(
                            TeleologyBuildRunRecord.dataset_id == dataset_uuid,
                            TeleologyBuildRunRecord.status == "completed",
                        )
                        .order_by(TeleologyBuildRunRecord.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            for record in records:
                payload = _run_dict(record).get("payload") or {}
                if str(payload.get("idempotency_key") or "") == str(key):
                    return payload
            return None
        return None

    async def get_dataset(self, dataset_id: Any) -> dict[str, Any] | None:
        from cognee.modules.teleology.goal_model_models import (
            TeleologyBuildRunRecord,
            TeleologyGoalCandidateRecord,
        )

        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            return None
        async for session in self._session():
            record = (
                (
                    await session.execute(
                        select(TeleologyBuildRunRecord)
                        .where(
                            TeleologyBuildRunRecord.dataset_id == dataset_uuid,
                            TeleologyBuildRunRecord.status == "completed",
                        )
                        .order_by(TeleologyBuildRunRecord.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if record is None:
                return None
            rows = (
                (
                    await session.execute(
                        select(TeleologyGoalCandidateRecord).where(
                            TeleologyGoalCandidateRecord.dataset_id == dataset_uuid
                        )
                    )
                )
                .scalars()
                .all()
            )
            return dataset_view(_run_dict(record), [_candidate_dict(row) for row in rows])
        return None

    async def set_candidate_status(
        self, dataset_id: Any, candidate_id: str, status: str
    ) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model_models import TeleologyGoalCandidateRecord

        if status not in {"proposed", "confirmed", "rejected"}:
            raise GoalBuildError("status must be proposed, confirmed, or rejected")
        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            raise GoalBuildError("dataset id must be a UUID")
        async for session in self._session():
            record = await session.get(TeleologyGoalCandidateRecord, str(candidate_id))
            if record is None or str(record.dataset_id) != str(dataset_uuid):
                raise GoalBuildError("Review item not found", 404)
            record.status = status
            record.updated_at = _now()
            await session.commit()
            return {
                "item": _candidate_dict(record),
                "graph_committed": False,
                "committed": False,
            }
        raise GoalBuildError("Review item not found", 404)

    async def move_candidate(
        self, dataset_id: Any, candidate_id: str, target_id: str | None, placement: str
    ) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model_models import TeleologyGoalCandidateRecord

        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            raise GoalBuildError("dataset id must be a UUID")
        view = await self.get_dataset(dataset_id)
        if view is None:
            raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
        display_order = {
            str(goal["id"]): index for index, goal in enumerate(view.get("candidates") or [])
        }
        async for session in self._session():
            records = (
                (
                    await session.execute(
                        select(TeleologyGoalCandidateRecord)
                        .where(TeleologyGoalCandidateRecord.dataset_id == dataset_uuid)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if not records:
                raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
            candidates = [_candidate_dict(record) for record in records]
            candidates.sort(key=lambda goal: display_order.get(str(goal["id"]), len(display_order)))
            result = move_candidate(candidates, candidate_id, target_id, placement)
            by_id = {str(goal["id"]): goal for goal in candidates}
            for record in records:
                goal = by_id[str(record.id)]
                record.parent_candidate_id = goal.get("parent_candidate_id")
                record.parent_override = bool(goal.get("parent_override"))
                record.sort_order = goal.get("sort_order")
                record.updated_at = _now()
            await session.commit()
            return {**result, "graph_committed": False, "committed": False}
        raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)

    async def set_teleology_status(
        self, dataset_id: Any, item_id: str, status: str, kind: str
    ) -> dict[str, Any]:
        from cognee.modules.teleology.goal_model_models import TeleologyBuildRunRecord

        dataset_uuid = _uuid(dataset_id)
        if dataset_uuid is None:
            raise GoalBuildError("dataset id must be a UUID")
        async for session in self._session():
            record = (
                (
                    await session.execute(
                        select(TeleologyBuildRunRecord)
                        .where(
                            TeleologyBuildRunRecord.dataset_id == dataset_uuid,
                            TeleologyBuildRunRecord.status == "completed",
                        )
                        .order_by(TeleologyBuildRunRecord.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if record is None:
                raise GoalBuildError("AI Goal Model has not been built for this dataset", 404)
            payload = json.loads(record.payload or "{}")
            found = _mark_review_item(payload, item_id, status, kind)
            record.payload = json.dumps(payload, ensure_ascii=False)
            await session.commit()
            return {"item": found, "graph_committed": False, "committed": False}
        raise GoalBuildError("Review item not found", 404)


def _mark_review_item(
    payload: dict[str, Any], item_id: str, status: str, kind: str
) -> dict[str, Any]:
    bucket = {"purpose": "purposes", "constraint": "constraints", "relation": "relations"}.get(kind)
    if bucket is None:
        raise GoalBuildError("kind must be purpose, constraint, or relation")
    if status not in {"proposed", "confirmed", "rejected"}:
        raise GoalBuildError("status must be proposed, confirmed, or rejected")
    found = None
    groups = [payload.get(bucket) or []]
    nested = payload.get("teleology")
    if isinstance(nested, dict):
        groups.append(nested.get(bucket) or [])
    for items in groups:
        for item in items:
            if str(item.get("id")) == str(item_id):
                item["status"] = status
                found = item
    if found is None:
        raise GoalBuildError("Review item not found", 404)
    return found


def run_history_row(row: dict[str, Any], record: Any = None) -> dict[str, Any]:
    """Run metadata only. Goal candidates stay out of this history row."""
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload or "{}")
        except json.JSONDecodeError:
            payload = {}
    created_at = row.get("created_at")
    completed_at = row.get("completed_at")
    if record is not None:
        created_at = created_at or getattr(record, "created_at", None)
        completed_at = completed_at or getattr(record, "completed_at", None)
    return {
        "run_id": str(row.get("id") or row.get("run_id") or ""),
        "dataset_id": str(row.get("dataset_id") or ""),
        "mode": row.get("mode") or payload.get("mode") or "",
        "generated_by": payload.get("generated_by") or "",
        "status": row.get("status") or "",
        "created_at": _iso(created_at),
        "completed_at": _iso(completed_at),
        "candidate_count": int(
            row.get("candidate_count") or payload.get("canonical_goal_count") or 0
        ),
        "committed": False,
        "graph_committed": False,
    }


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _run_dict(record: Any) -> dict[str, Any]:
    try:
        payload = json.loads(record.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": str(record.id),
        "dataset_id": str(record.dataset_id),
        "mode": record.mode,
        "status": record.status,
        "source_count": record.source_count,
        "candidate_count": record.candidate_count,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
        "payload": payload,
    }


def _merge_candidate_flags(
    rows: list[dict[str, Any]], stored: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep supplemental review flags from the run payload."""
    extras = {str(goal.get("id") or ""): goal for goal in stored}
    merged: list[dict[str, Any]] = []
    for goal in rows:
        extra = extras.get(str(goal.get("id") or "")) or {}
        row = dict(goal)
        for key in ("orchestrated_identity", "scope", "reason_provenance"):
            if extra.get(key) not in (None, "", [], {}):
                row[key] = extra[key]
        if extra.get("retirement_proposed"):
            row["retirement_proposed"] = True
            row["outside_current_snapshot"] = True
        if row.get("status") == "legacy_confirmed":
            row["outside_current_snapshot"] = True
        merged.append(row)
    return merged


def _candidate_dict(record: Any) -> dict[str, Any]:
    try:
        evidence = json.loads(record.evidence or "[]")
        source_ids = json.loads(record.source_node_ids or "[]")
    except json.JSONDecodeError:
        evidence, source_ids = [], []
    return {
        "id": record.id,
        "dataset_id": str(record.dataset_id),
        "name": record.name,
        "description": record.description or "",
        "confidence": record.confidence,
        "reason": record.reason,
        "source_node_ids": source_ids,
        "evidence": evidence,
        "parent_candidate_id": record.parent_candidate_id,
        "parent_override": bool(record.parent_override),
        "sort_order": record.sort_order,
        "status": record.status,
        "outside_current_snapshot": bool(
            record.outside_current_snapshot or record.status == "legacy_confirmed"
        ),
        "run_id": record.run_id,
        "generated_by": record.generated_by,
        "semantic_hash": record.semantic_hash,
    }


_installed: Any = None


def get_goal_store() -> Any:
    if _installed is not None:
        return _installed
    return SqlGoalModelStore()


def use_goal_store(store: Any) -> None:
    global _installed
    _installed = store
