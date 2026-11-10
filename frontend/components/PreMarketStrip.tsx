"use client";

import { useCallback, useEffect, useState } from "react";
import { getJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { Panel, Metric, Pill, Note, ErrLine } from "@/components/quant/Kit";

type Gap = {
  mode: string;
  instrument: string;
  source_note?: string | null;
  nifty: { prev_close: number | null; last: number | null };
  gift_nifty: { last: number | null; change_pct: number | null; expiry: string; days_to_expiry: number; is_proxy: boolean };
  fair_value: { fair_futures: number | null; basis_points: number | null; basis_pct: number | null };
  opening_gap: { points: number | null; pct: number | null; direction: string; label: string; note: string };
  sectors: { sector: string; signal: string; avg_change_pct: number | null; drivers: { symbol: string; name: string; last: number | null; change_pct: number | null }[] }[];
  overnight: {
    adrs: { symbol: string; name: string; sector: string; last: number | null; change_pct: number | null; currency: string }[];
    dxy: { last: number | null; change_pct: number | null; implication: string | null } | null;
    brent: { last: number | null; change_pct: number | null; implication: string | null } | null;
  };
  disclaimer: string;
};

type Vix = {
  spot: number; vix: number;
  regime: { label: string; band: string; tone: string; note: string };
  percentile_1y: number | null;
  mean_20d: number | null;
  ranges: { period: string; move_pct: number; move_points: number; lower: number; upper: number; formula: string }[];
  iv_crush: {
    warning: boolean; severity: string; vix_vs_20d_mean_pct: number | null;
    events: { symbol: string | null; company: string; kind: string; date: string | null; days_away: number | null; purpose: string }[];
    window_days: number; note: string;
  };
  formula_note: string;
};

function tone(n: number | null): "up" | "down" | "neutral" {
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "up" : "down";
}

export default function PreMarketStrip({ compact = false }: { compact?: boolean }) {
  const [gap, setGap] = useState<Gap | null>(null);
  const [vix, setVix] = useState<Vix | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const [g, v] = await Promise.all([
        getJSON<Gap>("/indices/gift-nifty"),
        getJSON<Vix>("/indices/vix-stability"),
      ]);
      setGap(g); setVix(v);
    } catch (e: any) {
      setErr(e?.message || "Pre-market feeds are unavailable.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (err) return <ErrLine message={err} onRetry={load} />;
  if (!gap || !vix) {
    return (
      <div className="grid lg:grid-cols-2 gap-3">
        {[0, 1].map((i) => (
          <div key={i} className="card h-40 animate-pulse" aria-busy="true" />
        ))}
      </div>
    );
  }

  const g = gap.opening_gap;
  const gapTone = tone(g.pct);
  return (
    <div className="grid lg:grid-cols-2 gap-3">
      <Panel
        title="GIFT Nifty & 09:15 implied opening gap"
        sub={`${gap.instrument} vs NIFTY 50 previous 15:30 close. ${gap.mode === "live" ? "Live feed." : "Proxy feed, clearly labelled."}`}
        right={<Pill tone={gap.mode === "live" ? "up" : "warn"}>{gap.mode === "live" ? "LIVE" : "PROXY"}</Pill>}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Metric label="Implied gap" value={<span className={gapTone === "up" ? "text-up" : gapTone === "down" ? "text-down" : ""}>{g.points == null ? "-" : `${g.points > 0 ? "+" : ""}${g.points}`}</span>} sub="points" tone={gapTone} />
          <Metric label="Gap %" value={pct(g.pct)} sub={g.label} tone={gapTone} />
          <Metric label="NIFTY prev close" value={inr(gap.nifty.prev_close)} sub="previous 3:30 PM" />
          <Metric label="GIFT / futures" value={inr(gap.gift_nifty.last)} sub={`expiry ${gap.gift_nifty.expiry}`} />
        </div>
        <div className="grid sm:grid-cols-3 gap-2 mt-2">
          {gap.sectors.map((s) => (
            <div key={s.sector} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11.5px] font-bold">{s.sector}</span>
                <Pill tone={s.signal === "lead" ? "up" : s.signal === "drag" ? "down" : "neutral"}>
                  {s.signal.toUpperCase()}
                </Pill>
              </div>
              <div className="muted text-[10px] mt-1">{pct(s.avg_change_pct)} avg ADR move</div>
            </div>
          ))}
        </div>
        {!compact && (
          <div className="mt-3 scroll-x">
            <table className="w-full text-[11.5px]">
              <thead>
                <tr className="muted text-[9px] uppercase tracking-wider text-left">
                  <th className="py-1.5 pr-2">ADR</th><th className="py-1.5 pr-2">Sector</th>
                  <th className="py-1.5 pr-2 text-right">Last (USD)</th><th className="py-1.5 text-right">Overnight</th>
                </tr>
              </thead>
              <tbody>
                {gap.overnight.adrs.map((a) => (
                  <tr key={a.symbol} style={{ borderTop: "1px solid var(--line)" }}>
                    <td className="py-1.5 pr-2 font-semibold">{a.symbol} <span className="muted font-normal">{a.name}</span></td>
                    <td className="py-1.5 pr-2 muted">{a.sector}</td>
                    <td className="py-1.5 pr-2 text-right knum">{a.last == null ? "-" : `$${a.last.toFixed(2)}`}</td>
                    <td className={`py-1.5 text-right knum ${tone(a.change_pct) === "up" ? "text-up" : tone(a.change_pct) === "down" ? "text-down" : ""}`}>{pct(a.change_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grid sm:grid-cols-2 gap-2 mt-2">
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="text-[11px] font-bold">Dollar Index (DXY)</div>
                <div className="knum text-[14px] font-bold mt-0.5">{gap.overnight.dxy?.last?.toFixed(2) ?? "-"} <span className={tone(gap.overnight.dxy?.change_pct ?? null) === "up" ? "text-down text-[11px]" : "text-up text-[11px]"}>{pct(gap.overnight.dxy?.change_pct)}</span></div>
                <div className="muted text-[10px] mt-1 leading-snug">{gap.overnight.dxy?.implication ?? "No read."}</div>
              </div>
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="text-[11px] font-bold">Brent crude</div>
                <div className="knum text-[14px] font-bold mt-0.5">{gap.overnight.brent?.last?.toFixed(2) ?? "-"} <span className={tone(gap.overnight.brent?.change_pct ?? null) === "up" ? "text-down text-[11px]" : "text-up text-[11px]"}>{pct(gap.overnight.brent?.change_pct)}</span></div>
                <div className="muted text-[10px] mt-1 leading-snug">{gap.overnight.brent?.implication ?? "No read."}</div>
              </div>
            </div>
          </div>
        )}
        <Note>{g.note} {gap.source_note ? `${gap.source_note} ` : ""}Basis {inr(gap.fair_value.basis_points)} pts.</Note>
      </Panel>

      <Panel
        title="India VIX stability & expected ranges"
        sub={`${vix.regime.label} (${vix.regime.band}). Ranges are one standard deviation from the VIX reading.`}
        right={<Pill tone={vix.regime.tone === "fear" ? "down" : vix.regime.tone === "calm" ? "up" : "accent"}>{vix.regime.label}</Pill>}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Metric label="INDIA VIX" value={vix.vix.toFixed(2)} sub={vix.regime.band} tone={vix.regime.tone === "fear" ? "down" : "neutral"} />
          <Metric label="1Y percentile" value={vix.percentile_1y == null ? "-" : `${vix.percentile_1y}%`} sub="of 252 sessions" />
          <Metric label="20-day mean" value={vix.mean_20d?.toFixed(2) ?? "-"} sub="implied volatility" />
          <Metric label="NIFTY 50" value={inr(vix.spot)} sub="range anchor" />
        </div>
        <div className="grid sm:grid-cols-3 gap-2 mt-2">
          {vix.ranges.map((r) => (
            <div key={r.period} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider">{r.period} swing</div>
              <div className="knum text-[14px] font-bold mt-0.5">±{r.move_points.toFixed(0)} pts</div>
              <div className="muted text-[10px] mt-0.5">±{r.move_pct.toFixed(2)}% · {inr(r.lower)}–{inr(r.upper)}</div>
            </div>
          ))}
        </div>
        <div className="mt-2 rounded-md px-3 py-2 text-[11.5px]"
             style={{ border: `1px solid color-mix(in srgb, ${vix.iv_crush.warning ? "var(--warn)" : "var(--line)"} 45%, var(--line))` }}>
          <div className="flex items-center gap-2">
            <Pill tone={vix.iv_crush.warning ? "warn" : "neutral"}>
              {vix.iv_crush.warning ? `IV-CRUSH WATCH · ${vix.iv_crush.severity}` : "NO IV-CRUSH SETUP"}
            </Pill>
            <span className="muted text-[10.5px]">
              VIX {vix.iv_crush.vix_vs_20d_mean_pct == null ? "-" : pct(vix.iv_crush.vix_vs_20d_mean_pct)} vs 20-day mean
            </span>
          </div>
          <p className="muted text-[10.5px] mt-1 leading-relaxed">{vix.iv_crush.note}</p>
          {!compact && vix.iv_crush.events.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {vix.iv_crush.events.slice(0, 5).map((e, i) => (
                <li key={`${e.symbol}-${e.date}-${i}`} className="text-[10.5px] flex gap-2">
                  <span className="knum muted">{e.date}</span>
                  <span className="font-semibold">{e.symbol || e.company}</span>
                  <span className="muted truncate">{e.purpose}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Note>{vix.regime.note} {vix.formula_note}</Note>
      </Panel>
    </div>
  );
}
