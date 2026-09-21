"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useCogniInstance, useTenant } from "@/modules/tenant/TenantProvider";
import getApiKeys from "@/modules/apiKeys/getApiKeys";
import { TrackPageView, trackEvent } from "@/modules/analytics";
import { copyTextToClipboard, isCloudEnvironment } from "@/utils";
import PageLoading from "@/ui/elements/PageLoading";
import UpgradeBanner from "@/ui/elements/UpgradeBanner";
import { MCP_STDIO_CONFIG, fillTemplate } from "@/data/prompts";
import { notifications } from "@mantine/notifications";

const MONO =
  'ui-monospace, Menlo, Monaco, "Cascadia Mono", "Segoe UI Mono", "Roboto Mono", monospace';

/** Same-origin MCP URL — follows the page host/port like CPD's MCP 接入. */
function mcpHttpUrlFromPage(): string {
  if (typeof window === "undefined") return "http://localhost:3030/mcp";
  return `${window.location.origin}/mcp`;
}

type ConfigTab = "cursor" | "http";

function buildHttpMcpConfig(mcpUrl: string, apiKey: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        cognee: {
          type: "http",
          url: mcpUrl,
          headers: {
            Authorization: `Bearer ${apiKey}`,
          },
        },
      },
    },
    null,
    2,
  );
}

function CopyBtn({
  label,
  onCopy,
  copied,
  primary = false,
}: {
  label: string;
  onCopy: () => void;
  copied: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onCopy}
      className="cursor-pointer"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: primary ? "#6510F4" : "rgba(255,255,255,0.06)",
        border: primary ? "none" : "1px solid rgba(255,255,255,0.12)",
        borderRadius: 8,
        padding: "8px 14px",
        fontSize: 13,
        fontWeight: 500,
        color: primary ? "#fff" : "rgba(237,236,234,0.85)",
        fontFamily: "inherit",
        whiteSpace: "nowrap",
      }}
    >
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path
            d="M3.5 8.5L6.5 11.5L12.5 4.5"
            stroke={primary ? "#fff" : "#22C55E"}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
      {copied ? "Copied" : label}
    </button>
  );
}

