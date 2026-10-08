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


## Enterprise Goal Network (orchestrated snapshots)

The existing `/goal-model/proposals` contract accepts six semantic node types
in `goals` / `upsert_goals`: `goal`, `capability`, `risk`, `constraint`, `metric`,
and `driver`. `node_type` defaults to goal for legacy submissions. A patch that
omits the type preserves the existing type. Non-goal nodes are not classified
or stored as semantic goals; `candidates` remains the historical snapshot bucket.

Patch upserts bind existing nodes only by `candidate_id` returned by the current
Goal Model. Names never bind an existing node. An unbound same-name submission
returns `EXISTING_CANDIDATE_BINDING_REQUIRED`; historical/legacy ids return
`INVALID_EXISTING_CANDIDATE`. Current canonical records are selected by stable
id and snapshot membership, never by historical name matches.

Proposal relations use `source_client_id` / `target_client_id` for proposal nodes
and `source_candidate_id` / `target_candidate_id` for current canonical nodes.
Use exactly one field per side. `source`, `target`, `source_id`, `target_id`,
`source_ref`, and `target_ref` are not proposal endpoint aliases; invalid,
ambiguous, missing or historical endpoints return `INVALID_RELATION_ENDPOINT`.
`source` / `target` remain the persisted/read-back fields, not proposal inputs.
The shared specification lives in
`goal_network.py`: advances, drives, amplifies, blocks, enables, serves,
constrains, measures, sets. Nodes and relations preserve reason, confidence,
evidence objects, evidence_node_ids, and source_node_ids.

An optional `condition` is a string, boolean, or an object such as
`{"expression": "purchase growth > sales demand", "status": "unresolved"}`.
Status is active, inactive, or unresolved; an `active` boolean is also accepted.
Expressions are explanatory text, never executable code. A string is unresolved.
The caller supplies observed activation; the backend does not infer satisfaction.

`GET /goal-model/loops?dataset_id=...` analyzes the current canonical snapshot.
Only advances/drives/amplifies (+) and blocks (-) close causal loops. An odd
number of blocks gives Balancing; an even number gives Reinforcing. Unresolved
conditions produce `status=CONDITIONAL`; inactive conditions exclude the edge.
Retired, rejected, retrieval-only and system-derived structural edges are excluded.
Hierarchy remains ownership/decomposition and cannot establish causality.

MCP clients use existing `validate_teleology_goal_model`,
`propose_teleology_goal_model`, and `get_teleology_goal_model`; the new
`get_teleology_goal_network_loops` tool reads loops. Validation returns warnings
for unusual type/relation combinations without banning them. Existing GOAL
blocks semantics and polarity warnings remain compatible.

Validation and dry-run also return `loop_preview` for the resulting proposal
network using the same analyzer. Patch preview includes unchanged current edges
and accepted new/updated edges. Each loop contains nodes, edges,
negative_edge_count, loop_type, conditions, confidence and activation status.
No proposal run is saved by dry-run.

The focused UN V3 regression includes D1 `sets` G6, G5 `drives` D2 (driver),
and D2 `amplifies` R2. It excludes the direct G5 `amplifies` R2 edge and expects
one Reinforcing causal loop between G2 and G6. This fixture is not a copy or
migration of the production snapshot.

All network metadata stays in the existing run JSON payload. SQL candidate reads
hydrate node_type and evidence_node_ids from that payload while retaining SQL
review flags, outside_current_snapshot and legacy_confirmed behavior. No migration
or automatic data rewrite is required. These APIs continue to create derived
proposals; they do not commit the company tree or formal teleology graph.
