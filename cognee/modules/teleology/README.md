# Teleology

Ontology answers **what a thing is** and may canonicalize extracted entities.
Teleology answers **what a knowledge point is for**. It annotates the graph with
`serves`, `advances`, or `blocks` edges — either automatically during cognify
(YAML keyword match) or manually via the Teleology UI / annotations API.

## Automatic (cognify)

Set `TELEOLOGY_FILE_PATH` to a local YAML file and leave `TELEOLOGY_MODE=annotate`
to enable it. `strict` is reserved for a future release and raises an explicit
`NotImplementedError`. Uploads from the UI land in
`{SYSTEM_ROOT_DIRECTORY}/teleology/goals.yaml` when the env path is unset.

## Manual (graph annotations)

HTTP (dataset-scoped):

- `GET /api/v1/teleology/annotations?dataset_id=...` — goals, nodes, purpose edges
- `POST /api/v1/teleology/annotations/sync-from-company-tree?dataset_id=...` — build teleology from the company goal tree (CPD goals = Goal nodes; `has_subgoal` → `advances`; optional entity name-overlap → `serves`)
- `POST /api/v1/teleology/annotations/sync-goals?dataset_id=...` — upsert YAML goals into the graph (optional vocabulary path)
- `POST /api/v1/teleology/annotations` — add `serves` / `advances` / `blocks`
- `DELETE /api/v1/teleology/annotations` — remove a purpose edge

## Retrieval

Search and recall use the persisted goal edges without changing the extraction schema:

```python
await cognee.search("retrieval quality", goal_id=goal_uuid)
await cognee.search("retrieval quality", goal_id=goal_uuid, goal_filter_mode="filter")
await cognee.recall("retrieval quality", goal_id=goal_uuid)
```

`rerank` is the default and stably promotes goal-related results. `filter`
returns only results connected to the selected goal through a teleology edge.
