"""Reuse mind-map's existing WeCom login through a one-time, PKCE-bound code."""

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
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


class SsoError(Exception):
    """Fixed error codes only; never provider responses or credentials."""


@dataclass(frozen=True)
class SsoConfig:
    issuer_origin: str
    redirect_uri: str
    client_secret: str

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
    async with get_relational_engine().get_async_session() as session:
        query = select(OAuthIdentity).where(
            OAuthIdentity.provider == PROVIDER, OAuthIdentity.subject == subject
        )
        identity = (await session.execute(query)).scalar_one_or_none()
        if identity is None:
            user = User(
                id=uuid4(),
                email=f"wecom-{hashlib.sha256(subject.encode()).hexdigest()[:40]}@mind-map.example.com",
                hashed_password=PasswordHelper().hash(secrets.token_urlsafe(48)),
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            identity = OAuthIdentity(user_id=user.id, provider=PROVIDER, subject=subject, email="")
            session.add(user)
            try:
                await session.flush()
                session.add(identity)
                await session.flush()
            except IntegrityError:
                await session.rollback()
                identity = (await session.execute(query)).scalar_one_or_none()
                if identity is None:
                    raise SsoError("account_failed") from None
        user = await session.get(User, identity.user_id)
        if user is None or not user.is_active:
            raise SsoError("account_disabled")
        identity.name = str(profile.get("name") or "企业微信用户")[:255]
        await session.commit()
        await session.refresh(user)
        return user
