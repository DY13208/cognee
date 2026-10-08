from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from cognee.infrastructure.databases.relational import get_relational_engine
from cognee.modules.users.authentication.default import default_transport
from cognee.modules.users.authentication.get_client_auth_backend import get_client_auth_backend
from cognee.modules.users.authentication.mind_map_sso import (
    PROVIDER,
    STATE_COOKIE,
    STATE_PATH,
    STATE_TTL,
    SsoError,
    begin_authorization,
    exchange_code,
    get_config,
    resolve_user,
    verify_state,
)
from cognee.modules.users.authentication.session_settings import mind_map_sso_enabled
from cognee.modules.users.methods.get_authenticated_user import get_authenticated_user
from cognee.modules.users.models import OAuthIdentity, User
from cognee.shared.logging_utils import get_logger

logger = get_logger(__name__)


class SsoCallback(BaseModel):
    code: str = Field(default="", max_length=128)
    state: str = Field(default="", max_length=128)
    error: str = Field(default="", max_length=255)


def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def get_mind_map_sso_router() -> APIRouter:
    router = APIRouter(prefix="/mind-map")

    @router.get("/config")
    async def configuration():
        return private_response(JSONResponse({"enabled": mind_map_sso_enabled()}))

    @router.get("/login")
    async def login():
        try:
            config = get_config()
            url, cookie = begin_authorization(config)
        except (SsoError, ValueError):
            return private_response(JSONResponse({"detail": "sso_not_configured"}, status_code=503))
        response = RedirectResponse(url, status_code=303)
        response.set_cookie(
            STATE_COOKIE,
            cookie,
            max_age=STATE_TTL,
            path=STATE_PATH,
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return private_response(response)

    @router.post("/callback")
    async def callback(request: Request, payload: SsoCallback):
        try:
            config = get_config()
        except (SsoError, ValueError):
            return private_response(JSONResponse({"detail": "sso_not_configured"}, status_code=503))
        try:
            verifier = verify_state(config, request.cookies.get(STATE_COOKIE, ""), payload.state)
            if payload.error:
                raise SsoError("sso_wecom_failed")
            if not payload.code:
                raise SsoError("sso_invalid_grant")
            user = await resolve_user(await exchange_code(config, payload.code, verifier))
            strategy = get_client_auth_backend().get_strategy()
            token = await strategy.write_token(user)
            response = RedirectResponse(config.origin + "/", status_code=303)
            response.set_cookie(
                default_transport.cookie_name,
                token,
                max_age=strategy.lifetime_seconds,
                path="/",
                secure=True,
                httponly=True,
                samesite="lax",
            )
        except SsoError as error:
            response = RedirectResponse(
                config.origin + "/local-login?error=" + str(error), status_code=303
            )
        except Exception as error:  # noqa: BLE001 -- Clear state at the login failure boundary.
            # A consumed code must not be retried after a DB/session failure.
            # Keep the error and all credentials out of logs and return a retry page.
            logger.warning("Mind-map SSO callback failed: error_type=%s", type(error).__name__)
            response = RedirectResponse(
                config.origin + "/local-login?error=sso_unavailable", status_code=303
            )
        response.delete_cookie(
            STATE_COOKIE, path=STATE_PATH, secure=True, httponly=True, samesite="lax"
        )
        return private_response(response)

    @router.get("/me")
    async def me(user: Annotated[User, Depends(get_authenticated_user)]):
        async with get_relational_engine().get_async_session() as session:
            identities = (
                (
                    await session.execute(
                        select(OAuthIdentity).where(
                            OAuthIdentity.user_id == user.id,
                            OAuthIdentity.provider.in_([PROVIDER, "codebuddy"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
            identity = next((item for item in identities if item.provider == PROVIDER), None)
            identity = identity or next(iter(identities), None)
            return private_response(
                JSONResponse(
                    {
                        "id": str(user.id),
                        "name": identity.name if identity else user.email,
                        "email": (identity.email or user.email) if identity else user.email,
                        "picture": "",
                    }
                )
            )

    return router
