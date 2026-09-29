"use client";

import type { GraphNodeSummary, ProposalItem, TeleologyProposal } from "@/modules/teleology/teleologyApi";
import type { OntologyEdge } from "./types";

const RELATIONS = ["serves", "advances", "blocks"] as const;
const LABELS = { serves: ["Serves", "服务于"], advances: ["Advances", "推进"], blocks: ["Blocks", "阻碍"] };

/** The fixed focus view is a selected-node detail, never a stand-in for the canvas. */
export function shouldShowFocusDetail(selectedId: string | null | undefined): boolean {
  return Boolean(selectedId);
}

export default function TeleologyFocusMap({ goal, purposes, constraints, relations, confirmedRelationCounts, proposal, subgoals, childTotal, language, loading, variant = "page", onSelectProposal, onSelectGoal, onAnalyze, onReviewProposal, onShowChildren }: {
  goal: GraphNodeSummary;
  purposes: GraphNodeSummary[];
  constraints: GraphNodeSummary[];
  relations: OntologyEdge[];
  confirmedRelationCounts?: { serves: number; advances: number; blocks: number };
  proposal: TeleologyProposal | null;
  subgoals: GraphNodeSummary[];
  childTotal: number;
  language: "zh" | "en";
  loading?: boolean;
  variant?: "page" | "detail";
  onSelectProposal: (item: ProposalItem) => void;
  onSelectGoal: (id: string) => void;
  onAnalyze?: () => void;
  onReviewProposal?: () => void;
  onShowChildren?: () => void;
}) {
  const t = (en: string, zh: string) => language === "zh" ? zh : en;
  const candidates = (proposal?.items || []).filter((item) => item.status !== "ignored");
  const proposedPurpose = candidates.filter((item) => item.kind === "purpose");
  const proposedConstraint = candidates.filter((item) => item.kind === "constraint");
  const proposedGoal = candidates.filter((item) => item.kind === "goal");
  const proposedRelations = candidates.filter((item) => item.kind === "relation" && RELATIONS.includes(item.relationship as typeof RELATIONS[number]));
  const hasRelation = relations.length > 0 || proposedRelations.length > 0 || Object.values(confirmedRelationCounts || {}).some((count) => count > 0);

  return <div className={`teleology-focus-map${variant === "detail" ? " is-detail" : ""}`}>
    <section className="teleology-focus-lane">
      <div className="onto-lane-caption">WHY · {purposes.length ? t("Confirmed purpose", "已确认目的") : proposedPurpose.length ? t("Purpose suggestions awaiting review", "待确认的目的建议") : t("Purpose", "目的")}</div>
      <div className="teleology-focus-cards">
        {purposes.map((item) => <div className="teleology-semantic-card is-confirmed" key={item.id}><small>{t("Confirmed", "已确认")}</small><strong>{item.name}</strong></div>)}
        {proposedPurpose.map((item) => <button type="button" className="teleology-semantic-card is-proposed" key={item.id} onClick={() => onSelectProposal(item)}><small>{t("AI suggestion", "AI建议")}</small><strong>{item.name}</strong><span>{item.confidence != null ? `${Math.round(item.confidence * 100)}% · ` : ""}{(item.evidence || item.evidence_node_ids || []).length} {t("evidence", "条证据")}</span></button>)}
        {!purposes.length && !proposedPurpose.length && <div className="teleology-focus-empty">{t("No purpose inference yet", "尚无目的推断")}</div>}
      </div>
    </section>

    <section className="teleology-focus-center">
      <div className={`teleology-current-goal${loading ? " is-loading" : ""}`}><small>{t("Current goal · Company Tree fact", "当前目标 · Company Tree 事实")}</small><strong>{goal.name}</strong>{goal.description && <p>{goal.description}</p>}</div>
      {!hasRelation && <div className="teleology-relation-empty"><strong>{t("No confirmed purpose relation", "暂无已确认的目的关系")}</strong><span>{candidates.length ? t(`${candidates.length} AI suggestions await review`, `有 ${candidates.length} 条 AI 建议待确认`) : proposal ? t("Analyzed · insufficient evidence", "已分析 · 暂无充分证据") : t("This goal may not have been analyzed yet.", "该目标可能尚未分析。")}</span>{candidates.length > 0 && onReviewProposal && <button type="button" onClick={onReviewProposal}>{t("View AI suggestions", "查看 AI 建议")}</button>}{onAnalyze && !proposal && <button type="button" onClick={onAnalyze}>{t("Analyze this goal", "分析此目标")}</button>}</div>}
      {hasRelation && <div className="teleology-relation-grid">{RELATIONS.map((kind) => {
        const confirmed = relations.filter((edge) => edge.relationship === kind);
        const proposed = proposedRelations.filter((item) => item.relationship === kind);
        const confirmedCount = confirmedRelationCounts?.[kind] ?? confirmed.length;
        if (!confirmedCount && !proposed.length) return null;
        return <div className="teleology-relation-group" key={kind}><h3>{t(LABELS[kind][0], LABELS[kind][1])} <small>{confirmedCount} {t("confirmed", "已确认")} · {proposed.length} {t("AI suggestions", "AI建议")}</small></h3>
          {confirmed.map((edge) => <div className="teleology-relation-item is-confirmed" key={edge.id}><span>{edge.sourceName} → {edge.targetName}</span><small>{t("Confirmed", "已确认")}</small></div>)}
          {proposed.map((item) => <button type="button" className="teleology-relation-item is-proposed" key={item.id} onClick={() => onSelectProposal(item)}><span>{item.source} → {item.target}</span><small>{t("AI suggestion", "AI建议")}</small></button>)}</div>;
      })}</div>}
    </section>

    {(constraints.length > 0 || proposedConstraint.length > 0 || proposedGoal.length > 0) && <section className="teleology-focus-lane"><div className="onto-lane-caption">{t("Constraints and suggested goals", "约束与建议目标")}</div><div className="teleology-focus-cards">
      {constraints.map((item) => <div className="teleology-semantic-card is-confirmed" key={item.id}><small>{t("Confirmed constraint", "已确认约束")}</small><strong>{item.name}</strong></div>)}
      {[...proposedConstraint, ...proposedGoal].map((item) => <button type="button" className="teleology-semantic-card is-proposed" key={item.id} onClick={() => onSelectProposal(item)}><small>{item.kind === "constraint" ? t("AI constraint", "AI约束建议") : t("AI suggested goal", "AI目标建议")}</small><strong>{item.name}</strong></button>)}
    </div></section>}

    {childTotal > 0 && <section className="teleology-how"><div className="onto-lane-caption">HOW · {t("Company Tree context", "Company Tree 上下文")}</div><div className="teleology-how-grid">{subgoals.slice(0, 6).map((child) => <button type="button" className="teleology-how-card" key={child.id} onClick={() => onSelectGoal(child.id)}>{child.name}</button>)}</div>{childTotal > 6 && onShowChildren && <button type="button" className="teleology-how-more" onClick={onShowChildren}>{t("View all subgoals", "查看全部子目标")} · {childTotal}</button>}</section>}
  </div>;
}
