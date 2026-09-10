export { default as handleServerErrors } from "./handleServerErrors";
export { default as useBoolean } from "./useBoolean";
export { default as useOutsideClick } from "./useOutsideClick";
export { default as isCloudEnvironment } from "./isCloudEnvironment";

/**
 * Copy text to the clipboard.
 *
 * `navigator.clipboard` only works in a secure context (HTTPS or localhost).
 * Self-hosted UIs opened via LAN IP over plain HTTP need a textarea fallback.
 * Cleanup must tolerate the node already being gone (React re-render, browser
 * extensions) — otherwise `removeChild` throws NotFoundError.
 */
export async function copyTextToClipboard(text: string): Promise<void> {
  if (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof navigator !== "undefined" &&
    navigator.clipboard?.writeText
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the legacy path (permissions / older browsers).
    }
  }

  if (typeof document === "undefined") {
    throw new Error("Clipboard is not available in this environment.");
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  // Keep off-screen and out of the accessibility tree / layout thrash.
  textarea.setAttribute("aria-hidden", "true");
  textarea.tabIndex = -1;
  textarea.style.cssText =
    "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;margin:0;" +
    "border:none;outline:none;box-shadow:none;background:transparent;opacity:0;";

  document.body.appendChild(textarea);

  const previousRange =
    typeof document.getSelection === "function" ? (() => {
      const selection = document.getSelection();
      if (!selection || selection.rangeCount === 0) return null;
      return selection.getRangeAt(0);
    })() : null;

  try {
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    if (!ok) throw new Error("document.execCommand('copy') failed");
  } finally {
    // Prefer Node.remove() — no parent required. Guard anyway for older
    // engines / nodes already detached by React or extensions.
    try {
      if (typeof textarea.remove === "function") {
        textarea.remove();
      } else if (textarea.parentNode) {
        textarea.parentNode.removeChild(textarea);
      }
    } catch {
      // Ignore: node already detached.
    }

    if (previousRange && typeof document.getSelection === "function") {
      const selection = document.getSelection();
      if (selection) {
        try {
          selection.removeAllRanges();
          selection.addRange(previousRange);
        } catch {
          // Ignore selection restore failures.
        }
      }
    }
  }
}
