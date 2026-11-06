"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton } from "@/components/PageKit";
import MetricTip from "@/components/MetricTip";

const SUB_TIPS: Record<string, { meaning: string; example?: string }> = {
  QIB: {
    meaning: "Qualified Institutional Buyers — mutual funds, insurers, banks and foreign portfolio investors. Their book is the institutional vote on the issue.",
  },
  bNII: {
    meaning: "Non-institutional bidders applying above ₹10 lakh (big NII). Typically high-net-worth investors bidding for listing gains.",
  },
  sNII: {
    meaning: "Non-institutional bidders applying between ₹2 lakh and ₹10 lakh (small NII).",
  },
  Retail: {
    meaning: "Individual bidders applying up to ₹2 lakh. Retail subscription is the most sentiment-driven slice of the book.",
  },
  Total: {
    meaning: "Total subscription across all categories, expressed as a multiple of the shares offered.",
    example: "12.40× means bids were received for 12.4 times the issue size.",
  },
};

export type IpoRow = {
  id: number; slug: string; name: string; symbol?: string;
  board: string; status: string;
  open?: string; close?: string; allotment?: string; listing?: string;
  price: Env; price_band: Env; lot: Env; min_investment: Env;
  issue_size: Env; registrar: Env; registrar_url?: string;
  fresh_pct: Env; ofs_pct: Env;
  subscription: Record<string, Env>;
  gmp: Env; gmp_pct: Env; gmp_trend: string; fire_rating: Env;
  est_listing_price: Env; est_listing_gain_rs: Env; est_listing_gain_pct: Env;
  realised_gain_pct: Env;
  preipo_price: Env; brlm: string[];
  anchor_lockin_30?: string; anchor_lockin_90?: string;
  note?: string;
  performance: { last: Env; changepct: Env; source?: string };
  ig_url?: string; live?: boolean; source?: string; updated_on?: string;
  href: string;
};

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

function money(v: number | null, suffix = ""): string {
  if (v == null) return "—";
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}${suffix}`;
}

const STATUS_META: Record<string, { label: string; dot: string; pill: string }> = {
  LIVE: { label: "Open Now", dot: "#2dd4bf", pill: "bg-teal-500/15 text-teal-300 border-teal-500/40" },
  TODAY: { label: "Opening / Closing Today", dot: "#fbbf24", pill: "bg-amber-500/15 text-amber-300 border-amber-500/40" },
  UPCOMING: { label: "Upcoming", dot: "#a78bfa", pill: "bg-purple-500/15 text-purple-300 border-purple-500/40" },
  CLOSED: { label: "Closed", dot: "#a1a1aa", pill: "bg-zinc-500/15 text-zinc-300 border-zinc-500/40" },
  LISTED: { label: "Listed", dot: "#34d399", pill: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40" },
  LOSS: { label: "Listed in Loss", dot: "#fb7185", pill: "bg-rose-500/15 text-rose-400 border-rose-500/40" },
};

function StatusDot({ status, gain, today }: { status: string; gain?: number | null; today?: boolean }) {
  const key = status === "LISTED" && gain != null && gain < 0
    ? "LOSS"
    : today ? "TODAY" : status;
  const meta = STATUS_META[key] || STATUS_META.CLOSED;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9.5px] font-semibold ${meta.pill}`}>
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: meta.dot }} />
      {meta.label}
    </span>
  );
}

function Fire({ env }: { env?: Env }) {
  const v = Math.round(envNum(env) || 0);
  return (
    <span className="inline-flex items-center gap-0.5" title={`${v || 0} of 5 demand rating`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className="text-[11px]" style={{ opacity: i <= v ? 1 : 0.18 }}>🔥</span>
      ))}
    </span>
  );
}

function SubTooltip({ sub, total }: { sub: Record<string, Env>; total: number | null }) {
  return (
    <div className="relative inline-block group">
      <span className={`knum text-[12px] font-bold ${total == null ? "muted" : total >= 1 ? "text-up" : ""}`}>
        {total != null ? `${total.toFixed(2)}×` : "—"}
      </span>
      <div className="pointer-events-none absolute right-0 top-full z-30 mt-1 hidden w-[190px] rounded-lg p-2.5 text-left shadow-xl group-hover:block"
           style={{ background: "var(--surface)", border: "1px solid var(--line)" }}>
        {[["QIB", "qib"], ["NII", "nii"], ["Retail", "retail"]].map(([label, key]) => {
          const v = envNum(sub?.[key]) ?? (key === "nii"
            ? ((envNum(sub?.bnii) || 0) + (envNum(sub?.snii) || 0) || null)
            : null);
          return (
            <div key={key} className="flex justify-between gap-2 text-[10.5px]">
              <span className="muted">{label}</span>
              <span className="knum font-semibold">{v != null ? `${v.toFixed(2)}×` : "—"}</span>
            </div>
          );
        })}
        <div className="muted text-[9px] mt-1 leading-snug">Bids received ÷ shares reserved for that category.</div>
      </div>
    </div>
  );
}

