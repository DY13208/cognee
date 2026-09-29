"use client";

import { useEffect, useState } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import {
  getGoalModel,
  reviewGoalCandidate,
  startTeleologyBuild,
  type GoalCandidate,
  type GoalModelView,
  type GoalTeleologyItem,
} from "@/modules/teleology/teleologyApi";

const STATUS_LABEL = { proposed: "提案", confirmed: "已确认", rejected: "已驳回" };

function childrenOf(model: GoalModelView, parentId: string | null) {
  return model.hierarchy.filter((goal) => (goal.parent_candidate_id || null) === parentId);
}

export default function GoalModelPage({
  instance,
  datasetId,
  datasetName = "",
  language,
}: {
  instance: CogneeInstance;
  datasetId: string;
  datasetName?: string;
  language: "zh" | "en";
}) {
  const zh = language === "zh";
  const [model, setModel] = useState<GoalModelView | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!datasetId) return;
    let active = true;
    setError(null);
    void getGoalModel(instance, datasetId)
      .then((loaded) => {
        if (!active) return;
        setModel(loaded);
        setSelectedId(loaded.hierarchy[0]?.id || loaded.candidates[0]?.id || null);
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      active = false;
    };
  }, [instance, datasetId]);

  const selected = model?.candidates.find((goal) => goal.id === selectedId) || null;
  const purposes = itemsFor(model?.purposes || [], selectedId);
  const constraints = itemsFor(model?.constraints || [], selectedId);
  const relations = itemsFor(model?.relations || [], selectedId);

  async function discover() {
    if (!datasetId) return;
    setBusy(true);
    setError(null);
    try {
      const loaded = await startTeleologyBuild(instance, {
        dataset_id: datasetId,
        mode: "baseline",
        batch_size: 20,
        concurrency: 1,
      });
      setModel(loaded);
      setSelectedId(loaded.hierarchy[0]?.id || null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function review(status: "confirmed" | "rejected") {
    if (!datasetId || !selected) return;
    setBusy(true);
    try {
      await reviewGoalCandidate(instance, datasetId, selected.id, status);
      const loaded = await getGoalModel(instance, datasetId);
      setModel(loaded);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="goal-model">
      <aside className="goal-model-nav" aria-label={zh ? "AI 目标模型" : "AI Goal Model"}>
        <header className="goal-model-kicker">
          <span>{zh ? "派生层" : "Derived"}{datasetName ? ` · ${datasetName}` : ""}</span>
          <strong>{zh ? "AI 目标模型" : "AI Goal Model"}</strong>
        </header>
        <button type="button" className="onto-btn onto-btn-primary" disabled={!datasetId || busy} onClick={() => void discover()}>
          {busy ? (zh ? "生成中…" : "Building…") : zh ? "生成候选，只保存 Proposal" : "Draft proposals only"}
        </button>
        {model && model.hierarchy.length > 0 ? (
          <div className="goal-model-tree">
            {childrenOf(model, null).map((goal) => (
              <GoalBranch key={goal.id} model={model} goalId={goal.id} depth={0} selectedId={selectedId} onSelect={setSelectedId} />
            ))}
          </div>
        ) : (
          <p className="goal-model-empty">
            {zh
              ? "尚未从 dataset 发现目标。公司树保存在来源面板，作为证据。"
              : "No goals have been discovered from this dataset yet. The company tree stays in the source panel as evidence."}
          </p>
        )}
      </aside>
      <section className="goal-model-main">
        {error && <p className="goal-model-error" role="alert">{error}</p>}
        {selected ? (
          <GoalReview goal={selected} purposes={purposes} constraints={constraints} relations={relations} zh={zh} busy={busy} onReview={review} />
        ) : (
          <p className="goal-model-empty">{zh ? "选择一个 AI 目标查看理由、证据和目的论提案。" : "Select an AI goal to review its reason, evidence, and teleology."}</p>
        )}
      </section>
      <aside className="goal-model-sources" aria-label={zh ? "来源 / Company Tree" : "Source / Company Tree"}>
        <header className="goal-model-kicker">
          <span>{zh ? "事实层" : "Fact"}</span>
          <strong>{zh ? "来源 / Company Tree" : "Source / Company Tree"}</strong>
        </header>
        <ul className="goal-model-source-list">
          {(model?.classifications || []).map((source) => (
            <li key={source.id}>
              <b>{source.name}</b>
              <span>{source.source_class}</span>
            </li>
          ))}
        </ul>
        {selected && (
          <div className="goal-model-source-note">
            <span>{zh ? "当前目标的证据" : "Evidence for this goal"}</span>
            <ul>
              {selected.evidence.map((entry) => (
                <li key={entry.node_id}>{entry.name} · {entry.source_class}</li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}

function GoalBranch({
  model,
  goalId,
  depth,
  selectedId,
  onSelect,
}: {
  model: GoalModelView;
  goalId: string;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const goal = model.hierarchy.find((item) => item.id === goalId);
  if (!goal) return null;
  const children = childrenOf(model, goal.id);
  return (
    <div className="goal-model-branch" style={{ marginLeft: depth ? 14 : 0 }}>
      <button type="button" className={`goal-model-row${selectedId === goal.id ? " is-selected" : ""}`} onClick={() => onSelect(goal.id)}>
        <span>{goal.name}</span>
        <small>
          {STATUS_LABEL[goal.status as keyof typeof STATUS_LABEL] || goal.status}
          {" · "}
          {Math.round((goal.confidence || 0) * 100)}%
          {" · "}
          {goal.evidence_count} 证据
        </small>
      </button>
      {children.map((child) => (
        <GoalBranch key={child.id} model={model} goalId={child.id} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}

function GoalReview({
  goal,
  purposes,
  constraints,
  relations,
  zh,
  busy,
  onReview,
}: {
  goal: GoalCandidate;
  purposes: GoalTeleologyItem[];
  constraints: GoalTeleologyItem[];
  relations: GoalTeleologyItem[];
  zh: boolean;
  busy: boolean;
  onReview: (status: "confirmed" | "rejected") => void;
}) {
  return (
    <article className="goal-model-review">
      <p className="goal-model-status">{STATUS_LABEL[goal.status] || goal.status} · {Math.round(goal.confidence * 100)}%</p>
      <h2>{goal.name}</h2>
      <p>{goal.description}</p>
      <h3>{zh ? "理由" : "Reason"}</h3>
      <p>{goal.reason}</p>
      <div className="goal-model-actions">
        <button type="button" className="onto-btn onto-btn-primary" disabled={busy} onClick={() => onReview("confirmed")}>{zh ? "标为已确认" : "Mark confirmed"}</button>
        <button type="button" className="onto-btn" disabled={busy} onClick={() => onReview("rejected")}>{zh ? "驳回" : "Reject"}</button>
      </div>
      <p className="goal-model-footnote">{zh ? "确认只改变派生层状态，不写入公司树，也不提交目的论图谱。" : "Confirmation stays on the derived layer. It does not write the company tree or commit teleology."}</p>
      <ReviewList title="Purpose" items={purposes} />
      <ReviewList title="Constraint" items={constraints} />
      <ReviewList title={zh ? "关系" : "Relations"} items={relations} />
    </article>
  );
}

function ReviewList({ title, items }: { title: string; items: GoalTeleologyItem[] }) {
  if (!items.length) return null;
  return (
    <div className="goal-model-block">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <b>{item.relationship ? `${item.relationship} · ${item.name}` : item.name}</b>
            <span>{item.reason}</span>
            <small>{Math.round((item.confidence || 0) * 100)}% · {(item.source_node_ids || []).length} sources</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

function itemsFor(items: GoalTeleologyItem[], goalId: string | null) {
  if (!goalId) return [];
  return items.filter((item) => item.goal_id === goalId || item.source === goalId || item.target === goalId);
}
