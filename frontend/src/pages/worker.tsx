import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { EvidenceTable, type LedgerRow } from "../components/EvidenceTable";
import { PillarBar, SeasonalityChart, TrendChart } from "../components/charts";
import { ReadAloud, Section } from "../components/shell";
import { BandBadge, ConfidencePill, EmptyState, ErrorState, Field, Loading, Modal, Notice, PageHeader, Pill, Stat } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtDate, inr, pct } from "../lib/format";


function useLang() {
  const { i18n } = useTranslation();
  return i18n.language as "en" | "ta" | "hi";
}

// ------------------------------------------------------------------ Passport

export function Passport() {
  const { t } = useTranslation();
  const lang = useLang();
  const q = useQuery({ queryKey: ["passport", lang], queryFn: () => api("/worker/passport", { params: { lang } }) });
  const [evidence, setEvidence] = useState<{ title: string; params: Record<string, string | number> } | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (p.empty)
    return (
      <>
        <PageHeader title={t("passport.title")} />
        <EmptyState title={t("passport.empty_title")} body={t("passport.empty_body")} action={<Link to="/worker/sources" className="btn-primary mt-2">{t("passport.add_source")}</Link>} />
      </>
    );
  const strengths = p.reasons.filter((r: any) => r.direction === "positive");
  const weaknesses = p.reasons.filter((r: any) => r.direction === "negative");
  const trend = p.trend as { as_of: string; score: number; band: string }[];
  const first = trend[0]?.score;
  const last = trend[trend.length - 1]?.score;
  const trendText = trend.length < 2 ? "" : last > first ? t("passport.trend_up", { a: first, b: last }) : last < first ? t("passport.trend_down", { a: first, b: last }) : t("passport.trend_flat", { a: first });
  const summary = [
    `${t("passport.score")} ${p.score} ${t("passport.out_of")}.`,
    p.show_band ? `${t("passport.band")} ${p.band}.` : p.sufficiency_message,
    t(`passport.conf_${p.confidence}`) + ".",
    `${t("passport.safe_emi")}: ${inr(p.safe_emi)}.`,
    ...p.reasons.slice(0, 4).map((r: any) => r.text),
  ].join(" ");
  const dsi = p.dsi;
  return (
    <div className="space-y-4">
      <PageHeader title={t("passport.title")} subtitle={t("passport.as_of", { date: fmtDate(p.as_of, lang) })} actions={<ReadAloud text={summary} />} />

      <section className="card" aria-label={t("passport.score")}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="flex items-center gap-4">
            <div className="flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-2xl bg-accent-50 ring-1 ring-accent-200">
              <span className="text-3xl font-bold tabular-nums text-accent-800">{p.score}</span>
              <span className="text-[11px] text-accent-700">{t("passport.out_of")}</span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                {p.show_band ? <BandBadge band={p.band} size="lg" /> : null}
                <ConfidencePill level={p.confidence} label={t(`passport.conf_${p.confidence}`)} />
              </div>
              {!p.show_band && <p className="max-w-xs text-xs text-slate-500">{t("passport.no_band")}</p>}
            </div>
          </div>
          <div className="grid flex-1 grid-cols-2 gap-4 sm:border-l sm:border-slate-100 sm:pl-5">
            <Stat label={t("passport.safe_emi")} value={inr(p.safe_emi)} sub={t("passport.safe_emi_hint")} />
            <Stat label={t("passport.bad_week")} value={inr(p.f20)} sub={`${t("passport.essentials_total")}: ${inr(p.e_ess)}`} />
          </div>
        </div>
        {p.sufficiency_message && <div className="mt-4"><Notice tone="warn">{p.sufficiency_message}</Notice></div>}
        {p.capacity_warning && <div className="mt-3"><Notice tone="warn">{t("passport.capacity_warning")}</Notice></div>}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("passport.pillars_title")}>
          <p className="muted mb-2">{t("passport.pillars_sub")}</p>
          <div className="space-y-1">
            {p.pillars.map((pl: any) => (
              <PillarBar
                key={pl.pillar}
                score={pl.score}
                label={t(`passport.pillar.${pl.pillar}`)}
                desc={t(`passport.pillar_desc.${pl.pillar}`)}
                weight={t("passport.weight", { w: Math.round(pl.weight * 100) })}
                onClick={() => setEvidence({ title: t(`passport.pillar.${pl.pillar}`), params: { pillar: pl.pillar } })}
              />
            ))}
          </div>
        </Section>

        <Section title={t("passport.reasons_title")}>
          {[{ k: "strengths", rows: strengths, tone: "text-emerald-700" }, { k: "weaknesses", rows: weaknesses, tone: "text-orange-700" }].map((g) =>
            g.rows.length ? (
              <div key={g.k} className="mb-3">
                <h3 className={`mb-1 text-xs font-semibold uppercase tracking-wide ${g.tone}`}>{t(`passport.${g.k}`)}</h3>
                <ul className="space-y-2">
                  {g.rows.slice(0, 5).map((r: any) => (
                    <li key={r.id} className="rounded-lg border border-slate-100 p-2">
                      <p className="text-sm text-slate-800">{r.text}</p>
                      <div className="mt-1 flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-500">{t(`passport.pillar.${r.pillar}`)}</span>
                        {r.evidence_count > 0 && (
                          <button className="text-xs font-medium text-accent-700 underline" onClick={() => setEvidence({ title: r.text, params: { reason_id: r.id } })}>
                            {t("passport.see_evidence")} ({r.evidence_count})
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
        </Section>
      </div>

      {p.watchouts.length > 0 && (
        <Section title={t("passport.watchouts_title")}>
          <ul className="space-y-2">
            {p.watchouts.map((w: any) => (
              <li key={w.code}>
                <Notice tone="warn">{w.text}</Notice>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={t("passport.season_title")}>
        <p className="mb-2 text-sm font-medium text-slate-800">{t("passport.season_finding", { raw: pct(p.volatility.raw), res: pct(p.volatility.unexplained) })}</p>
        <SeasonalityChart series={p.series} labels={{ raw: t("passport.raw"), adjusted: t("passport.adjusted") }} />
        <p className="muted mt-2">{t(`passport.method_${p.seasonality_method}`)}</p>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("passport.trend_title")}>
          {trendText && <p className="mb-2 text-sm font-medium text-slate-800">{trendText}</p>}
          <TrendChart points={trend} scoreLabel={t("passport.score")} />
        </Section>
        <Section title={t("passport.dsi_title")}>
          <p className="muted mb-3">{t("passport.dsi_sub")}</p>
          <ul className="space-y-3 text-sm">
            {[
              { label: t("passport.dsi_months", { n: dsi.inputs.months }), v: dsi.parts.months / 0.4 },
              { label: t("passport.dsi_sources", { n: dsi.inputs.sources }), v: dsi.parts.sources / 0.3 },
              { label: t("passport.dsi_reconcile", { p: pct(dsi.inputs.reconcile_rate) }), v: dsi.parts.reconcile_rate / 0.3 },
            ].map((x) => (
              <li key={x.label}>
                <div className="flex justify-between"><span>{x.label}</span><span className="tabular-nums text-slate-500">{pct(x.v)}</span></div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-sky-500" style={{ width: `${Math.max(2, x.v * 100)}%` }} /></div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm">
            DSI <span className="font-semibold tabular-nums">{dsi.dsi.toFixed(2)}</span> · <ConfidencePill level={p.confidence} label={t(`passport.conf_${p.confidence}`)} />
          </p>
        </Section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("passport.recon_title")}>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ["matched", `${p.reconciliation.matched} / ${p.reconciliation.payouts}`],
              ["unmatched", p.reconciliation.unmatched_payouts],
              ["self_excluded", p.reconciliation.self_transfers_excluded],
              ["refunds_excluded", p.reconciliation.refunds_excluded],
              ["loans_excluded", p.reconciliation.loans_excluded],
              ["earned_total", inr(p.reconciliation.earned_total)],
            ].map(([k, v]) => (
              <div key={k as string}>
                <dt className="text-xs text-slate-500">{t(`passport.${k}`)}</dt>
                <dd className="font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        </Section>
        <Section title={t("passport.essentials_title")}>
          <ul className="space-y-1 text-sm">
            {["rent", "utilities", "fuel", "emi"].map((k) => (
              <li key={k} className="flex justify-between">
                <span>{t(`passport.ess.${k}`)}</span>
                <span className="tabular-nums">{inr(p.e_ess_parts[k])} {t("common.per_week")}</span>
              </li>
            ))}
            <li className="flex justify-between border-t border-slate-100 pt-1 font-semibold">
              <span>{t("passport.essentials_total")}</span>
              <span className="tabular-nums">{inr(p.e_ess)}</span>
            </li>
          </ul>
          <Link to="/worker/sources#transactions" className="mt-3 inline-block text-xs font-medium text-accent-700 underline">{t("passport.edit_essentials")}</Link>
        </Section>
      </div>

      <EvidenceModal snapshotId={p.snapshot_id} state={evidence} onClose={() => setEvidence(null)} />
    </div>
  );
}

function EvidenceModal({ snapshotId, state, onClose }: { snapshotId: number; state: { title: string; params: Record<string, string | number> } | null; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["evidence", snapshotId, state?.params],
    queryFn: () => api(`/worker/passport/${snapshotId}/evidence`, { params: state!.params }),
    enabled: !!state,
  });
  return (
    <Modal open={!!state} title={t("passport.evidence_title")} onClose={onClose} wide>
      {state && <p className="mb-3 text-sm text-slate-700">{state.title}</p>}
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : <EvidenceTable rows={(q.data?.rows ?? []) as LedgerRow[]} />}
    </Modal>
  );
}

// ------------------------------------------------------------------ Sources

export function Sources() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const sq = useQuery({ queryKey: ["sources"], queryFn: () => api("/worker/sources") });
  const cq = useQuery({ queryKey: ["consents"], queryFn: () => api("/worker/consents") });
  const [mapping, setMapping] = useState<number | null>(null);
  const [del, setDel] = useState<any>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "warn"; text: string } | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["sources"] });
    qc.invalidateQueries({ queryKey: ["passport"] });
    qc.invalidateQueries({ queryKey: ["ledger"] });
    qc.invalidateQueries({ queryKey: ["consents"] });
    qc.invalidateQueries({ queryKey: ["recourse"] });
  };
  const delM = useMutation({
    mutationFn: (id: number) => api(`/worker/sources/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setDel(null);
      refresh();
    },
  });
  if (sq.isLoading || cq.isLoading) return <Loading />;
  if (sq.error) return <ErrorState error={sq.error} onRetry={() => sq.refetch()} />;
  const data = sq.data;
  return (
    <div className="space-y-4">
      <PageHeader title={t("sources.title")} subtitle={t("sources.sub")} />
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      <UploadForm
        consents={cq.data?.consents ?? []}
        scopes={cq.data?.scopes ?? {}}
        platforms={data.platforms}
        maxMb={data.max_upload_mb}
        onStart={() => setMsg(null)}
        onDone={(s) => {
          refresh();
          if (s.status === "needs_mapping") setMapping(s.id);
          else if (s.status === "processed") setMsg({ tone: "success", text: t("sources.success", { n: s.parsed_count }) });
          else setMsg({ tone: "error", text: s.error });
        }}
      />
      <Section title={t("sources.aa_title")}>
        <p className="text-sm text-slate-600">{data.aa.message}</p>
      </Section>
      <Section title={t("sources.list_title")}>
        {data.sources.length === 0 ? (
          <p className="muted">{t("sources.empty")}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.sources.map((s: any) => (
              <li key={s.id} className="py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{s.label}</p>
                    <p className="text-xs text-slate-500">
                      {s.kind === "bank_statement" ? t("sources.bank") : t("sources.platform_stmt")} · {s.file?.name} {s.account_ref && `· ${s.account_ref}`}
                    </p>
                  </div>
                  <Pill tone={s.status === "processed" ? "green" : s.status === "needs_mapping" ? "amber" : s.status === "failed" ? "red" : "slate"}>
                    {t(`sources.status.${s.status}`)}
                  </Pill>
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  {t("sources.parsed", { n: s.parsed_count })} · {t("sources.skipped", { n: s.skipped_count })} · {t("sources.duplicates", { n: s.duplicate_count })}
                </p>
                {s.error && <p className="mt-1 text-xs text-red-700">{s.error}</p>}
                {s.delete_after && <p className="mt-1 text-xs text-amber-700">{t("sources.deletion_scheduled", { date: fmtDate(s.delete_after) })}</p>}
                {s.skipped_rows?.length > 0 && (
                  <details className="mt-1 text-xs">
                    <summary className="cursor-pointer text-slate-600">{t("sources.skipped_rows")}</summary>
                    <ul className="mt-1 max-h-32 overflow-y-auto text-slate-500">
                      {s.skipped_rows.map((r: any) => (
                        <li key={r.row}>{t("sources.row", { n: r.row })}: {r.reason}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  {(s.status === "needs_mapping" || s.status === "processed") && (
                    <button className="btn-secondary px-3 py-1 text-xs" onClick={() => setMapping(s.id)}>{t("sources.open_mapping")}</button>
                  )}
                  <button className="btn-danger px-3 py-1 text-xs" onClick={() => setDel(s)}>{t("common.delete")}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Ledger />
      {mapping && <MappingModal id={mapping} onClose={() => setMapping(null)} onDone={(s) => { setMapping(null); refresh(); setMsg({ tone: s.status === "processed" ? "success" : "error", text: s.status === "processed" ? t("sources.success", { n: s.parsed_count }) : s.error }); }} />}
      <Modal open={!!del} title={t("common.delete")} onClose={() => setDel(null)}>
        <p className="text-sm text-slate-700">{t("sources.delete_confirm")}</p>
        <p className="mt-2 text-sm font-medium">{del?.label}</p>
        {delM.error && <div className="mt-2"><Notice tone="error">{(delM.error as Error).message}</Notice></div>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setDel(null)}>{t("common.cancel")}</button>
          <button className="btn-danger" disabled={delM.isPending} onClick={() => delM.mutate(del.id)}>{t("common.delete")}</button>
        </div>
      </Modal>
    </div>
  );
}

function UploadForm({ consents, scopes, platforms, maxMb, onStart, onDone }: { consents: any[]; scopes: Record<string, string>; platforms: string[]; maxMb: number; onStart: () => void; onDone: (s: any) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [kind, setKind] = useState<"bank_statement" | "platform_statement">("bank_statement");
  const [platform, setPlatform] = useState("");
  const [label, setLabel] = useState("");
  const [last4, setLast4] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = consents.filter((c) => c.status === "active" && c.source_kind === kind);
  const [consentId, setConsentId] = useState<number | "">("");
  const chosen = active.find((c) => c.id === consentId) ?? active[0];
  const grant = useMutation({
    mutationFn: () => api("/worker/consents", { body: { source_kind: kind, purpose: "income_assessment" } }),
    onSuccess: (c: any) => {
      qc.invalidateQueries({ queryKey: ["consents"] });
      setConsentId(c.id);
    },
  });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    onStart();
    if (!file) return setErr(t("common.required") + ": " + t("sources.file"));
    if (file.size > maxMb * 1024 * 1024) return setErr(t("sources.file_hint", { mb: maxMb }));
    if (kind === "platform_statement" && !platform) return setErr(t("common.required") + ": " + t("sources.platform"));
    if (!chosen) return setErr(t("sources.no_consent"));
    const fd = new FormData();
    fd.set("file", file);
    fd.set("kind", kind);
    fd.set("consent_id", String(chosen.id));
    fd.set("label", label);
    fd.set("account_ref", last4);
    fd.set("platform", platform);
    setBusy(true);
    try {
      const s = await api("/worker/sources", { form: fd });
      setFile(null);
      setLabel("");
      setLast4("");
      (document.getElementById("upload-file") as HTMLInputElement | null)?.value && ((document.getElementById("upload-file") as HTMLInputElement).value = "");
      onDone(s);
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="card space-y-4" onSubmit={submit} noValidate>
      <h2 className="h2">{t("sources.upload_title")}</h2>
      {err && <Notice tone="error">{err}</Notice>}
      <fieldset>
        <legend className="label">{t("sources.kind")}</legend>
        <div className="flex flex-wrap gap-4">
          {(["bank_statement", "platform_statement"] as const).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="radio" name="kind" checked={kind === k} onChange={() => { setKind(k); setConsentId(""); }} />
              {k === "bank_statement" ? t("sources.bank") : t("sources.platform_stmt")}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        {kind === "platform_statement" ? (
          <Field label={t("sources.platform")} htmlFor="plat">
            <select id="plat" className="input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="">{t("sources.choose")}</option>
              {platforms.map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
        ) : (
          <Field label={`${t("sources.account_last4")} (${t("common.optional")})`} htmlFor="last4" hint={t("sources.account_hint")}>
            <input id="last4" className="input" inputMode="numeric" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, ""))} />
          </Field>
        )}
        <Field label={`${t("sources.label")} (${t("common.optional")})`} htmlFor="label" hint={t("sources.label_hint")}>
          <input id="label" className="input" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} />
        </Field>
      </div>
      <Field label={t("sources.file")} htmlFor="upload-file" hint={t("sources.file_hint", { mb: maxMb })}>
        <input id="upload-file" className="input" type="file" accept=".csv,.xlsx,.pdf,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <div className="rounded-lg bg-slate-50 p-3 text-sm">
        <p className="font-medium text-slate-700">{t("sources.consent")}</p>
        {active.length ? (
          <>
            {active.length > 1 && (
              <select className="input mt-1" value={chosen?.id} onChange={(e) => setConsentId(Number(e.target.value))} aria-label={t("sources.consent")}>
                {active.map((c) => <option key={c.id} value={c.id}>{t(`consents.purposes.${c.purpose}`)} · {fmtDate(c.expires_at)}</option>)}
              </select>
            )}
            <p className="mt-1 text-xs text-slate-600">{chosen?.scope} · {t("consents.expires")} {fmtDate(chosen?.expires_at)}</p>
          </>
        ) : (
          <div className="mt-1 space-y-2">
            <p className="text-xs text-slate-600">{t("sources.no_consent")}</p>
            <p className="text-xs text-slate-500">{scopes[kind]}</p>
            <button type="button" className="btn-secondary px-3 py-1 text-xs" disabled={grant.isPending} onClick={() => grant.mutate()}>
              {t("sources.give_consent")} · {t("consents.purposes.income_assessment")}
            </button>
          </div>
        )}
      </div>
      <button className="btn-primary" disabled={busy || !active.length}>{busy ? t("sources.uploading") : t("sources.upload_btn")}</button>
    </form>
  );
}

function MappingModal({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: (s: any) => void }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["source", id], queryFn: () => api(`/worker/sources/${id}`) });
  const [m, setM] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"two" | "one" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = q.data;
  const det = d?.mapping ?? {};
  const val = (k: string) => (m[k] !== undefined ? m[k] : det[k] ?? "");
  const curMode = mode ?? (det.amount && !det.debit ? "one" : "two");
  const cols: string[] = d?.preview?.columns ?? [];
  const sel = (k: string) => (
    <Field label={t(`sources.map.${k}`)} htmlFor={`map-${k}`}>
      <select id={`map-${k}`} className="input" value={val(k)} onChange={(e) => setM((p) => ({ ...p, [k]: e.target.value }))}>
        <option value="">{t("sources.map_none")}</option>
        {cols.map((c) => <option key={c}>{c}</option>)}
      </select>
    </Field>
  );
  const apply = async () => {
    setErr(null);
    const body: any = { date: val("date"), narration: val("narration"), balance: val("balance") || null, ref: val("ref") || null, date_format: val("date_format") || "auto" };
    if (curMode === "two") Object.assign(body, { debit: val("debit") || null, credit: val("credit") || null, amount: null });
    else Object.assign(body, { amount: val("amount") || null, debit: null, credit: null });
    if (!body.date || !body.narration) return setErr(`${t("common.required")}: ${t("sources.map.date")}, ${t("sources.map.narration")}`);
    setBusy(true);
    try {
      onDone(await api(`/worker/sources/${id}/mapping`, { body }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open title={t("sources.map_title")} onClose={onClose} wide>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : !d.preview ? <Notice tone="error">{d.error}</Notice> : (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">{t("sources.map_body")}</p>
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{d.preview.rows.map((r: string[], i: number) => <tr key={i}>{r.map((c, j) => <td key={j} className="whitespace-nowrap text-xs">{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
          {err && <Notice tone="error">{err}</Notice>}
          <div className="grid gap-3 sm:grid-cols-3">
            {sel("date")}
            {sel("narration")}
            <Field label={t("sources.map.date_format")} htmlFor="map-df">
              <select id="map-df" className="input" value={val("date_format") || "auto"} onChange={(e) => setM((p) => ({ ...p, date_format: e.target.value }))}>
                {["auto", "dd/mm/yyyy", "dd-mm-yy", "yyyy-mm-dd", "mm/dd/yyyy"].map((f) => <option key={f}>{f}</option>)}
              </select>
            </Field>
          </div>
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="radio" checked={curMode === "two"} onChange={() => setMode("two")} />{t("sources.map_mode_two")}</label>
            <label className="flex items-center gap-2"><input type="radio" checked={curMode === "one"} onChange={() => setMode("one")} />{t("sources.map_mode_one")}</label>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-3">
            {curMode === "two" ? <>{sel("debit")}{sel("credit")}</> : sel("amount")}
            {sel("balance")}
            {sel("ref")}
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={onClose}>{t("common.cancel")}</button>
            <button className="btn-primary" disabled={busy} onClick={apply}>{busy ? t("common.saving") : t("sources.map_apply")}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Ledger() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["ledger", kind, page], queryFn: () => api("/worker/ledger", { params: { kind, page } }) });
  const recat = useMutation({
    mutationFn: ({ id, category }: { id: number; category: string }) => api(`/worker/ledger/${id}/category`, { method: "PATCH", body: { category } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ledger"] });
      qc.invalidateQueries({ queryKey: ["passport"] });
    },
  });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <section className="card" id="transactions">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="h2">{t("ledger.title")}</h2>
        <select className="input w-auto" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label={t("ledger.kind")}>
          <option value="">{t("ledger.all")}</option>
          {["earned", "self_transfer", "refund", "loan", "expense", "other"].map((k) => <option key={k} value={k}>{t(`ledger.kinds.${k}`)}</option>)}
        </select>
      </div>
      <p className="muted mb-3">{t("ledger.sub")}</p>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : q.data.rows.length === 0 ? <p className="muted">{t("ledger.empty")}</p> : (
        <>
          {recat.error && <Notice tone="error">{(recat.error as Error).message}</Notice>}
          <EvidenceTable
            rows={q.data.rows}
            actions={(r) =>
              r.direction === "debit" && r.source_kind === "bank_statement" ? (
                <select
                  className="rounded border border-slate-300 px-1 py-0.5 text-xs"
                  aria-label={t("ledger.recategorise")}
                  value={["rent", "utilities", "fuel", "emi", "savings"].includes(r.category) ? r.category : "other"}
                  onChange={(e) => recat.mutate({ id: r.id, category: e.target.value })}
                >
                  {["rent", "utilities", "fuel", "emi", "savings", "other"].map((c) => <option key={c} value={c}>{t(`ledger.cats.${c}`)}</option>)}
                </select>
              ) : null
            }
          />
          <div className="mt-3 flex items-center justify-between text-sm">
            <button className="btn-secondary px-3 py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("ledger.prev")}</button>
            <span className="text-slate-500">{t("ledger.page", { p: page, n: pages })}</span>
            <button className="btn-secondary px-3 py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("ledger.next")}</button>
          </div>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Consents

export function Consents() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["consents"], queryFn: () => api("/worker/consents") });
  const [f, setF] = useState({ source_kind: "bank_statement", purpose: "income_assessment", days: 90 });
  const [revoke, setRevoke] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const grant = useMutation({ mutationFn: () => api("/worker/consents", { body: f }), onSuccess: () => qc.invalidateQueries({ queryKey: ["consents"] }) });
  const rev = useMutation({
    mutationFn: (id: number) => api(`/worker/consents/${id}/revoke`, { method: "POST" }),
    onSuccess: (r: any) => {
      setRevoke(null);
      setMsg(t("consents.revoked_ok", { n: r.sources_withdrawn, m: r.share_links_closed }));
      ["consents", "sources", "passport", "ledger"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-4">
      <PageHeader title={t("consents.title")} subtitle={t("consents.sub")} />
      {msg && <Notice tone="success">{msg}</Notice>}
      <form className="card space-y-4" onSubmit={(e) => { e.preventDefault(); grant.mutate(); }}>
        <h2 className="h2">{t("consents.new")}</h2>
        {grant.error && <Notice tone="error">{(grant.error as Error).message}</Notice>}
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("consents.source_kind")} htmlFor="ck">
            <select id="ck" className="input" value={f.source_kind} onChange={(e) => setF({ ...f, source_kind: e.target.value })}>
              {["bank_statement", "platform_statement", "account_aggregator"].map((k) => <option key={k} value={k}>{t(`consents.kinds.${k}`)}</option>)}
            </select>
          </Field>
          <Field label={t("consents.purpose")} htmlFor="cp">
            <select id="cp" className="input" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>
              {["income_assessment", "loan_application", "monitoring"].map((k) => <option key={k} value={k}>{t(`consents.purposes.${k}`)}</option>)}
            </select>
          </Field>
          <Field label={t("consents.days")} htmlFor="cd">
            <input id="cd" className="input" type="number" min={1} max={365} value={f.days} onChange={(e) => setF({ ...f, days: Math.max(1, Math.min(365, Number(e.target.value) || 1)) })} />
          </Field>
        </div>
        <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600"><span className="font-medium">{t("consents.scope")}:</span> {q.data.scopes[f.source_kind]}</p>
        <button className="btn-primary" disabled={grant.isPending}>{t("consents.grant")}</button>
      </form>
      <Section title={t("nav.consents")}>
        {q.data.consents.length === 0 ? <p className="muted">{t("consents.empty")}</p> : (
          <ul className="divide-y divide-slate-100">
            {q.data.consents.map((c: any) => (
              <li key={c.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium">{t(`consents.kinds.${c.source_kind}`)} · {t(`consents.purposes.${c.purpose}`)}</p>
                  <p className="mt-0.5 text-xs text-slate-500">{c.scope}</p>
                  <p className="mt-1 text-xs text-slate-600">
                    {t("consents.granted")} {fmtDate(c.granted_at)} · {t("consents.expires")} {fmtDate(c.expires_at)} · {t("consents.sources", { n: c.sources })}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Pill tone={c.status === "active" ? "green" : "slate"}>{t(`consents.status.${c.status}`)}</Pill>
                  {c.status === "active" && <button className="btn-danger px-3 py-1 text-xs" onClick={() => setRevoke(c)}>{t("consents.revoke")}</button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Modal open={!!revoke} title={t("consents.revoke")} onClose={() => setRevoke(null)}>
        <p className="text-sm text-slate-700">{t("consents.revoke_confirm")}</p>
        {rev.error && <div className="mt-2"><Notice tone="error">{(rev.error as Error).message}</Notice></div>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setRevoke(null)}>{t("common.cancel")}</button>
          <button className="btn-danger" disabled={rev.isPending} onClick={() => rev.mutate(revoke.id)}>{t("consents.revoke")}</button>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Improve

export function Improve() {
  const { t } = useTranslation();
  const lang = useLang();
  const q = useQuery({ queryKey: ["recourse", lang], queryFn: () => api("/worker/recourse", { params: { lang } }) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (r.empty)
    return (
      <>
        <PageHeader title={t("improve.title")} />
        <EmptyState title={t("passport.empty_title")} body={t("passport.empty_body")} action={<Link to="/worker/sources" className="btn-primary mt-2">{t("passport.add_source")}</Link>} />
      </>
    );
  const text = r.steps.map((s: any) => s.text).join(" ");
  return (
    <div className="space-y-4">
      <PageHeader title={t("improve.title")} subtitle={t("improve.sub")} actions={r.steps.length ? <ReadAloud text={text} /> : undefined} />
      {r.confidence !== "Low" && (
        <div className="card flex items-center gap-3">
          <BandBadge band={r.current_band} size="lg" />
          <p className="font-medium">{t("improve.current", { band: r.current_band, score: r.current_score })}</p>
        </div>
      )}
      {r.confidence === "Low" && <Notice tone="warn">{t("improve.low_conf")}</Notice>}
      <Section title={t("improve.steps_title")}>
        {r.top_band ? <p className="text-sm text-slate-700">{t("improve.top_band")}</p> : r.steps.length === 0 ? <p className="text-sm text-slate-700">{t("improve.no_steps")}</p> : (
          <ol className="space-y-3">
            {r.steps.map((s: any, i: number) => (
              <li key={i} className="flex gap-3 rounded-lg border border-slate-100 p-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-100 text-sm font-semibold text-accent-800">{i + 1}</span>
                <div>
                  <p className="text-sm text-slate-800">{s.text}</p>
                  <p className="mt-1 text-xs text-emerald-700">{t("improve.new_band", { band: s.new_band, score: s.new_score })}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Section>
      <Section title={t("improve.locked_title")}>
        <p className="text-sm text-slate-600">{t("improve.locked")}</p>
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ Share

export function Share() {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const lq = useQuery({ queryKey: ["lenders"], queryFn: () => api("/meta/lenders") });
  const aq = useQuery({ queryKey: ["applications"], queryFn: () => api("/worker/applications") });
  const [f, setF] = useState({ lender_id: 0, days: 14, requested_amount: 30000, requested_tenure_weeks: 52, purpose: "" });
  const [touched, setTouched] = useState(false);
  const [revoke, setRevoke] = useState<any>(null);
  const create = useMutation({
    mutationFn: () => api("/worker/shares", { body: { ...f, lender_id: f.lender_id || lq.data?.lenders[0]?.id } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
  const rev = useMutation({
    mutationFn: (id: number) => api(`/worker/shares/${id}/revoke`, { method: "POST" }),
    onSuccess: () => {
      setRevoke(null);
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
  if (lq.isLoading || aq.isLoading) return <Loading />;
  if (lq.error || aq.error) return <ErrorState error={lq.error || aq.error} />;
  const lenders = lq.data.lenders;
  const apps = aq.data.applications;
  const lenderById = Object.fromEntries(lenders.map((l: any) => [l.id, l]));
  const amountErr = touched && !(f.requested_amount > 0) ? t("share.err_amount") : undefined;
  return (
    <div className="space-y-4">
      <PageHeader title={t("share.title")} subtitle={t("share.sub")} />
      <form className="card space-y-4" noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (f.requested_amount > 0) create.mutate(); }}>
        {create.error && <Notice tone="error">{(create.error as Error).message}</Notice>}
        {create.isSuccess && <Notice tone="success">{t(`share.status.${(create.data as any).status}`)}</Notice>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("share.lender")} htmlFor="sl">
            <select id="sl" className="input" value={f.lender_id || lenders[0]?.id} onChange={(e) => setF({ ...f, lender_id: Number(e.target.value) })}>
              {lenders.map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
          <Field label={t("share.days")} htmlFor="sd">
            <input id="sd" className="input" type="number" min={1} max={90} value={f.days} onChange={(e) => setF({ ...f, days: Math.max(1, Math.min(90, Number(e.target.value) || 1)) })} />
          </Field>
          <Field label={t("share.amount")} htmlFor="sa" error={amountErr}>
            <input id="sa" className="input" type="number" min={1000} step={1000} value={f.requested_amount} onChange={(e) => setF({ ...f, requested_amount: Number(e.target.value) })} />
          </Field>
          <Field label={t("share.tenure")} htmlFor="st">
            <input id="st" className="input" type="number" min={4} max={156} value={f.requested_tenure_weeks} onChange={(e) => setF({ ...f, requested_tenure_weeks: Math.max(4, Math.min(156, Number(e.target.value) || 4)) })} />
          </Field>
        </div>
        <Field label={`${t("share.purpose")} (${t("common.optional")})`} htmlFor="sp">
          <input id="sp" className="input" maxLength={120} value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
        </Field>
        <p className="text-xs text-slate-500">{t("share.routing")}</p>
        <button className="btn-primary" disabled={create.isPending}>{create.isPending ? t("share.creating") : t("share.create")}</button>
      </form>
      <Section title={t("share.apps_title")}>
        {apps.length === 0 ? <p className="muted">{t("share.empty")}</p> : (
          <ul className="space-y-3">
            {apps.map((a: any) => (
              <li key={a.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{a.lender}</p>
                    <p className="text-xs text-slate-500">{inr(a.requested_amount)} · {a.requested_tenure_weeks} {t("common.weeks")} · {fmtDate(a.created_at, lang)}</p>
                  </div>
                  <Pill tone={a.status === "approved" || a.status === "modified" ? "green" : a.status === "declined" ? "red" : "amber"}>{t(`share.status.${a.status}`)}</Pill>
                </div>
                {a.decision && (
                  <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
                    <p className="font-medium">{t("share.decision")}: {t(`share.outcome.${a.decision.outcome}`)}</p>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                      {a.decision.weekly_emi != null && <div><dt className="text-slate-500">{t("share.emi")}</dt><dd className="font-medium">{inr(a.decision.weekly_emi)}</dd></div>}
                      {a.decision.amount != null && <div><dt className="text-slate-500">{t("share.amount_l")}</dt><dd className="font-medium">{inr(a.decision.amount)}</dd></div>}
                      {a.decision.tenure_weeks != null && <div><dt className="text-slate-500">{t("share.tenure_w")}</dt><dd className="font-medium">{a.decision.tenure_weeks} {t("common.weeks")}</dd></div>}
                      {a.decision.payout_day && a.decision.outcome !== "decline" && <div><dt className="text-slate-500">{t("share.payout_day")}</dt><dd className="font-medium">{a.decision.payout_day}</dd></div>}
                      {a.decision.skip_weeks?.length > 0 && <div><dt className="text-slate-500">{t("share.skip")}</dt><dd className="font-medium">{a.decision.skip_weeks.map((w: string) => fmtDate(w, lang)).join(", ")}</dd></div>}
                      <div><dt className="text-slate-500">{t("share.reason")}</dt><dd className="font-medium">{a.decision.reason_code.replace(/_/g, " ").toLowerCase()}</dd></div>
                    </dl>
                    <p className="mt-2 text-xs text-slate-600"><span className="text-slate-500">{t("share.note")}:</span> {a.decision.note}</p>
                  </div>
                )}
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className={a.share.valid ? "text-emerald-700" : "text-slate-500"}>
                    {a.share.valid ? `${t("share.link_active")} · ${t("share.expires", { date: fmtDate(a.share.expires_at, lang) })}` : t("share.link_inactive")}
                  </span>
                  <div className="flex gap-2">
                    <Link to={`/worker/disputes?application=${a.id}`} className="btn-ghost px-2 py-1 text-xs">{t("share.raise_dispute")}</Link>
                    {a.share.valid && <button className="btn-danger px-2 py-1 text-xs" onClick={() => setRevoke(a)}>{t("share.revoke")}</button>}
                  </div>
                </div>
                {lenderById[a.lender_id]?.grievance_email && <p className="mt-1 text-xs text-slate-500">{t("share.grievance", { email: lenderById[a.lender_id].grievance_email })}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Modal open={!!revoke} title={t("share.revoke")} onClose={() => setRevoke(null)}>
        <p className="text-sm text-slate-700">{t("share.revoke_confirm")}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setRevoke(null)}>{t("common.cancel")}</button>
          <button className="btn-danger" disabled={rev.isPending} onClick={() => rev.mutate(revoke.share.id)}>{t("share.revoke")}</button>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Disputes

export function Disputes() {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const initialApp = useMemo(() => Number(new URLSearchParams(window.location.search).get("application")) || 0, []);
  const q = useQuery({ queryKey: ["disputes"], queryFn: () => api("/worker/disputes") });
  const aq = useQuery({ queryKey: ["applications"], queryFn: () => api("/worker/applications") });
  const [f, setF] = useState({ category: initialApp ? "decision" : "score", description: "", application_id: initialApp });
  const [touched, setTouched] = useState(false);
  const create = useMutation({
    mutationFn: () => api("/worker/disputes", { body: { ...f, application_id: f.application_id || null } }),
    onSuccess: () => {
      setF({ category: "score", description: "", application_id: 0 });
      setTouched(false);
      qc.invalidateQueries({ queryKey: ["disputes"] });
    },
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const descErr = touched && f.description.trim().length < 10 ? t("disputes.description_hint") : undefined;
  return (
    <div className="space-y-4">
      <PageHeader title={t("disputes.title")} subtitle={t("disputes.sub")} />
      <form className="card space-y-4" noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (f.description.trim().length >= 10) create.mutate(); }}>
        <h2 className="h2">{t("disputes.new")}</h2>
        {create.error && <Notice tone="error">{(create.error as Error).message}</Notice>}
        {create.isSuccess && <Notice tone="success">{t("disputes.sent")}</Notice>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("disputes.category")} htmlFor="dc">
            <select id="dc" className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {["score", "decision", "data"].map((c) => <option key={c} value={c}>{t(`disputes.cats.${c}`)}</option>)}
            </select>
          </Field>
          <Field label={t("disputes.application")} htmlFor="da">
            <select id="da" className="input" value={f.application_id} onChange={(e) => setF({ ...f, application_id: Number(e.target.value) })}>
              <option value={0}>{t("disputes.none")}</option>
              {(aq.data?.applications ?? []).map((a: any) => <option key={a.id} value={a.id}>{a.lender} · {fmtDate(a.created_at, lang)}</option>)}
            </select>
          </Field>
        </div>
        <Field label={t("disputes.description")} htmlFor="dd" hint={t("disputes.description_hint")} error={descErr}>
          <textarea id="dd" className="input min-h-[96px]" maxLength={2000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <button className="btn-primary" disabled={create.isPending}>{t("disputes.submit")}</button>
      </form>
      <Section title={t("disputes.title")}>
        {q.data.disputes.length === 0 ? <p className="muted">{t("disputes.empty")}</p> : (
          <ul className="divide-y divide-slate-100">
            {q.data.disputes.map((d: any) => (
              <li key={d.id} className="py-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium">{t(`disputes.cats.${d.category}`)} · {fmtDate(d.created_at, lang)}</p>
                  <Pill tone={d.status === "resolved" ? "green" : d.status === "in_review" ? "amber" : "slate"}>{t(`disputes.status.${d.status}`)}</Pill>
                </div>
                <p className="mt-1 text-sm text-slate-700">{d.description}</p>
                {d.response && <p className="mt-2 rounded-lg bg-slate-50 p-2 text-sm"><span className="text-xs text-slate-500">{t("disputes.response")}:</span> {d.response}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ Profile

export function Profile() {
  const { t, i18n } = useTranslation();
  const { me, refresh } = useAuth();
  const qc = useQueryClient();
  const [f, setF] = useState(() => ({
    name: me?.name ?? "", city: me?.profile?.city ?? "Chennai", work_type: me?.profile?.work_type ?? "rider",
    languages: me?.profile?.languages ?? ["en"], preferred_language: (me?.preferred_language ?? "en") as string,
    group_attr: me?.profile?.group_attr ?? "", group_attr_consent: me?.profile?.group_attr_consent ?? false,
    training_consent: me?.profile?.training_consent ?? false,
  }));
  const save = useMutation({
    mutationFn: () => api("/worker/profile", { method: "PUT", body: { ...f, group_attr: f.group_attr || null } }),
    onSuccess: async () => {
      await refresh();
      i18n.changeLanguage(f.preferred_language);
      qc.invalidateQueries({ queryKey: ["passport"] });
    },
  });
  return (
    <div className="space-y-4">
      <PageHeader title={t("profile.title")} />
      <form className="card space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} noValidate>
        {save.error && <Notice tone="error">{(save.error as Error).message}</Notice>}
        {save.isSuccess && <Notice tone="success">{t("profile.saved")}</Notice>}
        <Field label={t("auth.name")} htmlFor="pn" error={f.name.trim().length < 2 ? t("auth.err_name") : undefined}>
          <input id="pn" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("auth.city")} htmlFor="pc" hint={t("profile.cohort_note")}>
            <select id="pc" className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}>
              {["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label={t("auth.work_type")} htmlFor="pw">
            <select id="pw" className="input" value={f.work_type} onChange={(e) => setF({ ...f, work_type: e.target.value })}>
              {["rider", "home_service", "freelancer", "vendor"].map((w) => <option key={w} value={w}>{t(`work_types.${w}`)}</option>)}
            </select>
          </Field>
          <Field label={t("auth.pref_lang")} htmlFor="pl">
            <select id="pl" className="input" value={f.preferred_language} onChange={(e) => setF({ ...f, preferred_language: e.target.value })}>
              {["en", "ta", "hi"].map((l) => <option key={l} value={l}>{t(`langs.${l}`)}</option>)}
            </select>
          </Field>
        </div>
        <fieldset>
          <legend className="label">{t("auth.languages")}</legend>
          <div className="flex flex-wrap gap-4">
            {["en", "ta", "hi"].map((l) => (
              <label key={l} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={f.languages.includes(l)} onChange={(e) => setF({ ...f, languages: e.target.checked ? [...f.languages, l] : f.languages.filter((x) => x !== l) })} />
                {t(`langs.${l}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="rounded-lg bg-slate-50 p-3">
          <Field label={t("profile.group_attr")} htmlFor="pg" hint={t("profile.group_hint")}>
            <select id="pg" className="input" value={f.group_attr} onChange={(e) => setF({ ...f, group_attr: e.target.value })}>
              <option value="">{t("disputes.none")}</option>
              {["woman", "man", "non_binary"].map((g) => <option key={g} value={g}>{t(`profile.group.${g}`)}</option>)}
            </select>
          </Field>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.group_attr_consent} onChange={(e) => setF({ ...f, group_attr_consent: e.target.checked })} />
            {t("profile.group_consent")}
          </label>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input className="mt-1" type="checkbox" checked={f.training_consent} onChange={(e) => setF({ ...f, training_consent: e.target.checked })} />
          <span>{t("profile.training")}<span className="block text-xs text-slate-500">{t("profile.training_hint")}</span></span>
        </label>
        <button className="btn-primary" disabled={save.isPending || f.name.trim().length < 2 || f.languages.length === 0}>{save.isPending ? t("common.saving") : t("common.save")}</button>
      </form>
    </div>
  );
}
