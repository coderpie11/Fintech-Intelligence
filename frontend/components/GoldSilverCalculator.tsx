"use client";

import { useEffect, useState } from "react";
import { postJSON } from "@/lib/api";
import { inr } from "@/lib/format";
import MetricTip from "@/components/MetricTip";

type Row = {
  vehicle: string;
  units: number;
  outlay: number;
  fees: number;
  end_value: number;
  net_gain: number;
  effective_cagr_pct: number | null;
};

type Result = {
  metal: "gold" | "silver";
  rows: Row[];
  best: string;
  spot_per_gram: number;
  end_price_per_gram: number;
  years: number;
  grams: number;
  amount_inr: number;
  input_mode: "amount" | "weight";
  price_unit: string;
  note: string;
};

const QUICK = [5000, 10000, 25000, 50000, 100000];

const TIPS = {
  amount: {
    meaning:
      "How many rupees you want to put in. The calculator converts it into grams at today's live ₹ price and then shows what each route leaves you with.",
    example: "₹10,000 at ₹11,900 per gram buys about 0.84 g of 24K gold.",
  },
  weight: {
    meaning:
      "The metal weight you already hold or want to buy. The calculator converts it into rupees at today's live price.",
  },
  making: {
    meaning:
      "Jeweller's making / wastage charge added on top of the raw metal price. Digital gold, ETFs and SGBs charge zero making charges.",
    example: "12% making on ₹1,00,000 of gold adds ₹12,000 before GST.",
  },
  cagr: {
    meaning:
      "The average yearly price growth you expect for the metal. The same rate is applied to every vehicle so the comparison isolates charges and tax.",
  },
  years: {
    meaning: "How long you plan to stay invested before selling or redeeming.",
  },
  slab: {
    meaning:
      "Your income-tax slab. It applies to the SGB coupon and to physical/ETF gains if held for a short period.",
  },
  units: {
    meaning:
      "Grams of metal you actually own after upfront charges. Physical metal buys fewer grams for the same rupees because making charges and GST are deducted first.",
  },
  fees: {
    meaning:
      "Every rupee lost to making charges, GST, storage, TER, impact cost and coupon tax. Lower is better.",
  },
  net: {
    meaning:
      "Final value minus the money you put in. This is the real rupee profit after all charges and tax.",
  },
};

