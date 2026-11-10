"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import MetricTip, { type Tip } from "@/components/MetricTip";
import { Skeleton } from "./PageKit";

type Greek = {
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  theta_per_unit?: number | null;
  vega?: number | null;
  pop?: number | null;
};

type Row = {
  strike: number;
  expiry?: string;
  dte?: number;
  lot_size?: number;
  ce_oi?: number | null;
  ce_chg_oi?: number | null;
  ce_volume?: number | null;
  ce_iv?: number | null;
  ce_ltp?: number | null;
  pe_oi?: number | null;
  pe_chg_oi?: number | null;
  pe_volume?: number | null;
  pe_iv?: number | null;
  pe_ltp?: number | null;
  ce_greeks?: Greek;
  pe_greeks?: Greek;
};

type Horizon = {
  label: string;
  days: number;
  move_points: number;
  move_pct: number;
  lower: number;
  upper: number;
};

type Chain = {
  mode: "live" | "model" | "vix";
  underlying?: string;
  underlyingValue?: number;
  expiries?: string[];
  active_expiry?: string;
  spot?: Env;
  pcr?: Env;
  max_oi_support?: Env;
  max_oi_resistance?: Env;
  rows?: Row[];
  greeks_note?: string;
  model_note?: string;
  lot_size?: number;
  dte?: number;
  vix?: Env;
  regime?: Env;
  percentile_1y?: Env;
  vix_52w_high?: Env;
  vix_52w_low?: Env;
  horizons?: Horizon[];
  formula?: string;
  note?: string;
};

const TIPS: Record<string, Tip> = {
  pcr: {
    meaning:
      "Put/Call ratio: total put open interest divided by total call open interest. Above 1 suggests heavier put writing (often supportive); below 1 suggests call-heavy positioning.",
    formula: "PCR = Σ Put OI ÷ Σ Call OI",
    example: "12.4 lakh put OI against 10.0 lakh call OI gives a PCR of 1.24.",
  },
  iv: {
    meaning:
      "Implied Volatility: the annualised volatility the option price implies. Higher IV means the market is pricing bigger future swings, so options cost more.",
    formula: "IV is the σ that makes the Black-Scholes price equal the market price",
    example: "IV of 14% means the market prices roughly a ±14% annualised move.",
  },
  delta: {
    meaning:
      "Delta: how much the option premium moves for a ₹1 move in the underlying. Calls are 0 to +1, puts are −1 to 0. It is also a rough probability proxy.",
    formula: "Delta = ∂Premium ÷ ∂Spot",
    example: "A 0.42 call delta gains about ₹0.42 when spot rises ₹1.",
  },
  gamma: {
    meaning:
      "Gamma: how much delta itself changes for a ₹1 spot move. It is highest near the strike and close to expiry, which is why ATM options accelerate.",
    formula: "Gamma = ∂Delta ÷ ∂Spot",
    example: "Gamma of 0.0012 means delta rises by 0.0012 for each ₹1 move.",
  },
  theta: {
    meaning:
      "Theta: the premium an option loses to time decay each day, all else equal. The figure shown is per lot, so it is the rupee bleed on the position.",
    formula: "Theta = ∂Premium ÷ ∂Time (one day)",
    example: "Theta of −₹14.65 means one lot loses about ₹14.65 overnight.",
  },
  vega: {
    meaning:
      "Vega: how much the premium changes for a one percentage-point move in implied volatility. Long options gain when IV rises.",
    formula: "Vega = ∂Premium ÷ ∂IV (1 percentage point)",
    example: "Vega of 14 means a 1-point IV rise adds about ₹14 per unit.",
  },
  pop: {
    meaning:
      "Probability of Profit at expiry: the model's chance the option finishes in the money, derived from the risk-neutral distribution. It is not a certainty.",
    formula: "POP(call) = N(d2) · POP(put) = N(−d2)",
    example: "A 35% POP call loses money about 65% of the time at expiry.",
  },
  vix: {
    meaning:
      "INDIA VIX is the market's 30-day expected annualised volatility implied by NIFTY option prices. It rises when fear and hedging demand rise.",
    formula: "Expected move ≈ Spot × (VIX ÷ 100) × √(T ÷ 252)",
    example: "NIFTY 23,000 with VIX 15 gives a 1-month 1σ move of about ±990 points.",
  },
  bet: { meaning: "Call (CE) is a tezi / upside bet. Put (PE) is a mandi / downside-protection bet." },
  strike: { meaning: "Woh level jahan aap shart/contract laga rahe ho — the price at which the option becomes valuable at expiry." },
  lots: { meaning: "How many market lots you are buying. One lot already contains the exchange's fixed number of units." },
  lotSize: { meaning: "Units inside one lot. NIFTY is 75 units per lot; the exchange sets this and it changes from time to time." },
  premium: { meaning: "The price you actually paid per unit for the option. This is your maximum loss if the option expires worthless." },
  entryTime: { meaning: "The time you entered the trade. Time decay is charged from this moment." },
  move: { meaning: "How much you expect the underlying to move from here. Positive means up, negative means down." },
  horizon: { meaning: "How long you plan to hold the option before checking the result." },
  ivShift: { meaning: "How much market fear (IV) changes. Positive means options get costlier; negative means they get cheaper." },
};

