"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid } from "@/components/PageKit";
import LineChart from "@/components/LineChart";
import MetricTip from "@/components/MetricTip";

const TRUST_TIPS: Record<string, { meaning: string; formula?: string; example?: string }> = {
  occupancy: { meaning: "Share of leasable area that is actually leased. Higher occupancy means steadier rent." },
  wale: { meaning: "Weighted average lease expiry: the average time left on leases, weighted by rent. Longer WALE means more predictable cash flow.",
          example: "A 4.7-year WALE spreads lease renewals out, so a single tenant exit hurts less." },
  cap: { meaning: "Capitalisation rate: net operating income as a percentage of asset value, before financing. It is the property's earnings yield.",
         formula: "Cap rate % = Net operating income ÷ Property value × 100" },
  ndcf: { meaning: "Net Distributable Cash Flow yield: the cash a trust can distribute in a year as a percentage of its market price. This is the REIT's equivalent of a dividend yield.",
         formula: "NDCF yield % = Annual distribution per unit ÷ Market price × 100",
         example: "A ₹7 distribution on a ₹100 unit is a 7% NDCF yield." },
  debtgav: { meaning: "Total debt as a percentage of gross asset value. SEBI caps REIT leverage, so a lower number means more headroom.",
            formula: "Debt/GAV % = Total debt ÷ Gross asset value × 100" },
  nav: { meaning: "Net asset value per unit: the trust's assets minus liabilities, divided by units outstanding. Price below NAV can signal a discount to asset value." },
};

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

type Trust = {
  symbol: string; name: string; kind: string;
  last: Env; changepct: Env; asof: Env; market_cap: Env; listing_date: Env;
  occupancy_pct: Env; wale_years: Env; cap_rate_pct: Env;
  ndcf_yield_pct: Env; debt_gav_pct: Env; nav_per_unit: Env;
  distribution_split: Record<string, number>;
  distribution_rule: Env; yield: Env; facts_asof?: string; href: string;
};

