"""API-facing coverage operations. The worker is restarted from the database."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from cognee.modules.teleology.coverage_engine import CoverageEngine
from cognee.modules.teleology.coverage_sources import ProductionSources
from cognee.modules.teleology.coverage_store import SqlCoverageStore

_engine: CoverageEngine | None = None
_tasks: dict[str, asyncio.Task[None]] = {}


class CoverageServiceError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_coverage_engine() -> CoverageEngine:
    global _engine
    if _engine is None:
        _engine = CoverageEngine(SqlCoverageStore(), ProductionSources())
    return _engine


def _schedule(run_id: str, dataset_id: Any, user_id: Any, *, retry: bool = False) -> None:
    current = _tasks.get(run_id)
    if current is not None and not current.done():
        return

    async def _run() -> None:
        from cognee.modules.users.methods.get_user import get_user

        user = await get_user(UUID(str(user_id)))
        engine = get_coverage_engine()
        if retry:
            await engine.retry_failures(run_id, dataset_id, user, wait=True)
        else:
            await engine.drive(run_id, dataset_id, user)

    _tasks[run_id] = asyncio.create_task(_run())


async def start_coverage(dataset_id: UUID, user: Any, **options: Any) -> dict[str, Any]:
    try:
        run = await get_coverage_engine().start(dataset_id, user, wait=False, **options)
    except ValueError as exc:
        raise CoverageServiceError(400, str(exc)) from exc
    except RuntimeError as exc:
        raise CoverageServiceError(409, str(exc)) from exc
    _schedule(run["id"], dataset_id, user.id)
    return run


async def coverage_run(run_id: str) -> dict[str, Any]:
    engine = get_coverage_engine()
    run = await engine.store.get_run(run_id)
    if not run:
        raise CoverageServiceError(404, "Coverage run not found.")
    return engine.present(run) or run


async def coverage_items(
    run_id: str, user: Any, *, status: str | None = None, limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from cognee.modules.teleology.graph_annotations import _authorized_dataset

    try:
        UUID(str(run_id))
    except ValueError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc
    run = await get_coverage_engine().store.get_run(run_id)
    if not run:
        raise CoverageServiceError(404, "Coverage run not found.")
    await _authorized_dataset(UUID(str(run["dataset_id"])), user, "read")
    return await get_coverage_engine().store.list_items_page(
        run_id, status=status, limit=limit, offset=offset
    )


async def pause_coverage(run_id: str) -> dict[str, Any]:
    try:
        return await get_coverage_engine().pause(run_id)
    except KeyError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc
    except ValueError as exc:
        raise CoverageServiceError(409, str(exc)) from exc


async def resume_coverage(run_id: str, dataset_id: UUID, user: Any) -> dict[str, Any]:
    try:
        run = await get_coverage_engine().resume(run_id, dataset_id, user, wait=False)
    except KeyError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc
    except ValueError as exc:
        raise CoverageServiceError(409, str(exc)) from exc
    _schedule(run_id, dataset_id, user.id)
    return run


async def cancel_coverage(run_id: str) -> dict[str, Any]:
    try:
        return await get_coverage_engine().cancel(run_id)
    except KeyError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc


async def retry_coverage_failures(run_id: str, dataset_id: UUID, user: Any) -> dict[str, Any]:
    try:
        run = await get_coverage_engine().retry_failures(run_id, dataset_id, user, wait=False)
    except KeyError as exc:
        raise CoverageServiceError(404, "Coverage run not found.") from exc
    _schedule(run["id"], dataset_id, user.id)
    return run


async def coverage_state(
    dataset_id: UUID,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return await get_coverage_engine().store.list_states(
        dataset_id, status=status, limit=limit, offset=offset
    )
