"use client";

import { Flex, Text, Title, Button } from "@mantine/core";
import AuthCard from "@/ui/elements/Auth/AuthCard";

const ERRORS: Record<string, string> = {
  invalid_state: "登录请求已过期或不匹配，请重新点击登录。",
  access_denied: "你已取消授权，可以重新登录。",
  missing_code: "未收到授权码，请重新登录。",
  not_configured: "登录服务尚未配置完成，请联系管理员。",
  access_control_required: "管理员需要开启知识库访问权限控制。",
  provider_unavailable: "暂时无法连接 WorkBuddy，请稍后重试。",
  token_failed: "获取登录凭证失败，请重新登录。",
  invalid_profile: "未能获取 WorkBuddy 用户身份，请联系管理员。",
  account_disabled: "此账号已被停用，请联系管理员。",
  account_failed: "暂时无法创建账号，请重试。",
};

export default function LocalSignInForm({ errorCode }: { errorCode?: string }) {
  const error = errorCode ? ERRORS[errorCode] || "登录失败，请重新登录。" : null;
  return (
    <AuthCard>
      <Flex className="flex-col gap-[0.75rem] items-center">
        <Title order={2} className="!text-[2.5rem] !font-light !leading-[1.1] !tracking-[-0.04em] !text-[#EDECEA]"
          style={{ fontFamily: '"TWKLausanne", sans-serif' }}>
          登录知识库
        </Title>
        <Text size="sm" className="!text-[#EDECEA]/85 !font-light !text-center">
          使用 WorkBuddy 账号登录
        </Text>
      </Flex>
      {error && (
        <Text role="alert" size="sm" className="w-full px-4 py-3 rounded-lg"
          style={{ color: "#FCA5A5", backgroundColor: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)" }}>
          {error}
        </Text>
      )}
      <Button component="a" href="/oauth/login" fullWidth h="2.75rem" radius="md" mt="xs"
        className="!bg-[#BC9BFF] !text-[#1e1e1c] hover:!bg-[#A87CFF] !transition-colors !border-none">
        Login WorkBuddy
      </Button>
    </AuthCard>
  );
}
