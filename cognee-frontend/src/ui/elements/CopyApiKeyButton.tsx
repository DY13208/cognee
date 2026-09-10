"use client";

import { IconButton } from "@/ui/elements";
import { notifications } from "@mantine/notifications";
import Image from "next/image";
import { trackEvent } from "@/modules/analytics";
import { copyTextToClipboard } from "@/utils";

export default function CopyApiKeyButton({
  apiKey,
}: {
  apiKey: { key: string };
}) {
  async function copyApiKey(apiKey: { key: string }) {
    try {
      await copyTextToClipboard(apiKey.key);
      trackEvent({ pageName: "API Keys", eventName: "api_key_copied" });
      notifications.show({
        title: "Copied API key to clipboard",
        message: "",
        color: "primary2.6",
      });
    } catch (err) {
      console.error("Failed to copy API key:", err);
      notifications.show({
        title: "Copy failed",
        message: "Could not copy to clipboard. Please select and copy manually.",
        color: "red",
      });
    }
  }

  return (
    <IconButton onClick={copyApiKey.bind(null, apiKey)}>
      <Image
        width={28}
        height={28}
        src={"/images/icons/copy.svg"}
        alt={"Copy"}
      />
    </IconButton>
  );
}
