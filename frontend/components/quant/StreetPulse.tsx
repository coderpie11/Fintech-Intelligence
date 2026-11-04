"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { Bar, ErrLine, Loading, Metric, Note, Panel, Pill, num, signed } from "./Kit";

type Flow = {
  available: boolean;
  asof: string | null;
  fii_net_cr: number | null;
  dii_net_cr: number | null;
  fii_buy_cr: number | null;
  fii_sell_cr: number | null;
  dii_buy_cr: number | null;
  dii_sell_cr: number | null;
  combined_net_cr: number | null;
  regime: string;
  note: string;
};

type Row = {
  symbol: string;
  name: string;
  sector: string | null;
  last: number | null;
  changepct: number | null;
  delivery_pct: number | null;
  volume_ratio: number | null;
  turnover_est: number | null;
  pe: number | null;
  sector_pe: number | null;
  roe: number | null;
  href: string;
  delivery_z: { current: number; mean: number; z: number; sessions: number } | null;
  sentiment: { label: string; score: number } | null;
  quadrant: string;
  divergence_flags: string[];
};

type Headline = {
  title: string;
  source: string;
  link: string;
  published: string;
  label: string;
  score: number;
  symbols: string[];
};

type StreetData = {
  asof: string;
  flows: Flow;
  participation: {
    delivered_share_pct: number;
    churn_share_pct: number;
    universe: number;
    method: string;
  };
  news_tone: {
    engine: string;
    headlines_scored: number;
    positive: number;
    negative: number;
    neutral: number;
    net_tone: number;
    engine_status: { engine: string; state: string; error: string | null; note: string };
    note: string;
  };
  matrix: Row[];
  counts: Record<string, number>;
  headlines: Headline[];
  divergence_note: string;
  disclaimer: string;
};

const QUADRANTS: Record<string, { label: string; tone: "up" | "down" | "warn" | "accent" | "neutral"; meaning: string }> = {
  "institutional-accumulation": {
    label: "Institutional accumulation", tone: "up",
    meaning: "High delivery with a rising price — buyers took actual ownership rather than intraday positions.",
  },
  "distribution-under-delivery": {
    label: "Distribution under delivery", tone: "down",
    meaning: "High delivery with a falling price — sellers delivered stock into strength or weakness, a supply signal.",
  },
  "retail-hype": {
    label: "Retail hype", tone: "warn",
    meaning: "A large price move on low delivery — mostly intraday churn, not ownership change.",
  },
  "quiet-accumulation-against-press": {
    label: "Quiet accumulation vs press", tone: "accent",
    meaning: "Delivery is firm while the news tone is negative — accumulation that is not being talked about.",
  },
  balanced: {
    label: "Balanced", tone: "neutral",
    meaning: "No strong divergence between price, delivery and available tone.",
  },
};

