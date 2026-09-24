from abc import ABC, abstractmethod

from cognee.modules.teleology.models import Constraint, Goal, Purpose


class BaseTeleologyResolver(ABC):
    """Interface for sources of goals, purposes, and constraints."""

    @abstractmethod
    def get_goals(self) -> list[Goal]:
        """Return all configured goals."""

    def get_active_goals(self) -> list[Goal]:
        """Return goals which should receive new annotations."""
        return [goal for goal in self.get_goals() if goal.status == "active"]

    @abstractmethod
    def get_purposes(self) -> list[Purpose]:
        """Return all configured purposes."""

    @abstractmethod
    def get_constraints(self) -> list[Constraint]:
        """Return all configured constraints."""
