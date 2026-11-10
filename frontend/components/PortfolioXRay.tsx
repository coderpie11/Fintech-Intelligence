"use client";

import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { PageHeader } from "@/components/PageKit";
import { Panel, Metric, Pill, Bar, ErrLine, Note, Loading } from "@/components/quant/Kit";

type HoldingInput = {
  kind: "EQUITY" | "ETF" | "MF";
  symbol?: string; code?: string; name: string;
  quantity: number | null; price: number | null; value: number | null;
};
type Lookup = {
  equities: { symbol: string; name: string; kind: string; sector?: string | null; last?: number | null }[];
  funds: { code: string; name: string; amc?: string | null; category?: string | null }[];
};
type Allocation = { key: string; value_rs: number; weight_pct: number };
type SectorW = { sector: string; value_rs: number; weight_pct: number };
type Overlap = {
  funds: { id: string; name: string; value_rs: number }[];
  matrix: (number | null)[][];
  pairs: { a: string; b: string; overlap_pct: number; common_count: number; common: { name: string; shared_weight_pct: number }[] }[];
  stock_exposure: { name: string; value_rs: number; weight_sum_pct: number; fund_count: number; funds: string[] }[];
  note: string;
};
type FeeDrag = {
  total_fund_value_rs: number; blended_ter_pct: number | null; annual_fee_rs: number;
  funds: { id: string; name: string; value_rs: number; ter_pct: number; annual_fee_rs: number }[];
  horizons: { years: number; cumulative_fee_rs: number | null; opportunity_cost_rs: number | null }[];
  gross_return_pct: number; note: string;
};
type Analyze = {
  summary: { holdings: number; unresolved: string[]; invested_rs: number; value_rs: number; pnl_rs: number; pnl_pct: number | null };
  holdings: { kind: string; key: string; name: string; sector?: string | null; quantity: number | null; price: number | null; value_rs: number; weight_pct: number; ter_pct?: number | null; href?: string }[];
  allocation: Allocation[]; sector_weights: SectorW[];
  overlap: Overlap; fee_drag: FeeDrag; notes: string[];
};

const SAMPLE: HoldingInput[] = [
  { kind: "EQUITY", symbol: "RELIANCE", name: "Reliance Industries", quantity: 20, price: 1150, value: null },
  { kind: "EQUITY", symbol: "HDFCBANK", name: "HDFC Bank", quantity: 40, price: 720, value: null },
  { kind: "MF", code: "122639", name: "Parag Parikh Flexi Cap", quantity: null, price: null, value: 250000 },
  { kind: "MF", code: "131670", name: "Aditya Birla Sun Life", quantity: null, price: null, value: 150000 },
];

