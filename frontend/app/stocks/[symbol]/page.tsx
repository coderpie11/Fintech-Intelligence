"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { bigCrude, fmtDate, inr, pct } from "@/lib/format";
import { isMarketOpenIST } from "@/lib/market";
import {
  ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid,
} from "@/components/PageKit";
import MetricTip, { type Tip } from "@/components/MetricTip";
import LineChart, { type ChartHoverPoint } from "@/components/LineChart";
import Tabs from "@/components/Tabs";
import FnoTab from "@/components/FnoTab";
import StockFinancials from "@/components/stocks/StockFinancials";
import HealthScorecard from "@/components/stocks/HealthScorecard";
import StockCalculators from "@/components/stocks/StockCalculators";
import StockPeerDrawer from "@/components/stocks/StockPeerDrawer";
import WatchlistButton from "@/components/WatchlistButton";

const TIPS: Record<string, Tip> = {
  pe: {
    meaning: "How many rupees you pay for every ₹1 the company earns in a year. P/E 20 means ₹20 paid for ₹1 of yearly profit.",
    formula: "P/E = Share price ÷ profit per share (EPS)",
    example: "A ₹1,000 share earning ₹50 a year has a P/E of 1,000 ÷ 50 = 20.",
  },
  pb: {
    meaning: "What you pay compared with the company's own accounting net worth. Best for banks and businesses with many assets.",
    formula: "P/B = Share price ÷ net worth per share",
    example: "A ₹500 share with ₹250 net worth is 500 ÷ 250 = 2.0× book.",
  },
  dy: {
    meaning: "The cash dividend you get each year as a percent of the share price. It is like rent on your shares.",
    formula: "Dividend yield = Yearly dividend ÷ price × 100",
    example: "₹20 dividend on a ₹1,000 share = 20 ÷ 1,000 × 100 = 2%.",
  },
  roe: {
    meaning: "Profit made on the owners' money. 15%+ for many years is healthy, but heavy borrowing can make it look better than it is.",
    formula: "ROE = Yearly profit ÷ owners' money × 100",
    example: "₹100 profit on ₹1,000 of owners' money = 10% ROE.",
  },
  de: {
    meaning: "How much the company has borrowed compared with its own money. Lower usually means a safer balance sheet.",
    formula: "Debt to equity = Total debt ÷ owners' money",
    example: "₹400 borrowed against ₹1,000 of own money = 0.40×.",
  },
  cagr: {
    meaning: "The steady yearly growth rate that takes the start price to today's price. It makes long periods easy to compare.",
    formula: "CAGR = (End ÷ Start) to the power of (1 ÷ years) − 1",
    example: "₹1,000 growing to ₹1,610 over 5 years is about 10% a year.",
  },
  vol: {
    meaning: "How bumpy the price is day to day, shown as a yearly number. It measures the size of the ride, not the direction.",
    formula: "Yearly volatility ≈ size of daily ups and downs scaled to a year",
    example: "A 28% stock shakes about twice as much as a 14% index.",
  },
  mdd: {
    meaning: "The worst fall from a high point to a low point. It tells you how bad it felt, not what you earned.",
    formula: "Max fall = worst drop from a running high",
    example: "A −45% fall means a buyer at the top was once down 45%.",
  },
};

function envNum<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}

function RangeBar({ last, low, high }: { last?: number | null; low?: number | null; high?: number | null }) {
  if (last == null || low == null || high == null || high <= low) {
    return <div className="h-1.5 rounded-full" style={{ background: "var(--line)" }} />;
  }
  const p = Math.max(0, Math.min(100, ((last - low) / (high - low)) * 100));
  return (
    <div className="relative h-1.5 rounded-full" style={{ background: "var(--line)" }}>
      <div className="absolute inset-y-0 left-0 rounded-full"
           style={{ width: `${p}%`, background: "var(--accent)", opacity: 0.45 }} />
      <div className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full"
           style={{ left: `calc(${p}% - 5px)`, background: "var(--accent)",
                    boxShadow: "0 0 0 2px var(--surface)" }} />
    </div>
  );
}

const PERIODS = [
  { key: "1d", label: "1 day", simple: true },
  { key: "1w", label: "1 week", simple: true },
  { key: "1m", label: "1 month", simple: true },
  { key: "3m", label: "3 months", simple: true },
  { key: "6m", label: "6 months", simple: true },
  { key: "1y", label: "1 year", simple: true },
  { key: "3y", label: "3Y CAGR", simple: false },
  { key: "5y", label: "5Y CAGR", simple: false },
];

