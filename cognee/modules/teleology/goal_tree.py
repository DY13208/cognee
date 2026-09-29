"""Manual ordering and parent edits for derived goal candidates."""

from __future__ import annotations

from typing import Any

from cognee.modules.teleology.goal_model import GoalBuildError


def ordered_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep generated order until a sibling group receives a manual order."""
    return [
        goal
        for _, goal in sorted(
            enumerate(candidates),
            key=lambda pair: (
                pair[1].get("sort_order") is None,
                pair[1].get("sort_order") or 0,
                pair[0],
            ),
        )
    ]


def move_candidate(
    candidates: list[dict[str, Any]],
    candidate_id: str,
    target_id: str | None,
    placement: str,
) -> dict[str, Any]:
    """Move a goal before/after another goal, inside it, or to the root."""
    if placement not in {"before", "after", "inside", "root"}:
        raise GoalBuildError("Invalid goal placement")
    if placement == "root" and target_id is not None:
        raise GoalBuildError("Root placement cannot have a target")
    if placement != "root" and not target_id:
        raise GoalBuildError("Target goal is required")

    active = {
        str(goal["id"]): goal
        for goal in candidates
        if goal.get("status") not in {"rejected", "legacy_confirmed"}
        and not goal.get("outside_current_snapshot")
    }
    source = active.get(candidate_id)
    target = active.get(target_id or "")
    if source is None or (placement != "root" and target is None):
        raise GoalBuildError("Goal is not available in this dataset", 404)
    if target_id == candidate_id:
        raise GoalBuildError("A goal cannot be dropped on itself")

    previous_parent = source.get("parent_candidate_id") or None
    parent_id = (
        target_id
        if placement == "inside"
        else (target.get("parent_candidate_id") or None if target else None)
    )
    seen: set[str] = set()
    ancestor = parent_id
    while ancestor:
        if ancestor == candidate_id or ancestor in seen:
            raise GoalBuildError("Moving this goal would create a cycle")
        seen.add(ancestor)
        ancestor = (active.get(ancestor) or {}).get("parent_candidate_id") or None

    ordered = ordered_candidates(candidates)
    siblings = [
        goal
        for goal in ordered
        if str(goal.get("id")) in active
        and str(goal.get("id")) != candidate_id
        and (goal.get("parent_candidate_id") or None) == parent_id
    ]
    if placement in {"before", "after"}:
        assert target_id is not None
        position = next(i for i, goal in enumerate(siblings) if str(goal["id"]) == target_id)
        if placement == "after":
            position += 1
    else:
        position = len(siblings)
    siblings.insert(position, source)
    source["parent_candidate_id"] = parent_id
    if previous_parent != parent_id:
        source["parent_override"] = True
    for index, goal in enumerate(siblings):
        goal["sort_order"] = index
    if previous_parent != parent_id:
        old_siblings = [
            goal
            for goal in ordered
            if str(goal.get("id")) in active
            and str(goal.get("id")) != candidate_id
            and (goal.get("parent_candidate_id") or None) == previous_parent
        ]
        for index, goal in enumerate(old_siblings):
            goal["sort_order"] = index
    return {
        "candidate_id": candidate_id,
        "parent_candidate_id": parent_id,
        "parent_changed": previous_parent != parent_id,
        "sort_order": position,
    }
