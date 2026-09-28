"use client";

import { useState } from "react";
import { commitPurposeProposal, type ProposalItem, type TeleologyProposal } from "@/modules/teleology/teleologyApi";
import type { CogneeInstance } from "@/modules/instances/types";

const KIND: Record<ProposalItem["kind"], [string, string]> = {
  purpose: ["New purpose", "新目的"],
  goal: ["Suggested goal", "建议目标"],
  constraint: ["Constraint", "阻碍"],
  relation: ["Relation", "关系"],
  gap: ["Missing purpose", "缺少明确目的"],
};

export default function PurposeReview({ instance, datasetId, proposal, language, onClose, onCommitted }: {
  instance: CogneeInstance;
  datasetId: string;
  proposal: TeleologyProposal;
  language: "zh" | "en";
  onClose: () => void;
  onCommitted: () => void;
}) {
  const t = (en: string, zh: string) => (language === "zh" ? zh : en);
  const [decisions, setDecisions] = useState<Record<string, "accepted" | "ignored">>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { name: string; description: string; reason: string }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const summary = proposal.summary;

  function draft(item: ProposalItem) {
    return drafts[item.id] || { name: item.name, description: item.description, reason: item.reason };
  }

  async function commit() {
    const accepted = proposal.items.filter((item) => decisions[item.id] === "accepted" && item.kind !== "gap").map((item) => item.id);
    const edits: Record<string, { name: string; description: string; reason: string }> = {};
    for (const id of accepted) {
      if (drafts[id]) edits[id] = drafts[id];
    }
    setBusy(true);
    setError(null);
    try {
      await commitPurposeProposal(instance, datasetId, proposal.id, accepted, edits);
      onCommitted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const chips: [string, number][] = [
    [t("New purposes", "新增 Purpose"), summary.purposes],
    [t("Suggested goals", "建议 Goal"), summary.goals],
    [t("Constraints", "Constraint"), summary.constraints],
    [t("Serves", "serves"), summary.serves],
    [t("Advances", "advances"), summary.advances],
    [t("Blocks", "blocks"), summary.blocks],
  ];

  return <div className="onto-review-backdrop" onMouseDown={onClose}>
    <aside className="onto-review" onMouseDown={(event) => event.stopPropagation()}>
      <header>
        <div>
          <strong>{t("AI analysis", "AI 分析结果")}</strong>
          <small>{proposal.analysis_summary || t("Nothing here is in the formal graph until you confirm.", "确认写入之前，这些都不是正式目的论。")}</small>
        </div>
        <button type="button" onClick={onClose} aria-label={t("Close", "关闭")}>×</button>
      </header>
      <div className="onto-review-counts">{chips.map(([label, count]) => <span key={label}><b>{count}</b>{label}</span>)}</div>
      <div className="onto-review-list">
        {proposal.items.map((item) => {
          const decision = decisions[item.id];
          const current = draft(item);
          return <article key={item.id} className={decision ? `is-${decision}` : ""}>
            <div className="onto-review-kind">{t(...KIND[item.kind])}{item.relationship ? ` · ${item.relationship}` : ""}{item.confidence != null && <em>{Math.round(item.confidence * 100)}%</em>}</div>
            {editing === item.id ? <>
              <input value={current.name} onChange={(event) => setDrafts((old) => ({ ...old, [item.id]: { ...current, name: event.target.value } }))} />
              <textarea value={current.description} onChange={(event) => setDrafts((old) => ({ ...old, [item.id]: { ...current, description: event.target.value } }))} />
            </> : <>
              <h3>{current.name || t("Untitled", "未命名")}</h3>
              {item.kind === "relation" && <p>{item.relationship} · {item.source} → {item.target}</p>}
              {current.reason && <p>{t("Why", "依据")}：{current.reason}</p>}
              {!!item.evidence?.length && <p>{t("Evidence", "证据")}：{item.evidence.map((entry) => entry.name).join("、")}</p>}
            </>}
            <div className="onto-review-actions">
              {item.kind !== "gap" && <>
                <button type="button" className={decision === "accepted" ? "is-on" : ""} onClick={() => setDecisions((old) => ({ ...old, [item.id]: "accepted" }))}>{t("Accept", "接受")}</button>
                <button type="button" onClick={() => { setEditing(editing === item.id ? null : item.id); setDecisions((old) => ({ ...old, [item.id]: "accepted" })); }}>{t("Edit and accept", "编辑后接受")}</button>
              </>}
              <button type="button" className={decision === "ignored" ? "is-on" : ""} onClick={() => setDecisions((old) => ({ ...old, [item.id]: "ignored" }))}>{t("Ignore", "忽略")}</button>
            </div>
          </article>;
        })}
      </div>
      {error && <p className="onto-focus-error">{error}</p>}
      <footer>
        <span>{t("Accepted items are written as inferred teleology. The company tree is not changed.", "接受的内容写入推导层。公司树不会被修改。")}</span>
        <button type="button" className="onto-btn onto-btn-primary" disabled={busy} onClick={() => void commit()}>{busy ? t("Writing…", "写入中…") : t("Confirm write", "确认写入")}</button>
      </footer>
    </aside>
  </div>;
}
