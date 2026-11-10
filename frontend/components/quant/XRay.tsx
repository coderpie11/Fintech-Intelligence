"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { Bar, ErrLine, Loading, Metric, Note, Panel, Pill, num, signed } from "./Kit";

type Sector = {
  sector: string;
  count: number;
  advance: number;
  decline: number;
  avg_change_pct: number;
  delivered_turnover_share_pct: number;
  churn_turnover_share_pct: number;
  participation_tilt: number;
  turnover_cr: number;
};

type XRow = {
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
  shock_type?: string;
};

type XRayData = {
  asof: string;
  session_date?: string | null;
  session_label?: string | null;
  market_status: { value: string; status: string; note: string };
  chain: {
    step_1_official_flows: {
      available: boolean; asof: string | null;
      fii_net_cr: number | null; dii_net_cr: number | null;
      combined_net_cr: number | null; regime: string; note: string;
    };
    step_2_sector_tilt: {
      leaders: Sector[]; laggards: Sector[]; method: string;
    };
    step_3_stock_confirmation: { rows: XRow[]; note: string };
    step_4_context: {
      breadth: { advances: number; declines: number; unchanged: number; universe: number; advance_decline_ratio: number };
      india_vix: { value: number | null; status: string; note: string };
      vix_regime: { value: string; status: string; note: string };
      indices: { slug: string; name: string; last: number | null; changepct: number | null }[];
    };
  };
  sectors: Sector[];
  volume_shockers: XRow[];
  top_gainers: XRow[];
  top_losers: XRow[];
  action_items: { symbol: string; company: string; purpose: string; ex_date: string }[];
  synthesis: string[];
  footer_note: string;
};

const SECTOR_GROUPS: { key: string; label: string; words: string[] }[] = [
  { key: "all", label: "All Sectors", words: [] },
  { key: "banking", label: "Banking & Finance", words: ["bank", "financ", "nbfc", "insur"] },
  { key: "it", label: "IT & Tech", words: ["it ", "software", "technolog", "telecom", "digital"] },
  { key: "defense", label: "Defense & Capex", words: ["defen", "capital goods", "infra", "ship", "aerospace", "engineering"] },
  { key: "auto", label: "Auto & Retail", words: ["auto", "retail", "consumer", "apparel", "textile"] },
  { key: "energy", label: "Energy & Metals", words: ["energy", "power", "metal", "oil", "gas", "mining"] },
  { key: "fmcg", label: "FMCG & Pharma", words: ["fmcg", "pharma", "health", "food", "household"] },
];

function matchesSector(sector: string | null, key: string): boolean {
  if (key === "all") return true;
  const s = (sector || "").toLowerCase();
  const group = SECTOR_GROUPS.find((g) => g.key === key);
  return !!group && group.words.some((w) => s.includes(w));
}

function SectorRow({ s, side }: { s: Sector; side: "up" | "down" }) {
  const v = Math.min(100, Math.abs(s.participation_tilt));
  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between gap-2 text-[11.5px]">
        <span className="font-semibold truncate">{s.sector}</span>
        <span className={`knum font-bold ${side === "up" ? "text-up" : "text-down"}`}>{signed(s.participation_tilt, 1)} pp</span>
      </div>
      <div className="mt-1"><Bar value={v} tone={side} /></div>
      <div className="muted text-[9.5px] mt-0.5 knum">
        {s.count} stocks · {s.advance} adv / {s.decline} dec · ₹{num(s.turnover_cr, 0)} Cr turnover
      </div>
    </div>
  );
}

