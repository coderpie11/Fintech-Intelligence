"use client";

import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, Skeleton } from "@/components/PageKit";
import Drawer from "@/components/Drawer";
import MetricTip, { type Tip } from "@/components/MetricTip";

const TIPS: Record<string, Tip> = {
  coupon: {
    meaning: "The contractual interest rate printed on the bond, paid on face value. It does not change when the market price changes.",
    formula: "Annual coupon ₹ = Face value × Coupon %",
    example: "A 7.18% G-Sec with ₹100 face value pays ₹7.18 a year, usually in two half-yearly instalments.",
  },
  frequency: {
    meaning: "How many coupon payments the bond makes in a year. Two means half-yearly, which is the Indian sovereign default.",
  },
  clean: {
    meaning: "The quoted price per ₹100 of face value, excluding interest that has already accrued since the last coupon date.",
  },
  dirty: {
    meaning: "The cash the buyer actually pays: clean price plus accrued interest. On settlement the buyer compensates the seller for the coupon period already earned.",
    formula: "Dirty price = Clean price + Accrued interest",
  },
  ytm: {
    meaning: "Yield to maturity: the single annual return you earn if you buy at this price and hold to maturity, reinvesting every coupon at the same rate.",
    formula: "Solve Price = Σ C ÷ (1+YTM)^t + F ÷ (1+YTM)^n",
    example: "A bond at ₹98 with a 7% coupon and 3 years left yields about 7.65%, not 7%.",
  },
  posttax: {
    meaning: "Yield after tax: coupon income is taxed at your slab, while the capital gain at maturity is taxed at 12.5% LTCG after a year. It is the return that actually reaches you.",
    formula: "Post-tax YTM = (Post-tax coupons + Post-tax gain) ÷ Price ÷ Years",
  },
  years: {
    meaning: "Time until the principal is repaid. Longer duration means the price reacts more sharply to a change in yields.",
  },
  rating: {
    meaning: "A credit rating agency's view of the issuer's ability to pay. A sovereign or AAA rating implies very low default risk; lower ratings must pay a higher yield.",
  },
};

const CATEGORIES: { key: string; label: string }[] = [
  { key: "ALL", label: "All Bonds" },
  { key: "G-SEC", label: "Sovereign G-Secs" },
  { key: "T-BILL", label: "RBI T-Bills" },
  { key: "SDL", label: "State SDLs" },
  { key: "CORPORATE", label: "AAA/AA+ Corporate NCDs" },
  { key: "FLOATING", label: "Tax-Free & Floating" },
];

type BondRow = {
  id: number; name: string; kind: string; category: string; issuer: string;
  coupon: Env; coupon_type: string; frequency: number;
  face_value: Env; price: Env; clean_price: Env; accrued_interest: Env;
  dirty_price: Env; ytm: Env; post_tax_ytm_pct: Env;
  maturity: Env; years_to_maturity: Env; coupon_per_year_per_unit: Env;
  rating: string; rating_agency?: string; taxable?: boolean;
  liquidity?: string; seniority?: string; note?: string; href: string;
};

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

function ratingTone(rating: string): string {
  if (/SOVEREIGN/i.test(rating)) return "chip-live";
  if (/AAA/.test(rating)) return "chip-live";
  if (/AA\+/.test(rating)) return "chip-warn";
  return "";
}

