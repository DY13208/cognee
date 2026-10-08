"""Enterprise Goal Network semantics, shared by proposals and read-only analysis.

Polarity denotes direction of change, never business desirability. Conditions
are supplied observations; expressions are never executed by the server.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

NodeType = Literal["goal", "capability", "risk", "constraint", "metric", "driver"]
Relationship = Literal[
    "advances",
    "drives",
    "amplifies",
    "blocks",
    "enables",
    "serves",
    "constrains",
    "measures",
    "sets",
]
NODE_TYPES = frozenset(NodeType.__args__)
RELATIONS = frozenset(Relationship.__args__)
CAUSAL_POLARITY = {"advances": 1, "drives": 1, "amplifies": 1, "blocks": -1}
PREFERRED_RELATIONS = {
    "metric": {"measures"},
    "constraint": {"constrains"},
    "risk": {"blocks", "amplifies"},
    "driver": {"drives", "sets", "amplifies"},
    "capability": {"enables", "serves", "advances"},
    # Preserve the established GOAL blocks contract; polarity warnings remain in proposals.
    "goal": {"advances", "drives", "enables", "serves", "blocks"},
}


def condition_state(condition: Any) -> str:
    """Absent = active; text = unresolved; explicit false = inactive."""
    if condition is None or condition == "":
        return "active"
    if isinstance(condition, bool):
        return "active" if condition else "inactive"
    if isinstance(condition, str):
        return "unresolved"
    if isinstance(condition, dict):
        if isinstance(condition.get("active"), bool):
            return "active" if condition["active"] else "inactive"
        state = condition.get("status", "unresolved")
        if isinstance(state, str) and state in {"active", "inactive", "unresolved"}:
            return state
    raise ValueError("condition must be text, boolean, or an object with a valid status")


def semantic_warnings(nodes: list[dict], relations: list[dict]) -> list[dict]:
    types = {str(n["id"]): str(n.get("node_type") or "goal").lower() for n in nodes}
    warnings = []
    for edge in relations:
        source = str(edge.get("source") or edge.get("source_id") or "")
        kind = types.get(source, "goal")
        relationship = edge.get("relationship")
        if relationship in PREFERRED_RELATIONS.get(kind, set()):
            continue
        reason = "unusual_node_relation_combination"
        if kind == "metric" and relationship in CAUSAL_POLARITY:
            reason = "measurement_to_causality_overreach"
        elif kind == "constraint" and relationship == "advances":
            reason = "constraint_as_positive_causal_advancement"
        warnings.append(
            {
                "kind": "relation",
                "id": edge.get("id"),
                "source_id": source,
                "node_type": kind,
                "relationship": relationship,
                "reason": reason,
            }
        )
    return warnings


def analyze_feedback_loops(
    relations: list[dict[str, Any]], *, nodes: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Enumerate directed elementary cycles, including parallel causal edges.

    Unresolved conditions retain a cycle as CONDITIONAL. Inactive conditions,
    structural/retrieval edges and retired snapshot members never participate.
    """
    allowed = (
        None
        if nodes is None
        else {
            str(n["id"])
            for n in nodes
            if n.get("status") not in {"rejected", "legacy_confirmed"}
            and not n.get("outside_current_snapshot")
        }
    )
    adjacency: dict[str, list[tuple[str, dict]]] = {}
    for edge in relations:
        if edge.get("relationship") not in CAUSAL_POLARITY:
            continue
        if edge.get("status") in {"rejected", "legacy_confirmed"}:
            continue
        if edge.get("outside_current_snapshot") or edge.get("retrieval_only"):
            continue
        if edge.get("origin") == "system_derived":
            continue
        if condition_state(edge.get("condition")) == "inactive":
            continue
        source = str(edge.get("source") or edge.get("source_id") or "")
        target = str(edge.get("target") or edge.get("target_id") or "")
        if not source or not target or (allowed is not None and {source, target} - allowed):
            continue
        adjacency.setdefault(source, []).append((target, edge))
    loops = []
    seen = set()
    for start in sorted(adjacency):
        stack = [(start, [start], [])]
        while stack:
            current, path, edges = stack.pop()
            for target, edge in adjacency.get(current, []):
                if target == start:
                    cycle = edges + [edge]
                    identity = json.dumps(cycle, sort_keys=True, default=str)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    negative = sum(e["relationship"] == "blocks" for e in cycle)
                    conditions = [e["condition"] for e in cycle if e.get("condition") is not None]
                    loops.append(
                        {
                            "loop_id": hashlib.sha256(identity.encode()).hexdigest()[:24],
                            "nodes": path,
                            "edges": cycle,
                            "negative_edge_count": negative,
                            "loop_type": "Balancing" if negative % 2 else "Reinforcing",
                            "status": "CONDITIONAL"
                            if any(
                                condition_state(e.get("condition")) == "unresolved" for e in cycle
                            )
                            else "ACTIVE",
                            "confidence": min(float(e.get("confidence") or 0) for e in cycle),
                            "conditions": conditions,
                            "evidence": [
                                item
                                for e in cycle
                                for item in (e.get("evidence") or e.get("evidence_node_ids") or [])
                            ],
                        }
                    )
                elif target > start and target not in path:
                    stack.append((target, path + [target], edges + [edge]))
    return loops
