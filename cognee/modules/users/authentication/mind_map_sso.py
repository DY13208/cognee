"""Reuse mind-map's existing WeCom login through a one-time, PKCE-bound code."""

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cognee.infrastructure.databases.relational import get_relational_engine
from cognee.modules.users.authentication.session_settings import (
    mind_map_sso_enabled,
    session_settings,
)
from cognee.modules.users.models import OAuthIdentity, User

STATE_COOKIE = "cognee_mind_map_state"
STATE_PATH = "/sso/mind-map"
STATE_TTL = 600
PROVIDER = "mind-map-wecom"
MIND_MAP_BROWSER_COOKIE = "mind_map_oauth_browser"


class SsoError(Exception):
    """Fixed error codes only; never provider responses or credentials."""


@dataclass(frozen=True)
class SsoConfig:
    issuer_origin: str
    redirect_uri: str
    client_secret: str
    account_email: str = "izw99s@hotmail.com"

    @property
    def origin(self) -> str:
        parts = urlsplit(self.redirect_uri)
        return f"{parts.scheme}://{parts.netloc}"


def get_config() -> SsoConfig:
    if not mind_map_sso_enabled():
        raise SsoError("sso_not_configured")
    config = SsoConfig(
        issuer_origin=os.getenv("MIND_MAP_SSO_ORIGIN", "").rstrip("/"),
        redirect_uri=os.getenv("MIND_MAP_SSO_REDIRECT_URI", ""),
        client_secret=os.getenv("MIND_MAP_COGNEE_SSO_SECRET", ""),
        account_email=os.getenv("MIND_MAP_SSO_ACCOUNT_EMAIL", "izw99s@hotmail.com").strip().lower(),
    )
    for url in (config.issuer_origin, config.redirect_uri):
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise SsoError("sso_not_configured")
    if urlsplit(config.issuer_origin).path or (
        urlsplit(config.redirect_uri).path != "/sso/mind-map/callback"
    ):
        raise SsoError("sso_not_configured")
    if len(config.client_secret) < 32:
        raise SsoError("sso_not_configured")
    if (
        not config.account_email
        or len(config.account_email) > 320
        or "@" not in config.account_email
    ):
        raise SsoError("sso_not_configured")
    if os.getenv("ENABLE_BACKEND_ACCESS_CONTROL", "true").lower() != "true":
        raise SsoError("access_control_required")
    session_secret, _ = session_settings()
    if secrets.compare_digest(session_secret, config.client_secret):
        raise SsoError("sso_not_configured")
    return config


