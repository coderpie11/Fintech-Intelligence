"use client";

import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid } from "@/components/PageKit";
import LineChart from "@/components/LineChart";
import Tabs from "@/components/Tabs";
import MetricTip from "@/components/MetricTip";

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

type Metal = {
  symbol: string; name: string;
  last: Env; changepct: Env; usd_per_oz: Env; usdinr: Env;
  inr_per_gram_24k: Env; inr_per_10g_24k: Env;
  inr_per_gram_22k: Env; inr_per_10g_22k: Env;
  inr_per_gram_silver: Env; inr_per_kg_silver: Env; inr_per_10g_silver: Env;
  note: Env; href: string;
};

export default function CommodityDesk() {
  const [list, setList] = useState<any>(null);
  const [metal, setMetal] = useState<Metal | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [intraday, setIntraday] = useState<any>(null);
  const [ratio, setRatio] = useState<any>(null);
  const [sgb, setSgb] = useState<any>(null);
  const [tab, setTab] = useState("gold");
  const [err, setErr] = useState<string | null>(null);

  const [grams, setGrams] = useState("10");
  const [years, setYears] = useState("5");
  const [cagr, setCagr] = useState("8");
  const [making, setMaking] = useState("12");
  const [slab, setSlab] = useState("30");
  const [wealth, setWealth] = useState<any>(null);
  const [wErr, setWErr] = useState<string | null>(null);

  useEffect(() => {
    getJSON("/commodities").then((d) => {
      setList(d);
      setMetal(d.commodities?.[0] || null);
    }).catch((e) => setErr(String(e.message || e)));
    getJSON("/commodities/ratio/history").then(setRatio).catch(() => {});
    getJSON("/commodities/sgb").then(setSgb).catch(() => {});
  }, []);

  useEffect(() => {
    if (!metal) return;
    setDetail(null);
    setIntraday(null);
    getJSON(`/commodities/detail/${encodeURIComponent(metal.symbol)}`)
      .then(setDetail).catch(() => {});
    getJSON(`/commodities/${encodeURIComponent(metal.symbol)}/intraday`)
      .then(setIntraday).catch(() => {});
  }, [metal]);

  useEffect(() => {
    if (tab !== "ratio") return;
    getJSON("/commodities/ratio/intraday").then(setIntraday).catch(() => {});
  }, [tab]);

  useEffect(() => {
    if (!list?.commodities?.length) return;
    const g = list.commodities.find((c: Metal) => c.symbol === "GOLD");
    const s = list.commodities.find((c: Metal) => c.symbol === "SILVER");
    setMetal(tab === "gold" ? g : tab === "silver" ? s : null);
  }, [tab, list]);

  const runWealth = async () => {
    setWErr(null); setWealth(null);
    try {
      const r = await postJSON("/commodities/calc/wealth", {
        grams: Number(grams), years: Number(years), gold_cagr_pct: Number(cagr),
        making_charge_pct: Number(making), tax_slab_pct: Number(slab),
      });
      setWealth(r);
    } catch (e: any) { setWErr(String(e.message || e).slice(0, 200)); }
  };

  const isGold = metal?.symbol === "GOLD";
  const isSilver = metal?.symbol === "SILVER";
  const ratioPoints = useMemo(
    () => (ratio?.points || []).map((p: any) => ({ date: p.date, close: p.ratio })),
    [ratio],
  );
  const intradayPoints = useMemo(
    () => (intraday?.points || []).map((p: any) => ({
      date: p.date, close: p.close ?? p.c, open: p.open ?? p.o,
      high: p.high ?? p.h, low: p.low ?? p.l,
      time: p.time, datetime: p.datetime, volume: p.volume ?? p.v,
    })),
    [intraday],
  );

  const tabs = [
    { key: "gold", label: "Gold" },
    { key: "silver", label: "Silver" },
    { key: "ratio", label: "Gold : Silver ratio" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Precious metals"
        title="Gold & Silver Hub"
        sub="International spot converted to ₹ per gram and per 10 g, five-year crosshair charts, the gold/silver ratio with historical bands, an SGB secondary scanner and a physical-vs-ETF-vs-SGB calculator."
        right={<RefreshButton stage="commodities" />}
      />

      {err && <ErrorBox message={err} stage="commodities" />}
      {!list && !err && <Skeleton rows={6} />}

      {list && (
        <>
          <div className="mb-4"><Tabs tabs={tabs} active={tab} onChange={setTab} /></div>

          {tab === "ratio" ? (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
                {[
                  ["Latest ratio", ratio?.latest, (v: number) => v.toFixed(2)],
                  ["5Y mean", ratio?.mean, (v: number) => v.toFixed(2)],
                  ["+1σ zone", ratio?.zones?.upper, (v: number) => v.toFixed(2)],
                  ["−1σ zone", ratio?.zones?.lower, (v: number) => v.toFixed(2)],
                ].map(([label, v, fmt]: any) => (
                  <div key={label} className="card p-3">
                    <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">{label}</div>
                    <div className="knum text-[20px] font-black mt-1">
                      {v != null ? fmt(v) : "—"}
                    </div>
                  </div>
                ))}
              </div>
              <div className="card p-4 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="text-[13px] font-bold">Gold-to-silver ratio · 5 years</div>
                    <div className="muted text-[10.5px]">{ratio?.zone?.value}</div>
                  </div>
                  <div className="flex gap-1.5">
                    <span className="chip !text-[9px]">mean {ratio?.mean?.toFixed(2)}</span>
                    <span className="chip chip-warn !text-[9px]">±1σ band</span>
                  </div>
                </div>
                <LineChart points={ratioPoints} height={320} defaultRange="1D"
                           intradayPoints={intradayPoints}
                           intradaySource={intraday?.source}
                           prevClose={intraday?.prevClose}
                           valuePrefix="" valueSuffix="x"
                           title="Gold / silver ratio" />
                <p className="muted text-[10.5px] mt-2 leading-relaxed">{ratio?.note}</p>
              </div>
            </>
          ) : metal ? (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
                <div className="card p-3">
                  <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">International front month</div>
                  <div className="knum text-[22px] font-black mt-1">
                    ${envNum(metal.last)?.toFixed(2) ?? "—"}
                  </div>
                  <div className={`text-[11px] font-semibold ${(envNum(metal.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                    {envNum(metal.changepct) != null ? pct(envNum(metal.changepct)) : "—"} · USD/oz
                  </div>
                </div>
                <div className="card p-3">
                  <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">USD/INR</div>
                  <div className="knum text-[22px] font-black mt-1">{envNum(metal.usdinr)?.toFixed(2) ?? "—"}</div>
                  <div className="muted text-[10px] mt-0.5">conversion rate</div>
                </div>
                {isGold ? (
                  <>
                    <div className="card p-3">
                      <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">24K · ₹ per 10 g</div>
                      <div className="knum text-[22px] font-black mt-1">{envNum(metal.inr_per_10g_24k) != null ? inr(envNum(metal.inr_per_10g_24k)) : "—"}</div>
                      <div className="muted text-[10px] mt-0.5">₹{envNum(metal.inr_per_gram_24k)?.toFixed(2) ?? "—"} per gram</div>
                    </div>
                    <div className="card p-3">
                      <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">22K · ₹ per 10 g</div>
                      <div className="knum text-[22px] font-black mt-1">{envNum(metal.inr_per_10g_22k) != null ? inr(envNum(metal.inr_per_10g_22k)) : "—"}</div>
                      <div className="muted text-[10px] mt-0.5">91.6% purity conversion</div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="card p-3">
                      <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Silver · ₹ per kg</div>
                      <div className="knum text-[22px] font-black mt-1">{envNum(metal.inr_per_kg_silver) != null ? inr(envNum(metal.inr_per_kg_silver)) : "—"}</div>
                      <div className="muted text-[10px] mt-0.5">₹{envNum(metal.inr_per_gram_silver)?.toFixed(2) ?? "—"} per gram</div>
                    </div>
                    <div className="card p-3">
                      <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Silver · ₹ per 10 g</div>
                      <div className="knum text-[22px] font-black mt-1">{envNum(metal.inr_per_10g_silver) != null ? inr(envNum(metal.inr_per_10g_silver)) : "—"}</div>
                      <div className="muted text-[10px] mt-0.5">raw metal, before GST</div>
                    </div>
                  </>
                )}
              </div>

              {detail && (
                <>
                  <div className="card p-4 mb-4">
                    <LineChart
                      points={((detail.chart || detail.history) || []).map((h: any) => ({
                        date: h.date, close: h.close, open: h.open, high: h.high, low: h.low,
                      }))}
                      intradayPoints={intradayPoints}
                      intradaySource={intraday?.source}
                      prevClose={intraday?.prevClose}
                      height={340} defaultRange="1D"
                      title={`${metal.name} · price (${detail.chart_unit || "₹"})`}
                    />
                  </div>

                  <StatGrid items={[
                    { label: "Volatility 1Y", env: detail.stats?.vol_annual, fmt: (v: number) => `${v.toFixed(2)}%`,
                      tip: { meaning: "Annualised standard deviation of daily returns over the last 252 sessions — how wide the metal's normal price swings are.",
                             formula: "σ_annual = σ_daily × √252" } },
                    { label: "Max drawdown 5Y", env: detail.stats?.max_dd_5y, fmt: (v: number) => `${v.toFixed(2)}%`,
                      tip: { meaning: "The largest peak-to-trough fall in the stored five-year series. It measures pain already experienced, not a forecast.",
                             formula: "Max DD = (Trough ÷ prior Peak − 1) × 100" } },
                    { label: "5Y CAGR", env: detail.stats?.cagr_5y, fmt: (v: number) => `${v.toFixed(2)}%`,
                      tip: { meaning: "The constant annual rate that would take the five-year-ago price to today's price.",
                             formula: "CAGR = (End ÷ Start)^(1 ÷ Years) − 1" } },
                    { label: "5Y high", env: detail.stats?.high_5y, fmt: inr,
                      tip: { meaning: "Highest price in the stored five-year window, in the unit printed on the chart." } },
                    { label: "5Y low", env: detail.stats?.low_5y, fmt: inr,
                      tip: { meaning: "Lowest price in the stored five-year window. Together with the 5Y high it frames the historical range." } },
                  ]} />

                  <div className="card p-4 mt-4 muted text-[11.5px] leading-relaxed">
                    <b style={{ color: "var(--ink)" }}>Why ₹ figures are indicative:</b>{" "}
                    {String(metal.note?.value || "").replace(/\.$/, "")}. Indian jewellery adds import duty, GST (3% gold,
                    5% silver) and dealer margin.
                  </div>
                </>
              )}
            </>
          ) : null}

          <section className="mt-8">
            <SectionTitle title="Listed Sovereign Gold Bond scanner"
                        sub="Twelve real NSE tranches with market price vs gold fair value, remaining coupon, maturity and tax-free maturity yield." />
            {!sgb && <Skeleton rows={4} />}
            {sgb && (
              <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1150px] border-collapse">
                    <thead>
                      <tr style={{ background: "var(--surface-2)" }}>
                        <th className="table-head text-left px-3 py-2.5">Tranche</th>
                        <th className="table-head text-right px-2.5 py-2.5">Market price</th>
                        <th className="table-head text-right px-2.5 py-2.5">
                          <MetricTip label="Gold fair value" tip={{
                            meaning: "The intrinsic value of one SGB unit from the rupee gold price, before any market premium or discount.",
                            formula: "Fair value = gold price per gram × grams per unit",
                          }}>Gold fair value</MetricTip>
                        </th>
                        <th className="table-head text-right px-2.5 py-2.5">
                          <MetricTip label="Disc / premium" tip={{
                            meaning: "How far the exchange price sits from intrinsic gold value. A discount can reflect low liquidity, not free money.",
                            formula: "Disc/premium % = (Market price ÷ Fair value − 1) × 100",
                          }}>Disc / premium</MetricTip>
                        </th>
                        <th className="table-head text-right px-2.5 py-2.5">Coupon</th>
                        <th className="table-head text-right px-2.5 py-2.5">Next coupon</th>
                        <th className="table-head text-right px-2.5 py-2.5">Matures</th>
                        <th className="table-head text-right px-3 py-2.5">
                          <MetricTip label="Tax-free yield" tip={{
                            meaning: "Yield to maturity on the SGB's market price, using its coupon and redemption at par. SGB interest and maturity redemption are exempt from capital-gains tax for resident holders.",
                            example: "A ₹4,900 price with a 2.5% coupon and 3 years left to a ₹5,000 par redemption yields about 3.4% a year.",
                          }}>Tax-free yield</MetricTip>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sgb.tranches.map((t: any) => (
                        <tr key={t.symbol} className="table-row">
                          <td className="px-3 py-2.5">
                            <div className="text-[12px] font-bold">{t.symbol}</div>
                            <div className="muted text-[10px]">{t.name}</div>
                          </td>
                          <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{inr(envNum(t.market_price))}</td>
                          <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{inr(envNum(t.fair_value))}</td>
                          <td className={`px-2.5 py-2.5 text-right knum text-[11.5px] font-semibold ${(envNum(t.discount_premium_pct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                            {envNum(t.discount_premium_pct) != null ? pct(envNum(t.discount_premium_pct)) : "—"}
                          </td>
                          <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{t.coupon_pct}%</td>
                          <td className="px-2.5 py-2.5 text-right text-[11px]">{t.next_coupon_date || "—"}</td>
                          <td className="px-2.5 py-2.5 text-right text-[11px]">{t.maturity || "—"}</td>
                          <td className="px-3 py-2.5 text-right knum text-[11.5px] font-bold text-up">
                            {envNum(t.maturity_yield_pct) != null ? `${envNum(t.maturity_yield_pct)!.toFixed(2)}%` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="px-3.5 py-2.5 muted text-[10.5px] leading-relaxed"
                     style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  {sgb.note}
                </div>
              </div>
            )}
          </section>

          <section className="mt-8 grid lg:grid-cols-[380px_1fr] gap-3">
            <div className="card p-4">
              <div className="text-[13px] font-bold">Physical vs ETF vs SGB</div>
              <p className="muted text-[11px] mt-0.5 leading-relaxed">
                Same gold CAGR for all three; the difference is making charges, GST,
                TER and the SGB coupon.
              </p>
              <div className="grid grid-cols-2 gap-2 mt-3">
                {[
                  ["Grams", grams, setGrams], ["Years", years, setYears],
                  ["Gold CAGR %", cagr, setCagr], ["Making charge %", making, setMaking],
                  ["Tax slab %", slab, setSlab],
                ].map(([l, v, set]: any) => (
                  <label key={l} className="block">
                    <span className="muted text-[9px] font-bold uppercase tracking-wider">{l}</span>
                    <input value={v} onChange={(e) => set(e.target.value)} inputMode="decimal"
                           className="surface rounded-lg w-full mt-0.5 px-2 py-1.5 text-[11.5px] knum"
                           style={{ color: "var(--ink)" }} />
                  </label>
                ))}
              </div>
              <button onClick={runWealth} className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">
                Compare 1–8 year wealth
              </button>
              {wErr && <p className="text-[11px] text-down mt-1">{wErr}</p>}
            </div>
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-2">Wealth outcome</div>
              {!wealth && <p className="muted text-[12px]">Run the comparison.</p>}
              {wealth && (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] border-collapse text-[11.5px]">
                      <thead>
                        <tr style={{ background: "var(--surface-2)" }}>
                          <th className="table-head text-left px-2.5 py-2">Vehicle</th>
                          <th className="table-head text-right px-2.5 py-2">Outlay</th>
                          <th className="table-head text-right px-2.5 py-2">Fees/tax</th>
                          <th className="table-head text-right px-2.5 py-2">End value</th>
                          <th className="table-head text-right px-2.5 py-2">CAGR</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wealth.rows.map((r: any) => (
                          <tr key={r.vehicle} className="table-row">
                            <td className="px-2.5 py-2 font-semibold">{r.vehicle}</td>
                            <td className="px-2.5 py-2 text-right knum">{inr(r.outlay)}</td>
                            <td className="px-2.5 py-2 text-right knum text-down">{inr(r.fees)}</td>
                            <td className="px-2.5 py-2 text-right knum font-bold">{inr(r.end_value)}</td>
                            <td className={`px-2.5 py-2 text-right knum font-bold ${r.effective_cagr_pct >= 0 ? "text-up" : "text-down"}`}>
                              {r.effective_cagr_pct.toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted text-[10.5px] mt-2 leading-relaxed">{wealth.note}</p>
                </>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
