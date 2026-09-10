"use client";

import { useTranslations } from "next-intl";
import { AsciiFrame } from "@/app/(app)/dashboard/partials/redesign/AsciiFrame";
import { FONT, T } from "@/app/(app)/dashboard/partials/redesign/mono";

type CloudFeature = "activity" | "analytics" | "memoryCoverage";

const FEATURE_KEYS: Record<CloudFeature, { label: "activityLabel" | "analyticsLabel" | "memoryCoverageLabel"; title: "activityTitle" | "analyticsTitle" | "memoryCoverageTitle" }> = {
  activity: { label: "activityLabel", title: "activityTitle" },
  analytics: { label: "analyticsLabel", title: "analyticsTitle" },
  memoryCoverage: { label: "memoryCoverageLabel", title: "memoryCoverageTitle" },
};

export default function CloudFeatureNotice({
  feature,
  minHeight = 320,
  padded = true,
}: {
  feature: CloudFeature;
  minHeight?: number;
  padded?: boolean;
}) {
  const t = useTranslations("dashboard.stubs");
  const keys = FEATURE_KEYS[feature];
  const frame = (
    <AsciiFrame label={t(keys.label)} minHeight={minHeight}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, textAlign: "center", padding: 20 }}>
        <span style={{ ...FONT, fontSize: padded ? 16 : 14, fontWeight: 500, color: T.text }}>
          {t(keys.title)}
        </span>
        <span style={{ ...FONT, fontSize: 13, color: T.muted, maxWidth: padded ? 380 : 320 }}>
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
  if (!padded) return frame;
  return <div style={{ minHeight: "100%", padding: "24px 32px 32px" }}>{frame}</div>;
}
