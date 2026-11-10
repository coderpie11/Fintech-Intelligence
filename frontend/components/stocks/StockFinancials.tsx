"use client";

import { useMemo, useState } from "react";
import { inr } from "@/lib/format";
import MetricTip from "@/components/MetricTip";

type Block = { periods: string[]; sections: Record<string, Record<string, any[]>>; units?: string; source?: string; basis?: string };
type Statements = {
  annual?: Block;
  quarterly?: Block;
  standalone?: Block | null;
  consolidated_available?: boolean;
  note?: string;
};

const ROWS: Record<string, { key: string; label: string; tip?: string }[]> = {
  income: [
    { key: "revenue", label: "Revenue", tip: "Total sales recognised in the period." },
    { key: "expenses", label: "Expenses" },
    { key: "operating_profit", label: "Operating profit" },
    { key: "opm_pct", label: "Operating margin %" },
    { key: "other_income", label: "Other income" },
    { key: "interest_expense", label: "Interest expense" },
    { key: "depreciation", label: "Depreciation" },
    { key: "pretax_income", label: "Profit before tax" },
    { key: "tax_pct", label: "Tax rate %" },
    { key: "net_income", label: "Net profit" },
    { key: "eps", label: "EPS (₹)" },
    { key: "dividend_payout_pct", label: "Dividend payout %" },
    { key: "ebitda", label: "EBITDA" },
    { key: "gross_profit", label: "Gross profit" },
  ],
  balance: [
    { key: "equity_capital", label: "Equity capital" },
    { key: "reserves", label: "Reserves" },
    { key: "equity", label: "Shareholders' equity" },
    { key: "borrowings", label: "Borrowings" },
    { key: "total_debt", label: "Total debt" },
    { key: "other_liabilities", label: "Other liabilities" },
    { key: "total_liabilities", label: "Total liabilities" },
    { key: "fixed_assets", label: "Fixed assets" },
    { key: "cwip", label: "Capital work in progress" },
    { key: "investments", label: "Investments" },
    { key: "cash", label: "Cash & equivalents" },
    { key: "inventory", label: "Inventory" },
    { key: "receivables", label: "Receivables" },
    { key: "other_assets", label: "Other assets" },
    { key: "total_assets", label: "Total assets" },
    { key: "current_assets", label: "Current assets" },
    { key: "current_liabilities", label: "Current liabilities" },
    { key: "retained_earnings", label: "Retained earnings" },
    { key: "payables", label: "Payables" },
  ],
  cashflow: [
    { key: "cfo", label: "Cash from operations" },
    { key: "cfi", label: "Cash from investing" },
    { key: "cff", label: "Cash from financing" },
    { key: "capex", label: "Capital expenditure" },
    { key: "fcf", label: "Free cash flow" },
    { key: "net_cash_flow", label: "Net cash flow" },
  ],
};

const MONEY = new Set([
  "revenue", "expenses", "operating_profit", "other_income", "interest_expense",
  "depreciation", "pretax_income", "net_income", "ebitda", "gross_profit",
  "equity_capital", "reserves", "equity", "borrowings", "total_debt",
  "other_liabilities", "total_liabilities", "fixed_assets", "cwip", "investments",
  "cash", "inventory", "receivables", "other_assets", "total_assets",
  "current_assets", "current_liabilities", "retained_earnings", "payables",
  "cfo", "cfi", "cff", "capex", "fcf", "net_cash_flow",
]);

const BASE: Record<string, string> = {
  income: "revenue",
  balance: "total_assets",
  cashflow: "cfo",
};

function fmtCell(v: any, common: boolean): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (common) return `${v.toFixed(1)}%`;
  return inr(v, 0);
}

