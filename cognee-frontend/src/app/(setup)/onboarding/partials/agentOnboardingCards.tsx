"use client";

import { useState } from "react";
import { CLAUDE_MARKETPLACE_ADD, CLAUDE_PLUGIN_INSTALL, CODEX_HOOKS_ENABLE, CODEX_MARKETPLACE_ADD, CODEX_PLUGIN_INSTALL, UPLOAD_MEMORY_PROMPT, UPLOAD_SAMPLE_PROMPT, RECALL_SAMPLE_PROMPT } from "@/data/prompts";
import { exportEnvVar } from "@/utils/osCommands";
import type { PreferredOs } from "@/ui/layout/OsPreferenceContext";
import { useOnboardingTrackEvent } from "../useOnboardingTrackEvent";
import { useTranslations } from "next-intl";

export interface AgentOnboardingCard {
  title: string;
  description: string;
  node?: React.ReactNode;
}

// Identifies which snippet was copied — `onboarding_creds_copied` fires for every
// copy button on the page (creds, install commands, prompts, /exit), so this is
// the only way to tell a real credentials copy from the rest downstream.
export type OnboardingCopyTarget =
  | "api_credentials"
  | "marketplace_add"
  | "plugin_install"
  | "hooks_enable"
  | "upload_memory_prompt"
  | "upload_sample_prompt"
  | "exit_command"
  | "recall_sample_prompt";

