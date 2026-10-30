import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { EvidenceTable, type LedgerRow } from "../components/EvidenceTable";
import { PillarBar, SeasonalityChart, TrendChart } from "../components/charts";
import { Section } from "../components/shell";
import { BandBadge, ConfidencePill, EmptyState, ErrorState, Field, Loading, Modal, Notice, PageHeader, Pill, Stat } from "../components/ui";
import { fmtDate, fmtDateTime, inr, pct, titleCase } from "../lib/format";

const PILLAR_LABEL: Record<string, string> = { consistency: "Consistency", stability: "Stability", capacity: "Capacity", discipline: "Discipline", resilience: "Resilience" };
const STATUS_LABEL: Record<string, string> = { submitted: "Submitted", manual_review_required: "Manual review required", approved: "Approved", modified: "Approved (modified)", declined: "Declined" };
const ROUTE_LABEL: Record<string, string> = { band_D: "Band D", band_E: "Band E", low_confidence: "Low confidence", anti_gaming_flags: "Anti-gaming flag" };
const FLAG_LABEL: Record<string, string> = {
  round_trip: "Credits mirroring own-account transfers", unmatched_payout: "Platform payouts with no bank credit",
  unexplained_large_credit: "Unexplained large credits (not counted)", large_recent_credit: "Large credit in the 14 days before this report",
};
const SUB_LABEL: Record<string, string> = {
  active_week_share: "Active-week share", longest_gap_days: "Longest gap (days)", payout_gap_cv: "Payout-gap variation (CV)",
  v_res: "Unexplained volatility (V_res)", downside_dev: "Downside deviation", recovery_weeks: "Median weeks to recover",
  capacity_share: "Share of bad week left after essentials", dsr: "Debt-service ratio", bounces: "Bounced auto-debits (26 wk)",
  on_time_rate: "On-time bill rate", buffer_days: "Cash buffer (days)", savings_rate: "Months with savings",
  hhi: "Income concentration (HHI)", tenure_months: "Tenure on main sources (months)", eph_trend: "Earnings/hour trend per quarter",
};
const statusTone = (s: string) => (s === "approved" || s === "modified" ? "green" : s === "declined" ? "red" : s === "manual_review_required" ? "amber" : "slate") as any;

// ------------------------------------------------------------------ Queue

