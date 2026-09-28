"""Proposal review reads stored data without changing the proposal or queue."""

import importlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from cognee.infrastructure.databases.relational import Base
from cognee.modules.teleology import coverage_service, coverage_sources, proposal_review
from cognee.modules.teleology.coverage_models import (
    TeleologyAnalysisRunItemRecord,
    TeleologyAnalysisRunRecord,
)
from cognee.modules.teleology.coverage_store import SqlCoverageStore
from cognee.modules.teleology.proposal_models import TeleologyProposalRecord
from cognee.modules.users.methods import get_authenticated_user

router_module = importlib.import_module("cognee.api.v1.teleology.routers.get_teleology_router")


@pytest.mark.asyncio
async def test_coverage_analysis_passes_current_run_id_to_proposal(monkeypatch):
    calls = []

    async def analyze_goal(dataset_id, user, goal_id, *, run_id=None):
        calls.append((dataset_id, goal_id, run_id))
        return {"run_id": run_id}

    monkeypatch.setattr(coverage_sources, "analyze_goal", analyze_goal)
    dataset_id = uuid4()
    run_id = str(uuid4())
    result = await coverage_sources.ProductionSources().analyze(
        dataset_id, object(), "goal-1", run_id
    )
    assert result["run_id"] == run_id
    assert calls == [(dataset_id, "goal-1", run_id)]


class _Engine:
    def __init__(self, factory):
        self.factory = factory

    def get_async_session(self):
        return self.factory()


class _Store(SqlCoverageStore):
    def __init__(self, factory):
        self.factory = factory

    async def _session(self):
        return self.factory()


