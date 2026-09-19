"""Read-only grants for the explicit, operator-approved shared dataset list."""

import os
from uuid import UUID

from sqlalchemy import select

from cognee.infrastructure.databases.relational import get_relational_engine
from cognee.modules.data.models.Dataset import Dataset
from cognee.modules.users.models import OAuthIdentity, User
from cognee.modules.users.permissions.methods.give_permission_on_dataset import (
    give_permission_on_dataset,
)


async def grant_shared_read(user: User) -> int:
    raw = os.getenv("CODEBUDDY_SHARED_DATASET_IDS", "")
    dataset_ids = {UUID(value.strip()) for value in raw.split(",") if value.strip()}
    if not dataset_ids:
        return 0
    async with get_relational_engine().get_async_session() as session:
        datasets = (
            (await session.execute(select(Dataset).where(Dataset.id.in_(dataset_ids))))
            .scalars()
            .all()
        )
        if any(dataset.tenant_id != user.tenant_id for dataset in datasets):
            raise ValueError("CodeBuddy shared datasets must belong to the user's tenant")
        existing_ids = [dataset.id for dataset in datasets]
    # Reuse the existing idempotent ACL grant implementation; never grant write/share/delete.
    for dataset_id in existing_ids:
        await give_permission_on_dataset(user, dataset_id, "read")
    return len(existing_ids)


async def backfill_shared_read() -> int:
    async with get_relational_engine().get_async_session() as session:
        users = (
            (
                await session.execute(
                    select(User)
                    .join(OAuthIdentity, OAuthIdentity.user_id == User.id)
                    .where(OAuthIdentity.provider == "codebuddy", User.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
    for user in users:
        await grant_shared_read(user)
    return len(users)
