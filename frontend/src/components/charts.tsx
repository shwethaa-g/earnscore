import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { inr, shortWeek, fmtDate } from "../lib/format";

const ACCENT = "#0f7a6b";
const MUTED = "#94a3b8";

export function SeasonalityChart({ series, labels }: { series: { weeks: string[]; raw: number[]; adjusted: number[] }; labels: { raw: string; adjusted: string } }) {
  const data = series.weeks.map((w, i) => ({ week: w, raw: series.raw[i], adjusted: series.adjusted[i] }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="week" tickFormatter={shortWeek} minTickGap={28} tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis tickFormatter={(v) => `₹${Math.round(v / 1000)}k`} width={44} tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip formatter={(v: number) => inr(v)} labelFormatter={(l) => `Week of ${fmtDate(String(l))}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="raw" name={labels.raw} stroke={MUTED} dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line type="monotone" dataKey="adjusted" name={labels.adjusted} stroke={ACCENT} dot={false} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ points, scoreLabel }: { points: { as_of: string; score: number; band: string }[]; scoreLabel: string }) {
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="as_of" tickFormatter={(v) => new Date(v + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis domain={[0, 100]} width={32} tick={{ fontSize: 11, fill: "#64748b" }} />
          {[80, 65, 50, 35].map((y) => (
            <ReferenceLine key={y} y={y} stroke="#e2e8f0" strokeDasharray="4 4" />
          ))}
          <Tooltip formatter={(v: number, _n, p: any) => [`${v} (Band ${p.payload.band})`, scoreLabel]} labelFormatter={(l) => fmtDate(String(l))} />
          <Line type="monotone" dataKey="score" name={scoreLabel} stroke={ACCENT} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PillarBar({ score, label, weight, onClick, desc }: { score: number; label: string; weight: string; desc?: string; onClick?: () => void }) {
  const tone = score >= 65 ? "bg-accent-600" : score >= 50 ? "bg-amber-500" : "bg-orange-500";
  const body = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-slate-800">{label}</span>
        <span className="text-sm font-semibold tabular-nums">{score}</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label={label}>
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(2, score)}%` }} />
      </div>
      <div className="mt-1 flex justify-between gap-2 text-xs text-slate-500">
        <span className="truncate">{desc}</span>
        <span className="shrink-0">{weight}</span>
      </div>
    </>
  );
  if (!onClick) return <div className="py-1">{body}</div>;
  return (
    <button className="block w-full rounded-lg p-2 text-left hover:bg-slate-50" onClick={onClick}>
      {body}
    </button>
  );
}
