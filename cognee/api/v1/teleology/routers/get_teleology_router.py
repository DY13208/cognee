import asyncio
from pathlib import Path
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import Field

from cognee.api.DTO import InDTO
from cognee.exceptions import CogneeApiError
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.modules.teleology.coverage_service import (
    CoverageServiceError,
    cancel_coverage,
    coverage_items,
    coverage_run,
    coverage_state,
    pause_coverage,
    resume_coverage,
    retry_coverage_failures,
    start_coverage,
)
from cognee.modules.teleology.goal_build import (
    get_build_status,
    read_goal_model,
    review_goal_candidate,
    review_teleology_item,
    start_teleology_build,
)
from cognee.modules.teleology.goal_model import GoalBuildError
from cognee.modules.teleology.goal_orchestrated import submit_orchestrated_goal_model
from cognee.modules.teleology.goal_workspace import (
    create_goal as create_workspace_goal,
)
from cognee.modules.teleology.goal_workspace import (
    delete_goal as delete_workspace_goal,
)
from cognee.modules.teleology.goal_workspace import (
    goal_detail,
    goal_path,
    goal_relations,
)
from cognee.modules.teleology.goal_workspace import (
    move_goal as move_workspace_goal,
)
from cognee.modules.teleology.goal_workspace import (
    update_goal as update_workspace_goal,
)
from cognee.modules.teleology.graph_annotations import (
    _authorized_dataset,
    add_graph_annotation,
    list_graph_annotations,
    remove_graph_annotation,
    sync_from_company_tree,
    sync_goals_to_graph,
)
from cognee.modules.teleology.proposal_review import get_proposal, list_proposals
from cognee.modules.teleology.run_commit import commit_coverage_run
from cognee.modules.teleology.purpose_analyze import analyze_goal
from cognee.modules.teleology.purpose_layer import (
    ProposalCommitIncomplete,
    ProposalStaleError,
    commit_teleology_proposal,
    get_purpose_context,
    propose_teleology,
    start_purpose_review,
)
from cognee.modules.users.methods import get_authenticated_user
from cognee.modules.users.models import User
from cognee.shared.logging_utils import get_logger

from ..teleology import TeleologyService

logger = get_logger(__name__)


def _optional_query(value: Optional[str]) -> Optional[str]:
    return value.strip() or None if value is not None else None


# Bundled with the teleology package (present in Docker images; examples/ is not).
_SAMPLE_PATH = Path(__file__).resolve().parents[4] / "modules" / "teleology" / "sample_goals.yaml"

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
    source_id: str = Field(
        ..., min_length=1, description="Knowledge node id (serves/advances/blocks from)."
    )
    target_id: str = Field(..., min_length=1, description="Goal / Purpose / Constraint node id.")
    relationship: TeleologyRelLiteral = Field(
        ...,
        description="Purpose edge: serves, advances, or blocks.",
    )


class WorkspaceGoalCreate(InDTO):
    dataset_id: UUID
    parent_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    owner: Optional[str] = None


class WorkspaceGoalUpdate(InDTO):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    owner: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    status: Optional[GoalStatusLiteral] = None
    primary_purpose_id: Optional[str] = None
    primary_purpose_relation: Optional[Literal["serves", "advances"]] = None


class WorkspaceGoalMove(InDTO):
    parent_id: str = Field(min_length=1)


class PurposeAnalyzeRequest(InDTO):
    dataset_id: UUID
    goal_id: str = Field(min_length=1)


class PurposeProposalCreate(InDTO):
    dataset_id: UUID
    source_goal_id: str = Field(min_length=1)
    proposal: dict = Field(default_factory=dict)
    generated_by: Optional[str] = None


class CoverageRunCreate(InDTO):
    dataset_id: UUID
    mode: Literal["baseline", "incremental", "force"] = "incremental"
    batch_size: int = Field(default=20, ge=1, le=100)
    concurrency: int = Field(default=3, ge=1, le=5)
    max_goals: Optional[int] = Field(default=None, ge=1)
    token_budget: Optional[int] = Field(default=None, ge=1)


