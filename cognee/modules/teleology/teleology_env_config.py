"""Environment configuration for YAML-backed teleology annotations."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_TELEOLOGY_MODES = frozenset({"annotate", "strict"})
DEFAULT_TELEOLOGY_MODE = "annotate"


def normalize_teleology_mode(mode: str | None) -> str:
    normalized = str(mode or DEFAULT_TELEOLOGY_MODE).strip().lower()
    if normalized not in VALID_TELEOLOGY_MODES:
        raise ValueError(
            f"Unsupported TELEOLOGY_MODE={mode!r}. Valid values: "
            f"{', '.join(sorted(VALID_TELEOLOGY_MODES))}."
        )
    if normalized == "strict":
        raise NotImplementedError(
            "TELEOLOGY_MODE=strict is reserved but not implemented; use annotate."
        )
    return normalized


class TeleologyEnvConfig(BaseSettings):
    teleology_file_path: str = ""
    teleology_mode: str = DEFAULT_TELEOLOGY_MODE

    model_config = SettingsConfigDict(env_file=".env", extra="allow", populate_by_name=True)

    @field_validator("teleology_mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value) -> str:
        return normalize_teleology_mode(value)


@lru_cache
def get_teleology_env_config() -> TeleologyEnvConfig:
    return TeleologyEnvConfig()
