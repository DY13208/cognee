import PageLoading from "@/ui/elements/PageLoading";
import { getMessages } from "@/i18n/getMessages";
import { getRequestLocale } from "@/i18n/getRequestLocale";

export default async function Loading() {
  const locale = await getRequestLocale();
  const messages = getMessages(locale) as { apiKeys: { title: string } };
  return <PageLoading name={messages.apiKeys.title} />;
}
