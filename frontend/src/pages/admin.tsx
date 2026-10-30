import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Section } from "../components/shell";
import { BandBadge, EmptyState, ErrorState, Field, Loading, Modal, Notice, PageHeader, Pill, Stat } from "../components/ui";
import { fmtDate, fmtDateTime, num, pct, titleCase } from "../lib/format";

// ------------------------------------------------------------------ Model cards

export function Models() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["models"], queryFn: () => api("/admin/models") });
  const [confirm, setConfirm] = useState<any>(null);
  const act = useMutation({
    mutationFn: (v: string) => api(`/admin/models/${v}/activate`, { method: "POST" }),
    onSuccess: () => {
      setConfirm(null);
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-4">
      <PageHeader title="Model cards" subtitle="Every score records the model version that produced it. Switching the active model affects new scores only." />
      {act.error && <Notice tone="error">{(act.error as Error).message}</Notice>}
      {q.data.models.map((m: any) => (
        <section key={m.version} className="card space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{m.version}</h2>
              <Pill tone="teal">{m.kind === "ebm" ? "Explainable Boosting Machine" : "Expert scorecard"}</Pill>
              {m.is_active && <Pill tone="green">Active</Pill>}
              <Pill tone={m.validated ? "green" : "amber"}>{m.validated ? "Passed validation" : "Did not pass validation"}</Pill>
            </div>
            {!m.is_active && <button className="btn-secondary" onClick={() => setConfirm(m)}>Make active</button>}
          </div>
          <p className="text-sm text-slate-700">{m.notes}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Features</h3>
              <ul className="space-y-1 text-sm">
                {m.features.map((f: any) => (
                  <li key={f.pillar}>
                    <span className="font-medium">{titleCase(f.pillar)}</span>
                    {f.components && <span className="text-slate-500">: {f.components.map(titleCase).join(", ")}</span>}
                    {f.monotone && <span className="text-slate-500"> ({f.monotone})</span>}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Weights</h3>
              {m.weights.pillars ? (
                <ul className="space-y-1 text-sm">{Object.entries(m.weights.pillars).map(([k, v]: any) => <li key={k} className="flex justify-between"><span>{titleCase(k)}</span><span className="tabular-nums">{pct(v)}</span></li>)}</ul>
              ) : m.weights.term_importance ? (
                <ul className="space-y-1 text-sm">{Object.entries(m.weights.term_importance).map(([k, v]: any) => <li key={k} className="flex justify-between"><span>{titleCase(k)}</span><span className="tabular-nums">{num(v, 3)}</span></li>)}<li className="text-xs text-slate-500">{m.weights.output}</li></ul>
              ) : null}
              {m.weights.bands && <p className="mt-2 text-xs text-slate-500">Bands: {m.weights.bands.map((b: any) => `${b[0]} ≥ ${b[1]}`).join(", ")}</p>}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Training data</h3>
            <p className="text-sm text-slate-700">{m.training_data.description}</p>
          </div>
          {Object.keys(m.metrics).length > 0 && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {m.metrics.auc_v1 !== undefined && <Stat label="AUC v1 (held-out)" value={num(m.metrics.auc_v1, 3)} />}
              {m.metrics.auc_v2 !== undefined && <Stat label="AUC v2 (held-out)" value={num(m.metrics.auc_v2, 3)} />}
              {m.metrics.approval_at_equal_default_v1 !== undefined && <Stat label="Approvals at equal default, v1" value={pct(m.metrics.approval_at_equal_default_v1, 1)} />}
              {m.metrics.approval_at_equal_default_v2 !== undefined && <Stat label="Approvals at equal default, v2" value={pct(m.metrics.approval_at_equal_default_v2, 1)} />}
            </div>
          )}
          <p className="text-xs text-slate-500">Registered {fmtDateTime(m.created_at)}</p>
        </section>
      ))}
      <Modal open={!!confirm} title={`Make ${confirm?.version} active?`} onClose={() => setConfirm(null)}>
        {confirm && !confirm.validated && <Notice tone="warn">This model did not beat v1 on the held-out comparison. Switching is recorded in the audit log.</Notice>}
        <p className="mt-2 text-sm text-slate-700">New passports and reports will be scored with {confirm?.version}. Existing snapshots keep the version they were scored with.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setConfirm(null)}>Cancel</button>
          <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate(confirm.version)}>Make active</button>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Validation

function calibrationTitle(cal: { band: string; n: number; default_rate: number | null }[]): string {
  const rates = cal.filter((c) => c.n > 0 && c.default_rate != null).map((c) => c.default_rate as number); // ordered A..E
  if (rates.length < 2) return "Calibration by band";
  const monotone = rates.every((r, i) => i === 0 || r >= rates[i - 1]);
  return monotone
    ? `Calibration by band: default rate rises steadily from Band A (${pct(rates[0], 1)}) to Band E (${pct(rates[rates.length - 1], 1)})`
    : "Calibration by band: default rate is not monotonic across bands";
}

export function Validation() {
  const q = useQuery({ queryKey: ["validation"], queryFn: () => api("/admin/validation") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const run = q.data.run;
  if (!run) return <><PageHeader title="Validation" /><EmptyState title="No validation run stored" body="An administrator stores a validation run with the command line tool (app.cli). See the README." /></>;
  const m = run.metrics;
  const p = run.params;
  const policyRows = [
    { name: "Bureau-style baseline", ...m.baseline },
    { name: "EarnScore at equal default rate", ...m.earnscore_equal_default_rate },
    { name: "EarnScore, approve bands A–C", ...m.earnscore_band_a_to_c },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Validation" subtitle={`Validation run ${run.id} · ${fmtDateTime(run.created_at)} · ${num(m.n_workers)} workers · ${run.duration_s}s · see "About these results" below`} />
      <section className="card grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="AUC (EarnScore)" value={num(m.auc_earnscore, 3)} sub={`KS ${num(m.ks_earnscore, 3)}`} />
        <Stat label="AUC (bureau, file holders only)" value={m.auc_bureau_on_file != null ? num(m.auc_bureau_on_file, 3) : "—"} sub={`${pct(m.bureau_file_share)} have a bureau file`} />
        <Stat label="Approval uplift at equal default" value={m.approval_uplift_at_equal_default != null ? `${num(m.approval_uplift_at_equal_default, 2)}×` : "—"} sub={`target default rate ${pct(m.earnscore_equal_default_rate.target_default_rate, 1)}`} />
        <Stat label="Default rate" value={pct(m.default_rate, 1)} sub="all borrowers in this run" />
      </section>
      <Section title="Approval policies compared">
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Policy</th><th>Approval rate</th><th>Default rate among approved</th><th>Creditworthy workers rejected</th></tr></thead>
            <tbody>{policyRows.map((r) => <tr key={r.name}><td className="font-medium">{r.name}</td><td className="tabular-nums">{pct(r.approval_rate, 1)}</td><td className="tabular-nums">{r.default_rate_approved != null ? pct(r.default_rate_approved, 1) : "—"}</td><td className="tabular-nums">{pct(r.creditworthy_rejected_share, 1)}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">Thin-file workers (no bureau file): {pct(m.thin_file.share, 1)} of the population; EarnScore approves {pct(m.thin_file.earnscore_approval_rate, 1)} of them at the equal-default threshold; their default rate is {pct(m.thin_file.default_rate, 1)}.</p>
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={calibrationTitle(run.calibration)}>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={run.calibration.filter((c: any) => c.n > 0).map((c: any) => ({ ...c, default_pct: Math.round((c.default_rate ?? 0) * 1000) / 10 }))}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="band" tick={{ fontSize: 12 }} />
                <YAxis unit="%" width={40} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number, n: string) => (n === "default_pct" ? [`${v}%`, "Default rate"] : [v, n])} />
                <Bar dataKey="default_pct" name="Default rate" fill="#0f7a6b" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-wrap mt-2">
            <table className="tbl"><thead><tr><th>Band</th><th>Workers</th><th>Avg score</th><th>Default rate</th></tr></thead>
              <tbody>{run.calibration.map((c: any) => <tr key={c.band}><td><BandBadge band={c.band} /></td><td className="tabular-nums">{num(c.n)}</td><td className="tabular-nums">{c.avg_score ?? "—"}</td><td className="tabular-nums">{c.default_rate != null ? pct(c.default_rate, 1) : "—"}</td></tr>)}</tbody>
            </table>
          </div>
        </Section>
        <Section title="By work type and confidence">
          <div className="table-wrap">
            <table className="tbl"><thead><tr><th>Work type</th><th>Workers</th><th>Avg score</th><th>Default rate</th></tr></thead>
              <tbody>{Object.entries(m.by_work_type).map(([k, v]: any) => <tr key={k}><td>{titleCase(k)}</td><td className="tabular-nums">{num(v.n)}</td><td className="tabular-nums">{v.avg_score}</td><td className="tabular-nums">{pct(v.default_rate, 1)}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="table-wrap mt-3">
            <table className="tbl"><thead><tr><th>Confidence</th><th>Workers</th><th>Default rate</th></tr></thead>
              <tbody>{Object.entries(m.by_confidence).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className="tabular-nums">{num(v.n)}</td><td className="tabular-nums">{v.default_rate != null ? pct(v.default_rate, 1) : "—"}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="mt-3 text-sm">Recourse feasibility (Band C–E): <span className="font-semibold">{run.recourse.feasible_rate != null ? pct(run.recourse.feasible_rate, 1) : "—"}</span> of {num(run.recourse.evaluated)} evaluated workers have at least one tested step that raises their band.</p>
        </Section>
      </div>
      <Section title="EBM v2 vs scorecard v1 (held-out 30%)">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Stat label="AUC v1" value={num(run.model_comparison.auc_v1, 3)} />
          <Stat label="AUC v2" value={num(run.model_comparison.auc_v2, 3)} />
          <Stat label="Approvals v1" value={pct(run.model_comparison.approval_at_equal_default_v1, 1)} />
          <Stat label="Approvals v2" value={pct(run.model_comparison.approval_at_equal_default_v2, 1)} />
          <Stat label="v2 validated" value={run.model_comparison.validated ? "Yes" : "No"} sub={run.model_comparison.validated ? "admin may activate" : "v1 stays active"} />
        </div>
      </Section>
      <section className="card border-sky-200 bg-sky-50">
        <h2 className="h2">About these results</h2>
        <p className="mt-2 text-sm text-slate-700">
          These results come from a simulation, not from real borrowers. They show how the scoring method behaves under the stated assumptions; they are not evidence of real-world accuracy. Simulated workers are generated people with generated cash flows.
        </p>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="font-medium">Workers</dt><dd>{num(p.n_workers)} (seed {p.seed}), {p.personas.map(titleCase).join(", ")}; cities: {p.cities.join(", ")}</dd></div>
          <div><dt className="font-medium">Time span</dt><dd>{p.history_weeks[0]}–{p.history_weeks[1] - 1} weeks of history, then {p.outcome_weeks} weeks of repayment ({p.total_weeks_range[0]}–{p.total_weeks_range[1]} weeks in total)</dd></div>
          <div><dt className="font-medium">Loan</dt><dd>{p.loan}</dd></div>
          <div><dt className="font-medium">Default rule</dt><dd>{p.default_rule}</dd></div>
          <div><dt className="font-medium">Bureau-style baseline</dt><dd>{p.bureau_baseline}</dd></div>
          <div><dt className="font-medium">EarnScore policy</dt><dd>{p.earnscore_policy}</dd></div>
          <div><dt className="font-medium">Shocks</dt><dd>{Object.entries(p.shocks).map(([k, v]) => `${titleCase(k)}: ${v}`).join("; ")}</dd></div>
          <div><dt className="font-medium">Scoring</dt><dd>{p.scoring}</dd></div>
          <div className="sm:col-span-2"><dt className="font-medium">Seasonality effects (multipliers by work type)</dt><dd className="text-xs">{Object.entries(p.seasonality_effects).map(([k, v]: any) => `${titleCase(k)}: ${Object.entries(v).map(([e, x]: any) => `${e} ${x > 0 ? "+" : ""}${Math.round(x * 100)}%`).join(", ")}`).join(" · ")}</dd></div>
        </dl>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ Fairness

export function Fairness() {
  const q = useQuery({ queryKey: ["fairness"], queryFn: () => api("/admin/fairness") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const sim = q.data.simulated;
  const live = q.data.live;
  const groupTable = (title: string, fr: any) => (
    <Section title={title}>
      <div className="table-wrap">
        <table className="tbl">
          <thead><tr><th>Group</th><th>Workers</th><th>Approval (selection) rate</th><th>Creditworthy rejected (FNR)</th></tr></thead>
          <tbody>{Object.entries(fr.by_group).map(([g, v]: any) => <tr key={g}><td>{titleCase(g)}</td><td className="tabular-nums">{num(fr.counts[g])}</td><td className="tabular-nums">{pct(v.selection_rate, 1)}</td><td className="tabular-nums">{pct(v.false_negative_rate, 1)}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="mt-2 text-sm">Gap in approval rate: <span className="font-semibold">{pct(fr.difference.selection_rate, 1)}</span> · gap in creditworthy-rejected rate: <span className="font-semibold">{pct(fr.difference.false_negative_rate, 1)}</span></p>
    </Section>
  );
  return (
    <div className="space-y-4">
      <PageHeader title="Fairness" subtitle="The group attribute is optional, consented and used only for this audit. It is never a scoring input." />
      {sim ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            {groupTable("Validation run: EarnScore at equal default rate", sim.earnscore_equal_default_rate)}
            {groupTable("Validation run: bureau-style baseline", sim.baseline)}
          </div>
          <Section title="Proxy check: correlation of each pillar with the group attribute">
            <ul className="grid gap-2 sm:grid-cols-5">
              {Object.entries(sim.proxy_check).map(([k, v]: any) => (
                <li key={k} className="rounded-lg border border-slate-200 p-2 text-sm"><p className="text-xs text-slate-500">{titleCase(k)}</p><p className="font-semibold tabular-nums">{num(v, 3)}</p><Pill tone={v < 0.1 ? "green" : v < 0.3 ? "amber" : "red"}>{v < 0.1 ? "weak" : v < 0.3 ? "moderate" : "strong"}</Pill></li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-500">{sim.proxy_note}</p>
          </Section>
        </>
      ) : <EmptyState title="No validation run stored" />}
      <Section title={`Live applications by group (${q.data.live_consented_workers} workers consented)`}>
        {Object.keys(live).length === 0 ? <p className="muted">No applications from workers who consented to the group attribute yet.</p> : (
          <div className="table-wrap">
            <table className="tbl"><thead><tr><th>Group</th><th>Applications</th><th>Approved</th><th>Declined</th><th>Pending</th><th>Approval rate (decided)</th></tr></thead>
              <tbody>{Object.entries(live).map(([g, v]: any) => <tr key={g}><td>{titleCase(g)}</td><td>{v.applications}</td><td>{v.approved}</td><td>{v.declined}</td><td>{v.pending}</td><td className="tabular-nums">{v.approved + v.declined ? pct(v.approved / (v.approved + v.declined), 1) : "—"}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ Drift

export function Drift() {
  const q = useQuery({ queryKey: ["drift"], queryFn: () => api("/admin/drift") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data.comparison;
  if (!c) return <><PageHeader title="Drift" /><EmptyState title="Not enough monthly snapshots yet" body="Drift compares pillar distributions between the two latest month-end snapshot sets (5+ workers each)." /></>;
  const shifted = c.features.filter((f: any) => f.status !== "stable").length;
  return (
    <div className="space-y-4">
      <PageHeader title="Drift" subtitle={`Population stability index (PSI) between month-end snapshots ${fmtDate(c.previous)} and ${fmtDate(c.current)}.`} />
      <Section title={shifted ? `${shifted} feature(s) moved beyond the stable range (PSI ≥ 0.10)` : "All features within the stable range (PSI < 0.10)"}>
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={c.features}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="feature" tickFormatter={titleCase} tick={{ fontSize: 11 }} />
              <YAxis width={40} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => [num(v, 3), "PSI"]} labelFormatter={(l) => titleCase(String(l))} />
              <Legend />
              <Bar dataKey="psi" name="PSI" fill="#0f7a6b" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="table-wrap mt-2">
          <table className="tbl"><thead><tr><th>Feature</th><th>PSI</th><th>Mean (previous)</th><th>Mean (current)</th><th>Workers</th><th>Status</th></tr></thead>
            <tbody>{c.features.map((f: any) => <tr key={f.feature}><td>{titleCase(f.feature)}</td><td className="tabular-nums">{num(f.psi, 3)}</td><td className="tabular-nums">{f.mean_prev}</td><td className="tabular-nums">{f.mean_new}</td><td className="tabular-nums">{f.n_prev} → {f.n_new}</td><td><Pill tone={f.status === "stable" ? "green" : f.status === "watch" ? "amber" : "red"}>{titleCase(f.status)}</Pill></td></tr>)}</tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ Override log

export function Overrides() {
  const q = useQuery({ queryKey: ["overrides"], queryFn: () => api("/admin/overrides") });
  const [only, setOnly] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const rows = q.data.decisions.filter((d: any) => !only || d.override);
  return (
    <div className="space-y-4">
      <PageHeader title="Override log" subtitle="Every officer decision with its reason code, and every disagreement with the suggested outcome." actions={<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} />Overrides only</label>} />
      {rows.length === 0 ? <EmptyState title="No decisions recorded yet" /> : (
        <div className="card p-0 sm:p-0">
          <div className="table-wrap mx-0">
            <table className="tbl">
              <thead><tr><th>When</th><th>Worker</th><th>Lender / officer</th><th>Band</th><th>Suggested</th><th>Decision</th><th>Reason code</th><th>Note</th></tr></thead>
              <tbody>{rows.map((d: any) => (
                <tr key={d.id}>
                  <td className="whitespace-nowrap text-xs">{fmtDateTime(d.created_at)}</td>
                  <td>{d.worker}</td>
                  <td className="text-xs">{d.lender}<br />{d.officer}</td>
                  <td><div className="flex items-center gap-1"><BandBadge band={d.band} /><span className="text-xs">{d.confidence}</span></div></td>
                  <td>{titleCase(d.suggested)}</td>
                  <td><Pill tone={d.override ? "amber" : "slate"}>{titleCase(d.outcome)}{d.override ? " · override" : ""}</Pill></td>
                  <td className="font-mono text-xs">{d.reason_code}</td>
                  <td className="max-w-xs text-xs">{d.note}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Audit log

export function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["audit", action, page], queryFn: () => api("/admin/audit", { params: { action, page } }) });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <div className="space-y-4">
      <PageHeader title="Audit log" subtitle="Every lender read of a worker's report, every decision, consent change and upload." />
      <div className="card">
        <Field label="Action" htmlFor="aa">
          <select id="aa" className="input sm:w-72" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
            <option value="">All actions</option>
            {(q.data?.actions ?? []).map((a: string) => <option key={a}>{a}</option>)}
          </select>
        </Field>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : (
        <div className="card p-0 sm:p-0">
          <div className="table-wrap mx-0">
            <table className="tbl">
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
              <tbody>{q.data.rows.map((r: any) => (
                <tr key={r.id}>
                  <td className="whitespace-nowrap text-xs">{fmtDateTime(r.ts)}</td>
                  <td className="whitespace-nowrap">{r.actor}</td>
                  <td className="font-mono text-xs">{r.action}</td>
                  <td className="font-mono text-xs">{r.target}</td>
                  <td className="max-w-sm break-words font-mono text-xs text-slate-500">{Object.keys(r.details).length ? JSON.stringify(r.details) : ""}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="flex items-center justify-between p-3 text-sm">
            <button className="btn-secondary px-3 py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span className="text-slate-500">Page {page} of {pages} · {num(q.data.total)} entries</span>
            <button className="btn-secondary px-3 py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Users and lenders

export function Users() {
  const qc = useQueryClient();
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const uq = useQuery({ queryKey: ["users", role, search], queryFn: () => api("/admin/users", { params: { role, q: search } }) });
  const lq = useQuery({ queryKey: ["admin-lenders"], queryFn: () => api("/admin/lenders") });
  const upd = useMutation({ mutationFn: ({ id, body }: { id: number; body: any }) => api(`/admin/users/${id}`, { method: "PATCH", body }), onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }) });
  const [staff, setStaff] = useState(false);
  const [lender, setLender] = useState<any>(null);
  return (
    <div className="space-y-4">
      <PageHeader title="Users & lenders" actions={<><button className="btn-secondary" onClick={() => setLender({})}>Add lender</button><button className="btn-primary" onClick={() => setStaff(true)}>Add staff account</button></>} />
      <Section title="Lenders">
        {lq.isLoading ? <Loading /> : lq.error ? <ErrorState error={lq.error} /> : (
          <div className="table-wrap">
            <table className="tbl"><thead><tr><th>Name</th><th>α (safe EMI share)</th><th>Annual rate</th><th>Default tenure</th><th>Grievance contact</th><th>Applications</th><th /></tr></thead>
              <tbody>{lq.data.lenders.map((l: any) => <tr key={l.id}><td className="font-medium">{l.name}</td><td>{l.alpha}</td><td>{pct(l.annual_rate)}</td><td>{l.default_tenure_weeks} wk</td><td className="text-xs">{l.grievance_email || "—"}</td><td>{l.applications}</td><td><button className="btn-secondary px-3 py-1 text-xs" onClick={() => setLender(l)}>Edit</button></td></tr>)}</tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Accounts">
        <div className="mb-3 grid gap-3 sm:grid-cols-3">
          <Field label="Role" htmlFor="ur">
            <select id="ur" className="input" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">All roles</option>
              {["worker", "officer", "admin"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
            </select>
          </Field>
          <Field label="Search name or email" htmlFor="us"><input id="us" className="input" value={search} onChange={(e) => setSearch(e.target.value)} /></Field>
        </div>
        {upd.error && <Notice tone="error">{(upd.error as Error).message}</Notice>}
        {uq.isLoading ? <Loading /> : uq.error ? <ErrorState error={uq.error} /> : (
          <div className="table-wrap">
            <table className="tbl"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Lender / city</th><th>Status</th><th /></tr></thead>
              <tbody>{uq.data.users.map((u: any) => (
                <tr key={u.id}>
                  <td className="font-medium">{u.name}</td><td className="text-xs">{u.email}</td><td>{titleCase(u.role)}</td><td className="text-xs">{u.lender ?? u.city ?? "—"}</td>
                  <td><Pill tone={u.is_active ? "green" : "slate"}>{u.is_active ? "Active" : "Deactivated"}</Pill></td>
                  <td><button className="btn-secondary px-3 py-1 text-xs" onClick={() => upd.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? "Deactivate" : "Reactivate"}</button></td>
                </tr>
              ))}</tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">Showing {uq.data.users.length} of {uq.data.total}</p>
          </div>
        )}
      </Section>
      {staff && <StaffModal lenders={lq.data?.lenders ?? []} onClose={() => setStaff(false)} />}
      {lender && <LenderModal lender={lender} onClose={() => setLender(null)} />}
    </div>
  );
}

function StaffModal({ lenders, onClose }: { lenders: any[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "officer", lender_id: lenders[0]?.id ?? 0 });
  const m = useMutation({ mutationFn: () => api("/admin/users", { body: { ...f, lender_id: f.role === "officer" ? f.lender_id : null } }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); onClose(); } });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open title="Add staff account" onClose={onClose}>
      <form className="space-y-3" onSubmit={submit}>
        {m.error && <Notice tone="error">{(m.error as Error).message}</Notice>}
        <Field label="Name" htmlFor="sn"><input id="sn" className="input" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email" htmlFor="se"><input id="se" className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Initial password" htmlFor="sp" hint="At least 10 characters with a letter and a number."><input id="sp" className="input" type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label="Role" htmlFor="sr"><select id="sr" className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="officer">Credit officer</option><option value="admin">Auditor / admin</option></select></Field>
        {f.role === "officer" && <Field label="Lender" htmlFor="sl2"><select id="sl2" className="input" value={f.lender_id} onChange={(e) => setF({ ...f, lender_id: Number(e.target.value) })}>{lenders.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></Field>}
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={m.isPending}>Create</button></div>
      </form>
    </Modal>
  );
}

function LenderModal({ lender, onClose }: { lender: any; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = !lender.id;
  const [f, setF] = useState({ name: lender.name ?? "", alpha: lender.alpha ?? 0.5, annual_rate: lender.annual_rate ?? 0.24, default_tenure_weeks: lender.default_tenure_weeks ?? 52, grievance_email: lender.grievance_email ?? "" });
  const m = useMutation({
    mutationFn: () => api(isNew ? "/admin/lenders" : `/admin/lenders/${lender.id}`, { method: isNew ? "POST" : "PUT", body: { ...f, grievance_email: f.grievance_email || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-lenders"] }); onClose(); },
  });
  return (
    <Modal open title={isNew ? "Add lender" : `Edit ${lender.name}`} onClose={onClose}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        {m.error && <Notice tone="error">{(m.error as Error).message}</Notice>}
        <Field label="Name" htmlFor="ln"><input id="ln" className="input" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="α (0–1)" htmlFor="la" hint="Share of bad-week headroom used for the safe EMI."><input id="la" className="input" type="number" step="0.05" min={0.05} max={1} value={f.alpha} onChange={(e) => setF({ ...f, alpha: Number(e.target.value) })} /></Field>
          <Field label="Annual rate" htmlFor="lr" hint="e.g. 0.24 = 24%"><input id="lr" className="input" type="number" step="0.01" min={0} max={0.6} value={f.annual_rate} onChange={(e) => setF({ ...f, annual_rate: Number(e.target.value) })} /></Field>
          <Field label="Tenure (weeks)" htmlFor="lt"><input id="lt" className="input" type="number" min={4} max={156} value={f.default_tenure_weeks} onChange={(e) => setF({ ...f, default_tenure_weeks: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Grievance officer email" htmlFor="lg"><input id="lg" className="input" type="email" value={f.grievance_email} onChange={(e) => setF({ ...f, grievance_email: e.target.value })} /></Field>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={m.isPending}>Save</button></div>
      </form>
    </Modal>
  );
}
