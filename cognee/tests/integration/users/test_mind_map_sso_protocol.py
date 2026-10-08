"""Opt-in: real HTTPS Node issuer, PostgreSQL auth, SQLite users and native JWT auth.

Set MIND_MAP_SSO_INTEGRATION=1 and PG* for a test PostgreSQL server. The sibling
mind-map checkout must include its SSO fixture and installed Node dependencies.
Each run creates and drops only its own randomly named PostgreSQL schema.
WeCom's external API is simulated; no real application credentials are used.
"""

import importlib
import ipaddress
import os
import secrets
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cognee.api.v1.users.routers import get_auth_router
from cognee.api.v1.users.routers import get_mind_map_sso_router as routes
from cognee.infrastructure.databases.relational import Base
from cognee.modules.users.authentication import mind_map_sso as sso
from cognee.modules.users.get_user_db import get_async_session
from cognee.modules.users.models import User

pytestmark = pytest.mark.skipif(
    os.getenv("MIND_MAP_SSO_INTEGRATION") != "1", reason="requires opt-in Node/PostgreSQL fixture"
)


def make_certificate(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "localhost.pem", directory / "localhost.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    return cert_path, key_path


@pytest.fixture(scope="module")
def issuer(tmp_path_factory):
    directory = tmp_path_factory.mktemp("mind-map-protocol")
    cert, key = make_certificate(directory)
    root = Path(
        os.getenv(
            "MIND_MAP_TEST_ROOT", str(Path(__file__).resolve().parents[4].parent / "mind-map")
        )
    )
    fixture = root / "simple-mind-map/test/fixtures/cogneeSsoIssuer.js"
    assert fixture.exists(), "mind-map SSO test fixture is required"
    node = shutil.which("node")
    assert node, "Node.js is required"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"https://localhost:{port}"
    shared = "test-protocol-exchange-" + secrets.token_hex(24)
    # Only PG connection settings are inherited; never operator auth credentials.
    env = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "HOME", "TMPDIR", "LANG") or k.startswith("PG")
    }
    env.update(
        {
            "MIND_MAP_SKIP_ROOT_ENV": "1",
            "COLLAB_E2E": "1",
            "SSO_TEST_SCHEMA": "test_cognee_protocol_" + secrets.token_hex(8),
            "SSO_TEST_CERT": str(cert),
            "SSO_TEST_KEY": str(key),
            "SSO_TEST_PORT": str(port),
            "NODE_EXTRA_CA_CERTS": str(cert),
            "WECOM_AUTH_ENABLED": "true",
            "WECOM_CORP_ID": "ww-protocol-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_SECRET": "fixture-wecom-secret",
            "WECOM_REDIRECT_URI": origin + "/api/auth/wecom/callback",
            "WECOM_API_BASE": origin,
            "WECOM_SSO_BASE": origin,
            "AUTH_APP_ORIGIN": origin,
            "AUTH_COOKIE_SECURE": "true",
            "AUTH_SESSION_SECRET": "fixture-mind-map-session-" + secrets.token_hex(24),
            "MCP_TOKEN": "fixture-mcp-token-" + secrets.token_hex(24),
            "MIND_MAP_COGNEE_SSO_SECRET": shared,
            "COGNEE_SSO_REDIRECT_URI": "https://localhost:3030/sso/mind-map/callback",
        }
    )
    subprocess.run([node, str(fixture), "init"], env=env, check=True, timeout=15)
    process = None
    http = httpx.Client(verify=str(cert), timeout=5, trust_env=False)

    def stop():
        nonlocal process
        if process:
            process.terminate()
            process.wait(timeout=10)
            process = None

    def start():
        nonlocal process
        process = subprocess.Popen(
            [node, str(fixture)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, "isolated issuer failed to start"
            try:
                if http.get(origin + "/_fixture/ready").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("issuer readiness timed out")

    def restart():
        stop()
        start()

    try:
        start()
        yield SimpleNamespace(http=http, origin=origin, shared=shared, cert=cert, restart=restart)
    finally:
        stop()
        http.close()
        subprocess.run([node, str(fixture), "drop"], env=env, check=True, timeout=15)


@pytest.fixture
def browser(issuer, monkeypatch, tmp_path):
    values = {
        "CODEBUDDY_ENABLED": "false",
        "MIND_MAP_SSO_ENABLED": "true",
        "MIND_MAP_SSO_ORIGIN": issuer.origin,
        "MIND_MAP_SSO_REDIRECT_URI": "https://localhost:3030/sso/mind-map/callback",
        "MIND_MAP_COGNEE_SSO_SECRET": issuer.shared,
        "MIND_MAP_SSO_SESSION_SECRET": "fixture-cognee-session-" + secrets.token_hex(24),
        "ENABLE_BACKEND_ACCESS_CONTROL": "true",
        "SSL_CERT_FILE": str(issuer.cert),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "users.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter = SimpleNamespace(get_async_session=sessions)
    for module in [sso, routes, importlib.import_module("cognee.modules.users.methods.get_user")]:
        monkeypatch.setattr(module, "get_relational_engine", lambda: adapter)

    async def session_dependency():
        async with sessions() as session:
            yield session

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(get_auth_router(), prefix="/api/v1/auth")
    app.dependency_overrides[get_async_session] = session_dependency
    with TestClient(app, base_url="https://localhost:3030") as client:
        client.portal.call(setup)
        yield SimpleNamespace(client=client, sessions=sessions, config=sso.get_config())
        client.portal.call(engine.dispose)


def begin(browser):
    response = browser.client.get("/api/v1/auth/mind-map/login", follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"], response.headers["set-cookie"].split(";", 1)[0]


def callback(browser, location, cookie):
    payload = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
    return browser.client.post(
        "/api/v1/auth/mind-map/callback",
        json=payload,
        headers={"Cookie": cookie},
        follow_redirects=False,
    )


def authorize_member(issuer, browser, member):
    identity = issuer.http.post(
        issuer.origin + "/api/auth/e2e-identity",
        json={"userId": member, "name": "测试成员 " + member},
    )
    assert identity.status_code == 200
    url, state_cookie = begin(browser)
    result = issuer.http.get(url)
    assert result.status_code == 303
    return result.headers["location"], state_cookie


def test_real_exchange_native_auth_restart_replay_and_member_isolation(issuer, browser):
    assert browser.client.get("/api/v1/auth/me").status_code == 401
    location, cookie = authorize_member(issuer, browser, "first")
    issuer.restart()  # Both mind-map session and pending code must survive process restart.
    assert issuer.http.get(issuer.origin + "/api/auth/me").status_code == 200
    result = callback(browser, location, cookie)
    assert result.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/me").status_code == 200
    profile = browser.client.get("/api/v1/auth/mind-map/me").json()
    assert profile["name"] == "测试成员 first"
    first_id = profile["id"]
    replay = callback(browser, location, cookie)
    assert "sso_invalid_grant" in replay.headers["location"]
    assert not any(c.startswith("auth_token=") for c in replay.headers.get_list("set-cookie"))
    again = callback(browser, *authorize_member(issuer, browser, "first"))
    assert again.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/mind-map/me").json()["id"] == first_id
    callback(browser, *authorize_member(issuer, browser, "second"))
    second_id = browser.client.get("/api/v1/auth/mind-map/me").json()["id"]
    assert second_id != first_id

    async def check_users():
        async with browser.sessions() as session:
            users = (await session.scalars(select(User))).all()
            assert len(users) == 2
            assert all(u.is_active and not u.is_superuser and u.tenant_id is None for u in users)

    browser.client.portal.call(check_users)
    token = browser.client.cookies.get("auth_token")
    claims = jwt.decode(
        token,
        os.environ["MIND_MAP_SSO_SESSION_SECRET"],
        algorithms=["HS256"],
        audience="fastapi-users:auth",
    )
    claims["exp"] = int(time.time()) - 1
    expired = jwt.encode(claims, os.environ["MIND_MAP_SSO_SESSION_SECRET"], algorithm="HS256")
    assert (
        browser.client.get(
            "/api/v1/auth/me", headers={"Cookie": "auth_token=" + expired}
        ).status_code
        == 401
    )
    assert browser.client.post("/api/v1/auth/logout").status_code == 200
    assert browser.client.get("/api/v1/auth/me").status_code == 401


def test_expired_code_and_wrong_client_fail_without_session(issuer, browser):
    location, cookie = authorize_member(issuer, browser, "expiry")
    code = parse_qs(urlsplit(location).query)["code"][0]
    unauthorized = issuer.http.post(
        issuer.origin + "/api/auth/cognee/exchange", json={"code": code}
    )
    assert unauthorized.status_code == 401
    assert issuer.http.post(issuer.origin + "/_fixture/expire").status_code == 204
    result = callback(browser, location, cookie)
    assert "sso_invalid_grant" in result.headers["location"]
    assert browser.client.get("/api/v1/auth/me").status_code == 401


def test_existing_wecom_callback_failure_returns_once_to_cognee(issuer, browser):
    issuer.http.cookies.clear()
    authorize_url, cookie = begin(browser)
    require_login = issuer.http.get(authorize_url)
    assert require_login.headers["location"].startswith("/api/auth/login?return_to=")
    login = issuer.http.get(issuer.origin + require_login.headers["location"])
    provider_state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    failure = issuer.http.get(
        issuer.origin + "/api/auth/wecom/callback",
        params={"code": "fixture-fail", "state": provider_state},
    )
    assert "auth_error=" in failure.headers["location"]
    returned = issuer.http.get(failure.headers["location"])
    assert urlsplit(returned.headers["location"]).path == "/sso/mind-map/callback"
    assert "error=wecom_login_failed" in returned.headers["location"]
    result = callback(browser, returned.headers["location"], cookie)
    assert (
        result.headers["location"] == browser.config.origin + "/local-login?error=sso_wecom_failed"
    )
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert browser.client.get("/api/v1/auth/me").status_code == 401


def test_fresh_wecom_callback_and_client_login_use_existing_application(issuer, browser):
    issuer.http.cookies.clear()
    authorize_url, cookie = begin(browser)
    client_login = issuer.http.get(authorize_url, headers={"User-Agent": "MicroMessenger"})
    assert client_login.headers["location"].startswith("/api/auth/wecom/client-login?return_to=")
    require_login = issuer.http.get(authorize_url, headers={"User-Agent": "Desktop"})
    login = issuer.http.get(issuer.origin + require_login.headers["location"])
    qr = parse_qs(urlsplit(login.headers["location"]).query)
    assert qr["appid"] == ["ww-protocol-test"]
    assert qr["agentid"] == ["1000002"]
    assert qr["redirect_uri"] == [issuer.origin + "/api/auth/wecom/callback"]
    success = issuer.http.get(
        issuer.origin + "/api/auth/wecom/callback",
        params={"code": "fixture-success", "state": qr["state"][0]},
    )
    assert "auth_error" not in success.headers["location"]
    returned = issuer.http.get(success.headers["location"])
    result = callback(browser, returned.headers["location"], cookie)
    assert result.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/mind-map/me").json()["name"] == "首次扫码成员"
