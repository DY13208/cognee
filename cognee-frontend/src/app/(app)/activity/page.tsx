/**
 * Open-source stub — the full activity log reveals real per-event workspace
 * usage and is a Cognee Cloud feature. Renders a text-only notice instead of
 * syncing the real page.
 */
import CloudFeatureNotice from "@/ui/elements/CloudFeatureNotice";

export default function Page() {
  return <CloudFeatureNotice feature="activity" />;
}