function GmpChart({ history }: { history: { date: string; gmp: number }[] }) {
  const pts = (history || []).filter((p) => p.gmp != null);
  if (pts.length < 2) {
    return <div className="muted text-[11.5px] py-8 text-center">No day-wise GMP history was published for this issue.</div>;
  }
  const w = 760, h = 240, pad = 36;
  const vals = pts.map((p) => p.gmp);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (w - pad * 2);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.gmp)}`).join(" ");
  const area = `${line} L${x(pts.length - 1)},${h - pad} L${x(0)},${h - pad} Z`;
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={pad} x2={w - pad} y1={pad + f * (h - pad * 2)}
                y2={pad + f * (h - pad * 2)} stroke="var(--line)" strokeDasharray="3 4" />
        ))}
        <path d={area} fill="color-mix(in srgb, var(--accent) 12%, transparent)" />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2.2" />
        {pts.map((p, i) => (
          <circle key={`${p.date}-${i}`} cx={x(i)} cy={y(p.gmp)} r="2.6"
                  fill="var(--surface)" stroke="var(--accent)" strokeWidth="1.6">
            <title>{`${fmtDate(p.date)} · ₹${p.gmp}`}</title>
          </circle>
        ))}
        <text x={pad} y={h - 8} fontSize="10" fill="var(--muted)">{fmtDate(pts[0].date)}</text>
        <text x={w - pad} y={h - 8} fontSize="10" textAnchor="end" fill="var(--muted)">{fmtDate(pts[pts.length - 1].date)}</text>
        <text x={pad - 4} y={pad + 4} fontSize="10" textAnchor="end" fill="var(--muted)">₹{max.toFixed(0)}</text>
        <text x={pad - 4} y={h - pad} fontSize="10" textAnchor="end" fill="var(--muted)">₹{min.toFixed(0)}</text>
      </svg>
      <div className="muted text-[10px] text-center">Day-by-day grey-market premium. Unofficial and unregulated.</div>
    </div>
  );
}

export function IpoList() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const [board, setBoard] = useState("all");
  const [result, setResult] = useState("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    setErr(null);
    const p = new URLSearchParams({ filter, board });
    if (q.trim()) p.set("q", q.trim());
    getJSON(`/ipos?${p}`).then(setData).catch((e) => setErr(String(e.message || e)));
  }, [filter, board, q]);

  const counts = data?.filter_counts || {};
  const summary = data?.summary || {};
  const rows: IpoRow[] = data?.ipos || [];
  const todayIso = new Date().toISOString().slice(0, 10);
  const shownRows = useMemo(() => rows.filter((r) => {
    if (filter === "today" && r.open !== todayIso && r.close !== todayIso) return false;
    if (filter === "listed" && result !== "all") {
      const gain = envNum(r.realised_gain_pct) ?? envNum(r.performance?.changepct)
        ?? envNum(r.est_listing_gain_pct);
      if (gain == null) return false;
      return result === "gain" ? gain > 0 : gain < 0;
    }
    return true;
  }), [rows, filter, result, todayIso]);

  return (
    <div className="mx-auto max-w-[1680px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="IPO · live GMP · mainboard & SME"
        title="Live IPO GMP Dashboard"
        sub="Live grey-market premium, fire rating, subscription, issue structure and day-wise GMP history, merged with exchange offer-document facts. GMP is unofficial and can vanish on listing day."
        right={<RefreshButton stage="events" label="Refresh live GMP" />}
      />

      {err && <ErrorBox message={err} stage="ipos" />}
      {!data && !err && <Skeleton rows={9} />}

      {data && (
        <>
          {/* summary strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Open now</div>
              <div className="knum text-[26px] font-black mt-0.5 text-up">{summary.open_now ?? 0}</div>
              <div className="muted text-[10px]">issues accepting bids</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Upcoming</div>
              <div className="knum text-[26px] font-black mt-0.5" style={{ color: "var(--accent)" }}>{summary.upcoming ?? 0}</div>
              <div className="muted text-[10px]">opens in the next few weeks</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Listed this quarter</div>
              <div className="knum text-[26px] font-black mt-0.5">{summary.listed_quarter ?? 0}</div>
              <div className="muted text-[10px]">with realised listing prints</div>
            </div>
            <div className="card p-3.5">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Avg listing gain</div>
              <div className={`knum text-[26px] font-black mt-0.5 ${(summary.avg_listing_gain_pct || 0) >= 0 ? "text-up" : "text-down"}`}>
                {summary.avg_listing_gain_pct != null ? `${summary.avg_listing_gain_pct > 0 ? "+" : ""}${summary.avg_listing_gain_pct}%` : "—"}
              </div>
              <div className="muted text-[10px]">this quarter, realised prints</div>
            </div>
          </div>

          {/* professional dropdown filters */}
          <div className="sticky top-0 z-20 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 mb-3 backdrop-blur"
               style={{ background: "color-mix(in srgb, var(--bg) 88%, transparent)", borderBottom: "1px solid var(--line)" }}>
            <div className="flex flex-wrap items-center gap-2">
              <label className="block">
                <span className="muted text-[8.5px] font-bold uppercase tracking-[0.13em] block mb-0.5">Board</span>
                <select value={board} onChange={(e) => setBoard(e.target.value)}
                        className="surface rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold"
                        style={{ color: "var(--ink)" }}>
                  <option value="all">All Boards (Mainboard + SME)</option>
                  <option value="mainboard">Mainboard Only</option>
                  <option value="sme">SME Only</option>
                </select>
              </label>
              <label className="block">
                <span className="muted text-[8.5px] font-bold uppercase tracking-[0.13em] block mb-0.5">IPO Status</span>
                <select value={filter} onChange={(e) => { setFilter(e.target.value); if (e.target.value !== "listed") setResult("all"); }}
                        className="surface rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold"
                        style={{ color: "var(--ink)" }}>
                  <option value="all">All IPOs (Default)</option>
                  <option value="open">🟢 Open Now ({counts.open ?? 0})</option>
                  <option value="today">🟠 Closing Today / Opening Today</option>
                  <option value="upcoming">🟣 Upcoming IPOs ({counts.upcoming ?? 0})</option>
                  <option value="closed">⚪ Closed (Allotment Pending) ({counts.closed ?? 0})</option>
                  <option value="listed">📊 Listed Shares ({counts.listed ?? 0})</option>
                </select>
              </label>
              {filter === "listed" && (
                <label className="block">
                  <span className="muted text-[8.5px] font-bold uppercase tracking-[0.13em] block mb-0.5">Listing Result</span>
                  <select value={result} onChange={(e) => setResult(e.target.value)}
                          className={`surface rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold border ${result === "gain" ? "text-emerald-400 border-emerald-500/40" : result === "loss" ? "text-rose-400 border-rose-500/40" : ""}`}
                          style={{ color: result === "gain" ? "#34d399" : result === "loss" ? "#fb7185" : "var(--ink)" }}>
                    <option value="all">All Listed Shares</option>
                    <option value="gain">🟢 Listed in Profit (Positive Listing Gain &gt; 0%)</option>
                    <option value="loss">🔴 Listed in Loss (Negative Listing Return &lt; 0%)</option>
                  </select>
                </label>
              )}
              <div className="surface rounded-lg px-3 py-1.5 flex-1 min-w-[200px] max-w-sm ml-auto">
                <input value={q} onChange={(e) => setQ(e.target.value)}
                       placeholder="Search IPO company or symbol…"
                       className="w-full bg-transparent text-[12.5px] outline-none"
                       style={{ color: "var(--ink)" }} />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <span className="muted text-[11px]">
              {shownRows.length} of {data.total ?? rows.length} issues ·{" "}
              <span className="accent font-semibold">{data.feed_status?.value || "Live feed"}</span>
            </span>
            <span className="muted text-[10.5px]">Sort: status → newest listing</span>
          </div>

          <div className="card overflow-hidden">
            <div className="overflow-x-auto max-h-[70vh]">
              <table className="w-full min-w-[1520px] border-collapse">
                <thead className="sticky top-0 z-10">
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5 min-w-[230px]">IPO name &amp; board</th>
                    <th className="table-head text-right px-2.5 py-2.5">Price ₹</th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="GMP ₹" tip={{
                        meaning: "Grey-market premium: an unofficial, unregulated indication of what the unlisted shares trade at. It is not an exchange price and it can vanish on listing day.",
                      }}>GMP ₹</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Est. listing" tip={{
                        meaning: "Upper price band plus the current GMP. This is an implied listing price, not a forecast.",
                      }}>Est. listing</MetricTip>
                    </th>
                    <th className="table-head text-center px-2.5 py-2.5">
                      <MetricTip label="Fire rating" tip={{
                        meaning: "A 1-5 demand indicator built from GMP and subscription momentum. It is sentiment, not valuation.",
                      }}>Fire</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">Lot · Min ₹</th>
                    <th className="table-head text-right px-2.5 py-2.5">Issue size</th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Subscription" tip={SUB_TIPS.Total}>Sub</MetricTip>
                    </th>
                    <th className="table-head text-left px-3 py-2.5 min-w-[190px]">Dates</th>
                    <th className="table-head text-right px-3 py-2.5">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {shownRows.map((r) => {
                    const price = envNum(r.price);
                    const gmp = envNum(r.gmp);
                    const gmpPct = envNum(r.gmp_pct);
                    const est = envNum(r.est_listing_price);
                    const estPct = envNum(r.est_listing_gain_pct);
                    const lot = envNum(r.lot);
                    const minInv = envNum(r.min_investment);
                    const size = envNum(r.issue_size);
                    const freshRaw = envNum(r.fresh_pct);
                    const ofsRaw = envNum(r.ofs_pct);
                    const hasSplit = freshRaw != null && ofsRaw != null;
                    const fresh = freshRaw ?? 0;
                    const ofs = ofsRaw ?? 0;
                    const subTotal = envNum(r.subscription?.total);
                    const listed = r.status === "LISTED";
                    const perf = envNum(r.performance?.last);
                    const realised = envNum(r.realised_gain_pct) ?? envNum(r.performance?.changepct);
                    const isToday = r.open === todayIso || r.close === todayIso;
                    const accent = listed
                      ? ((realised || 0) >= 0 ? "#34d399" : "#fb7185")
                      : isToday ? "#fbbf24"
                      : r.status === "LIVE" ? "#2dd4bf"
                      : r.status === "UPCOMING" ? "#a78bfa" : "#a1a1aa";
                    return (
                      <tr key={r.id} className="table-row align-top"
                          style={{ borderLeft: `3px solid ${accent}` }}>
                        <td className="px-3 py-3">
                          <Link href={r.href} className="text-[12.5px] font-bold hover:underline leading-snug block">
                            {r.name}
                          </Link>
                          <div className="flex items-center gap-1.5 mt-1">
                            <span className="chip !text-[8.5px] !px-1.5 !py-0.5">{r.board === "SME" ? "SME" : "Mainboard"}</span>
                            <StatusDot status={r.status} gain={listed ? realised : null} today={isToday} />
                          </div>
                          {r.symbol && <div className="muted text-[9.5px] mt-1">{r.symbol}</div>}
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          <div className="knum text-[12.5px] font-bold">{price != null ? money(price) : "—"}</div>
                          <div className="muted text-[9.5px]">upper band</div>
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          {gmp != null ? (
                            <>
                              <div className="knum text-[12.5px] font-bold">{money(gmp)}</div>
                              <div className={`text-[9.5px] font-semibold ${(gmpPct || 0) >= 0 ? "text-up" : "text-down"}`}>
                                {gmpPct != null ? `${gmpPct > 0 ? "+" : ""}${gmpPct.toFixed(2)}%` : ""}
                              </div>
                              <div className={`text-[8.5px] mt-0.5 ${r.gmp_trend.includes("High") ? "text-up" : r.gmp_trend === "Discount" ? "text-down" : "muted"}`}>
                                {r.gmp_trend}
                              </div>
                            </>
                          ) : <span className="muted text-[11px]">No GMP</span>}
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          {listed && perf != null ? (
                            <>
                              <div className="knum text-[12.5px] font-bold">{money(perf)}</div>
                              <div className={`text-[9.5px] font-semibold ${(realised || 0) >= 0 ? "text-up" : "text-down"}`}>
                                {realised != null ? `${realised > 0 ? "+" : ""}${realised.toFixed(2)}%` : "listed"}
                              </div>
                              <div className="muted text-[8.5px]">realised</div>
                            </>
                          ) : est != null ? (
                            <>
                              <div className={`knum text-[12.5px] font-bold ${(estPct || 0) >= 0 ? "text-up" : "text-down"}`}>{money(est)}</div>
                              <div className={`text-[9.5px] font-semibold ${(estPct || 0) >= 0 ? "text-up" : "text-down"}`}>
                                {estPct != null ? `${estPct > 0 ? "+" : ""}${estPct.toFixed(2)}%` : ""}
                              </div>
                              <div className="muted text-[8.5px]">price + GMP</div>
                            </>
                          ) : <span className="muted text-[11px]">—</span>}
                        </td>
                        <td className="px-2.5 py-3 text-center"><Fire env={r.fire_rating} /></td>
                        <td className="px-2.5 py-3 text-right">
                          <div className="knum text-[11.5px] font-semibold">{lot != null ? `${lot.toLocaleString("en-IN")} sh` : "—"}</div>
                          <div className="muted text-[9.5px]">{minInv != null ? money(minInv) : "—"}</div>
                        </td>
                        <td className="px-2.5 py-3 text-right min-w-[110px]">
                          <div className="knum text-[11.5px] font-semibold">{size != null ? `₹${size.toLocaleString("en-IN")} Cr` : "—"}</div>
                          <div className="h-1.5 rounded-full overflow-hidden flex mt-1" style={{ background: "var(--line)" }}>
                            <div style={{ width: `${Math.min(fresh, 100)}%`, background: "var(--accent)" }} />
                            <div style={{ width: `${Math.min(ofs, 100 - Math.min(fresh, 100))}%`, background: "var(--warn)" }} />
                          </div>
                          <div className="muted text-[8.5px] mt-0.5">
                            {hasSplit ? `${fresh}% fresh · ${ofs}% OFS` : "fresh / OFS split not disclosed"}
                          </div>
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          <SubTooltip sub={r.subscription || {}} total={subTotal} />
                          <div className="muted text-[8.5px] mt-0.5">hover for QIB/NII</div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="grid grid-cols-[auto_1fr] gap-x-1.5 gap-y-0.5 text-[9.5px]">
                            <span className="muted">Open</span><span className="knum">{r.open ? fmtDate(r.open) : "—"}</span>
                            <span className="muted">Close</span><span className="knum">{r.close ? fmtDate(r.close) : "—"}</span>
                            <span className="muted">Allot</span><span className="knum">{r.allotment ? fmtDate(r.allotment) : "—"}</span>
                            <span className="muted">List</span><span className="knum font-semibold">{r.listing ? fmtDate(r.listing) : "—"}</span>
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right">
                          <Link href={r.href} className="accent text-[10.5px] font-bold hover:underline block whitespace-nowrap">
                            DRHP &amp; GMP →
                          </Link>
                          {r.registrar_url && (
                            <a href={r.registrar_url} target="_blank" rel="noreferrer"
                               className="muted text-[9.5px] hover:underline block mt-0.5">
                              Allotment status ↗
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {shownRows.length === 0 && (
                    <tr><td colSpan={10} className="px-4 py-8 muted text-[12.5px] text-center">
                      No IPO matches these dropdown filters. Try “All IPOs” or clear the search.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-3.5 py-2.5 muted text-[10.5px] leading-relaxed flex flex-wrap gap-x-4 gap-y-1"
                 style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <span>{data.source_note}</span>
              {data.live_sync?.fetched_at && <span>Feed fetched {data.live_sync.fetched_at.replace("T", " ")}</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function IpoDetail({ slug }: { slug: string }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setD(null);
    setErr(null);
    getJSON(`/ipos/${encodeURIComponent(slug)}`)
      .then((r) => { if (live) setD(r); })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    return () => { live = false; };
  }, [slug]);

  if (err) return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
      <ErrorBox message={err} stage="ipos" />
      <Link href="/ipos" className="btn-secondary mt-4">← Back to IPOs</Link>
    </div>
  );
  if (!d) return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8 space-y-3">
      <div className="skeleton h-16" /><Skeleton rows={7} />
    </div>
  );

  const s = d.issue_structure || {};
  const band = s.price_band?.value as any[] | undefined;
  const freshRaw = envNum(s.fresh_issue_pct);
  const ofsRaw = envNum(s.ofs_pct);
  const hasSplit = freshRaw != null && ofsRaw != null;
  const fresh = freshRaw ?? 0;
  const ofs = ofsRaw ?? 0;
  const sub = d.subscription_detail || d.subscription || {};
  const lotCalc = d.lot_calculator || {};
  const financials: any[] = d.financials || [];
  const peers: any[] = d.peers || [];
  const kpis: any[] = d.kpis || [];
  const statusMeta = STATUS_META[d.status] || STATUS_META.CLOSED;

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/ipos" className="hover:underline">IPOs</Link>
        <span className="opacity-40">/</span>
        <span className="font-semibold" style={{ color: "var(--ink)" }}>{d.symbol || d.slug}</span>
      </div>

      <PageHeader
        eyebrow={`${d.board} · ${statusMeta.label}`}
        title={d.name}
        sub={d.business_overview || d.note}
        right={
          <div className="flex flex-wrap gap-1.5">
            {d.symbol && (
              <Link href={`/stocks/${d.symbol}`} className="btn-primary !py-2 !text-[12px]">
                Stock page →
              </Link>
            )}
            {d.ig_url && (
              <a href={d.ig_url} target="_blank" rel="noreferrer" className="btn-secondary !py-2 !text-[12px]">
                Live GMP source ↗
              </a>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 mb-5">
        <div className="card p-3.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Price band</div>
          <div className="knum text-[20px] font-black mt-1">
            {band && band[0] != null ? `${money(band[0])} – ${money(band[1])}` : "Not opened"}
          </div>
          <div className="muted text-[10px] mt-0.5">per equity share</div>
        </div>
        <div className="card p-3.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">GMP</div>
          <div className={`knum text-[20px] font-black mt-1 ${(envNum(d.gmp_pct) || 0) >= 0 ? "text-up" : "text-down"}`}>
            {envNum(d.gmp) != null ? money(envNum(d.gmp)) : "—"}
          </div>
          <div className="muted text-[10px] mt-0.5">
            {envNum(d.gmp_pct) != null ? `${envNum(d.gmp_pct)!.toFixed(2)}% · ${d.gmp_trend}` : "no reliable GMP"}
          </div>
        </div>
        <div className="card p-3.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Est. listing</div>
          <div className={`knum text-[20px] font-black mt-1 ${(envNum(d.est_listing_gain_pct) || 0) >= 0 ? "text-up" : "text-down"}`}>
            {envNum(d.est_listing_price) != null ? money(envNum(d.est_listing_price)) : "—"}
          </div>
          <div className="muted text-[10px] mt-0.5">
            {envNum(d.est_listing_gain_pct) != null ? `${envNum(d.est_listing_gain_pct)!.toFixed(2)}% implied` : "price + GMP"}
          </div>
        </div>
        <div className="card p-3.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Issue size</div>
          <div className="knum text-[20px] font-black mt-1">
            {envNum(s.issue_size_crore) != null ? `₹${Number(envNum(s.issue_size_crore)).toLocaleString("en-IN")} Cr` : "—"}
          </div>
          <div className="muted text-[10px] mt-0.5">fresh + OFS</div>
        </div>
        <div className="card p-3.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Post-listing</div>
          <div className={`knum text-[20px] font-black mt-1 ${(envNum(d.performance?.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
            {envNum(d.performance?.last) != null ? money(envNum(d.performance.last)) : "—"}
          </div>
          <div className="muted text-[10px] mt-0.5">
            {envNum(d.performance?.changepct) != null ? `${pct(envNum(d.performance.changepct))} · ${d.performance?.source || "listing print"}` : "not listed yet"}
          </div>
        </div>
      </div>

      <section className="card p-4 mb-6">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div className="text-[13px] font-bold">Business overview</div>
          <span className="chip !text-[9px]">offer document</span>
        </div>
        <p className="text-[12px] leading-relaxed">
          {d.business_overview || d.note || "The company's business description is not published in the free offer-document feed."}
        </p>
        {(d.issue_objects || []).length > 0 && (
          <div className="mt-3">
            <div className="muted text-[10px] font-bold uppercase tracking-wider mb-1.5">
              Objects of the issue
            </div>
            <div className="grid sm:grid-cols-2 gap-1.5">
              {(d.issue_objects || []).map((o: any) => (
                <div key={o.no} className="rounded-md px-2.5 py-2 text-[11px] leading-snug"
                     style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  <span className="accent font-bold">{o.no}.</span> {o.object}
                  {o.amount_cr != null && (
                    <span className="knum font-semibold ml-1">₹{Number(o.amount_cr).toLocaleString("en-IN")} Cr</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 muted text-[10.5px]">
          <span>Board: <b style={{ color: "var(--ink)" }}>{d.board}</b></span>
          <span>Registrar: <b style={{ color: "var(--ink)" }}>{d.registrar?.value || (typeof d.registrar === "string" ? d.registrar : "—")}</b></span>
          <span>Lead manager: <b style={{ color: "var(--ink)" }}>{d.merchant_bankers?.[0]?.name || (typeof d.brlm?.[0] === "string" ? d.brlm[0] : d.brlm?.[0]?.name) || "—"}</b></span>
          <span>Listing: <b style={{ color: "var(--ink)" }}>{d.listing ? fmtDate(d.listing) : "—"}</b></span>
        </div>
      </section>

      <section className="grid lg:grid-cols-[1fr_380px] gap-3 mb-6">
        <div className="card p-4">
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="text-[13px] font-bold">Day-by-day GMP trend</div>
            <span className="chip !text-[9px]">unofficial · unregulated</span>
          </div>
          <GmpChart history={d.gmp_history || []} />
        </div>
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-2">Issue structure</div>
          <div className="mb-3">
            <div className="flex justify-between muted text-[10px] mb-1">
              <span>Fresh issue {hasSplit ? `${fresh}%` : "—"}</span>
              <span>OFS {hasSplit ? `${ofs}%` : "—"}</span>
            </div>
            <div className="h-2.5 rounded-full overflow-hidden flex" style={{ background: "var(--line)" }}>
              {hasSplit ? (
                <>
                  <div style={{ width: `${fresh}%`, background: "var(--accent)" }} />
                  <div style={{ width: `${ofs}%`, background: "var(--warn)" }} />
                </>
              ) : (
                <div className="w-full grid place-items-center text-[8.5px] muted">split not disclosed in the offer page</div>
              )}
            </div>
          </div>
          <dl className="space-y-1.5 text-[11.5px]">
            {[
              ["Fresh issue", envNum(s.fresh_issue_crore) != null ? `₹${Number(envNum(s.fresh_issue_crore)).toLocaleString("en-IN")} Cr` : "—"],
              ["Offer for sale", envNum(s.ofs_crore) != null ? `₹${Number(envNum(s.ofs_crore)).toLocaleString("en-IN")} Cr` : "—"],
              ["Lot size", envNum(s.lot_size) != null ? `${envNum(s.lot_size)} shares` : "—"],
              ["Face value", envNum(s.face_value) != null ? money(envNum(s.face_value)) : "—"],
              ["Registrar", d.registrar?.value || "—"],
              ["BRLMs", (d.merchant_bankers || []).map((b: any) => b.name).join(", ") || "—"],
            ].map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4">
                <dt className="muted">{k}</dt>
                <dd className="text-right font-semibold max-w-[68%]" style={{ color: "var(--ink)" }}>{v}</dd>
              </div>
            ))}
          </dl>
          {d.registrar_link && (
            <a href={d.registrar_link} target="_blank" rel="noreferrer"
               className="btn-secondary mt-3 !py-1.5 !text-[11px] inline-flex">
              Registrar allotment status →
            </a>
          )}
        </div>
      </section>

      <section className="grid lg:grid-cols-2 gap-3 mb-6">
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-2">Subscription breakdown</div>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {[
              ["QIB", "qib"], ["bNII", "bnii"], ["sNII", "snii"],
              ["Retail", "retail"], ["Employee", "employee"], ["Total", "total"],
            ].map(([label, key]) => {
              const v = envNum(sub[key]);
              return (
                <div key={key} className="rounded-md px-2 py-1.5" style={{ border: "1px solid var(--line)" }}>
                  <div className="muted text-[8.5px] font-bold uppercase tracking-wider">
                    <MetricTip label={label} tip={SUB_TIPS[label] || { meaning: "Subscription multiple for this bidder category." }}>{label}</MetricTip>
                  </div>
                  <div className={`knum text-[12px] font-bold ${v == null ? "muted" : v >= 1 ? "text-up" : ""}`}>
                    {v != null ? `${v.toFixed(2)}×` : "—"}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            <span className="chip !text-[9px]">{sub.anchor ? "Anchor book: ✅ present" : "Anchor book: ❌ not shown"}</span>
            {envNum(sub.pe) != null && <span className="chip !text-[9px]">Post-issue P/E {envNum(sub.pe)!.toFixed(2)}×</span>}
            <span className="chip !text-[9px]">Updated {sub.updated || "live report"}</span>
          </div>
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold mb-1">Lot-size application calculator</div>
          <p className="muted text-[10.5px] mb-2.5">{lotCalc.note || "Retail, sNII and bNII application slabs."}</p>
          <div className="grid sm:grid-cols-3 gap-2">
            {["retail", "snii", "bnii"].map((key) => {
              const c = lotCalc[key] || {};
              return (
                <div key={key} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  <div className="muted text-[9px] font-bold uppercase tracking-wider">{c.label || key}</div>
                  <div className="knum text-[14px] font-black mt-0.5">{c.amount != null ? money(c.amount) : "—"}</div>
                  <div className="muted text-[9.5px]">{c.shares != null ? `${c.shares.toLocaleString("en-IN")} shares` : ""}</div>
                  <div className="text-[9.5px] mt-1">
                    <span className="muted">Allotment chance </span>
                    <span className="knum font-bold accent">
                      {c.allotment_chance_pct != null ? `${c.allotment_chance_pct}%` : "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="muted text-[9.5px] mt-2">
            Chance = 1 ÷ category subscription, before the lottery. It is an estimate, not a promise.
          </p>
        </div>
      </section>

      <section className="grid lg:grid-cols-2 gap-3 mb-6">
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-1">Pre-IPO unlisted price vs IPO band</div>
          <p className="muted text-[11px] mb-3">{d.preipo_comparison?.note}</p>
          <div className="grid grid-cols-3 gap-2">
            {[
              ["Pre-IPO price", d.preipo_comparison?.preipo_price, inr],
              ["Offer price", d.preipo_comparison?.offer_price, inr],
              ["Offer premium", d.preipo_comparison?.premium_pct, (v: number) => pct(v)],
            ].map(([label, env, fmt]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                <div className="knum text-[13px] font-bold mt-0.5">
                  {env?.value != null ? fmt(env.value) : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold mb-1">Merchant banker (BRLM) track record</div>
          <p className="muted text-[11px] mb-2">Book-running lead managers named in the offer document. Historical deal counts are not published in the free feed, so they are not invented.</p>
          <div className="flex flex-wrap gap-1.5">
            {(d.merchant_bankers || []).map((b: any) => (
              <span key={b.name} className="chip !text-[10px]">{b.name}</span>
            ))}
          </div>
        </div>
      </section>

      {kpis.length > 0 && (
        <section className="mb-6">
          <SectionTitle title="Offer-document KPIs" sub="The company's own KPI table from the issue page." />
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5">KPI</th>
                    {kpis[0]?.values?.map((v: any) => (
                      <th key={v.period} className="table-head text-right px-2.5 py-2.5">{v.period}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {kpis.map((k: any) => (
                    <tr key={k.kpi} className="table-row">
                      <td className="px-3 py-2 text-[11.5px] font-semibold">{k.kpi}</td>
                      {(k.values || []).map((v: any, i: number) => (
                        <td key={i} className="px-2.5 py-2 text-right knum text-[11px]">{v.value}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      <section className="mb-6">
        <SectionTitle title="Financials — 3-year revenue, PAT and ROE"
                    sub="From the offer document. ROE = PAT ÷ net worth, shown only when both numbers are disclosed." />
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  <th className="table-head text-left px-3 py-2.5">Period</th>
                  <th className="table-head text-right px-2.5 py-2.5">Revenue</th>
                  <th className="table-head text-right px-2.5 py-2.5">EBITDA</th>
                  <th className="table-head text-right px-2.5 py-2.5">PAT</th>
                  <th className="table-head text-right px-2.5 py-2.5">Net worth</th>
                  <th className="table-head text-right px-3 py-2.5">ROE %</th>
                </tr>
              </thead>
              <tbody>
                {financials.map((f: any, i: number) => (
                  <tr key={i} className="table-row">
                    <td className="px-3 py-2 text-[11.5px] font-semibold">{f.period}</td>
                    <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(f.revenue) != null ? `₹${envNum(f.revenue)!.toLocaleString("en-IN")} Cr` : "—"}</td>
                    <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(f.ebitda) != null ? `₹${envNum(f.ebitda)!.toLocaleString("en-IN")} Cr` : "—"}</td>
                    <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(f.pat) != null ? `₹${envNum(f.pat)!.toLocaleString("en-IN")} Cr` : "—"}</td>
                    <td className="px-2.5 py-2 text-right knum text-[11px]">{envNum(f.net_worth) != null ? `₹${envNum(f.net_worth)!.toLocaleString("en-IN")} Cr` : "—"}</td>
                    <td className="px-3 py-2 text-right knum text-[11px] font-bold accent">
                      {envNum(f.roe_pct) != null ? `${envNum(f.roe_pct)!.toFixed(2)}%` : "—"}
                    </td>
                  </tr>
                ))}
                {financials.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-4 muted text-[12px]">
                    The free offer-document page did not publish a financial table for this issue.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="grid lg:grid-cols-2 gap-3 mb-6">
        <div>
          <SectionTitle title="OFS selling-shareholder exit table"
                      sub="Pre-IPO acquisition cost vs the IPO offer price, with the implied multiple and post-issue holding." />
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5">Seller</th>
                    <th className="table-head text-right px-2.5 py-2.5">Cost/sh</th>
                    <th className="table-head text-right px-2.5 py-2.5">Offer</th>
                    <th className="table-head text-right px-3 py-2.5">Multiple</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.ofs_selling_shareholders || []).map((sh: any, i: number) => (
                    <tr key={i} className="table-row">
                      <td className="px-3 py-2.5 text-[11.5px] font-semibold">{sh.name}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">{envNum(sh.preipo_cost) != null ? inr(envNum(sh.preipo_cost)) : "—"}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">{envNum(sh.offer_price) != null ? inr(envNum(sh.offer_price)) : "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[11px] font-bold text-up">
                        {envNum(sh.multiple) != null ? `${envNum(sh.multiple)!.toFixed(1)}×` : "—"}
                      </td>
                    </tr>
                  ))}
                  {(d.ofs_selling_shareholders || []).length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-4 muted text-[12px]">No OFS sellers — this issue is entirely a fresh issue.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <SectionTitle title="Peer valuation comparison"
                      sub="Listed peers from the offer document, or a sector proxy when the offer page has no peer table." />
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5">Peer</th>
                    <th className="table-head text-right px-2.5 py-2.5">Price</th>
                    <th className="table-head text-right px-2.5 py-2.5">P/E</th>
                    <th className="table-head text-right px-3 py-2.5">P/B</th>
                  </tr>
                </thead>
                <tbody>
                  {peers.map((p: any, i: number) => (
                    <tr key={`${p.symbol}-${i}`} className="table-row">
                      <td className="px-3 py-2.5">
                        <div className="text-[11.5px] font-semibold">{p.name}</div>
                        <div className="muted text-[9.5px]">{p.symbol || p.note}</div>
                      </td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">{envNum(p.last) != null ? inr(envNum(p.last)) : "—"}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">{envNum(p.pe) != null ? `${envNum(p.pe)!.toFixed(1)}×` : "—"}</td>
                      <td className="px-3 py-2.5 text-right knum text-[11px]">{envNum(p.pb) != null ? `${envNum(p.pb)!.toFixed(2)}×` : "—"}</td>
                    </tr>
                  ))}
                  {peers.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-4 muted text-[12px]">
                      No peer table was published and no sector match was found.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="card p-4">
        <div className="text-[13px] font-bold mb-1">Source &amp; honesty notes</div>
        {(d.source_notes || []).map((n: string) => (
          <p key={n} className="muted text-[11.5px] leading-relaxed mt-1">{n}</p>
        ))}
      </section>
    </div>
  );
}
