export function inr(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

const LOCALES: Record<string, string> = { en: "en-IN", ta: "ta-IN", hi: "hi-IN" };

export function fmtDate(iso: string | null | undefined, lang = "en"): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString(LOCALES[lang] ?? "en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function shortWeek(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
