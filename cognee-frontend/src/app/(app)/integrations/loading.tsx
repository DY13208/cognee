import PageLoading from "@/ui/elements/PageLoading";
import { getNavLoadingTitle } from "@/i18n/getNavLoadingTitle";

export default async function Loading() {
  return <PageLoading name={await getNavLoadingTitle("integrations")} />;
}
