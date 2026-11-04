"use client";

import { useState } from "react";
import { postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";

type Defaults = {
  fcff_millions?: number | null;
  growth_pct?: number | null;
  terminal_pct?: number | null;
  wacc_pct?: number | null;
  net_cash_millions?: number | null;
  shares_millions?: number | null;
  price?: number | null;
  years?: number;
};

function Field({
  label, value, onChange, step = 1, suffix,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: number;
  suffix?: string;
}) {
  return (
    <label className="block">
      <span className="muted text-[10.5px] font-semibold uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-1 mt-1">
        <input type="number" step={step} value={value}
               onChange={(e) => onChange(e.target.value)}
               className="surface rounded-lg w-full px-3 py-2 text-[12.5px] knum"
               style={{ color: "var(--ink)" }} />
        {suffix && <span className="muted text-[10.5px] whitespace-nowrap">{suffix}</span>}
      </div>
    </label>
  );
}

function Money({ v }: { v: any }) {
  return <span className="knum">{inr(v)}</span>;
}

export default function StockCalculators({
  symbol, defaults, price, eps, bvps, onOpenPeers,
}: {
  symbol: string;
  defaults?: Defaults;
  price?: number | null;
  eps?: number | null;
  bvps?: number | null;
  onOpenPeers?: () => void;
}) {
  const [tab, setTab] = useState<"dcf" | "reverse" | "sip" | "lumpsum" | "relative">("dcf");

  const d = defaults || {};
  const [fcff, setFcff] = useState(String(d.fcff_millions ?? ""));
  const [growth, setGrowth] = useState(String(d.growth_pct ?? 8));
  const [terminal, setTerminal] = useState(String(d.terminal_pct ?? 4));
  const [wacc, setWacc] = useState(String(d.wacc_pct ?? 11.5));
  const [netCash, setNetCash] = useState(String(d.net_cash_millions ?? 0));
  const [shares, setShares] = useState(String(d.shares_millions ?? ""));
  const [years, setYears] = useState(String(d.years ?? 5));
  const [dcf, setDcf] = useState<any>(null);
  const [dcfErr, setDcfErr] = useState<string | null>(null);

  const [rPrice, setRPrice] = useState(String(price ?? ""));
  const [rFcff, setRFcff] = useState(String(d.fcff_millions ?? ""));
  const [rTerm, setRTerm] = useState(String(d.terminal_pct ?? 4));
  const [rWacc, setRWacc] = useState(String(d.wacc_pct ?? 11.5));
  const [rCash, setRCash] = useState(String(d.net_cash_millions ?? 0));
  const [rShares, setRShares] = useState(String(d.shares_millions ?? ""));
  const [reverse, setReverse] = useState<any>(null);
  const [revErr, setRevErr] = useState<string | null>(null);

  const [monthly, setMonthly] = useState("5000");
  const [sipYears, setSipYears] = useState("5");
  const [sipReturn, setSipReturn] = useState("12");
  const [sip, setSip] = useState<any>(null);
  const [sipErr, setSipErr] = useState<string | null>(null);

  const [lump, setLump] = useState("100000");
  const [lumpYears, setLumpYears] = useState("5");
  const [lumpReturn, setLumpReturn] = useState("12");
  const [lumpsum, setLumpsum] = useState<any>(null);
  const [lumpErr, setLumpErr] = useState<string | null>(null);

  const [metric, setMetric] = useState<"pe" | "pb">("pe");
  const [multiple, setMultiple] = useState("");
  const [relative, setRelative] = useState<any>(null);
  const [relErr, setRelErr] = useState<string | null>(null);

  const run = async (fn: () => Promise<any>, set: (v: any) => void,
                     setErr: (v: string | null) => void) => {
    setErr(null);
    try {
      set(await fn());
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
  };

  const num = (s: string) => (s === "" ? undefined : Number(s));

  const runDcf = () => run(
    () => postJSON(`/stocks/${symbol}/dcf`, {
      fcff_millions: num(fcff), growth_pct: num(growth),
      terminal_pct: num(terminal), wacc_pct: num(wacc),
      net_cash_millions: num(netCash), shares_millions: num(shares),
      years: Number(years || 5),
    }), setDcf, setDcfErr);

  const runReverse = () => run(
    () => postJSON(`/stocks/${symbol}/reverse-dcf`, {
      price: num(rPrice), fcff_millions: num(rFcff), terminal_pct: num(rTerm),
      wacc_pct: num(rWacc), net_cash_millions: num(rCash),
      shares_millions: num(rShares), years: Number(years || 5),
    }), setReverse, setRevErr);

  const runSip = () => run(
    () => postJSON(`/stocks/${symbol}/sip`, {
      monthly: Number(monthly), years: Number(sipYears),
      annual_return_pct: Number(sipReturn),
    }), setSip, setSipErr);

  const runLump = () => run(
    () => postJSON(`/stocks/${symbol}/lumpsum`, {
      amount: Number(lump), years: Number(lumpYears),
      annual_return_pct: Number(lumpReturn),
    }), setLumpsum, setLumpErr);

  const runRelative = () => run(
    () => postJSON(`/stocks/${symbol}/relative-value`, {
      metric, ...(multiple ? { peer_multiple: Number(multiple) } : {}),
    }), setRelative, setRelErr);

  const tabs = [
    { key: "dcf", label: "DCF" },
    { key: "reverse", label: "Reverse DCF" },
    { key: "sip", label: "SIP" },
    { key: "lumpsum", label: "Lumpsum" },
    { key: "relative", label: "Relative value" },
  ] as const;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)}
                    className={`chip !text-[11px] ${tab === t.key ? "chip-active" : ""}`}>
              {t.label}
            </button>
          ))}
        </div>
        {onOpenPeers && (
          <button onClick={onOpenPeers} className="btn-secondary !py-1.5 !text-[11.5px]">
            + Compare with peers
          </button>
        )}
      </div>

      {tab === "dcf" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Two-stage DCF — your assumptions</div>
            <p className="muted text-[11px] leading-relaxed">
              Defaults come from reported cash flow, net cash and share count. Edit
              anything; the model is yours, not a recommendation.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <Field label="FCFF this year" value={fcff} onChange={setFcff} suffix="₹ mn" />
              <Field label="Growth years 1–5" value={growth} onChange={setGrowth} step={0.5} suffix="%" />
              <Field label="Terminal growth" value={terminal} onChange={setTerminal} step={0.5} suffix="%" />
              <Field label="WACC" value={wacc} onChange={setWacc} step={0.5} suffix="%" />
              <Field label="Net cash / (debt)" value={netCash} onChange={setNetCash} suffix="₹ mn" />
              <Field label="Shares outstanding" value={shares} onChange={setShares} suffix="mn" />
              <Field label="Forecast years" value={years} onChange={setYears} suffix="yrs" />
            </div>
            <button onClick={runDcf} className="btn-primary w-full justify-center">Compute intrinsic value</button>
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Result</div>
            {dcfErr && <p className="text-[12px] text-down font-semibold">{dcfErr}</p>}
            {!dcf && !dcfErr && <p className="muted text-[12.5px]">Set assumptions and compute.</p>}
            {dcf && !dcf.error && (
              <div className="space-y-2 text-[12.5px]">
                <div className="flex justify-between"><span className="muted">PV of explicit years</span><span className="knum">₹{Number(dcf.pv_explicit).toLocaleString("en-IN")} mn</span></div>
                <div className="flex justify-between"><span className="muted">PV of terminal value</span><span className="knum">₹{Number(dcf.pv_terminal).toLocaleString("en-IN")} mn</span></div>
                <div className="flex justify-between"><span className="muted">Equity value</span><span className="knum font-bold">₹{Number(dcf.equity_value_mn).toLocaleString("en-IN")} mn</span></div>
                <div className="flex items-baseline justify-between pt-2" style={{ borderTop: "1px solid var(--line)" }}>
                  <span className="muted font-bold">Per-share value</span>
                  <span className="knum text-[22px] font-black accent"><Money v={dcf.per_share} /></span>
                </div>
                {dcf.current_price && (
                  <div className="flex justify-between">
                    <span className="muted">Versus current price</span>
                    <span className={`knum font-bold ${dcf.upside_pct >= 0 ? "text-up" : "text-down"}`}>
                      {pct(dcf.upside_pct)}
                    </span>
                  </div>
                )}
                <p className="muted text-[10.5px] mt-2 leading-relaxed">{dcf.disclaimer}</p>
              </div>
            )}
            {dcf?.error && <p className="text-[12px] text-down font-semibold">{dcf.error}</p>}
          </div>
        </div>
      )}

      {tab === "reverse" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Reverse DCF — what growth is priced in?</div>
            <p className="muted text-[11px] leading-relaxed">
              Solves for the explicit-period growth rate that makes the model equal
              today's market price, holding WACC and terminal growth fixed.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <Field label="Market price" value={rPrice} onChange={setRPrice} suffix="₹" />
              <Field label="FCFF this year" value={rFcff} onChange={setRFcff} suffix="₹ mn" />
              <Field label="Terminal growth" value={rTerm} onChange={setRTerm} step={0.5} suffix="%" />
              <Field label="WACC" value={rWacc} onChange={setRWacc} step={0.5} suffix="%" />
              <Field label="Net cash / (debt)" value={rCash} onChange={setRCash} suffix="₹ mn" />
              <Field label="Shares outstanding" value={rShares} onChange={setRShares} suffix="mn" />
            </div>
            <button onClick={runReverse} className="btn-primary w-full justify-center">Solve implied growth</button>
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Result</div>
            {revErr && <p className="text-[12px] text-down font-semibold">{revErr}</p>}
            {!reverse && !revErr && <p className="muted text-[12.5px]">Run the model to see the growth rate the price implies.</p>}
            {reverse && (
              <div className="space-y-2 text-[12.5px]">
                <div className="knum text-[30px] font-black accent">
                  {reverse.implied_growth_pct != null ? `${Number(reverse.implied_growth_pct).toFixed(2)}%` : "—"}
                </div>
                <div className="muted text-[11px]">implied annual FCFF growth over the forecast period</div>
                {reverse.assumptions && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className="chip !text-[9px]">WACC {reverse.assumptions.wacc_pct}%</span>
                    <span className="chip !text-[9px]">terminal {reverse.assumptions.terminal_pct}%</span>
                    <span className="chip !text-[9px]">{reverse.assumptions.years} years</span>
                  </div>
                )}
                {reverse.note && <p className="muted text-[10.5px] mt-2 leading-relaxed">{reverse.note}</p>}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "sip" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">SIP calculator with statutory charges</div>
            <p className="muted text-[11px] leading-relaxed">
              A constant-return projection, then the delivery-equity charges you
              would actually pay on the buy and sell legs.
            </p>
            <div className="grid sm:grid-cols-3 gap-2">
              <Field label="Monthly ₹" value={monthly} onChange={setMonthly} />
              <Field label="Years" value={sipYears} onChange={setSipYears} step={0.5} />
              <Field label="Return p.a." value={sipReturn} onChange={setSipReturn} step={0.5} suffix="%" />
            </div>
            <button onClick={runSip} className="btn-primary w-full justify-center">Project SIP</button>
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Projection</div>
            {sipErr && <p className="text-[12px] text-down font-semibold">{sipErr}</p>}
            {!sip && !sipErr && <p className="muted text-[12.5px]">Set the inputs and project.</p>}
            {sip && !sip.error && (
              <div className="space-y-1.5 text-[12.5px]">
                <div className="flex justify-between"><span className="muted">Invested</span><span className="knum"><Money v={sip.invested} /></span></div>
                <div className="flex justify-between"><span className="muted">Future value</span><span className="knum font-bold accent"><Money v={sip.future_value} /></span></div>
                <div className="flex justify-between"><span className="muted">Gain</span><span className="knum text-up"><Money v={sip.gain} /></span></div>
                {sip.charges && (
                  <>
                    <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                      <span className="muted">Statutory charges</span>
                      <span className="knum text-down">−<Money v={sip.charges.total_charges} /></span>
                    </div>
                    <div className="flex justify-between"><span className="muted font-semibold">Net after charges</span><span className="knum font-black"><Money v={sip.net_after_charges} /></span></div>
                    <ChargeList charges={sip.charges} />
                  </>
                )}
                {sip.note && <p className="muted text-[10.5px] mt-2 leading-relaxed">{sip.note}</p>}
              </div>
            )}
            {sip?.error && <p className="text-[12px] text-down font-semibold">{sip.error}</p>}
          </div>
        </div>
      )}

      {tab === "lumpsum" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Lumpsum calculator</div>
            <p className="muted text-[11px] leading-relaxed">
              One-time investment compounded at a constant rate, net of delivery
              STT, exchange, SEBI, stamp duty, DP and GST.
            </p>
            <div className="grid sm:grid-cols-3 gap-2">
              <Field label="Amount ₹" value={lump} onChange={setLump} />
              <Field label="Years" value={lumpYears} onChange={setLumpYears} step={0.5} />
              <Field label="Return p.a." value={lumpReturn} onChange={setLumpReturn} step={0.5} suffix="%" />
            </div>
            <button onClick={runLump} className="btn-primary w-full justify-center">Project lumpsum</button>
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Projection</div>
            {lumpErr && <p className="text-[12px] text-down font-semibold">{lumpErr}</p>}
            {!lumpsum && !lumpErr && <p className="muted text-[12.5px]">Set the inputs and project.</p>}
            {lumpsum && (
              <div className="space-y-1.5 text-[12.5px]">
                <div className="flex justify-between"><span className="muted">Invested</span><span className="knum"><Money v={lumpsum.invested} /></span></div>
                <div className="flex justify-between"><span className="muted">Future value</span><span className="knum font-bold accent"><Money v={lumpsum.future_value} /></span></div>
                <div className="flex justify-between"><span className="muted">Gain</span><span className="knum text-up"><Money v={lumpsum.gain} /></span></div>
                <div className="flex justify-between"><span className="muted">CAGR</span><span className="knum">{pct(lumpsum.cagr_pct)}</span></div>
                {lumpsum.charges && (
                  <>
                    <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                      <span className="muted">Statutory charges</span>
                      <span className="knum text-down">−<Money v={lumpsum.charges.total_charges} /></span>
                    </div>
                    <div className="flex justify-between"><span className="muted font-semibold">Net after charges</span><span className="knum font-black"><Money v={lumpsum.net_after_charges} /></span></div>
                    <ChargeList charges={lumpsum.charges} />
                  </>
                )}
                {lumpsum.note && <p className="muted text-[10.5px] mt-2 leading-relaxed">{lumpsum.note}</p>}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "relative" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Relative value at a peer multiple</div>
            <p className="muted text-[11px] leading-relaxed">
              Uses this company's actual EPS ({eps != null ? inr(eps) : "—"}) or book
              value per share ({bvps != null ? inr(bvps) : "—"}). Leave the multiple
              blank to use the sector median from the local peer set.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block">
                <span className="muted text-[10.5px] font-semibold uppercase tracking-wide">Multiple</span>
                <select value={metric} onChange={(e) => setMetric(e.target.value as "pe" | "pb")}
                        className="surface rounded-lg w-full mt-1 px-3 py-2 text-[12.5px]"
                        style={{ color: "var(--ink)" }}>
                  <option value="pe">P/E × EPS</option>
                  <option value="pb">P/B × book value</option>
                </select>
              </label>
              <Field label="Peer multiple (blank = median)" value={multiple} onChange={setMultiple} step={0.1} suffix="×" />
            </div>
            <button onClick={runRelative} className="btn-primary w-full justify-center">Compute implied price</button>
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Result</div>
            {relErr && <p className="text-[12px] text-down font-semibold">{relErr}</p>}
            {!relative && !relErr && <p className="muted text-[12.5px]">Run the cross-check.</p>}
            {relative && (
              <div className="space-y-2 text-[12.5px]">
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Base / share</div>
                    <div className="knum text-[14px] font-bold mt-0.5"><Money v={relative.base_per_share} /></div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Multiple</div>
                    <div className="knum text-[14px] font-bold mt-0.5">{relative.peer_multiple}×</div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Implied</div>
                    <div className="knum text-[14px] font-black accent mt-0.5"><Money v={relative.implied_price} /></div>
                  </div>
                </div>
                <div className="flex justify-between">
                  <span className="muted">Current price</span>
                  <span className="knum"><Money v={relative.current_price} /></span>
                </div>
                <div className="flex justify-between">
                  <span className="muted">Implied upside</span>
                  <span className={`knum font-black ${relative.upside_pct >= 0 ? "text-up" : "text-down"}`}>
                    {pct(relative.upside_pct)}
                  </span>
                </div>
                {relative.note && <p className="muted text-[10.5px] mt-2 leading-relaxed">{relative.note}</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ChargeList({ charges }: { charges: any }) {
  const detail = charges?.charges_detail || [];
  if (!detail.length) return null;
  return (
    <div className="mt-2 rounded-md overflow-hidden" style={{ border: "1px solid var(--line)" }}>
      <div className="px-2.5 py-1.5 muted text-[9px] font-bold uppercase tracking-wider"
           style={{ background: "var(--surface-2)" }}>
        Charge breakdown
      </div>
      {detail.map((c: any) => (
        <div key={c.name} className="flex items-center justify-between px-2.5 py-1 text-[10.5px] table-row">
          <span className="muted truncate pr-2">{c.name}</span>
          <span className="knum whitespace-nowrap">{inr(c.amount)} <span className="muted">({c.pct}%)</span></span>
        </div>
      ))}
      <div className="px-2.5 py-1 muted text-[9.5px]" style={{ borderTop: "1px solid var(--line)" }}>
        {charges.disclaimer}
      </div>
    </div>
  );
}
