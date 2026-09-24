from cognee.modules.pipelines.tasks.task import task_summary
from cognee.modules.teleology.get_default_teleology_resolver import (
    get_configured_teleology_mode,
    get_configured_teleology_resolver,
)
from cognee.modules.teleology.link_data_points_to_goals import link_data_points_to_goals
from cognee.modules.teleology.teleology_config import Config


@task_summary("Linked knowledge to active goals in {n} chunk(s)")
async def link_to_active_goals(data_points: list, config: Config | None = None, **kwargs) -> list:
    """Post-process extracted data points with active-goal edges; no-op when unconfigured."""
    resolver = get_configured_teleology_resolver(config)
    if resolver is None:
        return data_points
    get_configured_teleology_mode(config)
    active_constraints = [
        constraint for constraint in resolver.get_constraints() if constraint.status == "active"
    ]
    link_data_points_to_goals(data_points, resolver.get_active_goals(), active_constraints)
    return data_points
