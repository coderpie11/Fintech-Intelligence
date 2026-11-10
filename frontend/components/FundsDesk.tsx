"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import {
  ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid,
} from "@/components/PageKit";
import { EnvVal } from "@/components/EnvVal";
import MetricTip, { type Tip } from "@/components/MetricTip";
import LineChart from "@/components/LineChart";
import Tabs from "@/components/Tabs";
import FundPeerDrawer from "@/components/funds/FundPeerDrawer";

type FundRow = {
  code: string;
  name: string;
  amc: string;
  category?: string;
  broad_category?: string;
  plan?: string;
  option?: string;
  nav_latest: Env;
  nav_date?: string;
  perf_1m: Env;
  perf_3m: Env;
  perf_6m: Env;
  perf_1y: Env;
  perf_3y: Env;
  perf_5y: Env;
  volatility: Env;
  max_drawdown: Env;
  sharpe: Env;
  ter: Env;
  aum_crore: Env;
  href: string;
};

const TIPS: Record<string, Tip> = {
  cagr: {
    meaning:
      "Compound Annual Growth Rate: the smooth yearly rate that takes the starting NAV to today's NAV. Used for 3Y and 5Y because a simple total return over long periods flatters the number.",
    formula: "CAGR = (End NAV ÷ Start NAV)^(1 ÷ Years) − 1",
    example: "₹100 → ₹161 over 5 years is a 10% CAGR.",
  },
  sharpe: {
    meaning:
      "Sharpe Ratio: return earned per unit of total risk, above the risk-free rate. Higher is better; above 1 is generally strong for an equity fund.",
    formula: "Sharpe = (Fund return − Risk-free return) ÷ Standard deviation",
    example: "A 14% return with 12% volatility and a 6.5% risk-free rate gives about 0.63.",
  },
  sortino: {
    meaning:
      "Sortino Ratio: like Sharpe, but it penalises only downside volatility. It is fairer for funds with sharp upside jumps.",
    formula: "Sortino = (Fund return − Risk-free return) ÷ Downside deviation",
    example: "A fund with fewer losing months usually scores a higher Sortino than Sharpe.",
  },
  alpha: {
    meaning:
      "Alpha: the return left after subtracting what the benchmark and the fund's beta would explain. Positive alpha means the manager added value.",
    formula: "Alpha = Fund return − [Risk-free + Beta × (Benchmark − Risk-free)]",
    example: "A 1.8% alpha means the fund beat its risk-adjusted benchmark by 1.8 points a year.",
  },
  beta: {
    meaning:
      "Beta: how much the fund moves when the benchmark moves 1%. Above 1 is more aggressive; below 1 is defensive.",
    formula: "Beta = Covariance(fund, benchmark) ÷ Variance(benchmark)",
    example: "Beta 0.8 means a 10% index fall is expected to cost the fund about 8%.",
  },
  vol: {
    meaning:
      "Annualised Volatility: how widely NAV returns swing, scaled to a year. It is the standard total-risk measure.",
    formula: "σ = standard deviation of periodic returns × √periods per year",
    example: "A 16% volatility fund is roughly twice as swingy as an 8% debt fund.",
  },
  mdd: {
    meaning:
      "Maximum Drawdown: the worst peak-to-trough fall in the window. It answers how bad it got, not what you earned.",
    formula: "Max DD = min over time of (NAV ÷ Running peak − 1)",
    example: "A −32% drawdown means a buyer at the peak was once down 32%.",
  },
  ter: {
    meaning:
      "Total Expense Ratio: the annual fee the AMC deducts from the scheme's assets. It is already reflected in NAV, so it lowers your return directly.",
    formula: "TER = Annual scheme expenses ÷ Average daily net assets",
    example: "A 0.65% Direct-plan TER costs ₹650 a year on ₹1 lakh.",
  },
  exit: {
    meaning:
      "Exit Load: a fee charged if you redeem before the stated holding period. It is deducted from the redemption proceeds.",
    formula: "Exit load = Redeemed amount × load % (within the load window)",
    example: "A 1% load on ₹1 lakh redeemed in month 6 costs ₹1,000.",
  },
  aum: {
    meaning:
      "Assets Under Management: the market value of all money the scheme manages. Very small AUM can mean viability risk; very large AUM can make a strategy harder to run.",
    formula: "AUM = Σ market value of every holding + cash",
    example: "₹45,000 crore is a large, mature equity scheme in India.",
  },
};

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

function PctCell({ env, strong = false, active = false }: { env?: Env; strong?: boolean; active?: boolean }) {
  const v = envNum(env);
  return (
    <span className={`knum text-[11.5px] ${strong || active ? "font-bold" : ""} ${v == null ? "muted" : v >= 0 ? "text-up" : "text-down"}`}>
      {v != null ? pct(v) : "—"}
    </span>
  );
}

function NumCell({ env, fmt, suffix = "" }: { env?: Env; fmt?: (v: number) => string; suffix?: string }) {
  const v = envNum(env);
  if (v == null) return <span className="muted text-[11px]">—</span>;
  return <span className="knum text-[11.5px]">{fmt ? fmt(v) : v.toFixed(2)}{suffix}</span>;
}

/* ------------------------------------------------------------------ list */

const FUND_TYPES = [
  "All Mutual Funds", "Large Cap", "Mid Cap", "Small Cap",
  "Flexi & Multi Cap", "Nifty & Sensex Index", "International / Nasdaq / US",
  "Gold & Silver Funds", "ELSS Tax Saver", "Hybrid & Balanced", "Debt & Liquid",
];

const PERIODS = [
  { key: "1m", label: "1 Month (1M)" },
  { key: "3m", label: "3 Months (3M)" },
  { key: "6m", label: "6 Months (6M)" },
  { key: "1y", label: "1 Year (1Y)" },
  { key: "3y", label: "3 Years (3Y CAGR)" },
  { key: "5y", label: "5 Years (5Y CAGR)" },
] as const;

type PeriodKey = (typeof PERIODS)[number]["key"];

