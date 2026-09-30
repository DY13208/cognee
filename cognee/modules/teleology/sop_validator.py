"""Validate traceability and structural quality of a proposed SOP."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE = re.compile(
    r"负责人|审批人|责任部门|\d+(?:\.\d+)?\s*(?:%|小时|分钟|天|次|元)|每周|每月|系统|路径|owner|approver|deadline|threshold",
    re.IGNORECASE,
)
_CHECK = re.compile(r"检查|核验|验收|确认|审核|是否|达到|符合|check|verify|accept", re.IGNORECASE)
_PLAN = re.compile(
    r"执行|提交|记录|整理|发送|处理|开展|实施|录入|execute|submit|record", re.IGNORECASE
)


def validate_sop_proposal(
    proposal: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    context = context or {}
    facts = context.get("mindmap_context") or {}
    if isinstance(facts, dict):
        facts = facts.get("facts") or facts.get("nodes") or []
    known_uids = {str(x) for x in context.get("source_uids") or []}
    known_ids = set()
    factual_text = []
    for fact in facts if isinstance(facts, list) else []:
        if isinstance(fact, dict):
            known_uids.update(
                str(fact[key]) for key in ("source_uid", "node_uid", "uid") if fact.get(key)
            )
            known_ids.update(str(x) for x in fact.get("evidence_node_ids") or [])
            factual_text.append(str(fact.get("text") or fact.get("name") or ""))
    for evidence in context.get("related_evidence") or []:
        if isinstance(evidence, dict) and evidence.get("node_id"):
            known_ids.add(str(evidence["node_id"]))
    unsupported = []
    missing = []
    conflicts = []
    missing.extend(
        str(item.get("field"))
        for item in proposal.get("missing_details") or []
        if isinstance(item, dict) and item.get("evidence_status") == "MISSING"
    )
    checks = proposal.get("checks") or []
    plan = proposal.get("plan") or []
    for kind, entries, pattern in (("C", checks, _CHECK), ("P", plan, _PLAN)):
        for item in entries:
            text = str(item.get("text") or "").strip()
            status = item.get("evidence_status")
            refs = [str(x) for x in item.get("source_uids") or []]
            ids = [str(x) for x in item.get("evidence_node_ids") or []]
            label = str(item.get("id") or kind)
            if status == "SOURCE":
                if (
                    not refs
                    and not ids
                    or any(x not in known_uids for x in refs)
                    or any(x not in known_ids for x in ids)
                ):
                    unsupported.append(
                        {"id": label, "reason": "SOURCE 缺少真实的 source/evidence id"}
                    )
                elif not any(text == fact for fact in factual_text):
                    unsupported.append({"id": label, "reason": "SOURCE 文本未被引用事实直接支持"})
            elif status == "DERIVED":
                if not str(item.get("reason") or "").strip():
                    unsupported.append({"id": label, "reason": "DERIVED 缺少推导原因"})
                if (
                    not refs
                    and not ids
                    or any(x not in known_uids for x in refs)
                    or any(x not in known_ids for x in ids)
                ):
                    unsupported.append({"id": label, "reason": "DERIVED 缺少真实事实依据"})
            elif status == "MISSING":
                missing.append(label)
                if (
                    text
                    and _SENSITIVE.search(text)
                    and not re.search(
                        r"待定|缺少|未明确|待确认|missing|unknown", text, re.IGNORECASE
                    )
                ):
                    unsupported.append({"id": label, "reason": "MISSING 内容须明确标注待确认"})
            else:
                unsupported.append({"id": label, "reason": "无效 evidence_status"})
            if _SENSITIVE.search(text) and status != "MISSING" and text not in factual_text:
                unsupported.append(
                    {"id": label, "reason": "负责人、数值或其他操作细节缺少直接事实依据"}
                )
            if not pattern.search(text):
                unsupported.append(
                    {"id": label, "reason": f"{kind} {'不可验收' if kind == 'C' else '不可执行'}"}
                )
    for constraint in context.get("constraints") or proposal.get("constraints") or []:
        name = (
            str(constraint.get("name") or "") if isinstance(constraint, dict) else str(constraint)
        )
        if name.startswith("禁止") and any(
            name[2:] and name[2:] in str(i.get("text") or "") for i in plan
        ):
            conflicts.append({"constraint": name, "reason": "计划包含被禁止的行为"})
    if not checks:
        missing.append("checks")
    if not plan:
        missing.append("plan")
    coverage = {"checks": len(checks), "plan": len(plan), "covered_checks": 0}
    action_prefixes = (
        "检查",
        "核验",
        "验收",
        "确认",
        "审核",
        "记录",
        "执行",
        "提交",
        "整理",
        "处理",
    )

    def subject(value: str) -> str:
        value = value.strip()
        for prefix in action_prefixes:
            if value.startswith(prefix):
                return value[len(prefix) :].strip()
        return value

    for check in checks:
        check_subject = subject(str(check.get("text") or ""))
        if any(check_subject and check_subject in str(step.get("text") or "") for step in plan):
            coverage["covered_checks"] += 1
    if checks and coverage["covered_checks"] < len(checks):
        missing.append("P 未覆盖全部 C")
    sop_conflicts = []
    for existing in context.get("existing_sops") or []:
        if not isinstance(existing, dict):
            continue
        same_goal = str(existing.get("goal_id") or "") == str(
            (proposal.get("goal") or {}).get("id") or ""
        )
        same_scope = str(existing.get("scope") or "") == str(proposal.get("scope") or "")
        if same_goal and same_scope:
            old_steps = {
                str(step.get("text") or "")
                for step in existing.get("plan") or []
                if isinstance(step, dict)
            }
            new_steps = {str(step.get("text") or "") for step in plan}
            if old_steps and new_steps and old_steps != new_steps:
                sop_conflicts.append(
                    {"sop_id": existing.get("id"), "reason": "同目标、同范围的已有 SOP 步骤不同"}
                )
    state = (
        "INSUFFICIENT_EVIDENCE"
        if not checks or not plan or not context.get("primary_goal")
        else "NEEDS_REVIEW"
        if unsupported or missing or conflicts or sop_conflicts
        else "VALID"
    )
    return {
        "status": state,
        "unsupported_claims": unsupported,
        "missing_fields": missing,
        "constraint_conflicts": conflicts,
        "sop_conflicts": sop_conflicts,
        "coverage": coverage,
    }
