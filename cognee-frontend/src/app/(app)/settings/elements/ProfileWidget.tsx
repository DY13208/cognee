"use client";

import { useCurrentUser } from "@/modules/users/useCurrentUser";
import { Avatar, Divider, Flex, Stack, Text, TextInput } from "@mantine/core";
import { useTranslations } from "next-intl";
import Image from "next/image";

export default function ProfileWidget() {
  const t = useTranslations("settings.profile");
  const { data: user } = useCurrentUser();

  return (
    <Stack
      className="rounded-[0.5rem] px-[2rem] pt-[1.5rem] pb-[1.75rem] !gap-[0] min-w-[25rem] max-w-[29.5rem]"
      style={{
        background: "rgba(255,255,255,0.06)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: 12,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: "1.375rem" }}>
        <h2 style={{ fontSize: 20, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif' }}>{t("title")}</h2>
        <p style={{ fontSize: 14, color: "rgba(237,236,234,0.55)", margin: 0 }}>{t("description")}</p>
      </div>
      <Flex align="center" gap="1rem" mb="1.5rem">
        <Avatar size="lg">
          <Image
            width={54}
            height={54}
            alt=""
            src="/images/icons/avatar.svg"
          />
        </Avatar>
        <Stack gap="0">
          <Text size="sm" fw={700} style={{ color: "#EDECEA" }}>{user?.name ?? "—"}</Text>
          <Text size="xs" style={{ color: "rgba(237,236,234,0.35)" }}>{user?.email ?? "—"}</Text>
        </Stack>
      </Flex>
      <Divider mb="1rem" style={{ borderColor: "rgba(255,255,255,0.08)" }} />
      <Stack gap="0.75rem">
        <TextInput
          label={t("name")}
          value={user?.name ?? ""}
          disabled
          classNames={{ input: "!h-[2.75rem] !border-cognee-border" }}
          radius="0.5rem"
          styles={{
            label: { color: "rgba(237,236,234,0.7)" },
            input: {
              background: "rgba(255,255,255,0.06)",
              borderColor: "rgba(255,255,255,0.12)",
              color: "#EDECEA",
            },
          }}
        />
        <TextInput
          label={t("email")}
          value={user?.email ?? ""}
          disabled
          classNames={{ input: "!h-[2.75rem] !border-cognee-border" }}
          radius="0.5rem"
          styles={{
            label: { color: "rgba(237,236,234,0.7)" },
            input: {
              background: "rgba(255,255,255,0.06)",
              borderColor: "rgba(255,255,255,0.12)",
              color: "#EDECEA",
            },
          }}
        />
      </Stack>
      <Text size="sm" style={{ color: "rgba(237,236,234,0.35)" }} mt="1rem">
        {t("managedHint")}
      </Text>
    </Stack>
  );
}
