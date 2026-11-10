"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { PageHeader } from "@/components/PageKit";
import { Panel, Metric, Pill, Bar, Loading, ErrLine, Note, signed } from "@/components/quant/Kit";
import PreMarketStrip from "@/components/PreMarketStrip";

type Row = {
  strike: number; expiry: string; dte: number; lot_size: number;
  ce_oi: number | null; ce_chg_oi: number | null; ce_iv: number | null; ce_ltp: number | null;
  pe_oi: number | null; pe_chg_oi: number | null; pe_iv: number | null; pe_ltp: number | null;
};
type Chain = {
  mode: string; underlying: string; underlyingValue: number | null;
  expiries: string[]; active_expiry: string | null;
  spot: Env; pcr: Env; max_oi_support: Env; max_oi_resistance: Env;
  rows: Row[]; max_pain: Env; max_pain_payout?: number | null;
  max_pain_curve?: { strike: number; payout: number }[];
  greeks_note?: string; model_note?: string;
};
type ULists = {
  indices: { symbol: string; name: string; kind: string; lot_size?: number | null }[];
  stocks: { symbol: string; name: string; kind: string; sector?: string | null }[];
  stock_count: number; note: string;
};
type FutRow = {
  expiry: string; last: number; change: number; change_pct: number | null;
  oi: number | null; chg_oi: number | null; oi_change_pct: number | null;
  volume: number | null; buildup: string;
};
type FuturesResp = {
  underlying: string; spot: number | null; futures: FutRow[];
  rollover: { near_expiry: string; next_expiry: string; near_oi: number | null; next_oi: number | null; rollover_pct: number | null; next_premium: number; next_premium_pct: number | null; note: string } | null;
  ban_meter: { applicable: boolean; banned: boolean | null; threshold_pct: number; utilization_pct: number | null; state: string; source: string; note: string };
  delivery_traps: { applicable: boolean; alerts: { strike: number; option_type: string; expiry: string; days_to_expiry: number; last: number; intrinsic: number; notional_per_unit: number; margin_per_lot: number | null; risk: string }[]; count: number; note?: string };
  lot_size: number | null; note: string;
};
type Leg = { side: "BUY" | "SELL"; option_type: "CE" | "PE"; strike: number; premium: number; lots: number };
type Payoff = {
  underlying: string; spot_reference: number; net_premium: number; premium_side: string;
  max_profit: number | null; max_profit_unbounded: boolean;
  max_loss: number | null; max_loss_unbounded: boolean;
  breakevens: number[]; curve: { spot: number; pnl: number }[]; note: string;
};

const TABS = [
  { key: "chain", label: "Option Chain" },
  { key: "futures", label: "Futures & Rollover" },
  { key: "strategy", label: "Strategy Builder" },
  { key: "premarket", label: "Pre-market & VIX" },
];
const LOT_SIZES: Record<string, number> = {
  NIFTY: 75, BANKNIFTY: 35, FINNIFTY: 65, MIDCPNIFTY: 120,
  NIFTYNXT50: 25, SENSEX: 20,
};

