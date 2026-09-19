import os


def codebuddy_enabled() -> bool:
    return os.getenv("CODEBUDDY_ENABLED", "false").lower() == "true"


def session_settings() -> tuple[str, int]:
    if codebuddy_enabled():
        secret = os.getenv("CODEBUDDY_SESSION_SECRET", "")
        if len(secret) < 32:
            raise ValueError("CODEBUDDY_SESSION_SECRET must contain at least 32 characters")
        lifetime = int(os.getenv("CODEBUDDY_SESSION_LIFETIME_SECONDS", "604800"))
    else:
        secret = os.getenv("FASTAPI_USERS_JWT_SECRET", "super_secret")
        lifetime = int(os.getenv("JWT_LIFETIME_SECONDS", "3600"))
    if lifetime <= 0:
        raise ValueError("Session lifetime must be positive")
    return secret, lifetime
