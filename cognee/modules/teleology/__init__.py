"""Goal-oriented annotations for Cognee knowledge graphs.

Ontology describes what a thing is. Teleology describes what a knowledge point
is for. The modules are intentionally independent: teleology reads YAML goals
and adds post-extraction edges without changing ontology grounding.
"""

from .models import Constraint, Goal, GoalStatus, Purpose

__all__ = ["Constraint", "Goal", "GoalStatus", "Purpose"]
