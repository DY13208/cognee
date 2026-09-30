/** User-facing SOP view. Technical identifiers stay in `developer`. */

const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const TECHNICAL_WORD = /\b(?:source_uids?|evidence_node_ids?|run_id|dataset_id)\b/gi;

export type SopOrigin = "SOURCE" | "DERIVED" | "MISSING" | "OTHER";
export type SopFlowKind = "start" | "input" | "plan" | "check" | "gap" | "end";

export interface SopViewItem {
  label: string;
  text: string;
  origin: SopOrigin;
  reason: string;
  sourceUid: string;
  evidenceNodeId: string;
}

export interface SopFlowNode {
  id: string;
  marker: string;
  text: string;
  kind: SopFlowKind;
}

export interface SopMissingItem {
  field: string;
  reason: string;
}

export interface SopViewModel {
  title: string;
  objective: string;
  status: string;
  confidence: string;
  steps: SopViewItem[];
  checks: SopViewItem[];
  inputs: SopViewItem[];
  missing: SopMissingItem[];
  basis: string[];
  notices: string[];
  flow: SopFlowNode[];
  mermaid: string;
  developer: {
    datasetId: string;
    runId: string;
    roomKey: string;
    goalId: string;
    mermaid: string;
    items: Array<{ label: string; sourceUid: string; evidenceNodeId: string }>;
    validation: unknown;
    proposal: unknown;
  };
}

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : null;
}

function asList(value: unknown): Dict[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const row = asDict(item);
    return row ? [row] : [];
  }) : [];
}

export function scrubTechnical(value: unknown): string {
  return String(value ?? "")
    .replace(UUID, "")
    .replace(TECHNICAL_WORD, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([，。；：])/g, "$1")
    .trim();
}

function plain(value: unknown): string {
  return String(value ?? "").trim();
}

function originOf(value: unknown): SopOrigin {
  if (value === "SOURCE" || value === "DERIVED" || value === "MISSING") return value;
  return "OTHER";
}

function itemText(row: Dict): string {
  return scrubTechnical(row.text || row.name || "");
}

function readItems(rows: Dict[], prefix: "P" | "C" | "I"): SopViewItem[] {
  const seen = new Set<string>();
  const items: SopViewItem[] = [];
  rows.forEach((row, index) => {
    const text = itemText(row);
    if (!text || seen.has(text)) return;
    seen.add(text);
    const given = plain(row.id);
    const label = new RegExp(`^${prefix}\\d+$`).test(given) ? given : `${prefix}${index + 1}`;
    items.push({
      label,
      text,
      origin: originOf(row.evidence_status),
      reason: scrubTechnical(row.reason),
      sourceUid: plain(row.source_uid) || plain((Array.isArray(row.source_uids) ? row.source_uids[0] : "")),
      evidenceNodeId: plain(row.evidence_node_id) || plain((Array.isArray(row.evidence_node_ids) ? row.evidence_node_ids[0] : "")),
    });
  });
  return items;
}

function named(rows: Dict[]): string[] {
  return rows
    .map((row) => scrubTechnical(row.name || row.text || ""))
    .filter((name, index, all) => name && all.indexOf(name) === index);
}