function envNum<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}

function Lbl({ label, tip }: { label: string; tip?: Tip }) {
  return (
    <span className="muted text-[10px] font-bold uppercase tracking-wider">
      {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
    </span>
  );
}

function fmtOI(n?: number | null): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`;
  if (Math.abs(n) >= 1e5) return `${(n / 1e5).toFixed(2)}L`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(Math.round(n));
}

function num(v: number | null | undefined, dec = 2): string {
  return v == null || Number.isNaN(v) ? "—" : v.toFixed(dec);
}

function nowIst(): string {
  try {
    return new Date().toLocaleTimeString("en-GB", {
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
    });
  } catch {
    return "10:00";
  }
}

function Unavailable({ env, what }: { env?: Env; what: string }) {
  if (envNum(env) != null) return <>{inr(envNum(env))}</>;
  return (
    <span className="muted text-[11px]" title={env?.note || `${what} is not available from a free feed`}>
      not on free feed
    </span>
  );
}

function GreekCell({
  g, field, dec = 2, suffix = "",
}: {
  g?: Greek;
  field: "delta" | "gamma" | "theta" | "vega";
  dec?: number;
  suffix?: string;
}) {
  const v = g?.[field];
  return (
    <td className={`px-2 py-1.5 text-right knum text-[10.5px] ${field === "theta" ? "text-down" : "muted"}`}>
      {v == null ? "—" : `${num(v, dec)}${suffix}`}
    </td>
  );
}

function PopCell({ g }: { g?: Greek }) {
  const v = g?.pop;
  return (
    <td className="px-2 py-1.5 text-right knum text-[10.5px] muted">
      {v == null ? "—" : `${(v * 100).toFixed(0)}%`}
    </td>
  );
}

export default function FnoTab({ underlying }: { underlying: string }) {
  const [chain, setChain] = useState<Chain | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [exp, setExp] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [cols, setCols] = useState({ chgOi: false, iv: false, pop: false, greeks: false });
  const scrollRef = useRef<HTMLDivElement>(null);
  const atmRef = useRef<HTMLTableRowElement>(null);

  // Replay state
  const [rType, setRType] = useState<"CE" | "PE">("CE");
  const [rStrike, setRStrike] = useState("");
  const [rLots, setRLots] = useState("1");
  const [rLotSize, setRLotSize] = useState("1");
  const [rEntry, setREntry] = useState("");
  const [rEntryTime, setREntryTime] = useState(nowIst());
  const [rHorizon, setRHorizon] = useState("+30m");
  const [rMove, setRMove] = useState("0.5");
  const [rIvShift, setRIvShift] = useState("0");
  const [replay, setReplay] = useState<any>(null);
  const [replayErr, setReplayErr] = useState<string | null>(null);
  const [replayBusy, setReplayBusy] = useState(false);
  const autoRan = useRef(false);

  // Reset the chosen expiry only when the underlying contract changes —
  // resetting it inside the fetch effect created an infinite request loop.
  useEffect(() => {
    setExp(null);
    autoRan.current = false;
  }, [underlying]);

  useEffect(() => {
    let live = true;
    setChain(null);
    setErr(null);
    const url = exp
      ? `/fno/${encodeURIComponent(underlying)}?expiry=${encodeURIComponent(exp)}`
      : `/fno/${encodeURIComponent(underlying)}`;
    getJSON<Chain>(url)
      .then((r) => {
        if (!live) return;
        setChain(r);
        if (!exp && r.active_expiry) setExp(r.active_expiry);
      })
      .catch((e) => {
        if (live) setErr(String(e.message || e));
      });
    return () => {
      live = false;
    };
  }, [underlying, exp]);

  const rows = useMemo(
    () => [...(chain?.rows || [])].sort((a, b) => a.strike - b.strike),
    [chain],
  );
  const spot = chain?.underlyingValue ?? envNum(chain?.spot);
  const activeExp = exp || chain?.active_expiry || null;
  const atm = useMemo(() => {
    if (!spot || !rows.length) return null;
    return rows.reduce((best, r) =>
      Math.abs(r.strike - spot) < Math.abs(best.strike - spot) ? r : best, rows[0]).strike;
  }, [rows, spot]);
  const atmRow = useMemo(
    () => (atm == null ? null : rows.find((r) => r.strike === atm) || null),
    [rows, atm],
  );
  const atmStraddle = atmRow && (atmRow.ce_ltp != null || atmRow.pe_ltp != null)
    ? (atmRow.ce_ltp ?? 0) + (atmRow.pe_ltp ?? 0)
    : null;
  const modelIv = atmRow?.ce_iv ?? rows[0]?.ce_iv ?? null;
  const dte = atmRow?.dte ?? chain?.dte ?? null;
  const defaultLot = atmRow?.lot_size || chain?.lot_size || 1;

  const visible = useMemo(() => {
    if (showAll || atm == null) return rows;
    const idx = rows.findIndex((r) => r.strike === atm);
    if (idx < 0) return rows;
    return rows.slice(Math.max(0, idx - 10), idx + 11);
  }, [rows, atm, showAll]);

  // Simple view keeps only the three core columns on each side. The filter
  // dropdown adds ΔOI, IV, POP and the full Greek set on demand.
  const anyExtra = cols.chgOi || cols.iv || cols.pop || cols.greeks;
  const callCols = useMemo(() => {
    const c = ["oi"];
    if (cols.chgOi) c.push("chgOi");
    c.push("vol");
    if (cols.iv) c.push("iv");
    c.push("ltp");
    if (cols.greeks) c.push("delta", "gamma", "theta", "vega");
    if (cols.pop) c.push("pop");
    return c;
  }, [cols]);
  const putCols = useMemo(() => {
    const c: string[] = [];
    if (cols.pop) c.push("pop");
    if (cols.greeks) c.push("vega", "theta", "gamma", "delta");
    c.push("ltp");
    if (cols.iv) c.push("iv");
    c.push("vol");
    if (cols.chgOi) c.push("chgOi");
    c.push("oi");
    return c;
  }, [cols]);

  // Keep the ATM row vertically centred inside the 540px scroll window.
  useEffect(() => {
    const box = scrollRef.current;
    const row = atmRef.current;
    if (!box || !row) return;
    const target = row.offsetTop - box.clientHeight / 2 + row.offsetHeight / 2;
    box.scrollTop = Math.max(0, target);
  }, [atm, activeExp, showAll, chain?.mode]);

  const runReplay = async (overrides?: Partial<{
    strike: number; type: "CE" | "PE"; entry: number; lotSize: number;
    lots: number; entryTime: string; horizon: string; move: number;
  }>) => {
    const strike = overrides?.strike ?? Number(rStrike);
    const type = overrides?.type ?? rType;
    const entry = overrides?.entry ?? Number(rEntry);
    const lotSize = overrides?.lotSize ?? Number(rLotSize);
    const lots = overrides?.lots ?? Number(rLots);
    const entryTime = overrides?.entryTime ?? rEntryTime;
    const horizon = overrides?.horizon ?? rHorizon;
    const move = overrides?.move ?? Number(rMove);
    if (!Number.isFinite(strike) || strike <= 0) {
      setReplayErr("Enter a valid strike.");
      return;
    }
    if (!Number.isFinite(entry) || entry <= 0) {
      setReplayErr("Enter the option premium you paid (or click an LTP in the chain).");
      return;
    }
    setReplayBusy(true);
    setReplayErr(null);
    try {
      const r = await postJSON("/fno/replay", {
        underlying,
        option_type: type,
        strike,
        spot: spot ?? undefined,
        entry_price: entry,
        lot_size: Math.max(1, Math.round(lotSize || 1)),
        lots: Math.max(1, Math.round(lots || 1)),
        entry_time: entryTime || undefined,
        horizon,
        target_spot_move_pct: Number.isFinite(move) ? move : 0,
        iv_shift_pct: Number(rIvShift) || 0,
        expiry: activeExp || undefined,
        days_to_expiry: dte ?? undefined,
      });
      setReplay(r);
    } catch (e: any) {
      setReplay(null);
      setReplayErr(String(e.message || e).slice(0, 220));
    } finally {
      setReplayBusy(false);
    }
  };

  // First load: seed the replay with the real ATM strike and its LTP so the
  // calculator is immediately useful rather than an empty form.
  useEffect(() => {
    if (autoRan.current || !chain || chain.mode === "vix" || !atmRow) return;
    const entry = atmRow.ce_ltp;
    if (entry == null || entry <= 0) return;
    autoRan.current = true;
    setRStrike(String(atmRow.strike));
    setRType("CE");
    setREntry(String(entry));
    setRLotSize(String(defaultLot));
    setRLots("1");
    setRHorizon("+30m");
    setRMove("0.5");
    setREntryTime(nowIst());
    runReplay({
      strike: atmRow.strike, type: "CE", entry, lotSize: defaultLot,
      lots: 1, entryTime: nowIst(), horizon: "+30m", move: 0.5,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chain, atmRow, defaultLot]);

  if (err) {
    return (
      <div className="card p-5" style={{ borderColor: "color-mix(in srgb, var(--warn) 35%, var(--line))" }}>
        <div className="text-[13px] font-semibold">Chain unavailable right now</div>
        <p className="muted text-[12px] mt-1.5 leading-relaxed">{err}</p>
        <p className="muted text-[11.5px] mt-1">
          NSE throttles its free option-chain endpoint. Retry in a minute — the rest of the desk is unaffected.
        </p>
      </div>
    );
  }

  if (!chain) return <Skeleton rows={8} />;

  /* ------------------------------ INDIA VIX ------------------------------ */
  if (chain.mode === "vix") {
    const vix = envNum(chain.vix);
    const regime = String(envNum(chain.regime) ?? "—");
    const pctile = envNum(chain.percentile_1y);
    const tone = regime === "Calm" ? "up" : regime === "Normal" ? "accent"
      : regime === "Elevated" ? "warn" : "down";

    return (
      <div className="space-y-3">
        <div className="grid md:grid-cols-[300px_1fr] gap-3">
          <div className="card p-4">
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">
              <MetricTip label="INDIA VIX" tip={TIPS.vix} />
            </div>
            <div className="knum text-[40px] font-black leading-none mt-1.5">
              {vix != null ? vix.toFixed(2) : "—"}
            </div>
            <div className="flex items-center gap-2 mt-2.5">
              <span className="chip !text-[9.5px]"
                    style={{
                      color: `var(--${tone})`,
                      borderColor: `color-mix(in srgb, var(--${tone}) 35%, var(--line))`,
                      background: `color-mix(in srgb, var(--${tone}) 10%, transparent)`,
                    }}>
                {regime} regime
              </span>
              <span className="chip !text-[9.5px]">30-day implied</span>
            </div>

            <div className="mt-4">
              <div className="flex items-center justify-between muted text-[10px] mb-1.5">
                <span className="font-bold uppercase tracking-[0.13em]">1-year percentile</span>
                <span className="knum">{pctile != null ? `${pctile.toFixed(0)}%` : "—"}</span>
              </div>
              <div className="relative h-2 rounded-full overflow-hidden"
                   style={{ background: "var(--line)" }}>
                <div className="absolute inset-y-0 left-0 rounded-full"
                     style={{ width: `${Math.max(0, Math.min(100, pctile ?? 0))}%`,
                              background: "linear-gradient(90deg,var(--up),var(--warn),var(--down))" }} />
              </div>
              <div className="flex justify-between muted text-[10px] mt-1.5">
                <span>Calm</span><span>Fear</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-4">
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">52W low</div>
                <div className="knum text-[13px] font-bold mt-0.5">
                  {envNum(chain.vix_52w_low)?.toFixed(2) ?? "—"}
                </div>
              </div>
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">52W high</div>
                <div className="knum text-[13px] font-bold mt-0.5">
                  {envNum(chain.vix_52w_high)?.toFixed(2) ?? "—"}
                </div>
              </div>
            </div>
          </div>

          <div className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-[14px] font-extrabold">Expected NIFTY swing</h3>
                <p className="muted text-[11px] mt-0.5">
                  One standard deviation band from the current NIFTY level at the current VIX.
                </p>
              </div>
              <span className="chip !text-[9.5px]">NIFTY {inr(envNum(chain.spot))}</span>
            </div>

            <div className="grid sm:grid-cols-3 gap-2">
              {(chain.horizons || []).map((h) => (
                <div key={h.label} className="rounded-lg p-3"
                     style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  <div className="flex items-center justify-between">
                    <span className="text-[11.5px] font-bold">{h.label}</span>
                    <span className="chip !text-[8.5px] !py-0.5">{h.days} session{h.days > 1 ? "s" : ""}</span>
                  </div>
                  <div className="knum text-[19px] font-black mt-2">±{inr(h.move_points)}</div>
                  <div className="muted text-[10px] mt-0.5">±{h.move_pct.toFixed(2)}% of spot</div>
                  <div className="mt-2.5 pt-2.5 space-y-1" style={{ borderTop: "1px solid var(--line)" }}>
                    <div className="flex justify-between knum text-[10.5px]">
                      <span className="muted">Lower</span><span className="text-down font-semibold">{inr(h.lower)}</span>
                    </div>
                    <div className="flex justify-between knum text-[10.5px]">
                      <span className="muted">Upper</span><span className="text-up font-semibold">{inr(h.upper)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-3 rounded-md px-3 py-2.5"
                 style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1">Formula</div>
              <div className="knum text-[12px] accent">{chain.formula}</div>
            </div>
          </div>
        </div>

        <div className="card p-4">
          <p className="muted text-[12px] leading-relaxed">{chain.note}</p>
          <p className="muted text-[11.5px] mt-2 leading-relaxed">
            <strong style={{ color: "var(--ink)" }}>How to read it:</strong> these are one-standard-deviation
            bands, not forecasts. Roughly two-thirds of outcomes should land inside the band if volatility
            stays at today's level; the remaining third lands outside. Volatility itself changes, which is
            why the bands widen and narrow over time.
          </p>
        </div>
      </div>
    );
  }

  /* ------------------------------ OPTION CHAIN ------------------------------ */
  const isModel = chain.mode === "model";
  const oiCell = (v: number | null | undefined) => (isModel ? "—" : fmtOI(v));

  const HEAD: Record<string, string> = {
    oi: "People / OI",
    chgOi: "ΔOI",
    vol: "Volume",
    iv: "IV",
    ltp: "LTP ₹",
    delta: "Speed Δ",
    gamma: "Gamma",
    theta: "Time Θ ₹/d",
    vega: "Vega",
    pop: "Win %",
  };

  const callCell = (k: string, r: Row) => {
    switch (k) {
      case "oi":
        return (
          <td key={k} className="px-2 py-1.5 text-right knum text-[11px]"
              style={{ color: spot != null && r.strike < spot ? "var(--ink)" : "var(--muted)" }}>
            {oiCell(r.ce_oi)}
          </td>
        );
      case "chgOi":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{oiCell(r.ce_chg_oi)}</td>;
      case "vol":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{oiCell(r.ce_volume)}</td>;
      case "iv":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{r.ce_iv != null ? `${r.ce_iv.toFixed(1)}%` : "—"}</td>;
      case "ltp":
        return (
          <td key={k} className="px-2 py-1.5 text-right">
            <button onClick={() => {
              setRType("CE"); setRStrike(String(r.strike));
              setRLotSize(String(r.lot_size || defaultLot));
              if (r.ce_ltp != null) setREntry(String(r.ce_ltp));
            }}
                    className="knum text-[11.5px] font-semibold hover:underline"
                    title="Use this call's strike and LTP in the replay calculator">
              {r.ce_ltp != null ? r.ce_ltp.toFixed(2) : "—"}
            </button>
          </td>
        );
      case "delta": return <GreekCell key={k} g={r.ce_greeks} field="delta" />;
      case "gamma": return <GreekCell key={k} g={r.ce_greeks} field="gamma" dec={4} />;
      case "theta": return <GreekCell key={k} g={r.ce_greeks} field="theta" />;
      case "vega": return <GreekCell key={k} g={r.ce_greeks} field="vega" />;
      case "pop": return <PopCell key={k} g={r.ce_greeks} />;
      default: return null;
    }
  };

  const putCell = (k: string, r: Row) => {
    switch (k) {
      case "oi":
        return (
          <td key={k} className="px-2 py-1.5 text-right knum text-[11px]"
              style={{ color: spot != null && r.strike > spot ? "var(--ink)" : "var(--muted)" }}>
            {oiCell(r.pe_oi)}
          </td>
        );
      case "chgOi":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{oiCell(r.pe_chg_oi)}</td>;
      case "vol":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{oiCell(r.pe_volume)}</td>;
      case "iv":
        return <td key={k} className="px-2 py-1.5 text-right knum text-[10.5px] muted">{r.pe_iv != null ? `${r.pe_iv.toFixed(1)}%` : "—"}</td>;
      case "ltp":
        return (
          <td key={k} className="px-2 py-1.5 text-right">
            <button onClick={() => {
              setRType("PE"); setRStrike(String(r.strike));
              setRLotSize(String(r.lot_size || defaultLot));
              if (r.pe_ltp != null) setREntry(String(r.pe_ltp));
            }}
                    className="knum text-[11.5px] font-semibold hover:underline"
                    title="Use this put's strike and LTP in the replay calculator">
              {r.pe_ltp != null ? r.pe_ltp.toFixed(2) : "—"}
            </button>
          </td>
        );
      case "delta": return <GreekCell key={k} g={r.pe_greeks} field="delta" />;
      case "gamma": return <GreekCell key={k} g={r.pe_greeks} field="gamma" dec={4} />;
      case "theta": return <GreekCell key={k} g={r.pe_greeks} field="theta" />;
      case "vega": return <GreekCell key={k} g={r.pe_greeks} field="vega" />;
      case "pop": return <PopCell key={k} g={r.pe_greeks} />;
      default: return null;
    }
  };

  return (
    <div className="space-y-3">
      {isModel && (
        <div className="card p-3.5" style={{ borderColor: "color-mix(in srgb, var(--accent) 35%, var(--line))" }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-active !text-[9.5px]">Model chain · not an exchange quote</span>
            <span className="muted text-[11px]">
              BSM engine around live spot · IV = INDIA VIX · OI left blank, never fabricated
            </span>
          </div>
          <p className="muted text-[11.5px] leading-relaxed mt-2">{chain.model_note}</p>
        </div>
      )}

      {/* summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="card p-3">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Underlying</div>
          <div className="knum text-[18px] font-black mt-1">{inr(spot)}</div>
          <div className="muted text-[10px] mt-0.5">{chain.underlying}</div>
        </div>
        {isModel ? (
          <>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">ATM strike</div>
              <div className="knum text-[18px] font-black mt-1">{atm != null ? inr(atm) : "—"}</div>
              <div className="muted text-[10px] mt-0.5">nearest strike to spot</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">ATM straddle</div>
              <div className="knum text-[18px] font-black mt-1">
                {atmStraddle != null ? inr(atmStraddle) : "—"}
              </div>
              <div className="muted text-[10px] mt-0.5">call + put premium at ATM</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Model IV" tip={TIPS.iv} />
              </div>
              <div className="knum text-[18px] font-black mt-1">
                {modelIv != null ? `${modelIv.toFixed(2)}%` : "—"}
              </div>
              <div className="muted text-[10px] mt-0.5">INDIA VIX used as the input</div>
            </div>
          </>
        ) : (
          <>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Put/Call OI" tip={TIPS.pcr} />
              </div>
              <div className="knum text-[18px] font-black mt-1">
                {envNum(chain.pcr) != null ? Number(envNum(chain.pcr)).toFixed(3) : "—"}
              </div>
              <div className="muted text-[10px] mt-0.5">
                {envNum(chain.pcr) != null ? "live open interest" : "not on free feed"}
              </div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Max OI support</div>
              <div className="knum text-[18px] font-black mt-1">
                <Unavailable env={chain.max_oi_support} what="support strike" />
              </div>
              <div className="muted text-[10px] mt-0.5">highest put OI below spot</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Max OI resistance</div>
              <div className="knum text-[18px] font-black mt-1">
                <Unavailable env={chain.max_oi_resistance} what="resistance strike" />
              </div>
              <div className="muted text-[10px] mt-0.5">highest call OI above spot</div>
            </div>
          </>
        )}
      </div>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {(chain.expiries || []).slice(0, 6).map((e) => (
            <button key={e} onClick={() => setExp(e)}
                    aria-pressed={activeExp === e}
                    className={`rounded-md px-2.5 py-1.5 text-[11.5px] font-semibold transition-colors ${activeExp === e ? "" : "muted hover:text-[var(--ink)]"}`}
                    style={activeExp === e
                      ? { background: "var(--accent)", color: "#041018" }
                      : { border: "1px solid var(--line)" }}>
              {e}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="muted text-[10.5px]">
            {visible.length} of {rows.length} strikes · ATM {atm != null ? inr(atm) : "—"}
          </span>
          <button onClick={() => setShowAll((v) => !v)}
                  className={`chip !text-[10px] ${showAll ? "chip-active" : ""}`}>
            {showAll ? "Show ATM ±10" : "Show All Strikes"}
          </button>
          <details className="relative">
            <summary className="chip !text-[10px] cursor-pointer list-none [&::-webkit-details-marker]:hidden">
              ⚙️ Filter Columns ▾
            </summary>
            <div className="absolute right-0 z-30 mt-1 w-[230px] rounded-lg p-3 space-y-2 text-[11.5px]"
                 style={{ background: "var(--surface)", border: "1px solid var(--line)", boxShadow: "0 10px 28px rgba(0,0,0,.18)" }}>
              {([
                ["chgOi", "Change in OI (ΔOI)"],
                ["iv", "Market Fear (IV %)"],
                ["pop", "Win Chance (POP %)"],
                ["greeks", "Option Greeks (Delta, Gamma, Theta, Vega)"],
              ] as const).map(([key, label]) => (
                <label key={key} className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" checked={cols[key]}
                         onChange={(e) => setCols((prev) => ({ ...prev, [key]: e.target.checked }))}
                         className="mt-0.5" />
                  <span>{label}</span>
                </label>
              ))}
              <div className="flex flex-wrap gap-1.5 pt-2" style={{ borderTop: "1px solid var(--line)" }}>
                <button onClick={() => setCols({ chgOi: true, iv: true, pop: true, greeks: true })}
                        className="chip !text-[9.5px]">Show All Columns</button>
                <button onClick={() => setCols({ chgOi: false, iv: false, pop: false, greeks: false })}
                        className={`chip !text-[9.5px] ${!anyExtra ? "chip-active" : ""}`}>
                  Simple View (Default)
                </button>
              </div>
            </div>
          </details>
        </div>
      </div>

      {/* chain table — 540px scroll window, auto-centred on ATM */}
      <div className="swipe-cue">‹ swipe the chain to see every Greek, OI and IV column ›</div>
      <div className="card overflow-hidden">
        <div ref={scrollRef} className="scroll-x scroll-x-tall">
          <table className="w-full border-collapse" style={{ minWidth: anyExtra ? 1480 : 720 }}>
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                <th colSpan={callCols.length} className="sticky top-0 z-20 px-3 py-1.5 text-center text-[10px] font-black uppercase tracking-[0.14em]"
                    style={{ background: "var(--surface-2)", borderRight: "1px solid var(--line)", color: "var(--up)" }}>
                  CALLS (TEZI)
                </th>
                <th className="sticky top-0 z-20 px-3 py-1.5 text-center text-[10px] font-black uppercase tracking-[0.14em]"
                    style={{ background: "var(--surface-2)", borderLeft: "1px solid var(--line)", borderRight: "1px solid var(--line)" }}>
                  STRIKE PRICE
                </th>
                <th colSpan={putCols.length} className="sticky top-0 z-20 px-3 py-1.5 text-center text-[10px] font-black uppercase tracking-[0.14em]"
                    style={{ background: "var(--surface-2)", borderLeft: "1px solid var(--line)", color: "var(--down)" }}>
                  PUTS (MANDI)
                </th>
              </tr>
              <tr style={{ background: "var(--surface-2)", borderTop: "1px solid var(--line)" }}>
                {callCols.map((h) => (
                  <th key={`c-${h}`} className="sticky top-[27px] z-20 table-head text-right px-2 py-1.5 whitespace-nowrap"
                      style={{ background: "var(--surface-2)" }}>
                    {h === "ltp" ? "Call Price ₹" : HEAD[h]}
                  </th>
                ))}
                <th className="sticky top-[27px] z-20 table-head text-center px-3 py-1.5 whitespace-nowrap"
                    style={{ background: "var(--surface-2)", borderLeft: "1px solid var(--line)", borderRight: "1px solid var(--line)" }}>
                  Strike / DTE
                </th>
                {putCols.map((h) => (
                  <th key={`p-${h}`} className="sticky top-[27px] z-20 table-head text-right px-2 py-1.5 whitespace-nowrap"
                      style={{ background: "var(--surface-2)" }}>
                    {h === "ltp" ? "Put Price ₹" : HEAD[h]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const isAtm = r.strike === atm;
                return (
                  <tr key={r.strike} ref={isAtm ? atmRef : undefined}
                      className="table-row"
                      style={isAtm
                        ? { background: "color-mix(in srgb, var(--accent) 9%, transparent)" }
                        : undefined}>
                    {callCols.map((k) => callCell(k, r))}

                    <td className={`px-3 py-1.5 text-center align-middle ${isAtm ? "accent" : ""}`}
                        style={{ borderLeft: "1px solid var(--line)", borderRight: "1px solid var(--line)",
                                 background: isAtm ? "color-mix(in srgb, var(--accent) 10%, transparent)" : undefined }}>
                      <div className="knum text-[12.5px] font-black">{r.strike.toLocaleString("en-IN")}</div>
                      <div className="muted text-[9.5px] knum">{r.dte != null ? `${r.dte.toFixed(1)}d` : "—"}</div>
                      {isAtm && <div className="chip chip-active !text-[7.5px] !py-0 !px-1 mt-0.5">ATM</div>}
                    </td>

                    {putCols.map((k) => putCell(k, r))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="px-3.5 py-2.5 muted text-[10.5px] leading-relaxed flex flex-wrap gap-x-4 gap-y-1"
             style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
          <span>{chain.greeks_note}</span>
          <span className="opacity-40">·</span>
          <span>Daily Time Melting Loss (Theta) is per lot per day; Fear Premium (Vega) is per 1 vol point.</span>
          <span className="opacity-40">·</span>
          <span>Click any LTP to load it into the replay calculator.</span>
          {!isModel && (
            <>
              <span className="opacity-40">·</span>
              <span>OI and volume are the exchange's own numbers; Greeks and POP are model outputs.</span>
            </>
          )}
        </div>
      </div>

      {/* ------------------------- replay calculator ------------------------- */}
      <div className="card p-4">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div>
            <h3 className="text-[14px] font-extrabold">Option time &amp; theta replay</h3>
            <p className="muted text-[11.5px] mt-0.5 leading-relaxed max-w-2xl">
              Project an option position forward to a chosen time or spot move. The model separates
              delta and gamma gains from theta decay and IV changes, then deducts statutory F&amp;O charges.
            </p>
          </div>
          <span className="chip !text-[9.5px]">Black-Scholes · ₹20 brokerage per order</span>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-3">
          <div className="space-y-2.5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <label className="block">
                <Lbl label="Bet Type (Call / Put)" tip={TIPS.bet} />
                <select value={rType} onChange={(e) => setRType(e.target.value as "CE" | "PE")}
                        className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px]"
                        style={{ color: "var(--ink)" }}>
                  <option value="CE">Call (Tezi / Upside)</option>
                  <option value="PE">Put (Mandi / Downside)</option>
                </select>
              </label>
              <label className="block">
                <Lbl label="Target Deal Price (Strike ₹)" tip={TIPS.strike} />
                <input value={rStrike} onChange={(e) => setRStrike(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <Lbl label="How Many Lots" tip={TIPS.lots} />
                <input value={rLots} onChange={(e) => setRLots(e.target.value)}
                       inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <Lbl label="Lot Size (units per lot)" tip={TIPS.lotSize} />
                <input value={rLotSize} onChange={(e) => setRLotSize(e.target.value)}
                       inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <label className="block">
                <Lbl label="Premium You Paid (₹)" tip={TIPS.premium} />
                <input value={rEntry} onChange={(e) => setREntry(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <Lbl label="Entry Time (IST)" tip={TIPS.entryTime} />
                <input type="time" value={rEntryTime} onChange={(e) => setREntryTime(e.target.value)}
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <Lbl label="Expected Market Move %" tip={TIPS.move} />
                <input value={rMove} onChange={(e) => setRMove(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>

            <div>
              <Lbl label="How Long to Hold" tip={TIPS.horizon} />
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {[
                  ["+10m", "+10m"], ["+30m", "+30m"], ["+1h", "+1h"],
                  ["15:15", "15:15 close"], ["next-open", "Next 09:15"], ["expiry", "Till expiry"],
                ].map(([v, label]) => (
                  <button key={v} onClick={() => setRHorizon(v)}
                          className={`chip !text-[10px] ${rHorizon === v ? "chip-active" : ""}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <Lbl label="Fear / Speed Change (IV points)" tip={TIPS.ivShift} />
                <input value={rIvShift} onChange={(e) => setRIvShift(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <div className="flex items-end">
                <button onClick={() => runReplay()} disabled={replayBusy}
                        className="btn-primary w-full justify-center !py-2 !text-[12px]">
                  {replayBusy ? "Projecting…" : "Show My Profit / Loss"}
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 muted text-[10.5px]">
              <span className="chip !text-[9px]">Spot {inr(spot)}</span>
              <span className="chip !text-[9px]">IV {modelIv != null ? `${modelIv.toFixed(1)}%` : "—"}</span>
              <span className="chip !text-[9px]">DTE {dte != null ? `${dte.toFixed(1)}d` : "—"}</span>
              <span className="chip !text-[9px]">Expiry {activeExp || "—"}</span>
            </div>
            {replayErr && <p className="text-[11.5px] text-down font-semibold">{replayErr}</p>}
          </div>

          <div className="rounded-lg p-3.5" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
            {!replay && !replayErr && (
              <p className="muted text-[12px]">Load a strike from the chain and press Project.</p>
            )}
            {replay && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Expected Option Price</div>
                    <div className="knum text-[17px] font-black mt-0.5">{inr(replay.exit?.premium)}</div>
                    <div className="muted text-[9.5px] mt-0.5">
                      from {inr(replay.entry?.premium)} · spot {inr(replay.exit?.spot)}
                    </div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Money You Put In</div>
                    <div className="knum text-[17px] font-black mt-0.5">{inr(replay.investment)}</div>
                    <div className="muted text-[9.5px] mt-0.5">
                      {replay.qty} units = {replay.lots} lot{replay.lots > 1 ? "s" : ""} × {replay.lot_size}
                    </div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Profit Before Charges</div>
                    <div className={`knum text-[17px] font-black mt-0.5 ${(replay.gross_pnl ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                      {inr(replay.gross_pnl)}
                    </div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Final Profit / Loss</div>
                    <div className={`knum text-[17px] font-black mt-0.5 ${(replay.net_pnl ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                      {inr(replay.net_pnl)}
                    </div>
                    <div className={`muted text-[9.5px] mt-0.5 ${(replay.net_pnl_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                      {pct(replay.net_pnl_pct)} on investment
                    </div>
                  </div>
                </div>

                <div className="rounded-md overflow-hidden" style={{ border: "1px solid var(--line)", background: "var(--surface)" }}>
                  <div className="px-2.5 py-1.5 muted text-[9px] font-bold uppercase tracking-wider"
                       style={{ background: "var(--surface-2)" }}>
                    P&amp;L decomposition
                  </div>
                  {[
                    ["Price Speed Gain (Delta)", replay.decomposition?.delta_gain, "text-up"],
                    ["Speed Change Gain (Gamma)", replay.decomposition?.gamma_gain, "text-up"],
                    ["Time Melting Loss (Theta)", replay.decomposition?.theta_loss, "text-down"],
                    ["Fear Gain (Vega)", replay.decomposition?.vega_gain, "text-up"],
                    ["Other / Rounding", replay.decomposition?.residual, ""],
                  ].map(([label, value, tone]: any) => (
                    <div key={label} className="flex items-center justify-between px-2.5 py-1.5 text-[11px] table-row">
                      <span className="muted">{label}</span>
                      <span className={`knum font-semibold ${tone}`}>
                        {inr(value)}
                        <span className="muted text-[9.5px] ml-1">
                          ({replay.investment ? ((Number(value) / replay.investment) * 100).toFixed(1) : "0.0"}%)
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between px-2.5 py-1.5 text-[11px]"
                       style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
                    <span className="muted">Total charges</span>
                    <span className="knum font-semibold text-down">{inr(replay.charges?.total)}</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-[10px] muted">
                  <span>Δ {num(replay.greeks_at_entry?.delta, 3)}</span>
                  <span>Γ {num(replay.greeks_at_entry?.gamma, 4)}</span>
                  <span>Θ {inr(replay.greeks_at_entry?.theta_per_day)}/day</span>
                  <span>ν {num(replay.greeks_at_entry?.vega, 2)}</span>
                  <span>POP {num(replay.greeks_at_entry?.pop_pct, 1)}%</span>
                  <span>{replay.horizon}</span>
                </div>

                <p className="muted text-[10px] leading-relaxed">{replay.note}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* greek legend */}
      <div className="card p-3.5">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {([
            { label: "Price Speed (Delta)", tip: TIPS.delta, sub: "premium change per ₹1 spot move" },
            { label: "Speed Change (Gamma)", tip: TIPS.gamma, sub: "change in delta per ₹1 move" },
            { label: "Daily Time Melting Loss (Theta)", tip: TIPS.theta, sub: "₹ lost per lot per day" },
            { label: "Fear Premium (Vega)", tip: TIPS.vega, sub: "₹ change per 1 vol point" },
          ] as { label: string; tip?: Tip; sub: string }[]).map((row) => (
            <div key={row.label}>
              <div className="text-[11.5px] font-bold" style={{ color: "var(--ink)" }}>
                {row.tip
                  ? <MetricTip label={row.label} tip={row.tip}>{row.label}</MetricTip>
                  : row.label}
              </div>
              <p className="muted text-[10.5px] mt-0.5 leading-relaxed">{row.sub}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
