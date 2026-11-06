"use client";

import Link from "next/link";
import { useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr } from "@/lib/format";
import { PageHeader } from "@/components/PageKit";
import MetricTip, { type Tip } from "@/components/MetricTip";
import GoldSilverCalculator from "@/components/GoldSilverCalculator";

/* ------------------------------------------------------------------ shared */

const TIPS: Record<string, Tip> = {
  fcff: {
    meaning: "Free cash flow to the firm: the cash the business throws off after running itself and paying for growth, before lenders and shareholders are paid.",
    formula: "FCFF = Operating cash flow − Capital expenditure",
  },
  growth: { meaning: "How fast you expect that free cash flow to grow each year for the next five years." },
  terminal: {
    meaning: "The slow, steady growth rate assumed forever after year five. It should usually be near long-run inflation, not today's hot growth.",
  },
  wacc: {
    meaning: "Weighted Average Cost of Capital: the blended yearly return lenders and shareholders demand. Higher WACC means future cash is worth less today.",
    formula: "WACC = (E/V × Cost of equity) + (D/V × Cost of debt × (1 − tax))",
  },
  netCash: { meaning: "Cash minus debt on the balance sheet. It is added to the business value because a buyer would receive it." },
  shares: { meaning: "Total shares outstanding. The equity value is divided by this number to get value per share." },
  mos: {
    meaning: "Margin of Safety: the discount you demand below fair value so a mistake or bad news does not wipe out your return.",
    example: "A ₹100 fair value with a 20% margin of safety gives a safe buy price of ₹80.",
  },
  swp: {
    meaning: "Systematic Withdrawal Plan: you pull a fixed rupee amount from the fund every month while the remaining corpus keeps growing.",
  },
  ltcg: {
    meaning: "Long-Term Capital Gains: profit on equity held over one year. FY2025-26 allows ₹1.25 lakh of LTCG per year before the 12.5% tax starts.",
  },
  xirr: {
    meaning: "Extended Internal Rate of Return: the annualised return when money goes in and out on different dates, like a monthly SIP. It is the true yearly return.",
    formula: "XIRR is the rate that makes the present value of all cash flows equal zero.",
  },
  ter: {
    meaning: "Total Expense Ratio: the yearly fee a fund deducts from your money. A 1.20% TER costs ₹1,200 a year on ₹1,00,000.",
  },
  clean: {
    meaning: "Clean price: the bond's quoted price without the interest that has already accrued since the last coupon.",
  },
  dirty: {
    meaning: "Dirty price: clean price plus accrued interest. This is the actual amount a buyer pays.",
    formula: "Dirty price = Clean price + Accrued interest",
  },
  accrued: {
    meaning: "Interest earned by the seller since the last coupon but not yet paid. The buyer reimburses it through the dirty price.",
  },
  postTaxYtm: {
    meaning: "The yield you keep after tax on the coupon. It shows what the bond really pays you in hand.",
  },
  ndcf: {
    meaning: "Net Distributable Cash Flow yield: the cash a REIT actually distributes each year divided by its unit price. It is the REIT version of a dividend yield.",
    formula: "NDCF yield = Distribution per unit ÷ Price per unit × 100",
  },
  wale: {
    meaning: "Weighted Average Lease Expiry: the average years left on a REIT's leases, weighted by rent. Longer WALE means steadier rental income.",
  },
  amort: {
    meaning: "Amortisation: part of a REIT distribution that is simply your own capital coming back. It is tax-free now but lowers your cost basis.",
  },
  tds: {
    meaning: "Tax Deducted at Source: the company withholds 10% of your dividend above the annual threshold and deposits it with the government. You claim it back when filing.",
  },
  exDate: {
    meaning: "Ex-Date: the first day the share trades without the dividend, split or bonus. Buy on or after this date and you do not get that corporate action.",
  },
  recordDate: {
    meaning: "Record Date: the day the company checks its register to decide who is eligible for the dividend, split or bonus.",
  },
  buybackQuota: {
    meaning: "Retail buyback quota: companies reserve a small portion of a buyback for small shareholders, usually those holding up to ₹2 lakh worth of shares.",
  },
  spot: { meaning: "Abhi share ya Nifty kis price par chal raha hai — the current market price you would buy or sell at right now." },
  strike: { meaning: "Woh level jahan aap shart/contract laga rahe ho — the price at which your option becomes valuable at expiry." },
  days: { meaning: "Contract khatam hone mein kitne din baaki hain. Fewer days means faster time decay and cheaper options." },
  iv: { meaning: "Market mein kitna utaar-chadhav expected hai. Zyada IV matlab option mehenga; kam IV matlab sasta." },
  rf: { meaning: "The government's safe interest rate. It is used as the 'no-risk' return while pricing the option." },
  div: { meaning: "Dividend yield the stock pays. A high dividend reduces the call price because the share price drops on the ex-date." },
  call: { meaning: "Fair price of a Call option — the bet that the market goes up (tezi). If the market rises above your target price, this gains." },
  put: { meaning: "Fair price of a Put option — the bet that the market falls (mandi). It works like insurance on your portfolio." },
  delta: { meaning: "Price Speed: how many rupees the option premium moves for every ₹1 move in the stock. A 0.42 delta gains about ₹0.42 when the stock rises ₹1." },
  gamma: { meaning: "Speed Change: how much the Delta itself changes when the stock moves ₹1. High gamma near expiry means the option accelerates fast." },
  theta: { meaning: "Daily Time Melting Loss: the rupees an option loses every day simply because expiry is one day closer. Option buyers pay this; sellers earn it." },
  vega: { meaning: "Fear Premium: how much the option price changes when market fear (IV) moves by 1 percentage point. Long options gain when fear rises." },
  pop: { meaning: "Win Chance: the model's probability that the option finishes profitable at expiry. It is an estimate, not a guarantee." },
};