class PurposeProposalCommit(InDTO):
    dataset_id: UUID
    accepted_item_ids: List[str] = Field(default_factory=list)
    edits: Optional[dict] = None


class TeleologyBuildCreate(InDTO):
    dataset_id: UUID
    mode: Literal["baseline", "incremental"] = "baseline"
    batch_size: int = Field(default=20, ge=1, le=100)
    concurrency: int = Field(default=1, ge=1, le=5)
    max_sources: Optional[int] = Field(default=None, ge=1)


class GoalCandidateReview(InDTO):
    dataset_id: UUID
    status: Literal["proposed", "confirmed", "rejected"]


class GoalTeleologyReview(InDTO):
    dataset_id: UUID
    kind: Literal["purpose", "constraint", "relation"]
    status: Literal["proposed", "confirmed", "rejected"]


class OrchestratedEvidenceIn(InDTO):
    node_id: str = ""
    name: str = ""
    source_layer: str = ""
    semantic_class: str = ""
    text: str = ""
    reason: str = ""


class OrchestratedGoalIn(InDTO):
    client_id: str = ""
    name: str = ""
    description: str = ""
    reason: str = ""
    confidence: Optional[float] = None
    business_object: str = ""
    scope: str = ""
    source_node_ids: List[str] = Field(default_factory=list)
    evidence_node_ids: List[str] = Field(default_factory=list)
    evidence: List[OrchestratedEvidenceIn] = Field(default_factory=list)


class OrchestratedHierarchyIn(InDTO):
    parent_client_id: str = ""
    child_client_id: str = ""
    reason: str = ""
    confidence: Optional[float] = None
    evidence_node_ids: List[str] = Field(default_factory=list)
    relationship: Optional[str] = None
    origin: Optional[str] = None


class OrchestratedEndpointIn(InDTO):
    client_id: str = ""
    goal_client_id: str = ""
    name: str = ""
    reason: str = ""
    confidence: Optional[float] = None
    source_node_ids: List[str] = Field(default_factory=list)
    evidence_node_ids: List[str] = Field(default_factory=list)
    evidence: List[OrchestratedEvidenceIn] = Field(default_factory=list)


class OrchestratedRelationIn(InDTO):
    client_id: str = ""
    source_client_id: str = ""
    target_client_id: str = ""
    relationship: str = ""
    reason: str = ""
    confidence: Optional[float] = None
    source_node_ids: List[str] = Field(default_factory=list)
    evidence_node_ids: List[str] = Field(default_factory=list)
    evidence: List[OrchestratedEvidenceIn] = Field(default_factory=list)


class OrchestratedGoalModelProposal(InDTO):
    dataset_id: UUID
    generated_by: str = "workbuddy_orchestrated"
    dry_run: bool = False
    strict: bool = True
    submission_mode: Literal["replace", "merge"] = "replace"
    goals: List[OrchestratedGoalIn] = Field(default_factory=list)
    hierarchy: List[OrchestratedHierarchyIn] = Field(default_factory=list)
    purposes: List[OrchestratedEndpointIn] = Field(default_factory=list)
    constraints: List[OrchestratedEndpointIn] = Field(default_factory=list)
    relations: List[OrchestratedRelationIn] = Field(default_factory=list)


class CoverageRunCommit(InDTO):
    dataset_id: UUID
    dry_run: bool = False


