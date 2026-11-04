"use client";

import Link from "next/link";
import { useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { PageHeader } from "@/components/PageKit";

/* ------------------------------------------------------------------ shared */

function Field({
  label, value, onChange, suffix, step = "any",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  step?: string;
}) {
  return (
    <label className="block">
      <span className="muted text-[9.5px] font-bold uppercase tracking-wider">{label}</span>
      <div className="flex items-center gap-1 mt-1">
        <input
          type="number"
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="surface rounded-lg w-full px-2.5 py-1.5 text-[12px] knum"
          style={{ color: "var(--ink)" }}
        />
        {suffix && <span className="muted text-[10px] shrink-0">{suffix}</span>}
      </div>
    </label>
  );
}

function RunButton({ onClick, busy, children }: {
  onClick: () => void; busy: boolean; children?: React.ReactNode;
}) {
  return (
    <button onClick={onClick} disabled={busy}
            className="btn-primary w-full justify-center !py-2 !text-[12px] mt-3 disabled:opacity-60">
      {busy ? "Calculating…" : children || "Calculate"}
    </button>
  );
}

function Result({ title, rows, note }: {
  title: string;
  rows: { label: string; value: string; tone?: "up" | "down" }[];
  note?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-[13px] font-bold mb-2">{title}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-2 text-[11.5px]">
            <span className="muted">{r.label}</span>
            <span className={`knum font-bold text-right ${r.tone === "up" ? "text-up" : r.tone === "down" ? "text-down" : ""}`}
                  style={r.tone ? undefined : { color: "var(--ink)" }}>
              {r.value}
            </span>
          </div>
        ))}
      </div>
      {note && <p className="muted text-[10px] leading-relaxed mt-2.5">{note}</p>}
    </div>
  );
}

function errText(e: any): string {
  return String(e?.message || e).slice(0, 180);
}

const money = (v: number | null | undefined, dec = 2) =>
  v == null || Number.isNaN(v) ? "—" : inr(v, dec);
const pctv = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : `${v.toFixed(2)}%`;

/* ------------------------------------------------------------------ equity */

