"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { bigCrude, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, Skeleton } from "@/components/PageKit";
import { EnvVal, PctVal } from "@/components/EnvVal";
import MetricTip from "@/components/MetricTip";

type Stock = {
  symbol: string; name: string; slug: string; sector?: string;
  last: Env; changepct: Env; pe: Env; pb: Env; market_cap: Env; href: string;
};

const SORTS = [
  ["mcap", "Biggest m-cap"], ["gainers", "Top gainers"], ["losers", "Top losers"],
  ["pe", "Lowest P/E"], ["symbol", "A–Z"],
] as const;

export default function StocksPage() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState("mcap");
  const [sector, setSector] = useState("");
  const [index, setIndex] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(60);

  // Deep links such as /stocks?q=PARAS (from the global search dropdown) must
  // pre-fill the filter. Read straight from the URL on mount so the page can
  // stay statically rendered without a Suspense boundary.
  useEffect(() => {
    const qp = new URLSearchParams(window.location.search).get("q");
    if (qp) setQ(qp);
  }, []);

  useEffect(() => {
    // Ignore a stale response: the deep-link filter (?q=) resolves after the
    // default browse request and both can be in flight at once.
    let live = true;
    setErr(null);
    const p = new URLSearchParams({ sort, limit: String(limit) });
    if (sector) p.set("sector", sector);
    if (index) p.set("index", index);
    if (q.trim()) p.set("q", q.trim());
    getJSON(`/stocks?${p}`)
      .then((r) => { if (live) setData(r); })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    return () => { live = false; };
  }, [sort, sector, index, q, limit]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6">
      <PageHeader
        eyebrow="Equities · NSE universe"
        title="Equities Desk"
        sub="Every tracked listed company with live price, valuation and sector context. Click a company for the full deep-dive: 5-year history, all ratios, DCF, peers and the F&O tab."
        right={<RefreshButton stage="equities" />}
      />

      <div className="flex flex-wrap gap-2 mb-4">
        {SORTS.map(([k, label]) => (
          <button key={k} onClick={() => setSort(k)}
            className={`chip ${sort === k ? "chip-active" : ""}`}>{label}</button>
        ))}
        <select value={sector} onChange={(e) => setSector(e.target.value)}
          className="surface rounded-lg px-3 py-1.5 text-[12.5px]" style={{ color: "var(--ink)" }}>
          <option value="">All sectors</option>
          {(data?.sectors || []).map((s: string) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={index} onChange={(e) => { setIndex(e.target.value); setLimit(250); }}
          className="surface rounded-lg px-3 py-1.5 text-[12.5px]" style={{ color: "var(--ink)" }}>
          <option value="">All indices</option>
          {["NIFTY 50", "NIFTY 100", "NIFTY 200", "SENSEX", "NIFTY NEXT 50",
            "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 100"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="surface rounded-xl px-3 py-2 mb-4 max-w-md">
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by symbol…"
          className="w-full bg-transparent text-[13.5px] outline-none"
          style={{ color: "var(--ink)" }}
        />
      </div>

      {err && <ErrorBox message={err} stage="equities" />}
      {!data && !err && <Skeleton rows={8} />}

      {data && (
        <>
          <div className="muted text-[12px] mb-2">{data.count} companies tracked</div>
          <div className="card overflow-x-auto">
            <div className="min-w-[880px]">
              <div className="grid grid-cols-[1.3fr_.9fr_.7fr_.7fr_.6fr_1fr] gap-3 px-5 py-3 muted text-[10.5px] font-bold uppercase tracking-[0.14em]">
                <span>Company</span>
                <span className="text-right">Price</span>
                <span className="text-right">
                  <MetricTip label="Day" tip={{ meaning: "Percentage change from the previous session's close." }}>Day</MetricTip>
                </span>
                <span className="text-right">
                  <MetricTip label="P/E" tip={{
                    meaning: "Price-to-Earnings: the market price divided by trailing twelve-month earnings per share — how many rupees investors pay per rupee of annual profit.",
                    formula: "P/E = Market price ÷ EPS",
                  }}>P/E</MetricTip>
                </span>
                <span className="text-right">
                  <MetricTip label="P/B" tip={{
                    meaning: "Price-to-Book: price divided by book value per share. A P/B below 1 means the market values the company below its stated net assets.",
                    formula: "P/B = Market price ÷ Book value per share",
                  }}>P/B</MetricTip>
                </span>
                <span className="text-right">
                  <MetricTip label="M-cap" tip={{
                    meaning: "Market capitalisation: the total value the market puts on the company's equity.",
                    formula: "M-cap = Last price × shares outstanding",
                    example: "Reliance at ₹1,164.90 × 1,353 crore shares ≈ ₹15.8 lakh crore.",
                  }}>M-cap</MetricTip>
                </span>
              </div>
              {data.stocks.map((s: Stock) => (
                <div key={s.symbol} className="table-row grid grid-cols-[1.3fr_.9fr_.7fr_.7fr_.6fr_1fr] gap-3 px-5 py-3 items-center">
                  <div>
                    <Link href={s.href} className="text-[13.5px] font-bold hover:underline">
                      {s.symbol}
                    </Link>
                    <div className="muted text-[11px] truncate">{s.name}</div>
                    {(s as any).indices?.value?.length ? (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {(s as any).indices.value.slice(0, 3).map((x: string) => (
                          <span key={x} className="chip !text-[8px] !py-0">{x}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="text-right knum font-semibold">{inr(s.last?.value)}</div>
                  <div className="text-right"><PctVal env={s.changepct} /></div>
                  <div className="text-right"><EnvVal env={s.pe} fmt={(v) => v.toFixed(1)} /></div>
                  <div className="text-right"><EnvVal env={s.pb} fmt={(v) => v.toFixed(1)} /></div>
                  <div className="text-right knum text-[12.5px]">{bigCrude(s.market_cap?.value)}</div>
                </div>
              ))}
            </div>
          </div>

          {data.count > data.stocks.length && (
            <div className="text-center mt-4">
              <button onClick={() => setLimit(limit + 100)} className="btn-ghost !py-2 !text-[13px]">
                Show more companies ({data.count - data.stocks.length} remaining)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
