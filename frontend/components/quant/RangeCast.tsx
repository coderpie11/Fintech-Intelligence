"use client";

import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";
import { inr } from "@/lib/format";
import { Bar, ErrLine, Loading, Metric, Note, Panel, Pill, num, signed } from "./Kit";

const QUICK = ["RELIANCE", "TCS", "HDFCBANK", "NIFTY", "BANKNIFTY"];
const HORIZONS = [7, 14, 21, 30];

type Band = [number, number];

type RangeCastData = {
  symbol: string;
  name: string;
  kind: string;
  asof: string | null;
  spot: { value: number | null; status: string; note: string };
  horizon_days: number;
  confidence_interval_pct: number;
  volatility: {
    daily_pct: number;
    annualised_pct: number;
    sessions_used: number;
    method: string;
  };
  bands: Record<string, Band>;
  wall_adjusted_80: { value: Band; status: string; note: string };
  wall_clamps: string[];
  oi_walls: {
    available: boolean;
    spot: number | null;
    expiry: string | null;
    support: { strike: number; oi: number; share_pct: number }[];
    resistance: { strike: number; oi: number; share_pct: number }[];
    pcr: number | null;
    pcr_label: string | null;
    note: string;
  };
  delivery: {
    available: boolean;
    current: number | null;
    mean: number | null;
    std: number | null;
    z: number | null;
    percentile: number | null;
    sessions: number;
    window_start?: string | null;
    asof?: string | null;
    label?: string;
    note: string;
  };
  regime_backtest: {
    available: boolean;
    regime?: string;
    samples?: number;
    median_forward_return_pct?: number;
    p10_pct?: number;
    p90_pct?: number;
    empirical_80pct_move_pct?: number;
    empirical_band_hit_rate_pct?: number;
    note: string;
  };
  outside_band_probability_pct?: Record<string, number>;
  touch_probabilities_pct?: Record<string, number>;
  method_note: { value: string };
  disclaimer: string;
  generated_at: string;
};

