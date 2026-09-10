"use client";

import { IconButton } from "@/ui/elements";
import { notifications } from "@mantine/notifications";
import { useTranslations } from "next-intl";
import Image from "next/image";
import { trackEvent } from "@/modules/analytics";

export default function CopyApiKeyButton({
  apiKey,
}: {
  apiKey: { key: string };
}) {
  const t = useTranslations("apiKeys");
  const tCommon = useTranslations("common");

  function copyApiKey(apiKey: { key: string }) {
    navigator.clipboard.writeText(apiKey.key);
    trackEvent({ pageName: "API Keys", eventName: "api_key_copied" });
    notifications.show({
      title: t("copiedToast"),
      message: "",
      color: "primary2.6",
    });
  }

  return (
    <IconButton onClick={copyApiKey.bind(null, apiKey)}>
      <Image
        width={28}
        height={28}
        src={"/images/icons/copy.svg"}
        alt={tCommon("copy")}
      />
    </IconButton>
  );
}
