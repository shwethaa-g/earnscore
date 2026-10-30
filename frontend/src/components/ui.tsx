import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin text-accent-600 ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 py-10 text-slate-500" role="status" aria-live="polite">
      <Spinner />
      <span className="text-sm">{label ?? t("common.loading")}</span>
    </div>
  );
}

export function FullPageLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="card border-red-200 bg-red-50">
      <p className="font-medium text-red-800">{t("common.error_title")}</p>
      <p className="mt-1 text-sm text-red-700">{msg}</p>
      {onRetry && (
        <button className="btn-secondary mt-3" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-start gap-2 border-dashed py-8 text-left sm:items-center sm:text-center">
      <svg className="h-8 w-8 text-slate-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path d="M3 7h18M3 12h18M3 17h10" strokeLinecap="round" />
      </svg>
      <p className="font-medium text-slate-800">{title}</p>
      {body && <p className="max-w-md text-sm text-slate-500">{body}</p>}
      {action}
    </div>
  );
}

const BAND_STYLE: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  B: "bg-teal-100 text-teal-800 ring-teal-200",
  C: "bg-amber-100 text-amber-800 ring-amber-200",
  D: "bg-orange-100 text-orange-800 ring-orange-200",
  E: "bg-red-100 text-red-800 ring-red-200",
};

export function BandBadge({ band, size = "sm" }: { band: string; size?: "sm" | "lg" }) {
  const s = size === "lg" ? "h-12 w-12 text-2xl" : "h-7 w-7 text-sm";
  return (
    <span className={`inline-flex ${s} items-center justify-center rounded-lg font-bold ring-1 ${BAND_STYLE[band] ?? "bg-slate-100"}`} aria-label={`Band ${band}`}>
      {band}
    </span>
  );
}

const CONF_STYLE: Record<string, string> = {
  High: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Medium: "bg-amber-50 text-amber-700 ring-amber-200",
  Low: "bg-slate-100 text-slate-700 ring-slate-300",
};

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "teal" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-800 ring-amber-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    teal: "bg-accent-50 text-accent-700 ring-accent-200",
  };
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${tones[tone]}`}>{children}</span>;
}

export function ConfidencePill({ level, label }: { level: string; label?: string }) {
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${CONF_STYLE[level] ?? CONF_STYLE.Low}`}>{label ?? level}</span>;
}

export function Field({ label, htmlFor, hint, error, children }: { label: string; htmlFor: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "success" | "error"; children: ReactNode }) {
  const t = {
    info: "border-sky-200 bg-sky-50 text-sky-900",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
    error: "border-red-200 bg-red-50 text-red-800",
  }[tone];
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${t}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useTranslation();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl sm:p-6 ${wide ? "sm:max-w-5xl" : "sm:max-w-lg"}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button className="btn-ghost -mr-2 -mt-1 px-2" onClick={onClose} aria-label={t("common.close")}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 truncate text-xl font-semibold text-slate-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="h1">{title}</h1>
        {subtitle && <p className="muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
