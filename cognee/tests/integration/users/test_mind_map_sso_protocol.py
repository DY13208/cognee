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
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cognee.api.v1.datasets.routers.get_datasets_router import get_datasets_router
from cognee.api.v1.users.routers import get_auth_router
from cognee.api.v1.users.routers import get_mind_map_sso_router as routes
from cognee.api.v1.users.routers.get_users_router import get_users_router
from cognee.infrastructure.databases.relational import Base
from cognee.modules.data.models import Dataset
from cognee.modules.users.authentication import mind_map_sso as sso
from cognee.modules.users.get_user_db import get_async_session
from cognee.modules.users.models import OAuthIdentity, User
from cognee.modules.users.models.ACL import ACL
from cognee.modules.users.models.Permission import Permission
from cognee.modules.users.models.Role import Role
from cognee.modules.users.models.Tenant import Tenant

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
        "MIND_MAP_SSO_ACCOUNT_EMAIL": "izw99s@hotmail.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "users.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    adapter = SimpleNamespace(get_async_session=sessions)
    for module in [
        sso,
        routes,
        importlib.import_module("cognee.modules.users.methods.get_user"),
        importlib.import_module("cognee.modules.users.authentication.methods.authenticate_user"),
        importlib.import_module("cognee.modules.users.permissions.methods.get_principal_datasets"),
    ]:
        monkeypatch.setattr(module, "get_relational_engine", lambda: adapter)
    monkeypatch.setattr(
        importlib.import_module("cognee.api.v1.datasets.routers.get_datasets_router"),
        "send_telemetry",
        lambda *args, **kw: None,
    )
    target_id, tenant_id, role_id = uuid4(), uuid4(), uuid4()
    dataset_ids = [uuid4() for _ in range(3)]

    async def session_dependency():
        async with sessions() as session:
            yield session

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            tenant = Tenant(id=tenant_id, name="Existing tenant", owner_id=target_id)
            role = Role(id=role_id, name="Existing role", tenant_id=tenant_id)
            user = User(
                id=target_id,
                email="izw99s@hotmail.com",
                hashed_password=PasswordHelper().hash("fixture-password"),
                is_active=True,
                is_verified=True,
                is_superuser=False,
                tenant_id=tenant_id,
                tenants=[tenant],
                roles=[role],
            )
            permission = Permission(id=uuid4(), name="read")
            session.add_all([user, permission])
            await session.flush()
            for index, principal_id in enumerate([target_id, tenant_id, role_id]):
                session.add(
                    Dataset(
                        id=dataset_ids[index],
                        name=f"Existing knowledge {index}",
                        owner_id=target_id,
                        tenant_id=tenant_id,
                    )
                )
                await session.flush()
                session.add(
                    ACL(
                        principal_id=principal_id,
                        permission_id=permission.id,
                        dataset_id=dataset_ids[index],
                    )
                )
            session.add(
                Dataset(
                    id=uuid4(), name="Unshared knowledge", owner_id=uuid4(), tenant_id=tenant_id
                )
            )
            await session.commit()

    app = FastAPI()
    app.include_router(get_auth_router(), prefix="/api/v1/auth")
    app.include_router(get_users_router(), prefix="/api/v1/users")
    app.include_router(get_datasets_router(), prefix="/api/v1/datasets")
    app.dependency_overrides[get_async_session] = session_dependency
    with TestClient(app, base_url="https://localhost:3030") as client:
        client.portal.call(setup)
        yield SimpleNamespace(
            client=client,
            sessions=sessions,
            config=sso.get_config(),
            target_id=target_id,
            dataset_ids=dataset_ids,
            tenant_id=tenant_id,
            role_id=role_id,
        )
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


