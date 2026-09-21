import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cognee.modules.company_tree.schema import CompanyTreeOut


@pytest.fixture
def client(monkeypatch):
    from cognee.api.v1.datasets.routers.get_company_tree_router import get_company_tree_router
    from cognee.modules.users.methods import get_authenticated_user as auth

    app = FastAPI()
    app.include_router(get_company_tree_router(), prefix="/api/v1/datasets")

    async def override_user():
        return SimpleNamespace(id=uuid.uuid4(), email="default@example.com", is_active=True)

    app.dependency_overrides[auth] = override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_company_tree_returns_assembled_payload(client, monkeypatch):
    import importlib

    router_mod = importlib.import_module("cognee.api.v1.datasets.routers.get_company_tree_router")

    async def fake_get(dataset_id, user, source_room=None):
        return CompanyTreeOut(
            nodes=[],
            edges=[],
            root_id=None,
            complete=False,
            missing=["empty"],
        )

    monkeypatch.setattr(router_mod, "get_company_tree", fake_get)
    dataset_id = uuid.uuid4()
    response = client.get(f"/api/v1/datasets/{dataset_id}/company-tree")
    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is False
    assert "empty" in body["missing"]


def test_put_company_tree_returns_missing_on_schema_failure(client, monkeypatch):
    dataset_id = uuid.uuid4()
    response = client.put(
        f"/api/v1/datasets/{dataset_id}/company-tree",
        json={
            "sourceRoom": "room-yk3tz4aj",
            "sourceRevision": "1",
            "nodes": [
                {
                    "sourceUid": "a",
                    "name": "A",
                    "cpdKind": "goal",
                    "sourceChildCount": 0,
                },
                {
                    "sourceUid": "b",
                    "name": "B",
                    "cpdKind": "goal",
                    "sourceChildCount": 0,
                },
            ],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert "missing" in body
    assert "root_missing_or_duplicate" in body["missing"]
