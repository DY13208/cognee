import asyncio
from pathlib import Path
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path as PathParam, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import Field

from cognee.api.DTO import InDTO
from cognee.exceptions import CogneeApiError
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.modules.teleology.graph_annotations import (
    add_graph_annotation,
    list_graph_annotations,
    remove_graph_annotation,
    sync_from_company_tree,
    sync_goals_to_graph,
)
from cognee.modules.users.methods import get_authenticated_user
from cognee.modules.users.models import User
from cognee.shared.logging_utils import get_logger

from ..teleology import TeleologyService

logger = get_logger(__name__)

# Bundled with the teleology package (present in Docker images; examples/ is not).
_SAMPLE_PATH = (
    Path(__file__).resolve().parents[4] / "modules" / "teleology" / "sample_goals.yaml"
)

NodeType = Literal["goal", "purpose", "constraint"]
GoalStatusLiteral = Literal["proposed", "active", "achieved", "abandoned"]
TeleologyRelLiteral = Literal["serves", "advances", "blocks"]


class TeleologyNodeCreate(InDTO):
    type: NodeType = Field(..., description="goal | purpose | constraint")
    name: str = Field(..., min_length=1, max_length=200)
    status: GoalStatusLiteral = "proposed"
    description: str = ""
    keywords: List[str] = Field(default_factory=list)


class TeleologyNodeUpdate(InDTO):
    type: Optional[NodeType] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[GoalStatusLiteral] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None


class GraphAnnotationCreate(InDTO):
    dataset_id: UUID = Field(..., description="Dataset whose graph receives the purpose edge.")
    source_id: str = Field(..., min_length=1, description="Knowledge node id (serves/advances/blocks from).")
    target_id: str = Field(..., min_length=1, description="Goal / Purpose / Constraint node id.")
    relationship: TeleologyRelLiteral = Field(
        ...,
        description="Purpose edge: serves, advances, or blocks.",
    )