function ev<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}
function fmtOI(n?: number | null): string {
  if (n == null) return "—";
  const a = Math.abs(n);
  if (a >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`;
  if (a >= 1e5) return `${(n / 1e5).toFixed(2)}L`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}
function toneOf(n: number | null | undefined): "up" | "down" | "neutral" {
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "up" : "down";
}

function PayoffChart({ curve, spot }: { curve: { spot: number; pnl: number }[]; spot: number }) {
  if (curve.length < 2) return null;
  const W = 680, H = 240, P = 34;
  const xs = curve.map((p) => p.spot), ys = curve.map((p) => p.pnl);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys, 0), maxY = Math.max(...ys, 0);
  const sx = (v: number) => P + ((v - minX) / (maxX - minX || 1)) * (W - 2 * P);
  const sy = (v: number) => H - P - ((v - minY) / (maxY - minY || 1)) * (H - 2 * P);
  const path = curve.map((p, i) => `${i ? "L" : "M"}${sx(p.spot).toFixed(1)},${sy(p.pnl).toFixed(1)}`).join(" ");
  const zero = sy(0);
  const profit = ys.some((v) => v > 0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Expiry payoff curve">
      <line x1={P} x2={W - P} y1={zero} y2={zero} stroke="var(--line)" strokeWidth="1" />
      <line x1={sx(spot)} x2={sx(spot)} y1={P / 2} y2={H - P} stroke="var(--accent)" strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
      <path d={path} fill="none" stroke={profit ? "var(--accent)" : "var(--warn)"} strokeWidth="2.2" />
      <text x={P} y={H - 12} fill="var(--muted)" fontSize="9">{inr(minX)}</text>
      <text x={W - P} y={H - 12} fill="var(--muted)" fontSize="9" textAnchor="end">{inr(maxX)}</text>
      <text x={P} y={P - 6} fill="var(--muted)" fontSize="9">P/L at expiry (₹)</text>
    </svg>
  );
}

function presetLegs(name: string, s: number, step: number, premium: (k: number, t: "CE" | "PE") => number): Leg[] {
  const atm = Math.round(s / step) * step;
  const L = (side: Leg["side"], option_type: Leg["option_type"], strike: number): Leg =>
    ({ side, option_type, strike, premium: Math.max(premium(strike, option_type), 1), lots: 1 });
  if (name === "bull") return [L("BUY", "CE", atm), L("SELL", "CE", atm + step * 4)];
  if (name === "bear") return [L("BUY", "PE", atm), L("SELL", "PE", atm - step * 4)];
  if (name === "iron") return [L("BUY", "PE", atm - step * 2), L("SELL", "PE", atm - step), L("SELL", "CE", atm + step), L("BUY", "CE", atm + step * 2)];
  if (name === "straddle") return [L("SELL", "CE", atm), L("SELL", "PE", atm)];
  if (name === "strangle") return [L("BUY", "CE", atm + step * 2), L("BUY", "PE", atm - step * 2)];
  return [L("BUY", "CE", atm)];
}

export default function FnoHub() {
  const [lists, setLists] = useState<ULists | null>(null);
  const [symbol, setSymbol] = useState("NIFTY");
  const [expiry, setExpiry] = useState("");
  const [chain, setChain] = useState<Chain | null>(null);
  const [chainBusy, setChainBusy] = useState(false);
  const [chainErr, setChainErr] = useState<string | null>(null);
  const [fut, setFut] = useState<FuturesResp | null>(null);
  const [futErr, setFutErr] = useState<string | null>(null);
  const [tab, setTab] = useState("chain");

  const [spot, setSpot] = useState(0);
  const [lotSize, setLotSize] = useState(75);
  const [legs, setLegs] = useState<Leg[]>([]);
  const [payoff, setPayoff] = useState<Payoff | null>(null);
  const [payoffErr, setPayoffErr] = useState<string | null>(null);
  const presetApplied = useRef(false);

  /* ---------------------------- loaders ---------------------------- */
  useEffect(() => {
    getJSON<ULists>("/fno/underlyings").then(setLists).catch(() => setLists(null));
  }, []);

  const loadChain = useCallback((sym: string, exp: string) => {
    setChainBusy(true); setChainErr(null);
    const q = exp ? `?expiry=${encodeURIComponent(exp)}` : "";
    getJSON<Chain>(`/fno/${encodeURIComponent(sym)}${q}`)
      .then((c) => {
        setChain(c);
        if (!exp) setExpiry(c.active_expiry || "");
      })
      .catch((e: any) => setChainErr(e?.message || "Option chain unavailable."))
      .finally(() => setChainBusy(false));
  }, []);

  const loadFutures = useCallback((sym: string) => {
    setFutErr(null);
    getJSON<FuturesResp>(`/fno/futures/${encodeURIComponent(sym)}${LOT_SIZES[sym] ? `?lot_size=${LOT_SIZES[sym]}` : ""}`)
      .then(setFut)
      .catch((e: any) => { setFut(null); setFutErr(e?.message || "Futures feed unavailable."); });
  }, []);

  useEffect(() => {
    setExpiry(""); setChain(null); setFut(null); setPayoff(null);
    setSpot(0); setLegs([]);
    loadChain(symbol, "");
    loadFutures(symbol);
    setLotSize(LOT_SIZES[symbol] ?? 1);
    presetApplied.current = false;
  }, [symbol, loadChain, loadFutures]);

  useEffect(() => {
    if (!chain) return;
    const s = chain.underlyingValue ?? ev(chain.spot);
    if (s && spot === 0) setSpot(Math.round(s));
  }, [chain, spot]);

  /* --------------------------- strategy --------------------------- */
  const step = useMemo(() => (spot > 20000 ? 100 : spot > 5000 ? 50 : spot > 1000 ? 20 : 5), [spot]);
  const premiumFor = useCallback((k: number, t: "CE" | "PE") => {
    const rows = chain?.rows || [];
    const row = rows.reduce<Row | null>((best, r) => !best || Math.abs(r.strike - k) < Math.abs(best.strike - k) ? r : best, null);
    const v = t === "CE" ? row?.ce_ltp : row?.pe_ltp;
    return v && v > 0 ? v : Math.max(5, Math.round(spot * 0.004));
  }, [chain, spot]);

  useEffect(() => {
    if (!chain || spot <= 0 || presetApplied.current) return;
    setLegs(presetLegs("bull", spot, step, premiumFor));
    presetApplied.current = true;
  }, [chain, spot, step, premiumFor]);

  useEffect(() => {
    if (!legs.length || spot <= 0) { setPayoff(null); return; }
    let dead = false;
    const t = setTimeout(() => {
      postJSON<Payoff>("/fno/strategy/payoff", {
        underlying: symbol, spot, points: 41, span_pct: 8,
        legs: legs.map((l) => ({ ...l, lot_size: lotSize })),
      }).then((p) => { if (!dead) { setPayoff(p); setPayoffErr(null); } })
        .catch((e: any) => { if (!dead) { setPayoff(null); setPayoffErr(e?.message || "Payoff unavailable."); } });
    }, 250);
    return () => { dead = true; clearTimeout(t); };
  }, [legs, spot, lotSize, symbol]);

  const updateLeg = (i: number, patch: Partial<Leg>) =>
    setLegs((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const applyPreset = (name: string) => {
    if (spot <= 0) return;
    setLegs(presetLegs(name, spot, step, premiumFor));
  };

  /* ----------------------------- chain ----------------------------- */
  const sortedRows = useMemo(() => [...(chain?.rows || [])].sort((a, b) => a.strike - b.strike), [chain]);
  const atm = chain?.underlyingValue ?? 0;
  const nearest = useMemo(() => {
    let best = 0;
    sortedRows.forEach((r, i) => {
      if (Math.abs(r.strike - atm) < Math.abs(sortedRows[best]?.strike - atm)) best = i;
    });
    return best;
  }, [sortedRows, atm]);
  const visible = sortedRows.slice(Math.max(0, nearest - 8), nearest + 9);
  const maxPain = ev<number>(chain?.max_pain);

  const idxGroup = lists?.indices || [];
  const stockGroup = lists?.stocks || [];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Derivatives terminal"
        title="F&O Hub"
        sub="Live NSE option chains with max pain, futures 4-quadrant buildup, rollover, MWPL ban state, physical-delivery alerts and a 4-leg expiry payoff builder. Every model-derived figure is labelled."
        right={<Link href="/calculators" className="btn-secondary !px-3.5 !py-2 !text-[12.5px]">Option calculators</Link>}
      />

      {/* toolbar */}
      <div className="card p-3 flex flex-wrap items-end gap-2.5">
        <label className="block min-w-[210px]">
          <span className="muted text-[9px] font-bold uppercase tracking-[0.13em]">Underlying</span>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
                  className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px]" style={{ color: "var(--ink)" }}>
            <optgroup label="Index derivatives">
              {idxGroup.map((i) => <option key={i.symbol} value={i.symbol}>{i.name} ({i.symbol})</option>)}
            </optgroup>
            <optgroup label={`Stocks · ${lists?.stock_count ?? 0}`}>
              {stockGroup.map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol} — {s.name.slice(0, 34)}</option>)}
            </optgroup>
          </select>
        </label>
        <label className="block min-w-[170px]">
          <span className="muted text-[9px] font-bold uppercase tracking-[0.13em]">Expiry</span>
          <select value={expiry} onChange={(e) => { setExpiry(e.target.value); if (e.target.value) loadChain(symbol, e.target.value); }}
                  className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum" style={{ color: "var(--ink)" }}>
            {(chain?.expiries || []).map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <div className="ml-auto flex items-center gap-2">
          {chainBusy && <span className="muted text-[11px]">loading chain…</span>}
          <button className="btn-secondary !px-3 !py-1.5 !text-[11.5px]"
                  onClick={() => { loadChain(symbol, expiry); loadFutures(symbol); }}>
            Refresh
          </button>
        </div>
      </div>

      {/* tabs */}
      <div className="mt-4 flex flex-wrap gap-1" role="tablist" aria-label="F&O workspaces">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key}
                  onClick={() => setTab(t.key)}
                  className={`chip !text-[11px] ${tab === t.key ? "chip-active" : ""}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-3 space-y-3">
        {tab === "chain" && (
          chainErr ? <ErrLine message={chainErr} onRetry={() => loadChain(symbol, expiry)} /> :
          !chain ? <Loading label="Loading the option chain." /> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
                <Metric label="Spot" value={inr(chain.underlyingValue)} sub={chain.mode === "live" ? "exchange chain" : "model chain"} />
                <Metric label="PCR (OI)" value={String(ev(chain.pcr) ?? "—")} sub="put/call open interest" />
                <Metric label="Max pain" value={maxPain == null ? "—" : inr(maxPain)} sub="minimum buyer payout" tone="accent" />
                <Metric label="Max OI support" value={inr(ev(chain.max_oi_support))} sub="highest put OI below spot" tone="up" />
                <Metric label="Max OI resistance" value={inr(ev(chain.max_oi_resistance))} sub="highest call OI above spot" tone="down" />
                <Metric label="Active expiry" value={chain.active_expiry || "—"} sub={`${chain.rows.length} strikes`} mono={false} />
              </div>

              <Panel title="Live option chain" sub="ATM window, 8 strikes each side. OI in contracts. Model chains leave OI blank rather than fabricate it.">
                <div className="scroll-x">
                  <table className="w-full min-w-[640px] text-[11.5px] knum">
                    <thead>
                      <tr className="muted text-[9px] uppercase tracking-wider">
                        <th className="py-1.5 pr-2 text-right">CE OI</th>
                        <th className="py-1.5 pr-2 text-right">CE IV</th>
                        <th className="py-1.5 pr-2 text-right">CE LTP</th>
                        <th className="py-1.5 px-2 text-center">Strike</th>
                        <th className="py-1.5 pl-2 text-right">PE LTP</th>
                        <th className="py-1.5 pl-2 text-right">PE IV</th>
                        <th className="py-1.5 pl-2 text-right">PE OI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((r) => {
                        const isAtm = r.strike === atm;
                        const isPain = maxPain != null && r.strike === maxPain;
                        return (
                          <tr key={`${r.expiry}-${r.strike}`}
                              style={{
                                borderTop: "1px solid var(--line)",
                                background: isAtm ? "color-mix(in srgb, var(--accent) 9%, transparent)"
                                  : isPain ? "color-mix(in srgb, var(--warn) 7%, transparent)" : undefined,
                              }}>
                            <td className="py-1.5 pr-2 text-right">{fmtOI(r.ce_oi)}</td>
                            <td className="py-1.5 pr-2 text-right">{r.ce_iv == null ? "—" : `${r.ce_iv.toFixed(1)}%`}</td>
                            <td className="py-1.5 pr-2 text-right">{r.ce_ltp == null ? "—" : inr(r.ce_ltp)}</td>
                            <td className="py-1.5 px-2 text-center font-bold">
                              {r.strike.toFixed(0)}
                              {isAtm && <span className="ml-1 text-[8px] accent font-black">ATM</span>}
                              {isPain && <span className="ml-1 text-[8px]" style={{ color: "var(--warn)" }}>MAX PAIN</span>}
                            </td>
                            <td className="py-1.5 pl-2 text-right">{r.pe_ltp == null ? "—" : inr(r.pe_ltp)}</td>
                            <td className="py-1.5 pl-2 text-right">{r.pe_iv == null ? "—" : `${r.pe_iv.toFixed(1)}%`}</td>
                            <td className="py-1.5 pl-2 text-right">{fmtOI(r.pe_oi)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <Note>{chain.model_note || chain.greeks_note || "Press a row in the calculator tab to replay a position."} Max pain = strike with the lowest total option-buyer payout across the chain&apos;s own OI.</Note>
              </Panel>
            </>
          )
        )}

        {tab === "futures" && (
          futErr ? <ErrLine message={futErr} onRetry={() => loadFutures(symbol)} /> :
          !fut ? <Loading label="Loading the futures matrix." /> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Metric label="Spot" value={inr(fut.spot)} sub="underlying" />
                <Metric label="Rollover" value={fut.rollover?.rollover_pct == null ? "—" : `${fut.rollover.rollover_pct}%`} sub={fut.rollover ? `${fut.rollover.next_expiry} OI share` : "no next expiry"} />
                <Metric label="Ban state" value={fut.ban_meter.state} sub="95% MWPL meter" tone={fut.ban_meter.banned ? "down" : "neutral"} mono={false} />
                <Metric label="Delivery alerts" value={String(fut.delivery_traps.count)} sub="ITM stock options, ≤4 DTE" tone={fut.delivery_traps.count ? "warn" : "neutral"} />
              </div>

              <div className="grid xl:grid-cols-3 gap-3">
                <Panel className="xl:col-span-2" title="Futures 4-quadrant buildup" sub="Price change × open-interest change. Long buildup / short buildup / short covering / long unwinding.">
                  <div className="scroll-x">
                    <table className="w-full min-w-[560px] text-[11.5px] knum">
                      <thead>
                        <tr className="muted text-[9px] uppercase tracking-wider text-left">
                          <th className="py-1.5 pr-2">Expiry</th><th className="py-1.5 pr-2 text-right">Last</th>
                          <th className="py-1.5 pr-2 text-right">Chg %</th><th className="py-1.5 pr-2 text-right">OI</th>
                          <th className="py-1.5 pr-2 text-right">Δ OI</th><th className="py-1.5 text-right">Read</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fut.futures.map((f) => (
                          <tr key={f.expiry} style={{ borderTop: "1px solid var(--line)" }}>
                            <td className="py-1.5 pr-2 font-semibold">{f.expiry}</td>
                            <td className="py-1.5 pr-2 text-right">{inr(f.last)}</td>
                            <td className={`py-1.5 pr-2 text-right ${toneOf(f.change_pct) === "up" ? "text-up" : toneOf(f.change_pct) === "down" ? "text-down" : ""}`}>{pct(f.change_pct)}</td>
                            <td className="py-1.5 pr-2 text-right">{fmtOI(f.oi)}</td>
                            <td className={`py-1.5 pr-2 text-right ${toneOf(f.chg_oi) === "up" ? "text-up" : toneOf(f.chg_oi) === "down" ? "text-down" : ""}`}>{f.chg_oi == null ? "—" : signed(f.chg_oi, 0)}</td>
                            <td className="py-1.5 text-right">
                              <Pill tone={f.buildup === "Long Buildup" ? "up" : f.buildup === "Short Buildup" ? "down" : f.buildup === "Short Covering" ? "accent" : "warn"}>{f.buildup}</Pill>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {fut.rollover && (
                    <div className="grid sm:grid-cols-3 gap-2 mt-3">
                      <Metric label="Near OI" value={fmtOI(fut.rollover.near_oi)} sub={fut.rollover.near_expiry} />
                      <Metric label="Next OI" value={fmtOI(fut.rollover.next_oi)} sub={fut.rollover.next_expiry} />
                      <Metric label="Roll cost" value={inr(fut.rollover.next_premium)} sub={pct(fut.rollover.next_premium_pct)} />
                    </div>
                  )}
                  <Note>{fut.note} {fut.rollover?.note}</Note>
                </Panel>

                <div className="space-y-3">
                  <Panel title="MWPL 95% ban meter" sub={fut.ban_meter.source}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[12px] font-bold">{fut.ban_meter.state}</span>
                      <span className="muted text-[10.5px]">threshold {fut.ban_meter.threshold_pct}%</span>
                    </div>
                    <Bar value={fut.ban_meter.utilization_pct ?? 0} tone={fut.ban_meter.banned ? "down" : "up"} />
                    <Note>{fut.ban_meter.note}</Note>
                  </Panel>

                  <Panel title="Physical-delivery margin trap" sub={fut.delivery_traps.applicable ? "Near-expiry ITM stock options can be assigned." : "Index derivatives are cash settled."}>
                    {!fut.delivery_traps.applicable ? (
                      <Note>No physical-delivery obligation on this underlying.</Note>
                    ) : fut.delivery_traps.count === 0 ? (
                      <Note>No ITM stock options inside the 4-day delivery window.</Note>
                    ) : (
                      <ul className="space-y-1.5">
                        {fut.delivery_traps.alerts.map((a, i) => (
                          <li key={`${a.strike}-${a.option_type}-${i}`} className="rounded-md px-2.5 py-2 text-[11px]" style={{ border: "1px solid var(--line)" }}>
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-bold">{a.strike.toFixed(0)} {a.option_type}</span>
                              <Pill tone="warn">{a.days_to_expiry} DTE</Pill>
                            </div>
                            <div className="muted mt-0.5">intrinsic {inr(a.intrinsic)} · notional/unit {inr(a.notional_per_unit)}{a.margin_per_lot ? ` · margin/lot ${inr(a.margin_per_lot)}` : ""}</div>
                          </li>
                        ))}
                      </ul>
                    )}
                    {fut.delivery_traps.note && <Note>{fut.delivery_traps.note}</Note>}
                  </Panel>
                </div>
              </div>
            </>
          )
        )}

        {tab === "strategy" && (
          <div className="grid xl:grid-cols-5 gap-3">
            <Panel className="xl:col-span-3" title="Expiry payoff builder" sub="Up to 4 legs. Premiums are per unit; lots × lot size is the multiplier.">
              <div className="flex flex-wrap gap-1.5 mb-3">
                {[["bull", "Bull Call Spread"], ["bear", "Bear Put Spread"], ["iron", "Iron Condor"], ["straddle", "Short Straddle"], ["strangle", "Long Strangle"]].map(([k, label]) => (
                  <button key={k} onClick={() => applyPreset(k)} className="chip !text-[10px]">{label}</button>
                ))}
                <button onClick={() => setLegs([])} className="chip !text-[10px]">Clear</button>
              </div>
              <div className="scroll-x">
                <table className="w-full min-w-[560px] text-[11.5px]">
                  <thead>
                    <tr className="muted text-[9px] uppercase tracking-wider text-left">
                      <th className="py-1 pr-1.5">Side</th><th className="py-1 pr-1.5">Type</th>
                      <th className="py-1 pr-1.5">Strike</th><th className="py-1 pr-1.5">Premium</th>
                      <th className="py-1 pr-1.5">Lots</th><th className="py-1" />
                    </tr>
                  </thead>
                  <tbody>
                    {legs.map((l, i) => (
                      <tr key={i} style={{ borderTop: "1px solid var(--line)" }}>
                        <td className="py-1.5 pr-1.5">
                          <select value={l.side} onChange={(e) => updateLeg(i, { side: e.target.value as Leg["side"] })}
                                  className="surface rounded px-1.5 py-1 text-[11px]" style={{ color: "var(--ink)" }}>
                            <option>BUY</option><option>SELL</option>
                          </select>
                        </td>
                        <td className="py-1.5 pr-1.5">
                          <select value={l.option_type} onChange={(e) => updateLeg(i, { option_type: e.target.value as Leg["option_type"] })}
                                  className="surface rounded px-1.5 py-1 text-[11px]" style={{ color: "var(--ink)" }}>
                            <option>CE</option><option>PE</option>
                          </select>
                        </td>
                        <td className="py-1.5 pr-1.5">
                          <input value={l.strike} inputMode="decimal" onChange={(e) => updateLeg(i, { strike: Number(e.target.value) || 0 })}
                                 className="surface rounded px-1.5 py-1 text-[11px] knum w-[86px]" style={{ color: "var(--ink)" }} />
                        </td>
                        <td className="py-1.5 pr-1.5">
                          <input value={l.premium} inputMode="decimal" onChange={(e) => updateLeg(i, { premium: Number(e.target.value) || 0 })}
                                 className="surface rounded px-1.5 py-1 text-[11px] knum w-[76px]" style={{ color: "var(--ink)" }} />
                        </td>
                        <td className="py-1.5 pr-1.5">
                          <input value={l.lots} inputMode="numeric" onChange={(e) => updateLeg(i, { lots: Number(e.target.value) || 0 })}
                                 className="surface rounded px-1.5 py-1 text-[11px] knum w-[58px]" style={{ color: "var(--ink)" }} />
                        </td>
                        <td className="py-1.5 text-right">
                          <button onClick={() => setLegs((prev) => prev.filter((_, j) => j !== i))}
                                  className="muted text-[11px]" aria-label="Remove leg">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-end gap-2 mt-3">
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em]">Spot reference</span>
                  <input value={spot || ""} inputMode="decimal" onChange={(e) => setSpot(Number(e.target.value) || 0)}
                         className="surface rounded-lg mt-1 px-2.5 py-2 text-[12px] knum w-[130px]" style={{ color: "var(--ink)" }} />
                </label>
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em]">Lot size</span>
                  <input value={lotSize} inputMode="numeric" onChange={(e) => setLotSize(Number(e.target.value) || 1)}
                         className="surface rounded-lg mt-1 px-2.5 py-2 text-[12px] knum w-[100px]" style={{ color: "var(--ink)" }} />
                </label>
                <button onClick={() => setLegs((prev) => prev.length >= 4 ? prev : [...prev, { side: "BUY", option_type: "CE", strike: Math.round(spot / step) * step, premium: premiumFor(Math.round(spot / step) * step, "CE"), lots: 1 }])}
                        className="btn-secondary !px-3 !py-1.5 !text-[11.5px]">+ Add leg</button>
              </div>
              <Note>Preset premiums are taken from the nearest chain strike when available, otherwise an illustrative 0.4% of spot. Edit them before reading the payoff.</Note>
            </Panel>

            <div className="xl:col-span-2 space-y-3">
              <Panel title="Strategy outcome">
                {payoffErr ? <ErrLine message={payoffErr} /> : !payoff ? <Note>Add at least one leg to compute the payoff.</Note> : (
                  <>
                    <div className="grid grid-cols-2 gap-2">
                      <Metric label={payoff.premium_side} value={inr(Math.abs(payoff.net_premium))} sub="net premium" />
                      <Metric label="Max profit" value={payoff.max_profit_unbounded ? "Unlimited" : inr(payoff.max_profit)} tone="up" sub={payoff.max_profit_unbounded ? "open-ended tail" : "at expiry"} />
                      <Metric label="Max loss" value={payoff.max_loss_unbounded ? "Unlimited" : inr(payoff.max_loss)} tone="down" sub={payoff.max_loss_unbounded ? "open-ended tail" : "at expiry"} />
                      <Metric label="Breakeven" value={payoff.breakevens.length ? payoff.breakevens.map((b) => inr(b)).join(" / ") : "—"} mono={false} sub="spot at expiry" />
                    </div>
                    <div className="mt-3 rounded-lg" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                      <PayoffChart curve={payoff.curve} spot={payoff.spot_reference} />
                    </div>
                    <Note>{payoff.note}</Note>
                  </>
                )}
              </Panel>
              <Panel title="Legs" sub="Each leg is one expiry contract.">
                <ul className="space-y-1 text-[11.5px]">
                  {legs.map((l, i) => (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span><Pill tone={l.side === "BUY" ? "up" : "down"}>{l.side}</Pill> <span className="font-semibold">{l.strike.toFixed(0)} {l.option_type}</span></span>
                      <span className="muted knum">{inr(l.premium)} × {l.lots} lot</span>
                    </li>
                  ))}
                  {!legs.length && <li className="muted">No legs.</li>}
                </ul>
              </Panel>
            </div>
          </div>
        )}

        {tab === "premarket" && <PreMarketStrip />}
      </div>

      <Note>
        Derivative levels and payoffs are factual/mathematical outputs from public exchange data, not buy or sell
        recommendations. F&amp;O trading carries leverage and can lose more than the premium shown. Verify lot sizes,
        margins and contract expiries with your broker before trading.
      </Note>
    </div>
  );
}
