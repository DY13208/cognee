"use client";

import { t, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";

const PAGE_NAME_ZH: Record<string, string> = {
  Overview: "总览",
  Brain: "脑库",
  Brains: "脑库",
  Sessions: "会话",
  Search: "搜索",
  Skills: "技能",
  Mindmap: "脑图",
  Integrations: "集成",
  "API Keys": "API 密钥",
  "MCP Access": "MCP 接入",
  Settings: "设置",
  Files: "文件",
  Workspace: "工作区",
  Dashboard: "总览",
};

export default function PageLoading({ name }: { name: string }) {
  const { language } = useBusinessLanguage();
  const label = language === "zh" ? PAGE_NAME_ZH[name] || name : name;
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      gap: 14,
    }}>
      <style>{`
        @keyframes pl-spin { to { transform: rotate(360deg); } }
        @keyframes pl-fade { 0%,100%{opacity:0.35} 50%{opacity:0.9} }
      `}</style>

      {/* Ring spinner */}
      <svg
        width="28" height="28" viewBox="0 0 28 28" fill="none"
        style={{ animation: "pl-spin 0.9s linear infinite", flexShrink: 0 }}
      >
        <circle cx="14" cy="14" r="11" stroke="rgba(255,255,255,0.1)" strokeWidth="2.5" />
        <path
          d="M14 3 a11 11 0 0 1 11 11"
          stroke="rgba(188,155,255,0.60)"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>

      {/* Page name */}
      <span style={{
        fontSize: 13,
        fontWeight: 500,
        color: "rgba(237,236,234,0.5)",
        letterSpacing: "0.01em",
        animation: "pl-fade 1.8s ease-in-out infinite",
      }}>
        {name ? label : t(language, "Loading…", "加载中…")}
      </span>
    </div>
  );
}