export default function StockFinancials({
  statements,
  shareholding,
}: {
  statements?: Statements;
  shareholding?: any;
}) {
  const hasStandalone = Boolean(statements?.standalone?.periods?.length);
  const [basis, setBasis] = useState<"consolidated" | "standalone">("consolidated");
  const [freq, setFreq] = useState<"annual" | "quarterly">("annual");
  const [section, setSection] = useState<"income" | "balance" | "cashflow" | "shareholding">("income");
  const [common, setCommon] = useState(false);

  const block: Block | undefined = useMemo(() => {
    if (basis === "standalone") return statements?.standalone || undefined;
    if (freq === "quarterly") return statements?.quarterly;
    return statements?.annual;
  }, [statements, basis, freq]);

  const periods = (block?.periods || []).slice(0, 5);
  const rows = ROWS[section] || [];
  const data = block?.sections?.[section] || {};
  const baseVals: any[] = (data[BASE[section]] as any[]) || [];
  const hasBase = baseVals.some((v) => v != null && v !== 0);

  const visibleRows = rows.filter((r) => {
    const vals = data[r.key];
    return Array.isArray(vals) && vals.slice(0, 5).some((v) => v !== null && v !== undefined);
  });

  const shpPeriods: string[] = (shareholding?.periods || []).slice(0, 6);
  const shpSeries: Record<string, any[]> = shareholding?.series || {};
  const shpRows: string[] = [
    "Promoters", "FIIs", "DIIs", "Government", "Public", "No. of Shareholders",
  ].filter((k) => Array.isArray(shpSeries[k]));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {(["income", "balance", "cashflow", "shareholding"] as const).map((s) => (
            <button key={s} onClick={() => setSection(s)}
                    className={`chip !text-[11px] ${section === s ? "chip-active" : ""}`}>
              {s === "income" ? "Income" : s === "balance" ? "Balance sheet" : s === "cashflow" ? "Cash flow" : "Shareholding"}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {section !== "shareholding" && (
            <>
              <div className="flex items-center gap-1 rounded-md p-0.5"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                {(["annual", "quarterly"] as const).map((f) => (
                  <button key={f} onClick={() => setFreq(f)}
                          disabled={basis === "standalone" && f === "quarterly"}
                          className={`rounded px-2 py-1 text-[10.5px] font-semibold ${freq === f && !(basis === "standalone" && f === "quarterly") ? "text-white" : "muted"}`}
                          style={freq === f && !(basis === "standalone" && f === "quarterly")
                            ? { background: "var(--accent)", color: "#041018" } : undefined}>
                    {f === "annual" ? "Annual" : "Quarterly"}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1 rounded-md p-0.5"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                {(["consolidated", "standalone"] as const).map((b) => (
                  <button key={b} onClick={() => setBasis(b)} disabled={b === "standalone" && !hasStandalone}
                          className={`rounded px-2 py-1 text-[10.5px] font-semibold ${basis === b ? "text-white" : "muted"}`}
                          style={basis === b ? { background: "var(--accent)", color: "#041018" } : undefined}
                          title={b === "standalone" && !hasStandalone ? "Standalone statements were not published on the free source for this company." : undefined}>
                    {b === "consolidated" ? "Consolidated" : "Standalone"}
                  </button>
                ))}
              </div>
              <button onClick={() => setCommon((v) => !v)}
                      className={`chip !text-[10.5px] ${common ? "chip-active" : ""}`}>
                {common ? "Common size" : "Absolute ₹ crore"}
              </button>
            </>
          )}
        </div>
      </div>

      {section === "shareholding" ? (
        <div className="card overflow-hidden">
          <div className="scroll-x">
            <table className="w-full min-w-[700px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  <th className="table-head text-left px-3 py-2.5">Holder category</th>
                  {shpPeriods.map((p) => (
                    <th key={p} className="table-head text-right px-3 py-2.5 whitespace-nowrap">{p}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shpRows.map((k) => (
                  <tr key={k} className="table-row">
                    <td className="px-3 py-2 text-[12px] font-semibold">{k}</td>
                    {shpPeriods.map((_, i) => {
                      const v = shpSeries[k]?.[i];
                      return (
                        <td key={i} className="px-3 py-2 text-right knum text-[12px]">
                          {v == null ? "—" : k === "No. of Shareholders"
                            ? Number(v).toLocaleString("en-IN")
                            : `${Number(v).toFixed(2)}%`}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-3 py-2 muted text-[10.5px]"
               style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
            {shareholding?.source || "Quarterly shareholding pattern"} · percentages of total equity shares.
          </div>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="scroll-x">
            <table className="w-full min-w-[720px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  <th className="table-head text-left px-3 py-2.5">Line item</th>
                  {periods.map((p) => (
                    <th key={p} className="table-head text-right px-3 py-2.5 whitespace-nowrap">{p}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((r) => (
                  <tr key={r.key} className="table-row">
                    <td className="px-3 py-2 text-[12px] font-semibold">
                      {r.tip ? <MetricTip label={r.label} tip={{ meaning: r.tip }}>{r.label}</MetricTip> : r.label}
                    </td>
                    {periods.map((_, i) => {
                      const raw = data[r.key]?.[i];
                      const isMoney = MONEY.has(r.key);
                      const colBase = baseVals[i];
                      const showCommon = common && isMoney && hasBase
                        && colBase != null && colBase !== 0 && raw != null;
                      const val = showCommon ? (raw / colBase) * 100 : raw;
                      return (
                        <td key={i} className="px-3 py-2 text-right knum text-[12px]">
                          {fmtCell(val, showCommon)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-3 py-2 muted text-[10.5px] flex flex-wrap gap-x-4 gap-y-1"
               style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
            <span>{block?.source || "Reported statements"}</span>
            <span className="opacity-40">·</span>
            <span>{basis === "standalone" ? "Standalone" : "Consolidated"} · {freq}</span>
            <span className="opacity-40">·</span>
            <span>
              {common
                ? `Common size: each monetary line as % of ${
                    BASE[section] === "revenue" ? "same-period revenue"
                    : BASE[section] === "total_assets" ? "same-period total assets"
                    : "same-period operating cash flow"}.`
                : "Values in ₹ crore; percentages and per-share items are shown as reported."}
            </span>
          </div>
        </div>
      )}

      {basis === "standalone" && !hasStandalone && (
        <p className="muted text-[11.5px]">
          Standalone statements are not available from the free source for this company;
          consolidated figures are shown instead.
        </p>
      )}
      {statements?.note && <p className="muted text-[11px] leading-relaxed">{statements.note}</p>}
    </div>
  );
}