function Field({
  label, value, onChange, suffix, step = "any", tip,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  step?: string;
  tip?: Tip;
}) {
  return (
    <label className="block">
      <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
        {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
      </span>
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
  rows: { label: string; value: string; tone?: "up" | "down"; tip?: Tip }[];
  note?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-[13px] font-bold mb-2">{title}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-2 text-[11.5px]">
            <span className="muted">
              {r.tip ? <MetricTip label={r.label} tip={r.tip}>{r.label}</MetricTip> : r.label}
            </span>
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
  const [mos, setMos] = useState("20");
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
          <Field label="Free Cash Flow (FCFF ₹ cr)" value={fcff} onChange={setFcff} tip={TIPS.fcff} />
          <Field label="Growth % (next 5Y)" value={growth} onChange={setGrowth} tip={TIPS.growth} />
          <Field label="Terminal Growth %" value={terminal} onChange={setTerminal} tip={TIPS.terminal} />
          <Field label="WACC % (discount rate)" value={wacc} onChange={setWacc} tip={TIPS.wacc} />
          <Field label="Net Cash (₹ cr)" value={netCash} onChange={setNetCash} tip={TIPS.netCash} />
          <Field label="Shares (crore)" value={shares} onChange={setShares} tip={TIPS.shares} />
          <Field label="Margin of Safety %" value={mos} onChange={setMos} tip={TIPS.mos} />
        </div>
        <RunButton onClick={run} busy={busy}>Run DCF</RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
        {res?.error && <p className="text-[11px] text-down mt-2">{res.error}</p>}
        {res && !res.error && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">DCF value per share</div>
              <div className="knum text-[22px] font-black mt-1">{money(res.per_share)}</div>
            </div>
            <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">
                <MetricTip label="Safe buy price" tip={TIPS.mos}>Safe buy price (MOS)</MetricTip>
              </div>
              <div className="knum text-[16px] font-black mt-1">
                {money((res.per_share || 0) * (1 - Number(mos) / 100))}
              </div>
              <div className="muted text-[9.5px] mt-0.5">{mos}% below fair value</div>
            </div>
            <div className="muted text-[10px] col-span-2">
              Equity value {money((res.equity_value_mn || 0) * 1e6 / 1e7)} Cr ·{" "}
              PV explicit {money((res.pv_explicit || 0) * 1e6 / 1e7)} Cr · PV terminal{" "}
              {money((res.pv_terminal || 0) * 1e6 / 1e7)} Cr · {res.assumptions?.years} years
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
  const [k, setK] = useState("23800");
  const [days, setDays] = useState("7");
  const [r, setR] = useState("6.5");
  const [sig, setSig] = useState("13");
  const [q, setQ] = useState("1.2");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (overrides?: {
    s: string; k: string; days: string; r: string; sig: string; q: string;
  }) => {
    const v = overrides ?? { s, k, days, r, sig, q };
    setBusy(true); setErr(null); setRes(null);
    try {
      const T = Math.max(Number(v.days) / 365, 1 / 365);
      setRes(await getJSON(
        `/calc/bsm?S=${Number(v.s)}&K=${Number(v.k)}&T=${T}` +
        `&r=${Number(v.r) / 100}&sigma=${Number(v.sig) / 100}&q=${Number(v.q) / 100}`));
    } catch (e: any) { setErr(errText(e)); }
    setBusy(false);
  };

  const presets = [
    { label: "Nifty 50 ATM Example", s: "23800", k: "23800", days: "7", r: "6.5", sig: "13", q: "1.2" },
    { label: "Bank Nifty Example", s: "51000", k: "51000", days: "10", r: "6.5", sig: "16", q: "0" },
    { label: "Reliance Option Example", s: "2950", k: "3000", days: "18", r: "6.5", sig: "22", q: "0.5" },
  ];

  const applyPreset = (p: (typeof presets)[number]) => {
    setS(p.s); setK(p.k); setDays(p.days); setR(p.r); setSig(p.sig); setQ(p.q);
    void run(p);
  };

  return (
    <div className="grid lg:grid-cols-[420px_1fr] gap-4">
      <div className="card p-4">
        <div className="text-[13px] font-bold">Option Price Calculator</div>
        <p className="muted text-[11px] mt-0.5 mb-2">
          Simple everyday language. Hover any label to decode the jargon.
        </p>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {presets.map((p) => (
            <button key={p.label} onClick={() => applyPreset(p)}
                    className="chip !text-[10px]">{p.label}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Current Market Price (Spot ₹)" value={s} onChange={setS} tip={TIPS.spot} />
          <Field label="Target Deal Price (Strike ₹)" value={k} onChange={setK} tip={TIPS.strike} />
          <Field label="Days Left till Expiry" value={days} onChange={setDays} step="1" tip={TIPS.days} />
          <Field label="Government Rate (Risk-Free %)" value={r} onChange={setR} tip={TIPS.rf} />
          <Field label="Market Fear / Speed (IV %)" value={sig} onChange={setSig} tip={TIPS.iv} />
          <Field label="Dividend You Get (%)" value={q} onChange={setQ} tip={TIPS.div} />
        </div>
        <RunButton onClick={() => run()} busy={busy}>Show Fair Price</RunButton>
        {err && <p className="text-[11px] text-down mt-2">{err}</p>}
      </div>

      <div className="space-y-3">
        {res ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  <MetricTip label="Call fair price" tip={TIPS.call}>Call Option Fair Price (Tezi / Upside ₹)</MetricTip>
                </div>
                <div className="knum text-[24px] font-black mt-1">{money(res.call)}</div>
                <div className="muted text-[10px] mt-0.5">
                  <MetricTip label="Win chance" tip={TIPS.pop}>Win Chance (POP)</MetricTip> {pctv(res.pop_call)}
                </div>
              </div>
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  <MetricTip label="Put fair price" tip={TIPS.put}>Put Option Fair Price (Mandi / Downside ₹)</MetricTip>
                </div>
                <div className="knum text-[24px] font-black mt-1">{money(res.put)}</div>
                <div className="muted text-[10px] mt-0.5">
                  <MetricTip label="Win chance" tip={TIPS.pop}>Win Chance (POP)</MetricTip> {pctv(res.pop_put)}
                </div>
              </div>
            </div>
            <Result
              title="What moves the option price (per unit)"
              rows={[
                { label: "Price Speed — Call (Delta)", value: String(res.delta_call), tip: TIPS.delta },
                { label: "Price Speed — Put (Delta)", value: String(res.delta_put), tip: TIPS.delta },
                { label: "Speed Change (Gamma)", value: String(res.gamma), tip: TIPS.gamma },
                { label: "Daily Time Melting Loss — Call (Theta ₹/day)", value: money(res.theta_call, 4), tone: "down", tip: TIPS.theta },
                { label: "Daily Time Melting Loss — Put (Theta ₹/day)", value: money(res.theta_put, 4), tone: "down", tip: TIPS.theta },
                { label: "Fear Premium (Vega ₹ per 1% IV)", value: money(res.vega, 4), tip: TIPS.vega },
              ]}
              note="Fair prices use the inputs above. Live option chains add bid-ask spreads, IV skew and early-exercise effects that this European model ignores."
            />
            <div className="card p-4 muted text-[11.5px] leading-relaxed">
              Want the live chain? Open a stock with F&amp;O and switch to its
              Derivatives tab for real strikes and OI.{" "}
              <Link href="/stocks/RELIANCE" className="accent font-semibold">RELIANCE F&amp;O →</Link>
            </div>
          </>
        ) : (
          <div className="card p-6 muted text-[12px]">
            Pick a preset or enter your own numbers, then press “Show Fair Price”.
          </div>
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
            <Field label="Monthly SIP" value={monthly} onChange={setMonthly} suffix="₹" />
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
          <p className="muted text-[10px] mt-2 leading-relaxed">
            <MetricTip label="XIRR" tip={TIPS.xirr}>XIRR</MetricTip> is the true annualised
            return when you invest on many different dates, like a monthly SIP.
          </p>
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">
            <MetricTip label="SWP" tip={TIPS.swp}>SWP duration</MetricTip>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <Field label="Corpus" value={corpus} onChange={setCorpus} suffix="₹" tip={TIPS.swp} />
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
          <div className="text-[13px] font-bold">
            <MetricTip label="LTCG harvest window" tip={TIPS.ltcg}>LTCG harvest window</MetricTip>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Unrealised gain" value={gain} onChange={setGain} suffix="₹" tip={TIPS.ltcg} />
            <Field label="₹1.25L exemption used" value={used} onChange={setUsed} suffix="₹" tip={TIPS.ltcg} />
          </div>
          <RunButton busy={false}
                     onClick={() => run(async () => setLtcg(await postJSON("/calc/ltcg", {
                       unrealized_gain: Number(gain), used_exemption: Number(used),
                     })))}>
            Compute tax
          </RunButton>
          {ltcg && !ltcg.error && (
            <Result title="Listed-equity LTCG (12.5%)" rows={[
              { label: "₹1.25L exemption left", value: money(ltcg.exemption_left), tip: TIPS.ltcg },
              { label: "Taxable gain", value: money(ltcg.taxable_gain), tip: TIPS.ltcg },
              { label: "Tax", value: money(ltcg.tax) },
              { label: "Post-tax gain", value: money(ltcg.post_tax_gain), tone: "up" },
            ]} note="FY2025-26 rules: ₹1.25 lakh annual exemption, 12.5% above it. A model, not tax advice." />
          )}
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold">
            <MetricTip label="Expense Ratio / TER" tip={TIPS.ter}>MF vs ETF fee drag</MetricTip>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="Amount" value={amount} onChange={setAmount} suffix="₹" />
            <Field label="Years" value={feeYears} onChange={setFeeYears} />
            <Field label="Gross return %" value={gross} onChange={setGross} />
            <Field label="Low TER %" value={lowCost} onChange={setLowCost} tip={TIPS.ter} />
            <Field label="High TER %" value={highCost} onChange={setHighCost} tip={TIPS.ter} />
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
              { label: "Clean Price", value: money(res.clean_price, 4), tip: TIPS.clean },
              { label: "Dirty Price", value: money(res.dirty_price, 4), tip: TIPS.dirty },
              { label: "Accrued Interest", value: money(res.accrued_interest, 4), tip: TIPS.accrued },
              { label: "Coupon income", value: money(res.coupon_income) },
              { label: "Post-tax income", value: money(res.post_tax_income) },
              { label: "Post-Tax YTM", value: pctv(res.post_tax_ytm_pct), tip: TIPS.postTaxYtm },
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
  return <GoldSilverCalculator />;
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
        <div className="text-[13px] font-bold">
          <MetricTip label="NDCF yield" tip={TIPS.ndcf}>Post-tax NDCF yield</MetricTip>
        </div>
        <p className="muted text-[11px] mt-0.5 mb-3">
          Interest, dividend and other income are taxed at slab;{" "}
          <MetricTip label="Amortisation" tip={TIPS.amort}>amortisation</MetricTip> is a
          tax-free return of capital.{" "}
          <MetricTip label="WALE" tip={TIPS.wale}>WALE</MetricTip> tells you how long the
          leases run.
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
          <Field label="Distribution / unit" value={dist} onChange={setDist} suffix="₹" tip={TIPS.ndcf} />
          <Field label="Tax slab %" value={slab} onChange={setSlab} />
          <Field label="Interest %" value={interest} onChange={setInterest} />
          <Field label="Dividend %" value={dividend} onChange={setDividend} />
          <Field label="Amortisation % (tax-free)" value={amort} onChange={setAmort} tip={TIPS.amort} />
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
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  <MetricTip label="NDCF yield" tip={TIPS.ndcf}>NDCF yield (pre-tax)</MetricTip>
                </div>
                <div className="knum text-[24px] font-black mt-1">{pctv(res.pre_tax_yield_pct)}</div>
              </div>
              <div className="card p-3">
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  <MetricTip label="NDCF yield" tip={TIPS.ndcf}>NDCF yield (post-tax)</MetricTip>
                </div>
                <div className="knum text-[24px] font-black mt-1 text-up">{pctv(res.post_tax_yield_pct)}</div>
              </div>
            </div>
            <Result title={`${res.symbol} distribution split`} rows={[
              { label: "Total distribution", value: money(res.total_distribution), tip: TIPS.ndcf },
              { label: "Interest", value: money(res.split?.interest) },
              { label: "Dividend", value: money(res.split?.dividend) },
              { label: "Amortisation (tax-free now)", value: money(res.split?.amortization), tip: TIPS.amort },
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
              { label: "TDS 10%", value: money(div.tds_10pct), tip: TIPS.tds },
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
      <div className="card p-4">
        <div className="text-[12px] font-bold mb-2">Corporate-action terms in plain English</div>
        <div className="grid sm:grid-cols-3 gap-2 text-[11.5px]">
          <div className="rounded-lg p-2.5" style={{ background: "var(--surface-2)" }}>
            <MetricTip label="Ex-Date" tip={TIPS.exDate}>Ex-Date</MetricTip>
            <p className="muted text-[10.5px] mt-1 leading-relaxed">First day the share trades without the dividend, split or bonus.</p>
          </div>
          <div className="rounded-lg p-2.5" style={{ background: "var(--surface-2)" }}>
            <MetricTip label="Record Date" tip={TIPS.recordDate}>Record Date</MetricTip>
            <p className="muted text-[10.5px] mt-1 leading-relaxed">The day the company checks who is eligible for the corporate action.</p>
          </div>
          <div className="rounded-lg p-2.5" style={{ background: "var(--surface-2)" }}>
            <MetricTip label="Retail buyback quota" tip={TIPS.buybackQuota}>Retail &lt;₹2L quota</MetricTip>
            <p className="muted text-[10.5px] mt-1 leading-relaxed">A reserved slice of a buyback for small shareholders holding up to ₹2 lakh.</p>
          </div>
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
