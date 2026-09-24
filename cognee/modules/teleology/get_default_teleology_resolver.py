from cognee.modules.teleology.base_teleology_resolver import BaseTeleologyResolver
from cognee.modules.teleology.resolve_teleology_file_path import resolve_teleology_file_path
from cognee.modules.teleology.teleology_config import Config
from cognee.modules.teleology.teleology_env_config import (
    get_teleology_env_config,
    normalize_teleology_mode,
)
from cognee.modules.teleology.yaml import YamlTeleologyResolver


def get_configured_teleology_resolver(
    config: Config | None = None,
) -> BaseTeleologyResolver | None:
    """Resolve an explicit resolver, env path, or the default system goals file."""
    if config is not None:
        teleology_config = config.get("teleology_config")
        if isinstance(teleology_config, dict) and "teleology_resolver" in teleology_config:
            return teleology_config["teleology_resolver"]
        # No explicit resolver — fall through to env / default file.

    path = resolve_teleology_file_path()
    if path.is_file():
        return YamlTeleologyResolver(path)
    return None


def get_configured_teleology_mode(config: Config | None = None) -> str:
    """Resolve and validate the per-call or environment teleology mode."""
    if config is not None:
        teleology_config = config.get("teleology_config")
        if (
            isinstance(teleology_config, dict)
            and teleology_config.get("teleology_mode") is not None
        ):
            return normalize_teleology_mode(teleology_config["teleology_mode"])
    return get_teleology_env_config().teleology_mode