export default function McpPage() {
  const { serviceUrl, apiKey: contextApiKey, isInitializing } = useCogniInstance();
  const { hasAccess } = useTenant();
  const isCloud = isCloudEnvironment();

  const [keysLoading, setKeysLoading] = useState(true);
  const [resolvedKey, setResolvedKey] = useState<string>("");
  const [tab, setTab] = useState<ConfigTab>("cursor");
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [mcpHttpUrl, setMcpHttpUrl] = useState("http://localhost:3030/mcp");

  // Keep MCP URL in lock-step with the address bar (LAN IP, localhost, public DNS).
  useEffect(() => {
    const sync = () => setMcpHttpUrl(mcpHttpUrlFromPage());
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener("focus", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("focus", sync);
    };
  }, []);

  useEffect(() => {
    if (isInitializing) return;
    let cancelled = false;

    async function resolveKey() {
      if (contextApiKey) {
        if (!cancelled) {
          setResolvedKey(contextApiKey);
          setKeysLoading(false);
        }
        return;
      }
      try {
        const keys = await getApiKeys();
        const first = keys.find((k) => k.key)?.key ?? "";
        if (!cancelled) setResolvedKey(first);
      } catch (err) {
        console.error("Failed to load API keys for MCP page:", err);
        if (!cancelled) setResolvedKey("");
      } finally {
        if (!cancelled) setKeysLoading(false);
      }
    }

    void resolveKey();
    return () => {
      cancelled = true;
    };
  }, [contextApiKey, isInitializing]);

  const baseUrl = serviceUrl ?? "";
  const displayKey = resolvedKey || "your-api-key";
  const hasRealKey = Boolean(resolvedKey);
  const loadingCreds = isInitializing || keysLoading || !baseUrl;

  const cursorConfig = useMemo(
    () => fillTemplate(MCP_STDIO_CONFIG, baseUrl || "https://your-tenant.aws.cognee.ai", displayKey),
    [baseUrl, displayKey],
  );

  const httpConfig = useMemo(
    () => buildHttpMcpConfig(mcpHttpUrl, displayKey),
    [mcpHttpUrl, displayKey],
  );

  const activeConfig = tab === "cursor" ? cursorConfig : httpConfig;

  async function copy(field: string, text: string) {
    try {
      await copyTextToClipboard(text);
      setCopiedField(field);
      trackEvent({
        pageName: "MCP Access",
        eventName: "mcp_config_copied",
        additionalProperties: { field },
      });
      window.setTimeout(() => {
        setCopiedField((cur) => (cur === field ? null : cur));
      }, 1800);
    } catch (err) {
      console.error("Failed to copy:", err);
      notifications.show({
        title: "Copy failed",
        message: "Could not copy to the clipboard.",
        color: "red",
      });
    }
  }

  if (isInitializing) {
    return (
      <>
        <TrackPageView page="MCP Access" />
        <PageLoading name="MCP Access" />
      </>
    );
  }

  return (
    <div style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 920 }}>
      <TrackPageView page="MCP Access" />
      {!hasAccess && <UpgradeBanner />}

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <h1
          style={{
            fontSize: 20,
            fontWeight: 300,
            color: "#EDECEA",
            margin: 0,
            fontFamily: '"TWKLausanne", sans-serif',
          }}
        >
          MCP Access
        </h1>
        <span style={{ fontSize: 14, color: "rgba(237,236,234,0.55)" }}>
          Copy personal configuration to connect MCP-capable AI clients to Cognee.
        </span>
      </div>

      <div
        style={{
          display: "flex",
          gap: 10,
          background: "rgba(60,20,140,0.55)",
          border: "1px solid rgba(188,155,255,0.35)",
          borderRadius: 8,
          padding: "14px 16px",
          alignItems: "flex-start",
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="rgba(188,155,255,0.85)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ flexShrink: 0, marginTop: 1 }}
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        <span style={{ fontSize: 13, color: "#EDECEA", lineHeight: "20px" }}>
          One config connects Cursor, Claude Desktop, and other MCP clients to your Cognee
          memory. Access follows your account and API key permissions.
        </span>
      </div>

      {!hasRealKey && !keysLoading && (
        <div
          style={{
            display: "flex",
            gap: 10,
            background: "rgba(180, 83, 9, 0.18)",
            border: "1px solid rgba(251, 191, 36, 0.35)",
            borderRadius: 8,
            padding: "14px 16px",
            alignItems: "flex-start",
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#FBBF24"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ flexShrink: 0, marginTop: 1 }}
          >
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span style={{ fontSize: 13, color: "#EDECEA", lineHeight: "20px" }}>
            No API key found yet. Config below uses a placeholder —{" "}
            <Link href="/api-keys" style={{ color: "#BC9BFF", textDecoration: "underline" }}>
              create an API key
            </Link>{" "}
            first, then come back to copy a ready-to-paste config.
          </span>
        </div>
      )}

      <div
        style={{
          background: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 12,
          padding: "20px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#EDECEA" }}>
              Full configuration
            </span>
            <span style={{ fontSize: 12, color: "rgba(237,236,234,0.45)" }}>
              Paste into your client&apos;s MCP config file after copying.
            </span>
          </div>
          <CopyBtn
            label="Copy full config"
            primary
            copied={copiedField === "full"}
            onCopy={() => void copy("full", activeConfig)}
          />
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          {(
            [
              { id: "cursor" as const, label: "Cursor / uvx" },
              { id: "http" as const, label: "HTTP (same origin)" },
            ] as const
          ).map((item) => {
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className="cursor-pointer"
                style={{
                  background: active ? "rgba(188,155,255,0.18)" : "transparent",
                  border: active
                    ? "1px solid rgba(188,155,255,0.45)"
                    : "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 999,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 500,
                  color: active ? "#EDECEA" : "rgba(237,236,234,0.55)",
                  fontFamily: "inherit",
                }}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        {tab === "http" && (
          <div
            style={{
              display: "flex",
              gap: 10,
              background: "rgba(180, 83, 9, 0.12)",
              border: "1px solid rgba(251, 191, 36, 0.28)",
              borderRadius: 8,
              padding: "12px 14px",
              alignItems: "flex-start",
            }}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#FBBF24"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ flexShrink: 0, marginTop: 1 }}
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span style={{ fontSize: 12.5, color: "rgba(237,236,234,0.75)", lineHeight: 1.55 }}>
              URL follows this page&apos;s address in real time ({mcpHttpUrl}). Requires the MCP
              container (`docker compose --profile mcp up`).
            </span>
          </div>
        )}

        <pre
          style={{
            margin: 0,
            background: "#18181B",
            borderRadius: 8,
            padding: "14px 16px",
            overflowX: "auto",
            fontFamily: MONO,
            fontSize: 12.5,
            lineHeight: 1.7,
            color: loadingCreds ? "rgba(237,236,234,0.45)" : "#EDECEA",
            whiteSpace: "pre",
          }}
        >
          {activeConfig}
        </pre>
      </div>

      <div
        style={{
          background: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 12,
          padding: "20px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#EDECEA" }}>Service addresses</span>
          <span style={{ fontSize: 12, color: "rgba(237,236,234,0.45)" }}>
            Individual endpoints you can paste into clients that ask for a URL only.
          </span>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 16,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "rgba(237,236,234,0.55)" }}>
              API base URL
            </span>
            <div
              style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 8,
                padding: "10px 14px",
                fontFamily: MONO,
                fontSize: 13,
                color: baseUrl ? "#EDECEA" : "rgba(237,236,234,0.35)",
                wordBreak: "break-all",
                minHeight: 42,
              }}
            >
              {baseUrl || (isCloud ? "Provisioning…" : "Unavailable")}
            </div>
            <CopyBtn
              label="Copy"
              copied={copiedField === "api"}
              onCopy={() => {
                if (!baseUrl) return;
                void copy("api", baseUrl);
              }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "rgba(237,236,234,0.55)" }}>
              MCP HTTP (follows page URL)
            </span>
            <div
              style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 8,
                padding: "10px 14px",
                fontFamily: MONO,
                fontSize: 13,
                color: "#EDECEA",
                wordBreak: "break-all",
                minHeight: 42,
              }}
            >
              {mcpHttpUrl}
            </div>
            <CopyBtn
              label="Copy"
              copied={copiedField === "mcp-http"}
              onCopy={() => void copy("mcp-http", mcpHttpUrl)}
            />
          </div>
        </div>
      </div>

      <p style={{ margin: 0, fontSize: 12, color: "rgba(237,236,234,0.4)", lineHeight: 1.6 }}>
        Keep your API key private — it represents your account permissions. Do not share it, and
        re-copy this configuration after rotating keys.
      </p>
    </div>
  );
}
