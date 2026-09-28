"""Persist proposals in the relational database, with the JSON file as fallback."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

_db_disabled: bool | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def database_enabled() -> bool:
    """DB is the default. JSON is used when explicitly requested or the DB host is unreachable."""
    global _db_disabled
    mode = os.getenv("TELEOLOGY_PROPOSAL_STORE", "auto").strip().lower()
    if mode == "json":
        return False
    if mode == "db":
        return True
    if _db_disabled is not None:
        return not _db_disabled
    host = os.getenv("DB_HOST", "").strip().strip('"')
    if host:
        try:
            socket.getaddrinfo(host, None)
        except socket.gaierror:
            _db_disabled = True
            return False
    return True


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _engine():
    from cognee.infrastructure.databases.relational import get_relational_engine

    return get_relational_engine()


async def save_proposal(dataset_id: UUID, proposal: dict[str, Any], user: Any | None = None) -> None:
    if not database_enabled():
        from cognee.modules.teleology.purpose_layer import _load, _save

        payload = _load(dataset_id)
        payload["proposals"][proposal["id"]] = proposal
        _save(dataset_id, payload)
        return
    from sqlalchemy import delete

    from cognee.modules.teleology.proposal_models import (
        TeleologyProposalItemRecord,
        TeleologyProposalRecord,
    )

    proposal_uuid = _uuid(proposal["id"])
    dataset_uuid = _uuid(dataset_id)
    if proposal_uuid is None or dataset_uuid is None:
        raise ValueError("Proposal id and dataset id must be UUIDs")
    user_id = _uuid(getattr(user, "id", None))
    committed_at = _now() if proposal.get("status") == "committed" else None
    async with (await _engine()).get_async_session() as session:
        existing = await session.get(TeleologyProposalRecord, proposal_uuid)
        record = existing or TeleologyProposalRecord(id=proposal_uuid, created_at=_now())
        record.dataset_id = dataset_uuid
        record.source_goal_id = str(proposal.get("source_goal_id") or "")
        record.status = str(proposal.get("status") or "open")
        record.generated_by = str(proposal.get("generated_by") or "")
        record.run_id = str(proposal.get("run_id") or "") or None
        record.source_revision = str(proposal.get("source_revision") or "") or None
        record.context_hash = str(proposal.get("context_hash") or "") or None
        record.semantic_context_hash = str(proposal.get("semantic_context_hash") or "") or None
        record.analysis_summary = proposal.get("analysis_summary") or None
        record.user_id = user_id
        record.payload = json.dumps(proposal, ensure_ascii=False)
        record.committed_at = committed_at
        session.add(record)
        await session.execute(
            delete(TeleologyProposalItemRecord).where(
                TeleologyProposalItemRecord.proposal_id == proposal_uuid
            )
        )
        for item in proposal.get("items") or []:
            item_id = _uuid(item.get("id"))
            if item_id is None:
                continue
            session.add(
                TeleologyProposalItemRecord(
                    id=item_id,
                    proposal_id=proposal_uuid,
                    kind=str(item.get("kind") or ""),
                    name=item.get("name"),
                    description=item.get("description"),
                    source=item.get("source"),
                    target=item.get("target"),
                    relationship=item.get("relationship"),
                    confidence=item.get("confidence"),
                    reason=item.get("reason"),
                    evidence_node_ids=json.dumps(item.get("evidence_node_ids") or []),
                    source_goal_ids=json.dumps(item.get("source_goal_ids") or []),
                    review_status=str(item.get("review_status") or item.get("status") or "proposed"),
                    committed_node_id=item.get("committed_node_id"),
                    committed_edge_key=item.get("committed_edge_key"),
                    created_at=_now(),
                )
            )
        await session.commit()


async def load_proposals(dataset_id: UUID) -> dict[str, Any]:
    if database_enabled():
        try:
            return await _load_db(dataset_id)
        except Exception:  # noqa: BLE001 - any DB failure falls back to the JSON store
            global _db_disabled
            _db_disabled = True
    from cognee.modules.teleology.purpose_layer import _load

    return _load(dataset_id)


async def _load_db(dataset_id: UUID) -> dict[str, Any]:
    from cognee.modules.teleology.proposal_models import TeleologyProposalRecord

    dataset_uuid = _uuid(dataset_id)
    if dataset_uuid is None:
        return {"proposals": {}}
    async with (await _engine()).get_async_session() as session:
        rows = (
            await session.execute(
                select(TeleologyProposalRecord).where(
                    TeleologyProposalRecord.dataset_id == dataset_uuid
                )
            )
        ).scalars().all()
    proposals = {}
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("id"):
            if row.semantic_context_hash and not payload.get("semantic_context_hash"):
                payload["semantic_context_hash"] = row.semantic_context_hash
            if row.context_hash and not payload.get("context_hash"):
                payload["context_hash"] = row.context_hash
            proposals[str(payload["id"])] = payload
    return {"proposals": proposals}


async def load_proposal(dataset_id: UUID, proposal_id: str) -> dict[str, Any] | None:
    payload = await load_proposals(dataset_id)
    return (payload.get("proposals") or {}).get(proposal_id)


async def open_items(dataset_id: UUID) -> list[dict[str, Any]]:
    payload = await load_proposals(dataset_id)
    items: list[dict[str, Any]] = []
    for proposal in (payload.get("proposals") or {}).values():
        if proposal.get("status") != "open":
            continue
        for item in proposal.get("items") or []:
            copied = dict(item)
            copied["proposal_id"] = proposal.get("id")
            items.append(copied)
    return items
