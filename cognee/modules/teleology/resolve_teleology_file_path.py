"""Resolve the active teleology YAML path (env or system default)."""

from pathlib import Path

from cognee.base_config import get_base_config
from cognee.modules.teleology.teleology_env_config import get_teleology_env_config


def default_teleology_file_path() -> Path:
    """Writable fallback when TELEOLOGY_FILE_PATH is unset."""
    return Path(get_base_config().system_root_directory) / "teleology" / "goals.yaml"


def resolve_teleology_file_path() -> Path:
    """Prefer TELEOLOGY_FILE_PATH; otherwise the system teleology goals file."""
    env_path = (get_teleology_env_config().teleology_file_path or "").strip()
    if env_path:
        return Path(env_path)
    return default_teleology_file_path()
