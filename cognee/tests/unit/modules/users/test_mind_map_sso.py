import base64
import hashlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cognee.api.v1.users.routers import get_auth_router
from cognee.api.v1.users.routers import get_mind_map_sso_router as routes
from cognee.modules.users.authentication import mind_map_sso as sso
from cognee.modules.users.authentication.session_settings import session_settings
from cognee.modules.users.models import OAuthIdentity, User
from cognee.modules.users.models.Principal import Principal


@pytest.fixture(autouse=True, scope="session")
def _relational_db_for_unit_tests():
    # This suite creates its own in-memory database; never migrate an operator's DB.
    yield


@pytest.fixture(autouse=True)
def config(monkeypatch):
    values = {
        "CODEBUDDY_ENABLED": "false",
        "MIND_MAP_SSO_ENABLED": "true",
        "MIND_MAP_SSO_ORIGIN": "https://xx.stillgroup.net:8989",
        "MIND_MAP_SSO_REDIRECT_URI": "https://xx.stillgroup.net:3030/sso/mind-map/callback",
        "MIND_MAP_COGNEE_SSO_SECRET": "test-exchange-secret-" * 3,
        "MIND_MAP_SSO_SESSION_SECRET": "test-session-secret-" * 3,
        "MIND_MAP_SSO_SESSION_LIFETIME_SECONDS": "604800",
        "ENABLE_BACKEND_ACCESS_CONTROL": "true",
        "MIND_MAP_SSO_ACCOUNT_EMAIL": "izw99s@hotmail.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return sso.get_config()


def test_state_is_browser_bound_and_uses_pkce(config):
    location, cookie = sso.begin_authorization(config)
    parts = urlsplit(location)
    assert parts.scheme == "https" and parts.netloc == "xx.stillgroup.net:8989"
    assert parts.path == "/api/auth/cognee/authorize"
    query = parse_qs(parts.query)
    verifier = sso.verify_state(config, cookie, query["state"][0])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == [challenge.decode()]
    assert query["code_challenge_method"] == ["S256"]
    assert config.client_secret not in location and verifier not in location
    with pytest.raises(sso.SsoError, match="invalid_state"):
        sso.verify_state(config, cookie, "another-browser")
    with pytest.raises(sso.SsoError, match="invalid_state"):
        sso.verify_state(config, "tampered", query["state"][0])
    secret, _ = session_settings()
    payload = jwt.decode(cookie, secret, algorithms=["HS256"], audience="cognee-mind-map-sso")
    payload["exp"] = int(time.time()) - 1
    with pytest.raises(sso.SsoError, match="invalid_state"):
        sso.verify_state(config, jwt.encode(payload, secret, algorithm="HS256"), query["state"][0])
    payload["exp"] = int(time.time()) + 100
    payload["aud"] = "codebuddy-oauth"
    with pytest.raises(sso.SsoError, match="invalid_state"):
        sso.verify_state(config, jwt.encode(payload, secret, algorithm="HS256"), query["state"][0])


@pytest.mark.parametrize(
    "key,value",
    [
        ("MIND_MAP_SSO_ORIGIN", "http://xx.stillgroup.net:8989"),
        ("MIND_MAP_SSO_ORIGIN", "https://xx.stillgroup.net:8989/extra"),
        ("MIND_MAP_SSO_REDIRECT_URI", "https://xx.stillgroup.net:3030/evil"),
        ("MIND_MAP_COGNEE_SSO_SECRET", "short"),
        ("MIND_MAP_SSO_SESSION_SECRET", "short"),
        ("MIND_MAP_SSO_SESSION_SECRET", "test-exchange-secret-" * 3),
        ("ENABLE_BACKEND_ACCESS_CONTROL", "false"),
        ("MIND_MAP_SSO_ACCOUNT_EMAIL", ""),
    ],
)
def test_bad_configuration_fails_closed(config, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises((sso.SsoError, ValueError)):
        sso.get_config()


def test_preserves_existing_workbuddy_session_key_and_lifetime(monkeypatch):
    monkeypatch.setenv("CODEBUDDY_ENABLED", "true")
    monkeypatch.setenv("CODEBUDDY_SESSION_SECRET", "existing-session-secret-" * 3)
    monkeypatch.setenv("CODEBUDDY_SESSION_LIFETIME_SECONDS", "7200")
    assert session_settings() == ("existing-session-secret-" * 3, 7200)
    sso.get_config()


@pytest.mark.asyncio
async def test_exchange_is_backend_only_and_validates_subject(config, monkeypatch):
    def issuer(request):
        assert str(request.url) == config.issuer_origin + "/api/auth/cognee/exchange"
        assert request.headers["authorization"] == "Bearer " + config.client_secret
        assert json.loads(request.content) == {
            "code": "one-time-code",
            "code_verifier": "test-verifier",
            "redirect_uri": config.redirect_uri,
        }
        return httpx.Response(
            200,
            json={
                "sub": "wecom:ww-test:member-1",
                "corp_id": "ww-test",
                "wecom_userid": "member-1",
                "name": "测试成员",
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sso.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(issuer), **kw),
    )
    profile = await sso.exchange_code(config, "one-time-code", "test-verifier")
    assert profile["name"] == "测试成员"
    assert "access_token" not in profile
    for bad in [
        {},
        {"corp_id": True, "wecom_userid": "one"},
        {"corp_id": "ww-test", "wecom_userid": "one", "sub": "wecom:other:one"},
    ]:
        with pytest.raises(sso.SsoError):
            sso.profile_subject(bad)


@pytest.mark.asyncio
async def test_members_reuse_existing_account_without_changing_permissions(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (Principal.__table__, User.__table__, OAuthIdentity.__table__):
            await conn.run_sync(table.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        sso, "get_relational_engine", lambda: SimpleNamespace(get_async_session=sessions)
    )

    def profile(corp):
        return {
            "sub": f"wecom:{corp}:member",
            "corp_id": corp,
            "wecom_userid": "member",
            "name": "Member",
        }

    try:
        shared_id, legacy_id = uuid4(), uuid4()
        async with sessions() as session:
            session.add_all(
                [
                    User(
                        id=shared_id,
                        email="izw99s@hotmail.com",
                        hashed_password="existing-hash",
                        is_active=True,
                        is_verified=False,
                        is_superuser=True,
                    ),
                    User(
                        id=legacy_id,
                        email="legacy@example.com",
                        hashed_password="legacy-hash",
                        is_active=True,
                        is_verified=True,
                        is_superuser=False,
                    ),
                ]
            )
            await session.flush()
            session.add(
                OAuthIdentity(
                    user_id=legacy_id,
                    provider=sso.PROVIDER,
                    subject="wecom:ww-one:member",
                    email="",
                )
            )
            await session.commit()
        first = await sso.resolve_user(profile("ww-one"))
        again = await sso.resolve_user(profile("ww-one"))
        other = await sso.resolve_user(profile("ww-two"))
        assert first.id == again.id == other.id == shared_id
        assert first.is_active and not first.is_verified and first.is_superuser
        assert first.hashed_password == "existing-hash"
        assert first.tenant_id is None
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 2
            identities = (await session.scalars(select(OAuthIdentity))).all()
            assert len(identities) == 2 and all(i.user_id == shared_id for i in identities)
            assert (await session.get(User, legacy_id)).hashed_password == "legacy-hash"
            user = await session.get(User, first.id)
            user.is_active = False
            await session.commit()
        with pytest.raises(sso.SsoError, match="account_disabled"):
            await sso.resolve_user(profile("ww-one"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_missing_shared_account_does_not_create_or_fallback(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (Principal.__table__, User.__table__, OAuthIdentity.__table__):
            await conn.run_sync(table.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        sso, "get_relational_engine", lambda: SimpleNamespace(get_async_session=sessions)
    )
    try:
        with pytest.raises(sso.SsoError, match="sso_account_missing"):
            await sso.resolve_user(
                {"sub": "wecom:corp:member", "corp_id": "corp", "wecom_userid": "member"}
            )
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 0
            assert await session.scalar(select(func.count()).select_from(OAuthIdentity)) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_qr_uses_original_callback_and_preserves_browser_binding(config, monkeypatch):
    def issuer(request):
        assert request.url.path == "/api/auth/qr"
        assert request.headers["cookie"] == "mind_map_oauth_browser=original-browser"
        return_to = request.url.params["return_to"]
        query = parse_qs(urlsplit(return_to).query)
        assert query["redirect_uri"] == [config.redirect_uri]
        assert query["code_challenge_method"] == ["S256"]
        qr_query = urlencode(
            {
                "redirect_uri": config.issuer_origin + "/api/auth/wecom/callback",
                "state": "issuer-state",
                "appid": "corp",
                "agentid": "1000002",
            }
        )
        return httpx.Response(
            200,
            json={
                "loginUrl": "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?" + qr_query,
                "state": "issuer-state",
            },
            headers={
                "set-cookie": "mind_map_oauth_browser=original-browser; Path=/; HttpOnly; Secure"
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sso.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(issuer), **kw),
    )
    data, state, browser = await sso.prepare_qr(config, "original-browser")
    assert data["expiresIn"] == sso.STATE_TTL and browser == "original-browser"
    query = parse_qs(urlsplit(data["loginUrl"]).query)
    assert query["style"] == ["black"]
    assert query["href"] == [config.origin + "/wecom-qr.css?v=1"]
    assert query["state"] == ["issuer-state"]
    assert query["redirect_uri"] == [config.issuer_origin + "/api/auth/wecom/callback"]
    secret, _ = session_settings()
    claims = jwt.decode(state, secret, algorithms=["HS256"], audience="cognee-mind-map-sso")
    assert claims["redirect_uri"] == config.redirect_uri
    assert "verifier" not in data and config.client_secret not in json.dumps(data)


def test_callback_issues_secure_cookie_only_after_valid_state(config, monkeypatch):
    app = FastAPI()
    app.include_router(get_auth_router(), prefix="/api/v1/auth")
    exchange = AsyncMock(return_value={"sub": "test"})
    monkeypatch.setattr(routes, "exchange_code", exchange)
    monkeypatch.setattr(
        routes, "resolve_user", AsyncMock(return_value=SimpleNamespace(id="user-1"))
    )
    with TestClient(app, base_url=config.origin) as client:
        start = client.get("/api/v1/auth/mind-map/login", follow_redirects=False)
        assert start.status_code == 303
        cookie = start.headers["set-cookie"].split(";", 1)[0]
        assert "Secure" in start.headers["set-cookie"] and "HttpOnly" in start.headers["set-cookie"]
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        bad = client.post(
            "/api/v1/auth/mind-map/callback",
            json={"code": "code", "state": "bad"},
            headers={"Cookie": cookie},
            follow_redirects=False,
        )
        assert "invalid_state" in bad.headers["location"]
        exchange.assert_not_awaited()
        result = client.post(
            "/api/v1/auth/mind-map/callback",
            json={"code": "code", "state": state},
            headers={"Cookie": cookie},
            follow_redirects=False,
        )
        assert result.headers["location"] == config.origin + "/"
        session_cookie = next(
            c for c in result.headers.get_list("set-cookie") if c.startswith("auth_token=")
        )
        assert (
            "Secure" in session_cookie
            and "HttpOnly" in session_cookie
            and "SameSite=lax" in session_cookie
        )
        assert "Max-Age=604800" in session_cookie
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["referrer-policy"] == "no-referrer"
        token = session_cookie.split(";", 1)[0].split("=", 1)[1]
        secret, _ = session_settings()
        claims = jwt.decode(token, secret, algorithms=["HS256"], audience="fastapi-users:auth")
        assert claims["sub"] == "user-1"
        assert "Max-Age=0" in client.post("/api/v1/auth/logout").headers["set-cookie"]


def test_disabled_sso_returns_503_without_provider_requests(monkeypatch):
    monkeypatch.setenv("MIND_MAP_SSO_ENABLED", "false")
    app = FastAPI()
    app.include_router(routes.get_mind_map_sso_router(), prefix="/api/v1/auth")
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/mind-map/config").json() == {"enabled": False}
        assert client.get("/api/v1/auth/mind-map/login").status_code == 503


@pytest.mark.parametrize("failure", ["provider", "database", "session"])
def test_callback_failures_return_retry_page_and_clear_state(config, monkeypatch, failure):
    app = FastAPI()
    app.include_router(routes.get_mind_map_sso_router(), prefix="/api/v1/auth")
    exchange = AsyncMock(return_value={"sub": "test"})
    resolve = AsyncMock(return_value=SimpleNamespace(id="user-1"))
    monkeypatch.setattr(routes, "exchange_code", exchange)
    monkeypatch.setattr(routes, "resolve_user", resolve)
    if failure == "database":
        resolve.side_effect = RuntimeError("sensitive database details")
    if failure == "session":
        monkeypatch.setattr(
            routes,
            "get_client_auth_backend",
            lambda: SimpleNamespace(
                get_strategy=lambda: SimpleNamespace(
                    write_token=AsyncMock(side_effect=RuntimeError("sensitive session details"))
                )
            ),
        )
    with TestClient(app, base_url=config.origin) as client:
        start = client.get("/api/v1/auth/mind-map/login", follow_redirects=False)
        cookie = start.headers["set-cookie"].split(";", 1)[0]
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        payload = {"code": "code", "state": state}
        if failure == "provider":
            payload["error"] = "wecom_login_failed"
            bad_state = client.post(
                "/api/v1/auth/mind-map/callback",
                json={**payload, "state": "bad"},
                headers={"Cookie": cookie},
                follow_redirects=False,
            )
            assert "invalid_state" in bad_state.headers["location"]
        result = client.post(
            "/api/v1/auth/mind-map/callback",
            json=payload,
            headers={"Cookie": cookie},
            follow_redirects=False,
        )
        error = "sso_wecom_failed" if failure == "provider" else "sso_unavailable"
        assert result.status_code == 303
        assert result.headers["location"] == config.origin + "/local-login?error=" + error
        cookies = result.headers.get_list("set-cookie")
        assert any(c.startswith(sso.STATE_COOKIE + "=") and "Max-Age=0" in c for c in cookies)
        assert not any(c.startswith("auth_token=") for c in cookies)
        if failure == "provider":
            exchange.assert_not_awaited()
            resolve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,error",
    [
        (400, {}, "sso_invalid_grant"),
        (401, {}, "sso_unavailable"),
        (503, {}, "sso_unavailable"),
        (200, [], "sso_invalid_profile"),
        (200, {"sub": "wrong", "corp_id": "corp", "wecom_userid": "member"}, "sso_invalid_profile"),
    ],
)
async def test_exchange_failures_are_fixed_errors(config, monkeypatch, status, body, error):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sso.httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)), **kw
        ),
    )
    with pytest.raises(sso.SsoError, match=error):
        await sso.exchange_code(config, "code", "verifier")
