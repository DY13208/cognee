"use client";

import React from "react";
import type { SessionRow } from "@/modules/sessions/getSessions";
import type { PipelineRun } from "@/ui/elements/AgentActivityTerminal";
import type { Agent, Dataset } from "@/ui/layout/FilterContext";
import CloudFeatureNotice from "@/ui/elements/CloudFeatureNotice";

/** Open-source stub — the per-event activity log reveals real workspace
 *  usage and is a Cognee Cloud feature. Renders a text-only notice instead
 *  of syncing the real log. */

interface ActivityPanelProps {
  runs: PipelineRun[];
  sessions: SessionRow[];
  agents: Agent[];
  datasets: Dataset[];
  onViewFullLog?: () => void;
}

export function ActivityPanel(_props: ActivityPanelProps): React.ReactElement {
  return <CloudFeatureNotice feature="activity" padded={false} minHeight={260} />;
}
