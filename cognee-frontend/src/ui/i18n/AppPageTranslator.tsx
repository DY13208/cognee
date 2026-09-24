"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { pageCopyZh } from "./pageCopy";

const originalText = new WeakMap<Text, string>();
const originalAttributes = new WeakMap<Element, Map<string, string>>();
const attributes = ["placeholder", "title", "aria-label"];

// Short UI labels that also appear as user-authored names/status chips.
// Only translate them when they sit in chrome (nav/buttons/headings), not in
// free-form content nodes where a dataset named "Key" would get rewritten.
const AMBIGUOUS_KEYS = new Set([
  "Name", "Key", "Type", "Size", "Status", "Default", "Open", "Copy", "Copied",
  "all", "Session", "Prompt", "Email", "Password", "Connected", "Ready", "Empty",
  "Agents", "Connect", "History", "Metadata", "Documents", "Description",
]);

const SAFE_AMBIGUOUS_PARENT =
  "button, a, label, th, h1, h2, h3, h4, nav, header, [role='button'], [role='menuitem'], [role='heading'], [role='tab']";

function translated(source: string): string {
  const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(source);
  if (!match) return source;
  const key = match[2].replace(/\s+/g, " ");
  const replacement = pageCopyZh[key];
  return replacement ? `${match[1]}${replacement}${match[3]}` : source;
}

function isAmbiguousSafe(node: Text, source: string): boolean {
  const key = source.replace(/\s+/g, " ").trim();
  if (!AMBIGUOUS_KEYS.has(key)) return true;
  return !!node.parentElement?.closest(SAFE_AMBIGUOUS_PARENT);
}

function applyText(node: Text, chinese: boolean) {
  const current = node.nodeValue || "";
  const previous = originalText.get(node);
  const source = previous && (current === previous || current === translated(previous)) ? previous : current;
  if (translated(source) === source) return;
  if (!isAmbiguousSafe(node, source)) return;
  originalText.set(node, source);
  const next = chinese ? translated(source) : source;
  if (current !== next) node.nodeValue = next;
}

function applyAttributes(element: Element, chinese: boolean) {
  const stored = originalAttributes.get(element) || new Map<string, string>();
  for (const name of attributes) {
    const current = element.getAttribute(name);
    if (current === null) continue;
    const previous = stored.get(name);
    const source = previous && (current === previous || current === translated(previous)) ? previous : current;
    if (translated(source) === source) continue;
    stored.set(name, source);
    const next = chinese ? translated(source) : source;
    if (current !== next) element.setAttribute(name, next);
  }
  if (stored.size) originalAttributes.set(element, stored);
}

function applyTree(root: Node, chinese: boolean) {
  if (root instanceof Element) {
    if (root.matches("script,style,code,pre,textarea,[contenteditable='true'],[data-no-i18n]")) return;
    applyAttributes(root, chinese);
  }
  if (root instanceof Text) {
    if (root.parentElement?.closest("script,style,code,pre,textarea,[contenteditable='true'],[data-no-i18n]")) return;
    applyText(root, chinese);
    return;
  }
  for (const child of root.childNodes) applyTree(child, chinese);
}

// Legacy pages still contain fixed English JSX copy. Translate only phrases
// listed in pageCopyZh; unknown text and user-created content stay untouched.
// The observer handles page data loading and React updating an existing label.
export default function AppPageTranslator() {
  const pathname = usePathname();
  const { language } = useBusinessLanguage();

  useEffect(() => {
    if (pathname === "/knowledge-graph" || pathname === "/business") return;
    const root = document.querySelector("[data-app-page]");
    if (!root) return;
    const chinese = language === "zh";
    applyTree(root, chinese);
    const observer = new MutationObserver((changes) => {
      for (const change of changes) {
        if (change.type === "characterData") applyTree(change.target, chinese);
        else if (change.type === "attributes") applyTree(change.target, chinese);
        else for (const node of change.addedNodes) applyTree(node, chinese);
      }
    });
    observer.observe(root, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: attributes,
    });
    return () => observer.disconnect();
  }, [language, pathname]);

  return null;
}
