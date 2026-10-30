import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Field, Notice } from "../components/ui";
import { LanguageSwitch, Logo } from "../components/shell";
import { HOME, useAuth, type Me } from "../lib/auth";

const CITIES = ["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"];
const WORK = ["rider", "home_service", "freelancer", "vendor"];
const emailOk = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
const passOk = (s: string) => s.length >= 10 && /[A-Za-z]/.test(s) && /\d/.test(s);

function PublicFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <Logo />
          <LanguageSwitch compact />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        {children}
      </main>
      <footer className="border-t border-slate-200 py-4 text-center text-xs text-slate-500">EarnScore · {new Date().getFullYear()}</footer>
    </div>
  );
}

export function Landing() {
  const { t } = useTranslation();
  const { me } = useAuth();
  if (me) return <Navigate to={HOME[me.role]} replace />;
  return (
    <PublicFrame>
      <div className="grid items-center gap-8 md:grid-cols-2">
        <div>
          <h1 className="text-3xl font-bold leading-tight text-slate-900 sm:text-4xl">{t("landing.tagline")}</h1>
          <p className="mt-4 text-slate-600">{t("landing.sub")}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/register" className="btn-primary">
              {t("landing.register")}
            </Link>
            <Link to="/login" className="btn-secondary">
              {t("landing.signin")}
            </Link>
          </div>
        </div>
        <ul className="space-y-3">
          {["p1", "p2", "p3"].map((k) => (
            <li key={k} className="card flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-100 text-accent-700" aria-hidden="true">
                ✓
              </span>
              <span className="text-sm text-slate-700">{t(`landing.${k}`)}</span>
            </li>
          ))}
          <li className="px-1 text-xs text-slate-500">{t("auth.privacy")}</li>
        </ul>
      </div>
    </PublicFrame>
  );
}

export function Login() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const { me } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  if (me && !signedIn) return <Navigate to={HOME[me.role]} replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!emailOk(email) || !password) return;
    setSignedIn(true);
    setBusy(true);
    setErr(null);
    try {
      const u = await api<Me>("/auth/login", { body: { email, password } });
      qc.setQueryData(["me"], u);
      const next = params.get("next");
      nav(next && next.startsWith(HOME[u.role]) ? next : HOME[u.role], { replace: true });
    } catch (e) {
      setSignedIn(false);
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <PublicFrame>
      <form onSubmit={submit} className="card mx-auto max-w-md space-y-4" noValidate>
        <h1 className="h1">{t("auth.signin_title")}</h1>
        {err && <Notice tone="error">{err}</Notice>}
        <Field label={t("auth.email")} htmlFor="email" error={touched && !emailOk(email) ? t("auth.err_email") : undefined}>
          <input id="email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>
        <Field label={t("auth.password")} htmlFor="password" error={touched && !password ? t("common.required") : undefined}>
          <input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? t("common.loading") : t("auth.signin_btn")}
        </button>
        <p className="text-sm text-slate-600">
          {t("auth.no_account")}{" "}
          <Link className="font-medium text-accent-700 underline" to="/register">
            {t("landing.register")}
          </Link>
        </p>
      </form>
    </PublicFrame>
  );
}

export function Register() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { me } = useAuth();
  const [f, setF] = useState({ name: "", email: "", password: "", city: "Chennai", work_type: "rider", languages: ["en"] as string[] });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  const [registered, setRegistered] = useState(false);
  if (me && !registered) return <Navigate to={HOME[me.role]} replace />;
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  const errors = {
    name: f.name.trim().length < 2 ? t("auth.err_name") : undefined,
    email: !emailOk(f.email) ? t("auth.err_email") : undefined,
    password: !passOk(f.password) ? t("auth.err_password") : undefined,
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    setRegistered(true);
    setBusy(true);
    setErr(null);
    try {
      const langs = Array.from(new Set([...f.languages, i18n.language]));
      const u = await api<Me>("/auth/register", { body: { ...f, languages: langs, preferred_language: i18n.language } });
      qc.setQueryData(["me"], u);
      nav("/worker/consents", { replace: true });
    } catch (e) {
      setRegistered(false);
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <PublicFrame>
      <form onSubmit={submit} className="card mx-auto max-w-lg space-y-4" noValidate>
        <h1 className="h1">{t("auth.register_title")}</h1>
        {err && <Notice tone="error">{err}</Notice>}
        <Field label={t("auth.name")} htmlFor="name" error={touched ? errors.name : undefined}>
          <input id="name" className="input" autoComplete="name" value={f.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label={t("auth.email")} htmlFor="remail" error={touched ? errors.email : undefined}>
          <input id="remail" className="input" type="email" autoComplete="email" value={f.email} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label={t("auth.password")} htmlFor="rpass" hint={t("auth.password_hint")} error={touched ? errors.password : undefined}>
          <input id="rpass" className="input" type="password" autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("auth.city")} htmlFor="city">
            <select id="city" className="input" value={f.city} onChange={(e) => set("city", e.target.value)}>
              {CITIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Field>
          <Field label={t("auth.work_type")} htmlFor="wt">
            <select id="wt" className="input" value={f.work_type} onChange={(e) => set("work_type", e.target.value)}>
              {WORK.map((w) => (
                <option key={w} value={w}>
                  {t(`work_types.${w}`)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <fieldset>
          <legend className="label">{t("auth.languages")}</legend>
          <div className="flex flex-wrap gap-4">
            {["en", "ta", "hi"].map((l) => (
              <label key={l} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={f.languages.includes(l)}
                  onChange={(e) => set("languages", e.target.checked ? [...f.languages, l] : f.languages.filter((x) => x !== l))}
                />
                {t(`langs.${l}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <p className="text-xs text-slate-500">{t("auth.privacy")}</p>
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? t("common.loading") : t("auth.register_btn")}
        </button>
        <p className="text-sm text-slate-600">
          {t("auth.have_account")}{" "}
          <Link className="font-medium text-accent-700 underline" to="/login">
            {t("landing.signin")}
          </Link>
        </p>
      </form>
    </PublicFrame>
  );
}

export function NotFound() {
  return (
    <PublicFrame>
      <div className="card mx-auto max-w-md text-center">
        <h1 className="h1">Page not found</h1>
        <p className="muted mt-2">The page you opened does not exist or has moved.</p>
        <Link to="/" className="btn-primary mt-4">
          Go to EarnScore
        </Link>
      </div>
    </PublicFrame>
  );
}