export default function XRay() {
  const [d, setD] = useState<XRayData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter] = useState("all");

  const filteredShockers = useMemo(
    () => (d?.volume_shockers || []).filter((r) => matchesSector(r.sector, sectorFilter)),
    [d, sectorFilter]);
  const filteredConfirmations = useMemo(
    () => (d?.chain?.step_3_stock_confirmation?.rows || []).filter((r) => matchesSector(r.sector, sectorFilter)),
    [d, sectorFilter]);

  const run = () => {
    setErr(null);
    getJSON<XRayData>("/quant-hub/xray")
      .then(setD)
      .catch((e) => setErr(String(e.message || e).slice(0, 200)));
  };
  useEffect(() => { run(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  if (err) return <ErrLine message={`The X-Ray could not load: ${err}`} onRetry={run} />;
  if (!d) return <Loading label="Reconstructing the 4 PM money-flow chain from the stored session…" />;

  const s1 = d.chain?.step_1_official_flows;
  const s2 = d.chain?.step_2_sector_tilt;
  const s3 = d.chain?.step_3_stock_confirmation;
  const s4 = d.chain?.step_4_context;
  const breadth = s4?.breadth;

  return (
    <div className="space-y-3">
      <div className="rounded-xl px-4 py-3"
           style={{ border: "1px solid color-mix(in srgb, var(--accent) 40%, var(--line))",
                    background: "color-mix(in srgb, var(--accent) 8%, transparent)" }}>
        <div className="text-[12.5px] font-bold leading-snug">
          📅 Official Session Data: Showing post-market institutional money flow for{" "}
          <span className="accent">{d.session_label || d.session_date || d.asof}</span>.
        </div>
        <div className="muted text-[11px] leading-snug mt-1">
          (Note: On weekends or before 4:30 PM IST on trading days, this displays the latest
          completed market session&apos;s closing data.)
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mr-1">Session sector filter</span>
        {SECTOR_GROUPS.map((g) => (
          <button key={g.key} onClick={() => setSectorFilter(g.key)}
                  className={`chip !text-[10px] ${sectorFilter === g.key ? "chip-active" : ""}`}>
            {g.label}
          </button>
        ))}
      </div>

      <Panel
        title="4 PM Market X-Ray — the money-flow chain"
        sub="Four steps, in order: official rupee flows, sector participation tilt, stock-level confirmation, then market context. Each step states what it can and cannot prove."
        right={<Pill tone="accent">{d.asof} · {d.market_status?.value}</Pill>}
      >
        <ol className="space-y-1.5">
          {(d.synthesis || []).map((line, i) => (
            <li key={i} className="flex gap-2 text-[12.5px] leading-relaxed">
              <span className="knum accent font-bold shrink-0">{i + 1}.</span>
              <span>{line}</span>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-2.5">
        <Metric label="FII / FPI net" value={signed(s1?.fii_net_cr, 2)} sub="₹ crore, provisional"
                tip={{ meaning: "Foreign portfolio investors' net cash-market flow, from the exchanges' provisional print. It is the only rupee figure in the chain.",
                       formula: "FII net = FII buys − FII sells" }}
                tone={(s1?.fii_net_cr || 0) >= 0 ? "up" : "down"} />
        <Metric label="DII net" value={signed(s1?.dii_net_cr, 2)} sub="₹ crore, provisional"
                tip={{ meaning: "Domestic institutional investors' net cash-market flow for the same session.", formula: "DII net = DII buys − DII sells" }}
                tone={(s1?.dii_net_cr || 0) >= 0 ? "up" : "down"} />
        <Metric label="Advance / decline" value={num(breadth?.advance_decline_ratio, 2)}
                tip={{ meaning: "Advancing stocks divided by declining stocks across the tracked universe. Above 1 means participation was broad and positive.",
                       formula: "A/D = Advances ÷ Declines",
                       example: "96 advances and 152 declines gives 0.63 — a weak tape." }}
                sub={`${num(breadth?.advances, 0)} up · ${num(breadth?.declines, 0)} down of ${num(breadth?.universe, 0)}`}
                tone={(breadth?.advance_decline_ratio || 0) >= 1 ? "up" : "down"} />
        <Metric label="INDIA VIX" value={num(s4?.india_vix?.value, 2)}
                tip={{ meaning: "The NSE's implied-volatility index from NIFTY options — the market's priced expectation of near-term movement, not a direction.",
                       example: "15.65 implies roughly a 15.65% annualised move in NIFTY." }}
                sub={`${s4?.vix_regime?.value || "—"} volatility regime`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <Panel title="Step 1 — Official rupee flows" sub="The only step with actual rupee amounts. Everything after this is participation, not money.">
          <div className="rounded-lg px-3 py-2.5 mb-2.5"
               style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
            <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Combined institutional net</div>
            <div className={`knum text-[22px] font-black ${(s1?.combined_net_cr || 0) >= 0 ? "text-up" : "text-down"}`}>
              {signed(s1?.combined_net_cr, 2)} <span className="text-[12px] muted font-semibold">₹ crore</span>
            </div>
            <div className="muted text-[11px] mt-0.5">{s1?.regime}</div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="FII net" value={signed(s1?.fii_net_cr, 2)} tone={(s1?.fii_net_cr || 0) >= 0 ? "up" : "down"} />
            <Metric label="DII net" value={signed(s1?.dii_net_cr, 2)} tone={(s1?.dii_net_cr || 0) >= 0 ? "up" : "down"} />
          </div>
          <Note>{s1?.note}</Note>
        </Panel>

        <Panel title="Step 2 — Sector participation tilt" sub="Delivery-weighted participation in percentage points. A tilt is not a rupee flow.">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1">Strongest delivery tilt</div>
              {(s2?.leaders || []).slice(0, 5).map((s) => <SectorRow key={s.sector} s={s} side="up" />)}
            </div>
            <div>
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1">Weakest delivery tilt</div>
              {(s2?.laggards || []).slice(0, 5).map((s) => <SectorRow key={s.sector} s={s} side="down" />)}
              {!s2?.laggards?.length && <p className="muted text-[11px]">No sector had a negative tilt with enough breadth.</p>}
            </div>
          </div>
          <Note>{s2?.method}</Note>
        </Panel>
      </div>

      <Panel title="Step 3 — Stock-level confirmation" sub="Names where delivery and price agree with the sector tilt. Delivery Z compares the stock with its own 45-session history.">
        <div className="scroll-x">
          <table className="w-full min-w-[760px] border-collapse">
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {["Stock", "Sector", "Day", "Delivery", "Delivery Z", "Vol ×", "P/E"].map((h) => (
                  <th key={h} className={`table-head px-3 py-2 ${h === "Stock" || h === "Sector" ? "text-left" : "text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredConfirmations.map((r) => (
                <tr key={r.symbol} className="table-row">
                  <td className="px-3 py-2.5">
                    <Link href={r.href} className="text-[12.5px] font-bold hover:underline">{r.symbol}</Link>
                    <div className="muted text-[10px] knum">{inr(r.last)}</div>
                  </td>
                  <td className="px-3 py-2.5 muted text-[11px] max-w-[180px] truncate">{r.sector || "—"}</td>
                  <td className={`px-3 py-2.5 text-right knum text-[12px] font-semibold ${(r.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(r.changepct)}</td>
                  <td className="px-3 py-2.5 text-right knum text-[12px] font-bold">{num(r.delivery_pct, 1)}%</td>
                  <td className="px-3 py-2.5 text-right knum text-[12px]">{r.delivery_z ? <span className={r.delivery_z.z >= 0 ? "text-up" : "text-down"}>{signed(r.delivery_z.z, 2)}</span> : "—"}</td>
                  <td className="px-3 py-2.5 text-right knum text-[12px]">{num(r.volume_ratio, 2)}×</td>
                  <td className="px-3 py-2.5 text-right knum text-[12px]">{num(r.pe, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note>{s3?.note}</Note>
      </Panel>

      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-3">
        <Panel title="Volume shockers" sub="Turnover far above the stock's own recent average, with the direction and delivery that came with it.">
          <div className="scroll-x">
            <table className="w-full min-w-[620px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  {["Stock", "Vol ×", "Day", "Delivery", "Read"].map((h) => (
                    <th key={h} className={`table-head px-3 py-2 ${h === "Stock" || h === "Read" ? "text-left" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredShockers.map((r) => (
                  <tr key={r.symbol} className="table-row">
                    <td className="px-3 py-2.5">
                      <Link href={r.href} className="text-[12.5px] font-bold hover:underline">{r.symbol}</Link>
                    </td>
                    <td className="px-3 py-2.5 text-right knum text-[12px] font-bold accent">{num(r.volume_ratio, 2)}×</td>
                    <td className={`px-3 py-2.5 text-right knum text-[12px] ${(r.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(r.changepct)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[12px]">{num(r.delivery_pct, 1)}%</td>
                    <td className="px-3 py-2.5 text-[10.5px] muted max-w-[240px]">{r.shock_type || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Step 4 — Market context" sub="Breadth, volatility and the index tape that the flow numbers sit inside.">
          <div className="grid grid-cols-2 gap-2">
            <Metric label="Advances" value={num(breadth?.advances, 0)} tone="up" />
            <Metric label="Declines" value={num(breadth?.declines, 0)} tone="down" />
            <Metric label="Unchanged" value={num(breadth?.unchanged, 0)} />
            <Metric label="A/D ratio" value={num(breadth?.advance_decline_ratio, 2)} tone={(breadth?.advance_decline_ratio || 0) >= 1 ? "up" : "down"} />
          </div>
          <div className="mt-3 space-y-1">
            {(s4?.indices || []).map((ix) => (
              <Link key={ix.slug} href={`/indices/${ix.slug}`}
                    className="flex items-center justify-between gap-2 py-1.5 hover:opacity-80 text-[12px]">
                <span className="font-semibold truncate">{ix.name}</span>
                <span className="knum muted">{num(ix.last, 2)}</span>
                <span className={`knum font-bold ${(ix.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(ix.changepct)}</span>
              </Link>
            ))}
          </div>
          <Note>{s4?.india_vix?.note} {s4?.vix_regime?.note}</Note>
        </Panel>
      </div>

      {(d.action_items || []).length > 0 && (
        <Panel title="Corporate actions in force" sub="Ex-dates and purposes from the exchange calendar — factual events, not trade ideas.">
          <div className="grid sm:grid-cols-2 gap-1.5">
            {d.action_items.map((a) => (
              <div key={`${a.symbol}-${a.ex_date}-${a.purpose}`} className="rounded-lg px-3 py-2 flex items-start gap-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <Pill tone="accent">{a.ex_date}</Pill>
                <div className="min-w-0">
                  <Link href={`/stocks/${a.symbol}`} className="text-[11.5px] font-bold hover:underline">{a.symbol}</Link>
                  <div className="muted text-[10.5px] leading-snug">{a.purpose}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <p className="muted text-[11px] leading-relaxed">{d.footer_note}</p>
    </div>
  );
}
