from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from cognee.api.DTO import OutDTO
from cognee.modules.company_tree.exceptions import CompanyTreeWriteError
from cognee.modules.company_tree.mindmap_mcp import import_linked_mindmaps
from cognee.modules.company_tree.schema import CompanyTreeOut, CompanyTreeWriteRequest
from cognee.modules.company_tree.upsert import (
    get_company_tree,
    reconcile_company_tree,
    upsert_company_tree,
)
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.modules.users.methods import get_authenticated_user
from cognee.modules.users.models import User


class CompanyTreeWriteErrorDTO(OutDTO):
    detail: str
    missing: list[str]


def get_company_tree_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/{dataset_id}/company-tree",
        response_model=CompanyTreeOut,
        responses={404: {"model": dict}},
    )
    async def read_company_tree(
        dataset_id: UUID,
        source_room: str | None = Query(
            default=None,
            description="Mind-map room id. Omit to infer from stamped company-model nodes.",
        ),
        user: User = Depends(get_authenticated_user),
    ):
        """Return the company goal tree for a dataset.

        The backend owns membership, root selection, and completeness. Incomplete
        trees are returned with `complete=false` and `missing`, not as an empty
        payload.
        """
        try:
            return await get_company_tree(dataset_id, user, source_room)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc.message)})

    @router.put(
        "/{dataset_id}/company-tree",
        response_model=CompanyTreeOut,
        responses={
            404: {"model": dict},
            422: {"model": CompanyTreeWriteErrorDTO},
        },
    )
    async def write_company_tree(
        dataset_id: UUID,
        payload: CompanyTreeWriteRequest,
        user: User = Depends(get_authenticated_user),
    ):
        """Upsert the company tree as one validated batch.

        Nodes are merged by `source_key` (`mindmap:{room}:{uid}`). Partial writes
        are rejected unless `allowIncomplete` is true. Requires write permission.
        """
        try:
            return await upsert_company_tree(dataset_id, user, payload)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc.message)})
        except CompanyTreeWriteError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.message, "missing": exc.missing},
            )

    @router.post(
        "/{dataset_id}/company-tree/import-links",
        response_model=CompanyTreeOut,
        responses={
            404: {"model": dict},
            422: {"model": CompanyTreeWriteErrorDTO},
        },
    )
    async def import_company_tree_links(
        dataset_id: UUID,
        user: User = Depends(get_authenticated_user),
    ):
        """Read linked mind maps and write them in as child goals.

        Requires `MINDMAP_MCP_URL` and `MINDMAP_MCP_TOKEN`. A room is imported
        once; a link whose map cannot be read stays a reference.
        """
        try:
            return await import_linked_mindmaps(dataset_id, user)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc.message)})
        except CompanyTreeWriteError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.message, "missing": exc.missing},
            )

    @router.post(
        "/{dataset_id}/company-tree/reconcile",
        response_model=CompanyTreeOut,
        responses={404: {"model": dict}},
    )
    async def reconcile_existing_company_tree(
        dataset_id: UUID,
        source_room: str | None = Query(default=None),
        user: User = Depends(get_authenticated_user),
    ):
        """Stamp existing Goal ancestors that belong to the tree but lack
        company-tree fields. Use this once to repair mixed API writes."""
        try:
            return await reconcile_company_tree(dataset_id, user, source_room)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc.message)})

    return router