def get_teleology_router() -> APIRouter:
    router = APIRouter()
    service = TeleologyService()

    @router.get("", response_model=dict)
    async def get_teleology(user: User = Depends(get_authenticated_user)):
        """Return the active teleology YAML status and parsed goals/constraints."""
        _ = user
        return await asyncio.to_thread(service.get_status)

    @router.post("/nodes", response_model=dict)
    async def create_teleology_node(
        payload: TeleologyNodeCreate,
        user: User = Depends(get_authenticated_user),
    ):
        """Create a goal / purpose / constraint via form fields (writes the YAML)."""
        _ = user
        try:
            return await asyncio.to_thread(
                service.create_node,
                payload.type,  # type: ignore[arg-type]
                name=payload.name,
                status=payload.status,
                description=payload.description,
                keywords=payload.keywords,
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Teleology node create failed: %s", exc)
            return JSONResponse(status_code=400, content={"error": f"Invalid teleology node: {exc}"})

    @router.put("/nodes/{node_id}", response_model=dict)
    async def update_teleology_node(
        payload: TeleologyNodeUpdate,
        node_id: str = PathParam(..., description="UUID of the teleology node"),
        user: User = Depends(get_authenticated_user),
    ):
        """Update an existing teleology node."""
        _ = user
        try:
            return await asyncio.to_thread(
                service.update_node,
                node_id,
                kind=payload.type,  # type: ignore[arg-type]
                name=payload.name,
                status=payload.status,
                description=payload.description,
                keywords=payload.keywords,
            )
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Teleology node update failed: %s", exc)
            return JSONResponse(status_code=400, content={"error": f"Invalid teleology node: {exc}"})

    @router.delete("/nodes/{node_id}", response_model=dict)
    async def delete_teleology_node(
        node_id: str = PathParam(..., description="UUID of the teleology node"),
        node_type: Optional[NodeType] = Query(default=None, alias="node_type"),
        user: User = Depends(get_authenticated_user),
    ):
        """Delete a teleology node by id."""
        _ = user
        try:
            return await asyncio.to_thread(
                service.delete_node,
                node_id,
                kind=node_type,  # type: ignore[arg-type]
            )
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.post("", response_model=dict)
    async def upload_teleology(
        teleology_file: UploadFile = File(
            ...,
            description="YAML file with goals / purposes / constraints (see examples/teleology).",
        ),
        user: User = Depends(get_authenticated_user),
    ):
        """Upload (replace) the active teleology YAML used by cognify annotations."""
        _ = user
        filename = teleology_file.filename or "goals.yaml"
        if not filename.lower().endswith((".yaml", ".yml")):
            return JSONResponse(
                status_code=400,
                content={"error": "Teleology file must be .yaml or .yml"},
            )
        content = await teleology_file.read()
        if not content.strip():
            return JSONResponse(status_code=400, content={"error": "Empty teleology file"})
        try:
            return await asyncio.to_thread(service.save_yaml, content, filename)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Teleology upload rejected: %s", exc)
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid teleology YAML: {exc}"},
            )

    @router.post("/sample", response_model=dict)
    async def load_sample_teleology(user: User = Depends(get_authenticated_user)):
        """Install the bundled sample goals YAML as the active teleology file."""
        _ = user
        if not _SAMPLE_PATH.is_file():
            return JSONResponse(
                status_code=404,
                content={"error": "Sample teleology file not found on server"},
            )
        content = _SAMPLE_PATH.read_bytes()
        return await asyncio.to_thread(service.save_yaml, content, "sample_goals.yaml")

    @router.delete("", response_model=dict)
    async def clear_teleology(user: User = Depends(get_authenticated_user)):
        """Remove the active teleology YAML (disables goal annotations until re-uploaded)."""
        _ = user
        return await asyncio.to_thread(service.clear)

    @router.get("/annotations", response_model=dict)
    async def get_graph_annotations(
        dataset_id: UUID = Query(..., description="Dataset to inspect"),
        q: Optional[str] = Query(default=None, description="Filter annotatable nodes by name/type"),
        limit: int = Query(default=200, ge=1, le=1000),
        user: User = Depends(get_authenticated_user),
    ):
        """List purpose edges and annotatable nodes on a dataset knowledge graph."""
        try:
            return await list_graph_annotations(dataset_id, user, q=q, limit=limit)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except CogneeApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("List teleology annotations failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/annotations/sync-goals", response_model=dict)
    async def sync_teleology_goals(
        dataset_id: UUID = Query(..., description="Dataset graph to receive Goal nodes"),
        user: User = Depends(get_authenticated_user),
    ):
        """Upsert YAML goals/purposes/constraints into the dataset graph as nodes."""
        try:
            return await sync_goals_to_graph(dataset_id, user)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sync teleology goals failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/annotations/sync-from-company-tree", response_model=dict)
    async def sync_teleology_from_company_tree(
        dataset_id: UUID = Query(..., description="Dataset that owns the company goal tree"),
        link_entities: bool = Query(
            default=True,
            description="Also attach serves edges from knowledge entities whose names overlap a goal.",
        ),
        source_room: Optional[str] = Query(
            default=None,
            description="Optional mind-map room id; omit to infer from stamped tree nodes.",
        ),
        user: User = Depends(get_authenticated_user),
    ):
        """Derive teleology goals/edges from the company goal tree (+ optional entity links)."""
        try:
            return await sync_from_company_tree(
                dataset_id,
                user,
                link_entities=link_entities,
                source_room=source_room,
            )
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sync teleology from company tree failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/annotations", response_model=dict)
    async def create_graph_annotation(
        payload: GraphAnnotationCreate,
        user: User = Depends(get_authenticated_user),
    ):
        """Attach a serves/advances/blocks edge from a graph node to a goal."""
        try:
            return await add_graph_annotation(
                payload.dataset_id,
                user,
                source_id=payload.source_id,
                target_id=payload.target_id,
                relationship=payload.relationship,
            )
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Create teleology annotation failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.delete("/annotations", response_model=dict)
    async def delete_graph_annotation(
        dataset_id: UUID = Query(...),
        source_id: str = Query(..., min_length=1),
        target_id: str = Query(..., min_length=1),
        relationship: TeleologyRelLiteral = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        """Remove a purpose edge; endpoint nodes are kept."""
        try:
            return await remove_graph_annotation(
                dataset_id,
                user,
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
            )
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Delete teleology annotation failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    return router
