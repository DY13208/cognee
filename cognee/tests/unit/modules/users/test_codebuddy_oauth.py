import base64
import hashlib
import importlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cognee.api.v1.users.routers import get_auth_router
from cognee.api.v1.users.routers import get_codebuddy_router as routes
from cognee.modules.data.models.Dataset import Dataset
from cognee.modules.users.authentication import codebuddy as oauth
from cognee.modules.users.authentication import codebuddy_sharing as sharing
from cognee.modules.users.models import ACL, OAuthIdentity, Permission, User
from cognee.modules.users.models.Principal import Principal
from cognee.modules.users.models.User import UserRead


@pytest.fixture(autouse=True, scope="session")
def _relational_db_for_unit_tests():
    # This suite owns an in-memory database; never migrate an operator's configured DB.
    yield


@pytest.fixture(autouse=True)
def config(monkeypatch):
    values = {
        "CODEBUDDY_ENABLED": "true",
        "CODEBUDDY_CLIENT_ID": "test-client",
        "CODEBUDDY_CLIENT_SECRET": "test-client-secret",
        "CODEBUDDY_REDIRECT_URI": "https://127.0.0.1:3030/oauth/callback",
        "CODEBUDDY_SESSION_SECRET": "test-signing-key-" * 4,
        "CODEBUDDY_SESSION_LIFETIME_SECONDS": "604800",
        "ENABLE_BACKEND_ACCESS_CONTROL": "true",
        "CODEBUDDY_SHARED_DATASET_IDS": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return oauth.get_config()


def test_authorization_state_pkce_and_expiry(config):
    location, cookie = oauth.begin_authorization(config)
    query = parse_qs(urlsplit(location).query)
    verifier = oauth.verify_state(config, cookie, query["state"][0])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == [challenge.decode()]
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [config.redirect_uri]
    assert config.client_secret not in location
    with pytest.raises(oauth.OAuthError, match="invalid_state"):
        oauth.verify_state(config, cookie, "another-browser-state")
    with pytest.raises(oauth.OAuthError, match="invalid_state"):
        oauth.verify_state(config, "tampered", query["state"][0])
    secret, _ = oauth.session_settings()
    payload = jwt.decode(cookie, secret, algorithms=["HS256"], audience="codebuddy-oauth")
    payload["exp"] = int(time.time()) - 1
    with pytest.raises(oauth.OAuthError, match="invalid_state"):
        oauth.verify_state(
            config, jwt.encode(payload, secret, algorithm="HS256"), query["state"][0]
        )


@pytest.mark.asyncio
async def test_token_exchange_and_userinfo(config, monkeypatch):
    requests = []

    def provider(request):
        requests.append(request)
        if request.url.path.endswith("/token"):
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["authorization_code"]
            assert form["code_verifier"] == ["test-verifier"]
            assert form["redirect_uri"] == [config.redirect_uri]
            assert form["client_secret"] == [config.client_secret]
            return httpx.Response(
                200, json={"access_token": "provider-secret", "token_type": "Bearer"}
            )
        assert request.headers["authorization"] == "Bearer provider-secret"
        return httpx.Response(200, json={"sub": "member-1", "name": "Member"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(provider), **kw),
    )
    profile = await oauth.fetch_userinfo(config, "test-code", "test-verifier")
    assert profile["sub"] == "member-1"
    assert "access_token" not in profile
    assert len(requests) == 2


@pytest.mark.parametrize("profile", [{}, {"sub": ""}, {"sub": True}, {"sub": ["bad"]}])
def test_profile_requires_stable_subject(profile):
    with pytest.raises(oauth.OAuthError, match="invalid_profile"):
        oauth.profile_subject(profile)


@pytest.mark.asyncio
async def test_identity_persistence_isolation_and_disabled_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (Principal.__table__, User.__table__, OAuthIdentity.__table__):
            await conn.run_sync(table.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        oauth, "get_relational_engine", lambda: SimpleNamespace(get_async_session=sessions)
    )
    try:
        first = await oauth.resolve_user({"sub": "one", "email": "same@example.com", "name": "One"})
        again = await oauth.resolve_user({"sub": "one", "email": "changed@example.com"})
        second = await oauth.resolve_user({"sub": "two", "email": "same@example.com"})
        assert first.id == again.id
        assert second.id != first.id
        assert first.is_superuser is False
        assert first.tenant_id is None
        # The ordinary /users/me response still goes through FastAPI Users' EmailStr schema.
        assert UserRead.model_validate(first, from_attributes=True).id == first.id
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 2
            user = await session.get(User, first.id)
            user.is_active = False
            await session.commit()
        with pytest.raises(oauth.OAuthError, match="account_disabled"):
            await oauth.resolve_user({"sub": "one"})
    finally:
        await engine.dispose()


def test_callback_establishes_secure_session_and_logout_clears_it(monkeypatch):
    app = FastAPI()
    app.include_router(get_auth_router(), prefix="/api/v1/auth")
    profile = {"sub": "member-1", "name": "Member"}
    fetch = AsyncMock(return_value=profile)
    monkeypatch.setattr(routes, "fetch_userinfo", fetch)
    monkeypatch.setattr(
        routes, "resolve_user", AsyncMock(return_value=SimpleNamespace(id="user-1"))
    )
    with TestClient(app, base_url="https://127.0.0.1:3030") as client:
        start = client.get("/api/v1/auth/codebuddy/login", follow_redirects=False)
        assert start.status_code == 303
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        # The Next /oauth callback forwards the cookie to the backend explicitly.
        cookie = start.headers["set-cookie"].split(";", 1)[0]
        invalid = client.post(
            "/api/v1/auth/codebuddy/callback",
            json={"code": "x", "state": "bad"},
            headers={"Cookie": cookie},
            follow_redirects=False,
        )
        assert "invalid_state" in invalid.headers["location"]
        fetch.assert_not_awaited()
        result = client.post(
            "/api/v1/auth/codebuddy/callback",
            json={"code": "x", "state": state},
            headers={"Cookie": cookie},
            follow_redirects=False,
        )
        assert result.headers["location"] == "https://127.0.0.1:3030/"
        session_cookie = next(
            c for c in result.headers.get_list("set-cookie") if c.startswith("auth_token=")
        )
        assert "HttpOnly" in session_cookie and "Secure" in session_cookie
        assert "Max-Age=604800" in session_cookie
        token = session_cookie.split(";", 1)[0].split("=", 1)[1]
        payload = jwt.decode(
            token, oauth.session_settings()[0], algorithms=["HS256"], audience="fastapi-users:auth"
        )
        assert payload["sub"] == "user-1"
        assert "provider-secret" not in result.text
        logout = client.post("/api/v1/auth/logout")
        assert "Max-Age=0" in logout.headers["set-cookie"]
        password_login = client.post(
            "/api/v1/auth/login", data={"username": "old", "password": "old"}
        )
        assert password_login.status_code == 403


def test_refuse_shared_global_backend(monkeypatch):
    monkeypatch.setenv("ENABLE_BACKEND_ACCESS_CONTROL", "false")
    with pytest.raises(oauth.OAuthError, match="access_control_required"):
        oauth.get_config()


@pytest.mark.asyncio
async def test_provider_failure_does_not_return_provider_body(config, monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    400, json={"error_description": "sensitive-provider-details"}
                )
            ),
            **kw,
        ),
    )
    with pytest.raises(oauth.OAuthError, match="^provider_unavailable$"):
        await oauth.fetch_userinfo(config, "invalid-code", "verifier")


