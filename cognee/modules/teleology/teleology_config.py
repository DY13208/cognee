from typing import TypedDict

from cognee.modules.teleology.base_teleology_resolver import BaseTeleologyResolver


class TeleologyConfig(TypedDict, total=False):
    """Configuration for goal annotation."""

    teleology_resolver: BaseTeleologyResolver | None
    teleology_mode: str | None


class Config(TypedDict, total=False):
    """Top-level configuration containing optional teleology settings."""

    teleology_config: TeleologyConfig | None
