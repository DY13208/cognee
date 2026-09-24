from pathlib import Path

from cognee.modules.teleology.resolve_teleology_file_path import (
    default_teleology_file_path,
    resolve_teleology_file_path,
)


def test_resolve_falls_back_from_windows_host_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "cognee.modules.teleology.resolve_teleology_file_path.get_base_config",
        lambda: type("Cfg", (), {"system_root_directory": str(tmp_path)})(),
    )
    monkeypatch.setattr(
        "cognee.modules.teleology.resolve_teleology_file_path.get_teleology_env_config",
        lambda: type(
            "Env", (), {"teleology_file_path": r"D:\cognee\examples\teleology\sample_goals.yaml"}
        )(),
    )
    monkeypatch.setattr("os.name", "posix")

    resolved = resolve_teleology_file_path()

    assert resolved == default_teleology_file_path()
    assert resolved == tmp_path / "teleology" / "goals.yaml"


def test_resolve_uses_unset_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "cognee.modules.teleology.resolve_teleology_file_path.get_base_config",
        lambda: type("Cfg", (), {"system_root_directory": str(tmp_path)})(),
    )
    monkeypatch.setattr(
        "cognee.modules.teleology.resolve_teleology_file_path.get_teleology_env_config",
        lambda: type("Env", (), {"teleology_file_path": ""})(),
    )

    assert resolve_teleology_file_path() == tmp_path / "teleology" / "goals.yaml"