function mermaidLabel(text: string): string {
  return text.replace(/["[\]{}|#]/g, " ").replace(/\s+/g, " ").trim() || "步骤";
}

function buildFlow(steps: SopViewItem[], checks: SopViewItem[], inputs: SopViewItem[]): SopFlowNode[] {
  const flow: SopFlowNode[] = [{ id: "start", marker: "开始", text: "开始", kind: "start" }];
  inputs.forEach((item, index) => {
    flow.push({ id: `in${index + 1}`, marker: "资料", text: item.text, kind: "input" });
  });
  if (steps.length === 0) {
    flow.push({ id: "gap", marker: "·", text: "还没有可执行步骤", kind: "gap" });
  } else {
    steps.forEach((item, index) => {
      flow.push({ id: `p${index + 1}`, marker: String(index + 1), text: item.text, kind: "plan" });
    });
  }
  checks.forEach((item, index) => {
    flow.push({ id: `c${index + 1}`, marker: "验收", text: item.text, kind: "check" });
  });
  flow.push({ id: "finish", marker: "结束", text: "结束", kind: "end" });
  return flow;
}

export function buildSopMermaid(flow: SopFlowNode[]): string {
  const lines = ["flowchart TD"];
  flow.forEach((node) => {
    const label = mermaidLabel(node.text);
    if (node.kind === "start" || node.kind === "end") lines.push(`  ${node.id}([${label}])`);
    else if (node.kind === "check") lines.push(`  ${node.id}{"${label}"}`);
    else lines.push(`  ${node.id}["${label}"]`);
  });
  for (let index = 0; index < flow.length - 1; index += 1) {
    lines.push(`  ${flow[index].id} --> ${flow[index + 1].id}`);
  }
  return lines.join("\n");
}

function pushUnique(target: string[], value: string) {
  const text = scrubTechnical(value);
  if (text && !target.includes(text)) target.push(text);
}

export function buildSopViewModel(proposal: unknown): SopViewModel {
  const root = asDict(proposal) || {};
  const goal = asDict(root.goal);
  const validation = asDict(root.validation);
  const steps = readItems(asList(root.plan), "P");
  const checks = readItems(asList(root.checks), "C");
  const inputs = readItems(asList(root.inputs), "I");
  const flow = buildFlow(steps, checks, inputs);
  const mermaid = buildSopMermaid(flow);

  const missing: SopMissingItem[] = [];
  const seenMissing = new Set<string>();
  const addMissing = (field: string, reason: string) => {
    const name = scrubTechnical(field);
    if (!name || seenMissing.has(name)) return;
    seenMissing.add(name);
    missing.push({ field: name, reason: scrubTechnical(reason) || "当前资料没有写明这一项" });
  };
  asList(root.missing_details).forEach((row) => addMissing(plain(row.field || row.text), plain(row.reason)));
  (Array.isArray(root.gaps) ? root.gaps : []).forEach((gap) => addMissing(plain(gap), ""));
  (Array.isArray(validation?.quality_gaps) ? validation.quality_gaps : []).forEach((gap) => addMissing(plain(gap), ""));
  (Array.isArray(validation?.missing_fields) ? validation.missing_fields : []).forEach((field) => addMissing(plain(field), ""));

  const basis: string[] = [];
  const goalName = scrubTechnical(goal?.name || root.objective || "");
  if (goalName) pushUnique(basis, `关联目标：${goalName}`);
  named(asList(root.purpose)).forEach((name) => pushUnique(basis, `目的：${name}`));
  named(asList(root.constraints)).forEach((name) => pushUnique(basis, `约束：${name}`));
  [...steps, ...checks].forEach((item) => {
    if (item.reason) pushUnique(basis, `${item.label}：${item.reason}`);
  });
  pushUnique(basis, plain(validation?.goal_resolution_reason || root.goal_resolution_reason));

  const notices: string[] = [];
  (Array.isArray(root.risks) ? root.risks : []).forEach((risk) => pushUnique(notices, plain(risk)));
  asList(validation?.unsupported_claims).forEach((row) => pushUnique(notices, plain(row.reason)));
  asList(validation?.constraint_conflicts).forEach((row) => pushUnique(notices, plain(row.reason)));
  asList(validation?.provenance_conflicts).forEach((row) => pushUnique(notices, plain(row.reason)));
  asList(validation?.sop_conflicts).forEach((row) => pushUnique(notices, plain(row.reason)));

  const confidenceValue = Number(root.overall_confidence);
  const confidence = Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "";
  const status = plain(validation?.status || root.status || "proposal");

  return {
    title: scrubTechnical(root.title) || "SOP 草案",
    objective: goalName,
    status,
    confidence,
    steps,
    checks,
    inputs,
    missing,
    basis,
    notices,
    flow,
    mermaid,
    developer: {
      datasetId: plain(root.dataset_id),
      runId: plain(root.run_id),
      roomKey: plain(root.scope),
      goalId: plain(goal?.id),
      mermaid,
      items: [...inputs, ...checks, ...steps].map((item) => ({
        label: item.label,
        sourceUid: item.sourceUid,
        evidenceNodeId: item.evidenceNodeId,
      })),
      validation: root.validation ?? null,
      proposal: root,
    },
  };
}
