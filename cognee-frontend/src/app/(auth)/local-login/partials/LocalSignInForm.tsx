"use client";

import { useState } from "react";
import { Flex, Text, Title, TextInput, PasswordInput, Button } from "@mantine/core";
import { useTranslations } from "next-intl";
import AuthCard from "@/ui/elements/Auth/AuthCard";
import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";
import { getLocalizedErrorKey } from "@/i18n/errorMessages";

export default function LocalSignInForm() {
  const t = useTranslations("Auth");
  const localApiUrl = getLocalApiUrl();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const response = await global.fetch(`${localApiUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
        credentials: "include",
      });

      if (!response.ok) {
        const data = await response.json().catch((err) => {
          console.warn("Failed to parse login error response:", err);
          return null;
        });
        const detail = data?.detail;
        setError(t(getLocalizedErrorKey(detail)));
        return;
      }

      window.location.href = "/";
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          t("connectionFailed", { url: localApiUrl })
        );
      } else {
        setError(t("genericError"));
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthCard>
      <Flex className="flex-col gap-[0.75rem] items-center">
        <Title
          order={2}
          className="!text-[2.5rem] !font-light !leading-[1.1] !tracking-[-0.04em] !text-[#EDECEA]"
          style={{ fontFamily: '"TWKLausanne", sans-serif' }}
        >
          {t("localInstance")}
        </Title>
        <Text size="sm" className="!text-[#EDECEA]/85 !font-light !text-center">
          {t("signInLocal")}
        </Text>
      </Flex>

      {error && (
        <Flex
          className="w-full px-4 py-3 rounded-lg gap-2 items-start"
          style={{ backgroundColor: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)" }}
        >
          <Text size="sm" style={{ color: "#FCA5A5" }}>
            {error}
          </Text>
        </Flex>
      )}

      <form onSubmit={handleSubmit} className="w-full flex flex-col gap-[0.75rem]">
        <TextInput
          label={t("email")}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
          required
          autoComplete="email"
          size="md"
          radius="md"
          classNames={{
            label: "!text-[#EDECEA]/85 !font-light",
            input:
              "!bg-white/[0.06] !border-white/15 !text-[#EDECEA] focus:!border-[#BC9BFF] focus:!border-2",
          }}
        />

        <PasswordInput
          label={t("password")}
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          required
          autoComplete="current-password"
          size="md"
          radius="md"
          classNames={{
            label: "!text-[#EDECEA]/85 !font-light",
            input:
              "!bg-white/[0.06] !border-white/15 !text-[#EDECEA] focus:!border-[#BC9BFF] focus:!border-2",
            innerInput: "!text-[#EDECEA]",
          }}
        />

        <Text size="xs" className="!text-[#EDECEA]/60 !font-light" mt={-4}>
          {t("credentialsHint")}
        </Text>

        <Button
          type="submit"
          loading={isLoading}
          fullWidth
          h="2.75rem"
          radius="md"
          mt="xs"
          className="!bg-[#BC9BFF] !text-[#1e1e1c] hover:!bg-[#A87CFF] !transition-colors !border-none"
        >
          <Text size="sm" fw={500}>
            {t("signIn")}
          </Text>
        </Button>
      </form>
    </AuthCard>
  );
}