function fundBucket(f: FundRow): string {
  const hay = `${f.category || ""} ${f.broad_category || ""} ${f.name || ""}`.toLowerCase();
  if (/silver|gold/.test(hay)) return "Gold & Silver Funds";
  if (/elss|tax saver/.test(hay)) return "ELSS Tax Saver";
  if (/nasdaq|s&p 500|us equity|international|overseas|global/.test(hay)) return "International / Nasdaq / US";
  if (/index|nifty|sensex/.test(hay)) return "Nifty & Sensex Index";
  if (/small/.test(hay)) return "Small Cap";
  if (/mid/.test(hay)) return "Mid Cap";
  if (/large cap|large & mid|large and mid/.test(hay)) return "Large Cap";
  if (/flexi|multi cap|multicap|focused|value fund|contra|dividend yield/.test(hay)) return "Flexi & Multi Cap";
  if (/hybrid|balanced|arbitrage|multi asset|equity savings|conservative|aggressive/.test(hay)) return "Hybrid & Balanced";
  if (/debt|liquid|gilt|bond|overnight|money market|credit risk|corporate bond/.test(hay)) return "Debt & Liquid";
  return "Flexi & Multi Cap";
}

function FundTable({ funds, period }: { funds: FundRow[]; period: PeriodKey }) {
  return (
    <div className="card overflow-hidden">
      <div className="scroll-x">
        <table className="w-full min-w-[1500px] border-collapse">
          <thead>
            <tr style={{ background: "var(--surface-2)" }}>
              <th className="table-head text-left px-3 py-2.5">Scheme</th>
              <th className="table-head text-right px-2.5 py-2.5">NAV</th>
              {PERIODS.map((p) => (
                <th key={p.key} className="table-head text-right px-2.5 py-2.5"
                    style={period === p.key ? { color: "var(--accent)" } : undefined}>
                  {p.key === "3y" || p.key === "5y" ? (
                    <MetricTip label={`${p.key.toUpperCase()} CAGR`} tip={TIPS.cagr}>
                      {p.key.toUpperCase()} CAGR
                    </MetricTip>
                  ) : p.key.toUpperCase()}
                </th>
              ))}
              <th className="table-head text-right px-2.5 py-2.5">
                <MetricTip label="Volatility" tip={TIPS.vol}>Volatility</MetricTip>
              </th>
              <th className="table-head text-right px-2.5 py-2.5">
                <MetricTip label="Sharpe" tip={TIPS.sharpe}>Sharpe</MetricTip>
              </th>
              <th className="table-head text-right px-2.5 py-2.5">
                <MetricTip label="Max DD" tip={TIPS.mdd}>Max DD</MetricTip>
              </th>
              <th className="table-head text-right px-2.5 py-2.5">
                <MetricTip label="TER" tip={TIPS.ter}>TER</MetricTip>
              </th>
              <th className="table-head text-right px-3 py-2.5">
                <MetricTip label="AUM" tip={TIPS.aum}>AUM</MetricTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {funds.map((f) => (
              <tr key={f.code} className="table-row">
                <td className="px-3 py-2.5 min-w-[310px]">
                  <Link href={f.href} className="text-[12.5px] font-bold hover:underline">
                    {f.name.length > 78 ? f.name.slice(0, 78) + "…" : f.name}
                  </Link>
                  <div className="muted text-[10.5px] mt-0.5 flex flex-wrap gap-x-2">
                    <span>{f.amc}</span>
                    <span className="opacity-40">·</span>
                    <span>{f.category || "Unclassified"}</span>
                    <span className="opacity-40">·</span>
                    <span>{f.plan || "Direct"} · {f.option || "Growth"}</span>
                  </div>
                </td>
                <td className="px-2.5 py-2.5 text-right">
                  <div className="knum text-[12px] font-semibold">{envNum(f.nav_latest) != null ? inr(envNum(f.nav_latest)) : "—"}</div>
                  <div className="muted text-[9.5px]">{f.nav_date ? fmtDate(f.nav_date) : "—"}</div>
                </td>
                {PERIODS.map((p) => {
                  const env = p.key === "1m" ? f.perf_1m
                    : p.key === "3m" ? f.perf_3m
                    : p.key === "6m" ? f.perf_6m
                    : p.key === "1y" ? f.perf_1y
                    : p.key === "3y" ? f.perf_3y : f.perf_5y;
                  return (
                    <td key={p.key} className="px-2.5 py-2.5 text-right"
                        style={period === p.key ? { background: "color-mix(in srgb, var(--accent) 7%, transparent)" } : undefined}>
                      <PctCell env={env}
                               strong={p.key === "3y" || p.key === "5y"}
                               active={period === p.key} />
                    </td>
                  );
                })}
                <td className="px-2.5 py-2.5 text-right"><NumCell env={f.volatility} suffix="%" /></td>
                <td className="px-2.5 py-2.5 text-right"><NumCell env={f.sharpe} /></td>
                <td className="px-2.5 py-2.5 text-right"><PctCell env={f.max_drawdown} /></td>
                <td className="px-2.5 py-2.5 text-right"><NumCell env={f.ter} suffix="%" /></td>
                <td className="px-3 py-2.5 text-right">
                  {envNum(f.aum_crore) != null
                    ? <span className="knum text-[11px]">₹{Number(envNum(f.aum_crore)).toLocaleString("en-IN")} Cr</span>
                    : <span className="muted text-[11px]">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FundsDesk({ kind }: { kind: "mf" | "etf" }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [type, setType] = useState("All Mutual Funds");
  const [period, setPeriod] = useState<PeriodKey>("1y");
  const [order, setOrder] = useState<"desc" | "asc">("desc");

  // Deep links such as /mutual-funds?q=nestec (global search) pre-fill the
  // filter. Read from the URL on mount to keep the route static.
  useEffect(() => {
    const qp = new URLSearchParams(window.location.search).get("q");
    if (qp) setQ(qp);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(q), 180);
    return () => window.clearTimeout(id);
  }, [q]);

  useEffect(() => {
    // Guard against out-of-order responses: an all-scheme fuzzy search can take
    // longer than the default browse query, which would otherwise overwrite the
    // filtered table with unfiltered rows.
    let live = true;
    setErr(null);
    const p = new URLSearchParams({ kind, limit: "500", page: "1" });
    if (debouncedQ.trim()) p.set("q", debouncedQ.trim());
    getJSON(`/mutual-funds?${p}`)
      .then((r) => { if (live) setData(r); })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    return () => { live = false; };
  }, [kind, debouncedQ]);

  const rows = useMemo(() => {
    const list: FundRow[] = data?.funds || [];
    const needle = q.trim().toLowerCase();
    // A server-side search is already fuzzy/phonetic ("nestec" → Nasdaq), so
    // keep its relevance order instead of dropping those rows on a literal
    // substring test. The local needle only refines the default browse list.
    const serverSearch = debouncedQ.trim().length > 0;
    const filtered = list.filter((f) => {
      if (type !== "All Mutual Funds" && fundBucket(f) !== type) return false;
      if (serverSearch || !needle) return true;
      return f.name.toLowerCase().includes(needle)
        || (f.amc || "").toLowerCase().includes(needle)
        || (f.category || "").toLowerCase().includes(needle)
        || f.code.toLowerCase().includes(needle);
    });
    return [...filtered].sort((a, b) => {
      const av = envNum(a[`perf_${period}` as keyof FundRow] as Env);
      const bv = envNum(b[`perf_${period}` as keyof FundRow] as Env);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return order === "desc" ? bv - av : av - bv;
    });
  }, [data, q, debouncedQ, type, period, order]);

  const latest = useMemo(() => {
    const dates = (data?.funds || []).map((f: FundRow) => f.nav_date).filter(Boolean).sort();
    return dates.length ? dates[dates.length - 1] : null;
  }, [data]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6">
      <PageHeader
        eyebrow={kind === "etf" ? "ETF" : "Mutual funds"}
        title={kind === "etf" ? "ETF Desk" : "Mutual Funds Desk"}
        sub={
          kind === "etf"
            ? "Exchange-traded funds with live quotes and true 1/3/5-year stats computed from real NAV series."
            : "Active Direct-Growth schemes across large, mid, small, flexi, index, international, gold/silver, ELSS, hybrid and debt categories. Filter by type, pick a return period and sort instantly."
        }
        right={<RefreshButton stage="funds" />}
      />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="surface rounded-lg px-3 py-1.5 flex-1 min-w-[220px] max-w-md">
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Search any of 38,000+ schemes or AMC…"
                 className="w-full bg-transparent text-[12.5px] outline-none"
                 style={{ color: "var(--ink)" }} />
        </div>
        <label className="flex items-center gap-1.5">
          <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}
                  className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
            {FUND_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Return period</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value as PeriodKey)}
                  className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
            {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Sort by return</span>
          <select value={order} onChange={(e) => setOrder(e.target.value as "desc" | "asc")}
                  className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
            <option value="desc">Highest Return First (Max → Min ↓)</option>
            <option value="asc">Lowest Return First (Min → Max ↑)</option>
          </select>
        </label>
      </div>

      {err && <ErrorBox message={err} stage="funds" />}
      {!data && !err && <Skeleton rows={10} />}

      {data && rows.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div className="muted text-[11.5px]">
              {rows.length} of {data.count} schemes shown
              {latest ? ` · latest NAV ${fmtDate(latest)}` : ""}
              {debouncedQ ? ` · searched all ${data.count} matching schemes` : ""}
            </div>
          </div>
          <FundTable funds={rows} period={period} />
          <p className="muted text-[10.5px] mt-2 leading-relaxed">
            Returns are computed from the stored NAV series; 3Y and 5Y are
            compound annual growth rates. TER and AUM appear when the scheme record
            has been enriched — a blank means the field was not disclosed, not zero.
          </p>
        </>
      )}

      {data && rows.length === 0 && (
        <div className="card p-5">
          <div className="text-[14px] font-bold">No scheme matches these filters</div>
          <p className="muted text-[12.5px] mt-1">
            Clear the search or type filter. The desk lists active schemes with a
            current NAV series; typing searches all 38,000+ AMFI codes.
          </p>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- detail */

type Det = any;

function HoldingBadge({ badge }: { badge?: string | null }) {
  if (!badge) return null;
  const official = /official/i.test(badge);
  return (
    <span className={`chip !text-[8px] !py-0.5 ${official ? "chip-live" : "chip-warn"}`}>
      {official ? "Official AMC Reason" : badge}
    </span>
  );
}

function ChurnBucket({
  title, items, tone,
}: {
  title: string;
  items: any[];
  tone: "up" | "down" | "accent" | "warn";
}) {
  const toneClass = tone === "up" ? "text-up" : tone === "down" ? "text-down"
    : tone === "warn" ? "text-warn" : "accent";
  return (
    <div className="card p-3.5">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[12px] font-bold">{title}</div>
        <span className="chip !text-[9px]">{items.length}</span>
      </div>
      {items.length === 0 && <p className="muted text-[11px]">None this period.</p>}
      <div className="space-y-1.5 max-h-[210px] overflow-y-auto pr-1">
        {items.map((h: any) => (
          <div key={h.name} className="flex items-start justify-between gap-2 text-[11px]">
            <div className="min-w-0">
              <div className="font-semibold truncate" title={h.name}>{h.name}</div>
              <div className="muted text-[10px] truncate">{h.reason}</div>
            </div>
            <div className="text-right shrink-0">
              <div className={`knum font-bold ${toneClass}`}>{h.change}</div>
              <div className="muted text-[9.5px]">{Number(h.weight).toFixed(2)}%</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FundCalculators({
  code, defaults, ter, expected, exitLoad, onOpenPeers,
}: {
  code: string;
  defaults?: any;
  ter?: number | null;
  expected?: number | null;
  exitLoad?: number | null;
  onOpenPeers: () => void;
}) {
  const [tab, setTab] = useState<"backtest" | "vs-etf" | "swp" | "ltcg">("backtest");

  const [mode, setMode] = useState<"sip" | "lumpsum">("sip");
  const [monthly, setMonthly] = useState(String(defaults?.monthly ?? 5000));
  const [amount, setAmount] = useState(String(defaults?.amount ?? 100000));
  const [years, setYears] = useState(String(defaults?.years ?? 5));
  const [bt, setBt] = useState<any>(null);
  const [btErr, setBtErr] = useState<string | null>(null);
  const [btBusy, setBtBusy] = useState(false);

  const [etfAmount, setEtfAmount] = useState(String(defaults?.amount ?? 100000));
  const [etfYears, setEtfYears] = useState(String(defaults?.years ?? 5));
  const [mfTer, setMfTer] = useState(ter != null ? String(ter) : "");
  const [etfTer, setEtfTer] = useState("0.20");
  const [gross, setGross] = useState(expected != null ? String(expected.toFixed(2)) : "");
  const [vs, setVs] = useState<any>(null);
  const [vsErr, setVsErr] = useState<string | null>(null);
  const [vsBusy, setVsBusy] = useState(false);

  const [corpus, setCorpus] = useState("1000000");
  const [withdrawal, setWithdrawal] = useState("10000");
  const [swpReturn, setSwpReturn] = useState(expected != null ? String(expected.toFixed(2)) : "10");
  const [swp, setSwp] = useState<any>(null);
  const [swpErr, setSwpErr] = useState<string | null>(null);
  const [swpBusy, setSwpBusy] = useState(false);

  const [gain, setGain] = useState("250000");
  const [used, setUsed] = useState("0");
  const [ltcg, setLtcg] = useState<any>(null);
  const [ltcgErr, setLtcgErr] = useState<string | null>(null);
  const [ltcgBusy, setLtcgBusy] = useState(false);

  const runBt = async () => {
    setBtBusy(true); setBtErr(null); setBt(null);
    try {
      const r = await postJSON(`/mutual-funds/${code}/backtest`, {
        mode, monthly: Number(monthly) || 0, amount: Number(amount) || 0,
        years: Number(years) || 1, exit_load_pct: exitLoad || 0,
      });
      setBt(r);
    } catch (e: any) {
      setBtErr(String(e.message || e).slice(0, 200));
    } finally { setBtBusy(false); }
  };

  const runVs = async () => {
    setVsBusy(true); setVsErr(null); setVs(null);
    try {
      const r = await postJSON(`/mutual-funds/${code}/vs-etf`, {
        amount: Number(etfAmount) || 0, years: Number(etfYears) || 1,
        etf_ter_pct: Number(etfTer) || 0,
        mf_ter_pct: mfTer === "" ? undefined : Number(mfTer),
        expected_return_pct: gross === "" ? undefined : Number(gross),
      });
      setVs(r);
    } catch (e: any) {
      setVsErr(String(e.message || e).slice(0, 200));
    } finally { setVsBusy(false); }
  };

  const runSwp = async () => {
    setSwpBusy(true); setSwpErr(null); setSwp(null);
    try {
      const r = await postJSON(`/mutual-funds/${code}/swp`, {
        corpus: Number(corpus) || 0,
        monthly_withdrawal: Number(withdrawal) || 0,
        annual_return_pct: Number(swpReturn) || 0,
      });
      setSwp(r);
    } catch (e: any) {
      setSwpErr(String(e.message || e).slice(0, 200));
    } finally { setSwpBusy(false); }
  };

  const runLtcg = async () => {
    setLtcgBusy(true); setLtcgErr(null); setLtcg(null);
    try {
      const r = await postJSON(`/mutual-funds/${code}/ltcg`, {
        gain: Number(gain) || 0, used_exemption: Number(used) || 0,
      });
      setLtcg(r);
    } catch (e: any) {
      setLtcgErr(String(e.message || e).slice(0, 200));
    } finally { setLtcgBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {[
            ["backtest", "SIP / Lumpsum backtest"],
            ["vs-etf", "Fund vs ETF"],
            ["swp", "SWP"],
            ["ltcg", "LTCG harvest"],
          ].map(([k, label]) => (
            <button key={k} onClick={() => setTab(k as any)}
                    className={`chip !text-[11px] ${tab === k ? "chip-active" : ""}`}>
              {label}
            </button>
          ))}
        </div>
        <button onClick={onOpenPeers} className="btn-secondary !py-1.5 !text-[11.5px]">
          + Peer fee-drag drawer
        </button>
      </div>

      {tab === "backtest" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Backtest this scheme's actual NAVs</div>
            <p className="muted text-[11px] leading-relaxed">
              SIP buys the first available NAV each month; lumpsum buys once at the
              start. Exit load and statutory fund charges are deducted at redemption.
            </p>
            <div className="flex gap-1.5">
              {(["sip", "lumpsum"] as const).map((m) => (
                <button key={m} onClick={() => setMode(m)}
                        className={`chip !text-[10.5px] ${mode === m ? "chip-active" : ""}`}>
                  {m === "sip" ? "Monthly SIP" : "One-time lumpsum"}
                </button>
              ))}
            </div>
            <div className="grid sm:grid-cols-3 gap-2">
              {mode === "sip" ? (
                <label className="block">
                  <span className="muted text-[10px] font-bold uppercase tracking-wider">Monthly ₹</span>
                  <input value={monthly} onChange={(e) => setMonthly(e.target.value)} inputMode="numeric"
                         className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                         style={{ color: "var(--ink)" }} />
                </label>
              ) : (
                <label className="block">
                  <span className="muted text-[10px] font-bold uppercase tracking-wider">Amount ₹</span>
                  <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="numeric"
                         className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                         style={{ color: "var(--ink)" }} />
                </label>
              )}
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Years</span>
                <input value={years} onChange={(e) => setYears(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <div className="flex items-end">
                <button onClick={runBt} disabled={btBusy}
                        className="btn-primary w-full justify-center !py-2 !text-[12px]">
                  {btBusy ? "Running…" : "Run backtest"}
                </button>
              </div>
            </div>
            {btErr && <p className="text-[11.5px] text-down font-semibold">{btErr}</p>}
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Backtest result</div>
            {!bt && !btErr && <p className="muted text-[12px]">Run the actual NAV path.</p>}
            {bt && (
              <div className="space-y-1.5 text-[12px]">
                <div className="flex justify-between"><span className="muted">Window</span><span className="knum">{fmtDate(bt.start)} → {fmtDate(bt.end)}</span></div>
                {bt.months && <div className="flex justify-between"><span className="muted">Instalments</span><span className="knum">{bt.months}</span></div>}
                <div className="flex justify-between"><span className="muted">Invested</span><span className="knum">{inr(bt.invested)}</span></div>
                <div className="flex justify-between"><span className="muted">Value</span><span className="knum font-bold accent">{inr(bt.value)}</span></div>
                <div className="flex justify-between"><span className="muted">Gain</span><span className={`knum font-semibold ${bt.gain >= 0 ? "text-up" : "text-down"}`}>{inr(bt.gain)}</span></div>
                <div className="flex justify-between"><span className="muted">Absolute return</span><span className="knum">{pct(bt.return_pct)}</span></div>
                <div className="flex justify-between"><span className="muted">XIRR</span><span className="knum font-bold">{pct(bt.xirr_pct)}</span></div>
                {bt.charges && (
                  <>
                    <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                      <span className="muted">Exit load + charges</span>
                      <span className="knum text-down">−{inr(bt.charges.total)}</span>
                    </div>
                    <div className="flex justify-between"><span className="muted font-semibold">Net value</span><span className="knum font-black">{inr(bt.net_value)}</span></div>
                  </>
                )}
                <p className="muted text-[10.5px] leading-relaxed mt-2">{bt.note}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "vs-etf" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Mutual fund vs equivalent ETF</div>
            <p className="muted text-[11px] leading-relaxed">
              Same gross portfolio return for both wrappers. The ETF saves the TER gap
              but pays delivery brokerage, STT, DP and a modelled impact cost.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Amount ₹</span>
                <input value={etfAmount} onChange={(e) => setEtfAmount(e.target.value)} inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Years</span>
                <input value={etfYears} onChange={(e) => setEtfYears(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">MF TER %</span>
                <input value={mfTer} onChange={(e) => setMfTer(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">ETF TER %</span>
                <input value={etfTer} onChange={(e) => setEtfTer(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block sm:col-span-2">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Expected gross return % p.a.</span>
                <input value={gross} onChange={(e) => setGross(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>
            <button onClick={runVs} disabled={vsBusy}
                    className="btn-primary w-full justify-center !py-2 !text-[12px]">
              {vsBusy ? "Calculating…" : "Compare true cost"}
            </button>
            {vsErr && <p className="text-[11.5px] text-down font-semibold">{vsErr}</p>}
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Wealth outcome</div>
            {!vs && !vsErr && <p className="muted text-[12px]">Run the comparison.</p>}
            {vs && (
              <div className="space-y-1.5 text-[12px]">
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">Mutual fund</div>
                    <div className="knum text-[16px] font-black mt-0.5">{inr(vs.mf_value)}</div>
                    <div className="muted text-[9.5px]">net {pct(vs.mf_net_return_pct)} · TER {vs.mf_ter_pct}%</div>
                  </div>
                  <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">ETF after charges</div>
                    <div className="knum text-[16px] font-black mt-0.5">{inr(vs.etf_value_after_charges)}</div>
                    <div className="muted text-[9.5px]">net {pct(vs.etf_net_return_pct)} · TER {vs.etf_ter_pct}%</div>
                  </div>
                </div>
                <div className="flex justify-between"><span className="muted">Gross return assumed</span><span className="knum">{pct(vs.expected_gross_return_pct)}</span></div>
                <div className="flex justify-between"><span className="muted">Equivalent ETF</span><span className="knum font-semibold">{vs.equivalent_etf?.symbol || "—"}</span></div>
                <div className="flex justify-between"><span className="muted">MF exit load</span><span className="knum text-down">-{inr(vs.mf_exit_load)}</span></div>
                <div className="flex justify-between"><span className="muted">ETF brokerage + taxes</span><span className="knum text-down">-{inr(vs.etf_charges?.total)}</span></div>
                <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                  <span className="muted font-semibold">ETF advantage</span>
                  <span className={`knum font-black ${vs.advantage_etf >= 0 ? "text-up" : "text-down"}`}>{inr(vs.advantage_etf)}</span>
                </div>
                <p className="muted text-[10.5px] leading-relaxed mt-2">{vs.note}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "swp" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">Systematic withdrawal plan</div>
            <p className="muted text-[11px] leading-relaxed">
              A constant-return SWP projection. Real NAV paths vary; equity SWPs can
              deplete faster during a drawdown.
            </p>
            <div className="grid sm:grid-cols-3 gap-2">
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Corpus ₹</span>
                <input value={corpus} onChange={(e) => setCorpus(e.target.value)} inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Monthly ₹</span>
                <input value={withdrawal} onChange={(e) => setWithdrawal(e.target.value)} inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Return % p.a.</span>
                <input value={swpReturn} onChange={(e) => setSwpReturn(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>
            <button onClick={runSwp} disabled={swpBusy}
                    className="btn-primary w-full justify-center !py-2 !text-[12px]">
              {swpBusy ? "Calculating…" : "Project withdrawals"}
            </button>
            {swpErr && <p className="text-[11.5px] text-down font-semibold">{swpErr}</p>}
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">SWP outcome</div>
            {!swp && !swpErr && <p className="muted text-[12px]">Run the projection.</p>}
            {swp && !swp.error && (
              <div className="space-y-1.5 text-[12px]">
                <div className="flex justify-between"><span className="muted">Monthly withdrawal</span><span className="knum">{inr(Number(withdrawal))}</span></div>
                <div className="flex justify-between"><span className="muted">Annual withdrawal</span><span className="knum">{inr(swp.annual_withdrawal)}</span></div>
                <div className="flex justify-between"><span className="muted">Withdrawal rate</span><span className="knum">{pct(swp.withdrawal_rate_pct)}</span></div>
                <div className="flex justify-between"><span className="muted">Corpus lasts</span><span className="knum font-bold">{swp.perpetual ? "Perpetual at this return" : `${swp.years_lasted} years`}</span></div>
                <div className="flex justify-between"><span className="muted">Balance left</span><span className="knum">{inr(swp.balance_left)}</span></div>
                {swp.estimated_ltcg_tax != null && (
                  <>
                    <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                      <span className="muted">Estimated LTCG tax</span><span className="knum text-down">{inr(swp.estimated_ltcg_tax)}</span>
                    </div>
                    <div className="flex justify-between"><span className="muted">Exemption left</span><span className="knum">{inr(swp.ltcg_exemption_left)}</span></div>
                    <div className="flex justify-between"><span className="muted">Post-tax gain</span><span className="knum text-up">{inr(swp.estimated_post_tax_gain)}</span></div>
                    <div className="flex justify-between"><span className="muted">Post-tax monthly</span><span className="knum font-bold">{inr(swp.post_tax_annual_withdrawal)}</span></div>
                  </>
                )}
                <p className="muted text-[10.5px] leading-relaxed mt-2">{swp.note}</p>
              </div>
            )}
            {swp?.error && <p className="text-[11.5px] text-down font-semibold">{swp.error}</p>}
          </div>
        </div>
      )}

      {tab === "ltcg" && (
        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-4 space-y-2.5">
            <div className="text-[13px] font-bold">₹1.25 lakh LTCG harvesting</div>
            <p className="muted text-[11px] leading-relaxed">
              Equity mutual-fund long-term gains are taxed at 12.5% above the
              ₹1,25,000 annual exemption. Enter the unrealised gain and any exemption
              already used this financial year.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Unrealised gain ₹</span>
                <input value={gain} onChange={(e) => setGain(e.target.value)} inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[10px] font-bold uppercase tracking-wider">Exemption already used ₹</span>
                <input value={used} onChange={(e) => setUsed(e.target.value)} inputMode="numeric"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>
            <button onClick={runLtcg} disabled={ltcgBusy}
                    className="btn-primary w-full justify-center !py-2 !text-[12px]">
              {ltcgBusy ? "Calculating…" : "Compute harvest window"}
            </button>
            {ltcgErr && <p className="text-[11.5px] text-down font-semibold">{ltcgErr}</p>}
          </div>
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2">Tax outcome</div>
            {!ltcg && !ltcgErr && <p className="muted text-[12px]">Run the harvest calculation.</p>}
            {ltcg && (
              <div className="space-y-1.5 text-[12px]">
                <div className="flex justify-between"><span className="muted">Exemption left</span><span className="knum font-bold">{inr(ltcg.exemption_left)}</span></div>
                <div className="flex justify-between"><span className="muted">Taxable gain</span><span className="knum">{inr(ltcg.taxable_gain)}</span></div>
                <div className="flex justify-between"><span className="muted">Tax at 12.5%</span><span className="knum text-down">{inr(ltcg.tax)}</span></div>
                <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                  <span className="muted font-semibold">Post-tax gain</span>
                  <span className="knum font-black text-up">{inr(ltcg.post_tax_gain)}</span>
                </div>
                <div className="flex justify-between"><span className="muted">Exemption left</span><span className="knum">{inr(ltcg.exemption_left)}</span></div>
                <p className="muted text-[10.5px] leading-relaxed mt-2">
                  Harvesting up to the unused exemption resets your cost basis without
                  tax. This is a quantitative tax estimate, not personalised advice.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function FundDetail({ code }: { code: string }) {
  const [d, setD] = useState<Det | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState("overview");
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    let live = true;
    setD(null);
    setErr(null);
    getJSON(`/mutual-funds/${encodeURIComponent(code)}`)
      .then((r) => { if (live) setD(r); })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    return () => { live = false; };
  }, [code]);

  const navPoints = useMemo(
    () => (d?.navs || []).map((n: any) => ({ date: n.date, close: n.nav })),
    [d],
  );

  if (err) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
        <ErrorBox message={err} stage="funds" />
        <Link href="/mutual-funds" className="btn-secondary mt-4">← Back to mutual funds</Link>
      </div>
    );
  }

  if (!d) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8 space-y-3">
        <div className="skeleton h-16" />
        <Skeleton rows={7} />
      </div>
    );
  }

  if (d.available === false) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
        <PageHeader eyebrow={`Scheme ${code}`} title={d.name || code}
                    sub="This scheme code exists in the fund universe but no NAV series is available yet." />
        <div className="card p-5 muted text-[12.5px] leading-relaxed">
          No NAV history is available from the free source right now, so the desk will
          not invent a chart, return or risk number. Try Refresh, or open a scheme from
          the main list — those rows are guaranteed to have a live five-year series.
        </div>
        <Link href="/mutual-funds" className="btn-secondary mt-4">← Back to mutual funds</Link>
      </div>
    );
  }

  const returns = d.returns || {};
  const risk = d.risk || {};
  const fund = d.fund || {};
  const churn = d.churn || {};
  const nav = envNum(d.nav_latest);
  const ter = envNum(fund.ter);
  const aum = envNum(fund.aum_crore);
  const expected = envNum(returns["5y"]) ?? envNum(returns["3y"]);
  const holdings = d.holdings || [];

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "holdings", label: `Holdings & churn (${holdings.length})` },
    { key: "calculators", label: "Calculators" },
    { key: "peers", label: `Peers (${(d.peers || []).length})` },
    { key: "sources", label: "Data & sources" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/mutual-funds" className="hover:underline">Mutual funds</Link>
        <span className="opacity-40">/</span>
        <span style={{ color: "var(--ink)" }} className="font-semibold">{code}</span>
      </div>

      <PageHeader
        eyebrow={`${d.category || "Fund"} · ${d.plan || "Direct"} plan · ${d.option || "Growth"}`}
        title={d.name}
        sub={`${d.amc || ""}${d.sub_category ? ` · ${d.sub_category}` : ""} · NAV series since ${d.history_start ? fmtDate(d.history_start) : "—"}`}
        right={
          <>
            <button onClick={() => setDrawer(true)} className="btn-primary !py-2 !text-[12.5px]">
              + Compare with peers
            </button>
            <RefreshButton stage="funds" label="Refresh funds" />
          </>
        }
      />

      <div className="grid lg:grid-cols-[1fr_330px] gap-3 mb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
            <div>
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">Latest NAV</div>
              <div className="flex items-end gap-3 mt-1">
                <span className="knum text-[34px] font-black leading-none">{inr(nav)}</span>
                <span className={`knum text-[14px] font-bold ${(envNum(returns["1y"]) || 0) >= 0 ? "text-up" : "text-down"}`}>
                  1Y {pct(envNum(returns["1y"]))}
                </span>
              </div>
              <div className="muted text-[11px] mt-1.5">
                {d.nav_date ? `NAV dated ${fmtDate(d.nav_date)}` : "Latest available NAV"}
                {" · "}{Number(d.history_points || 0).toLocaleString("en-IN")} observations
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {ter != null && <span className="chip !text-[9.5px]">TER {ter.toFixed(2)}%</span>}
              {aum != null && <span className="chip !text-[9.5px]">AUM ₹{aum.toLocaleString("en-IN")} Cr</span>}
              {fund.modelled && <span className="chip chip-warn !text-[9px]">Benchmark model</span>}
              {fund.riskometer?.value && <span className="chip chip-warn !text-[9.5px]">{fund.riskometer.value}</span>}
            </div>
          </div>

          <LineChart points={navPoints} height={330} defaultRange="5Y"
                     title={`${d.name} · NAV history`} />
        </div>

        <aside className="card p-4 sm:p-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {[
              ["TER", fund.ter, (v: number) => `${v.toFixed(2)}%`, TIPS.ter],
              ["AUM", fund.aum_crore, (v: number) => `₹${v.toLocaleString("en-IN")} Cr`, TIPS.aum],
              ["Exit load", fund.exit_load_pct, (v: number) => `${v.toFixed(2)}%`, TIPS.exit],
              ["Riskometer", fund.riskometer, (v: string) => String(v), undefined],
            ].map(([label, env, fmt, tip]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
                </div>
                <div className="knum text-[12.5px] font-bold mt-0.5">
                  {envNum(env) != null
                    ? fmt(envNum(env))
                    : env?.value != null ? String(env.value) : <span className="muted text-[10px]">Not disclosed</span>}
                </div>
              </div>
            ))}
          </div>

          <div>
            <div className="flex justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">5-year CAGR</span>
              <span className={`knum font-bold ${(envNum(returns["5y"]) || 0) >= 0 ? "text-up" : "text-down"}`}>
                {pct(envNum(returns["5y"]))}
              </span>
            </div>
            <div className="relative h-2 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
              <div className="absolute inset-y-0 left-0 rounded-full"
                   style={{ width: `${Math.max(0, Math.min(100, ((envNum(returns["5y"]) || 0) + 10) / 40 * 100))}%`,
                            background: "linear-gradient(90deg,var(--accent-2),var(--accent))" }} />
            </div>
            <div className="flex justify-between muted text-[9.5px] mt-1">
              <span>−10%</span><span>30%</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {[
              ["Sharpe", risk.sharpe, (v: number) => v.toFixed(2), TIPS.sharpe],
              ["Sortino", risk.sortino, (v: number) => v.toFixed(2), TIPS.sortino],
              ["Alpha", risk.alpha, (v: number) => `${v.toFixed(2)}%`, TIPS.alpha],
              ["Beta", risk.beta, (v: number) => v.toFixed(2), TIPS.beta],
            ].map(([label, env, fmt, tip]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
                </div>
                <div className="knum text-[12.5px] font-bold mt-0.5">
                  {envNum(env) != null ? fmt(envNum(env)) : <span className="muted text-[10px]">—</span>}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={setTab} />
      </div>

      {tab === "overview" && (
        <div className="space-y-6">
          <section>
            <SectionTitle title="Returns ladder"
                        sub="1M to 1Y are simple NAV returns; 3Y and 5Y are compound annual growth rates." />
            <StatGrid items={[
              ["1M", returns["1m"]], ["3M", returns["3m"]], ["6M", returns["6m"]],
              ["1Y", returns["1y"]], ["3Y CAGR", returns["3y"]], ["5Y CAGR", returns["5y"]],
            ].map(([label, env]: any) => ({
              label,
              env,
              fmt: (v: number) => pct(v),
              tip: TIPS.cagr,
            }))} />
          </section>

          <section>
            <SectionTitle title="Risk statistics"
                        sub="Computed by the platform from this scheme's NAV series. Alpha and beta use NIFTY 50 for equity categories." />
            <StatGrid items={[
              { label: "Volatility", env: risk.volatility, fmt: (v: number) => `${v.toFixed(2)}%`, tip: TIPS.vol },
              { label: "Max drawdown", env: risk.max_drawdown, fmt: (v: number) => pct(v), tip: TIPS.mdd },
              { label: "Sharpe", env: risk.sharpe, fmt: (v: number) => v.toFixed(2), tip: TIPS.sharpe },
              { label: "Sortino", env: risk.sortino, fmt: (v: number) => v.toFixed(2), tip: TIPS.sortino },
              { label: "Alpha", env: risk.alpha, fmt: (v: number) => `${v.toFixed(2)}%`, tip: TIPS.alpha },
              { label: "Beta", env: risk.beta, fmt: (v: number) => v.toFixed(2), tip: TIPS.beta },
              { label: "Upside capture", env: risk.upside_capture, fmt: (v: number) => `${v.toFixed(1)}%` },
              { label: "Downside capture", env: risk.downside_capture, fmt: (v: number) => `${v.toFixed(1)}%` },
            ]} />
          </section>

          <section className="grid md:grid-cols-2 gap-3">
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-2">Scheme facts</div>
              <dl className="space-y-2 text-[12px]">
                {[
                  ["AMC", d.amc || "—"],
                  ["Category", d.category || "—"],
                  ["Plan / option", `${d.plan || "—"} / ${d.option || "—"}`],
                  ["Benchmark", fund.benchmark?.value || "—"],
                  ["Fund manager", fund.fund_manager?.value || "—"],
                  ["Launch date", fund.launch_date?.value || "—"],
                  ["Portfolio turnover", fund.portfolio_turnover_pct?.value != null ? `${Number(fund.portfolio_turnover_pct.value).toFixed(2)}%` : "—"],
                  ["Exit load", fund.exit_load?.value || "—"],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-start justify-between gap-4">
                    <dt className="muted">{k}</dt>
                    <dd className="text-right font-semibold max-w-[65%]" style={{ color: "var(--ink)" }}>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-2">Category context</div>
              <div className="grid grid-cols-3 gap-2 mb-3">
                {[
                  ["1Y avg", fund.category_avg?.["1y"]],
                  ["3Y avg", fund.category_avg?.["3y"]],
                  ["5Y avg", fund.category_avg?.["5y"]],
                ].map(([label, v]: any) => (
                  <div key={label} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                    <div className="knum text-[13px] font-bold mt-0.5">{v != null ? pct(Number(v)) : "—"}</div>
                  </div>
                ))}
              </div>
              <div className="space-y-1.5 text-[12px]">
                <div className="flex justify-between"><span className="muted">Rank 1Y</span><span className="knum">{fund.rank?.["1y"] ?? "—"}</span></div>
                <div className="flex justify-between"><span className="muted">Rank 3Y</span><span className="knum">{fund.rank?.["3y"] ?? "—"}</span></div>
                <div className="flex justify-between"><span className="muted">Rank 5Y</span><span className="knum">{fund.rank?.["5y"] ?? "—"}</span></div>
                <div className="flex justify-between"><span className="muted">History depth</span><span className="knum">{Number(d.history_points || 0).toLocaleString("en-IN")} NAVs</span></div>
              </div>
              {d.reported_risk?.source && (
                <p className="muted text-[10.5px] mt-3 leading-relaxed">
                  Reported risk stats are shown alongside the platform's own
                  calculations in the risk section.
                </p>
              )}
            </div>
          </section>
        </div>
      )}

      {tab === "holdings" && (
        <div className="space-y-4">
          <SectionTitle title="Portfolio holdings"
                      sub={`Disclosed portfolio${d.holdings_date ? ` as of ${fmtDate(d.holdings_date)}` : ""}. Weights are percentages of the scheme corpus.`} />
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
            {[
              ["Fresh additions", churn.additions || [], "accent"],
              ["Full exits", churn.exits || [], "down"],
              ["Stake increased", churn.increased || [], "up"],
              ["Stake trimmed", churn.trimmed || [], "warn"],
            ].map(([title, items, tone]: any) => (
              <ChurnBucket key={title} title={title} items={items} tone={tone} />
            ))}
          </div>
          <div className="card p-3 text-[11.5px] muted leading-relaxed">
            <strong style={{ color: "var(--ink)" }}>Churn status: {churn.status || "—"}.</strong>{" "}
            {churn.note || "No portfolio comparison is available yet."}
            {churn.previous_period && ` Compared ${fmtDate(churn.previous_period)} → ${fmtDate(churn.period)}.`}
          </div>

          <div className="card overflow-hidden">
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full min-w-[780px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="sticky top-0 table-head text-left px-3 py-2.5" style={{ background: "var(--surface-2)" }}>Holding</th>
                    <th className="sticky top-0 table-head text-left px-3 py-2.5" style={{ background: "var(--surface-2)" }}>Sector</th>
                    <th className="sticky top-0 table-head text-right px-3 py-2.5" style={{ background: "var(--surface-2)" }}>Weight</th>
                    <th className="sticky top-0 table-head text-right px-3 py-2.5" style={{ background: "var(--surface-2)" }}>Change</th>
                    <th className="sticky top-0 table-head text-left px-3 py-2.5" style={{ background: "var(--surface-2)" }}>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h: any, i: number) => (
                    <tr key={`${h.name}-${i}`} className="table-row">
                      <td className="px-3 py-2 text-[12px] font-semibold">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span>{h.name}</span>
                          <HoldingBadge badge={h.badge} />
                        </div>
                        <div className="muted text-[10px]">{h.instrument || ""}</div>
                      </td>
                      <td className="px-3 py-2 muted text-[11px]">{h.sector || "—"}</td>
                      <td className="px-3 py-2 text-right knum text-[12px] font-bold">{Number(h.weight).toFixed(2)}%</td>
                      <td className={`px-3 py-2 text-right knum text-[11px] ${h.change?.startsWith("-") ? "text-down" : h.change ? "text-up" : "muted"}`}>
                        {h.change || "—"}
                      </td>
                      <td className="px-3 py-2 muted text-[10.5px] max-w-[300px]">{h.reason || "No change versus the previous disclosure."}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-3 py-2 muted text-[10.5px]"
                 style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
              {holdings.length} disclosed positions.
              Badges are AI Verified unless the AMC itself published a rationale.
            </div>
          </div>
        </div>
      )}

      {tab === "calculators" && (
        <section>
          <SectionTitle title="Four-in-one calculator suite"
                      sub="Backtested SIP/lumpsum, fund-versus-ETF true cost, SWP and ₹1.25 lakh LTCG harvesting — plus the peer fee-drag drawer." />
          <FundCalculators
            code={d.code}
            defaults={d.calculator_defaults}
            ter={ter}
            expected={expected}
            exitLoad={envNum(fund.exit_load_pct)}
            onOpenPeers={() => setDrawer(true)}
          />
        </section>
      )}

      {tab === "peers" && (
        <section>
          <SectionTitle title="Same-category peers"
                      sub="Direct-Growth schemes in the same category, ranked by 3-year CAGR. Open the drawer for the fee-drag and alpha-wealth comparison."
                      right={<button onClick={() => setDrawer(true)} className="btn-secondary !py-1.5 !text-[11.5px]">Open peer drawer</button>} />
          <div className="card overflow-hidden">
            <div className="scroll-x">
              <table className="w-full min-w-[820px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-4 py-2.5">Scheme</th>
                    <th className="table-head text-left px-3 py-2.5">Category</th>
                    <th className="table-head text-right px-3 py-2.5">TER</th>
                    <th className="table-head text-right px-3 py-2.5">1Y</th>
                    <th className="table-head text-right px-3 py-2.5">3Y CAGR</th>
                    <th className="table-head text-right px-3 py-2.5">5Y CAGR</th>
                    <th className="table-head text-right px-4 py-2.5">AUM</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.peers || []).map((p: any) => (
                    <tr key={p.code} className="table-row">
                      <td className="px-4 py-2.5">
                        <Link href={p.href} className="text-[12.5px] font-bold hover:underline">
                          {p.name.length > 68 ? p.name.slice(0, 68) + "…" : p.name}
                        </Link>
                        <div className="muted text-[10px]">{p.amc} · {p.plan || "Direct"} · {p.option || "Growth"}</div>
                      </td>
                      <td className="px-3 py-2.5 muted text-[11.5px]">{p.category || "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[11.5px]">{p.ter != null ? `${Number(p.ter).toFixed(2)}%` : "—"}</td>
                      <td className={`px-3 py-2.5 text-right knum text-[11.5px] ${(p.perf_1y || 0) >= 0 ? "text-up" : "text-down"}`}>{p.perf_1y != null ? pct(p.perf_1y) : "—"}</td>
                      <td className={`px-3 py-2.5 text-right knum text-[11.5px] font-bold ${(p.perf_3y || 0) >= 0 ? "text-up" : "text-down"}`}>{p.perf_3y != null ? pct(p.perf_3y) : "—"}</td>
                      <td className={`px-3 py-2.5 text-right knum text-[11.5px] font-bold ${(p.perf_5y || 0) >= 0 ? "text-up" : "text-down"}`}>{p.perf_5y != null ? pct(p.perf_5y) : "—"}</td>
                      <td className="px-4 py-2.5 text-right knum text-[11.5px]">
                        {p.aum_crore != null ? `₹${Number(p.aum_crore).toLocaleString("en-IN")} Cr` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {tab === "sources" && (
        <section className="grid md:grid-cols-2 gap-3">
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2.5">Where these numbers come from</div>
            <dl className="space-y-2 text-[12px]">
              {[
                ["Scheme code", d.code],
                ["NAV basis", "Stored NAV history"],
                ["NAV depth", `${Number(d.history_points || 0).toLocaleString("en-IN")} observations from ${d.history_start ? fmtDate(d.history_start) : "—"}`],
                ["Fund facts basis", "Disclosed scheme record"],
                ["Holdings basis", d.holdings_date ? `Portfolio disclosure ${fmtDate(d.holdings_date)}` : "Disclosed scheme record"],
                ["Benchmark", d.benchmark_used || "—"],
                ["Risk engine", "Platform-computed from the stored NAV series"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-4">
                  <dt className="muted">{k}</dt>
                  <dd className="text-right font-semibold max-w-[62%]" style={{ color: "var(--ink)" }}>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="card p-4 space-y-3">
            <div className="text-[13px] font-bold">Honesty notes</div>
            {(d.source_notes || []).map((n: string) => (
              <p key={n} className="muted text-[12px] leading-relaxed">{n}</p>
            ))}
            {d.enrichment_error && (
              <p className="text-[11.5px]" style={{ color: "var(--warn)" }}>
                Enrichment note: {d.enrichment_error}
              </p>
            )}
            <p className="muted text-[11px] leading-relaxed">
              This desk is quantitative research, not a distribution or advisory
              service. Past NAV returns are not a forecast.
            </p>
          </div>
        </section>
      )}

      <FundPeerDrawer code={d.code} open={drawer} onClose={() => setDrawer(false)} />
    </div>
  );
}
