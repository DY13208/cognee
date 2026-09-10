/**
 * Open-source stub — Analytics reads the tenant's real spend/usage history
 * and is a Cognee Cloud feature. Renders a text-only notice instead of
 * syncing the real page.
 */
import CloudFeatureNotice from "@/ui/elements/CloudFeatureNotice";

export default function Page() {
  return <CloudFeatureNotice feature="analytics" />;
}
