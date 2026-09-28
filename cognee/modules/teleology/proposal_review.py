"""Read-only, dataset-scoped views of stored teleology proposals."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select

from cognee.modules.teleology.coverage_models import TeleologyAnalysisRunItemRecord
from cognee.modules.teleology.proposal_models import TeleologyProposalRecord
from cognee.modules.teleology.proposal_store import _engine, _uuid, database_enabled

_ITEM_FIELDS = (
    "id",
    "kind",
    "name",
    "description",
    "source",
    "target",
    "relationship",
    "confidence",
    "reason",
    "evidence_node_ids",
    "evidence",
    "source_goal_ids",
    "review_status",
)


def _json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _view(payload: dict[str, Any], row: Any | None = None, *, detail: bool = False) -> dict:
    fields = (
        "id",
        "dataset_id",
        "run_id",
        "source_goal_id",
        "status",
        "generated_by",
        "context_hash",
        "semantic_context_hash",
        "analysis_summary",
        "created_at",
        "committed_at",
    )
    result = {key: payload.get(key) for key in fields}
    if row is not None:
        for key in fields:
            if key == "created_at":
                result[key] = _iso(row.created_at)
            elif key == "committed_at":
                result[key] = _iso(row.committed_at)
            elif key in {"id", "dataset_id"}:
                result[key] = str(getattr(row, key))
            elif key != "analysis_summary" or row.analysis_summary is not None:
                result[key] = getattr(row, key)
    if detail:
        result["items"] = [
            {key: item.get(key) for key in _ITEM_FIELDS}
            for item in payload.get("items") or []
            if isinstance(item, dict)
        ]
        result["weak_signals"] = payload.get("weak_signals") or []
        result["open_conflicts"] = payload.get("open_conflicts") or []
    else:
        result["items_count"] = len(payload.get("items") or [])
    return result


async def list_proposals(
    dataset_id: UUID,
    *,
    run_id: str | None = None,
    source_goal_id: str | None = None,
    status: str | None = None,
    generated_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if not database_enabled():
        from cognee.modules.teleology.purpose_layer import _load

        rows = list((_load(dataset_id).get("proposals") or {}).values())
        rows = [p for p in rows if str(p.get("dataset_id")) == str(dataset_id)]
        for key, value in (
            ("run_id", run_id),
            ("source_goal_id", source_goal_id),
            ("status", status),
            ("generated_by", generated_by),
        ):
            if value is not None:
                rows = [p for p in rows if p.get(key) == value]
        rows.sort(
            key=lambda p: (str(p.get("created_at") or ""), str(p.get("id") or "")), reverse=True
        )
        return {
            "items": [_view(p) for p in rows[offset : offset + limit]],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    filters = [TeleologyProposalRecord.dataset_id == dataset_id]
    for column, value in (
        (TeleologyProposalRecord.source_goal_id, source_goal_id),
        (TeleologyProposalRecord.status, status),
        (TeleologyProposalRecord.generated_by, generated_by),
    ):
        if value is not None:
            filters.append(column == value)
    async with (await _engine()).get_async_session() as session:
        if run_id is not None:
            run_uuid = _uuid(run_id)
            if run_uuid is None:
                return {"items": [], "total": 0, "limit": limit, "offset": offset}
            linked_ids = (
                (
                    await session.execute(
                        select(TeleologyAnalysisRunItemRecord.proposal_id).where(
                            TeleologyAnalysisRunItemRecord.run_id == run_uuid,
                            TeleologyAnalysisRunItemRecord.proposal_id.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            proposal_ids = [_uuid(value) for value in linked_ids]
            proposal_ids = [value for value in proposal_ids if value is not None]
            filters.append(
                or_(
                    TeleologyProposalRecord.run_id == run_id,
                    TeleologyProposalRecord.id.in_(proposal_ids),
                )
            )
        total = (
            await session.execute(
                select(func.count()).select_from(TeleologyProposalRecord).where(*filters)
            )
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(TeleologyProposalRecord)
                    .where(*filters)
                    .order_by(
                        TeleologyProposalRecord.created_at.desc(), TeleologyProposalRecord.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [_view(_json(row.payload), row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


async def get_proposal(dataset_id: UUID, proposal_id: str) -> dict[str, Any] | None:
    proposal_uuid = _uuid(proposal_id)
    if proposal_uuid is None:
        return None
    if not database_enabled():
        from cognee.modules.teleology.purpose_layer import _load

        payload = (_load(dataset_id).get("proposals") or {}).get(proposal_id)
        if not payload or str(payload.get("dataset_id")) != str(dataset_id):
            return None
        return _view(payload, detail=True)
    async with (await _engine()).get_async_session() as session:
        row = (
            await session.execute(
                select(TeleologyProposalRecord).where(
                    TeleologyProposalRecord.id == proposal_uuid,
                    TeleologyProposalRecord.dataset_id == dataset_id,
                )
            )
        ).scalar_one_or_none()
        return _view(_json(row.payload), row, detail=True) if row else None
