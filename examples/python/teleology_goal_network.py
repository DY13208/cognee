"""Enterprise Goal Network analysis; no dataset writes or migrations."""

from cognee.modules.teleology.goal_network import analyze_feedback_loops

relations = [
    {"source_id": "gmv", "target_id": "intensity", "relationship": "drives", "confidence": 0.8},
    {
        "source_id": "intensity",
        "target_id": "risk",
        "relationship": "amplifies",
        "condition": {"expression": "purchase growth > sales demand", "status": "unresolved"},
        "confidence": 0.8,
    },
    {"source_id": "risk", "target_id": "gmv", "relationship": "blocks", "confidence": 0.8},
]

if __name__ == "__main__":
    print(analyze_feedback_loops(relations))  # Balancing, CONDITIONAL


def goal_network_patch(dataset_id: str, base_run_id: str, existing_goal_id: str) -> dict:
    """Construct a dry-run body; never send it or modify production data."""

    def new_node(client_id: str, node_type: str) -> dict:
        return {
            "client_id": client_id,
            "name": client_id,
            "node_type": node_type,
            "reason": "supported by evidence",
            "confidence": 0.8,
            "evidence_node_ids": ["replace-with-dataset-evidence-id"],
        }

    def edge(relationship: str, **endpoints) -> dict:
        return {
            "relationship": relationship,
            "reason": "business mechanism",
            "confidence": 0.8,
            "evidence_node_ids": ["replace-with-dataset-evidence-id"],
            **endpoints,
        }

    return {
        "dataset_id": dataset_id,
        "submission_mode": "patch",
        "base_run_id": base_run_id,
        "dry_run": True,
        "upsert_goals": [
            {"candidate_id": existing_goal_id},
            new_node("G6", "goal"),
            new_node("G5", "goal"),
            new_node("D1", "driver"),
            new_node("D2", "driver"),
            new_node("R2", "risk"),
        ],
        "relations": [
            edge("drives", source_candidate_id=existing_goal_id, target_client_id="G6"),
            edge("advances", source_client_id="G6", target_candidate_id=existing_goal_id),
            edge("sets", source_client_id="D1", target_client_id="G6"),
            edge("drives", source_client_id="G5", target_client_id="D2"),
            edge("amplifies", source_client_id="D2", target_client_id="R2"),
        ],
    }
