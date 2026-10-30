import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth, type Role } from "../lib/auth";
import { LANGS, type Lang } from "../i18n";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 font-semibold text-slate-900">
      <svg className="h-7 w-7" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="#0f7a6b" />
        <path d="M8 21l5-6 4 3 7-9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>EarnScore</span>
    </Link>
  );
}

export function LanguageSwitch({ compact }: { compact?: boolean }) {
  const { t, i18n } = useTranslation();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className={compact ? "sr-only" : "text-slate-600"}>{t("common.language")}</span>
      <select
        className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
        value={i18n.language}
        onChange={(e) => i18n.changeLanguage(e.target.value as Lang)}
        aria-label={t("common.language")}
      >
        {LANGS.map((l) => (
          <option key={l} value={l}>
            {t(`langs.${l}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

const NAV: Record<Role, { to: string; key: string }[]> = {
  worker: [
    { to: "/worker", key: "nav.passport" },
    { to: "/worker/sources", key: "nav.sources" },
    { to: "/worker/consents", key: "nav.consents" },
    { to: "/worker/improve", key: "nav.improve" },
    { to: "/worker/share", key: "nav.share" },
    { to: "/worker/disputes", key: "nav.disputes" },
    { to: "/worker/profile", key: "nav.profile" },
  ],
  officer: [
    { to: "/officer", key: "nav.queue" },
    { to: "/officer/portfolio", key: "nav.portfolio" },
    { to: "/officer/disputes", key: "nav.disputes_inbox" },
  ],
  admin: [
    { to: "/admin", key: "nav.models" },
    { to: "/admin/validation", key: "nav.validation" },
    { to: "/admin/fairness", key: "nav.fairness" },
    { to: "/admin/drift", key: "nav.drift" },
    { to: "/admin/overrides", key: "nav.overrides" },
    { to: "/admin/audit", key: "nav.audit" },
    { to: "/admin/users", key: "nav.users" },
    { to: "/admin/disputes", key: "nav.disputes_inbox" },
  ],
};

const ROLE_LABEL: Record<Role, string> = { worker: "Worker", officer: "Credit officer", admin: "Auditor / admin" };

export function AppShell({ role }: { role: Role }) {
  const { t } = useTranslation();
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [loc.pathname]);
  const items = NAV[role];
  const wide = role !== "worker";
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-accent-50 text-accent-800" : "text-slate-700 hover:bg-slate-100"}`;
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className={`mx-auto flex h-14 items-center justify-between gap-3 px-4 ${wide ? "max-w-7xl" : "max-w-5xl"}`}>
          <div className="flex min-w-0 items-center gap-3">
            <Logo to={items[0].to} />
            <span className="hidden truncate text-xs text-slate-500 sm:inline">
              {ROLE_LABEL[role]}
              {me?.lender ? ` · ${me.lender.name}` : ""}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {role === "worker" && <LanguageSwitch compact />}
            <span className="hidden max-w-[10rem] truncate text-sm text-slate-600 md:inline">{me?.name}</span>
            <button
              className="btn-ghost hidden px-3 sm:inline-flex"
              onClick={async () => {
                await logout();
                nav("/login");
              }}
            >
              {t("common.signout")}
            </button>
            <button className="btn-secondary px-3 lg:hidden" aria-expanded={open} aria-controls="side-nav" onClick={() => setOpen((v) => !v)}>
              {t("common.menu")}
            </button>
          </div>
        </div>
      </header>
      <div className={`mx-auto flex gap-6 px-4 py-5 ${wide ? "max-w-7xl" : "max-w-5xl"}`}>
        <nav
          id="side-nav"
          aria-label="Main"
          className={`${open ? "fixed inset-x-0 top-14 z-20 block border-b border-slate-200 bg-white p-3 shadow-md" : "hidden"} lg:static lg:block lg:w-52 lg:shrink-0 lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none`}
        >
          <ul className="space-y-1">
            {items.map((i) => (
              <li key={i.to}>
                <NavLink to={i.to} end={i.to === items[0].to} className={linkCls}>
                  {t(i.key)}
                </NavLink>
              </li>
            ))}
            <li className="pt-2 sm:hidden">
              <button
                className="btn-secondary w-full"
                onClick={async () => {
                  await logout();
                  nav("/login");
                }}
              >
                {t("common.signout")}
              </button>
            </li>
          </ul>
        </nav>
        <main id="main" className="min-w-0 flex-1" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

const SPEECH_LANG: Record<string, string> = { en: "en-IN", ta: "ta-IN", hi: "hi-IN" };

export function ReadAloud({ text }: { text: string }) {
  const { t, i18n } = useTranslation();
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  useEffect(() => () => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);
  if (!supported) return null;
  const toggle = () => {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = SPEECH_LANG[i18n.language] ?? "en-IN";
    const voice = synth.getVoices().find((v) => v.lang.toLowerCase().startsWith(u.lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  };
  return (
    <button className="btn-secondary px-3 py-1.5 text-xs" onClick={toggle} aria-pressed={speaking}>
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M11 5L6 9H2v6h4l5 4V5z" />
        {speaking ? <path d="M22 9l-6 6M16 9l6 6" /> : <path d="M15.5 8.5a5 5 0 010 7M19 5a10 10 0 010 14" />}
      </svg>
      {speaking ? t("common.stop_reading") : t("common.read_aloud")}
    </button>
  );
}

export function Section({ title, children, actions, id }: { title: ReactNode; children: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <section className="card" aria-labelledby={id}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="h2" id={id}>
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