// Single-line code block: shows ONE line, truncates the rest with an ellipsis (…)
// so long commands never wrap or overflow on small screens. `code` is what's
// shown; `toCopy` (when set) is the full multi-line command that's copied.
export function OnboardingInlineCode({ code, toCopy, loading, placeholder = "Preparing…", agent, copyTarget }: {
  code: string; toCopy?: string; loading?: boolean; placeholder?: string; agent?: "claude-code" | "codex"; copyTarget: OnboardingCopyTarget;
}) {
  const [copied, setCopied] = useState(false);
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");
  const copy = () => {
    if (loading) return;
    navigator.clipboard.writeText(toCopy ?? code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    track({ pageName: "Onboarding", eventName: "onboarding_creds_copied", additionalProperties: { copy_target: copyTarget, ...(agent ? { agent } : {}) } });
  };
  return (
    <div
      onClick={copy}
      className="cursor-pointer"
      style={{ background: "#18181B", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "11px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, cursor: loading ? "wait" : "pointer", width: "100%" }}
    >
      <pre style={{ margin: 0, fontSize: 12.5, fontFamily: 'ui-monospace, Menlo, Monaco, "Cascadia Mono", "Segoe UI Mono", "Roboto Mono", monospace', color: loading ? "#585B70" : "rgba(237,236,234,0.85)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1, minWidth: 0 }}>
        <code>{loading ? placeholder : code}</code>
      </pre>
      <button
        onClick={(e) => { e.stopPropagation(); copy(); }}
        className="cursor-pointer"
        style={{ background: "#27272A", border: "1px solid #3F3F46", borderRadius: 4, padding: "4px 8px", fontSize: 11, color: loading ? "rgba(237,236,234,0.35)" : "rgba(237,236,234,0.65)", flexShrink: 0 }}
      >
        {copied ? t("copied") : t("copy")}
      </button>
    </div>
  );
}

// Live connection indicator for the "connect & recall" step: a pulsing dim dot
// while we wait for the agent's first session, flipping to a solid green dot +
// "Connected" once a new session is detected in Cognee Cloud.
export function ConnectStatus({ verified }: { verified: boolean }) {
  const t = useTranslations("Setup");
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
      <span
        className={verified ? undefined : "ob-pulse"}
        style={{
          width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
          background: verified ? "#22C55E" : "rgba(237,236,234,0.4)",
          boxShadow: verified ? "0 0 0 3px rgba(34,197,94,0.18)" : "none",
        }}
      />
      <span style={{ color: verified ? "#22C55E" : "rgba(237,236,234,0.5)" }}>
        {verified ? t("agent.connected") : t("agent.waiting")}
      </span>
    </div>
  );
}

export function buildAgentOnboardingCards(params: {
  agent: "claude-code" | "codex";
  name: string;
  baseUrl: string;
  credsCode: string;
  credsReady: boolean;
  connectVerified: boolean;
  goToDashboard: () => void;
  os: PreferredOs;
}): AgentOnboardingCard[] {
  const t = useTranslations("Setup");
  const { agent, name, baseUrl, credsCode, credsReady, connectVerified, goToDashboard, os } = params;

  const credsCard: AgentOnboardingCard = {
    title: t("agent.credentialsTitle"),
    description: t("agent.credentialsDescription"),
    node: <OnboardingInlineCode code={exportEnvVar(os, "COGNEE_BASE_URL", baseUrl)} toCopy={credsCode} loading={!credsReady} placeholder={t("agent.credentialsPreparing")} agent={agent} copyTarget="api_credentials" />,
  };
  const allSetCard: AgentOnboardingCard = {
    title: t("agent.allSet"),
    description: t("agent.allSetDescription"),
    node: (
      <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 14, borderRadius: 10, background: "rgba(237,236,234,0.04)", border: "1px solid rgba(237,236,234,0.10)" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA" }}>{t("agent.whatHappened")}</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: "19px", color: "rgba(237,236,234,0.6)" }}>
            <li>{t("agent.lifeCycle")}</li>
            <li>{t("agent.sessionEnd")}</li>
            <li>{t("agent.newSession")}</li>
          </ul>
          <div style={{ fontSize: 13, lineHeight: "19px", color: "rgba(237,236,234,0.6)" }}>
            {t("agent.why")}
          </div>
        </div>
        <button onClick={goToDashboard} className="cursor-pointer" style={{ background: "#BC9BFF", border: "none", borderRadius: 8, padding: "11px 32px", fontSize: 14, fontWeight: 500, color: "#1e1e1c", letterSpacing: "-0.01em" }}>
          {t("agent.dashboard")}
        </button>
      </div>
    ),
  };

  return agent === "claude-code"
    ? [
        credsCard,
        {
          title: t("agent.installTitle"),
          description: t("agent.installClaude"),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
              <OnboardingInlineCode code={CLAUDE_MARKETPLACE_ADD} agent={agent} copyTarget="marketplace_add" />
              <OnboardingInlineCode code={CLAUDE_PLUGIN_INSTALL} agent={agent} copyTarget="plugin_install" />
            </div>
          ),
        },
        {
          title: t("agent.uploadTitle"),
          description: t("agent.uploadDescription", { name: "Claude" }),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 14, width: "100%" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.optionA")}</div>
                <OnboardingInlineCode code={UPLOAD_MEMORY_PROMPT} agent={agent} copyTarget="upload_memory_prompt" />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.optionB")}</div>
                <OnboardingInlineCode code={UPLOAD_SAMPLE_PROMPT} agent={agent} copyTarget="upload_sample_prompt" />
              </div>
              <ConnectStatus verified={connectVerified} />
            </div>
          ),
        },
        {
          title: connectVerified ? t("agent.detected") : t("agent.recall"),
          description: connectVerified
            ? t("agent.detectedDescription")
            : t("agent.recallDescription", { name: "Claude" }),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.freshSession")}</div>
                <OnboardingInlineCode code="/exit" agent={agent} copyTarget="exit_command" />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.thenAsk")}</div>
                <OnboardingInlineCode code={RECALL_SAMPLE_PROMPT} agent={agent} copyTarget="recall_sample_prompt" />
              </div>
              <ConnectStatus verified={connectVerified} />
            </div>
          ),
        },
        allSetCard,
      ]
    : [
        credsCard,
        {
          title: t("agent.installTitle"),
          description: t("agent.installCodex"),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
              <OnboardingInlineCode code={CODEX_HOOKS_ENABLE} agent={agent} copyTarget="hooks_enable" />
              <OnboardingInlineCode code={CODEX_MARKETPLACE_ADD} agent={agent} copyTarget="marketplace_add" />
              <OnboardingInlineCode code={CODEX_PLUGIN_INSTALL} agent={agent} copyTarget="plugin_install" />
            </div>
          ),
        },
        {
          title: t("agent.uploadTitle"),
          description: t("agent.uploadDescription", { name }),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 14, width: "100%" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.optionA")}</div>
                <OnboardingInlineCode code={UPLOAD_MEMORY_PROMPT} agent={agent} copyTarget="upload_memory_prompt" />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.optionB")}</div>
                <OnboardingInlineCode code={UPLOAD_SAMPLE_PROMPT} agent={agent} copyTarget="upload_sample_prompt" />
              </div>
              <ConnectStatus verified={connectVerified} />
            </div>
          ),
        },
        {
          title: connectVerified ? t("agent.detected") : t("agent.recall"),
          description: connectVerified
            ? t("agent.detectedDescription")
            : t("agent.recallDescription", { name }),
          node: (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.freshSession")}</div>
                <OnboardingInlineCode code="/exit" agent={agent} copyTarget="exit_command" />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#EDECEA", marginBottom: 6 }}>{t("agent.thenAsk")}</div>
                <OnboardingInlineCode code={RECALL_SAMPLE_PROMPT} agent={agent} copyTarget="recall_sample_prompt" />
              </div>
              <ConnectStatus verified={connectVerified} />
            </div>
          ),
        },
        allSetCard,
      ];
}
