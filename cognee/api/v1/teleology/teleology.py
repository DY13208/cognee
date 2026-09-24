"""Read / write the active teleology YAML used by cognify annotations."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

import yaml

from cognee.modules.teleology.models import Constraint, Goal, Purpose
from cognee.modules.teleology.resolve_teleology_file_path import resolve_teleology_file_path
from cognee.modules.teleology.teleology_env_config import get_teleology_env_config
from cognee.modules.teleology.yaml import YamlTeleologyResolver

NodeKind = Literal["goal", "purpose", "constraint"]

_KIND_TO_KEY: dict[NodeKind, str] = {
    "goal": "goals",
    "purpose": "purposes",
    "constraint": "constraints",
}

_VALID_STATUSES = frozenset({"proposed", "active", "achieved", "abandoned"})


def _serialize_node(node: Goal | Purpose | Constraint) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "name": node.name,
        "status": node.status,
        "description": node.description,
        "keywords": list(node.keywords or []),
        "type": type(node).__name__.lower(),
    }


def _empty_payload() -> dict[str, list]:
    return {"goals": [], "purposes": [], "constraints": []}


class TeleologyService:
    def get_status(self) -> dict[str, Any]:
        path = resolve_teleology_file_path()
        mode = get_teleology_env_config().teleology_mode
        exists = path.is_file()
        payload: dict[str, Any] = {
            "enabled": exists,
            "mode": mode,
            "file_path": str(path),
            "source": (
                "env"
                if (get_teleology_env_config().teleology_file_path or "").strip()
                else "default"
            ),
            "goals": [],
            "purposes": [],
            "constraints": [],
        }
        if not exists:
            return payload
        try:
            resolver = YamlTeleologyResolver(path)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the API
            payload["enabled"] = False
            payload["error"] = str(exc)
            return payload
        payload["goals"] = [_serialize_node(g) for g in resolver.get_goals()]
        payload["purposes"] = [_serialize_node(p) for p in resolver.get_purposes()]
        payload["constraints"] = [_serialize_node(c) for c in resolver.get_constraints()]
        return payload

    def _load_raw(self) -> dict[str, list]:
        path = resolve_teleology_file_path()
        if not path.is_file():
            return _empty_payload()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("Teleology YAML root must be a mapping")
        result = _empty_payload()
        for key in result:
            items = data.get(key, [])
            if items is None:
                items = []
            if not isinstance(items, list):
                raise ValueError(f"Teleology '{key}' must be a list")
            result[key] = [item for item in items if isinstance(item, dict)]
        return result

    def _write_raw(self, data: dict[str, list], filename: str | None = None) -> dict[str, Any]:
        # Keep only known sections; drop empty optional lists for cleaner files.
        clean: dict[str, list] = {
            "goals": data.get("goals") or [],
            "purposes": data.get("purposes") or [],
            "constraints": data.get("constraints") or [],
        }
        text = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, default_flow_style=False)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        try:
            YamlTeleologyResolver(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        path = resolve_teleology_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        status = self.get_status()
        if filename:
            status["uploaded_filename"] = filename
        return status

    def save_yaml(self, content: bytes, filename: str | None = None) -> dict[str, Any]:
        text = content.decode("utf-8")
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        try:
            YamlTeleologyResolver(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        path = resolve_teleology_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        status = self.get_status()
        status["uploaded_filename"] = filename
        return status

    def clear(self) -> dict[str, Any]:
        path = resolve_teleology_file_path()
        if path.is_file():
            path.unlink()
        return self.get_status()

    @staticmethod
    def _normalize_entry(
        *,
        name: str,
        status: str | None,
        description: str | None,
        keywords: list[str] | None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("Name is required")
        cleaned_status = (status or "proposed").strip().lower()
        if cleaned_status not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid status {status!r}. Valid: {', '.join(sorted(_VALID_STATUSES))}"
            )
        kw = keywords or []
        if isinstance(kw, str):
            kw = [part.strip() for part in kw.split(",") if part.strip()]
        else:
            kw = [str(part).strip() for part in kw if str(part).strip()]
        entry: dict[str, Any] = {
            "id": node_id or str(uuid.uuid4()),
            "name": cleaned_name,
            "status": cleaned_status,
            "description": (description or "").strip(),
            "keywords": kw,
        }
        # Validate against the pydantic model for the shared fields.
        Goal.model_validate({**entry, "status": cleaned_status})  # type: ignore[arg-type]
        return entry

    def create_node(
        self,
        kind: NodeKind,
        *,
        name: str,
        status: str | None = "proposed",
        description: str | None = "",
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        if kind not in _KIND_TO_KEY:
            raise ValueError(f"Invalid node type: {kind}")
        data = self._load_raw()
        key = _KIND_TO_KEY[kind]
        entry = self._normalize_entry(
            name=name, status=status, description=description, keywords=keywords
        )
        data[key].append(entry)
        status_payload = self._write_raw(data)
        status_payload["created"] = {**entry, "type": kind}
        return status_payload

    def update_node(
        self,
        node_id: str,
        *,
        kind: NodeKind | None = None,
        name: str | None = None,
        status: str | None = None,
        description: str | None = None,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        data = self._load_raw()
        found_key: str | None = None
        found_index = -1
        existing: dict[str, Any] | None = None
        search_keys = (
            [_KIND_TO_KEY[kind]] if kind and kind in _KIND_TO_KEY else list(_KIND_TO_KEY.values())
        )
        for key in search_keys:
            for i, item in enumerate(data[key]):
                if str(item.get("id")) == str(node_id):
                    found_key = key
                    found_index = i
                    existing = item
                    break
            if existing is not None:
                break
        if existing is None or found_key is None:
            raise KeyError(f"Teleology node '{node_id}' not found")

        entry = self._normalize_entry(
            name=name if name is not None else str(existing.get("name") or ""),
            status=status if status is not None else str(existing.get("status") or "proposed"),
            description=(
                description if description is not None else str(existing.get("description") or "")
            ),
            keywords=keywords if keywords is not None else list(existing.get("keywords") or []),
            node_id=str(node_id),
        )
        data[found_key][found_index] = entry
        kind_name = next(k for k, v in _KIND_TO_KEY.items() if v == found_key)
        status_payload = self._write_raw(data)
        status_payload["updated"] = {**entry, "type": kind_name}
        return status_payload

    def delete_node(self, node_id: str, kind: NodeKind | None = None) -> dict[str, Any]:
        data = self._load_raw()
        search_keys = (
            [_KIND_TO_KEY[kind]] if kind and kind in _KIND_TO_KEY else list(_KIND_TO_KEY.values())
        )
        removed = False
        for key in search_keys:
            before = len(data[key])
            data[key] = [item for item in data[key] if str(item.get("id")) != str(node_id)]
            if len(data[key]) < before:
                removed = True
                break
        if not removed:
            raise KeyError(f"Teleology node '{node_id}' not found")

        # If everything is empty, remove the file so enabled=false.
        if not any(data[k] for k in data):
            return self.clear()
        return self._write_raw(data)

    def upsert_goals(self, entries: list[dict[str, Any]]) -> int:
        """Merge goal dicts by id into the teleology YAML (create or update)."""
        if not entries:
            return 0
        data = self._load_raw()
        by_id = {str(item.get("id")): i for i, item in enumerate(data["goals"])}
        changed = 0
        for raw in entries:
            entry = self._normalize_entry(
                name=str(raw.get("name") or ""),
                status=str(raw.get("status") or "active"),
                description=str(raw.get("description") or ""),
                keywords=list(raw.get("keywords") or []),
                node_id=str(raw["id"]) if raw.get("id") else None,
            )
            idx = by_id.get(str(entry["id"]))
            if idx is None:
                data["goals"].append(entry)
                by_id[str(entry["id"])] = len(data["goals"]) - 1
            else:
                data["goals"][idx] = entry
            changed += 1
        if changed:
            self._write_raw(data)
        return changed
