import re
from collections.abc import Iterable

from cognee.infrastructure.engine import DataPoint
from cognee.infrastructure.engine.models.Edge import Edge
from cognee.modules.teleology.models import Constraint, Goal

_TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)
_STOP_WORDS = {"a", "an", "and", "for", "of", "or", "the", "to", "with"}
_BLOCKING_TERMS = {"block", "blocks", "conflict", "prevents", "violate", "violates", "weakens"}


def _tokens(value: object) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(str(value or ""))
        if len(token) > 1 and token.lower() not in _STOP_WORDS
    }


def _node_tokens(data_point: DataPoint) -> set[str]:
    return _tokens(getattr(data_point, "name", "")) | _tokens(
        getattr(data_point, "description", "")
    )


def _goal_tokens(goal: Goal | Constraint) -> set[str]:
    tokens = _tokens(goal.name) | _tokens(goal.description)
    for keyword in goal.keywords:
        tokens.update(_tokens(keyword))
    return tokens


def _matches_goal(node_text: str, node_tokens: set[str], goal: Goal | Constraint) -> bool:
    searchable_terms = [goal.name, goal.description, *goal.keywords]
    phrase_match = any(
        str(term).strip().lower() in node_text for term in searchable_terms if str(term).strip()
    )
    return phrase_match or bool(node_tokens & _goal_tokens(goal))


def _has_relation(relations: list[tuple], relationship: str, target_id: object) -> bool:
    return any(
        isinstance(item, tuple)
        and len(item) == 2
        and getattr(item[0], "relationship_type", None) == relationship
        and getattr(item[1], "id", None) == target_id
        for item in relations
    )


def _iter_data_points(values: Iterable[object]) -> Iterable[DataPoint]:
    seen: set[int] = set()
    stack = list(values)
    while stack:
        value = stack.pop()
        if isinstance(value, tuple) and len(value) == 2:
            value = value[1]
        if not isinstance(value, DataPoint) or id(value) in seen:
            continue
        seen.add(id(value))
        yield value
        for field_name in type(value).model_fields:
            field_value = getattr(value, field_name, None)
            if isinstance(field_value, DataPoint):
                stack.append(field_value)
            elif isinstance(field_value, (list, tuple)):
                stack.extend(field_value)


def link_data_points_to_goals(
    data_points: Iterable[object],
    active_goals: Iterable[Goal],
    active_constraints: Iterable[Constraint] = (),
) -> list[DataPoint]:
    """Annotate matching data points with deterministic ``serves``/``advances`` edges.

    Exact phrase matches advance a goal; token/keyword overlap serves it. Nodes
    are never removed, and duplicate edges are suppressed.
    """
    roots = list(data_points)
    goals = list(active_goals)
    constraints = list(active_constraints)
    for data_point in _iter_data_points(roots):
        if isinstance(data_point, Goal):
            continue
        node_text = " ".join(
            str(getattr(data_point, field, "") or "") for field in ("name", "description", "text")
        ).lower()
        node_tokens = _node_tokens(data_point) | _tokens(getattr(data_point, "text", ""))
        relations = getattr(data_point, "relations", None)
        if not isinstance(relations, list):
            continue
        for goal in goals:
            goal_tokens = _goal_tokens(goal)
            if not goal_tokens or not _matches_goal(node_text, node_tokens, goal):
                continue
            goal_name = goal.name.strip().lower()
            relationship = "advances" if goal_name and goal_name in node_text else "serves"
            if _has_relation(relations, relationship, goal.id):
                continue
            relations.append((Edge(relationship_type=relationship), goal))
        if node_tokens & _BLOCKING_TERMS:
            for constraint in constraints:
                if _matches_goal(node_text, node_tokens, constraint) and not _has_relation(
                    relations, "blocks", constraint.id
                ):
                    relations.append((Edge(relationship_type="blocks"), constraint))
    return roots
