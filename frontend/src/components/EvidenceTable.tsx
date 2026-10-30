import { useTranslation } from "react-i18next";
import { fmtDate, inr, titleCase } from "../lib/format";
import { Pill } from "./ui";

export type LedgerRow = {
  id: number;
  date: string;
  narration: string;
  direction: "credit" | "debit";
  amount: number;
  kind: string;
  category: string;
  platform: string;
  counted: boolean;
  match_status: string;
  matched_to: number | null;
  flags: string[];
  rule: string;
  balance: number | null;
  active_hours: number | null;
  source: string;
  source_kind: string;
  pair?: LedgerRow | null;
};

export function EvidenceTable({ rows, showPair, actions }: { rows: LedgerRow[]; showPair?: boolean; actions?: (r: LedgerRow) => React.ReactNode }) {
  const { t, i18n } = useTranslation();
  if (!rows.length) return <p className="muted py-4">{t("passport.evidence_none")}</p>;
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th scope="col">{t("ledger.date")}</th>
            <th scope="col">{t("ledger.narration")}</th>
            <th scope="col" className="text-right">{t("ledger.amount")}</th>
            <th scope="col">{t("ledger.kind")}</th>
            <th scope="col">{t("ledger.source")}</th>
            {showPair && <th scope="col">Matched payout</th>}
            {actions && <th scope="col"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="whitespace-nowrap">{fmtDate(r.date, i18n.language)}</td>
              <td className="max-w-[18rem] break-words font-mono text-xs text-slate-700">{r.narration}</td>
              <td className={`whitespace-nowrap text-right tabular-nums ${r.direction === "credit" ? "text-emerald-700" : "text-slate-800"}`}>
                {r.direction === "credit" ? "+" : "−"}
                {inr(r.amount, 2)}
              </td>
              <td className="whitespace-nowrap">
                <div className="flex flex-wrap gap-1">
                  <Pill tone={r.counted ? "green" : "slate"}>{t(`ledger.kinds.${r.kind}`, { defaultValue: titleCase(r.kind) })}</Pill>
                  {r.category && !["payout", "general", "customer_payment"].includes(r.category) && <Pill>{titleCase(r.category)}</Pill>}
                  {r.platform && <Pill tone="teal">{r.platform}</Pill>}
                  {r.match_status === "matched" && <Pill tone="green">Matched</Pill>}
                  {r.flags.map((f) => (
                    <Pill key={f} tone="amber">
                      {t(`ledger.flags.${f}`, { defaultValue: titleCase(f) })}
                    </Pill>
                  ))}
                </div>
              </td>
              <td className="whitespace-nowrap text-xs text-slate-500">{r.source}</td>
              {showPair && (
                <td className="whitespace-nowrap text-xs">
                  {r.pair ? (
                    <span>
                      {r.pair.platform} · {fmtDate(r.pair.date)} · {inr(r.pair.amount, 2)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              )}
              {actions && <td className="whitespace-nowrap">{actions(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
