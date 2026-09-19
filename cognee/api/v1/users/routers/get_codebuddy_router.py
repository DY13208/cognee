from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from cognee.infrastructure.databases.relational import get_relational_engine
from cognee.modules.users.authentication.codebuddy import (
    STATE_COOKIE,
    STATE_TTL,
    OAuthError,
    begin_authorization,
    fetch_userinfo,
    get_config,
    resolve_user,
    verify_state,
)
from cognee.modules.users.authentication.default import default_transport
from cognee.modules.users.authentication.get_client_auth_backend import get_client_auth_backend
from cognee.modules.users.methods.get_authenticated_user import get_authenticated_user
from cognee.modules.users.models import OAuthIdentity, User


class OAuthCallback(BaseModel):
    code: str = Field(default="", max_length=4096)
    state: str = Field(default="", max_length=1024)
    error: str = Field(default="", max_length=255)


def get_codebuddy_router() -> APIRouter:
    router = APIRouter(prefix="/codebuddy")

    @router.get("/login")
    async def login():
        try:
            config = get_config()
            authorization_url, cookie = begin_authorization(config)
        except (OAuthError, ValueError):
            return JSONResponse({"detail": "WorkBuddy login is not configured"}, status_code=503)
        response = RedirectResponse(authorization_url, status_code=303)
        response.set_cookie(
            STATE_COOKIE,
            cookie,
            max_age=STATE_TTL,
            path="/oauth",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.post("/callback")
    async def callback(request: Request, payload: OAuthCallback):
        try:
            config = get_config()
        except (OAuthError, ValueError):
            return JSONResponse({"detail": "WorkBuddy login is not configured"}, status_code=503)
        try:
            verifier = verify_state(
                config,
                request.cookies.get(STATE_COOKIE, ""),
                payload.state,
            )
            if payload.error:
                raise OAuthError("access_denied")
            code = payload.code
            if not code or len(code) > 4096:
                raise OAuthError("missing_code")
            profile = await fetch_userinfo(config, code, verifier)
            user = await resolve_user(profile)
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
        except OAuthError as error:
            response = RedirectResponse(
                config.origin + "/local-login?error=" + str(error), status_code=303
            )
        response.delete_cookie(
            STATE_COOKIE, path="/oauth", secure=True, httponly=True, samesite="lax"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.get("/me")
    async def me(user: Annotated[User, Depends(get_authenticated_user)]):
        async with get_relational_engine().get_async_session() as session:
            identity = (
                await session.execute(
                    select(OAuthIdentity).where(
                        OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "codebuddy"
                    )
                )
            ).scalar_one_or_none()
            return {
                "id": str(user.id),
                "name": identity.name if identity else user.email,
                "email": identity.email if identity else user.email,
                "picture": "",
            }

    return router
