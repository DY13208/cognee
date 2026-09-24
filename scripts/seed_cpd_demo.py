"""Seed a small local CPD goal tree + sync teleology purpose edges.

Run inside the cognee container:
  python /tmp/seed_cpd_demo.py
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from cognee.context_global_variables import set_database_global_context_variables
from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.company_tree.schema import CompanyTreeNodeIn, CompanyTreeWriteRequest
from cognee.modules.company_tree.upsert import get_company_tree, upsert_company_tree
from cognee.modules.data.methods import create_authorized_dataset, get_datasets_by_name
from cognee.modules.engine.models import Entity
from cognee.modules.teleology.graph_annotations import sync_from_company_tree
from cognee.modules.users.methods import get_default_user

DATASET_NAME = "cpd_demo"
ROOM = "room-local-demo"
REVISION = "demo-1"


async def ensure_dataset(user):
    existing = await get_datasets_by_name(DATASET_NAME, user.id)
    if existing:
        return existing[0] if isinstance(existing, list) else existing
    return await create_authorized_dataset(DATASET_NAME, user)


async def seed_entities(dataset_id, owner_id):
    """A few knowledge nodes whose names overlap CPD goals → serves edges."""
    async with set_database_global_context_variables(dataset_id, owner_id):
        graph = await get_graph_engine()
        nodes = [
            Entity(
                id=uuid4(),
                name="AHC 检索质量周报",
                description="Hybrid search 周报，服务 AHC 项目目标",
            ),
            Entity(
                id=uuid4(),
                name="NARKA 利润看板",
                description="追踪 NARKA 项目利润分",
            ),
            Entity(
                id=uuid4(),
                name="公司运营例会纪要",
                description="公司运营根目标相关例会",
            ),
        ]
        await graph.add_nodes(nodes)
        return [str(n.id) for n in nodes]


async def main() -> None:
    user = await get_default_user()
    dataset = await ensure_dataset(user)
    dataset_id = dataset.id
    print(f"dataset={dataset.name} id={dataset_id}")

    payload = CompanyTreeWriteRequest(
        source_room=ROOM,
        source_revision=REVISION,
        nodes=[
            CompanyTreeNodeIn(
                source_uid="root",
                name="公司运营",
                cpd_kind="goal",
                source_child_count=2,
                source_note="根目标",
            ),
            CompanyTreeNodeIn(
                source_uid="biz",
                name="公司业务",
                cpd_kind="goal",
                source_parent_uid="root",
                source_child_count=2,
                source_note="业务线",
            ),
            CompanyTreeNodeIn(
                source_uid="profit",
                name="公司利润",
                cpd_kind="goal",
                source_parent_uid="root",
                source_child_count=0,
                source_note="利润目标",
            ),
            CompanyTreeNodeIn(
                source_uid="ahc",
                name="AHC项目",
                cpd_kind="goal",
                source_parent_uid="biz",
                source_child_count=0,
                source_note="AHC 交付与检索质量",
            ),
            CompanyTreeNodeIn(
                source_uid="narka",
                name="NARKA项目",
                cpd_kind="goal",
                source_parent_uid="biz",
                source_child_count=0,
                source_note="NARKA 利润分",
            ),
        ],
    )

    tree = await upsert_company_tree(dataset_id, user, payload)
    print(
        f"cpd_tree goals={len([n for n in tree.nodes if n.kind == 'goal'])} "
        f"edges={len(tree.edges)} complete={tree.complete} root={tree.root_id}"
    )
    for n in tree.nodes:
        print(f"  - [{n.kind}] {n.name} id={n.id}")
    for e in tree.edges:
        print(f"  > {e.label}: {e.source} -> {e.target}")

    entity_ids = await seed_entities(dataset_id, dataset.owner_id)
    print(f"seeded_entities={len(entity_ids)}")

    sync = await sync_from_company_tree(dataset_id, user, link_entities=True)
    print(
        f"teleology sync: tree_goals={sync['tree_goals']} "
        f"advances={sync['advances_created']} serves={sync['serves_created']} "
        f"yaml={sync['yaml_upserted']}"
    )
    print(f"annotations={len(sync.get('annotations') or [])}")
    for a in (sync.get("annotations") or [])[:20]:
        print(
            f"  {a['relationship']}: {a['source_name']} -> {a['target_name']}"
        )

    again = await get_company_tree(dataset_id, user)
    print(f"re-read cpd root={again.root_id} nodes={len(again.nodes)}")
    print("DONE — open Teleology UI, pick dataset cpd_demo, click 从目标树同步 (already done).")


if __name__ == "__main__":
    asyncio.run(main())
