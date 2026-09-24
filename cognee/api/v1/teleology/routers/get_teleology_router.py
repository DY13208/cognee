import asyncio
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Path as PathParam, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import Field

from cognee.api.DTO import InDTO
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

    return router