export default function GoldSilverCalculator() {
  const [metal, setMetal] = useState<"gold" | "silver">("gold");
  const [mode, setMode] = useState<"amount" | "weight">("amount");
  const [amount, setAmount] = useState("10000");
  const [grams, setGrams] = useState("10");
  const [years, setYears] = useState("5");
  const [cagr, setCagr] = useState("8");
  const [making, setMaking] = useState("12");
  const [slab, setSlab] = useState("30");
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (overrides?: { metal?: "gold" | "silver"; mode?: "amount" | "weight" }) => {
    const m = overrides?.metal ?? metal;
    const md = overrides?.mode ?? mode;
    setBusy(true);
    setErr(null);
    try {
      const r = await postJSON<Result>("/commodities/calc/wealth", {
        metal: m,
        amount_inr: md === "amount" ? Number(amount) : null,
        grams: Number(grams),
        years: Number(years),
        cagr_pct: Number(cagr),
        making_charge_pct: Number(making),
        tax_slab_pct: Number(slab),
      });
      setRes(r);
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  // First paint should already show a real comparison, not an empty form.
  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchMetal = (m: "gold" | "silver") => {
    setMetal(m);
    setMaking(m === "gold" ? "12" : "8");
    setCagr(m === "gold" ? "8" : "7");
    void run({ metal: m });
  };

  const switchMode = (m: "amount" | "weight") => {
    setMode(m);
    void run({ mode: m });
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {([
          ["gold", "🪙 Gold Calculator"],
          ["silver", "🥈 Silver Calculator"],
        ] as const).map(([key, label]) => (
          <button key={key} onClick={() => switchMetal(key)}
                  className={`chip !text-[11.5px] ${metal === key ? "chip-active" : ""}`}>
            {label}
          </button>
        ))}
        <span className="h-4 w-px mx-1" style={{ background: "var(--line)" }} />
        {([
          ["amount", "💰 Invest by Amount (₹)"],
          ["weight", "⚖️ Enter by Weight (g / kg)"],
        ] as const).map(([key, label]) => (
          <button key={key} onClick={() => switchMode(key)}
                  className={`chip !text-[11.5px] ${mode === key ? "chip-active" : ""}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-[380px_1fr] gap-3">
        <div className="card p-4">
          <div className="text-[13px] font-bold">
            {metal === "gold" ? "Gold money vs weight" : "Silver money vs weight"}
          </div>
          <p className="muted text-[11px] mt-0.5 leading-relaxed">
            Physical, ETF{metal === "gold" ? " and SGB" : " and FoF"} compared in ₹.
            Charges are deducted first, so the same rupees buy different grams.
          </p>

          <div className="mt-3 space-y-2">
            {mode === "amount" ? (
              <>
                <label className="block">
                  <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                    <MetricTip label="Invest by amount" tip={TIPS.amount}>Invest amount (₹)</MetricTip>
                  </span>
                  <input value={amount} onChange={(e) => setAmount(e.target.value)}
                         inputMode="numeric"
                         className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[13px] knum font-bold"
                         style={{ color: "var(--ink)" }} />
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {QUICK.map((v) => (
                    <button key={v} onClick={() => setAmount(String(v))}
                            className={`chip !text-[10px] ${Number(amount) === v ? "chip-active" : ""}`}>
                      ₹{v.toLocaleString("en-IN")}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <label className="block">
                <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                  <MetricTip label="Enter by weight" tip={TIPS.weight}>Weight (grams / kg)</MetricTip>
                </span>
                <input value={grams} onChange={(e) => setGrams(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[13px] knum font-bold"
                       style={{ color: "var(--ink)" }} />
                <span className="muted text-[10px]">Enter 1000 for 1 kg.</span>
              </label>
            )}

            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                  <MetricTip label="Years" tip={TIPS.years}>Years</MetricTip>
                </span>
                <input value={years} onChange={(e) => setYears(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                  <MetricTip label="Expected CAGR" tip={TIPS.cagr}>Expected CAGR %</MetricTip>
                </span>
                <input value={cagr} onChange={(e) => setCagr(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                  <MetricTip label="Making / wastage" tip={TIPS.making}>Making / wastage %</MetricTip>
                </span>
                <input value={making} onChange={(e) => setMaking(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
              <label className="block">
                <span className="muted text-[9.5px] font-bold uppercase tracking-wider">
                  <MetricTip label="Tax slab" tip={TIPS.slab}>Tax slab %</MetricTip>
                </span>
                <input value={slab} onChange={(e) => setSlab(e.target.value)}
                       inputMode="decimal"
                       className="surface rounded-lg w-full mt-1 px-2.5 py-1.5 text-[12px] knum"
                       style={{ color: "var(--ink)" }} />
              </label>
            </div>

            <button onClick={() => run()} disabled={busy}
                    className="btn-primary w-full justify-center !py-2 !text-[12px] mt-1 disabled:opacity-60">
              {busy ? "Calculating…" : "Compare in ₹"}
            </button>
            {err && <p className="text-[11px] text-down mt-1">{err}</p>}
          </div>
        </div>

        <div className="card p-4">
          {!res && !err && <p className="muted text-[12px]">Calculating today's ₹ price…</p>}
          {res && (
            <>
              <div className="rounded-lg p-3 mb-3"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                  {res.input_mode === "amount" ? "Your rupees buy" : "Your weight is worth"}
                </div>
                <div className="knum text-[24px] font-black mt-1">
                  {res.grams.toLocaleString("en-IN", { maximumFractionDigits: 4 })} g{" "}
                  <span className="text-[13px] font-semibold muted">
                    of {res.metal === "gold" ? "gold" : "silver"}
                  </span>
                </div>
                <div className="muted text-[11px] mt-1">
                  {inr(res.amount_inr)} at {inr(res.spot_per_gram)} per gram today ·{" "}
                  after {res.years} years at {inr(res.end_price_per_gram)}/g
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-[11.5px]">
                  <thead>
                    <tr style={{ background: "var(--surface-2)" }}>
                      <th className="table-head text-left px-2.5 py-2">Vehicle</th>
                      <th className="table-head text-right px-2.5 py-2">
                        <MetricTip label="Grams bought" tip={TIPS.units}>Grams</MetricTip>
                      </th>
                      <th className="table-head text-right px-2.5 py-2">You pay</th>
                      <th className="table-head text-right px-2.5 py-2">
                        <MetricTip label="Charges lost" tip={TIPS.fees}>Charges lost</MetricTip>
                      </th>
                      <th className="table-head text-right px-2.5 py-2">Final value</th>
                      <th className="table-head text-right px-2.5 py-2">
                        <MetricTip label="Net profit" tip={TIPS.net}>Net profit</MetricTip>
                      </th>
                      <th className="table-head text-right px-2.5 py-2">CAGR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {res.rows.map((r) => (
                      <tr key={r.vehicle} className="table-row">
                        <td className="px-2.5 py-2 font-semibold">
                          {r.vehicle}
                          {r.vehicle === res.best && (
                            <span className="chip chip-active !text-[7.5px] !py-0 !px-1 ml-1.5">BEST</span>
                          )}
                        </td>
                        <td className="px-2.5 py-2 text-right knum">
                          {r.units.toLocaleString("en-IN", { maximumFractionDigits: 4 })}
                        </td>
                        <td className="px-2.5 py-2 text-right knum">{inr(r.outlay)}</td>
                        <td className="px-2.5 py-2 text-right knum text-down">{inr(r.fees)}</td>
                        <td className="px-2.5 py-2 text-right knum font-bold">{inr(r.end_value)}</td>
                        <td className={`px-2.5 py-2 text-right knum font-bold ${r.net_gain >= 0 ? "text-up" : "text-down"}`}>
                          {inr(r.net_gain)}
                        </td>
                        <td className={`px-2.5 py-2 text-right knum font-bold ${(r.effective_cagr_pct || 0) >= 0 ? "text-up" : "text-down"}`}>
                          {r.effective_cagr_pct == null ? "—" : `${r.effective_cagr_pct.toFixed(2)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted text-[10.5px] mt-2 leading-relaxed">{res.note}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
