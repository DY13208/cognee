"""Validate traceability and structural quality of a proposed SOP."""

from __future__ import annotations

import re
from typing import Any

from cognee.modules.teleology.sop_sources import (
    MINDMAP_SOURCE_TYPES,
    _strip_plan_prefix,
    extract_factual_atoms,
    normalize_mindmap_text,
)

_SENSITIVE = re.compile(
    r"负责人|审批人|责任部门|\d+(?:\.\d+)?\s*(?:%|小时|分钟|天|次|元)|每周|每月|系统|路径|owner|approver|deadline|threshold",
    re.IGNORECASE,
)
_CHECK = re.compile(
    r"检查|核验|验收|确认|审核|是否|达到|符合|必须|不得|红线|目标值|核对|^C[：:]|check|verify|accept",
    re.IGNORECASE,
)
_PLAN = re.compile(
    r"制定|填写|计算|提交|复核|更新|上传|同步|通知|审批|导出|录入|分析|跟进|"
    r"执行|记录|整理|发送|处理|开展|实施|确认|检查|核对|^P[：:]|execute|submit|record",
    re.IGNORECASE,
)


def _atoms(context: dict[str, Any]) -> list[dict[str, Any]]:
    stored = [
        atom
        for atom in context.get("factual_atoms") or []
        if isinstance(atom, dict)
        and (not atom.get("source_type") or atom.get("source_type") in MINDMAP_SOURCE_TYPES)
    ]
    if stored:
        return stored
    return extract_factual_atoms(
        context.get("mindmap_context"), room_key=str(context.get("room_key") or "")
    )