export default function PortfolioXRay() {
  const [holdings, setHoldings] = useState<HoldingInput[]>(SAMPLE);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Lookup | null>(null);
  const [data, setData] = useState<Analyze | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2) { setResults(null); return; }
    const t = setTimeout(() => {
      getJSON<Lookup>(`/portfolio-xray/lookup?q=${encodeURIComponent(query.trim())}`)
        .then(setResults).catch(() => setResults(null));
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!holdings.length) { setData(null); return; }
    let dead = false;
    setBusy(true);
    const t = setTimeout(() => {
      postJSON<Analyze>("/portfolio-xray/analyze", {
        holdings: holdings.map((h) => ({
          kind: h.kind, symbol: h.symbol, code: h.code, name: h.name,
          quantity: h.quantity, price: h.price, value: h.value,
        })),
      })
        .then((r) => { if (!dead) { setData(r); setErr(null); } })
        .catch((e: any) => { if (!dead) setErr(e?.message || "Analysis failed."); })
        .finally(() => { if (!dead) setBusy(false); });
    }, 350);
    return () => { dead = true; clearTimeout(t); };
  }, [holdings]);

  const add = (h: HoldingInput) => { setHoldings((prev) => [...prev, h]); setQuery(""); setResults(null); };
  const update = (i: number, patch: Partial<HoldingInput>) =>
    setHoldings((prev) => prev.map((h, j) => (j === i ? { ...h, ...patch } : h)));
  const remove = (i: number) => setHoldings((prev) => prev.filter((_, j) => j !== i));

  const maxAlloc = useMemo(() => Math.max(1, ...(data?.allocation.map((a) => a.weight_pct) || [1])), [data]);
  const maxSector = useMemo(() => Math.max(1, ...(data?.sector_weights.slice(0, 12).map((s) => s.weight_pct) || [1])), [data]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Manual holdings · X-ray"
        title="Portfolio X-Ray"
        sub="Enter your equity, ETF and mutual-fund holdings to see allocation and sector weights, the hidden stock overlap across funds, and the rupee fee drag from expense ratios over 1/3/5/10 years."
        right={busy ? <span className="muted text-[11px]">analyzing…</span> : undefined}
      />

      <div className="grid xl:grid-cols-5 gap-3">
        {/* input panel */}
        <Panel className="xl:col-span-2" title="Your holdings" sub="Search the local universe or add a row manually.">
          <div className="relative">
            <input value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="Search RELIANCE, NIFTYBEES or a fund name…"
                   className="surface rounded-lg w-full px-3 py-2 text-[12px]" style={{ color: "var(--ink)" }} />
            {results && (results.equities.length > 0 || results.funds.length > 0) && (
              <div className="absolute z-20 mt-1 w-full max-h-64 overflow-auto rounded-lg card p-1">
                {results.equities.map((e) => (
                  <button key={e.symbol} onClick={() => add({ kind: e.kind === "ETF" ? "ETF" : "EQUITY", symbol: e.symbol, name: e.name, quantity: 1, price: e.last ?? null, value: null })}
                          className="w-full text-left px-2 py-1.5 rounded hover:bg-[var(--surface-2)] text-[11.5px]">
                    <b>{e.symbol}</b> <span className="muted">{e.name}</span>
                    <span className="muted"> · {e.kind}</span>
                  </button>
                ))}
                {results.funds.map((f) => (
                  <button key={f.code} onClick={() => add({ kind: "MF", code: f.code, name: f.name, quantity: null, price: null, value: 100000 })}
                          className="w-full text-left px-2 py-1.5 rounded hover:bg-[var(--surface-2)] text-[11.5px]">
                    <b>{f.name}</b> <span className="muted"> · {f.amc || "Fund"} ({f.code})</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="mt-3 scroll-x">
            <table className="w-full min-w-[430px] text-[11.5px]">
              <thead>
                <tr className="muted text-[9px] uppercase tracking-wider text-left">
                  <th className="py-1 pr-1.5">Instrument</th><th className="py-1 pr-1.5">Qty</th>
                  <th className="py-1 pr-1.5">Price</th><th className="py-1 pr-1.5">Value ₹</th><th className="py-1" />
                </tr>
              </thead>
              <tbody>
                {holdings.map((h, i) => (
                  <tr key={`${h.symbol || h.code}-${i}`} style={{ borderTop: "1px solid var(--line)" }}>
                    <td className="py-1.5 pr-1.5">
                      <div className="font-semibold">{h.symbol || h.code}</div>
                      <div className="muted text-[9.5px] truncate max-w-[150px]">{h.name}</div>
                    </td>
                    <td className="py-1.5 pr-1.5">
                      <input value={h.quantity ?? ""} inputMode="decimal" onChange={(e) => update(i, { quantity: e.target.value === "" ? null : Number(e.target.value) })}
                             className="surface rounded px-1.5 py-1 text-[11px] knum w-[60px]" style={{ color: "var(--ink)" }} />
                    </td>
                    <td className="py-1.5 pr-1.5">
                      <input value={h.price ?? ""} inputMode="decimal" onChange={(e) => update(i, { price: e.target.value === "" ? null : Number(e.target.value) })}
                             className="surface rounded px-1.5 py-1 text-[11px] knum w-[72px]" style={{ color: "var(--ink)" }} />
                    </td>
                    <td className="py-1.5 pr-1.5">
                      <input value={h.value ?? ""} inputMode="decimal" placeholder="override" onChange={(e) => update(i, { value: e.target.value === "" ? null : Number(e.target.value) })}
                             className="surface rounded px-1.5 py-1 text-[11px] knum w-[88px]" style={{ color: "var(--ink)" }} />
                    </td>
                    <td className="py-1.5 text-right">
                      <button onClick={() => remove(i)} className="muted text-[11px]" aria-label="Remove">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            <button onClick={() => setHoldings(SAMPLE)} className="chip !text-[10px]">Load sample</button>
            <button onClick={() => setHoldings([])} className="chip !text-[10px]">Clear</button>
          </div>
          <Note>For funds enter the current value (or leave quantity/price blank). For equities enter quantity and average price for a P&amp;L read.</Note>
        </Panel>

        {/* results */}
        <div className="xl:col-span-3 space-y-3">
          {err && <ErrLine message={err} />}
          {!data && !err && <Loading label="Waiting for holdings." />}
          {data && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Metric label="Portfolio value" value={inr(data.summary.value_rs)} sub={`${data.summary.holdings} holdings`} />
                <Metric label="Invested" value={inr(data.summary.invested_rs)} sub="cost basis" />
                <Metric label="P&L" value={inr(data.summary.pnl_rs)} sub={pct(data.summary.pnl_pct)} tone={(data.summary.pnl_rs ?? 0) >= 0 ? "up" : "down"} />
                <Metric label="Annual fee" value={inr(data.fee_drag.annual_fee_rs)} sub={`blended TER ${data.fee_drag.blended_ter_pct ?? "—"}%`} tone="warn" />
              </div>
              {data.summary.unresolved.length > 0 && (
                <Note>Could not resolve: {data.summary.unresolved.join(", ")}. Check the symbol or fund code.</Note>
              )}

              <Panel title="Asset allocation & sector weights" sub="Funds are looked through to their disclosed holdings for the sector split.">
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <div className="muted text-[10px] font-bold uppercase tracking-wider mb-2">By wrapper</div>
                    {data.allocation.map((a) => (
                      <div key={a.key} className="mb-2">
                        <div className="flex justify-between text-[11.5px]"><span>{a.key}</span><span className="knum">{a.weight_pct}%</span></div>
                        <Bar value={(a.weight_pct / maxAlloc) * 100} />
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="muted text-[10px] font-bold uppercase tracking-wider mb-2">Top sectors</div>
                    {data.sector_weights.slice(0, 10).map((s) => (
                      <div key={s.sector} className="mb-2">
                        <div className="flex justify-between text-[11.5px]"><span className="truncate max-w-[150px]">{s.sector}</span><span className="knum">{s.weight_pct}%</span></div>
                        <Bar value={(s.weight_pct / maxSector) * 100} tone="accent" />
                      </div>
                    ))}
                  </div>
                </div>
              </Panel>

              <Panel title="Cross-fund stock overlap" sub={data.overlap.note}>
                {data.overlap.funds.length < 2 ? (
                  <Note>Add two or more funds/ETFs to expose hidden concentration.</Note>
                ) : (
                  <>
                    <div className="scroll-x">
                      <table className="text-[11.5px] min-w-[520px]">
                        <thead>
                          <tr className="muted text-[9px] uppercase tracking-wider">
                            <th className="py-1 px-2 text-left">Overlap %</th>
                            {data.overlap.funds.map((f) => <th key={f.id} className="py-1 px-2 text-right truncate max-w-[110px]">{f.name.slice(0, 16)}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {data.overlap.funds.map((f, i) => (
                            <tr key={f.id} style={{ borderTop: "1px solid var(--line)" }}>
                              <td className="py-1 px-2 font-semibold truncate max-w-[160px]">{f.name}</td>
                              {data.overlap.matrix[i].map((v, j) => (
                                <td key={j} className="py-1 px-2 text-right knum"
                                    style={v != null && v >= 50 && i !== j ? { color: "var(--warn)", fontWeight: 700 } : undefined}>
                                  {v == null ? "—" : `${v}%`}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3 mt-3">
                      <div>
                        <div className="muted text-[10px] font-bold uppercase tracking-wider mb-1.5">Highest overlaps</div>
                        <ul className="space-y-1.5">
                          {data.overlap.pairs.slice(0, 4).map((p, i) => (
                            <li key={i} className="text-[11px] rounded-md px-2 py-1.5" style={{ border: "1px solid var(--line)" }}>
                              <div className="flex justify-between gap-2"><span className="truncate">{p.a.slice(0, 20)} ↔ {p.b.slice(0, 20)}</span><Pill tone={p.overlap_pct >= 40 ? "warn" : "neutral"}>{p.overlap_pct}%</Pill></div>
                              <div className="muted truncate">{p.common.slice(0, 4).map((c) => c.name).join(", ")}</div>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <div className="muted text-[10px] font-bold uppercase tracking-wider mb-1.5">Aggregate stock exposure</div>
                        <ul className="space-y-1">
                          {data.overlap.stock_exposure.slice(0, 6).map((s) => (
                            <li key={s.name} className="flex justify-between text-[11px]">
                              <span className="truncate max-w-[150px]">{s.name} <span className="muted">·{s.fund_count}f</span></span>
                              <span className="knum">{inr(s.value_rs)}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </>
                )}
              </Panel>

              <Panel title="Expense-ratio fee drag" sub={data.fee_drag.note}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {data.fee_drag.horizons.map((h) => (
                    <div key={h.years} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                      <div className="muted text-[9px] font-bold uppercase tracking-wider">{h.years}Y</div>
                      <div className="knum text-[14px] font-bold mt-0.5" style={{ color: "var(--warn)" }}>{h.cumulative_fee_rs == null ? "—" : inr(h.cumulative_fee_rs)}</div>
                      <div className="muted text-[9.5px] mt-0.5">opportunity cost {h.opportunity_cost_rs == null ? "—" : inr(h.opportunity_cost_rs)}</div>
                    </div>
                  ))}
                </div>
                {data.fee_drag.funds.length > 0 && (
                  <div className="scroll-x mt-3">
                    <table className="w-full text-[11.5px]">
                      <thead>
                        <tr className="muted text-[9px] uppercase tracking-wider text-left">
                          <th className="py-1 pr-2">Fund</th><th className="py-1 pr-2 text-right">Value</th>
                          <th className="py-1 pr-2 text-right">TER</th><th className="py-1 text-right">Annual fee</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.fee_drag.funds.map((f) => (
                          <tr key={f.id} style={{ borderTop: "1px solid var(--line)" }}>
                            <td className="py-1.5 pr-2 truncate max-w-[220px]">{f.name}</td>
                            <td className="py-1.5 pr-2 text-right knum">{inr(f.value_rs)}</td>
                            <td className="py-1.5 pr-2 text-right knum">{f.ter_pct}%</td>
                            <td className="py-1.5 text-right knum" style={{ color: "var(--warn)" }}>{inr(f.annual_fee_rs)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Note>Blended TER {data.fee_drag.blended_ter_pct ?? "—"}% · gross-return assumption {data.fee_drag.gross_return_pct}% (edit via API or treat as a sensitivity).</Note>
              </Panel>
            </>
          )}
        </div>
      </div>

      <Note>
        Portfolio X-Ray is a factual computation on your own inputs and the platform&apos;s stored fund/equity data.
        It is not investment advice. Overlap uses the latest disclosed monthly portfolios, which lag by up to a month.
      </Note>
    </div>
  );
}