export default function StockDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const sym = (symbol || "").toUpperCase();
  const [d, setD] = useState<any>(null);
  const [intraday, setIntraday] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState("overview");
  const [drawer, setDrawer] = useState(false);
  const [scrub, setScrub] = useState<ChartHoverPoint | null>(null);

  const openFno = () => {
    setTab("fno");
    setTimeout(() => {
      document.getElementById("fno-section-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  };

  useEffect(() => {
    let live = true;
    setD(null);
    setErr(null);
    setScrub(null);

    const load = (initial: boolean) => {
      Promise.allSettled([
        getJSON(`/stocks/${sym}`),
        getJSON(`/stocks/${sym}/intraday`),
      ]).then(([det, intra]) => {
        if (!live) return;
        if (det.status === "fulfilled") {
          setD(det.value);
          setErr(null);
        } else if (initial) {
          setErr(String((det.reason as any)?.message || det.reason));
        }
        if (intra.status === "fulfilled") setIntraday(intra.value);
        else if (initial) setIntraday(null);
      });
    };

    load(true);
    // Live tick while the cash market is open. The backend reconciles against
    // the latest 5-minute candle and caches for 15 seconds, so this is cheap.
    const id = window.setInterval(() => {
      if (isMarketOpenIST()) load(false);
    }, 15_000);
    return () => { live = false; window.clearInterval(id); };
  }, [sym]);

  const intradayPoints = useMemo(
    () => (intraday?.points || []).map((p: any) => ({
      date: p.date, close: p.c, open: p.o, high: p.h, low: p.l,
      time: p.time, datetime: p.datetime, volume: p.v,
    })),
    [intraday],
  );

  if (err) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
        <ErrorBox message={err} stage="equities" />
        <Link href="/stocks" className="btn-secondary mt-4">← Back to equities</Link>
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

  const last = envNum(d.last);
  const chg = envNum(d.changepct);
  const liveChange = envNum(d.change)
    ?? (last != null && envNum(d.prev_close) != null ? last - (envNum(d.prev_close) as number) : null);
  const shownLast = scrub?.price ?? last;
  const shownChange = scrub ? scrub.change : liveChange;
  const shownPct = scrub ? scrub.pctChange : chg;
  const up = (shownChange ?? 0) >= 0;
  const yrLow = d.year_range?.value?.[0] ?? null;
  const yrHigh = d.year_range?.value?.[1] ?? null;
  const dayLow = d.day_range?.value?.[0] ?? null;
  const dayHigh = d.day_range?.value?.[1] ?? null;
  const val = d.fundamentals?.valuation || {};
  const prof = d.fundamentals?.profitability || {};
  const solv = d.fundamentals?.solvency || {};
  const risk = d.risk || {};
  const dcf = d.dcf_defaults || {};

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "financials", label: "Financials" },
    { key: "health", label: "Health scorecard" },
    { key: "calculators", label: "Calculators" },
    { key: "peers", label: `Peers (${(d.peers || []).length})` },
    { key: "fno", label: "F&O" },
    { key: "sources", label: "Data & sources" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/stocks" className="hover:underline">Equities</Link>
        <span className="opacity-40">/</span>
        <span style={{ color: "var(--ink)" }} className="font-semibold">{d.symbol}</span>
      </div>

      <PageHeader
        eyebrow={`${d.sector || "Equity"}${d.industry ? ` · ${d.industry}` : ""} · ${d.symbol}`}
        title={d.name}
        sub={d.about}
        right={
          <>
            <WatchlistButton symbol={d.symbol} kind="EQUITY" href={`/stocks/${d.symbol}`} />
            <button onClick={() => setDrawer(true)} className="btn-primary !py-2 !text-[12.5px]">
              + Compare with Peers
            </button>
            <RefreshButton stage="equity_fundamentals" label="Refresh research" />
          </>
        }
      />

      {/* price + chart */}
      <div className="grid lg:grid-cols-[1fr_330px] gap-3 mb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
            <div>
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">
                {scrub ? "Chart point" : "Live price"}
                <span className="ml-2 normal-case tracking-normal opacity-80">
                  {scrub ? "· move cursor off chart to return live" : ""}
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3 mt-1">
                <span className="knum text-[34px] font-black leading-none">{inr(shownLast)}</span>
                <span className={`knum text-[15px] font-bold ${up ? "text-up" : "text-down"}`}>
                  {shownChange != null && shownChange > 0 ? "+" : ""}{inr(shownChange)}
                  <span className="ml-2">{pct(shownPct)}</span>
                </span>
                <span className={`chip !text-[9px] ${scrub ? "chip-warn" : "chip-live"}`}>
                  {scrub ? "SCRUBBING" : "LIVE"}
                </span>
              </div>
              <div className="muted text-[11px] mt-1.5">
                {scrub
                  ? `${scrub.label} · chart candle`
                  : (d.live_time || (d.asof ? `Session ${fmtDate(d.asof)}` : "Latest available session"))}
                {" · "}indicative
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {d.financial_sector && <span className="chip chip-warn !text-[9.5px]">Financial sector</span>}
              {d.indices?.value?.slice?.(0, 3).map((i: string) => (
                <span key={i} className="chip !text-[9.5px]">{i}</span>
              ))}
            </div>
          </div>

          <LineChart
            points={(d.history || []).map((h: any) => ({
              date: h.date, close: h.close, open: h.open, high: h.high, low: h.low,
            }))}
            intradayPoints={intradayPoints}
            intradaySource={intraday?.source}
            prevClose={envNum(d.prev_close)}
            onHoverPointChange={setScrub}
            height={330}
            defaultRange="1D"
            title={`${d.symbol} · price history`}
          />
        </div>

        <aside className="card p-4 sm:p-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {([
              ["Open", d.open?.value],
              ["Prev close", d.prev_close?.value],
              ["Day high", d.day_range?.value?.[1]],
              ["Day low", d.day_range?.value?.[0]],
            ] as [string, any][]).map(([label, v]) => (
              <div key={label} className="rounded-md px-2.5 py-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                <div className="knum text-[13px] font-bold mt-0.5">{v != null ? inr(v) : "—"}</div>
              </div>
            ))}
          </div>

          <div>
            <div className="flex items-center justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">52-week range</span>
              <span className="knum">
                {last != null && yrLow != null && yrHigh != null
                  ? `${Math.max(0, Math.min(100, ((last - yrLow) / (yrHigh - yrLow || 1)) * 100)).toFixed(0)}%`
                  : "—"}
              </span>
            </div>
            <RangeBar last={last} low={yrLow} high={yrHigh} />
            <div className="flex justify-between knum muted text-[10px] mt-1.5">
              <span>{inr(yrLow)}</span><span>{inr(yrHigh)}</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">Day range</span>
              <span className="knum">{dayLow != null && dayHigh != null ? `${inr(dayLow)} – ${inr(dayHigh)}` : "—"}</span>
            </div>
            <RangeBar last={last} low={dayLow} high={dayHigh} />
          </div>

          <div className="grid grid-cols-2 gap-2">
            {([
              ["P/E", val.pe, (v: number) => v.toFixed(2), TIPS.pe],
              ["P/B", val.pb, (v: number) => v.toFixed(2), TIPS.pb],
              ["Div yield", val.dividend_yield, (v: number) => `${v.toFixed(2)}%`, TIPS.dy],
              ["Market cap", val.market_cap, bigCrude, undefined],
            ] as [string, any, (v: number) => string, Tip | undefined][]).map(([label, env, fmt, tip]) => (
              <div key={label} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
                </div>
                <div className="knum text-[13px] font-bold mt-0.5">
                  {envNum(env) != null ? fmt(envNum(env) as number) : <span className="muted text-[10.5px]">Source pending</span>}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">
                <MetricTip label="ROE" tip={TIPS.roe} />
              </div>
              <div className="knum text-[13px] font-bold mt-0.5">
                {envNum(prof.roe) != null ? `${envNum(prof.roe)?.toFixed(2)}%` : "—"}
              </div>
            </div>
            <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">
                <MetricTip label="Debt / equity" tip={TIPS.de} />
              </div>
              <div className="knum text-[13px] font-bold mt-0.5">
                {envNum(solv.debt_equity) != null ? `${envNum(solv.debt_equity)?.toFixed(2)}×` : "—"}
              </div>
            </div>
          </div>
        </aside>
      </div>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={(k) => (k === "fno" ? openFno() : setTab(k))} />
      </div>

      {tab === "overview" && (
        <div className="space-y-6">
          <section>
            <SectionTitle title="Performance ladder"
                        sub="Simple returns up to one year; 3-year and 5-year figures are compound annual growth rates." />
            <StatGrid items={PERIODS.map((p) => ({
              label: p.label,
              env: d.returns?.[p.key],
              fmt: (v: number) => pct(v),
              tip: {
                meaning: p.simple
                  ? `Simple price return over the ${p.label} window.`
                  : `Compound annual growth over roughly ${p.key === "3y" ? "756" : "1,260"} sessions.`,
                formula: p.simple ? "Return = (End ÷ Start − 1) × 100" : "CAGR = (End ÷ Start)^(1 ÷ Years) − 1",
              },
            }))} />
          </section>

          <section>
            <SectionTitle title="Risk statistics"
                        sub="Computed by the platform from the stored daily closes." />
            <StatGrid items={[
              { label: "Volatility 1Y", env: risk.vol_1y, fmt: (v: number) => `${v}%`, tip: TIPS.vol },
              { label: "Volatility 3Y", env: risk.vol_3y, fmt: (v: number) => `${v}%`, tip: TIPS.vol },
              { label: "Max drawdown 1Y", env: risk.max_dd_1y, fmt: (v: number) => pct(v), tip: TIPS.mdd },
              { label: "Max drawdown 5Y", env: risk.max_dd_5y, fmt: (v: number) => pct(v), tip: TIPS.mdd },
              { label: "Beta", env: risk.beta, fmt: (v: number) => v.toFixed(2) },
              { label: "52W high", env: risk.high_52w, fmt: inr },
              { label: "52W low", env: risk.low_52w, fmt: inr },
              { label: "History depth", env: { value: d.history_points, status: "REPORTED", note: "" },
                fmt: (v: number) => `${v.toLocaleString("en-IN")} sessions` },
            ]} />
          </section>

          <section className="grid md:grid-cols-2 gap-3">
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-2">Valuation &amp; profitability</div>
              <StatGrid items={[
                { label: "P/E", env: val.pe, fmt: (v: number) => v.toFixed(2), tip: TIPS.pe },
                { label: "P/B", env: val.pb, fmt: (v: number) => v.toFixed(2), tip: TIPS.pb },
                { label: "PEG", env: val.peg, fmt: (v: number) => v.toFixed(2) },
                { label: "EV / EBITDA", env: val.ev_ebitda, fmt: (v: number) => v.toFixed(2) },
                { label: "Dividend yield", env: val.dividend_yield, fmt: (v: number) => `${v.toFixed(2)}%`, tip: TIPS.dy },
                { label: "Earnings yield", env: val.earnings_yield, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "ROE", env: prof.roe, fmt: (v: number) => `${v.toFixed(2)}%`, tip: TIPS.roe },
                { label: "ROCE", env: prof.roce, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "ROIC", env: prof.roic, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Operating margin", env: prof.operating_margin, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Net margin", env: prof.net_margin, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Graham number", env: val.graham_number, fmt: inr },
                { label: "Book value / share", env: val.book_value_per_share, fmt: inr },
              ]} />
            </div>
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-2">Solvency, efficiency &amp; growth</div>
              <StatGrid items={[
                { label: "Debt / equity", env: solv.debt_equity, fmt: (v: number) => `${v.toFixed(2)}×`, tip: TIPS.de },
                { label: "Interest coverage", env: solv.interest_coverage, fmt: (v: number) => `${v.toFixed(2)}×` },
                { label: "Net debt / EBITDA", env: solv.net_debt_ebitda, fmt: (v: number) => `${v.toFixed(2)}×` },
                { label: "Current ratio", env: solv.current_ratio, fmt: (v: number) => v.toFixed(2) },
                { label: "Asset turnover", env: d.fundamentals?.efficiency?.asset_turnover, fmt: (v: number) => `${v.toFixed(2)}×` },
                { label: "Receivable days", env: d.fundamentals?.efficiency?.receivable_days, fmt: (v: number) => `${v.toFixed(0)} d` },
                { label: "FCF yield", env: d.fundamentals?.efficiency?.fcf_yield, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Revenue growth 1Y", env: d.fundamentals?.growth?.revenue_growth_1y, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Revenue CAGR 3Y", env: d.fundamentals?.growth?.revenue_cagr_3y, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Profit growth 1Y", env: d.fundamentals?.growth?.profit_growth_1y, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "Profit CAGR 3Y", env: d.fundamentals?.growth?.profit_cagr_3y, fmt: (v: number) => `${v.toFixed(2)}%` },
                { label: "EPS", env: val.eps, fmt: inr },
              ]} />
            </div>
          </section>
        </div>
      )}

      {tab === "financials" && (
        <section>
          <SectionTitle title="Five-year financial statements"
                        sub="Annual and quarterly statements with common-size and consolidated/standalone toggles." />
          <StockFinancials statements={d.statements} shareholding={d.shareholding} />
        </section>
      )}

      {tab === "health" && (
        <section>
          <SectionTitle title="Three-pillar health scorecard"
                        sub="Piotroski F, Altman Z and Beneish M, plus the three-step DuPont decomposition — all computed from reported statements." />
          <HealthScorecard health={d.health} />
        </section>
      )}

      {tab === "calculators" && (
        <section>
          <SectionTitle title="Valuation and return calculators"
                        sub="DCF, reverse DCF, SIP, lumpsum and relative value — the platform does all the maths locally." />
          <StockCalculators
            symbol={d.symbol}
            defaults={dcf}
            price={val.price ?? last}
            eps={envNum(val.eps)}
            bvps={envNum(val.book_value_per_share)}
            onOpenPeers={() => setDrawer(true)}
          />
        </section>
      )}

      {tab === "peers" && (
        <section>
          <SectionTitle title="Same-sector peers"
                        sub="Leader badges mark the highest ROE, lowest P/E, lowest D/E and highest 5-year CAGR in this set."
                        right={<button onClick={() => setDrawer(true)} className="btn-secondary !py-1.5 !text-[11.5px]">Open peer drawer</button>} />
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-4 py-2.5">Company</th>
                    <th className="table-head text-right px-3 py-2.5">Last</th>
                    <th className="table-head text-right px-3 py-2.5">Day</th>
                    <th className="table-head text-right px-3 py-2.5">P/E</th>
                    <th className="table-head text-right px-3 py-2.5">P/B</th>
                    <th className="table-head text-right px-3 py-2.5">ROE</th>
                    <th className="table-head text-right px-3 py-2.5">ROCE</th>
                    <th className="table-head text-right px-3 py-2.5">D/E</th>
                    <th className="table-head text-right px-4 py-2.5">5Y CAGR</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.peers || []).map((p: any) => (
                    <tr key={p.symbol} className="table-row"
                        style={p.is_subject ? { background: "color-mix(in srgb, var(--accent) 7%, transparent)" } : undefined}>
                      <td className="px-4 py-2.5">
                        <Link href={p.href} className="text-[12.5px] font-bold hover:underline">{p.symbol}</Link>
                        <div className="muted text-[10px] truncate max-w-[220px]">{p.name}</div>
                        {(p.badges || []).map((b: string) => (
                          <span key={b} className="chip chip-live !text-[8px] !py-0.5 mt-1 mr-1">{b}</span>
                        ))}
                      </td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{inr(p.last)}</td>
                      <td className={`px-3 py-2.5 text-right knum text-[12px] font-bold ${(p.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(p.changepct)}</td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{p.pe ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{p.pb ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{p.roe != null ? `${p.roe.toFixed(2)}%` : "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{p.roce != null ? `${p.roce.toFixed(2)}%` : "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[12px]">{p.debt_equity != null ? p.debt_equity.toFixed(2) : "—"}</td>
                      <td className={`px-4 py-2.5 text-right knum text-[12px] font-semibold ${(p.cagr_5y || 0) >= 0 ? "text-up" : "text-down"}`}>{p.cagr_5y != null ? pct(p.cagr_5y) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {tab === "fno" && (
        <div id="fno-section-anchor" className="scroll-mt-24">
        <section>
          <SectionTitle title={`${d.symbol} derivatives`}
                        sub="Live NSE option chain with platform-computed Greeks, probability of profit and the time/theta replay calculator." />
          <FnoTab underlying={d.symbol} />
        </section>
        </div>
      )}

      {tab === "sources" && (
        <section className="grid md:grid-cols-2 gap-3">
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2.5">Where these numbers come from</div>
            <dl className="space-y-2 text-[12px]">
              {[
                ["NSE symbol", d.symbol],
                ["Sector", d.sector || "—"],
                ["Price basis", "Platform quote snapshot (indicative)"],
                ["Statement basis", "Reported company statements"],
                ["Shareholding basis", "Quarterly shareholding pattern"],
                ["History depth", `${Number(d.history_points || 0).toLocaleString("en-IN")} daily sessions`],
                ["Data stamp", d.asof ? fmtDate(d.asof) : "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-4">
                  <dt className="muted">{k}</dt>
                  <dd className="text-right font-semibold" style={{ color: "var(--ink)" }}>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="card p-4 space-y-3">
            <div className="text-[13px] font-bold">Honesty notes</div>
            {(d.source_notes || []).map((n: string) => (
              <p key={n} className="muted text-[12px] leading-relaxed">{n}</p>
            ))}
            {d.data_error && (
              <p className="text-[11.5px]" style={{ color: "var(--warn)" }}>
                Research fetch note: {d.data_error}
              </p>
            )}
          </div>
        </section>
      )}

      <StockPeerDrawer symbol={d.symbol} open={drawer} onClose={() => setDrawer(false)}
                       initialPeers={d.peers || []} />
    </div>
  );
}
