"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useNavbar } from "../NavbarContext";
import NavbarIconLink from "./NavbarIconLink";
import { ReactNode } from "react";
import { useTenant } from "@/modules/tenant/TenantContext";
import isCloudEnvironment from "@/utils/isCloudEnvironment";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";

// Sidebar widths (px). The rail shows icons only; collapsing only applies on
// desktop, matching the Tailwind `sm` breakpoint (640px) used below.
const EXPANDED_WIDTH = 240;
const COLLAPSED_WIDTH = 72;

// -- Icon components for nav items --

function HouseIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function SessionsIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H8l-5 4z" /><line x1="7" y1="8" x2="15" y2="8" /><line x1="7" y1="12" x2="12" y2="12" />
    </svg>
  );
}

function DatabaseIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

function SearchIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function GraphIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="12" cy="18" r="3" />
      <line x1="8.5" y1="7.5" x2="10.5" y2="16" />
      <line x1="15.5" y1="7.5" x2="13.5" y2="16" />
    </svg>
  );
}



function IntegrationsIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="9" height="9" rx="2" /><rect x="13" y="2" width="9" height="9" rx="2" /><rect x="2" y="13" width="9" height="9" rx="2" /><path d="M17.5 13.5v3m0 0v3m0-3h3m-3 0h-3" />
    </svg>
  );
}

function SkillsIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2.1-2.1z" />
    </svg>
  );
}

function KeyIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  );
}

function McpIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={active ? "#BC9BFF" : "rgba(255,255,255,0.5)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M7 9L4 12L7 15" />
      <path d="M17 9L20 12L17 15" />
      <line x1="13" y1="8" x2="11" y2="16" />
    </svg>
  );
}

// -- Navigation data --

// Routes that require the tenant pod — dimmed/locked while it provisions.
const POD_DEPENDENT_LINKS = new Set([
  "/sessions",
  "/datasets",
  "/search",
  "/skills",
  "/knowledge-graph",
]);

interface NavItem {
  text: string;
  link: string;
  icon: (props: { active: boolean }) => ReactNode;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "DATA",
    items: [
      { text: "Overview", link: "/dashboard", icon: HouseIcon },
      { text: "Sessions", link: "/sessions", icon: SessionsIcon },
      { text: "Brain", link: "/datasets", icon: DatabaseIcon },
    ],
  },
  {
    label: "EXPLORE",
    items: [
      { text: "Search", link: "/search", icon: SearchIcon },
      { text: "Skills", link: "/skills", icon: SkillsIcon },
      { text: "Mindmap", link: "/knowledge-graph", icon: GraphIcon },
    ],
  },
  {
    label: "CONNECT",
    items: [
      { text: "Integrations", link: "/integrations", icon: IntegrationsIcon },
      { text: "MCP Access", link: "/mcp-access", icon: McpIcon },
      { text: "API Keys", link: "/api-keys", icon: KeyIcon },
    ],
  },
];

const ZH_NAV_LABELS: Record<string, string> = {
  DATA: "数据", EXPLORE: "探索", CONNECT: "连接",
  Overview: "总览", Sessions: "会话", Brain: "脑库",
  Search: "搜索", Skills: "技能", Mindmap: "脑图",
  Integrations: "集成", "MCP Access": "MCP 接入", "API Keys": "API 密钥",
  "Expand sidebar": "展开侧栏", "Collapse sidebar": "收起侧栏",
  "Close navigation": "关闭导航", "Available once your workspace is ready": "工作区准备就绪后可用",
  "Billing / Pricing": "账单 / 定价",
};

