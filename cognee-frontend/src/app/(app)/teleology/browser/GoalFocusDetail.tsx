"use client";

import { useEffect, useState } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import {
  analyzePurpose,
  getGoalRelations,
  getGraphAnnotations,
  getLatestOpenGoalProposal,
  getPurposeContext,
  type GraphNodeSummary,
  type ProposalItem,
  type TeleologyProposal,
} from "@/modules/teleology/teleologyApi";
import { isMissingGraphGoal } from "./derivedGoalTree";
import TeleologyFocusMap from "./TeleologyFocusMap";
import type { OntologyEdge } from "./types";

export interface FocusPreset {
  goal: GraphNodeSummary;
  purposes: GraphNodeSummary[];
  constraints: GraphNodeSummary[];
  relations: OntologyEdge[];
  counts?: { serves: number; advances: number; blocks: number };
  proposal: TeleologyProposal | null;
  children: GraphNodeSummary[];
  childTotal: number;
}

function relationEdges(items: { source_id: string; target_id: string; source_name: string; target_name: string; source_type: string; target_type: string; relationship: string }[]): OntologyEdge[] {
  return items.map((edge) => ({
    id: `${edge.source_id}|${edge.relationship}|${edge.target_id}`,
    sourceId: edge.source_id,
    targetId: edge.target_id,
    sourceName: edge.source_name,
    targetName: edge.target_name,
    sourceType: edge.source_type,
    targetType: edge.target_type,
    relationship: edge.relationship,
    status: "confirmed" as const,
  }));
}

export default function GoalFocusDetail({
  instance,
  datasetId,
  goalId,
  preset,
  language,
  selectedProposalItem,
  onSelectProposal,
  onSelectGoal,
  onAnalyze,
  onReviewProposal,
  onShowChildren,
}: {
  instance: CogneeInstance;
  datasetId: string;
  goalId: string;
  preset?: FocusPreset | null;
  language: "zh" | "en";
  selectedProposalItem?: ProposalItem | null;
  onSelectProposal: (item: ProposalItem) => void;
  onSelectGoal: (id: string) => void;
  onAnalyze?: () => void;
  onReviewProposal?: (proposal: TeleologyProposal) => void;
  onShowChildren?: () => void;
}) {
  const presetMatches = preset && (preset.goal.id === goalId || preset.goal.candidate_id === goalId || preset.goal.visual_id === goalId) ? preset : null;
  const [loaded, setLoaded] = useState<FocusPreset | null>(presetMatches);
  const [loading, setLoading] = useState(!presetMatches);
  const [error, setError] = useState<string | null>(null);
  const [localProposal, setLocalProposal] = useState<TeleologyProposal | null>(null);

  useEffect(() => {
    const matched = preset && (preset.goal.id === goalId || preset.goal.candidate_id === goalId || preset.goal.visual_id === goalId) ? preset : null;
    if (matched) {
      setLoaded(matched);
      setLocalProposal(null);
      setLoading(false);
      setError(null);
      const graphId = matched.goal.graph_id;
      if (!graphId) return;
      let active = true;
      void Promise.all([
        getPurposeContext(instance, datasetId, graphId),
        getGoalRelations(instance, datasetId, graphId, { limit: 30 }),
      ]).then(([context, relations]) => {
        if (!active) return;
        setLoaded((current) => current && current.goal.candidate_id === matched.goal.candidate_id ? {
          ...current,
          purposes: current.purposes.length ? current.purposes : context.purposes || [],
          constraints: current.constraints.length ? current.constraints : context.constraints || [],
          relations: current.relations.length ? current.relations : relationEdges(relations.items),
          counts: current.relations.length ? current.counts : relations.counts,
        } : current);
      }).catch((cause) => {
        const message = cause instanceof Error ? cause.message : String(cause);
        if (active && !isMissingGraphGoal(message)) setError(message);
      });
      return () => { active = false; };
    }
    if (goalId.startsWith("visual:") || goalId.startsWith("data:")) {
      setLoaded(null);
      setLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setLocalProposal(null);
    void Promise.all([
      getPurposeContext(instance, datasetId, goalId),
      getGoalRelations(instance, datasetId, goalId, { limit: 30 }),
      getLatestOpenGoalProposal(instance, datasetId, goalId),
      getGraphAnnotations(instance, datasetId, { parentId: goalId, goalsLimit: 6 }),
    ]).then(([context, relations, proposal, children]) => {
      if (!active) return;
      setLoaded({
        goal: context.goal,
        purposes: context.purposes || [],
        constraints: context.constraints || [],
        relations: relationEdges(relations.items),
        counts: relations.counts,
        proposal,
        children: children.goals,
        childTotal: children.goals_total ?? children.goals.length,
      });
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [instance, datasetId, goalId, preset]);

  const view = loaded && (loaded.goal.id === goalId || loaded.goal.candidate_id === goalId || loaded.goal.visual_id === goalId) ? loaded : presetMatches;
  const proposal = localProposal || view?.proposal || null;
  const t = (en: string, zh: string) => (language === "zh" ? zh : en);

  async function analyze() {
    if (onAnalyze) {
      onAnalyze();
      return;
    }
    try {
      const result = await analyzePurpose(instance, datasetId, goalId);
      setLocalProposal(result);
      onReviewProposal?.(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  if (!view) {
    return <div className="teleology-focus-empty">{error || (loading ? t("Loading purpose detail…", "正在加载目的详情…") : t("This node has no purpose detail.", "该节点没有目的详情。"))}</div>;
  }

  return (
    <>
    <TeleologyFocusMap
      variant="detail"
      goal={view.goal}
      purposes={view.purposes}
      constraints={view.constraints}
      relations={view.relations}
      confirmedRelationCounts={view.counts}
      proposal={proposal}
      subgoals={view.children}
      childTotal={view.childTotal}
      language={language}
      loading={loading}
      onSelectProposal={(item) => onSelectProposal(item)}
      onSelectGoal={onSelectGoal}
      onAnalyze={() => void analyze()}
      onReviewProposal={() => { if (proposal) onReviewProposal?.(proposal); }}
      onShowChildren={onShowChildren}
    />
    {selectedProposalItem ? <div className="teleology-detail-selected"><strong>{selectedProposalItem.name || `${selectedProposalItem.source || ""} → ${selectedProposalItem.target || ""}`}</strong><p>{selectedProposalItem.reason || "—"}</p><p>{selectedProposalItem.confidence == null ? "—" : `${Math.round(selectedProposalItem.confidence * 100)}%`}</p><p>{selectedProposalItem.evidence?.map((entry) => entry.name).join("、") || selectedProposalItem.evidence_node_ids?.join("、") || "—"}</p></div> : null}
    </>
  );
}
