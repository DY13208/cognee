"""Unit tests for MCP API-key middleware helpers."""

import importlib
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

mcp_auth = importlib.import_module("src.mcp_auth")


@pytest.fixture(autouse=True)
def _require_auth(monkeypatch):
    monkeypatch.setenv("MCP_REQUIRE_API_KEY", "true")


async def _ok(_request: Request):
    return JSONResponse({"ok": True, "key": mcp_auth.get_request_api_key()})


def _app(validate_ok: bool = True):
    async def fake_validate(api_key: str, api_url=None):
        return validate_ok and api_key == "good-key"

    mcp_auth.validate_api_key = fake_validate  # type: ignore[assignment]
    app = Starlette(routes=[Route("/mcp", _ok, methods=["POST"]), Route("/health", _ok)])
    app.add_middleware(mcp_auth.McpApiKeyMiddleware, api_url=None)
    return app


def test_missing_key_returns_401():
    client = TestClient(_app())
    response = client.post("/mcp")
    assert response.status_code == 401


def test_invalid_key_returns_401():
    client = TestClient(_app(validate_ok=False))
    response = client.post("/mcp", headers={"X-Api-Key": "bad"})
    assert response.status_code == 401


def test_valid_key_passes_and_sets_context():
    client = TestClient(_app(validate_ok=True))
    response = client.post("/mcp", headers={"X-Api-Key": "good-key"})
    assert response.status_code == 200
    assert response.json()["key"] == "good-key"


def test_health_skips_auth():
    client = TestClient(_app())
    response = client.get("/health")
    assert response.status_code == 200


def test_options_skips_auth():
    client = TestClient(_app())
    response = client.options("/mcp")
    # Starlette may 405 if OPTIONS not registered; middleware must not 401.
    assert response.status_code != 401
