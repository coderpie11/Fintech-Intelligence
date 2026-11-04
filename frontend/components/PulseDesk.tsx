"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { ErrorBox, MoverCard, PageHeader, RefreshButton, Skeleton } from "@/components/PageKit";
import Drawer from "@/components/Drawer";
import MetricTip from "@/components/MetricTip";

function envNum(e: any): number | null {
  return e && e.value != null ? e.value : null;
}

export default function PulseDesk() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loadedMs, setLoadedMs] = useState<number | null>(null);
  const [sector, setSector] = useState<string | null>(null);
  const [sectorData, setSectorData] = useState<any>(null);
  const [sectorErr, setSectorErr] = useState<string | null>(null);

  useEffect(() => {
    const t0 = performance.now();
    getJSON("/pulse")
      .then((r) => { setD(r); setLoadedMs(Math.round(performance.now() - t0)); })
      .catch((e) => setErr(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!sector) return;
    setSectorData(null); setSectorErr(null);
    getJSON(`/pulse/sector/${encodeURIComponent(sector)}`)
      .then(setSectorData)
      .catch((e) => setSectorErr(String(e.message || e)));
  }, [sector]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow={`4 PM Market X-Ray${d?.asof_date ? ` · ${d.asof_date}` : ""}`}
        title="Market Pulse"
        sub="Breadth, INDIA VIX regime, movers, volume/delivery accumulation shockers and clickable sector money-flow with every constituent. The payload is served from a warm in-process cache while quotes refresh in the background."
        right={<RefreshButton stage="equities" label="Recompute" />}
      />

      {err && <ErrorBox message={err} stage="pulse" />}
      {!d && !err && <Skeleton rows={10} />}

      {d && (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="chip chip-live !text-[10px]">instant pulse</span>
            <span className="muted text-[10.5px]">
              served in {loadedMs ?? "—"} ms · as of {d.asof_date || "latest session"} · background quote refresh
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 mb-5">
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Market status" tip={{
                  meaning: "The exchange session state from the platform clock: pre-open, live, closed or weekend. Prices outside a live session are the last close.",
                }}>Market status</MetricTip>
              </div>
              <div className="text-[15px] font-black mt-1">{d.market_status?.value}</div>
              <div className="muted text-[10px]">{d.mood_line?.value}</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Breadth" tip={{
                  meaning: "How many tracked stocks advanced versus declined. Broad participation matters more than a single large stock moving an index.",
                }}>Breadth</MetricTip>
              </div>
              <div className="knum text-[18px] font-black mt-1 text-up">⬆ {d.breadth?.advances}</div>
              <div className="knum text-[11px] text-down">⬇ {d.breadth?.declines} · flat {d.breadth?.unchanged}</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="A/D ratio" tip={{
                  meaning: "Advance-decline ratio: advancing stocks divided by declining stocks. Above 1 means more names rose than fell.",
                  formula: "A/D = Advances ÷ Declines",
                  example: "96 advances and 152 declines gives 0.63 — a weak tape even if the index is flat.",
                }}>A/D ratio</MetricTip>
              </div>
              <div className="knum text-[18px] font-black mt-1">{d.breadth?.advance_decline_ratio}×</div>
              <div className="muted text-[10px]">of {d.breadth?.universe} tracked stocks</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="INDIA VIX" tip={{
                  meaning: "India's implied-volatility index, computed from NIFTY option prices. It is the market's priced expectation of near-term movement, not a direction call.",
                  example: "A VIX of 15.65 implies roughly a 15.65% annualised move in NIFTY; higher readings mean options are pricing more uncertainty.",
                }}>INDIA VIX</MetricTip>
              </div>
              <div className="knum text-[18px] font-black mt-1">{envNum(d.india_vix)?.toFixed(2) ?? "—"}</div>
              <div className="muted text-[10px]">{d.vix_regime?.value || "regime n/a"}</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Shockers" tip={{
                  meaning: "Stocks whose volume or delivery today was far above their own recent normal. A shock is an attention flag, not a conclusion.",
                }}>Shockers</MetricTip>
              </div>
              <div className="knum text-[18px] font-black mt-1">{(d.volume_shockers?.length || 0) + (d.delivery_shockers?.length || 0)}</div>
              <div className="muted text-[10px]">volume + delivery flags</div>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-6 mb-8">
            <div>
              <h2 className="text-[15px] font-extrabold mb-3 text-up">Top gainers</h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {d.top_gainers?.slice(0, 8).map((m: any) => <MoverCard key={m.symbol} mover={m} />)}
              </div>
            </div>
            <div>
              <h2 className="text-[15px] font-extrabold mb-3 text-down">Top losers</h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {d.top_losers?.slice(0, 8).map((m: any) => <MoverCard key={m.symbol} mover={m} />)}
              </div>
            </div>
          </div>

          <h2 className="text-[15px] font-extrabold mb-1">Sector money-flow</h2>
          <p className="muted text-[11px] mb-3">Click any sector to open its full constituent table.</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-8">
            {d.sector_flows?.map((s: any) => (
              <button key={s.sector} onClick={() => setSector(s.sector)}
                      className="card p-3.5 text-left hover:opacity-90 transition-opacity">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-bold">{s.sector}</span>
                  <span className={`knum text-[13px] font-black ${s.avg_change >= 0 ? "text-up" : "text-down"}`}>
                    {s.avg_change > 0 ? "+" : ""}{s.avg_change}%
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2 muted text-[10.5px]">
                  <span>⬆ {s.advance} · ⬇ {s.decline}</span>
                  <span>{s.count} stocks</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden mt-2" style={{ background: "var(--line)" }}>
                  <div style={{ width: `${(s.advance / Math.max(s.count, 1)) * 100}%`, background: "var(--up)" }} className="h-full" />
                </div>
              </button>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-4 mb-8">
            <div>
              <h2 className="text-[15px] font-extrabold mb-3">5× volume shockers</h2>
              <div className="card overflow-hidden">
                {(d.volume_shockers || []).length === 0 && <div className="p-4 muted text-[12px]">No stock crossed 1.8× its 20-day average volume today.</div>}
                {d.volume_shockers?.map((s: any) => (
                  <Link key={s.symbol} href={s.href} className="table-row flex items-center gap-3 px-4 py-2.5">
                    <span className="text-[12.5px] font-bold w-24">{s.symbol}</span>
                    <span className="muted text-[10.5px] flex-1 truncate">{s.name}</span>
                    <span className="knum text-[11.5px]">{s.volume_ratio?.toFixed(2)}× vol</span>
                    <span className={`knum text-[11.5px] font-bold ${(s.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(s.changepct)}</span>
                  </Link>
                ))}
              </div>
            </div>
            <div>
              <h2 className="text-[15px] font-extrabold mb-3">Delivery accumulation</h2>
              <div className="card overflow-hidden">
                {(d.delivery_shockers || []).length === 0 && <div className="p-4 muted text-[12px]">No high-delivery positive close cleared the 55% threshold.</div>}
                {d.delivery_shockers?.map((s: any) => (
                  <Link key={s.symbol} href={s.href} className="table-row flex items-center gap-3 px-4 py-2.5">
                    <span className="text-[12.5px] font-bold w-24">{s.symbol}</span>
                    <span className="muted text-[10.5px] flex-1 truncate">{s.name}</span>
                    <span className="knum text-[11.5px]">{s.delivery_pct?.toFixed(1)}% del</span>
                    <span className={`knum text-[11.5px] font-bold ${(s.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(s.changepct)}</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          <h2 className="text-[15px] font-extrabold mb-3">Action items — the real calendar</h2>
          <div className="card mb-8">
            {d.action_items?.slice(0, 12).map((e: any, i: number) => (
              <div key={i} className="table-row px-5 py-3 flex flex-wrap gap-x-4 gap-y-1 items-center">
                <Link href={e.symbol ? `/stocks/${e.symbol}` : "#"} className="text-[13px] font-bold hover:underline w-20">
                  {e.symbol}
                </Link>
                <span className="text-[12.5px] flex-1 truncate">{e.purpose}</span>
                <span className="muted text-[11.5px]">{e.ex_date}</span>
              </div>
            ))}
          </div>

          <h2 className="text-[15px] font-extrabold mb-3">Index scoreboard</h2>
          <div className="grid sm:grid-cols-3 gap-3">
            {d.indices_modal?.map((i: any) => (
              <Link key={i.name} href={`/indices/${i.slug}`} className="card p-4 hover:opacity-90">
                <div className="text-[12.5px] font-bold">{i.name}</div>
                <div className={`knum text-[13px] font-bold mt-1 ${i.changepct > 0 ? "text-up" : "text-down"}`}>
                  {pct(i.changepct)}
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      <Drawer open={!!sector} onClose={() => setSector(null)} width={980}
              eyebrow="Sector constituents" title={sector || "Sector"}>
        {sectorErr && <div className="text-[12px] text-down">{sectorErr}</div>}
        {!sectorData && !sectorErr && <Skeleton rows={6} />}
        {sectorData && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 text-[11.5px]">
              <span className="chip !text-[10px]">{sectorData.count} stocks</span>
              <span className="chip !text-[10px] text-up">⬆ {sectorData.advances}</span>
              <span className="chip !text-[10px] text-down">⬇ {sectorData.declines}</span>
              <span className={`chip !text-[10px] ${sectorData.avg_change >= 0 ? "text-up" : "text-down"}`}>
                avg {pct(sectorData.avg_change)}
              </span>
            </div>
            <div className="card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] border-collapse">
                  <thead>
                    <tr style={{ background: "var(--surface-2)" }}>
                      <th className="table-head text-left px-3 py-2">Stock</th>
                      <th className="table-head text-right px-2 py-2">Price</th>
                      <th className="table-head text-right px-2 py-2">1D</th>
                      <th className="table-head text-right px-2 py-2">1W</th>
                      <th className="table-head text-right px-2 py-2">1M</th>
                      <th className="table-head text-right px-2 py-2">1Y</th>
                      <th className="table-head text-right px-2 py-2">M-cap</th>
                      <th className="table-head text-right px-2 py-2">P/E</th>
                      <th className="table-head text-right px-3 py-2">ROE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sectorData.constituents.map((s: any) => (
                      <tr key={s.symbol} className="table-row">
                        <td className="px-3 py-2">
                          <Link href={s.href} className="text-[12px] font-bold hover:underline">{s.symbol}</Link>
                          <div className="muted text-[9.5px] truncate max-w-[180px]">{s.name}</div>
                        </td>
                        <td className="px-2 py-2 text-right knum text-[11.5px]">{s.last != null ? inr(s.last) : "—"}</td>
                        <td className={`px-2 py-2 text-right knum text-[11px] ${(s.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(s.changepct)}</td>
                        <td className="px-2 py-2 text-right knum text-[11px]">{s.return_1w != null ? pct(s.return_1w) : "—"}</td>
                        <td className="px-2 py-2 text-right knum text-[11px]">{s.return_1m != null ? pct(s.return_1m) : "—"}</td>
                        <td className="px-2 py-2 text-right knum text-[11px]">{s.return_1y != null ? pct(s.return_1y) : "—"}</td>
                        <td className="px-2 py-2 text-right knum text-[11px]">{s.market_cap != null ? `₹${(s.market_cap / 1e7).toFixed(0)} Cr` : "—"}</td>
                        <td className="px-2 py-2 text-right knum text-[11px]">{s.pe != null ? s.pe.toFixed(1) : "—"}</td>
                        <td className="px-3 py-2 text-right knum text-[11px]">{s.roe != null ? `${s.roe.toFixed(1)}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