export default function RangeCast() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [horizon, setHorizon] = useState(7);
  const [data, setData] = useState<RangeCastData | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = (sym = symbol, h = horizon) => {
    setBusy(true);
    setErr(null);
    getJSON<RangeCastData>(`/quant-hub/rangecast/${encodeURIComponent(sym.trim().toUpperCase())}?horizon_days=${h}`)
      .then(setData)
      .catch((e) => setErr(String(e.message || e).slice(0, 200)))
      .finally(() => setBusy(false));
  };

  useEffect(() => { run("RELIANCE", 7); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const d = data;
  const band80 = d?.bands?.["80"];
  const adjusted = d?.wall_adjusted_80?.value;
  const outside = d?.outside_band_probability_pct || d?.touch_probabilities_pct || {};

  return (
    <div className="space-y-3">
      <Panel
        title="RangeCast AI — 7 / 14-day probabilistic bands"
        sub="A statistical price envelope built from this instrument's own realised volatility, then clipped at the largest live F&O open-interest walls. It is a distribution, not a direction call."
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] block mb-1">Symbol</span>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter") run(); }}
              placeholder="RELIANCE / NIFTY"
              className="surface rounded-lg px-3 py-2 knum w-44 text-[13px]"
              style={{ color: "var(--ink)" }}
            />
          </label>
          <label className="block">
            <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] block mb-1">Horizon</span>
            <select
              value={horizon}
              onChange={(e) => { const h = Number(e.target.value); setHorizon(h); run(symbol, h); }}
              className="surface rounded-lg px-3 py-2 text-[12.5px]"
              style={{ color: "var(--ink)" }}
            >
              {HORIZONS.map((h) => <option key={h} value={h}>{h} trading sessions</option>)}
            </select>
          </label>
          <button onClick={() => run()} disabled={busy} className="btn-primary !py-2 !text-[12.5px]">
            {busy ? "Computing…" : "Project bands"}
          </button>
          <div className="flex flex-wrap gap-1 ml-auto">
            {QUICK.map((q) => (
              <button key={q} onClick={() => { setSymbol(q); run(q, horizon); }}
                      className="chip !text-[9.5px] hover:opacity-80">{q}</button>
            ))}
          </div>
        </div>
      </Panel>

      {err && <ErrLine message={`Could not build a band: ${err}`} onRetry={() => run()} />}
      {!d && busy && <Loading label="Reading stored closes and the live NSE chain…" />}

      {d && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <Metric label="Spot" value={inr(d.spot?.value)} sub={`${d.kind} · as of ${d.asof || "latest session"}`}
                    tip={{ meaning: "The last available price from the platform store. On the free feed it is end-of-day or delayed, not a live tick." }} />
            <Metric label="Daily σ" value={`${num(d.volatility?.daily_pct, 3)}%`} sub="1-session standard deviation"
                    tip={{ meaning: "How far the price typically moves in one session, as the standard deviation of daily log returns.",
                           formula: "σ_daily = std( ln(Close_t ÷ Close_{t−1}) )" }} />
            <Metric label="Annualised σ" value={`${num(d.volatility?.annualised_pct)}%`} sub={`${num(d.volatility?.sessions_used, 0)} sessions used`}
                    tip={{ meaning: "The daily standard deviation scaled to a year. It is the input the bands are built from.",
                           formula: "σ_annual = σ_daily × √252",
                           example: "0.865% a day scales to about 13.72% a year." }} />
            <Metric label={`80% band · ${d.horizon_days}d`} value={band80 ? `${num(band80[0], 0)} – ${num(band80[1], 0)}` : "—"}
                    tip={{ meaning: "The range that would contain 80% of drift-free outcomes over the horizon, from the instrument's own realised volatility.",
                           formula: "Band = Spot × exp( ± z × σ_daily × √days ),  z ≈ 1.2816 for 80%" }}
                    sub={adjusted && (adjusted[0] !== band80?.[0] || adjusted[1] !== band80?.[1]) ? "OI-wall adjusted below" : "No wall adjustment applied"} />
          </div>

          <div className="grid lg:grid-cols-[1.1fr_1fr] gap-3">
            <Panel title="Probability envelope" sub="Central bands from realised volatility. The widest band holds 95% of normally distributed outcomes — it is not a price target.">
              <div className="space-y-2.5">
                {Object.entries(d.bands || {}).map(([conf, band]) => {
                  const width = d.spot?.value ? ((band[1] - band[0]) / d.spot.value) * 100 : 0;
                  const is80 = conf === "80";
                  return (
                    <div key={conf} className="rounded-lg px-3 py-2.5"
                         style={{ border: `1px solid ${is80 ? "color-mix(in srgb, var(--accent) 45%, var(--line))" : "var(--line)"}` }}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-bold uppercase tracking-[0.1em] muted">{conf}% band</span>
                        <span className="knum text-[12.5px] font-bold">
                          <span className="text-[var(--down)]">{inr(band[0])}</span>
                          <span className="muted mx-1">to</span>
                          <span className="text-[var(--up)]">{inr(band[1])}</span>
                        </span>
                      </div>
                      <div className="mt-2"><Bar value={Math.min(100, width * 4)} tone={is80 ? "accent" : "warn"} /></div>
                      <div className="muted text-[10px] mt-1 knum">
                        width {num(width, 2)}% of spot · chance of finishing outside {num(outside?.[conf], 2)}%
                      </div>
                    </div>
                  );
                })}
              </div>
              <Note>{d.method_note?.value}</Note>
              <Note>
                Tail probabilities are drift-free model properties (2·(1−Φ(z))), not the
                probability of touching the edge at any point before expiry.
              </Note>
            </Panel>

            <div className="space-y-3">
              <Panel title="OI-wall overlay" sub={d.oi_walls?.expiry ? `NSE chain expiry ${d.oi_walls.expiry}` : "Live NSE chain"}>
                {d.oi_walls?.available ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2 mb-2.5">
                      <Pill tone="accent">PCR {num(d.oi_walls.pcr, 3)}</Pill>
                      {d.oi_walls.pcr_label && <span className="muted text-[11px]">{d.oi_walls.pcr_label}</span>}
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3">
                      <div>
                        <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1.5">Put-OI support</div>
                        {(d.oi_walls.support || []).slice(0, 4).map((w) => (
                          <div key={w.strike} className="flex items-center justify-between gap-2 py-1 text-[12px]">
                            <span className="knum font-bold">{num(w.strike, 0)}</span>
                            <span className="knum muted">{num(w.oi, 0)} OI</span>
                            <span className="knum accent">{num(w.share_pct, 1)}%</span>
                          </div>
                        ))}
                      </div>
                      <div>
                        <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1.5">Call-OI resistance</div>
                        {(d.oi_walls.resistance || []).slice(0, 4).map((w) => (
                          <div key={w.strike} className="flex items-center justify-between gap-2 py-1 text-[12px]">
                            <span className="knum font-bold">{num(w.strike, 0)}</span>
                            <span className="knum muted">{num(w.oi, 0)} OI</span>
                            <span className="knum accent">{num(w.share_pct, 1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <Note>{d.oi_walls.note}</Note>
                  </>
                ) : (
                  <p className="muted text-[12px]">{d.oi_walls?.note || "No live option chain for this instrument."}</p>
                )}

                {adjusted && band80 && (
                  <div className="mt-3 rounded-lg px-3 py-2.5"
                       style={{ border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
                                background: "color-mix(in srgb, var(--accent) 6%, transparent)" }}>
                    <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Wall-adjusted 80% band</div>
                    <div className="knum text-[14px] font-bold mt-1">{inr(adjusted[0])} — {inr(adjusted[1])}</div>
                    {(d.wall_clamps || []).length > 0 && (
                      <ul className="muted text-[10.5px] mt-1 list-disc pl-4">
                        {d.wall_clamps.map((c) => <li key={c}>{c}</li>)}
                      </ul>
                    )}
                  </div>
                )}
              </Panel>

              <Panel title="Delivery Z-score" sub="Does today's delivery look normal for this stock?">
                {d.delivery?.available ? (
                  <>
                    <div className="grid grid-cols-3 gap-2">
                      <Metric label="Delivery today" value={`${num(d.delivery.current, 1)}%`} />
                      <Metric label="45-session mean" value={`${num(d.delivery.mean, 1)}%`} />
                      <Metric label="Z-score" value={signed(d.delivery.z, 2)} tone={(d.delivery.z || 0) >= 0 ? "up" : "down"} />
                    </div>
                    <div className="mt-2.5"><Bar value={Math.max(0, Math.min(100, ((d.delivery.z || 0) + 3) / 6 * 100))} /></div>
                    <div className="muted text-[11px] mt-1.5">
                      {d.delivery.label || "Neutral versus its own recent range"} · percentile {num(d.delivery.percentile, 1)} · {d.delivery.sessions} sessions
                    </div>
                    <Note>{d.delivery.note}</Note>
                  </>
                ) : (
                  <p className="muted text-[12px]">{d.delivery?.note}</p>
                )}
              </Panel>
            </div>
          </div>

          <Panel title="Regime backtest — what actually happened" sub="Forward outcomes for past sessions whose 20-day volatility matched today's. This is history, not a forecast.">
            {d.regime_backtest?.available ? (
              <>
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <Pill tone="accent">{d.regime_backtest.regime}</Pill>
                  <span className="muted text-[11px]">{num(d.regime_backtest.samples, 0)} matching sessions</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
                  <Metric label="Median forward" value={`${signed(d.regime_backtest.median_forward_return_pct, 2)}%`} tone={(d.regime_backtest.median_forward_return_pct || 0) >= 0 ? "up" : "down"} />
                  <Metric label="10th percentile" value={`${signed(d.regime_backtest.p10_pct, 2)}%`} tone="down" />
                  <Metric label="90th percentile" value={`${signed(d.regime_backtest.p90_pct, 2)}%`} tone="up" />
                  <Metric label="Empirical 80% move" value={`±${num(d.regime_backtest.empirical_80pct_move_pct, 2)}%`} />
                  <Metric label="Band hit rate" value={`${num(d.regime_backtest.empirical_band_hit_rate_pct, 1)}%`} tone="accent" />
                </div>
                <Note>{d.regime_backtest.note}</Note>
              </>
            ) : (
              <p className="muted text-[12px]">{d.regime_backtest?.note}</p>
            )}
          </Panel>

          <p className="muted text-[11px] leading-relaxed">{d.disclaimer}</p>
        </>
      )}
    </div>
  );
}
