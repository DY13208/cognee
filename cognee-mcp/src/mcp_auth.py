"""Per-request MCP API-key auth (permanent user keys from /api/v1/auth/api-keys)."""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from cognee.shared.logging_utils import get_logger

logger = get_logger("mcp_auth")

# Raw API key presented by the MCP client (Cursor headers). Used to call the
# Cognee HTTP API as that user when the MCP server runs in API mode.
_mcp_api_key: ContextVar[Optional[str]] = ContextVar("mcp_api_key", default=None)


def get_request_api_key() -> Optional[str]:
    return _mcp_api_key.get()


def set_request_api_key(api_key: Optional[str]):
    return _mcp_api_key.set(api_key)


def reset_request_api_key(token) -> None:
    _mcp_api_key.reset(token)


def mcp_auth_required() -> bool:
    """Require X-Api-Key on MCP HTTP unless explicitly disabled."""
    return os.getenv("MCP_REQUIRE_API_KEY", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def extract_api_key(request: Request) -> Optional[str]:
    header = request.headers.get("x-api-key")
    if header and header.strip():
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


async def validate_api_key(api_key: str, api_url: Optional[str] = None) -> bool:
    """Return True if the key maps to a user.

    Prefer validating against the Cognee HTTP API when ``api_url`` is set
    (API mode). Fall back to a direct DB lookup so a key that exists in the
    shared relational store still works if /auth/me rejects for transport
    reasons. Direct mode validates only via the DB.
    """
    if not api_key:
        return False

    if api_url:
        import httpx

        base = api_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{base}/api/v1/auth/me",
                    headers={"X-Api-Key": api_key},
                )
                if response.status_code == 200:
                    return True
                logger.info("MCP API key rejected by /auth/me (HTTP %s)", response.status_code)
        except Exception as exc:
            logger.error("MCP API key validation against API failed: %s", exc)

        # Fall through to DB — same postgres as the API container.
        db_ok = await _validate_api_key_db(api_key)
        if db_ok:
            logger.info("MCP API key accepted via shared DB after /auth/me miss")
        return db_ok

    return await _validate_api_key_db(api_key)


async def _validate_api_key_db(api_key: str) -> bool:
    try:
        from cognee.modules.users.api_key.hash_api_key import prepare_api_key
        from cognee.modules.users.models import User
        from cognee.modules.users.models.UserApiKey import UserApiKey
        from cognee.infrastructure.databases.relational import get_relational_engine
        from sqlalchemy import select

        prepared = prepare_api_key(api_key)
        engine = get_relational_engine()
        async with engine.get_async_session() as session:
            row = (
                await session.execute(select(UserApiKey).filter_by(api_key=prepared))
            ).scalar_one_or_none()
            if row is None:
                return False
            user = (
                await session.execute(select(User).filter_by(id=row.user_id))
            ).scalar_one_or_none()
            return user is not None
    except Exception as exc:
        logger.error("MCP API key DB validation failed: %s", exc)
        return False


class McpApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated MCP traffic when MCP_REQUIRE_API_KEY is on.

    ``/health`` stays open for Docker healthchecks.
    """

    def __init__(self, app: ASGIApp, api_url: Optional[str] = None):
        super().__init__(app)
        self.api_url = api_url

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or ""
        if request.method == "OPTIONS":
            return await call_next(request)
        if path.rstrip("/").endswith("/health") or path.endswith("/health"):
            return await call_next(request)
        # WorkBuddy / Cursor probe OAuth discovery before MCP initialize; do not
        # treat those as authenticated API calls.
        if "/.well-known/" in path or path.rstrip("/").endswith("/register"):
            return await call_next(request)

        if not mcp_auth_required():
            return await call_next(request)

        api_key = extract_api_key(request)
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Missing X-Api-Key. Copy your permanent key from the MCP Access page.",
                },
            )

        if not await validate_api_key(api_key, self.api_url):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "Invalid API key."},
            )

        token = set_request_api_key(api_key)
        try:
            return await call_next(request)
        finally:
            reset_request_api_key(token)