function YieldCurve({ curve }: { curve: any[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = curve.filter((c) => c.yield_pct != null);
  if (pts.length < 2) return null;
  const w = 760, h = 220, pad = 34;
  const ys = pts.map((p) => p.yield_pct as number);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (w - pad * 2);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.yield_pct)}`).join(" ");
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto"
           onMouseLeave={() => setHover(null)}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={pad} x2={w - pad} y1={pad + f * (h - pad * 2)}
                y2={pad + f * (h - pad * 2)}
                stroke="var(--line)" strokeDasharray="3 4" />
        ))}
        <path d={`${path} L${x(pts.length - 1)},${h - pad} L${x(0)},${h - pad} Z`}
              fill="color-mix(in srgb, var(--accent) 10%, transparent)" />
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2.2" />
        {pts.map((p, i) => (
          <g key={p.label}>
            <circle cx={x(i)} cy={y(p.yield_pct)} r={hover === i ? 5 : 3.2}
                    fill={hover === i ? "var(--accent)" : "var(--surface)"}
                    stroke="var(--accent)" strokeWidth="2" />
            <rect x={x(i) - 18} y={pad} width={36} height={h - pad * 2}
                  fill="transparent" onMouseEnter={() => setHover(i)} />
            <text x={x(i)} y={h - 10} textAnchor="middle" fontSize="10"
                  fill="var(--muted)">{p.label}</text>
          </g>
        ))}
        {hover != null && (
          <g>
            <text x={x(hover)} y={y(pts[hover].yield_pct) - 12} textAnchor="middle"
                  fontSize="11" fill="var(--ink)" fontWeight="700">
              {pts[hover].yield_pct.toFixed(2)}%
            </text>
          </g>
        )}
      </svg>
      <div className="muted text-[10px] text-center">
        Hover a point — par-yield curve, interpolated from sovereign/T-Bill/SDL anchors.
      </div>
    </div>
  );
}

function Cashflows({ bond, cashflows }: { bond: BondRow; cashflows: any[] }) {
  if (!cashflows?.length) {
    return <p className="muted text-[11.5px]">No future cash-flow dates are available for this security.</p>;
  }
  return (
    <div className="card overflow-hidden">
      <div className="max-h-[260px] overflow-auto">
        <table className="w-full min-w-[420px] border-collapse">
          <thead className="sticky top-0">
            <tr style={{ background: "var(--surface-2)" }}>
              <th className="table-head text-left px-3 py-2">Date</th>
              <th className="table-head text-right px-2.5 py-2">Coupon ₹</th>
              <th className="table-head text-right px-2.5 py-2">Principal ₹</th>
              <th className="table-head text-right px-3 py-2">Total ₹</th>
            </tr>
          </thead>
          <tbody>
            {cashflows.map((c, i) => (
              <tr key={`${c.date}-${i}`} className="table-row">
                <td className="px-3 py-1.5 text-[11px] knum">{fmtDate(c.date)}</td>
                <td className="px-2.5 py-1.5 text-right knum text-[11px]">{inr(c.coupon)}</td>
                <td className="px-2.5 py-1.5 text-right knum text-[11px]">{c.principal ? inr(c.principal) : "—"}</td>
                <td className="px-3 py-1.5 text-right knum text-[11px] font-semibold">{inr(c.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-3 py-2 muted text-[10px]"
           style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
        Schedule counted back from maturity at {bond.frequency}× a year. Amounts are per ₹100 face value.
      </div>
    </div>
  );
}

function BondDetail({
  bond, open, onClose,
}: { bond: BondRow | null; open: boolean; onClose: () => void }) {
  const [face, setFace] = useState("100");
  const [coupon, setCoupon] = useState("7.18");
  const [ytm, setYtm] = useState("7.18");
  const [years, setYears] = useState("7");
  const [days, setDays] = useState("45");
  const [freq, setFreq] = useState("2");
  const [slab, setSlab] = useState("30");
  const [callYears, setCallYears] = useState("3");
  const [cd, setCd] = useState<any>(null);
  const [cdErr, setCdErr] = useState<string | null>(null);

  const [fixedCoupon, setFixedCoupon] = useState("8");
  const [floatBase, setFloatBase] = useState("6.5");
  const [spread, setSpread] = useState("1.2");
  const [ffYears, setFfYears] = useState("5");
  const [path, setPath] = useState("0");
  const [ff, setFf] = useState<any>(null);
  const [ffErr, setFfErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    if (!bond) return;
    setFace(String(envNum(bond.face_value) ?? 100));
    setCoupon(String(envNum(bond.coupon) ?? 7.18));
    setYtm(String(envNum(bond.ytm) ?? 7.18));
    setYears(String(envNum(bond.years_to_maturity) ?? 7));
    setFreq(String(bond.frequency ?? 2));
    setFixedCoupon(String(envNum(bond.coupon) ?? 8));
    setFloatBase(String(Math.max((envNum(bond.coupon) ?? 8) - 1.2, 0.1)));
    setFfYears(String(Math.max(Math.round(envNum(bond.years_to_maturity) ?? 5), 1)));
    setCd(null); setFf(null); setDetail(null);
    getJSON(bond.href).then(setDetail).catch(() => {});
  }, [bond]);

  const runCd = async () => {
    setCdErr(null); setCd(null);
    try {
      const r = await postJSON("/bonds/calc/clean-dirty", {
        face: Number(face), coupon_pct: Number(coupon), ytm_pct: Number(ytm),
        years: Number(years), frequency: Number(freq),
        days_since_coupon: Number(days),
        tax_slab_pct: Number(slab), holding_years: Number(years),
        call_years: Number(callYears) || undefined, call_price: 100,
      });
      setCd(r);
    } catch (e: any) { setCdErr(String(e.message || e).slice(0, 180)); }
  };

  const runFf = async () => {
    setFfErr(null); setFf(null);
    try {
      const r = await postJSON("/bonds/calc/fixed-floating", {
        face: Number(face), fixed_coupon_pct: Number(fixedCoupon),
        floating_base_pct: Number(floatBase), spread_pct: Number(spread),
        years: Number(ffYears), rate_path_pct: Number(path),
      });
      setFf(r);
    } catch (e: any) { setFfErr(String(e.message || e).slice(0, 180)); }
  };

  if (!bond) return null;

  return (
    <Drawer open={open} onClose={onClose} width={880}
            eyebrow={`${bond.category} · ${bond.rating}`} title={bond.name}>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          <span className={`chip !text-[10px] ${ratingTone(bond.rating)}`}>{bond.rating}</span>
          <span className="chip !text-[10px]">{bond.coupon_type}</span>
          <span className="chip !text-[10px]">{bond.frequency}× / year</span>
          <span className="chip !text-[10px]">{bond.taxable === false ? "tax-free" : "taxable"}</span>
          <span className="chip !text-[10px]">Matures {bond.maturity.value ? fmtDate(bond.maturity.value) : "—"}</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {[
            ["Coupon", bond.coupon, (v: number) => `${v.toFixed(2)}%`],
            ["Clean price", bond.clean_price, inr],
            ["Accrued", bond.accrued_interest, (v: number) => inr(v, 4)],
            ["Dirty price", bond.dirty_price, (v: number) => inr(v, 4)],
            ["YTM", bond.ytm, (v: number) => `${v.toFixed(2)}%`],
            ["Post-tax YTM", bond.post_tax_ytm_pct, (v: number) => `${v.toFixed(2)}%`],
          ].map(([label, env, fmt]: any) => (
            <div key={label} className="rounded-md px-2.5 py-2"
                 style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
              <div className={`knum text-[13px] font-bold mt-0.5 ${label === "Post-tax YTM" ? "accent" : ""}`}>
                {envNum(env) != null ? fmt(envNum(env)) : "—"}
              </div>
            </div>
          ))}
        </div>

        <div>
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <div className="text-[13px] font-bold">Cash-flow schedule</div>
            <span className="muted text-[10px]">per ₹100 face value</span>
          </div>
          <Cashflows bond={bond} cashflows={detail?.cashflows || []} />
        </div>

        <div className="grid lg:grid-cols-2 gap-3">
          <div className="card p-3.5">
            <div className="text-[13px] font-bold">Clean vs dirty price &amp; post-tax YTM</div>
            <p className="muted text-[10.5px] mt-0.5 leading-relaxed">
              Accrued interest bridges the quoted clean price and the cash actually paid.
            </p>
            <div className="grid grid-cols-2 gap-2 mt-2.5">
              {[
                ["Face ₹", face, setFace], ["Coupon %", coupon, setCoupon],
                ["YTM %", ytm, setYtm], ["Years", years, setYears],
                ["Frequency", freq, setFreq],
                ["Days since coupon", days, setDays], ["Tax slab %", slab, setSlab],
                ["Call years", callYears, setCallYears],
              ].map(([l, v, set]: any) => (
                <label key={l} className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-wider">{l}</span>
                  <input value={v} onChange={(e) => set(e.target.value)} inputMode="decimal"
                         className="surface rounded-lg w-full mt-0.5 px-2 py-1.5 text-[11.5px] knum"
                         style={{ color: "var(--ink)" }} />
                </label>
              ))}
            </div>
            <button onClick={runCd} className="btn-primary w-full justify-center !py-1.5 !text-[11.5px] mt-2">
              Solve clean / dirty / post-tax
            </button>
            {cdErr && <p className="text-[11px] text-down mt-1">{cdErr}</p>}
            {cd && (
              <div className="mt-2 space-y-1 text-[11px]">
                {[
                  ["Accrued interest", inr(cd.accrued_interest, 4)],
                  ["Clean price", inr(cd.clean_price)],
                  ["Dirty price", inr(cd.dirty_price, 4)],
                  ["Post-tax YTM", `${cd.post_tax_ytm_pct}%`],
                  ["Post-tax total", inr(cd.post_tax_total_return)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="muted">{k}</span><span className="knum font-semibold">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card p-3.5">
            <div className="text-[13px] font-bold">Fixed vs floating coupon</div>
            <p className="muted text-[10.5px] mt-0.5 leading-relaxed">
              Floating coupons reset to base + spread. A rate path above zero shows a rising-rate scenario.
            </p>
            <div className="grid grid-cols-2 gap-2 mt-2.5">
              {[
                ["Fixed coupon %", fixedCoupon, setFixedCoupon],
                ["Floating base %", floatBase, setFloatBase],
                ["Spread %", spread, setSpread], ["Years", ffYears, setFfYears],
                ["Rate path %/yr", path, setPath],
              ].map(([l, v, set]: any) => (
                <label key={l} className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-wider">{l}</span>
                  <input value={v} onChange={(e) => set(e.target.value)} inputMode="decimal"
                         className="surface rounded-lg w-full mt-0.5 px-2 py-1.5 text-[11.5px] knum"
                         style={{ color: "var(--ink)" }} />
                </label>
              ))}
            </div>
            <button onClick={runFf} className="btn-primary w-full justify-center !py-1.5 !text-[11.5px] mt-2">
              Compare coupons
            </button>
            {ffErr && <p className="text-[11px] text-down mt-1">{ffErr}</p>}
            {ff && (
              <div className="mt-2 space-y-1 text-[11px]">
                <div className="flex justify-between"><span className="muted">Fixed interest</span><span className="knum">{inr(ff.fixed_total_interest)}</span></div>
                <div className="flex justify-between"><span className="muted">Floating interest</span><span className="knum">{inr(ff.floating_total_interest)}</span></div>
                <div className="flex justify-between"><span className="muted font-semibold">Winner</span><span className="knum font-black accent">{ff.winner}</span></div>
              </div>
            )}
          </div>
        </div>

        <p className="muted text-[10.5px] leading-relaxed">{bond.note}</p>
        <p className="muted text-[10px] leading-relaxed">{detail?.cashflow_note}</p>
      </div>
    </Drawer>
  );
}

export default function BondDesk() {
  const [data, setData] = useState<any>(null);
  const [curve, setCurve] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [kind, setKind] = useState("ALL");
  const [sel, setSel] = useState<BondRow | null>(null);

  useEffect(() => {
    setErr(null);
    getJSON("/bonds").then(setData).catch((e) => setErr(String(e.message || e)));
  }, []);
  useEffect(() => {
    getJSON("/bonds/curve/yields").then(setCurve).catch(() => {});
  }, []);

  const all: BondRow[] = data?.bonds || [];
  const rows = useMemo(
    () => (kind === "ALL" ? all : all.filter((b) => b.kind === kind)),
    [all, kind],
  );

  const counts = useMemo(() => {
    const out: Record<string, number> = { ALL: all.length };
    for (const b of all) out[b.kind] = (out[b.kind] || 0) + 1;
    return out;
  }, [all]);

  return (
    <div className="mx-auto max-w-[1680px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Bonds & debt · fixed income"
        title="Bonds & Debt Hub"
        sub="Twenty real G-Secs, T-Bills, SDLs, floating-rate and corporate bonds with credit ratings, an India par-yield curve, clean vs dirty pricing, post-tax YTM and a full cash-flow schedule."
        right={<RefreshButton stage="bonds" />}
      />

      {err && <ErrorBox message={err} stage="bonds" />}
      {!data && !err && <Skeleton rows={8} />}

      {data && (
        <>
          <div className="grid lg:grid-cols-[1fr_360px] gap-3 mb-5">
            <div className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="text-[13px] font-bold">India sovereign yield curve</div>
                  <div className="muted text-[10.5px]">3M → 30Y · par yields</div>
                </div>
                {curve?.curve && (
                  <div className="flex gap-1.5">
                    {curve.curve.filter((c: any) => c.yield_pct != null).slice(-3).map((c: any) => (
                      <span key={c.label} className="chip !text-[9px]">
                        {c.label} {c.yield_pct.toFixed(2)}%
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {curve?.curve ? <YieldCurve curve={curve.curve} /> : <Skeleton rows={3} />}
            </div>
            <div className="card p-4">
              <div className="text-[13px] font-bold mb-1">How to read this desk</div>
              <p className="muted text-[11.5px] leading-relaxed">
                Coupon is the contractual interest. Price and YTM are two views of the
                same cash-flow stream: when price falls, yield rises. Corporate bonds
                add credit risk, so an AA+ NBFC pays more than a sovereign. Dirty price
                is the cash you actually pay, including accrued interest.
              </p>
              <div className="mt-3 rounded-md px-2.5 py-2 text-[10.5px] muted"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                {curve?.note}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5 mb-3">
            {CATEGORIES.map((c) => (
              <button key={c.key} onClick={() => setKind(c.key)}
                      className={`chip !text-[11px] ${kind === c.key ? "chip-active" : ""}`}>
                {c.label}
                <span className={`knum ml-1.5 ${kind === c.key ? "" : "muted"}`}>{counts[c.key] ?? 0}</span>
              </button>
            ))}
            <span className="muted text-[11.5px] ml-auto">{rows.length} securities</span>
          </div>

          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1240px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5 min-w-[250px]">Security &amp; issuer</th>
                    <th className="table-head text-left px-2.5 py-2.5">Type</th>
                    <th className="table-head text-left px-2.5 py-2.5">
                      <MetricTip label="Rating" tip={TIPS.rating}>Rating</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Coupon" tip={TIPS.coupon}>Coupon</MetricTip>
                    </th>
                    <th className="table-head text-center px-2.5 py-2.5">
                      <MetricTip label="Freq" tip={TIPS.frequency}>Freq</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Clean" tip={TIPS.clean}>Clean</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Dirty" tip={TIPS.dirty}>Dirty</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="YTM" tip={TIPS.ytm}>YTM</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Post-tax YTM" tip={TIPS.posttax}>Post-tax YTM</MetricTip>
                    </th>
                    <th className="table-head text-right px-3 py-2.5">Maturity</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((b) => (
                    <tr key={b.id} className="table-row cursor-pointer"
                        onClick={() => setSel(b)}>
                      <td className="px-3 py-2.5 min-w-[260px]">
                        <div className="text-[12px] font-bold">{b.name}</div>
                        <div className="muted text-[10.5px]">{b.issuer}</div>
                      </td>
                      <td className="px-2.5 py-2.5"><span className="chip !text-[9px]">{b.kind}</span></td>
                      <td className="px-2.5 py-2.5">
                        <span className={`chip !text-[9px] ${ratingTone(b.rating)}`}>{b.rating}</span>
                      </td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">
                        {envNum(b.coupon) != null ? `${envNum(b.coupon)!.toFixed(2)}%` : "zero"}
                      </td>
                      <td className="px-2.5 py-2.5 text-center knum text-[11px]">{b.frequency}×</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{envNum(b.clean_price) != null ? inr(envNum(b.clean_price)) : "—"}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{envNum(b.dirty_price) != null ? inr(envNum(b.dirty_price), 4) : "—"}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px] font-semibold text-up">
                        {envNum(b.ytm) != null ? `${envNum(b.ytm)!.toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px] font-semibold accent">
                        {envNum(b.post_tax_ytm_pct) != null ? `${envNum(b.post_tax_ytm_pct)!.toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[11px]">{b.maturity.value ? fmtDate(b.maturity.value) : "—"}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={10} className="px-4 py-8 muted text-[12.5px] text-center">No bonds in this category.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-3.5 py-2.5 muted text-[10.5px]"
                 style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
              Click any bond to open its cash-flow schedule and the two prefilled calculators. Prices and YTMs are indicative, not dealer quotes.
            </div>
          </div>
        </>
      )}

      <BondDetail bond={sel} open={!!sel} onClose={() => setSel(null)} />
    </div>
  );
}