@pytest_asyncio.fixture
async def review_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                TeleologyProposalRecord.__table__,
                TeleologyAnalysisRunRecord.__table__,
                TeleologyAnalysisRunItemRecord.__table__,
            ],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(proposal_review, "database_enabled", lambda: True)

    async def get_engine():
        return _Engine(factory)

    monkeypatch.setattr(proposal_review, "_engine", get_engine)
    dataset_a, dataset_b, run_b = (uuid4() for _ in range(3))
    run_a = UUID("df0a2f50-9507-4d0d-9eac-18a892c92f81")
    proposals = []
    async with factory() as session:
        for index in range(4):
            proposal_id = uuid4()
            dataset = dataset_a if index < 3 else dataset_b
            goal_id = "g1" if index in (0, 1) else "g2"
            # First proposal models a legacy coverage result with an unrelated stored run_id.
            stored_run = str(run_b if index != 1 else run_a)
            item = {
                "id": str(uuid4()),
                "kind": "relation",
                "name": "a advances b",
                "description": "",
                "source": "a",
                "target": "b",
                "relationship": "advances",
                "confidence": 0.7,
                "reason": "evidence supports it",
                "evidence_node_ids": ["node-1"],
                "evidence": [{"id": "node-1", "text": "proof"}],
                "source_goal_ids": [goal_id],
                "review_status": "proposed",
            }
            payload = {
                "id": str(proposal_id),
                "dataset_id": str(dataset),
                "run_id": stored_run,
                "source_goal_id": goal_id,
                "status": "open",
                "generated_by": "purpose-agent",
                "context_hash": "ctx",
                "semantic_context_hash": "semantic",
                "analysis_summary": "reasoning",
                "items": [item],
                "weak_signals": [{"reason": "low confidence"}],
                "open_conflicts": [{"type": "similar_open_proposal"}],
            }
            session.add(
                TeleologyProposalRecord(
                    id=proposal_id,
                    dataset_id=dataset,
                    source_goal_id=goal_id,
                    status="open",
                    generated_by="purpose-agent",
                    run_id=stored_run,
                    context_hash="ctx",
                    semantic_context_hash="semantic",
                    analysis_summary="reasoning",
                    payload=json.dumps(payload),
                )
            )
            proposals.append(payload)
        session.add(TeleologyAnalysisRunRecord(id=run_a, dataset_id=dataset_a, mode="baseline"))
        session.add(TeleologyAnalysisRunRecord(id=run_b, dataset_id=dataset_b, mode="baseline"))
        for index, proposal in enumerate(proposals[:2]):
            session.add(
                TeleologyAnalysisRunItemRecord(
                    id=uuid4(),
                    run_id=run_a,
                    goal_id=f"g{index}",
                    priority=index,
                    status="done" if index == 0 else "pending",
                    attempts=index,
                    action="analyze",
                    semantic_context_hash="semantic",
                    proposal_id=proposal["id"],
                    input_tokens=12,
                    output_tokens=8,
                )
            )
        await session.commit()
    yield SimpleNamespace(
        factory=factory,
        engine=engine,
        dataset_a=dataset_a,
        dataset_b=dataset_b,
        run_a=run_a,
        run_b=run_b,
        proposals=proposals,
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_filters_run_goal_and_pagination(review_db):
    db = review_db
    listed = await proposal_review.list_proposals(db.dataset_a)
    assert listed["total"] == 3
    assert listed["limit"] == 50
    assert all(row["items_count"] == 1 for row in listed["items"])
    assert "payload" not in listed["items"][0]
    run = await proposal_review.list_proposals(db.dataset_a, run_id=str(db.run_a))
    assert {row["id"] for row in run["items"]} == {
        db.proposals[0]["id"],
        db.proposals[1]["id"],
    }
    goal = await proposal_review.list_proposals(db.dataset_a, source_goal_id="g1")
    assert goal["total"] == 2
    assert (await proposal_review.list_proposals(db.dataset_a, status="open"))["total"] == 3
    assert (await proposal_review.list_proposals(db.dataset_a, generated_by="manual"))["total"] == 0
    page = await proposal_review.list_proposals(db.dataset_a, limit=1, offset=1)
    assert page["total"] == 3 and len(page["items"]) == 1
    assert page["items"][0]["id"] != listed["items"][0]["id"]
    assert (await proposal_review.list_proposals(db.dataset_b, run_id=str(db.run_a)))["total"] == 0


@pytest.mark.asyncio
async def test_run_filter_returns_all_ten_linked_proposals_and_excludes_other_runs(review_db):
    db = review_db
    async with db.factory() as session:
        for index in range(8):
            proposal_id = uuid4()
            payload = {
                "id": str(proposal_id),
                "dataset_id": str(db.dataset_a),
                "run_id": str(db.run_a),
                "source_goal_id": f"extra-{index}",
                "status": "open",
                "generated_by": "purpose-agent",
                "items": [],
            }
            session.add(
                TeleologyProposalRecord(
                    id=proposal_id,
                    dataset_id=db.dataset_a,
                    source_goal_id=f"extra-{index}",
                    status="open",
                    generated_by="purpose-agent",
                    run_id=str(db.run_a),
                    payload=json.dumps(payload),
                )
            )
            session.add(
                TeleologyAnalysisRunItemRecord(
                    id=uuid4(),
                    run_id=db.run_a,
                    goal_id=f"extra-{index}",
                    status="done",
                    proposal_id=str(proposal_id),
                )
            )
        await session.commit()
    result = await proposal_review.list_proposals(db.dataset_a, run_id=str(db.run_a))
    assert result["total"] == 10 and len(result["items"]) == 10
    assert db.proposals[2]["id"] not in {row["id"] for row in result["items"]}


@pytest.mark.asyncio
async def test_detail_preserves_all_review_evidence_and_is_dataset_scoped(review_db):
    db = review_db
    proposal = await proposal_review.get_proposal(db.dataset_a, db.proposals[0]["id"])
    assert proposal["items"][0]["evidence"] == [{"id": "node-1", "text": "proof"}]
    assert proposal["items"][0]["reason"] == "evidence supports it"
    assert proposal["items"][0]["source_goal_ids"] == ["g1"]
    assert proposal["weak_signals"] == [{"reason": "low confidence"}]
    assert proposal["open_conflicts"] == [{"type": "similar_open_proposal"}]
    assert await proposal_review.get_proposal(db.dataset_b, db.proposals[0]["id"]) is None
    assert await proposal_review.get_proposal(db.dataset_a, "missing") is None


@pytest.mark.asyncio
async def test_run_items_status_and_pagination_are_read_only(review_db):
    db = review_db
    store = _Store(db.factory)
    all_items = await store.list_items_page(str(db.run_a))
    assert all_items["total"] == 2
    assert all_items["items"][0]["action"] == "analyze"
    assert all_items["items"][0]["input_tokens"] == 12
    done = await store.list_items_page(str(db.run_a), status="done")
    assert done["total"] == 1 and done["items"][0]["status"] == "done"
    page = await store.list_items_page(str(db.run_a), limit=1, offset=1)
    assert page["total"] == 2 and len(page["items"]) == 1
    commits = []

    def on_commit(_session):
        commits.append(True)

    event.listen(Session, "after_commit", on_commit)
    try:
        before = await proposal_review.get_proposal(db.dataset_a, db.proposals[0]["id"])
        await proposal_review.list_proposals(db.dataset_a)
        await store.list_items_page(str(db.run_a))
        after = await proposal_review.get_proposal(db.dataset_a, db.proposals[0]["id"])
        assert after == before and after["status"] == "open"
        assert (await proposal_review.list_proposals(db.dataset_a))["total"] == 3
        assert commits == []
    finally:
        event.remove(Session, "after_commit", on_commit)


@pytest.mark.asyncio
async def test_run_items_authorizes_owner_dataset(review_db, monkeypatch):
    db = review_db
    store = _Store(db.factory)
    monkeypatch.setattr(
        coverage_service, "get_coverage_engine", lambda: SimpleNamespace(store=store)
    )
    checked = []

    async def authorize(dataset_id, user, permission):
        checked.append((dataset_id, permission))
        if dataset_id != db.dataset_a:
            raise PermissionError("dataset denied")

    monkeypatch.setattr("cognee.modules.teleology.graph_annotations._authorized_dataset", authorize)
    assert (await coverage_service.coverage_items(str(db.run_a), object()))["total"] == 2
    assert checked == [(db.dataset_a, "read")]
    with pytest.raises(PermissionError):
        await coverage_service.coverage_items(str(db.run_b), object())


@pytest.mark.asyncio
async def test_http_review_routes_enforce_dataset_access_without_writes(review_db, monkeypatch):
    db = review_db
    store = _Store(db.factory)
    monkeypatch.setattr(
        coverage_service, "get_coverage_engine", lambda: SimpleNamespace(store=store)
    )

    async def authorize(dataset_id, _user, _permission):
        if dataset_id != db.dataset_a:
            from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError

            raise DatasetNotFoundError(message="Dataset not found.")

    monkeypatch.setattr(router_module, "_authorized_dataset", authorize)
    monkeypatch.setattr("cognee.modules.teleology.graph_annotations._authorized_dataset", authorize)
    app = FastAPI()
    from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError

    @app.exception_handler(DatasetNotFoundError)
    async def missing_dataset(_request, _exc):
        return JSONResponse(status_code=404, content={"error": "Dataset not found."})

    app.include_router(router_module.get_teleology_router(), prefix="/api/v1/teleology")
    app.dependency_overrides[get_authenticated_user] = lambda: SimpleNamespace(id=uuid4())
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    base = "/api/v1/teleology"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"{base}/proposals",
            params={
                "dataset_id": str(db.dataset_a),
                "run_id": str(db.run_a),
            },
        )
        assert response.status_code == 200 and response.json()["total"] == 2
        response = await client.get(
            f"{base}/proposals/{db.proposals[0]['id']}",
            params={"dataset_id": str(db.dataset_a)},
        )
        assert response.status_code == 200
        assert response.json()["items"][0]["evidence"][0]["text"] == "proof"
        response = await client.get(
            f"{base}/coverage/runs/{db.run_a}/items", params={"status": "done"}
        )
        assert response.status_code == 200 and response.json()["total"] == 1
        response = await client.get(
            f"{base}/proposals/{db.proposals[0]['id']}",
            params={"dataset_id": str(db.dataset_b)},
        )
        assert response.status_code in (403, 404)
        response = await client.get(f"{base}/coverage/runs/{db.run_b}/items")
        assert response.status_code in (403, 404)
        response = await client.get(
            f"{base}/proposals", params={"dataset_id": str(db.dataset_a), "limit": 201}
        )
        assert response.status_code == 422
    assert (await proposal_review.list_proposals(db.dataset_a))["total"] == 3
    assert (await proposal_review.get_proposal(db.dataset_a, db.proposals[0]["id"]))[
        "status"
    ] == "open"