export default function CustomAppShellNavbar() {
  const pathname = usePathname();
  const { language } = useBusinessLanguage();
  const translate = (text: string) => language === "zh" ? ZH_NAV_LABELS[text] || text : text;
  const { isOpen, close, collapsed, toggleCollapsed } = useNavbar();
  const { tenantReady } = useTenant();

  // Collapsing to an icon rail only applies on desktop. On mobile the sidebar
  // is a full-width drawer toggled by the hamburger (isOpen), so whenever the
  // drawer is open it shows full labels. Deriving `railed` from isOpen instead
  // of a media query keeps it deterministic on the server, so the first paint
  // already has the correct width (no flash on hard navigation).
  const railed = collapsed && !isOpen;

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-30 sm:hidden"
          onClick={close}
        />
      )}

      <aside
        className={`
          group flex-shrink-0 flex flex-col
          fixed sm:relative z-40 sm:z-auto h-full sm:h-auto
          transition-[transform,width] sm:translate-x-0
          ${isOpen ? "translate-x-0" : "-translate-x-full sm:translate-x-0"}
        `}
        style={{ width: railed ? COLLAPSED_WIDTH : EXPANDED_WIDTH, maxHeight: "100vh", overflow: "hidden", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(12px)", borderRight: "1px solid rgba(255,255,255,0.08)" }}
      >
        {/* Desktop-only collapse handle: a thin control on the sidebar's right
            edge that fades in on hover (Notion-style). No dedicated header row. */}
        <button
          onClick={toggleCollapsed}
          aria-label={railed ? translate("Expand sidebar") : translate("Collapse sidebar")}
          title={railed ? translate("Expand sidebar") : translate("Collapse sidebar")}
          className="cursor-pointer hidden sm:flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ position: "absolute", top: 8, right: 6, width: 18, height: 44, borderRadius: 6, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", zIndex: 10 }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.12)")}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.06)")}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.6)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: railed ? "rotate(180deg)" : undefined }}>
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        {/* Mobile-only close button (the desktop collapse control is the hover
            handle above, so there is no desktop header row). */}
        <div className="flex sm:hidden items-center justify-end flex-shrink-0 px-3" style={{ height: 40 }}>
          <button
            onClick={close}
            aria-label={translate("Close navigation")}
            className="cursor-pointer"
            style={{ background: "none", border: "none", fontSize: 20, color: "rgba(255,255,255,0.6)", padding: 4 }}
          >
            &#10005;
          </button>
        </div>

        {/* Nav sections */}
        <nav className="flex-1 overflow-y-auto px-3 py-2">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="mb-4">
              {railed ? (
                <div style={{ height: 1, background: "rgba(255,255,255,0.08)", margin: "0 8px 8px" }} />
              ) : (
                <div
                  className="px-3 mb-1"
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: 0.5,
                    color: "rgba(255,255,255,0.3)",
                    textTransform: "uppercase",
                  }}
                >
                  {translate(section.label)}
                </div>
              )}
              {section.items.map((item) => {
                const isActive = pathname === item.link || pathname.startsWith(item.link + "/");
                const locked = !tenantReady && POD_DEPENDENT_LINKS.has(item.link);
                if (locked) {
                  return (
                    <div
                      key={item.link}
                      title={railed ? `${translate(item.text)} — ${translate("Available once your workspace is ready")}` : translate("Available once your workspace is ready")}
                      className={`flex items-center gap-[10px] rounded-[6px] px-3 py-2 text-[14px] ${railed ? "justify-center" : ""}`}
                      style={{ color: "rgba(237,236,234,0.3)", cursor: "not-allowed", userSelect: "none" }}
                      aria-disabled="true"
                    >
                      {item.icon({ active: false })}
                      {!railed && translate(item.text)}
                    </div>
                  );
                }
                return (
                  <NavbarIconLink
                    key={item.link}
                    text={translate(item.text)}
                    link={item.link}
                    isActive={isActive}
                    collapsed={railed}
                    icon={item.icon({ active: isActive })}
                  />
                );
              })}
            </div>
          ))}
        </nav>

        {/* Billing is only available in the cloud app. */}
        {isCloudEnvironment() && (
          <div style={{ padding: 12, borderTop: "1px solid rgba(255,255,255,0.08)", display: "flex", flexDirection: "column", gap: 8 }}>
            <Link
              href="/billing"
              title={railed ? translate("Billing / Pricing") : undefined}
              className="flex items-center justify-center rounded-[8px] w-full"
              style={{
                padding: "10px 12px",
                background: "#BC9BFF",
                color: "#1e1e1c",
                fontSize: 14,
                fontWeight: 500,
                textDecoration: "none",
              }}
              onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "#A988F0")}
              onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "#BC9BFF")}
            >
              {railed ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1e1e1c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" />
                </svg>
              ) : translate("Billing / Pricing")}
            </Link>
          </div>
        )}
      </aside>
    </>
  );
}
