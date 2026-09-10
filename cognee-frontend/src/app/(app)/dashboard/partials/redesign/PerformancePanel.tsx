"use client";

import React from "react";
import CloudFeatureNotice from "@/ui/elements/CloudFeatureNotice";

/** Open-source stub — recall/coverage scoring reads the tenant's real brains
 *  and is a Cognee Cloud feature. Renders a text-only notice instead of
 *  syncing the real panel. */

export interface TopicScore { name: string; pct: number | null }

interface PerformancePanelProps {
  recallPct: number | null;
  topics: TopicScore[];
  onUpload?: () => void;
  onViewAnalysis?: () => void;
}

export function PerformancePanel(_props: PerformancePanelProps): React.ReactElement {
  return <CloudFeatureNotice feature="memoryCoverage" padded={false} minHeight={260} />;
}