def _known(context: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    uids: set[str] = set()
    ids: set[str] = set()
    texts: set[str] = set()
    for atom in _atoms(context):
        if atom.get("source_uid"):
            uids.add(str(atom["source_uid"]))
        if atom.get("evidence_node_id"):
            ids.add(str(atom["evidence_node_id"]))
        for key in ("text", "raw_text"):
            if str(atom.get(key) or "").strip():
                texts.add(str(atom.get(key)).strip())
    for ref in context.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        if ref.get("mindmap_uid"):
            uids.add(str(ref["mindmap_uid"]))
        if ref.get("resolution_status") == "EXACT" and ref.get("company_tree_node_id"):
            ids.add(str(ref["company_tree_node_id"]))
    for uid in context.get("source_uids") or []:
        if str(uid).strip():
            uids.add(str(uid))
    for evidence in context.get("related_evidence") or []:
        if isinstance(evidence, dict) and evidence.get("node_id"):
            ids.add(str(evidence["node_id"]))
    return uids, ids, texts


def _id_set(values: Any) -> list[str]:
    return [str(value) for value in values or [] if str(value).strip()]


def _collect_ids(item: dict[str, Any], singular: str, plural: str) -> list[str]:
    values = _id_set(item.get(plural))
    value = str(item.get(singular) or "").strip()
    if value:
        values.append(value)
    return list(dict.fromkeys(values))


def collect_source_uids(item: dict[str, Any]) -> list[str]:
    return _collect_ids(item, "source_uid", "source_uids")


def collect_evidence_node_ids(item: dict[str, Any]) -> list[str]:
    return _collect_ids(item, "evidence_node_id", "evidence_node_ids")


def verify_source_provenance(
    item: dict[str, Any], context: dict[str, Any], known_uids: set[str], known_ids: set[str]
) -> str | None:
    uids = collect_source_uids(item)
    ids = collect_evidence_node_ids(item)
    if not uids and not ids:
        return "SOURCE 缺少真实的 source/evidence id"
    exact_pairs = {
        (str(ref.get("mindmap_uid")), str(ref.get("company_tree_node_id")))
        for ref in context.get("source_refs") or []
        if isinstance(ref, dict)
        and ref.get("resolution_status") == "EXACT"
        and ref.get("mindmap_uid")
        and ref.get("company_tree_node_id")
    }
    if uids and ids:
        if any((uid, node_id) not in exact_pairs for uid in uids for node_id in ids):
            return "SOURCE_PROVENANCE_MISMATCH: SOURCE provenance pair 不一致"
    elif any(uid not in known_uids for uid in uids) or any(
        node_id not in known_ids for node_id in ids
    ):
        return "SOURCE 缺少真实的 source/evidence id"
    return None


def _canonical_source_text(value: Any) -> str:
    normalized = normalize_mindmap_text(str(value or "")).strip()
    return _strip_plan_prefix(normalized)[0]


def _source_text_supported(item: dict[str, Any], context: dict[str, Any]) -> bool:
    expected = _canonical_source_text(item.get("text"))
    if not expected:
        return False
    item_uids = set(collect_source_uids(item))
    ids = set(collect_evidence_node_ids(item))
    mapped_uids = (
        {
            str(ref["mindmap_uid"])
            for ref in context.get("source_refs") or []
            if isinstance(ref, dict)
            and ref.get("resolution_status") == "EXACT"
            and str(ref.get("company_tree_node_id") or "") in ids
            and ref.get("mindmap_uid")
        }
        if ids
        else set()
    )
    for atom in _atoms(context):
        atom_uid = str(atom.get("source_uid") or "")
        atom_id = str(atom.get("evidence_node_id") or "")
        if item_uids and atom_uid not in item_uids:
            continue
        if not item_uids and ids and atom_uid not in mapped_uids and atom_id not in ids:
            continue
        if ids and atom_id and atom_id not in ids:
            continue
        if (
            item.get("provenance")
            and atom.get("provenance")
            and item["provenance"] != atom["provenance"]
        ):
            continue
        factual_text = atom.get("text")
        if not str(factual_text or "").strip():
            factual_text = atom.get("raw_text")
        if _canonical_source_text(factual_text) == expected:
            return True
    return False


def _known_constraint_ids(context: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in context.get("constraints") or []
        if isinstance(item, dict) and item.get("id")
    }


def _known_purpose_ids(context: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in context.get("purposes") or []
        if isinstance(item, dict) and item.get("id")
    }


def _cited_blob(item: dict[str, Any], context: dict[str, Any]) -> str:
    constraint_ids = set(_id_set(item.get("derived_from_constraint_ids")))
    if item.get("derived_from_constraint_id"):
        constraint_ids.add(str(item.get("derived_from_constraint_id")))
    purpose_ids = set(_id_set(item.get("derived_from_purpose_ids")))
    parts: list[str] = []
    for constraint in context.get("constraints") or []:
        if isinstance(constraint, dict) and str(constraint.get("id") or "") in constraint_ids:
            parts.append(str(constraint.get("name") or ""))
            parts.append(str(constraint.get("description") or ""))
    for purpose in context.get("purposes") or []:
        if isinstance(purpose, dict) and str(purpose.get("id") or "") in purpose_ids:
            parts.append(str(purpose.get("name") or ""))
    return "\n".join(parts)


def _sensitive_grounded(text: str, item: dict[str, Any], context: dict[str, Any]) -> bool:
    blob = _cited_blob(item, context)
    return all(match.group(0) in blob for match in _SENSITIVE.finditer(text))


def _derived_pointer_ok(
    item: dict[str, Any],
    *,
    known_uids: set[str],
    known_ids: set[str],
    constraint_ids: set[str],
    purpose_ids: set[str],
) -> bool:
    groups = {
        "derived_from_source_uids": known_uids,
        "source_uids": known_uids,
        "derived_from_evidence_node_ids": known_ids,
        "evidence_node_ids": known_ids,
        "derived_from_constraint_ids": constraint_ids,
        "derived_from_purpose_ids": purpose_ids,
    }
    found = False
    for key, allowed in groups.items():
        values = _id_set(item.get(key))
        if not values:
            continue
        if any(value not in allowed for value in values):
            return False
        found = True
    single = str(item.get("derived_from_constraint_id") or "").strip()
    if single:
        if single not in constraint_ids:
            return False
        found = True
    return found


def _resolution_issues(
    context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    identity: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    resolution = context.get("source_resolution") or {}
    for item in resolution.get("ambiguous") or []:
        if isinstance(item, dict):
            identity.append(
                {
                    "reason": "source identity ambiguity",
                    "mindmap_uid": item.get("mindmap_uid"),
                    "source_key": item.get("source_key"),
                }
            )
    for item in resolution.get("unresolved") or []:
        if isinstance(item, dict) and item.get("cross_room"):
            provenance.append(
                {
                    "reason": "cross-room provenance conflict",
                    "mindmap_uid": item.get("mindmap_uid"),
                    "source_key": item.get("source_key"),
                }
            )
    if context.get("goal_resolution_status") == "AMBIGUOUS":
        provenance.append(
            {"reason": context.get("goal_resolution_reason") or "primary_goal provenance conflict"}
        )
    return identity, provenance


def validate_sop_proposal(
    proposal: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    context = context or {}
    known_uids, known_ids, factual_text = _known(context)
    constraint_ids = _known_constraint_ids(context)
    purpose_ids = _known_purpose_ids(context)
    unsupported: list[dict[str, Any]] = []
    quality_gaps: list[str] = []
    missing = [
        str(item.get("field"))
        for item in proposal.get("missing_details") or []
        if isinstance(item, dict) and item.get("evidence_status") == "MISSING"
    ]
    conflicts: list[dict[str, Any]] = []
    checks = proposal.get("checks") or []
    plan = proposal.get("plan") or []
    for kind, entries, pattern in (("C", checks, _CHECK), ("P", plan, _PLAN)):
        for item in entries:
            text = str(item.get("text") or "").strip()
            status = item.get("evidence_status")
            label = str(item.get("id") or kind)
            if status == "SOURCE":
                provenance_error = verify_source_provenance(item, context, known_uids, known_ids)
                if provenance_error:
                    unsupported.append({"id": label, "reason": provenance_error})
                elif not _source_text_supported(item, context):
                    unsupported.append({"id": label, "reason": "SOURCE 文本未被引用事实直接支持"})
            elif status == "DERIVED":
                if not str(item.get("reason") or "").strip():
                    unsupported.append({"id": label, "reason": "DERIVED 缺少推导原因"})
                if not _derived_pointer_ok(
                    item,
                    known_uids=known_uids,
                    known_ids=known_ids,
                    constraint_ids=constraint_ids,
                    purpose_ids=purpose_ids,
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
            source_grounded = status == "SOURCE" and _source_text_supported(item, context)
            if (
                _SENSITIVE.search(text)
                and status != "MISSING"
                and not source_grounded
                and text not in factual_text
            ):
                grounded = status == "DERIVED" and _sensitive_grounded(text, item, context)
                if not grounded:
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
            name[2:] and name[2:] in str(item.get("text") or "") for item in plan
        ):
            conflicts.append({"constraint": name, "reason": "计划包含被禁止的行为"})
    if not checks:
        quality_gaps.append("缺少可验收的检查标准")
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
        "制定",
        "填写",
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
    identity_issues, provenance_conflicts = _resolution_issues(context)
    if not plan:
        state = "INSUFFICIENT_EVIDENCE"
    elif (
        unsupported
        or missing
        or quality_gaps
        or conflicts
        or sop_conflicts
        or identity_issues
        or provenance_conflicts
    ):
        state = "NEEDS_REVIEW"
    else:
        state = "VALID"
    return {
        "status": state,
        "goal_resolution_status": context.get("goal_resolution_status")
        or proposal.get("goal_resolution_status"),
        "goal_resolution_reason": context.get("goal_resolution_reason")
        or proposal.get("goal_resolution_reason")
        or "",
        "unsupported_claims": unsupported,
        "missing_fields": missing,
        "quality_gaps": quality_gaps,
        "constraint_conflicts": conflicts,
        "sop_conflicts": sop_conflicts,
        "source_identity_issues": identity_issues,
        "provenance_conflicts": provenance_conflicts,
        "coverage": coverage,
    }
