"""WorkBuddy authorization-code client. Provider tokens never leave the backend."""

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
from cognee.modules.users.authentication.codebuddy_sharing import grant_shared_read
from cognee.modules.users.authentication.session_settings import codebuddy_enabled, session_settings
from cognee.modules.users.models import OAuthIdentity, User

STATE_COOKIE = "codebuddy_oauth_state"
STATE_TTL = 600


class OAuthError(Exception):
    """An intentionally non-sensitive error code suitable for the login page."""


@dataclass(frozen=True)
class CodeBuddyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    scope: str = ""
    token_auth_method: str = "client_secret_post"

    @property
    def origin(self) -> str:
        parts = urlsplit(self.redirect_uri)
        return f"{parts.scheme}://{parts.netloc}"


def get_config() -> CodeBuddyConfig:
    if not codebuddy_enabled():
        raise OAuthError("not_configured")
    config = CodeBuddyConfig(
        client_id=os.getenv("CODEBUDDY_CLIENT_ID", ""),
        client_secret=os.getenv("CODEBUDDY_CLIENT_SECRET", ""),
        redirect_uri=os.getenv("CODEBUDDY_REDIRECT_URI", ""),
        authorization_endpoint=os.getenv(
            "CODEBUDDY_AUTHORIZATION_ENDPOINT", "https://www.workbuddy.cn/oauth2"
        ),
        token_endpoint=os.getenv(
            "CODEBUDDY_TOKEN_ENDPOINT", "https://www.workbuddy.cn/oauth2/token"
        ),
        userinfo_endpoint=os.getenv(
            "CODEBUDDY_USERINFO_ENDPOINT", "https://www.workbuddy.cn/oauth2/userinfo"
        ),
        scope=os.getenv("CODEBUDDY_SCOPE", ""),
        token_auth_method=os.getenv("CODEBUDDY_TOKEN_AUTH_METHOD", "client_secret_post"),
    )
    if not config.client_id or not config.client_secret:
        raise OAuthError("not_configured")
    for url in (
        config.redirect_uri,
        config.authorization_endpoint,
        config.token_endpoint,
        config.userinfo_endpoint,
    ):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.fragment:
            raise OAuthError("not_configured")
    if urlsplit(config.redirect_uri).path != "/oauth/callback":
        raise OAuthError("not_configured")
    if config.token_auth_method not in ("client_secret_post", "client_secret_basic"):
        raise OAuthError("not_configured")
    # Independent users must not accidentally share a global graph/vector backend.
    if os.getenv("ENABLE_BACKEND_ACCESS_CONTROL", "true").lower() != "true":
        raise OAuthError("access_control_required")
    return config


def begin_authorization(config: CodeBuddyConfig) -> tuple[str, str]:
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
            "aud": "codebuddy-oauth",
            "redirect_uri": config.redirect_uri,
        },
        secret,
        algorithm="HS256",
    )
    query = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
        "code_challenge": challenge.decode(),
        "code_challenge_method": "S256",
    }
    if config.scope:
        query["scope"] = config.scope
    separator = "&" if "?" in config.authorization_endpoint else "?"
    return config.authorization_endpoint + separator + urlencode(query), cookie


def verify_state(config: CodeBuddyConfig, cookie: str, state: str) -> str:
    secret, _ = session_settings()
    try:
        payload = jwt.decode(
            cookie,
            secret,
            algorithms=["HS256"],
            audience="codebuddy-oauth",
            options={"require": ["exp", "iat", "aud", "state", "verifier", "redirect_uri"]},
        )
        if not state or not secrets.compare_digest(payload["state"], state):
            raise OAuthError("invalid_state")
        if payload["redirect_uri"] != config.redirect_uri:
            raise OAuthError("invalid_state")
        return payload["verifier"]
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise OAuthError("invalid_state") from error


async def fetch_userinfo(config: CodeBuddyConfig, code: str, verifier: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "code_verifier": verifier,
    }
    auth = None
    if config.token_auth_method == "client_secret_basic":
        auth = httpx.BasicAuth(config.client_id, config.client_secret)
    else:
        data["client_secret"] = config.client_secret
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            token_response = await client.post(
                config.token_endpoint, data=data, auth=auth, headers={"Accept": "application/json"}
            )
            token_response.raise_for_status()
            token = token_response.json()
            access_token = token.get("access_token") if isinstance(token, dict) else None
            if not isinstance(access_token, str) or not access_token:
                raise OAuthError("token_failed")
            if str(token.get("token_type", "Bearer")).lower() != "bearer":
                raise OAuthError("token_failed")
            response = await client.get(
                config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            profile = response.json()
    except (httpx.HTTPError, ValueError) as error:
        # Never log provider bodies, URLs containing codes, or access/refresh tokens.
        raise OAuthError("provider_unavailable") from error
    if not isinstance(profile, dict):
        raise OAuthError("invalid_profile")
    return profile


def profile_subject(profile: dict) -> str:
    subject = profile.get("sub", profile.get("id"))
    if isinstance(subject, bool) or not isinstance(subject, (str, int)):
        raise OAuthError("invalid_profile")
    subject = str(subject).strip()
    if not subject or len(subject) > 255:
        raise OAuthError("invalid_profile")
    return subject


async def resolve_user(profile: dict) -> User:
    subject = profile_subject(profile)
    engine = get_relational_engine()
    async with engine.get_async_session() as session:
        query = select(OAuthIdentity).where(
            OAuthIdentity.provider == "codebuddy", OAuthIdentity.subject == subject
        )
        identity = (await session.execute(query)).scalar_one_or_none()
        if identity is None:
            # A provider email is profile data, never an automatic account-linking key.
            user = User(
                id=uuid4(),
                email=f"cb-{hashlib.sha256(subject.encode()).hexdigest()[:40]}@codebuddy.example.com",
                hashed_password=PasswordHelper().hash(secrets.token_urlsafe(48)),
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            identity = OAuthIdentity(
                user_id=user.id, provider="codebuddy", subject=subject, name="", email=""
            )
            session.add(user)
            try:
                await session.flush()
                session.add(identity)
                await session.flush()
            except IntegrityError:
                # Two simultaneous first logins must resolve to one user, atomically.
                await session.rollback()
                identity = (await session.execute(query)).scalar_one_or_none()
                if identity is None:
                    raise OAuthError("account_failed") from None
        user = await session.get(User, identity.user_id)
        if user is None or not user.is_active:
            raise OAuthError("account_disabled")
        identity.name = str(profile.get("name") or profile.get("nickname") or "WorkBuddy User")[
            :255
        ]
        identity.email = str(profile.get("email") or "")[:320]
        await session.commit()
        await session.refresh(user)
    await grant_shared_read(user)
    return user
