"""LLM adapter for a dataset teleology build.

Production calls these methods through LLMGateway. A missing model fails the
run. Keyword classification is not a fallback.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

_CLASSES = (
    "GoalSignal",
    "Project",
    "Metric",
    "Process",
    "Responsibility",
    "Constraint",
    "Document",
    "Entity",
    "Reference",
    "Other",
)


class _LabeledSource(BaseModel):
    id: str
    semantic_class: str
    classification_reason: str


class _ClassificationBatch(BaseModel):
    items: list[_LabeledSource] = Field(default_factory=list)


class _EvidenceRef(BaseModel):
    node_id: str
    name: str = ""


class _DraftGoal(BaseModel):
    name: str
    description: str = ""
    reason: str
    confidence: float = 0
    source_node_ids: list[str] = Field(default_factory=list)
    evidence: list[_EvidenceRef] = Field(default_factory=list)


class _GoalBatch(BaseModel):
    goals: list[_DraftGoal] = Field(default_factory=list)


class _ParentLink(BaseModel):
    id: str
    parent_candidate_id: str | None = None


class _HierarchyBatch(BaseModel):
    links: list[_ParentLink] = Field(default_factory=list)


_CLASSIFY = (
    "Classify each source. Company-tree membership is provenance, not the class. "
    f"Use only these classes: {', '.join(_CLASSES)}. "
    "A project, metric, responsibility, or document is not itself a goal."
)
_EXTRACT = (
    "Synthesize business goals from the sources. A goal is an outcome, not a copied node. "
    "Combine project, metric, document, entity, process, responsibility, and constraint "
    "evidence. Example: a project plus its profit metric becomes "
    "「提升 <brand> 项目盈利能力」. Every goal needs a name, description, reason, "
    "confidence, and source_node_ids that exist in the input. "
    "Do not emit a goal with no evidence. Do not emit a company-tree node as a goal."
)
_CANONICAL = (
    "Merge goals that name the same business result. Keep every supporting source id. "
    "Do not drop evidence. Do not invent source ids."
)
_HIERARCHY = (
    "Parent a goal only when another goal is the broader business result. "
    "Return links of goal id to parent goal id. "
    "A company-tree parent, directory, or source node id is not a goal parent."
)


class LlmUnavailable(Exception):
    error_code = "llm_unavailable"


class GoalBuildLLM:
    """Production model. Each method is one structured LLMGateway call."""

    async def available(self) -> bool:
        try:
            from cognee.infrastructure.llm.config import get_llm_config

            config = get_llm_config()
        except Exception:  # noqa: BLE001 - missing config means the model is unavailable
            return False
        provider = str(getattr(config, "llm_provider", "") or "").lower()
        if provider in {"ollama", "llama_cpp"}:
            return True
        return bool(getattr(config, "llm_api_key", None))

    async def classify_sources(self, sources: list[dict[str, Any]]) -> list[tuple[str, str]]:
        batch = await self._call(_CLASSIFY, _compact_sources(sources), _ClassificationBatch)
        by_id = {item.id: item for item in batch.items}
        labels: list[tuple[str, str]] = []
        for source in sources:
            item = by_id.get(str(source.get("id") or ""))
            semantic = item.semantic_class if item and item.semantic_class in _CLASSES else "Other"
            reason = (
                item.classification_reason
                if item and item.classification_reason
                else "模型没有给出类别。"
            )
            labels.append((semantic, reason))
        return labels

    async def extract_goals(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        batch = await self._call(_EXTRACT, _compact_sources(sources), _GoalBatch)
        return [goal.model_dump() for goal in batch.goals]

    async def canonicalize_goals(self, goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not goals:
            return []
        batch = await self._call(_CANONICAL, goals, _GoalBatch)
        return [goal.model_dump() for goal in batch.goals]

    async def build_goal_hierarchy(self, goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not goals:
            return []
        brief = [
            {"id": goal.get("id"), "name": goal.get("name"), "description": goal.get("description")}
            for goal in goals
        ]
        batch = await self._call(_HIERARCHY, brief, _HierarchyBatch)
        return [link.model_dump() for link in batch.links]

    async def _call(self, system_prompt: str, payload: Any, response_model: type[BaseModel]) -> Any:
        from cognee.infrastructure.llm.LLMGateway import LLMGateway

        try:
            return await LLMGateway.acreate_structured_output(
                text_input=json.dumps(payload, ensure_ascii=False),
                system_prompt=system_prompt,
                response_model=response_model,
            )
        except Exception as exc:
            raise LlmUnavailable(str(exc)) from exc


def _compact_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in sources:
        rows.append(
            {
                "id": source.get("id"),
                "name": source.get("name"),
                "description": _clip(source.get("description")),
                "note": _clip(source.get("note") or source.get("source_note")),
                "parent_name": source.get("parent_name") or "",
                "ancestor_names": list(source.get("ancestor_names") or [])[:8],
                "child_names": list(
                    source.get("child_names") or source.get("direct_child_names") or []
                )[:20],
                "source_layer": source.get("source_layer") or source.get("layer") or "",
                "semantic_class": source.get("semantic_class") or "",
                "related_documents": list(source.get("related_documents") or [])[:8],
                "related_entities": list(source.get("related_entities") or [])[:8],
                "graph_neighbors": list(source.get("graph_neighbors") or [])[:8],
            }
        )
    return rows


def _clip(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit]