function EquityTab() {
  const [fcff, setFcff] = useState("2500");
  const [growth, setGrowth] = useState("12");
  const [terminal, setTerminal] = useState("4");
  const [wacc, setWacc] = useState("11");
  const [netCash, setNetCash] = useState("500");
  const [shares, setShares] = useState("100");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await postJSON("/calc/dcf", {
        fcff_millions: Number(fcff) * 10,
        growth_pct: Number(growth),
        terminal_pct: Number(terminal),
        wacc_pct: Number(wacc),
        net_cash_millions: Number(netCash) * 10,
        shares_millions: Number(shares) * 10,
        years: 5,
      }));
    } catch (e: any) { setErr(errText(e)); }
    setBusy(false);
  };

  const [buy, setBuy] = useState("100000");
  const [sell, setSell] = useState("110000");
  const [charges, setCharges] = useState<any>(null);
  const [cErr, setCErr] = useState<string | null>(null);

  const runCharges = async () => {
    setCErr(null); setCharges(null);
    try {
      setCharges(await getJSON(`/calc/net-in-pocket?buy_value=${Number(buy)}&sell_value=${Number(sell)}`));
    } catch (e: any) { setCErr(errText(e)); }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Two-stage DCF</div>
        <p className="muted text-[11px] mt-0.5 mb-3">
          FCFF and net cash in ₹ crore; the engine works in ₹ million internally.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Field label="FCFF (₹ crore)" value={fcff} onChange={setFcff} />
          <Field label="Growth %" value={growth} onChange={setGrowth} />
          <Field label="Terminal growth %" value={terminal} onChange={setTerminal} />
          <Field label="WACC %" value={wacc} onChange={setWacc} />
          <Field label="Net cash (₹ crore)" value={netCash} onChange={setNetCash} />
          <Field label="Shares (₹ crore)" value={shares} onChange={setShares} />
        </div>
        <RunButton onClick={run} busy={busy}>Run DCF</RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
        {res?.error && <p className="text-[11px] text-down mt-2">{res.error}</p>}
        {res && !res.error && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">Per-share value</div>
              <div className="knum text-[22px] font-black mt-1">{money(res.per_share)}</div>
            </div>
            <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">Equity value</div>
              <div className="knum text-[16px] font-black mt-1">
                {money((res.equity_value_mn || 0) * 1e6 / 1e7)} Cr
              </div>
            </div>
            <div className="muted text-[10px] col-span-2">
              PV explicit {money((res.pv_explicit || 0) * 1e6 / 1e7)} Cr · PV terminal{" "}
              {money((res.pv_terminal || 0) * 1e6 / 1e7)} Cr · {res.assumptions?.years} years
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="card p-4">
          <div className="text-[13px] font-bold">Delivery trade charges</div>
          <p className="muted text-[11px] mt-0.5 mb-3">
            STT, exchange, SEBI, stamp, DP and GST on a CNC equity round trip.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Buy value" value={buy} onChange={setBuy} suffix="₹" />
            <Field label="Sell value" value={sell} onChange={setSell} suffix="₹" />
          </div>
          <RunButton onClick={runCharges} busy={false}>Compute charges</RunButton>
          {cErr && <p className="text-[11px] text-down mt-2">{cErr}</p>}
          {charges && (
            <div className="mt-3">
              <Result
                title="Net in pocket"
                rows={[
                  { label: "Gross P&L", value: money(charges.gross_pnl), tone: (charges.gross_pnl || 0) >= 0 ? "up" : "down" },
                  { label: "Total charges", value: money(charges.total_charges) },
                  { label: "Net in pocket", value: money(charges.net_in_pocket), tone: (charges.net_in_pocket || 0) >= 0 ? "up" : "down" },
                  { label: "Charges %", value: `${(charges.charges_pct_of_turnover || 0).toFixed(3)}%` },
                ]}
                note={charges.disclaimer}
              />
            </div>
          )}
        </div>
        <div className="card p-4 muted text-[11.5px] leading-relaxed">
          Need company defaults? Open any stock and use the in-page DCF with its
          reported cash flow, net cash and share count pre-filled.{" "}
          <Link href="/stocks" className="accent font-semibold">Browse equities →</Link>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- F&O */

function FnoTab() {
  const [s, setS] = useState("23800");
  const [k, setK] = useState("24000");
  const [t, setT] = useState("0.08");
  const [r, setR] = useState("6.5");
  const [sig, setSig] = useState("14");
  const [q, setQ] = useState("1.2");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await getJSON(
        `/calc/bsm?S=${Number(s)}&K=${Number(k)}&T=${Number(t)}` +
        `&r=${Number(r) / 100}&sigma=${Number(sig) / 100}&q=${Number(q) / 100}`));
    } catch (e: any) { setErr(errText(e)); }
    setBusy(false);
  };

  return (
    <div className="grid lg:grid-cols-[420px_1fr] gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Black-Scholes-Merton</div>
        <p className="muted text-[11px] mt-0.5 mb-3">
          European option on a dividend-yielding underlying. T in years.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Spot" value={s} onChange={setS} />
          <Field label="Strike" value={k} onChange={setK} />
          <Field label="Time (years)" value={t} onChange={setT} />
          <Field label="Risk-free %" value={r} onChange={setR} />
          <Field label="Volatility %" value={sig} onChange={setSig} />
          <Field label="Dividend yield %" value={q} onChange={setQ} />
        </div>
        <RunButton onClick={run} busy={busy}>Price the option</RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
      </div>

      <div className="space-y-3">
        {res ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Call premium</div>
                <div className="knum text-[24px] font-black mt-1">{money(res.call)}</div>
                <div className="muted text-[10px] mt-0.5">POP {pctv(res.pop_call)}</div>
              </div>
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Put premium</div>
                <div className="knum text-[24px] font-black mt-1">{money(res.put)}</div>
                <div className="muted text-[10px] mt-0.5">POP {pctv(res.pop_put)}</div>
              </div>
            </div>
            <Result
              title="Greeks (per unit)"
              rows={[
                { label: "Delta call", value: String(res.delta_call) },
                { label: "Delta put", value: String(res.delta_put) },
                { label: "Gamma", value: String(res.gamma) },
                { label: "Theta call / day", value: money(res.theta_call, 4) },
                { label: "Theta put / day", value: money(res.theta_put, 4) },
                { label: "Vega / 1% vol", value: money(res.vega, 4) },
              ]}
              note="Model prices use the inputs above; live chains carry bid-ask, IV skew and early-exercise effects that this European model ignores."
            />
            <div className="card p-4 muted text-[11.5px] leading-relaxed">
              Want the live chain? Open a stock with F&amp;O and switch to its
              Derivatives tab for real strikes and OI.{" "}
              <Link href="/stocks/RELIANCE" className="accent font-semibold">RELIANCE F&amp;O →</Link>
            </div>
          </>
        ) : (
          <div className="card p-6 muted text-[12px]">Enter inputs and price the option.</div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- MF */

function MfTab() {
  const [monthly, setMonthly] = useState("10000");
  const [years, setYears] = useState("10");
  const [ret, setRet] = useState("12");
  const [sip, setSip] = useState<any>(null);

  const [corpus, setCorpus] = useState("5000000");
  const [withdrawal, setWithdrawal] = useState("40000");
  const [swpRet, setSwpRet] = useState("8");
  const [swp, setSwp] = useState<any>(null);

  const [gain, setGain] = useState("300000");
  const [used, setUsed] = useState("0");
  const [ltcg, setLtcg] = useState<any>(null);

  const [amount, setAmount] = useState("1000000");
  const [feeYears, setFeeYears] = useState("10");
  const [gross, setGross] = useState("11");
  const [lowCost, setLowCost] = useState("0.20");
  const [highCost, setHighCost] = useState("1.20");
  const [drag, setDrag] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setErr(null);
    try { await fn(); } catch (e: any) { setErr(errText(e)); }
  };

  return (
    <div className="space-y-3">
      {err && <p className="text-[11px] text-down">{err}</p>}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="text-[13px] font-bold">SIP future value</div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <Field label="Monthly" value={monthly} onChange={setMonthly} suffix="₹" />
            <Field label="Years" value={years} onChange={setYears} />
            <Field label="Return %" value={ret} onChange={setRet} />
          </div>
          <RunButton busy={false}
                     onClick={() => run(async () => setSip(await getJSON(
                       `/calc/sip?monthly=${Number(monthly)}&years=${Number(years)}&annual_return_pct=${Number(ret)}`)))}>
            Project SIP
          </RunButton>
          {sip && !sip.error && (
            <div className="grid grid-cols-3 gap-2 mt-3">
              {[["Invested", sip.invested], ["Future value", sip.future_value], ["Gain", sip.gain]].map(([l, v]: any) => (
                <div key={l} className="rounded-lg p-2.5" style={{ background: "var(--surface-2)" }}>
                  <div className="muted text-[8.5px] font-bold uppercase tracking-wider">{l}</div>
                  <div className="knum text-[13px] font-black mt-0.5">{money(v)}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">SWP duration</div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <Field label="Corpus" value={corpus} onChange={setCorpus} suffix="₹" />
            <Field label="Monthly draw" value={withdrawal} onChange={setWithdrawal} suffix="₹" />
            <Field label="Return %" value={swpRet} onChange={setSwpRet} />
          </div>
          <RunButton busy={false}
                     onClick={() => run(async () => setSwp(await postJSON("/calc/swp", {
                       corpus: Number(corpus), monthly_withdrawal: Number(withdrawal),
                       annual_return_pct: Number(swpRet),
                     })))}>
            Test withdrawal plan
          </RunButton>
          {swp && !swp.error && (
            <Result title="How long the corpus lasts" rows={[
              { label: "Months", value: swp.perpetual ? "Perpetual" : String(swp.months_lasted) },
              { label: "Years", value: String(swp.years_lasted) },
              { label: "Balance left", value: money(swp.balance_left) },
            ]} note="Deterministic monthly compounding at the stated return; real returns vary." />
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">LTCG harvest window</div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Unrealised gain" value={gain} onChange={setGain} suffix="₹" />
            <Field label="Exemption already used" value={used} onChange={setUsed} suffix="₹" />
          </div>
          <RunButton busy={false}
                     onClick={() => run(async () => setLtcg(await postJSON("/calc/ltcg", {
                       unrealized_gain: Number(gain), used_exemption: Number(used),
                     })))}>
            Compute tax
          </RunButton>
          {ltcg && !ltcg.error && (
            <Result title="Listed-equity LTCG (12.5%)" rows={[
              { label: "Exemption left", value: money(ltcg.exemption_left) },
              { label: "Taxable gain", value: money(ltcg.taxable_gain) },
              { label: "Tax", value: money(ltcg.tax) },
              { label: "Post-tax gain", value: money(ltcg.post_tax_gain), tone: "up" },
            ]} note="FY2025-26 rules: ₹1.25 lakh annual exemption, 12.5% above it. A model, not tax advice." />
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">MF vs ETF fee drag</div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Amount" value={amount} onChange={setAmount} suffix="₹" />
            <Field label="Years" value={feeYears} onChange={setFeeYears} />
            <Field label="Gross return %" value={gross} onChange={setGross} />
            <Field label="Low TER %" value={lowCost} onChange={setLowCost} />
            <Field label="High TER %" value={highCost} onChange={setHighCost} />
          </div>
          <RunButton busy={false}
                     onClick={() => run(async () => setDrag(await postJSON("/calc/fee-drag", {
                       amount: Number(amount), years: Number(feeYears),
                       annual_return_pct: Number(gross),
                       low_cost_pct: Number(lowCost), high_cost_pct: Number(highCost),
                     })))}>
            Compare costs
          </RunButton>
          {drag && !drag.error && (
            <Result title="Same gross return, different expense ratio" rows={[
              { label: `At ${drag.low_cost_pct}% TER`, value: money(drag.low_cost_value) },
              { label: `At ${drag.high_cost_pct}% TER`, value: money(drag.high_cost_value) },
              { label: "Difference", value: money(drag.difference), tone: "down" },
            ]} note={drag.note} />
          )}
        </div>
      </div>
      <div className="card p-4 muted text-[11.5px] leading-relaxed">
        Scheme-level backtests, SWP and LTCG with real NAV history live on each
        fund page. <Link href="/mutual-funds" className="accent font-semibold">Open mutual funds →</Link>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- bonds */

function BondTab() {
  const [face, setFace] = useState("100");
  const [coupon, setCoupon] = useState("7.18");
  const [ytm, setYtm] = useState("7.18");
  const [years, setYears] = useState("7");
  const [freq, setFreq] = useState("2");
  const [days, setDays] = useState("45");
  const [slab, setSlab] = useState("30");
  const [hold, setHold] = useState("5");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const [price, setPrice] = useState("98.5");
  const [sCoupon, setSCoupon] = useState("7.18");
  const [sFace, setSFace] = useState("100");
  const [sYears, setSYears] = useState("7");
  const [solved, setSolved] = useState<any>(null);

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Clean / dirty price &amp; post-tax yield</div>
        <div className="grid grid-cols-3 gap-2 mt-3">
          <Field label="Face" value={face} onChange={setFace} />
          <Field label="Coupon %" value={coupon} onChange={setCoupon} />
          <Field label="YTM %" value={ytm} onChange={setYtm} />
          <Field label="Years" value={years} onChange={setYears} />
          <Field label="Frequency" value={freq} onChange={setFreq} step="1" />
          <Field label="Days since coupon" value={days} onChange={setDays} step="1" />
          <Field label="Tax slab %" value={slab} onChange={setSlab} />
          <Field label="Holding years" value={hold} onChange={setHold} />
        </div>
        <RunButton busy={false}
                   onClick={async () => {
                     setErr(null); setRes(null);
                     try {
                       setRes(await postJSON("/bonds/calc/clean-dirty", {
                         face: Number(face), coupon_pct: Number(coupon),
                         ytm_pct: Number(ytm), years: Number(years),
                         frequency: Number(freq), days_since_coupon: Number(days),
                         tax_slab_pct: Number(slab), holding_years: Number(hold),
                       }));
                     } catch (e: any) { setErr(errText(e)); }
                   }}>
          Price the bond
        </RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
        {res && !res.error && (
          <div className="mt-3">
            <Result title="Price and income" rows={[
              { label: "Clean price", value: money(res.clean_price, 4) },
              { label: "Dirty price", value: money(res.dirty_price, 4) },
              { label: "Accrued interest", value: money(res.accrued_interest, 4) },
              { label: "Coupon income", value: money(res.coupon_income) },
              { label: "Post-tax income", value: money(res.post_tax_income) },
              { label: "Post-tax YTM", value: pctv(res.post_tax_ytm_pct) },
            ]} note={res.note} />
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="card p-4">
          <div className="text-[13px] font-bold">YTM solver</div>
          <p className="muted text-[11px] mt-0.5 mb-3">Find the yield implied by a traded price.</p>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Price" value={price} onChange={setPrice} />
            <Field label="Coupon %" value={sCoupon} onChange={setSCoupon} />
            <Field label="Face" value={sFace} onChange={setSFace} />
            <Field label="Years" value={sYears} onChange={setSYears} />
          </div>
          <RunButton busy={false}
                     onClick={async () => {
                       setSolved(null);
                       try {
                         setSolved(await getJSON(
                           `/bonds/calc/ytm?price=${Number(price)}&coupon_pct=${Number(sCoupon)}` +
                           `&face=${Number(sFace)}&years=${Number(sYears)}`));
                       } catch (e: any) { setErr(errText(e)); }
                     }}>
            Solve YTM
          </RunButton>
          {solved && !solved.error && (
            <div className="mt-3 rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">Yield to maturity</div>
              <div className="knum text-[26px] font-black mt-1">{pctv(solved.yield_to_maturity_pct)}</div>
              <div className="muted text-[10px] mt-1">
                Annual coupon ₹{solved.coupon?.toFixed(2)} · {solved.years} years
              </div>
            </div>
          )}
        </div>
        <div className="card p-4 muted text-[11.5px] leading-relaxed">
          The live G-Sec curve and each bond&apos;s cash-flow schedule are on the
          bond desk. <Link href="/bonds" className="accent font-semibold">Open bonds →</Link>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- gold */

function GoldTab() {
  const [grams, setGrams] = useState("100");
  const [years, setYears] = useState("8");
  const [cagr, setCagr] = useState("9");
  const [making, setMaking] = useState("12");
  const [slab, setSlab] = useState("30");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  return (
    <div className="grid lg:grid-cols-[380px_1fr] gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Physical vs ETF vs SGB</div>
        <p className="muted text-[11px] mt-0.5 mb-3">
          Same gold CAGR for all three; the difference is making charges, GST,
          TER and the SGB coupon.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Grams" value={grams} onChange={setGrams} />
          <Field label="Years" value={years} onChange={setYears} />
          <Field label="Gold CAGR %" value={cagr} onChange={setCagr} />
          <Field label="Making charge %" value={making} onChange={setMaking} />
          <Field label="Tax slab %" value={slab} onChange={setSlab} />
        </div>
        <RunButton busy={false}
                   onClick={async () => {
                     setErr(null); setRes(null);
                     try {
                       setRes(await postJSON("/commodities/calc/wealth", {
                         grams: Number(grams), years: Number(years),
                         gold_cagr_pct: Number(cagr),
                         making_charge_pct: Number(making),
                         tax_slab_pct: Number(slab),
                       }));
                     } catch (e: any) { setErr(errText(e)); }
                   }}>
          Compare wealth
        </RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
      </div>

      <div className="card p-4">
        <div className="text-[13px] font-bold mb-2">Outcome after fees and tax</div>
        {!res && <p className="muted text-[12px]">Run the comparison to see the three vehicles side by side.</p>}
        {res && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-[11.5px]">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  <th className="table-head text-left px-2.5 py-2">Vehicle</th>
                  <th className="table-head text-right px-2.5 py-2">Outlay</th>
                  <th className="table-head text-right px-2.5 py-2">Fees / tax</th>
                  <th className="table-head text-right px-2.5 py-2">End value</th>
                  <th className="table-head text-right px-2.5 py-2">CAGR</th>
                </tr>
              </thead>
              <tbody>
                {res.rows?.map((r: any) => (
                  <tr key={r.vehicle} className="table-row">
                    <td className="px-2.5 py-2 font-semibold">{r.vehicle}</td>
                    <td className="px-2.5 py-2 text-right knum">{money(r.outlay)}</td>
                    <td className="px-2.5 py-2 text-right knum text-down">{money(r.fees)}</td>
                    <td className="px-2.5 py-2 text-right knum font-bold">{money(r.end_value)}</td>
                    <td className={`px-2.5 py-2 text-right knum font-bold ${r.effective_cagr_pct >= 0 ? "text-up" : "text-down"}`}>
                      {pct(r.effective_cagr_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted text-[10.5px] mt-2 leading-relaxed">{res.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- REIT */

const TRUSTS = ["EMBASSY", "BIRET", "MINDSPACE", "NXST", "IRBINVIT", "INDIGRID", "PGINVIT"];

function ReitTab() {
  const [symbol, setSymbol] = useState("EMBASSY");
  const [units, setUnits] = useState("1000");
  const [price, setPrice] = useState("400");
  const [dist, setDist] = useState("24");
  const [interest, setInterest] = useState("45");
  const [dividend, setDividend] = useState("30");
  const [amort, setAmort] = useState("20");
  const [other, setOther] = useState("5");
  const [slab, setSlab] = useState("30");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  return (
    <div className="grid lg:grid-cols-[400px_1fr] gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Post-tax distribution yield</div>
        <p className="muted text-[11px] mt-0.5 mb-3">
          Interest, dividend and other income are taxed at slab; amortisation is
          a return of capital.
        </p>
        <label className="block mb-2">
          <span className="muted text-[9.5px] font-bold uppercase tracking-wider">Trust</span>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
                  className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[12px]"
                  style={{ color: "var(--ink)" }}>
            {TRUSTS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Units" value={units} onChange={setUnits} />
          <Field label="Price / unit" value={price} onChange={setPrice} suffix="₹" />
          <Field label="Distribution / unit" value={dist} onChange={setDist} suffix="₹" />
          <Field label="Tax slab %" value={slab} onChange={setSlab} />
          <Field label="Interest %" value={interest} onChange={setInterest} />
          <Field label="Dividend %" value={dividend} onChange={setDividend} />
          <Field label="Amortisation %" value={amort} onChange={setAmort} />
          <Field label="Other %" value={other} onChange={setOther} />
        </div>
        <RunButton busy={false}
                   onClick={async () => {
                     setErr(null); setRes(null);
                     try {
                       setRes(await postJSON(`/reits/${symbol}/distribution-calculator`, {
                         units: Number(units), price_per_unit: Number(price),
                         distribution_per_unit: Number(dist),
                         interest_pct: Number(interest), dividend_pct: Number(dividend),
                         amortization_pct: Number(amort), other_pct: Number(other),
                         tax_slab_pct: Number(slab),
                       }));
                     } catch (e: any) { setErr(errText(e)); }
                   }}>
          Compute post-tax yield
        </RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
      </div>

      <div className="space-y-3">
        {res && !res.error ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Pre-tax yield</div>
                <div className="knum text-[24px] font-black mt-1">{pctv(res.pre_tax_yield_pct)}</div>
              </div>
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Post-tax yield</div>
                <div className="knum text-[24px] font-black mt-1 text-up">{pctv(res.post_tax_yield_pct)}</div>
              </div>
            </div>
            <Result title={`${res.symbol} distribution split`} rows={[
              { label: "Total distribution", value: money(res.total_distribution) },
              { label: "Interest", value: money(res.split?.interest) },
              { label: "Dividend", value: money(res.split?.dividend) },
              { label: "Amortisation (tax-free now)", value: money(res.split?.amortization) },
              { label: "Other income", value: money(res.split?.other) },
              { label: "Tax at slab", value: money(res.tax_at_slab), tone: "down" },
              { label: "Post-tax distribution", value: money(res.post_tax_distribution), tone: "up" },
            ]} note={res.note} />
          </>
        ) : (
          <div className="card p-6 muted text-[12px]">
            Pick a trust and run the calculator. Live prices and distribution
            splits are pre-filled on each trust page.
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------- corporate actions */

function CorpTab() {
  const [dps, setDps] = useState("10");
  const [shares, setShares] = useState("1000");
  const [slab, setSlab] = useState("30");
  const [div, setDiv] = useState<any>(null);

  const [splitShares, setSplitShares] = useState("100");
  const [oldFv, setOldFv] = useState("10");
  const [newFv, setNewFv] = useState("2");
  const [pre, setPre] = useState("500");
  const [split, setSplit] = useState<any>(null);

  const [bShares, setBShares] = useState("100");
  const [num, setNum] = useState("1");
  const [den, setDen] = useState("1");
  const [cost, setCost] = useState("200");
  const [cmp, setCmp] = useState("500");
  const [sold, setSold] = useState("0");
  const [bSlab, setBSlab] = useState("30");
  const [bonus, setBonus] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      {err && <p className="text-[11px] text-down">{err}</p>}
      <div className="grid lg:grid-cols-3 gap-3">
        <div className="card p-4">
          <div className="text-[13px] font-bold">Dividend net in hand</div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Dividend / share" value={dps} onChange={setDps} suffix="₹" />
            <Field label="Shares" value={shares} onChange={setShares} step="1" />
            <Field label="Tax slab %" value={slab} onChange={setSlab} />
          </div>
          <RunButton busy={false}
                     onClick={async () => {
                       setErr(null);
                       try { setDiv(await postJSON("/events/calc/dividend", {
                         dividend_per_share: Number(dps), shares: Number(shares),
                         tax_slab_pct: Number(slab),
                       })); } catch (e: any) { setErr(errText(e)); }
                     }}>
            Compute dividend
          </RunButton>
          {div && !div.error && (
            <Result title="Dividend outcome" rows={[
              { label: "Gross", value: money(div.gross_dividend) },
              { label: "TDS 10%", value: money(div.tds_10pct) },
              { label: "Tax at slab", value: money(div.estimated_tax_at_slab) },
              { label: "Net in hand", value: money(div.net_in_hand), tone: "up" },
            ]} note={div.note} />
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">Stock split</div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Shares held" value={splitShares} onChange={setSplitShares} step="1" />
            <Field label="Old face value" value={oldFv} onChange={setOldFv} />
            <Field label="New face value" value={newFv} onChange={setNewFv} />
            <Field label="Pre-split price" value={pre} onChange={setPre} suffix="₹" />
          </div>
          <RunButton busy={false}
                     onClick={async () => {
                       setErr(null);
                       try { setSplit(await postJSON("/events/calc/split", {
                         shares: Number(splitShares), old_face_value: Number(oldFv),
                         new_face_value: Number(newFv), pre_split_price: Number(pre),
                       })); } catch (e: any) { setErr(errText(e)); }
                     }}>
            Compute split
          </RunButton>
          {split && !split.error && (
            <Result title={`${split.split_ratio} split`} rows={[
              { label: "New shares", value: String(split.new_shares) },
              { label: "Theoretical price", value: money(split.theoretical_post_split_price) },
              { label: "Pre value", value: money(split.pre_value) },
              { label: "Post value", value: money(split.post_value_at_theoretical) },
            ]} note={split.note} />
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">Bonus shares &amp; FIFO tax</div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Original shares" value={bShares} onChange={setBShares} step="1" />
            <Field label="Bonus ratio (num)" value={num} onChange={setNum} step="1" />
            <Field label="Bonus ratio (den)" value={den} onChange={setDen} step="1" />
            <Field label="Cost / share" value={cost} onChange={setCost} suffix="₹" />
            <Field label="Current price" value={cmp} onChange={setCmp} suffix="₹" />
            <Field label="Shares sold" value={sold} onChange={setSold} step="1" />
            <Field label="Tax slab %" value={bSlab} onChange={setBSlab} />
          </div>
          <RunButton busy={false}
                     onClick={async () => {
                       setErr(null);
                       try { setBonus(await postJSON("/events/calc/bonus", {
                         original_shares: Number(bShares), bonus_ratio_num: Number(num),
                         bonus_ratio_den: Number(den),
                         original_cost_per_share: Number(cost),
                         current_price: Number(cmp), shares_sold: Number(sold),
                         tax_slab_pct: Number(bSlab),
                       })); } catch (e: any) { setErr(errText(e)); }
                     }}>
            Compute bonus
          </RunButton>
          {bonus && !bonus.error && (
            <Result title="Bonus outcome" rows={[
              { label: "Bonus shares", value: String(bonus.bonus_shares) },
              { label: "Total shares", value: String(bonus.total_shares) },
              { label: "New cost / share", value: money(bonus.new_cost_per_share) },
              { label: "Estimated tax 20%", value: money(bonus.estimated_tax_20pct), tone: "down" },
            ]} note={bonus.note} />
          )}
        </div>
      </div>
      <div className="card p-4 muted text-[11.5px] leading-relaxed">
        Buyback and demerger models, plus the real corporate-action calendar,
        live on the events desk.{" "}
        <Link href="/events" className="accent font-semibold">Open corporate events →</Link>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- page */

const TABS = [
  { key: "equity", label: "Equity & DCF" },
  { key: "fno", label: "F&O & Black-Scholes" },
  { key: "mf", label: "MF SIP / SWP / LTCG" },
  { key: "bonds", label: "Bonds YTM & Dirty Price" },
  { key: "gold", label: "Gold vs SGB" },
  { key: "reit", label: "REIT Post-Tax Yield" },
  { key: "corp", label: "Corporate Actions" },
];

export default function CalculatorsPage() {
  const [tab, setTab] = useState("equity");

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Calculators · every model on one page"
        title="Calculators"
        sub="DCF, Black-Scholes, SIP/SWP, LTCG, bond clean and dirty price, gold vs SGB, REIT post-tax yield and corporate-action maths — all computed by the platform's own engines, with the inputs visible."
        right={<Link href="/learn" className="btn-secondary !px-3.5 !py-2 !text-[12.5px]">Learn the formulas →</Link>}
      />

      <div className="card p-1.5 mb-4 overflow-x-auto">
        <div className="flex items-center gap-1 min-w-max">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              aria-pressed={tab === t.key}
              className={`rounded-md px-3 py-1.5 text-[12px] font-semibold whitespace-nowrap transition-colors ${
                tab === t.key ? "text-white" : "muted hover:text-[var(--ink)]"
              }`}
              style={tab === t.key ? { background: "var(--accent)", color: "#041018" } : undefined}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "equity" && <EquityTab />}
      {tab === "fno" && <FnoTab />}
      {tab === "mf" && <MfTab />}
      {tab === "bonds" && <BondTab />}
      {tab === "gold" && <GoldTab />}
      {tab === "reit" && <ReitTab />}
      {tab === "corp" && <CorpTab />}

      <p className="muted text-[10.5px] leading-relaxed mt-6">
        Every calculator is a teaching model over the inputs you provide. It is
        not investment, tax or legal advice. Statutory rates reflect FY2025-26
        and can change.
      </p>
    </div>
  );
}
