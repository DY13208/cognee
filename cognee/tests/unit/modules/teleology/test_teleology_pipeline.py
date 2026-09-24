import pytest

from cognee.api.v1.cognify.cognify import get_default_tasks


@pytest.mark.asyncio
async def test_teleology_task_runs_between_extraction_and_storage() -> None:
    tasks = await get_default_tasks(
        chunk_size=128,
        config={"ontology_config": {}, "teleology_config": {}},
    )
    task_names = [task.executable.__name__ for task in tasks]

    assert (
        task_names.index("extract_graph_and_summarize")
        < task_names.index("link_to_active_goals")
        < task_names.index("add_data_points")
    )
