"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import {
  coverageAction,
  getCoverageRun,
  getCoverageState,
  startCoverageRun,
  type CoverageRun,
  type CoverageStatePage,
} from "@/modules/teleology/teleologyApi";

const ACTIVE = new Set(["pending", "running", "paused", "paused_budget"]);

function count(summary: Record<string, number> | undefined, key: string): number {
  return summary?.[key] || 0;
}

export default function CoveragePanel({
  instance,
  datasetId,
  onClose,
}: {
  instance: CogneeInstance;
  datasetId: string;
  onClose: () => void;
}) {
  const [state, setState] = useState<CoverageStatePage | null>(null);
  const [run, setRun] = useState<CoverageRun | null>(null);
  const [maxGoals, setMaxGoals] = useState("100");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [advanced, setAdvanced] = useState(false);

  const refreshState = useCallback(async () => {
    const page = await getCoverageState(instance, datasetId);
    setState(page);
  }, [datasetId, instance]);

  useEffect(() => {
    refreshState().catch((exc: Error) => setError(exc.message));
  }, [refreshState]);

  useEffect(() => {
    if (!run || !ACTIVE.has(run.status)) return undefined;
    const timer = window.setInterval(() => {
      getCoverageRun(instance, run.id)
        .then(setRun)
        .catch((exc: Error) => setError(exc.message));
      refreshState().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [instance, refreshState, run]);

  const summary = state?.summary || {};
  const known = Object.values(summary).reduce((sum, value) => sum + value, 0);
  const analyzed = count(summary, "clean") + count(summary, "confirmed") + count(summary, "proposal_open") + count(summary, "no_supported_proposal");
  const coverage = known > 0 ? Math.round((analyzed / known) * 100) : 0;
  const tokens = useMemo(() => {
    if (!run?.token_usage_available) return "Token 用量暂不可用";
    const input = run.used_input_tokens || 0;
    const output = run.used_output_tokens || 0;
    return `${input + output}（输入 ${input} / 输出 ${output}）`;
  }, [run]);

  async function begin(mode: "baseline" | "incremental" | "force") {
    if (mode === "force") {
      const first = window.confirm("强制重新分析会再次调用模型，并且只生成待审核提案。确定继续？");
      if (!first) return;
      const second = window.confirm("再次确认：当前上限内的目标会重新分析。不会自动写入正式图谱。");
      if (!second) return;
    }
    const cap = maxGoals.trim() ? Number(maxGoals) : null;
    if (!cap && mode !== "force") {
      const proceed = window.confirm("没有设置本次上限，可能会分析大量目标。确定继续？");
      if (!proceed) return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await startCoverageRun(instance, {
        dataset_id: datasetId,
        mode,
        batch_size: 20,
        concurrency: 3,
        max_goals: cap,
      });
      setRun(created);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "覆盖分析没有启动");
    } finally {
      setBusy(false);
    }
  }

  async function act(action: "pause" | "resume" | "cancel" | "retry-failures") {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      setRun(await coverageAction(instance, run.id, action));
      await refreshState();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      style={{
        margin: "0 16px 12px",
        padding: "14px 16px",
        background: "#101114",
        border: "1px solid rgba(212, 175, 116, 0.35)",
        borderRadius: 12,
        color: "#EDECEA",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: "0.14em", color: "#D4AF74" }}>COVERAGE</div>
          <h2 style={{ margin: "2px 0 0", fontSize: 18 }}>目的论覆盖分析</h2>
        </div>
        <button type="button" onClick={onClose} style={quietButton}>关闭</button>
      </div>
      <p style={{ margin: "8px 0 12px", color: "rgba(237,236,234,0.62)", fontSize: 13 }}>
        只生成提案，不会自动确认，也不会写入正式图谱。默认先处理最多 100 个目标。
      </p>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: "rgba(237,236,234,0.62)" }}>{tokens}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        <Stat label="覆盖率" value={`${coverage}%`} />
        <Stat label="已记录" value={String(known)} />
        <Stat label="已分析" value={String(analyzed)} />
        <Stat label="已确认" value={String(count(summary, "confirmed"))} />
        <Stat label="待审核" value={String(count(summary, "proposal_open"))} />
        <Stat label="dirty" value={String(count(summary, "dirty"))} />
        <Stat label="未分析" value={String(count(summary, "never_analyzed"))} />
        <Stat label="证据不足" value={String(count(summary, "insufficient_context"))} />
        <Stat label="失败" value={String(count(summary, "retry_required"))} />
      </div>
      {run ? (
        <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.6 }}>
          <div>当前 Run {run.status} · {run.mode}</div>
          <div>已扫描 {run.scanned_goals || 0} / {run.total_goals || 0}</div>
          <div>queued {run.queued_goals} · processed {run.processed_goals}</div>
          <div>skipped {run.skipped_goals} · proposal {run.proposal_goals} · no change {run.no_change_goals} · failed {run.failed_goals}</div>
        </div>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12, alignItems: "center" }}>
        <label style={{ fontSize: 12, color: "rgba(237,236,234,0.7)" }}>
          本次最多
          <input
            value={maxGoals}
            onChange={(event) => setMaxGoals(event.target.value)}
            inputMode="numeric"
            style={{
              marginLeft: 6,
              width: 72,
              background: "#18191d",
              color: "#EDECEA",
              border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: 8,
              padding: "6px 8px",
            }}
          />
        </label>
        <button type="button" disabled={busy || !datasetId} style={button} onClick={() => begin("incremental")}>开始增量分析</button>
        <button type="button" disabled={busy || !run} style={quietButton} onClick={() => act("pause")}>暂停</button>
        <button type="button" disabled={busy || !run} style={quietButton} onClick={() => act("resume")}>继续</button>
        <button type="button" disabled={busy || !run} style={quietButton} onClick={() => act("cancel")}>取消</button>
        <button type="button" disabled={busy || !run} style={quietButton} onClick={() => act("retry-failures")}>重试失败</button>
      </div>
      <button type="button" style={{ ...quietButton, marginTop: 8 }} onClick={() => setAdvanced((open) => !open)}>
        {advanced ? "收起高级操作" : "高级操作"}
      </button>
      {advanced ? (
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button type="button" disabled={busy} style={quietButton} onClick={() => begin("baseline")}>首次建立基线</button>
          <button type="button" disabled={busy} style={quietButton} onClick={() => begin("force")}>强制重新分析</button>
        </div>
      ) : null}
      {error ? <div style={{ marginTop: 8, color: "#E7B3A1", fontSize: 13 }}>{error}</div> : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "#18191d", borderRadius: 8, padding: "8px 10px" }}>
      <div style={{ fontSize: 11, color: "rgba(237,236,234,0.5)" }}>{label}</div>
      <div style={{ fontSize: 16, marginTop: 2 }}>{value}</div>
    </div>
  );
}

const button: CSSProperties = {
  background: "rgba(212,175,116,0.18)",
  border: "1px solid rgba(212,175,116,0.5)",
  color: "#EDECEA",
  borderRadius: 8,
  padding: "7px 12px",
  cursor: "pointer",
};

const quietButton: CSSProperties = {
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.12)",
  color: "#EDECEA",
  borderRadius: 8,
  padding: "7px 12px",
  cursor: "pointer",
};