def get_teleology_router() -> APIRouter:
    router = APIRouter()
    service = TeleologyService()

    @router.get("", response_model=dict)
    async def get_teleology(
        q: Optional[str] = Query(default=None, description="Filter YAML vocab by name"),
        limit: int = Query(default=80, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_authenticated_user),
    ):
        """Return the active teleology YAML status (paginated — never dumps 10k rows)."""
        _ = user
        return await asyncio.to_thread(lambda: service.get_status(q=q, limit=limit, offset=offset))

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
            return JSONResponse(
                status_code=400, content={"error": f"Invalid teleology node: {exc}"}
            )

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
            return JSONResponse(
                status_code=400, content={"error": f"Invalid teleology node: {exc}"}
            )

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
        goals_limit: int = Query(
            default=120,
            ge=0,
            le=500,
            description="Max Goal/Purpose/Constraint rows to return (0 = count only). Large CPD trees exceed this.",
        ),
        goals_offset: int = Query(
            default=0,
            ge=0,
            description="Skip this many goals before applying goals_limit (load-more / pagination).",
        ),
        goal_id: Optional[str] = Query(
            default=None,
            description="If set, only return that goal's 1-hop purpose neighbourhood.",
        ),
        parent_id: Optional[str] = Query(
            default=None,
            description=(
                "Purpose-picker tree browse: '_roots' for top-level goals, "
                "or a goal id for its direct has_subgoal children."
            ),
        ),
        user: User = Depends(get_authenticated_user),
    ):
        """List purpose edges and annotatable nodes on a dataset knowledge graph."""
        try:
            return await list_graph_annotations(
                dataset_id,
                user,
                q=q,
                limit=limit,
                goals_limit=goals_limit,
                goals_offset=goals_offset,
                goal_id=goal_id,
                parent_id=parent_id,
            )
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except CogneeApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("List teleology annotations failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.get("/annotations/goals/{goal_id}/path", response_model=dict)
    async def read_goal_path(
        goal_id: str,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        """Return one bounded root-to-goal chain without loading siblings."""
        try:
            return await goal_path(dataset_id, user, goal_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"error": str(exc)})

    @router.get("/annotations/goals/{goal_id}/detail", response_model=dict)
    async def read_goal_detail(
        goal_id: str,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await goal_detail(dataset_id, user, goal_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.get("/annotations/goals/{goal_id}/relations", response_model=dict)
    async def read_goal_relations(
        goal_id: str,
        dataset_id: UUID = Query(...),
        relationship: Optional[TeleologyRelLiteral] = Query(default=None),
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await goal_relations(
                dataset_id, user, goal_id, relationship=relationship, limit=limit, offset=offset
            )
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.post("/annotations/goals", response_model=dict)
    async def create_goal_in_workspace(
        payload: WorkspaceGoalCreate,
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await create_workspace_goal(
                payload.dataset_id,
                user,
                parent_id=payload.parent_id,
                name=payload.name,
                description=payload.description,
                owner=payload.owner,
            )
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.patch("/annotations/goals/{goal_id}", response_model=dict)
    async def edit_goal_in_workspace(
        goal_id: str,
        payload: WorkspaceGoalUpdate,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await update_workspace_goal(
                dataset_id, user, goal_id, **payload.model_dump(exclude_unset=True)
            )
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"error": str(exc)})

    @router.post("/annotations/goals/{goal_id}/move", response_model=dict)
    async def move_goal_in_workspace(
        goal_id: str,
        payload: WorkspaceGoalMove,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await move_workspace_goal(dataset_id, user, goal_id, payload.parent_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"error": str(exc)})

    @router.delete("/annotations/goals/{goal_id}", response_model=dict)
    async def delete_goal_in_workspace(
        goal_id: str,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await delete_workspace_goal(dataset_id, user, goal_id)
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"error": str(exc)})

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
            default=False,
            description="Optional name-overlap serves edges. They are system_derived, not purpose analysis.",
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

    @router.get("/annotations/goals/{goal_id}/purpose-context", response_model=dict)
    async def read_purpose_context(
        goal_id: str,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        """Bounded context for one company-tree goal. Does not return the whole tree."""
        try:
            return await get_purpose_context(dataset_id, user, goal_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.post("/annotations/goals/{goal_id}/purpose-review", response_model=dict)
    async def open_purpose_review(
        goal_id: str,
        dataset_id: UUID = Query(...),
        user: User = Depends(get_authenticated_user),
    ):
        """Record which goals lack a confirmed purpose. Does not invent purpose text."""
        try:
            return await start_purpose_review(dataset_id, user, goal_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/annotations/purpose-proposals", response_model=dict)
    async def create_purpose_proposal(
        payload: PurposeProposalCreate,
        user: User = Depends(get_authenticated_user),
    ):
        """Store an AI candidate. It stays out of the formal graph until commit."""
        try:
            from cognee.modules.teleology.proposal_rules import normalize_generated_by

            return await propose_teleology(
                payload.dataset_id,
                user,
                source_goal_id=payload.source_goal_id,
                proposal=payload.proposal,
                generated_by=normalize_generated_by(payload.generated_by, external=True),
            )
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @router.post("/annotations/purpose-proposals/{proposal_id}/commit", response_model=dict)
    async def commit_purpose_proposal(
        proposal_id: str,
        payload: PurposeProposalCommit,
        user: User = Depends(get_authenticated_user),
    ):
        """Write only the accepted items, with ai_inferred provenance."""
        try:
            return await commit_teleology_proposal(
                payload.dataset_id,
                user,
                proposal_id,
                payload.accepted_item_ids,
                edits=payload.edits,
            )
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except ProposalStaleError:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "proposal_stale",
                    "message": "目标上下文已变化，请重新分析后再确认。",
                },
            )
        except ProposalCommitIncomplete as exc:
            return JSONResponse(
                status_code=409,
                content={"error": str(exc), "code": "commit_incomplete"},
            )

    @router.post("/analyze", response_model=dict)
    async def analyze_purpose(
        payload: PurposeAnalyzeRequest,
        user: User = Depends(get_authenticated_user),
    ):
        """Analyze one goal with the configured model and store a proposal."""
        try:
            return await analyze_goal(payload.dataset_id, user, payload.goal_id)
        except (DatasetNotFoundError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Purpose analysis failed: %s", exc, exc_info=True)
            return JSONResponse(status_code=502, content={"error": str(exc)})

    @router.get("/proposals", response_model=dict)
    async def list_teleology_proposals(
        dataset_id: UUID,
        run_id: Optional[str] = None,
        source_goal_id: Optional[str] = None,
        status: Optional[str] = None,
        generated_by: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_authenticated_user),
    ):
        await _authorized_dataset(dataset_id, user, "read")
        return await list_proposals(
            dataset_id,
            run_id=_optional_query(run_id),
            source_goal_id=_optional_query(source_goal_id),
            status=_optional_query(status),
            generated_by=_optional_query(generated_by),
            limit=limit,
            offset=offset,
        )

    @router.get("/proposals/{proposal_id}", response_model=dict)
    async def get_teleology_proposal(
        proposal_id: str,
        dataset_id: UUID,
        user: User = Depends(get_authenticated_user),
    ):
        await _authorized_dataset(dataset_id, user, "read")
        proposal = await get_proposal(dataset_id, proposal_id)
        if proposal is None:
            return JSONResponse(status_code=404, content={"error": "Proposal not found."})
        return proposal

    @router.get("/coverage/runs/{run_id}/items", response_model=dict)
    async def get_coverage_run_items(
        run_id: str,
        status: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_authenticated_user),
    ):
        try:
            return await coverage_items(
                run_id, user, status=_optional_query(status), limit=limit, offset=offset
            )
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/coverage/runs/{run_id}/commit-all", response_model=dict)
    async def commit_all_coverage_proposals(
        run_id: str,
        payload: CoverageRunCommit,
        user: User = Depends(get_authenticated_user),
    ):
        """Preview or confirm all valid formal items for one reviewed Coverage Run."""
        try:
            return await commit_coverage_run(
                run_id, payload.dataset_id, user, dry_run=payload.dry_run
            )
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.post("/coverage/runs", response_model=dict)
    async def start_coverage_run(
        payload: CoverageRunCreate,
        user: User = Depends(get_authenticated_user),
    ):
        """Queue a coverage run. It creates proposals and never commits them."""
        try:
            return await start_coverage(
                payload.dataset_id,
                user,
                mode=payload.mode,
                batch_size=payload.batch_size,
                concurrency=payload.concurrency,
                max_goals=payload.max_goals,
                token_budget=payload.token_budget,
            )
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.get("/coverage/runs/{run_id}", response_model=dict)
    async def get_coverage_run(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        del user
        try:
            return await coverage_run(run_id)
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/coverage/runs/{run_id}/pause", response_model=dict)
    async def pause_coverage_run(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        del user
        try:
            return await pause_coverage(run_id)
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/coverage/runs/{run_id}/resume", response_model=dict)
    async def resume_coverage_run(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        try:
            current = await coverage_run(run_id)
            return await resume_coverage(run_id, UUID(str(current["dataset_id"])), user)
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/coverage/runs/{run_id}/cancel", response_model=dict)
    async def cancel_coverage_run(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        del user
        try:
            return await cancel_coverage(run_id)
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/coverage/runs/{run_id}/retry-failures", response_model=dict)
    async def retry_coverage_run(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        try:
            current = await coverage_run(run_id)
            return await retry_coverage_failures(run_id, UUID(str(current["dataset_id"])), user)
        except CoverageServiceError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.get("/coverage/state", response_model=dict)
    async def get_coverage_state(
        dataset_id: UUID,
        status: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: User = Depends(get_authenticated_user),
    ):
        del user
        return await coverage_state(dataset_id, status=status, limit=limit, offset=offset)

    @router.post("/builds", response_model=dict)
    async def start_dataset_teleology_build(
        payload: TeleologyBuildCreate,
        user: User = Depends(get_authenticated_user),
    ):
        """Queue a goal build. The response is pending; the run continues in the background."""
        try:
            return await start_teleology_build(
                payload.dataset_id,
                user,
                mode=payload.mode,
                batch_size=payload.batch_size,
                concurrency=payload.concurrency,
                max_sources=payload.max_sources,
            )
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.get("/builds/{run_id}", response_model=dict)
    async def get_dataset_teleology_build(
        run_id: str,
        user: User = Depends(get_authenticated_user),
    ):
        """Read one goal build. The run stays in the database after the client disconnects."""
        try:
            return await get_build_status(run_id, user)
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/goal-model/proposals", response_model=dict)
    async def propose_orchestrated_goal_model(
        payload: OrchestratedGoalModelProposal,
        user: User = Depends(get_authenticated_user),
    ):
        """Store a WorkBuddy analysis as proposals. Nothing is confirmed or committed."""
        try:
            return await submit_orchestrated_goal_model(
                payload.dataset_id,
                user,
                payload.model_dump(),
            )
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})
        except DatasetNotFoundError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})

    @router.get("/goal-model", response_model=dict)
    async def get_ai_goal_model(
        dataset_id: UUID,
        user: User = Depends(get_authenticated_user),
    ):
        """Read the derived AI Goal Model. Company-tree nodes stay in the evidence."""
        try:
            return await read_goal_model(dataset_id, user)
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/goal-model/candidates/{candidate_id}/review", response_model=dict)
    async def review_ai_goal_candidate(
        candidate_id: str,
        payload: GoalCandidateReview,
        user: User = Depends(get_authenticated_user),
    ):
        """Accept or reject one derived goal. This does not commit the graph."""
        await _authorized_dataset(payload.dataset_id, user, "write")
        try:
            return await review_goal_candidate(payload.dataset_id, candidate_id, payload.status)
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @router.post("/goal-model/items/{item_id}/review", response_model=dict)
    async def review_ai_goal_teleology(
        item_id: str,
        payload: GoalTeleologyReview,
        user: User = Depends(get_authenticated_user),
    ):
        """Accept or reject one purpose, constraint, or relation proposal."""
        await _authorized_dataset(payload.dataset_id, user, "write")
        try:
            return await review_teleology_item(
                payload.dataset_id, item_id, payload.status, payload.kind
            )
        except GoalBuildError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    return router
