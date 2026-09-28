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

    owner: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    primary_purpose_id: str | None = None
    primary_purpose_relation: Literal["serves", "advances"] | None = None
    source: str | None = None


class Purpose(_TeleologyNode):
    """A statement of why a goal or body of work exists."""


class Constraint(_TeleologyNode):
    """A boundary that goal-directed work should satisfy or avoid violating."""
