import { DEFAULT_LOCALE, type Locale } from "@/i18n/config";

export function formatDate(dateStr?: string, withTime = false, locale: Locale = DEFAULT_LOCALE): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  const date = d.toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" });
  if (!withTime) return date;
  const time = d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${date}, ${time}`;
}

// Filenames can arrive percent-encoded (sometimes multiply); decode until
// stable, falling back to the raw name if decoding throws.
export function decodeFilename(name: string): string {
  try {
    let decoded = name;
    let prev: string;
    do {
      prev = decoded;
      decoded = decodeURIComponent(decoded);
    } while (decoded !== prev);
    return decoded;
  } catch {
    return name;
  }
}

export function formatFileSize(bytes?: number, locale: Locale = DEFAULT_LOCALE): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(bytes / 1024)} KB`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MB`;
}