export function ReitList() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getJSON("/reits").then(setData).catch((e) => setErr(String(e.message || e)));
  }, []);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="REITs & InvITs"
        title="Trusts Desk"
        sub="Seven listed trusts with live prices, five-year charts, occupancy, WALE, cap rate, NDCF distribution yield, Debt-GAV and a four-component post-tax distribution calculator."
        right={<RefreshButton stage="reits" />}
      />

      {err && <ErrorBox message={err} stage="reits" />}
      {!data && !err && <Skeleton rows={6} />}

      {data && (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-5">
            {data.reits.map((t: Trust) => (
              <Link key={t.symbol} href={t.href} className="card p-4 hover:opacity-90 transition-opacity">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[14px] font-extrabold">{t.symbol}</div>
                    <div className="muted text-[10.5px] leading-snug">{t.name}</div>
                  </div>
                  <span className="chip !text-[9px]">{t.kind}</span>
                </div>
                <div className="flex items-end gap-2 mt-3">
                  <span className="knum text-[22px] font-black">{envNum(t.last) != null ? inr(envNum(t.last)) : "—"}</span>
                  <span className={`knum text-[11.5px] font-bold ${(envNum(t.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                    {envNum(t.changepct) != null ? pct(envNum(t.changepct)) : "—"}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1.5 mt-3 text-[10.5px]">
                  <div className="flex justify-between"><span className="muted"><MetricTip label="Occupancy" tip={TRUST_TIPS.occupancy}>Occupancy</MetricTip></span><span className="knum">{envNum(t.occupancy_pct) != null ? `${envNum(t.occupancy_pct)!.toFixed(1)}%` : "—"}</span></div>
                  <div className="flex justify-between"><span className="muted"><MetricTip label="WALE" tip={TRUST_TIPS.wale}>WALE</MetricTip></span><span className="knum">{envNum(t.wale_years) != null ? `${envNum(t.wale_years)!.toFixed(1)}y` : "—"}</span></div>
                  <div className="flex justify-between"><span className="muted"><MetricTip label="Cap rate" tip={TRUST_TIPS.cap}>Cap rate</MetricTip></span><span className="knum">{envNum(t.cap_rate_pct) != null ? `${envNum(t.cap_rate_pct)!.toFixed(1)}%` : "—"}</span></div>
                  <div className="flex justify-between"><span className="muted"><MetricTip label="NDCF yield" tip={TRUST_TIPS.ndcf}>NDCF yield</MetricTip></span><span className="knum text-up">{envNum(t.ndcf_yield_pct) != null ? `${envNum(t.ndcf_yield_pct)!.toFixed(1)}%` : "—"}</span></div>
                  <div className="flex justify-between"><span className="muted"><MetricTip label="Debt/GAV" tip={TRUST_TIPS.debtgav}>Debt/GAV</MetricTip></span><span className="knum">{envNum(t.debt_gav_pct) != null ? `${envNum(t.debt_gav_pct)!.toFixed(1)}%` : "—"}</span></div>
                  <div className="flex justify-between"><span className="muted"><MetricTip label="NAV/unit" tip={TRUST_TIPS.nav}>NAV/unit</MetricTip></span><span className="knum">{envNum(t.nav_per_unit) != null ? inr(envNum(t.nav_per_unit)) : "—"}</span></div>
                </div>
              </Link>
            ))}
          </div>

          <div className="card overflow-hidden mb-4">
            <div className="px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-2"
                 style={{ borderBottom: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <div className="text-[12.5px] font-bold">All seven listed trusts · complete metric check</div>
              <span className="muted text-[10.5px]">{data.reits.length}/7 trusts priced</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2">Trust</th>
                    <th className="table-head text-right px-2.5 py-2">Price</th>
                    <th className="table-head text-right px-2.5 py-2">1D</th>
                    <th className="table-head text-right px-2.5 py-2">Occupancy</th>
                    <th className="table-head text-right px-2.5 py-2">WALE</th>
                    <th className="table-head text-right px-2.5 py-2">Cap rate</th>
                    <th className="table-head text-right px-2.5 py-2">NDCF yield</th>
                    <th className="table-head text-right px-2.5 py-2">Debt/GAV</th>
                    <th className="table-head text-right px-2.5 py-2">NAV/unit</th>
                    <th className="table-head text-center px-3 py-2">Complete</th>
                  </tr>
                </thead>
                <tbody>
                  {data.reits.map((t: Trust) => {
                    const metrics = [t.last, t.occupancy_pct, t.wale_years, t.cap_rate_pct,
                                     t.ndcf_yield_pct, t.debt_gav_pct, t.nav_per_unit];
                    const complete = metrics.every((m) => envNum(m) != null);
                    return (
                      <tr key={t.symbol} className="table-row">
                        <td className="px-3 py-2">
                          <Link href={t.href} className="text-[12px] font-bold hover:underline">{t.symbol}</Link>
                          <div className="muted text-[9.5px] truncate max-w-[220px]">{t.name}</div>
                        </td>
                        <td className="px-2.5 py-2 text-right knum text-[11.5px] font-semibold">{envNum(t.last) != null ? inr(envNum(t.last)) : "—"}</td>
                        <td className={`px-2.5 py-2 text-right knum text-[11px] ${(envNum(t.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                          {envNum(t.changepct) != null ? pct(envNum(t.changepct)) : "—"}
                        </td>
                        <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(t.occupancy_pct) != null ? `${envNum(t.occupancy_pct)!.toFixed(1)}%` : "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(t.wale_years) != null ? `${envNum(t.wale_years)!.toFixed(1)}y` : "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(t.cap_rate_pct) != null ? `${envNum(t.cap_rate_pct)!.toFixed(1)}%` : "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[11px] text-up">{envNum(t.ndcf_yield_pct) != null ? `${envNum(t.ndcf_yield_pct)!.toFixed(1)}%` : "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(t.debt_gav_pct) != null ? `${envNum(t.debt_gav_pct)!.toFixed(1)}%` : "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(t.nav_per_unit) != null ? inr(envNum(t.nav_per_unit)) : "—"}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`chip !text-[9px] ${complete ? "chip-live" : "chip-warn"}`}>
                            {complete ? "complete" : "partial"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card p-4 muted text-[11.5px] leading-relaxed">
            <b style={{ color: "var(--ink)" }}>Distribution rule (statutory):</b>{" "}
            SEBI requires each REIT/InvIT to distribute at least 90% of Net
            Distributable Cash Flows to unitholders. Operating metrics are the latest
            disclosed figures and are labelled approximate where a quarter-end
            disclosure is not available.
          </div>
        </>
      )}
    </div>
  );
}

export function ReitDetail({ symbol }: { symbol: string }) {
  const sym = (symbol || "").toUpperCase();
  const [d, setD] = useState<any>(null);
  const [intraday, setIntraday] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const [units, setUnits] = useState("1000");
  const [price, setPrice] = useState("100");
  const [dist, setDist] = useState("7");
  const [interest, setInterest] = useState("45");
  const [dividend, setDividend] = useState("30");
  const [amort, setAmort] = useState("20");
  const [other, setOther] = useState("5");
  const [slab, setSlab] = useState("30");
  const [calc, setCalc] = useState<any>(null);
  const [calcErr, setCalcErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setD(null); setIntraday(null); setErr(null);
    getJSON(`/reits/${encodeURIComponent(sym)}`)
      .then((r) => {
        if (!live) return;
        setD(r);
        if (r.last?.value != null) setPrice(String(r.last.value));
        if (r.last?.value != null && r.ndcf_yield_pct?.value != null) {
          // The calculator takes the annual distribution per unit. Deriving it
          // from the NDCF yield keeps the worked example consistent with the
          // yield printed on the card instead of silently using a monthly figure.
          setDist(String((r.last.value * r.ndcf_yield_pct.value / 100).toFixed(2)));
        }
        const split = r.distribution_split || {};
        if (split.interest != null) setInterest(String(split.interest));
        if (split.dividend != null) setDividend(String(split.dividend));
        if (split.amortization != null) setAmort(String(split.amortization));
        if (split.other != null) setOther(String(split.other));
      })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    getJSON(`/reits/${encodeURIComponent(sym)}/intraday`)
      .then((r) => { if (live) setIntraday(r); })
      .catch(() => {});
    return () => { live = false; };
  }, [sym]);

  const runCalc = async () => {
    setCalcErr(null); setCalc(null);
    try {
      const r = await postJSON(`/reits/${encodeURIComponent(sym)}/distribution-calculator`, {
        units: Number(units), price_per_unit: Number(price),
        distribution_per_unit: Number(dist),
        interest_pct: Number(interest), dividend_pct: Number(dividend),
        amortization_pct: Number(amort), other_pct: Number(other),
        tax_slab_pct: Number(slab),
      });
      setCalc(r);
    } catch (e: any) { setCalcErr(String(e.message || e).slice(0, 180)); }
  };

  const intradayPoints = (intraday?.points || []).map((p: any) => ({
    date: p.date, close: p.c, open: p.o, high: p.h, low: p.l,
    time: p.time, datetime: p.datetime, volume: p.v,
  }));

  if (err) return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
      <ErrorBox message={err} stage="reits" />
      <Link href="/reits" className="btn-secondary mt-4">← Back to trusts</Link>
    </div>
  );
  if (!d) return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8 space-y-3">
      <div className="skeleton h-16" /><Skeleton rows={7} />
    </div>
  );

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/reits" className="hover:underline">Trusts</Link>
        <span className="opacity-40">/</span>
        <span className="font-semibold" style={{ color: "var(--ink)" }}>{d.symbol}</span>
      </div>

      <PageHeader
        eyebrow={`${d.kind} · ${d.facts_asof || "latest disclosure"}`}
        title={d.name}
        sub={`${d.symbol} · ${d.kind === "REIT" ? "commercial real estate" : "infrastructure"} trust listed on the NSE.`}
        right={<RefreshButton stage="reits" label="Refresh trusts" />}
      />

      <div className="grid lg:grid-cols-[1fr_330px] gap-3 mb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
            <div>
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">Last traded price</div>
              <div className="flex items-end gap-3 mt-1">
                <span className="knum text-[34px] font-black leading-none">{inr(envNum(d.last))}</span>
                <span className={`knum text-[14px] font-bold ${(envNum(d.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                  {envNum(d.changepct) != null ? pct(envNum(d.changepct)) : "—"}
                </span>
              </div>
              <div className="muted text-[11px] mt-1.5">As of {d.asof?.value ? fmtDate(d.asof.value) : "—"}</div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="chip !text-[9.5px]">NDCF {envNum(d.ndcf_yield_pct) != null ? `${envNum(d.ndcf_yield_pct)!.toFixed(1)}%` : "—"}</span>
              <span className="chip !text-[9.5px]">Cap rate {envNum(d.cap_rate_pct) != null ? `${envNum(d.cap_rate_pct)!.toFixed(1)}%` : "—"}</span>
              <span className="chip !text-[9.5px]">Debt/GAV {envNum(d.debt_gav_pct) != null ? `${envNum(d.debt_gav_pct)!.toFixed(1)}%` : "—"}</span>
            </div>
          </div>
          <LineChart points={d.history || []} height={330} defaultRange="5Y"
                     intradayPoints={intradayPoints}
                     intradaySource={intraday?.source}
                     prevClose={intraday?.prevClose ?? d.prev_close?.value}
                     title={`${d.name} · five-year price history`} />
        </div>

        <aside className="card p-4 sm:p-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {[
              ["Occupancy", d.occupancy_pct, (v: number) => `${v.toFixed(1)}%`],
              ["WALE", d.wale_years, (v: number) => `${v.toFixed(1)} years`],
              ["Cap rate", d.cap_rate_pct, (v: number) => `${v.toFixed(2)}%`],
              ["NDCF yield", d.ndcf_yield_pct, (v: number) => `${v.toFixed(2)}%`],
              ["Debt to GAV", d.debt_gav_pct, (v: number) => `${v.toFixed(1)}%`],
              ["NAV / unit", d.nav_per_unit, inr],
            ].map(([label, env, fmt]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                <div className="knum text-[12.5px] font-bold mt-0.5">
                  {envNum(env) != null ? fmt(envNum(env)) : "—"}
                </div>
              </div>
            ))}
          </div>
          <div>
            <div className="muted text-[10px] font-bold uppercase tracking-[0.13em] mb-1.5">Distribution mix</div>
            {["interest", "dividend", "amortization", "other"].map((k) => {
              const v = d.distribution_split?.[k] ?? 0;
              return (
                <div key={k} className="mb-1.5">
                  <div className="flex justify-between text-[10px] muted">
                    <span>{k === "amortization" ? "Debt repayment (tax-free)" : k}</span>
                    <span className="knum">{v}%</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
                    <div style={{ width: `${v}%`, background: "var(--accent)" }} className="h-full" />
                  </div>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      <section className="mb-6">
        <SectionTitle title="Returns & risk" sub="Price returns from the stored five-year series; 3Y and 5Y are CAGR." />
        <StatGrid items={[
          { label: "1M", env: d.returns?.["1m"], fmt: pct,
            tip: { meaning: "Simple price return over the last 21 trading sessions.", formula: "Return = (End ÷ Start − 1) × 100" } },
          { label: "3M", env: d.returns?.["3m"], fmt: pct,
            tip: { meaning: "Simple price return over the last 63 trading sessions.", formula: "Return = (End ÷ Start − 1) × 100" } },
          { label: "1Y", env: d.returns?.["1y"], fmt: pct,
            tip: { meaning: "Simple price return over the last 252 trading sessions.", formula: "Return = (End ÷ Start − 1) × 100" } },
          { label: "3Y CAGR", env: d.returns?.["3y"], fmt: pct,
            tip: { meaning: "Compound annual growth over roughly 756 sessions — the constant yearly rate that reaches the same end value.",
                   formula: "CAGR = (End ÷ Start)^(1 ÷ Years) − 1" } },
          { label: "5Y CAGR", env: d.returns?.["5y"], fmt: pct,
            tip: { meaning: "Compound annual growth across the full stored five-year history.",
                   formula: "CAGR = (End ÷ Start)^(1 ÷ Years) − 1" } },
          { label: "Volatility", env: d.stats?.vol_annual, fmt: (v: number) => `${v.toFixed(2)}%`,
            tip: { meaning: "Annualised standard deviation of daily returns: how wide the normal swings are.",
                   formula: "σ_annual = σ_daily × √252" } },
          { label: "Max drawdown", env: d.stats?.max_dd_5y, fmt: (v: number) => `${v.toFixed(2)}%`,
            tip: { meaning: "Largest peak-to-trough fall in the stored series — realised pain, not a forecast.",
                   formula: "Max DD = (Trough ÷ prior Peak − 1) × 100" } },
          { label: "History depth", env: { value: d.history_points, status: "REPORTED", note: "Stored sessions available for this instrument." }, fmt: (v: number) => `${v} sessions`,
            tip: { meaning: "How many stored sessions back this calculation can see. A short series makes every statistic less reliable." } },
        ]} />
      </section>

      <section className="grid lg:grid-cols-[380px_1fr] gap-3 mb-6">
        <div className="card p-4">
          <div className="text-[13px] font-bold">Post-tax distribution calculator</div>
          <p className="muted text-[11px] mt-0.5 leading-relaxed">
            Splits the payout into interest, dividend, tax-free debt repayment and
            other income, then applies your slab.
          </p>
          <div className="grid grid-cols-2 gap-2 mt-3">
            {[
              ["Units", units, setUnits], ["Price / unit", price, setPrice],
              ["Distribution / unit", dist, setDist], ["Interest %", interest, setInterest],
              ["Dividend %", dividend, setDividend], ["Amortization %", amort, setAmort],
              ["Other %", other, setOther], ["Tax slab %", slab, setSlab],
            ].map(([l, v, set]: any) => (
              <label key={l} className="block">
                <span className="muted text-[9px] font-bold uppercase tracking-wider">{l}</span>
                <input value={v} onChange={(e) => set(e.target.value)} inputMode="decimal"
                       className="surface rounded-lg w-full mt-0.5 px-2 py-1.5 text-[11.5px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            ))}
          </div>
          <button onClick={runCalc} className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">
            Compute post-tax payout
          </button>
          {calcErr && <p className="text-[11px] text-down mt-1">{calcErr}</p>}
        </div>
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-2">Payout outcome</div>
          {!calc && !calcErr && <p className="muted text-[12px]">Run the calculator.</p>}
          {calc && (
            <div className="space-y-1.5 text-[12px]">
              <div className="flex justify-between"><span className="muted">Total distribution</span><span className="knum font-bold">{inr(calc.total_distribution)}</span></div>
              {["interest", "dividend", "amortization", "other"].map((k) => (
                <div key={k} className="flex justify-between">
                  <span className="muted">{k === "amortization" ? "Debt repayment (tax-free)" : k}</span>
                  <span className="knum">{inr(calc.split[k])}</span>
                </div>
              ))}
              <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                <span className="muted">Tax at slab</span><span className="knum text-down">−{inr(calc.tax_at_slab)}</span>
              </div>
              <div className="flex justify-between"><span className="muted font-semibold">Post-tax payout</span><span className="knum font-black">{inr(calc.post_tax_distribution)}</span></div>
              <div className="flex justify-between"><span className="muted">Post-tax yield</span><span className="knum font-bold accent">{calc.post_tax_yield_pct}%</span></div>
              <p className="muted text-[10.5px] leading-relaxed mt-2">{calc.note}</p>
            </div>
          )}
        </div>
      </section>

      <section className="mb-6">
        <SectionTitle title="On-demand peer compare" sub={`Other listed ${d.kind === "REIT" ? "REITs" : "InvITs"} with the same operating metrics.`} />
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  <th className="table-head text-left px-3 py-2.5">Trust</th>
                  <th className="table-head text-right px-2.5 py-2.5">Price</th>
                  <th className="table-head text-right px-2.5 py-2.5">Occupancy</th>
                  <th className="table-head text-right px-2.5 py-2.5">Cap rate</th>
                  <th className="table-head text-right px-2.5 py-2.5">NDCF yield</th>
                  <th className="table-head text-right px-3 py-2.5">Debt/GAV</th>
                </tr>
              </thead>
              <tbody>
                {(d.peers || []).map((p: any) => (
                  <tr key={p.symbol} className="table-row">
                    <td className="px-3 py-2.5">
                      <Link href={p.href} className="text-[12px] font-bold hover:underline">{p.symbol}</Link>
                      <div className="muted text-[10px]">{p.name}</div>
                    </td>
                    <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{inr(envNum(p.last))}</td>
                    <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{envNum(p.occupancy_pct) != null ? `${envNum(p.occupancy_pct)!.toFixed(1)}%` : "—"}</td>
                    <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{envNum(p.cap_rate_pct) != null ? `${envNum(p.cap_rate_pct)!.toFixed(1)}%` : "—"}</td>
                    <td className="px-2.5 py-2.5 text-right knum text-[11.5px] text-up">{envNum(p.ndcf_yield_pct) != null ? `${envNum(p.ndcf_yield_pct)!.toFixed(1)}%` : "—"}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{envNum(p.debt_gav_pct) != null ? `${envNum(p.debt_gav_pct)!.toFixed(1)}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="card p-4">
        <div className="text-[13px] font-bold mb-1">Source & honesty notes</div>
        {(d.source_notes || []).map((n: string) => (
          <p key={n} className="muted text-[11.5px] leading-relaxed mt-1">{n}</p>
        ))}
      </section>
    </div>
  );
}
