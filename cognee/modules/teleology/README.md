# Teleology

Ontology answers **what a thing is** and may canonicalize extracted entities.
Teleology answers **what a knowledge point is for**. It runs afterwards and only
annotates the existing graph with `serves`, `advances`, or `blocks` edges.

Set `TELEOLOGY_FILE_PATH` to a local YAML file and leave `TELEOLOGY_MODE=annotate`
to enable it. `strict` is reserved for a future release and raises an explicit
`NotImplementedError`.

Search can use the persisted goal edges without changing the extraction schema:

```python
await cognee.search("retrieval quality", goal_id=goal_uuid)
await cognee.search("retrieval quality", goal_id=goal_uuid, goal_filter_mode="filter")
await cognee.recall("retrieval quality", goal_id=goal_uuid)
```

`rerank` is the default and stably promotes goal-related results. `filter`
returns only results connected to the selected goal through a teleology edge.
