"use client";

import { buildSopViewModel, type SopOrigin, type SopViewModel } from "@/modules/teleology/sop/sopViewModel";
import "./sop.css";

const STATUS_ZH: Record<string, string> = {
  VALID: "可以审阅",
  NEEDS_REVIEW: "需要补充",
  INSUFFICIENT_EVIDENCE: "证据不足",
  proposal: "草案",
};

const STATUS_EN: Record<string, string> = {
  VALID: "Ready for review",
  NEEDS_REVIEW: "Needs detail",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
  proposal: "Draft",
};

const ORIGIN_ZH: Record<SopOrigin, string> = {
  SOURCE: "来自资料",
  DERIVED: "由约束推导",
  MISSING: "待确认",
  OTHER: "未标注",
};

const ORIGIN_EN: Record<SopOrigin, string> = {
  SOURCE: "From the source",
  DERIVED: "Derived from a constraint",
  MISSING: "Not stated",
  OTHER: "Unmarked",
};

function statusClass(status: string): string {
  if (status === "VALID") return "is-valid";
  if (status === "INSUFFICIENT_EVIDENCE") return "is-thin";
  return "is-review";
}

export default function SopViewer({
  proposal,
  language = "zh",
}: {
  proposal: unknown;
  language?: "zh" | "en";
}) {
  const zh = language === "zh";
  const view = buildSopViewModel(proposal);
  const statusLabel = (zh ? STATUS_ZH : STATUS_EN)[view.status] || view.status;
  const origin = zh ? ORIGIN_ZH : ORIGIN_EN;

  return (
    <div className="sop-sheet">
      <article className="sop-reader" data-testid="sop-reader">
        <header>
          <p className="sop-kicker">{zh ? "流程草案" : "Procedure draft"}</p>
          <h1>{view.title}</h1>
          <div className="sop-meta">
            <span className={statusClass(view.status)}>{statusLabel}</span>
            {view.confidence ? <span>{zh ? `把握 ${view.confidence}` : `Confidence ${view.confidence}`}</span> : null}
          </div>
        </header>

        {view.objective ? (
          <section className="sop-section">
            <h2>{zh ? "要完成什么" : "Outcome"}</h2>
            <p className="sop-objective">{view.objective}</p>
          </section>
        ) : null}

        <section className="sop-section">
          <h2>{zh ? "流程图" : "Flow"}</h2>
          <ol className="sop-flow" aria-label={zh ? "流程图" : "Flow"}>
            {view.flow.map((node) => (
              <li key={node.id} className={`is-${node.kind}`}>
                <span className="sop-flow-mark">{node.marker}</span>
                <p className="sop-flow-body">{node.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <ItemSection title={zh ? "执行步骤" : "Steps"} items={view.steps} origin={origin} empty={zh ? "资料里还没有可执行的步骤。" : "No executable step is in the source."} />
        <ItemSection title={zh ? "验收" : "Checks"} items={view.checks} origin={origin} empty={zh ? "资料里还没有验收标准。" : "No check is in the source."} />
        <ItemSection title={zh ? "需要的资料" : "Inputs"} items={view.inputs} origin={origin} empty={zh ? "没有点名的附件或引用。" : "No named attachment or reference."} />

        <section className="sop-section">
          <h2>{zh ? "还缺什么" : "Still missing"}</h2>
          {view.missing.length === 0 ? (
            <p>{zh ? "没有标出的缺口。" : "No listed gap."}</p>
          ) : (
            <ul className="sop-missing">
              {view.missing.map((item) => (
                <li key={item.field}>
                  <strong>{item.field}</strong>
                  {item.reason ? <small>{item.reason}</small> : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="sop-section">
          <h2>{zh ? "AI 依据" : "Why this draft"}</h2>
          {view.basis.length === 0 && view.notices.length === 0 ? (
            <p>{zh ? "这份草案没有附带说明。" : "This draft has no explanation."}</p>
          ) : (
            <ul className="sop-basis">
              {view.basis.map((line) => <li key={line}>{line}</li>)}
              {view.notices.map((line) => <li key={line}>{line}</li>)}
            </ul>
          )}
        </section>
      </article>

      <DeveloperFold view={view} language={language} />
    </div>
  );
}

function ItemSection({
  title,
  items,
  origin,
  empty,
}: {
  title: string;
  items: SopViewModel["steps"];
  origin: Record<SopOrigin, string>;
  empty: string;
}) {
  return (
    <section className="sop-section">
      <h2>{title}</h2>
      {items.length === 0 ? <p>{empty}</p> : (
        <div className="sop-list">
          {items.map((item) => (
            <article key={item.label}>
              <span className="sop-origin">{item.label}</span>
              <div>
                <strong>{item.text}</strong>
                <p>{origin[item.origin]}{item.reason ? ` · ${item.reason}` : ""}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function DeveloperFold({ view, language }: { view: SopViewModel; language: "zh" | "en" }) {
  const zh = language === "zh";
  return (
    <details className="sop-developer" data-testid="sop-developer">
      <summary>{zh ? "查看依据 / 开发信息" : "Evidence / developer detail"}</summary>
      <p>
        {zh ? "房间" : "Room"}: {view.developer.roomKey || "—"}
        {" · "}
        {zh ? "目标编号" : "Goal id"}: {view.developer.goalId || "—"}
        {" · "}
        run_id: {view.developer.runId || "—"}
        {" · "}
        dataset_id: {view.developer.datasetId || "—"}
      </p>
      <ul>
        {view.developer.items.map((item) => (
          <li key={item.label}>
            {item.label}: source_uid={item.sourceUid || "—"} evidence_node_id={item.evidenceNodeId || "—"}
          </li>
        ))}
      </ul>
      <pre>{view.mermaid}</pre>
      <pre>{JSON.stringify(view.developer.proposal, null, 2)}</pre>
    </details>
  );
}