def test_oauth_identity_migration_roundtrip():
    migration = importlib.import_module("cognee.alembic.versions.e8b4d2c6a901_add_oauth_identities")
    engine = create_engine("sqlite://")
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        assert "oauth_identities" in inspect(connection).get_table_names()
        unique = inspect(connection).get_unique_constraints("oauth_identities")
        assert any(item["column_names"] == ["provider", "subject"] for item in unique)
        migration.downgrade()
        assert "oauth_identities" not in inspect(connection).get_table_names()
    engine.dispose()


@pytest.mark.asyncio
async def test_approved_brain_shared_read_only_with_current_and_future_users(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (
            Principal.__table__,
            User.__table__,
            OAuthIdentity.__table__,
            Dataset.__table__,
            Permission.__table__,
            ACL.__table__,
        ):
            await conn.run_sync(table.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter = SimpleNamespace(get_async_session=sessions)
    permission_module = importlib.import_module(
        "cognee.modules.users.permissions.methods.give_permission_on_dataset"
    )
    for module in (oauth, sharing, permission_module):
        monkeypatch.setattr(module, "get_relational_engine", lambda: adapter)
    owner_id, shared_id, private_id = uuid4(), uuid4(), uuid4()
    try:
        async with sessions() as session:
            session.add_all(
                [
                    Dataset(id=shared_id, owner_id=owner_id, name="Shared brain"),
                    Dataset(id=private_id, owner_id=owner_id, name="Private brain"),
                ]
            )
            await session.commit()
        existing = await oauth.resolve_user({"sub": "existing-member"})
        monkeypatch.setenv("CODEBUDDY_SHARED_DATASET_IDS", str(shared_id))
        assert await sharing.backfill_shared_read() == 1
        future = await oauth.resolve_user({"sub": "future-member"})
        await sharing.grant_shared_read(future)  # Repeated login must not duplicate ACLs.
        async with sessions() as session:
            rows = (await session.execute(select(ACL, Permission.name).join(Permission))).all()
            assert len(rows) == 2
            assert {acl.principal_id for acl, _ in rows} == {existing.id, future.id}
            assert all(
                acl.dataset_id == shared_id and permission == "read" for acl, permission in rows
            )
            assert (await session.get(Dataset, shared_id)).owner_id == owner_id
    finally:
        await engine.dispose()