def test_real_exchange_reuses_password_account_permissions_after_restart(issuer, browser):
    assert browser.client.get("/api/v1/auth/me").status_code == 401
    password = browser.client.post(
        "/api/v1/auth/login",
        data={"username": "izw99s@hotmail.com", "password": "fixture-password"},
    )
    assert password.status_code == 200
    baseline = browser.client.get("/api/v1/datasets")
    assert baseline.status_code == 200
    assert {row["id"] for row in baseline.json()} == {str(i) for i in browser.dataset_ids}
    browser.client.post("/api/v1/auth/logout")
    location, cookie = authorize_member(issuer, browser, "first")
    issuer.restart()  # Both mind-map session and pending code must survive process restart.
    assert issuer.http.get(issuer.origin + "/api/auth/me").status_code == 200
    result = callback(browser, location, cookie)
    assert result.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/me").status_code == 200
    profile = browser.client.get("/api/v1/auth/mind-map/me").json()
    assert profile["name"] == "izw99s@hotmail.com"
    first_id = profile["id"]
    assert first_id == str(browser.target_id)
    native_profile = browser.client.get("/api/v1/users/me")
    assert native_profile.status_code == 200 and native_profile.json()["id"] == first_id
    assert browser.client.get("/api/v1/datasets").json() == baseline.json()
    replay = callback(browser, location, cookie)
    assert "sso_invalid_grant" in replay.headers["location"]
    assert not any(c.startswith("auth_token=") for c in replay.headers.get_list("set-cookie"))
    again = callback(browser, *authorize_member(issuer, browser, "first"))
    assert again.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/mind-map/me").json()["id"] == first_id
    callback(browser, *authorize_member(issuer, browser, "second"))
    second_id = browser.client.get("/api/v1/auth/mind-map/me").json()["id"]
    assert second_id == first_id
    assert browser.client.get("/api/v1/datasets").json() == baseline.json()

    async def check_users():
        async with browser.sessions() as session:
            users = (await session.scalars(select(User))).all()
            assert len(users) == 1
            assert users[0].tenant_id == browser.tenant_id and not users[0].is_superuser
            assert len((await session.scalars(select(OAuthIdentity))).all()) == 2

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
    assert browser.client.get("/api/v1/auth/mind-map/me").json()["id"] == str(browser.target_id)


def test_embedded_qr_refresh_uses_original_callback_and_shared_permissions(issuer, browser):
    issuer.http.cookies.clear()
    first = browser.client.get("/api/v1/auth/mind-map/qr")
    assert first.status_code == 200
    first_cookie = next(
        c.split(";", 1)[0]
        for c in first.headers.get_list("set-cookie")
        if c.startswith(sso.STATE_COOKIE + "=")
    )
    qr_response = browser.client.get("/api/v1/auth/mind-map/qr")
    assert qr_response.status_code == 200
    cookies = qr_response.headers.get_list("set-cookie")
    state_cookie = next(c.split(";", 1)[0] for c in cookies if c.startswith(sso.STATE_COOKIE + "="))
    assert state_cookie != first_cookie
    assert all("Secure" in c and "HttpOnly" in c for c in cookies)
    qr = parse_qs(urlsplit(qr_response.json()["loginUrl"]).query)
    assert qr["login_type"] == ["jssdk"]
    assert qr["appid"] == ["ww-protocol-test"] and qr["agentid"] == ["1000002"]
    assert qr["redirect_uri"] == [issuer.origin + "/api/auth/wecom/callback"]
    issuer.http.cookies.set(
        sso.MIND_MAP_BROWSER_COOKIE, browser.client.cookies.get(sso.MIND_MAP_BROWSER_COOKIE)
    )
    success = issuer.http.get(
        qr["redirect_uri"][0], params={"code": "fixture-success", "state": qr["state"][0]}
    )
    assert "auth_error" not in success.headers["location"]
    returned = issuer.http.get(success.headers["location"])
    result = callback(browser, returned.headers["location"], state_cookie)
    assert result.headers["location"] == browser.config.origin + "/"
    assert browser.client.get("/api/v1/auth/mind-map/me").json()["id"] == str(browser.target_id)
    datasets = browser.client.get("/api/v1/datasets")
    assert datasets.status_code == 200 and len(datasets.json()) == 3
