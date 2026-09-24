"""Resolve the active teleology YAML path (env or system default)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from cognee.base_config import get_base_config
from cognee.modules.teleology.teleology_env_config import get_teleology_env_config
from cognee.shared.logging_utils import get_logger

logger = get_logger(__name__)

_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def default_teleology_file_path() -> Path:
    """Writable fallback when TELEOLOGY_FILE_PATH is unset."""
    return Path(get_base_config().system_root_directory) / "teleology" / "goals.yaml"


def _is_unreachable_host_windows_path(value: str) -> bool:
    """True when a Windows drive path is configured on a non-Windows runtime.

    Common Docker misconfig: TELEOLOGY_FILE_PATH=D:\\repo\\... on the host.
    Inside the Linux container that path does not exist, so we fall back.
    """
    if os.name == "nt":
        return False
    return bool(_WINDOWS_DRIVE_PATH.match(value)) or ("\\" in value and not value.startswith("/"))


def resolve_teleology_file_path() -> Path:
    """Prefer TELEOLOGY_FILE_PATH; otherwise the system teleology goals file.

    Leave TELEOLOGY_FILE_PATH unset in Docker/production — goals created in the
    UI are stored under ``{SYSTEM_ROOT_DIRECTORY}/teleology/goals.yaml``.
    """
    env_path = (get_teleology_env_config().teleology_file_path or "").strip()
    if not env_path:
        return default_teleology_file_path()

    if _is_unreachable_host_windows_path(env_path):
        fallback = default_teleology_file_path()
        logger.warning(
            "TELEOLOGY_FILE_PATH=%r looks like a host Windows path and is not "
            "reachable here; using %s instead. Leave TELEOLOGY_FILE_PATH unset "
            "in Docker/production, or point it at a path inside the container.",
            env_path,
            fallback,
        )
        return fallback

    return Path(env_path)
