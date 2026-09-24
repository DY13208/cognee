from typing import Literal

from pydantic import Field

from cognee.infrastructure.engine import DataPoint

GoalStatus = Literal["proposed", "active", "achieved", "abandoned"]


class _TeleologyNode(DataPoint):
    """Base for persistent, deterministically identified teleology nodes."""

    name: str
    status: GoalStatus = "proposed"
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    relations: list[tuple] = Field(default_factory=list)
    metadata: dict = {  # noqa: RUF012 - Pydantic model field default, matching DataPoint models.
        "index_fields": ["name"],
        "identity_fields": ["id"],
    }


class Goal(_TeleologyNode):
    """An outcome that knowledge can serve, advance, or block."""


class Purpose(_TeleologyNode):
    """A statement of why a goal or body of work exists."""


class Constraint(_TeleologyNode):
    """A boundary that goal-directed work should satisfy or avoid violating."""