export default function StreetPulse() {
  const [d, setD] = useState<StreetData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [limit, setLimit] = useState(12);

  const run = (n = limit) => {
    setErr(null);
    getJSON<StreetData>(`/quant-hub/streetpulse?limit=${n}`)
      .then(setD)
      .catch((e) => setErr(String(e.message || e).slice(0, 200)));
  };
  useEffect(() => { run(12); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  if (err) return <ErrLine message={`StreetPulse could not load: ${err}`} onRetry={() => run()} />;
  if (!d) return <Loading label="Reading the official FII/DII print, bhavcopy delivery and public headlines…" />;

  const toneTotal = (d.news_tone?.positive || 0) + (d.news_tone?.negative || 0) + (d.news_tone?.neutral || 0);
  const tonePos = toneTotal ? ((d.news_tone.positive / toneTotal) * 100) : 0;
  const toneNeg = toneTotal ? ((d.news_tone.negative / toneTotal) * 100) : 0;

  return (
    <div className="space-y-3">
      <Panel
        title="StreetPulse Matrix — who actually took ownership today?"
        sub="Official FII/DII cash-market flows, exchange delivery percentage and public-headline tone, read together instead of separately. Rupee flows exist only in step 1; everything after that is a participation measure."
        right={<Pill tone="accent">As of {d.asof?.slice(0, 10)}</Pill>}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <Metric label="FII / FPI net" value={signed(d.flows?.fii_net_cr, 2)} sub={`₹${num(d.flows?.fii_buy_cr, 0)} Cr bought · ₹${num(d.flows?.fii_sell_cr, 0)} Cr sold`}
                  tip={{ meaning: "Net cash-market flow from foreign portfolio investors, from the exchanges' provisional daily print.",
                         formula: "FII net = FII buys − FII sells (₹ crore)" }}
                  tone={(d.flows?.fii_net_cr || 0) >= 0 ? "up" : "down"} />
          <Metric label="DII net" value={signed(d.flows?.dii_net_cr, 2)} sub={`₹${num(d.flows?.dii_buy_cr, 0)} Cr bought · ₹${num(d.flows?.dii_sell_cr, 0)} Cr sold`}
                  tip={{ meaning: "Net cash-market flow from domestic institutional investors — mutual funds, insurers and banks.",
                         formula: "DII net = DII buys − DII sells (₹ crore)",
                         example: "FII +₹3,114.68 Cr and DII −₹392.20 Cr means foreigners bought while domestic institutions sold." }}
                  tone={(d.flows?.dii_net_cr || 0) >= 0 ? "up" : "down"} />
          <Metric label="Combined net" value={signed(d.flows?.combined_net_cr, 2)} sub={d.flows?.regime}
                  tip={{ meaning: "FII and DII net flows added together. This is the only rupee-denominated measure on this panel.",
                         formula: "Combined = FII net + DII net" }}
                  tone={(d.flows?.combined_net_cr || 0) >= 0 ? "up" : "down"} />
          <Metric label="Delivery participation" value={`${num(d.participation?.delivered_share_pct, 1)}%`}
                  tip={{ meaning: "Turnover-weighted share of tracked equities with delivery of at least 55% — i.e. buyers took ownership rather than trading intraday.",
                         example: "47.7% delivered against 6.1% churn is a moderately conviction-led session." }}
                  sub={`${num(d.participation?.universe, 0)} tracked stocks · ${num(d.participation?.churn_share_pct, 1)}% churn`} />
        </div>
        <Note>{d.flows?.note}</Note>
      </Panel>

      <div className="grid lg:grid-cols-[1.15fr_1fr] gap-3">
        <Panel title="Headline tone" sub="A financial-sentiment model applied to public RSS titles. It reads language, not truth.">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <Pill tone={d.news_tone?.engine === "finbert" ? "up" : "warn"}>
              {d.news_tone?.engine === "finbert" ? "FinBERT · CPU" : "Lexicon fallback"}
            </Pill>
            <span className="muted text-[11px]">{num(d.news_tone?.headlines_scored, 0)} headlines scored</span>
            <span className={`knum text-[12px] font-bold ml-auto ${(d.news_tone?.net_tone || 0) >= 0 ? "text-up" : "text-down"}`}>
              net tone {signed(d.news_tone?.net_tone, 3)}
            </span>
          </div>
          <div className="h-2 w-full rounded-full overflow-hidden flex" style={{ background: "var(--line)" }}>
            <div style={{ width: `${tonePos}%`, background: "var(--up)" }} />
            <div style={{ width: `${toneNeg}%`, background: "var(--down)" }} />
            <div style={{ width: `${Math.max(0, 100 - tonePos - toneNeg)}%`, background: "color-mix(in srgb, var(--muted) 35%, transparent)" }} />
          </div>
          <div className="flex justify-between muted text-[10.5px] mt-1.5 knum">
            <span className="text-up">{num(d.news_tone?.positive, 0)} positive</span>
            <span>{num(d.news_tone?.neutral, 0)} neutral</span>
            <span className="text-down">{num(d.news_tone?.negative, 0)} negative</span>
          </div>
          <div className="mt-3 space-y-1.5 max-h-[230px] overflow-y-auto pr-1">
            {(d.headlines || []).slice(0, 8).map((h) => (
              <a key={h.link} href={h.link} target="_blank" rel="noopener noreferrer"
                 className="block rounded-lg px-2.5 py-2 hover:opacity-90"
                 style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="flex items-start gap-2">
                  <span className={`chip !text-[8.5px] !py-0.5 shrink-0 ${h.label === "positive" ? "chip-live" : ""}`}
                        style={h.label === "negative" ? { color: "var(--down)", borderColor: "color-mix(in srgb, var(--down) 35%, var(--line))" } : undefined}>
                    {h.label}
                  </span>
                  <span className="text-[11.5px] leading-snug">{h.title}</span>
                </div>
                <div className="muted text-[9.5px] mt-1 truncate">{h.source} · {h.published}</div>
              </a>
            ))}
          </div>
          <Note>{d.news_tone?.note}</Note>
        </Panel>

        <Panel title="Quadrant distribution" sub="Each tracked stock is classified from price direction and delivery share.">
          <div className="space-y-2.5">
            {Object.entries(d.counts || {}).map(([k, v]) => {
              const q = QUADRANTS[k] || { label: k, tone: "neutral" as const, meaning: "" };
              const total = Object.values(d.counts || {}).reduce((a, b) => a + b, 0) || 1;
              return (
                <div key={k}>
                  <div className="flex items-center justify-between gap-2 text-[11.5px]">
                    <span className="font-semibold">{q.label}</span>
                    <span className="knum muted">{num(v, 0)}</span>
                  </div>
                  <div className="mt-1">
                    <Bar value={(v / total) * 100} tone={q.tone === "neutral" ? "accent" : q.tone} />
                  </div>
                  <div className="muted text-[10px] mt-0.5 leading-snug">{q.meaning}</div>
                </div>
              );
            })}
          </div>
          <Note>{d.participation?.method}</Note>
        </Panel>
      </div>

      <Panel
        title="Flow matrix — price × delivery × tone"
        sub="Delivery is the exchange's own print: the share of traded quantity that changed ownership. High delivery means someone wanted the stock, not just the tick."
        right={
          <select value={limit} onChange={(e) => { const n = Number(e.target.value); setLimit(n); run(n); }}
                  className="surface rounded-lg px-2.5 py-1.5 text-[11.5px]" style={{ color: "var(--ink)" }}>
            {[8, 12, 20, 30].map((n) => <option key={n} value={n}>Top {n}</option>)}
          </select>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] border-collapse">
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {["Stock", "Sector", "Day", "Delivery", "Delivery Z", "Vol ×", "Quadrant", "Flags"].map((h) => (
                  <th key={h} className={`table-head px-3 py-2 ${h === "Stock" || h === "Sector" || h === "Quadrant" || h === "Flags" ? "text-left" : "text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.matrix.map((r) => {
                const q = QUADRANTS[r.quadrant] || { label: r.quadrant, tone: "neutral" as const };
                return (
                  <tr key={r.symbol} className="table-row">
                    <td className="px-3 py-2.5">
                      <Link href={r.href} className="text-[12.5px] font-bold hover:underline">{r.symbol}</Link>
                      <div className="muted text-[10px] knum">{inr(r.last)}</div>
                    </td>
                    <td className="px-3 py-2.5 muted text-[11px] max-w-[170px] truncate">{r.sector || "—"}</td>
                    <td className={`px-3 py-2.5 text-right knum text-[12px] font-semibold ${(r.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(r.changepct)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[12px] font-bold">{num(r.delivery_pct, 1)}%</td>
                    <td className="px-3 py-2.5 text-right knum text-[12px]">
                      {r.delivery_z ? (
                        <span className={r.delivery_z.z >= 0 ? "text-up" : "text-down"}>{signed(r.delivery_z.z, 2)}</span>
                      ) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right knum text-[12px]">{num(r.volume_ratio, 2)}×</td>
                    <td className="px-3 py-2.5"><Pill tone={q.tone}>{q.label}</Pill></td>
                    <td className="px-3 py-2.5 text-[10.5px] muted max-w-[210px]">
                      {(r.divergence_flags || []).length ? r.divergence_flags.join(" · ") : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Note>{d.divergence_note}</Note>
      </Panel>

      <p className="muted text-[11px] leading-relaxed">{d.disclaimer}</p>
    </div>
  );
}
