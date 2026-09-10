"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { SessionRow } from "@/modules/sessions/getSessions";
import type { TenantHourlyCosts } from "@/modules/billing/getTenantHourlyCosts";
import type { PipelineRun } from "@/ui/elements/AgentActivityTerminal";
import { AsciiFrame } from "./AsciiFrame";
import { FONT, T } from "./mono";
import type { DashRange } from "./RangeToggle";

/** Open-source stub — the spend/savings chart is priced off the tenant's real
 *  billing data and is a Cognee Cloud feature. Renders a text-only notice
 *  instead of syncing the real chart. */

interface CostPanelProps {
  sessions: SessionRow[];
  runs: PipelineRun[];
  balanceUsd: number | null;
  range: DashRange;
  onRangeChange: (range: DashRange) => void;
  hourlyCosts?: TenantHourlyCosts | null;
  onViewBreakdown?: () => void;
}

export function CostPanel(_props: CostPanelProps): React.ReactElement {
  const t = useTranslations("dashboard.stubs");
  return (
    <AsciiFrame label="Cost Savings" minHeight={260}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, textAlign: "center", padding: 20 }}>
        <span style={{ ...FONT, fontSize: 14, fontWeight: 500, color: T.text }}>
          {t("costSavingsTitle")}
        </span>
        <span style={{ ...FONT, fontSize: 13, color: T.muted, maxWidth: 320 }}>
          {t("description")}
        </span>
        <a
          href="https://www.cognee.ai"
          target="_blank"
          rel="noopener noreferrer"
          style={{ ...FONT, marginTop: 4, background: T.lavender, color: "#000000", borderRadius: 8, padding: "8px 20px", fontSize: 13, fontWeight: 600, textDecoration: "none" }}
        >
          {t("openCloud")}
        </a>
      </div>
    </AsciiFrame>
  );
}