export function Queue() {
  const [filters, setFilters] = useState({ band: "", confidence: "", status: "", manual_review: "" });
  const q = useQuery({ queryKey: ["queue", filters], queryFn: () => api("/officer/applications", { params: filters }) });
  const set = (k: string, v: string) => setFilters((f) => ({ ...f, [k]: v }));
  return (
    <div className="space-y-4">
      <PageHeader title="Applications" subtitle={q.data ? `Shared with ${q.data.lender}. Nothing here is decided automatically.` : undefined} />
      <div className="card grid gap-3 sm:grid-cols-4">
        <Field label="Band" htmlFor="fb">
          <select id="fb" className="input" value={filters.band} onChange={(e) => set("band", e.target.value)}>
            <option value="">All bands</option>
            {["A", "B", "C", "D", "E"].map((b) => <option key={b}>{b}</option>)}
          </select>
        </Field>
        <Field label="Confidence" htmlFor="fc">
          <select id="fc" className="input" value={filters.confidence} onChange={(e) => set("confidence", e.target.value)}>
            <option value="">All</option>
            {["High", "Medium", "Low"].map((b) => <option key={b}>{b}</option>)}
          </select>
        </Field>
        <Field label="Status" htmlFor="fs">
          <select id="fs" className="input" value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Routing" htmlFor="fr">
          <select id="fr" className="input" value={filters.manual_review} onChange={(e) => set("manual_review", e.target.value)}>
            <option value="">All</option>
            <option value="true">Manual review required</option>
            <option value="false">No routing flag</option>
          </select>
        </Field>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data.applications.length === 0 ? (
        <EmptyState title="No applications match these filters" body="Applications appear here when a worker shares their passport with your institution." />
      ) : (
        <div className="card p-0 sm:p-0">
          <div className="table-wrap mx-0">
            <table className="tbl">
              <thead>
                <tr><th>Worker</th><th>Score</th><th>Confidence</th><th>Safe EMI / wk</th><th>Requested</th><th>Status</th><th>Routing</th><th>Received</th></tr>
              </thead>
              <tbody>
                {q.data.applications.map((a: any) => (
                  <tr key={a.id} className="hover:bg-slate-50">
                    <td>
                      <Link className="font-medium text-accent-700 underline" to={`/officer/applications/${a.id}`}>{a.worker}</Link>
                      <div className="text-xs text-slate-500">{a.city} · {titleCase(a.work_type)}</div>
                    </td>
                    <td><div className="flex items-center gap-2"><BandBadge band={a.band} /><span className="tabular-nums">{a.score}</span></div></td>
                    <td><ConfidencePill level={a.confidence} /></td>
                    <td className="tabular-nums">{inr(a.safe_emi)}</td>
                    <td className="whitespace-nowrap tabular-nums">{inr(a.requested_amount)} · {a.requested_tenure_weeks} wk</td>
                    <td><Pill tone={statusTone(a.status)}>{STATUS_LABEL[a.status]}</Pill>{!a.share_valid && <div className="mt-1 text-xs text-slate-500">Share link closed</div>}</td>
                    <td>{a.manual_review ? <div className="flex flex-wrap gap-1">{a.routing_reasons.map((r: string) => <Pill key={r} tone="amber">{ROUTE_LABEL[r] ?? r}</Pill>)}</div> : <span className="text-xs text-slate-400">—</span>}</td>
                    <td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Report

export function Report() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["report", id], queryFn: () => api(`/officer/applications/${id}`), retry: false });
  const [ev, setEv] = useState<{ title: string; params: Record<string, string | number> } | null>(null);
  const [ledgerView, setLedgerView] = useState<string | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error)
    return (
      <div className="space-y-3">
        <Link to="/officer" className="btn-ghost px-2">← Applications</Link>
        {q.error instanceof ApiError && q.error.status === 410 ? <Notice tone="warn">{q.error.message}</Notice> : <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      </div>
    );
  const r = q.data;
  const app = r.application;
  const decided = ["approved", "modified", "declined"].includes(app.status);
  const recon = r.reconciliation;
  return (
    <div className="space-y-4">
      <Link to="/officer" className="btn-ghost -ml-2 px-2">← Applications</Link>
      <PageHeader
        title={r.worker.name}
        subtitle={`${r.worker.city} · ${titleCase(r.worker.work_type)} · requested ${inr(app.requested_amount)} over ${app.requested_tenure_weeks} weeks${app.purpose ? ` · ${app.purpose}` : ""} · data up to ${fmtDate(r.as_of)}`}
        actions={<Pill tone={statusTone(app.status)}>{STATUS_LABEL[app.status]}</Pill>}
      />
      {app.manual_review && (
        <Notice tone="warn">
          <span className="font-semibold">Manual review required:</span> {app.routing_reasons.map((x: string) => ROUTE_LABEL[x] ?? x).join(", ")}. The suggestion below is advisory; you decide.
        </Notice>
      )}
      <section className="card grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="EarnScore" value={<span className="flex items-center gap-2">{r.score}<BandBadge band={r.band} /></span>} sub={`Model ${r.model_version}`} />
        <Stat label="Confidence" value={<ConfidencePill level={r.confidence} />} sub={`DSI ${r.dsi.dsi.toFixed(2)}`} />
        <Stat label="Safe weekly EMI" value={inr(r.safe_emi)} sub={`α ${r.alpha} × (F20 − essentials)`} />
        <Stat label="Bad-week floor F20" value={inr(r.f20)} sub="20th pct, last 26 weeks" />
        <Stat label="Weekly essentials" value={inr(r.e_ess)} sub="rent, bills, fuel, EMIs" />
      </section>
      {r.capacity_warning && <Notice tone="warn">Capacity warning: F20 does not exceed weekly essentials, so the safe EMI is ₹0.</Notice>}

      {r.flags.length > 0 && (
        <Section title="Anti-gaming checks">
          <ul className="space-y-2">
            {r.flags.map((f: any) => (
              <li key={f.flag} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-sm">
                <span>{FLAG_LABEL[f.flag] ?? f.flag} · {f.count}</span>
                <button className="text-xs font-medium text-accent-700 underline" onClick={() => setEv({ title: FLAG_LABEL[f.flag] ?? f.flag, params: { flag: f.flag } })}>Open transactions</button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Pillars (click to see the transactions behind each)">
          {r.pillars.map((p: any) => (
            <div key={p.pillar} className="border-b border-slate-100 py-1 last:border-0">
              <PillarBar score={p.score} label={PILLAR_LABEL[p.pillar]} weight={`${Math.round(p.weight * 100)}% · ${p.contribution} pts`} onClick={() => setEv({ title: `${PILLAR_LABEL[p.pillar]} pillar`, params: { pillar: p.pillar } })} />
              <dl className="grid grid-cols-1 gap-x-4 px-2 pb-2 text-xs text-slate-600 sm:grid-cols-2">
                {Object.entries(p.components).map(([k, c]: any) => (
                  <div key={k} className="flex justify-between gap-2">
                    <dt className="truncate">{SUB_LABEL[k] ?? k}</dt>
                    <dd className="shrink-0 tabular-nums">{c.measured ? `${typeof c.value === "number" ? Number(c.value.toFixed(3)) : c.value} → ${Math.round(c.score)}` : "not measured → 50"}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </Section>
        <Section title="Reason codes">
          <ul className="space-y-2">
            {r.reasons.map((x: any) => (
              <li key={x.id} className="rounded-lg border border-slate-100 p-2">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm">{x.text}</p>
                  <span className={`shrink-0 text-xs font-semibold tabular-nums ${x.impact >= 0 ? "text-emerald-700" : "text-orange-700"}`}>{x.impact >= 0 ? "+" : ""}{x.impact}</span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-2 text-xs text-slate-500">
                  <span className="font-mono">{x.code}</span>
                  {x.evidence_count > 0 && <button className="font-medium text-accent-700 underline" onClick={() => setEv({ title: x.text, params: { reason_id: x.id } })}>{x.evidence_count} transactions</button>}
                </div>
              </li>
            ))}
          </ul>
          {r.watchouts.length > 0 && (
            <div className="mt-3 space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Watch-outs</h3>
              {r.watchouts.map((w: any) => <Notice key={w.code} tone="warn">{w.text}</Notice>)}
            </div>
          )}
        </Section>
      </div>

      <Section title="Reconciliation summary">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { k: "matched", label: "Payouts matched to bank", v: `${recon.matched} / ${recon.payouts}` },
            { k: "unmatched", label: "Unmatched payouts (flagged)", v: recon.unmatched_payouts },
            { k: "excluded", label: "Credits excluded", v: `${recon.self_transfers_excluded + recon.refunds_excluded + recon.loans_excluded} (${inr(recon.excluded_total)})` },
            { k: "flagged", label: "Flagged credits", v: recon.flagged_credits },
          ].map((x) => (
            <button key={x.k} className="rounded-lg border border-slate-200 p-3 text-left hover:border-accent-500" onClick={() => setLedgerView(x.k)}>
              <p className="text-xs text-slate-500">{x.label}</p>
              <p className="mt-1 font-semibold tabular-nums">{x.v}</p>
              <p className="mt-1 text-xs text-accent-700 underline">Open</p>
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">Earned income counted once: {inr(recon.earned_total)}. Own-account transfers {recon.self_transfers_excluded}, refunds {recon.refunds_excluded}, loan credits {recon.loans_excluded} left out.</p>
      </Section>

      <Section title={`Seasonality: raw swing ${pct(r.volatility.raw)} vs unexplained swing ${pct(r.volatility.unexplained)} after adjustment`}>
        <SeasonalityChart series={r.series} labels={{ raw: "Earned (₹/week)", adjusted: "Seasonally adjusted (₹/week)" }} />
        <p className="muted mt-2">Method: {r.seasonality_method === "stl" ? "STL decomposition (period 52) on the worker's own 2+ year history" : r.seasonality_method === "cohort" ? "cohort seasonal index (same city and work type) with a rolling-median trend" : "4-week moving median (cohort too small); confidence capped at Medium"}.</p>
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Score over time">
          <TrendChart points={r.trend} scoreLabel="EarnScore" />
        </Section>
        <Section title="Data sufficiency (sets confidence only)">
          <ul className="space-y-1 text-sm">
            <li className="flex justify-between"><span>History {r.dsi.inputs.months} months</span><span className="tabular-nums">{r.dsi.parts.months.toFixed(2)} / 0.40</span></li>
            <li className="flex justify-between"><span>{r.dsi.inputs.sources} sources</span><span className="tabular-nums">{r.dsi.parts.sources.toFixed(2)} / 0.30</span></li>
            <li className="flex justify-between"><span>Reconcile rate {pct(r.dsi.inputs.reconcile_rate)}</span><span className="tabular-nums">{r.dsi.parts.reconcile_rate.toFixed(2)} / 0.30</span></li>
            <li className="flex justify-between border-t border-slate-100 pt-1 font-semibold"><span>DSI</span><span className="tabular-nums">{r.dsi.dsi.toFixed(2)} → {r.confidence}</span></li>
          </ul>
          <p className="mt-2 text-xs text-slate-500">Sources: {r.sources.map((s: any) => s.label).join(", ")}</p>
        </Section>
      </div>

      <LoanShape shape={r.loan_shape} safe={r.safe_emi} />
      {r.early_warnings.length > 0 && (
        <Section title="Early warnings">
          {r.early_warnings.map((w: any) => (
            <Notice key={w.id} tone="warn">Bad-week floor fell {pct(w.drop_pct)} ({inr(w.f20_prev)} → {inr(w.f20_new)}) on {fmtDate(w.created_at)}. Suggested: {w.suggestion === "skip_week" ? "offer a skip-week" : "restructure the loan"}.</Notice>
          ))}
        </Section>
      )}
      {r.decisions.length > 0 && (
        <Section title="Decision record">
          {r.decisions.map((d: any, i: number) => (
            <div key={i} className="text-sm">
              <p className="font-medium">{titleCase(d.outcome)} · {d.reason_code} · {d.officer} · {fmtDateTime(d.created_at)}</p>
              {d.weekly_emi != null && <p className="text-xs text-slate-600">EMI {inr(d.weekly_emi)} / week · {d.tenure_weeks} weeks · {inr(d.amount)}{d.skip_weeks?.length ? ` · skip ${d.skip_weeks.map((w: string) => fmtDate(w)).join(", ")}` : ""}</p>}
              <p className="mt-1 text-slate-700">{d.note}</p>
              {!d.agrees_with_suggestion && <Pill tone="amber">Override of the suggested outcome</Pill>}
            </div>
          ))}
        </Section>
      )}
      {!decided && <DecisionForm id={Number(id)} report={r} />}

      <EvidenceModal appId={Number(id)} state={ev} onClose={() => setEv(null)} />
      <LedgerModal appId={Number(id)} view={ledgerView} onClose={() => setLedgerView(null)} />
    </div>
  );
}

function LoanShape({ shape, safe }: { shape: any; safe: number }) {
  return (
    <Section title="Suggested loan shape">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <Stat label="Weekly EMI" value={inr(shape.weekly_emi)} sub={shape.fits_safe_emi ? "requested EMI fits the safe EMI" : `requested ${inr(shape.requested_emi)} exceeds safe ${inr(safe)}`} />
        <Stat label="Collect on" value={shape.payout_day || "—"} sub="most common payout day" />
        <Stat label="Amount" value={inr(shape.amount)} sub={`${Math.round(shape.annual_rate * 100)}% p.a.`} />
        <Stat label="Tenure" value={`${shape.tenure_weeks} wk`} />
        <Stat label="Seasonal skip-week" value={shape.skip_weeks.length ? shape.skip_weeks.map((w: string) => fmtDate(w)).join(", ") : "—"} sub={shape.skip_weeks.length ? "lowest expected income week" : "no seasonal index available"} />
      </div>
    </Section>
  );
}

function DecisionForm({ id, report }: { id: number; report: any }) {
  const qc = useQueryClient();
  const shape = report.loan_shape;
  const sugg = report.application.suggested_outcome;
  const [f, setF] = useState({ outcome: sugg === "modify" ? "modify" : "approve", reason_code: "", note: "", weekly_emi: shape.weekly_emi, tenure_weeks: shape.tenure_weeks, amount: shape.amount, skip: shape.skip_weeks.length > 0 });
  const [touched, setTouched] = useState(false);
  const m = useMutation({
    mutationFn: () =>
      api(`/officer/applications/${id}/decision`, {
        body: {
          outcome: f.outcome, reason_code: f.reason_code, note: f.note,
          weekly_emi: f.outcome === "modify" ? f.weekly_emi : null, tenure_weeks: f.outcome === "modify" ? f.tenure_weeks : null,
          amount: f.outcome === "modify" ? f.amount : null, skip_weeks: f.skip && f.outcome !== "decline" ? shape.skip_weeks : [],
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report", String(id)] });
      qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
  const codes: string[] = report.reason_codes[f.outcome];
  const errs = { reason: !f.reason_code ? "Choose a reason code." : "", note: f.note.trim().length < 5 ? "Write a short note (5+ characters)." : "" };
  const disagree = sugg !== "review" && sugg !== f.outcome;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (errs.reason || errs.note) return;
    m.mutate();
  };
  return (
    <form className="card space-y-4" onSubmit={submit} noValidate>
      <h2 className="h2">Your decision</h2>
      <p className="text-sm text-slate-600">Suggested outcome: <span className="font-medium">{sugg === "review" ? "no suggestion (manual review)" : titleCase(sugg)}</span>. A reason code is required for every decision.</p>
      {m.error && <Notice tone="error">{(m.error as Error).message}</Notice>}
      <fieldset className="flex flex-wrap gap-4">
        <legend className="sr-only">Outcome</legend>
        {["approve", "modify", "decline"].map((o) => (
          <label key={o} className="flex items-center gap-2 text-sm font-medium">
            <input type="radio" name="outcome" checked={f.outcome === o} onChange={() => setF({ ...f, outcome: o, reason_code: "" })} />
            {titleCase(o)}
          </label>
        ))}
      </fieldset>
      {disagree && <Notice tone="warn">This differs from the suggested outcome and will be recorded in the override log with your reason.</Notice>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Reason code" htmlFor="rc" error={touched ? errs.reason : undefined}>
          <select id="rc" className="input" value={f.reason_code} onChange={(e) => setF({ ...f, reason_code: e.target.value })}>
            <option value="">Choose…</option>
            {codes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        {f.outcome !== "decline" && shape.skip_weeks.length > 0 && (
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" checked={f.skip} onChange={(e) => setF({ ...f, skip: e.target.checked })} />
            Include seasonal skip-week ({shape.skip_weeks.map((w: string) => fmtDate(w)).join(", ")})
          </label>
        )}
      </div>
      {f.outcome === "modify" && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Weekly EMI (₹)" htmlFor="me"><input id="me" className="input" type="number" min={0} value={f.weekly_emi} onChange={(e) => setF({ ...f, weekly_emi: Number(e.target.value) })} /></Field>
          <Field label="Tenure (weeks)" htmlFor="mt"><input id="mt" className="input" type="number" min={4} max={156} value={f.tenure_weeks} onChange={(e) => setF({ ...f, tenure_weeks: Number(e.target.value) })} /></Field>
          <Field label="Amount (₹)" htmlFor="ma"><input id="ma" className="input" type="number" min={0} value={f.amount} onChange={(e) => setF({ ...f, amount: Number(e.target.value) })} /></Field>
        </div>
      )}
      <Field label="Note" htmlFor="dn" error={touched ? errs.note : undefined}>
        <textarea id="dn" className="input min-h-[80px]" maxLength={2000} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
      </Field>
      <button className="btn-primary" disabled={m.isPending}>{m.isPending ? "Recording…" : "Record decision"}</button>
    </form>
  );
}

function EvidenceModal({ appId, state, onClose }: { appId: number; state: { title: string; params: Record<string, string | number> } | null; onClose: () => void }) {
  const q = useQuery({ queryKey: ["off-evidence", appId, state?.params], queryFn: () => api(`/officer/applications/${appId}/evidence`, { params: state!.params }), enabled: !!state });
  return (
    <Modal open={!!state} title="Evidence" onClose={onClose} wide>
      {state && <p className="mb-3 text-sm text-slate-700">{state.title}</p>}
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : <EvidenceTable rows={(q.data?.rows ?? []) as LedgerRow[]} />}
    </Modal>
  );
}

const VIEW_TITLE: Record<string, string> = { matched: "Bank credits matched to platform payouts", unmatched: "Platform payouts with no matching bank credit", excluded: "Credits not counted as earned income", flagged: "Rows carrying an anti-gaming flag" };

function LedgerModal({ appId, view, onClose }: { appId: number; view: string | null; onClose: () => void }) {
  const q = useQuery({ queryKey: ["off-ledger", appId, view], queryFn: () => api(`/officer/applications/${appId}/ledger`, { params: { view } }), enabled: !!view });
  return (
    <Modal open={!!view} title={view ? VIEW_TITLE[view] : ""} onClose={onClose} wide>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : <EvidenceTable rows={(q.data?.rows ?? []) as LedgerRow[]} showPair={view === "matched"} />}
    </Modal>
  );
}

// ------------------------------------------------------------------ Portfolio

export function Portfolio() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portfolio"], queryFn: () => api("/officer/portfolio") });
  const refresh = useMutation({ mutationFn: () => api("/officer/portfolio/refresh", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }) });
  const alerts = (q.data?.loans ?? []).filter((l: any) => l.warning);
  return (
    <div className="space-y-4">
      <PageHeader
        title="Portfolio & early warnings"
        subtitle="Monthly refresh re-scores every active loan. An alert fires when the bad-week floor falls more than 20% against the previous snapshot."
        actions={<button className="btn-primary" disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? "Refreshing…" : "Run monthly refresh"}</button>}
      />
      {refresh.error && <Notice tone="error">{(refresh.error as Error).message}</Notice>}
      {refresh.data && <Notice tone="success">Refreshed {(refresh.data as any).results.length} loans; {(refresh.data as any).results.filter((r: any) => r.alert).length} alert(s).</Notice>}
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : q.data.loans.length === 0 ? (
        <EmptyState title="No active loans yet" body="Approved and modified applications appear here for monthly monitoring." />
      ) : (
        <>
          {alerts.length > 0 && <Notice tone="warn">{alerts.length} loan(s) need attention: their bad-week income dropped sharply. Consider a skip-week before an EMI is missed.</Notice>}
          <div className="card p-0 sm:p-0">
            <div className="table-wrap mx-0">
              <table className="tbl">
                <thead><tr><th>Worker</th><th>Band at approval</th><th>Weekly EMI</th><th>Decided</th><th>Early warning</th></tr></thead>
                <tbody>
                  {q.data.loans.map((l: any) => (
                    <tr key={l.id}>
                      <td><Link className="font-medium text-accent-700 underline" to={`/officer/applications/${l.id}`}>{l.worker}</Link><div className="text-xs text-slate-500">{l.city} · {titleCase(l.work_type)}</div></td>
                      <td><div className="flex items-center gap-2"><BandBadge band={l.band} /> {l.score}</div></td>
                      <td className="tabular-nums">{inr(l.weekly_emi)}</td>
                      <td className="text-xs text-slate-500">{fmtDate(l.decided_at)}</td>
                      <td>
                        {l.warning ? (
                          <div className="text-sm">
                            <Pill tone="red">F20 −{pct(l.warning.drop_pct)}</Pill>
                            <p className="mt-1 text-xs text-slate-600">{inr(l.warning.f20_prev)} → {inr(l.warning.f20_new)} · suggest {l.warning.suggestion === "skip_week" ? "a skip-week" : "restructuring"}</p>
                          </div>
                        ) : <span className="text-xs text-slate-500">No alert</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Disputes inbox (officer and admin)

export function DisputesInbox() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["disputes-inbox"], queryFn: () => api("/officer/disputes") });
  const [open, setOpen] = useState<any>(null);
  const [resp, setResp] = useState({ status: "in_review", response: "" });
  const m = useMutation({
    mutationFn: () => api(`/officer/disputes/${open.id}`, { method: "PATCH", body: resp }),
    onSuccess: () => {
      setOpen(null);
      qc.invalidateQueries({ queryKey: ["disputes-inbox"] });
    },
  });
  return (
    <div className="space-y-4">
      <PageHeader title="Disputes" subtitle="Grievance inbox. Respond to each worker in plain language; the worker sees your response." />
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : q.data.disputes.length === 0 ? <EmptyState title="No disputes" body="Disputes raised by workers appear here." /> : (
        <div className="card p-0 sm:p-0">
          <div className="table-wrap mx-0">
            <table className="tbl">
              <thead><tr><th>Worker</th><th>About</th><th>Description</th><th>Status</th><th>Raised</th><th /></tr></thead>
              <tbody>
                {q.data.disputes.map((d: any) => (
                  <tr key={d.id}>
                    <td className="whitespace-nowrap font-medium">{d.worker}</td>
                    <td>{titleCase(d.category)}{d.application_id ? ` · application ${d.application_id}` : ""}</td>
                    <td className="max-w-sm text-sm">{d.description}{d.response && <p className="mt-1 text-xs text-slate-500">Response: {d.response}</p>}</td>
                    <td><Pill tone={d.status === "resolved" ? "green" : d.status === "in_review" ? "amber" : "slate"}>{titleCase(d.status)}</Pill></td>
                    <td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(d.created_at)}</td>
                    <td><button className="btn-secondary px-3 py-1 text-xs" onClick={() => { setOpen(d); setResp({ status: d.status === "open" ? "in_review" : d.status, response: d.response }); }}>Respond</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <Modal open={!!open} title={`Dispute from ${open?.worker ?? ""}`} onClose={() => setOpen(null)}>
        <p className="mb-3 text-sm text-slate-700">{open?.description}</p>
        {m.error && <Notice tone="error">{(m.error as Error).message}</Notice>}
        <div className="space-y-3">
          <Field label="Status" htmlFor="ds">
            <select id="ds" className="input" value={resp.status} onChange={(e) => setResp({ ...resp, status: e.target.value })}>
              {["open", "in_review", "resolved"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
            </select>
          </Field>
          <Field label="Response to the worker" htmlFor="dr" hint="Required to resolve.">
            <textarea id="dr" className="input min-h-[80px]" maxLength={2000} value={resp.response} onChange={(e) => setResp({ ...resp, response: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setOpen(null)}>Cancel</button>
            <button className="btn-primary" disabled={m.isPending} onClick={() => m.mutate()}>Save</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