def begin_authorization(config: SsoConfig) -> tuple[str, str]:
    secret, _ = session_settings()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    now = int(time.time())
    cookie = jwt.encode(
        {
            "state": state,
            "verifier": verifier,
            "iat": now,
            "exp": now + STATE_TTL,
            "aud": "cognee-mind-map-sso",
            "redirect_uri": config.redirect_uri,
            "issuer_origin": config.issuer_origin,
        },
        secret,
        algorithm="HS256",
    )
    query = urlencode(
        {
            "state": state,
            "redirect_uri": config.redirect_uri,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    return f"{config.issuer_origin}/api/auth/cognee/authorize?{query}", cookie


def verify_state(config: SsoConfig, cookie: str, state: str) -> str:
    secret, _ = session_settings()
    try:
        payload = jwt.decode(
            cookie,
            secret,
            algorithms=["HS256"],
            audience="cognee-mind-map-sso",
            options={
                "require": [
                    "exp",
                    "iat",
                    "aud",
                    "state",
                    "verifier",
                    "redirect_uri",
                    "issuer_origin",
                ]
            },
        )
        if (
            not state
            or not secrets.compare_digest(payload["state"], state)
            or payload["redirect_uri"] != config.redirect_uri
            or payload["issuer_origin"] != config.issuer_origin
        ):
            raise SsoError("invalid_state")
        return payload["verifier"]
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise SsoError("invalid_state") from error


def profile_subject(profile: dict) -> str:
    corp = profile.get("corp_id")
    member = profile.get("wecom_userid")
    if not isinstance(corp, str) or not isinstance(member, str) or not corp or not member:
        raise SsoError("sso_invalid_profile")
    subject = f"wecom:{corp}:{member}"
    if profile.get("sub") != subject or len(subject) > 255:
        raise SsoError("sso_invalid_profile")
    return subject


async def exchange_code(config: SsoConfig, code: str, verifier: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(
                f"{config.issuer_origin}/api/auth/cognee/exchange",
                json={
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": config.redirect_uri,
                },
                headers={"Authorization": f"Bearer {config.client_secret}"},
            )
            if response.status_code == 400:
                raise SsoError("sso_invalid_grant")
            response.raise_for_status()
            profile = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise SsoError("sso_unavailable") from error
    if not isinstance(profile, dict):
        raise SsoError("sso_invalid_profile")
    profile_subject(profile)
    return profile


async def resolve_user(profile: dict) -> User:
    subject = profile_subject(profile)
    email = get_config().account_email
    async with get_relational_engine().get_async_session() as session:
        user_query = select(User).where(func.lower(User.email) == email)
        user = (await session.execute(user_query)).scalar_one_or_none()
        if user is None:
            raise SsoError("sso_account_missing")
        if not user.is_active:
            raise SsoError("account_disabled")
        query = select(OAuthIdentity).where(
            OAuthIdentity.provider == PROVIDER, OAuthIdentity.subject == subject
        )
        identity = (await session.execute(query)).scalar_one_or_none()
        if identity is None:
            identity = OAuthIdentity(user_id=user.id, provider=PROVIDER, subject=subject, email="")
            session.add(identity)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                identity = (await session.execute(query)).scalar_one_or_none()
                user = (await session.execute(user_query)).scalar_one_or_none()
                if identity is None:
                    raise SsoError("account_failed") from None
        # All verified WeCom members intentionally use the configured existing account.
        # Rebind legacy SSO identities without copying or changing either user's data.
        if user is None or not user.is_active:
            raise SsoError("account_disabled")
        identity.user_id = user.id
        identity.name = str(profile.get("name") or "企业微信用户")[:255]
        identity.email = user.email
        await session.commit()
        await session.refresh(user)
        return user


async def prepare_qr(config: SsoConfig, browser_cookie: str) -> tuple[dict, str, str]:
    # Both apps use the same HTTPS hostname on different ports. Cookie scope
    # deliberately matches mind-map's original OAuth callback, with no new callback.
    if urlsplit(config.issuer_origin).hostname != urlsplit(config.origin).hostname:
        raise SsoError("sso_qr_host_mismatch")
    authorization_url, state_cookie = begin_authorization(config)
    parts = urlsplit(authorization_url)
    return_to = parts.path + "?" + parts.query
    headers = {}
    if browser_cookie:
        cookies = SimpleCookie()
        cookies[MIND_MAP_BROWSER_COOKIE] = browser_cookie
        headers["Cookie"] = cookies.output(header="").strip()
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(
                config.issuer_origin + "/api/auth/qr",
                params={"return_to": return_to},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise SsoError("sso_unavailable") from error
    if not isinstance(data, dict) or not isinstance(data.get("loginUrl"), str):
        raise SsoError("sso_unavailable")
    qr_url = urlsplit(data["loginUrl"])
    qr_query = parse_qs(qr_url.query)
    callback = qr_query.get("redirect_uri", [""])[0]
    if (
        qr_url.scheme != "https"
        or qr_url.username
        or qr_url.password
        or qr_url.fragment
        or qr_url.path != "/wwopen/sso/qrConnect"
        or f"{qr_url.scheme}://{qr_url.netloc}"
        not in ("https://open.work.weixin.qq.com", config.issuer_origin)
        or callback != config.issuer_origin + "/api/auth/wecom/callback"
        or not isinstance(data.get("state"), str)
        or not data["state"]
        or qr_query.get("state") != [data["state"]]
    ):
        raise SsoError("sso_unavailable")
    cookies = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        cookies.load(value)
    if MIND_MAP_BROWSER_COOKIE not in cookies:
        raise SsoError("sso_unavailable")
    # The official iframe loads this public stylesheet through its supported
    # href option. Only presentation changes; state and the original callback stay intact.
    qr_query["style"] = ["black"]
    qr_query["href"] = [config.origin + "/wecom-qr.css?v=1"]
    login_url = qr_url._replace(query=urlencode(qr_query, doseq=True)).geturl()
    return (
        {"loginUrl": login_url, "expiresIn": STATE_TTL},
        state_cookie,
        cookies[MIND_MAP_BROWSER_COOKIE].value,
    )
