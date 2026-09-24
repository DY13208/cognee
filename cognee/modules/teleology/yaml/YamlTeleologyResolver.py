# ruff: noqa: N999 - public filename follows the existing ontology resolver convention.

from pathlib import Path
from typing import TypeVar

import yaml

from cognee.modules.teleology.base_teleology_resolver import BaseTeleologyResolver
from cognee.modules.teleology.models import Constraint, Goal, Purpose

TeleologyNode = TypeVar("TeleologyNode", Goal, Purpose, Constraint)


class YamlTeleologyResolver(BaseTeleologyResolver):
    """Load a small goal graph from a local YAML file."""

    def __init__(self, teleology_file: str | Path):
        self.teleology_file = Path(teleology_file)
        if not self.teleology_file.is_file():
            raise FileNotFoundError(f"Teleology YAML file not found: {self.teleology_file}")
        with self.teleology_file.open("r", encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise TypeError("Teleology YAML root must be a mapping.")
        self._goals = self._parse(payload.get("goals", []), Goal)
        self._purposes = self._parse(payload.get("purposes", []), Purpose)
        self._constraints = self._parse(payload.get("constraints", []), Constraint)

    @staticmethod
    def _parse(items: object, model: type[TeleologyNode]) -> list[TeleologyNode]:
        if not isinstance(items, list):
            raise TypeError(f"Teleology {model.__name__.lower()} entries must be a list.")
        return [model.model_validate(item) for item in items]

    def get_goals(self) -> list[Goal]:
        return list(self._goals)

    def get_purposes(self) -> list[Purpose]:
        return list(self._purposes)

    def get_constraints(self) -> list[Constraint]:
        return list(self._constraints)
