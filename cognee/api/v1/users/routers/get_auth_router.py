from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm

from cognee.modules.users.authentication.default.default_transport import default_transport
from cognee.modules.users.authentication.get_client_auth_backend import get_client_auth_backend
from cognee.modules.users.authentication.methods.authenticate_user import authenticate_user
from cognee.modules.users.authentication.session_settings import codebuddy_enabled
from cognee.modules.users.methods import get_authenticated_user
from cognee.modules.users.models import User

from .get_codebuddy_router import get_codebuddy_router


def get_auth_router():
    router = APIRouter()
    router.include_router(get_codebuddy_router())

    @router.post("/login")
    async def login(
        response: Response,
        credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    ):
        """Login — POST /api/v1/auth/login."""
        user = await authenticate_user(credentials.username, credentials.password)

        if user is None:
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")

        client_backend = get_client_auth_backend()
        strategy = client_backend.get_strategy()
        token = await strategy.write_token(user)

        response.set_cookie(
            key=default_transport.cookie_name,
            value=token,
            max_age=strategy.lifetime_seconds,
            path=default_transport.cookie_path,
            domain=None if codebuddy_enabled() else default_transport.cookie_domain,
            secure=codebuddy_enabled() or default_transport.cookie_secure,
            httponly=default_transport.cookie_httponly,
            samesite=default_transport.cookie_samesite,
        )

        return {"access_token": token, "token_type": "bearer"}

    @router.post("/logout")
    async def logout(response: Response):
        """Logout — POST /api/v1/auth/logout."""
        response.delete_cookie(
            key=default_transport.cookie_name,
            domain=None if codebuddy_enabled() else default_transport.cookie_domain,
            path="/",
        )

        return {}

    @router.get("/me")
    async def get_me(user: Annotated[User, Depends(get_authenticated_user)]):
        """Get me — GET /api/v1/auth/me."""
        return {
            "email": user.email,
        }

    return router
