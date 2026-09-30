"""Conservative, deterministic SOP proposal generation without writes."""

from __future__ import annotations

import re
from typing import Any

from cognee.modules.teleology.sop_sources import (
    MINDMAP_SOURCE_TYPES,
    extract_factual_atoms,
)

_CHECK_MARKERS = re.compile(r"验收标准|检查项|必须满足|目标数值|红线|核对规则|确认条件|验收|核验")
_CHECK_LEAD = re.compile(r"^(?:检查|核验|验收|审核)")
_PLAN_LEAD = re.compile(
    r"^(?:制定|填写|计算|提交|复核|更新|上传|同步|通知|审批|导出|录入|分析|跟进|"
    r"执行|记录|整理|发送|处理|开展|实施|确认)"
)
_MISSING_FIELDS = (
    ("负责人", "当前资料未找到明确责任人"),
    ("审批人", "当前资料未找到明确审批人"),
    ("时间要求", "当前资料未找到明确时间要求"),
    ("数值阈值", "当前资料未找到明确数值阈值"),
    ("系统名称", "当前资料未找到明确系统名称"),
    ("操作路径", "当前资料未找到明确操作路径"),
    ("责任部门", "当前资料未找到明确责任部门"),
    ("频率", "当前资料未找到明确频率"),
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _mindmap_atoms(context: dict[str, Any]) -> list[dict[str, Any]]:
    atoms = [
        atom
        for atom in context.get("factual_atoms") or []
        if atom.get("source_type") in MINDMAP_SOURCE_TYPES and str(atom.get("text") or "").strip()
    ]
    if atoms:
        return atoms
    return [
        atom
        for atom in extract_factual_atoms(
            context.get("mindmap_context"), room_key=str(context.get("room_key") or "")
        )
        if str(atom.get("text") or "").strip()
    ]


def _traceable(atom: dict[str, Any]) -> bool:
    return bool(str(atom.get("source_uid") or "").strip() or atom.get("evidence_node_id"))


def _kind(atom: dict[str, Any]) -> str | None:
    text = str(atom.get("text") or "").strip()
    if not text:
        return None
    if atom.get("explicit_plan"):
        return "plan"
    if _CHECK_MARKERS.search(text) or _CHECK_LEAD.search(text):
        return "check"
    if _PLAN_LEAD.search(text):
        return "plan"
    return None


def _source_item(kind: str, index: int, atom: dict[str, Any], reason: str) -> dict[str, Any]:
    uid = str(atom.get("source_uid") or "").strip()
    evidence_id = str(atom.get("evidence_node_id") or "").strip()
    return {
        "id": f"{'C' if kind == 'check' else 'P'}{index}",
        "text": str(atom.get("text") or "").strip(),
        "evidence_status": "SOURCE",
        "source_uids": [uid] if uid else [],
        "evidence_node_ids": [evidence_id] if evidence_id else [],
        "source_type": atom.get("source_type"),
        "reason": reason,
        "confidence": float(atom.get("confidence") or 1.0),
        "room_key": atom.get("room_key") or "",
        "path": list(atom.get("path") or []),
    }


def _derive_check_text(name: str) -> str:
    text = name.strip()
    if text.startswith("禁止"):
        body = text[2:].strip()
        for token in ("：", ":", " "):
            body = body.removeprefix(token)
        body = body.strip()
        return f"确认未发生被禁止的行为：{body or text}"
    for marker in ("不可修改", "不得修改", "不能修改"):
        if marker in text:
            subject = text.split(marker, 1)[0].strip()
            for token in ("，", ",", "：", ":", " "):
                subject = subject.removesuffix(token)
            subject = subject.strip() or "该目标"
            return f"确认{subject}在确定后未被随意修改"
    if text.startswith("必须"):
        return f"确认满足约束：{text}"
    return f"确认执行结果符合约束：{text}"


def _derived_check(index: int, constraint: dict[str, Any]) -> dict[str, Any] | None:
    name = str(constraint.get("name") or constraint.get("text") or "").strip()
    constraint_id = str(constraint.get("id") or "").strip()
    if not name or not constraint_id:
        return None
    return {
        "id": f"C{index}",
        "text": _derive_check_text(name),
        "evidence_status": "DERIVED",
        "source_uids": [],
        "evidence_node_ids": [],
        "derived_from_constraint_id": constraint_id,
        "derived_from_constraint_ids": [constraint_id],
        "reason": f"由约束“{name}”推导验收项；约束本身不是执行步骤。",
        "confidence": 0.5,
    }


def _input_item(atom: dict[str, Any]) -> dict[str, Any]:
    uid = str(atom.get("source_uid") or "").strip()
    evidence_id = str(atom.get("evidence_node_id") or "").strip()
    return {
        "text": str(atom.get("text") or "").strip(),
        "evidence_status": "SOURCE",
        "source_type": atom.get("source_type"),
        "source_uids": [uid] if uid else [],
        "evidence_node_ids": [evidence_id] if evidence_id else [],
        "provenance": atom.get("provenance") or "",
    }


def generate_sop_proposal(context: dict[str, Any]) -> dict[str, Any]:
    """Generate C/P only from supplied facts. Missing metadata does not erase them."""
    goal = context.get("primary_goal") or {}
    checks: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    seen_checks: set[str] = set()
    seen_plan: set[str] = set()
    for atom in _mindmap_atoms(context):
        if atom.get("source_type") in {"REFERENCE", "ATTACHMENT"} and _traceable(atom):
            inputs.append(_input_item(atom))
        kind = _kind(atom)
        if kind is None or not _traceable(atom):
            continue
        text = str(atom.get("text") or "").strip()
        if kind == "check" and text not in seen_checks:
            seen_checks.add(text)
            reason = "资料中明确写有验收或检查要求。"
            checks.append(_source_item("check", len(checks) + 1, atom, reason))
        elif kind == "plan" and text not in seen_plan:
            seen_plan.add(text)
            reason = (
                "节点名称明确以执行计划标记开头。"
                if atom.get("explicit_plan")
                else "节点内容是明确的执行动作。"
            )
            plan.append(_source_item("plan", len(plan) + 1, atom, reason))
    if not any(item["evidence_status"] == "SOURCE" for item in checks) and plan:
        for constraint in context.get("constraints") or []:
            if not isinstance(constraint, dict):
                continue
            derived = _derived_check(len(checks) + 1, constraint)
            if derived is not None:
                checks.append(derived)
    corpus = "\n".join(
        str(atom.get("text") or "") + "\n" + str(atom.get("raw_text") or "")
        for atom in _mindmap_atoms(context)
    )
    gaps: list[str] = []
    missing_details: list[dict[str, Any]] = []
    for field, reason in _MISSING_FIELDS:
        if field in corpus:
            continue
        gaps.append(field)
        missing_details.append({"field": field, "evidence_status": "MISSING", "reason": reason})
    if not checks:
        gaps.append("缺少可验收的检查标准")
    if not plan:
        gaps.append("缺少可执行的计划步骤")
    counts = {
        key.lower(): sum(item["evidence_status"] == key for item in checks + plan)
        for key in ("SOURCE", "DERIVED", "MISSING")
    }
    counts["missing"] += len(missing_details)
    source_count = counts["source"]
    if not checks and not plan:
        confidence = 0.0
    elif source_count and goal:
        confidence = 0.75
    elif source_count:
        confidence = 0.55
    else:
        confidence = 0.45
    reason = str(context.get("goal_resolution_reason") or "")
    risks = [reason] if not goal and reason else ([] if goal else ["尚未找到关联的 current Goal"])
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
        "risks": risks,
        "evidence_coverage": counts,
        "overall_confidence": confidence,
        "status": "proposal",
        "dataset_id": context.get("dataset_id"),
        "run_id": context.get("run_id"),
    }
