"""Conservative, deterministic SOP proposal generation without writes."""

from __future__ import annotations

import re
from typing import Any

from cognee.modules.teleology.sop_context import _facts

_CHECK = re.compile(r"检查|核验|验收|确认|审核|是否|check|verify|accept", re.IGNORECASE)
_PLAN = re.compile(r"执行|提交|记录|整理|发送|处理|开展|实施|execute|submit|record", re.IGNORECASE)
_SENSITIVE = re.compile(
    r"负责人|审批人|责任部门|小时|分钟|天内|每周|每月|频率|阈值|系统|路径|owner|approver|deadline|threshold",
    re.IGNORECASE,
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def generate_sop_proposal(context: dict[str, Any]) -> dict[str, Any]:
    """Generate only from supplied factual clauses; never invent operational details."""
    goal = context.get("primary_goal") or {}
    source_uids = {str(x) for x in context.get("source_uids") or []}
    checks: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    gaps: list[str] = []
    inputs: list[dict[str, Any]] = []
    for fact in _facts(context.get("mindmap_context")):
        text = str(fact.get("text") or fact.get("name") or "").strip()
        uid = str(fact.get("source_uid") or fact.get("node_uid") or fact.get("uid") or "")
        ids = _unique([str(x) for x in fact.get("evidence_node_ids") or []])
        if not text or (uid not in source_uids and not ids):
            continue
        source = [uid] if uid and uid in source_uids else []
        inputs.append({"text": text, "source_uids": source, "evidence_node_ids": ids})
        bucket = checks if _CHECK.search(text) else plan if _PLAN.search(text) else None
        if bucket is None:
            continue
        if _SENSITIVE.search(text) and not (source or ids):
            gaps.append(text)
            continue
        bucket.append(
            {
                "id": f"{'C' if bucket is checks else 'P'}{len(bucket) + 1}",
                "text": text,
                "evidence_status": "SOURCE",
                "source_uids": source,
                "evidence_node_ids": ids,
                "reason": "直接来自提供的 mind-map 事实。",
                "confidence": 1.0,
            }
        )
    if not checks and goal and inputs and context.get("constraints"):
        constraint = context["constraints"][0]
        name = (
            str(constraint.get("name") or "") if isinstance(constraint, dict) else str(constraint)
        )
        if name:
            checks.append(
                {
                    "id": "C1",
                    "text": f"检查执行结果是否符合约束：{name}",
                    "evidence_status": "DERIVED",
                    "source_uids": inputs[0]["source_uids"],
                    "evidence_node_ids": inputs[0]["evidence_node_ids"],
                    "reason": f"基于事实、目标“{goal.get('name')}”与约束“{name}”推导验收项。",
                    "confidence": 0.5,
                }
            )
    if not checks:
        gaps.append("缺少可验收的检查标准")
    if not plan:
        gaps.append("缺少可执行的计划步骤")
    missing_details = []
    for field in (
        "负责人",
        "审批人",
        "时间要求",
        "数值阈值",
        "系统名称",
        "操作路径",
        "责任部门",
        "频率",
    ):
        if not any(field in item["text"] for item in inputs):
            gaps.append(field)
            missing_details.append(
                {"field": field, "evidence_status": "MISSING", "reason": "输入事实未明确提供"}
            )
    counts = {
        key.lower(): sum(item["evidence_status"] == key for item in checks + plan)
        for key in ("SOURCE", "DERIVED", "MISSING")
    }
    counts["missing"] += len(missing_details)
    return {
        "title": f"{goal.get('name', '待确定目标')} SOP 草案",
        "objective": goal.get("name") or "",
        "scope": context.get("room_key") or "",
        "goal": {"id": goal.get("id"), "name": goal.get("name")} if goal else None,
        "purpose": context.get("purposes") or [],
        "constraints": context.get("constraints") or [],
        "inputs": inputs,
        "checks": checks,
        "plan": plan,
        "gaps": _unique(gaps),
        "missing_details": missing_details,
        "risks": ["尚未找到关联的 current Goal"] if not goal else [],
        "evidence_coverage": counts,
        "overall_confidence": 0.0 if not goal or not checks or not plan else 0.7,
        "status": "proposal",
        "dataset_id": context.get("dataset_id"),
        "run_id": context.get("run_id"),
    }
