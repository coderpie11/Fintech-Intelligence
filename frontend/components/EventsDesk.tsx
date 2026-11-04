"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { bigCrude, fmtDate, inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton } from "@/components/PageKit";
import MetricTip from "@/components/MetricTip";

type Ev = {
  symbol: string;
  company: string;
  kind: string;
  raw_kind: string;
  tab: string;
  ex_date: Env;
  record_date: Env;
  purpose: string;
  announcement: string;
  event_type: string;
  dividend_per_share: Env;
  dividend_yield_pct: Env;
  buyback_price: Env;
  buyback_premium_pct: Env;
  split_ratio: number | null;
  bonus_ratio: string | null;
  price: Env;
  changepct: Env;
  market_cap: Env;
  countdown_days: number | null;
  countdown_badge: string;
  upcoming: boolean;
  completed: boolean;
  in_universe: boolean;
  calc_prefill: Record<string, any> | null;
  href: string | null;
};

const TAB_TONE: Record<string, string> = {
  DIVIDENDS: "chip-live",
  SPLITS: "chip-warn",
  BONUSES: "chip-live",
  BUYBACKS: "chip-warn",
  "RIGHTS & MERGERS": "chip-warn",
  "BOARD MEETINGS & EARNINGS": "",
  OTHER: "",
};

const AVATAR_COLORS = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#0891b2", "#16a34a", "#ca8a04"];

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

function avatarColor(symbol: string): string {
  let h = 0;
  for (let i = 0; i < symbol.length; i++) h = (h * 31 + symbol.charCodeAt(i)) % 9973;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

function initials(name: string): string {
  return (name || "?")
    .replace(/\b(ltd|limited|the|of|and|&)\b/gi, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

function Field({ label, value, set, suffix }: { label: string; value: string; set: (v: string) => void; suffix?: string }) {
  return (
    <label className="block">
      <span className="muted text-[9px] font-bold uppercase tracking-wider">{label}{suffix ? ` (${suffix})` : ""}</span>
      <input value={value} onChange={(e) => set(e.target.value)} inputMode="decimal"
             className="surface rounded-lg w-full mt-0.5 px-2 py-1.5 text-[11.5px] knum"
             style={{ color: "var(--ink)" }} />
    </label>
  );
}

function Result({ r, err }: { r: any; err: string | null }) {
  if (err) return <div className="card p-4 text-[11.5px] text-down">{err}</div>;
  if (!r) return <div className="card p-4 muted text-[12px]">Run the calculator, or pick an event above to prefill it.</div>;
  return (
    <div className="card p-4 space-y-1.5 text-[12px]">
      {Object.entries(r).filter(([k]) => k !== "note").map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="muted capitalize">{k.replace(/_/g, " ")}</span>
          <span className="knum font-semibold text-right">
            {typeof v === "number" ? (Math.abs(v) >= 1000 ? inr(v) : v.toFixed(2)) : String(v)}
          </span>
        </div>
      ))}
      {r.note && <p className="muted text-[10.5px] leading-relaxed pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>{r.note}</p>}
    </div>
  );
}

export default function EventsDesk() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [kind, setKind] = useState("ALL");
  const [q, setQ] = useState("");
  const [win, setWin] = useState("week");
  const [sort, setSort] = useState("ex_date");
  const [tab, setTab] = useState("dividend");

  // calculator state
  const [dividend, setDividend] = useState({ dps: "10", shares: "1000", slab: "30" });
  const [split, setSplit] = useState({ shares: "100", oldFace: "10", newFace: "2", price: "500" });
  const [bonus, setBonus] = useState({ shares: "100", num: "1", den: "1", cost: "200", price: "500", sold: "0" });
  const [buyback, setBuyback] = useState({ price: "1000", cmp: "900", held: "100", acceptance: "30" });
  const [demerger, setDemerger] = useState({ cost: "100000", demerged: "25", remaining: "75", num: "1", den: "4", sub: "100", cmp: "130", held: "100" });
  const [r, setR] = useState<any>(null);
  const [calcErr, setCalcErr] = useState<string | null>(null);
  const [prefilled, setPrefilled] = useState<string | null>(null);
  const calcRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setErr(null);
    const p = new URLSearchParams({ kind, window: win, sort });
    if (q.trim()) p.set("q", q.trim());
    getJSON(`/events?${p}`).then(setData).catch((e) => setErr(String(e.message || e)));
  }, [kind, q, win, sort]);

  const run = async (path: string, body: any) => {
    setCalcErr(null); setR(null);
    try {
      setR(await postJSON(path, body));
    } catch (e: any) { setCalcErr(String(e.message || e).slice(0, 200)); }
  };

  const prefill = (e: Ev) => {
    const p = e.calc_prefill;
    if (!p) return;
    setR(null); setCalcErr(null);
    setPrefilled(`${e.symbol} · ${e.announcement}`);
    if (p.type === "dividend") {
      setTab("dividend");
      setDividend({
        dps: String(p.dividend_per_share ?? 10),
        shares: String(p.shares ?? 100),
        slab: String(p.tax_slab_pct ?? 30),
      });
    } else if (p.type === "split") {
      setTab("split");
      setSplit({
        shares: String(p.shares ?? 100),
        oldFace: String(p.old_face_value ?? 10),
        newFace: String(p.new_face_value ?? 2),
        price: String(p.pre_split_price ?? 500),
      });
    } else if (p.type === "bonus") {
      setTab("bonus");
      setBonus({
        shares: String(p.original_shares ?? 100),
        num: String(p.bonus_ratio_num ?? 1),
        den: String(p.bonus_ratio_den ?? 1),
        cost: String(p.original_cost_per_share ?? 200),
        price: String(p.current_price ?? 500),
        sold: String(p.shares_sold ?? 0),
      });
    } else if (p.type === "buyback") {
      setTab("buyback");
      setBuyback({
        price: String(p.buyback_price ?? 1000),
        cmp: String(p.cmp ?? 900),
        held: String(p.shares_held ?? 100),
        acceptance: String(p.acceptance_ratio_pct ?? 30),
      });
    } else {
      setTab("demerger");
      setDemerger((prev) => ({
        ...prev,
        num: String(p.rights_ratio_num ?? prev.num),
        den: String(p.rights_ratio_den ?? prev.den),
        sub: String(p.rights_subscription_price ?? prev.sub),
      }));
    }
    window.setTimeout(() => calcRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const tabs: { key: string; label: string; count: number }[] = data?.tabs || [];
  const counts: Record<string, number> = data?.filter_counts || {};
  const events: Ev[] = data?.events || [];

  const windows = useMemo(() => ([
    ["week", "Upcoming & Ex-Date This Week"],
    ["month", "This Month"],
    ["past", "Recent / Past"],
    ["all", "All"],
  ] as [string, string][]), []);

  const sorts = useMemo(() => ([
    ["ex_date", "Ex-Date"],
    ["dividend_yield", "Dividend Yield %"],
    ["market_cap", "Market Cap"],
  ] as [string, string][]), []);

  return (
    <div className="mx-auto max-w-[1680px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Corporate events · Groww / Zerodha style"
        title="Corporate Actions Calendar"
        sub="Dividends, splits, bonuses, buybacks, rights, mergers and board meetings with announcement details, ex-date countdowns, live prices and one-click prefill into the matching calculator."
        right={<RefreshButton stage="events" />}
      />

      {err && <ErrorBox message={err} stage="events" />}
      {!data && !err && <Skeleton rows={8} />}

      {data && (
        <>
          {/* sticky tab bar */}
          <div className="sticky top-0 z-20 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 mb-3 backdrop-blur"
               style={{ background: "color-mix(in srgb, var(--bg) 90%, transparent)", borderBottom: "1px solid var(--line)" }}>
            <div className="flex gap-1.5 overflow-x-auto pb-0.5">
              {tabs.map((t) => (
                <button key={t.key} onClick={() => setKind(t.key)}
                        className={`chip !text-[11px] !px-3 !py-1.5 whitespace-nowrap ${kind === t.key ? "chip-active" : ""}`}>
                  {t.label}
                  <span className={`knum ml-1.5 ${kind === t.key ? "" : "muted"}`}>{t.count}</span>
                </button>
              ))}
            </div>
          </div>

          {/* controls */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <div className="flex flex-wrap gap-1.5">
              {windows.map(([k, label]) => (
                <button key={k} onClick={() => setWin(k)}
                        className={`chip !text-[10.5px] ${win === k ? "chip-active" : ""}`}>{label}</button>
              ))}
            </div>
            <div className="surface rounded-lg px-3 py-1.5 flex-1 min-w-[200px] max-w-sm">
              <input value={q} onChange={(e) => setQ(e.target.value)}
                     placeholder="Search company or symbol…"
                     className="w-full bg-transparent text-[12.5px] outline-none"
                     style={{ color: "var(--ink)" }} />
            </div>
            <div className="flex items-center gap-1.5 ml-auto">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Sort</span>
              {sorts.map(([k, label]) => (
                <button key={k} onClick={() => setSort(k)}
                        className={`chip !text-[10.5px] ${sort === k ? "chip-active" : ""}`}>{label}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <span className="muted text-[11px]">
              {events.length} of {data.total ?? events.length} events ·{" "}
              <span className="accent font-semibold">{data.feed_status?.value ?? ""} shown</span>
            </span>
            <span className="muted text-[10.5px]">
              {kind === "ALL" ? `All ${counts.ALL ?? 0} stored actions` : `${kind} · ${counts[kind] ?? 0} stored`}
            </span>
          </div>

          <div className="card overflow-hidden mb-8">
            <div className="max-h-[620px] overflow-auto">
              <table className="w-full min-w-[1180px] border-collapse">
                <thead className="sticky top-0 z-10">
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5 min-w-[230px]">Company</th>
                    <th className="table-head text-left px-2.5 py-2.5">Event</th>
                    <th className="table-head text-left px-2.5 py-2.5 min-w-[240px]">Announcement / ratio</th>
                    <th className="table-head text-right px-2.5 py-2.5">Ex-date</th>
                    <th className="table-head text-right px-2.5 py-2.5">Record date</th>
                    <th className="table-head text-right px-2.5 py-2.5">Price · 1D</th>
                    <th className="table-head text-right px-2.5 py-2.5">M-cap</th>
                    <th className="table-head text-right px-3 py-2.5">Impact</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e, i) => {
                    const price = envNum(e.price);
                    const chg = envNum(e.changepct);
                    const mcap = envNum(e.market_cap);
                    const dy = envNum(e.dividend_yield_pct);
                    const premium = envNum(e.buyback_premium_pct);
                    const cd = e.countdown_days;
                    return (
                      <tr key={`${e.symbol}-${i}`} className="table-row align-top">
                        <td className="px-3 py-3">
                          <div className="flex items-start gap-2.5">
                            <span className="shrink-0 grid place-items-center h-8 w-8 rounded-full text-[10px] font-black text-white"
                                  style={{ background: avatarColor(e.symbol || e.company) }}>
                              {initials(e.company || e.symbol)}
                            </span>
                            <div className="min-w-0">
                              {e.href ? (
                                <Link href={e.href} className="text-[12.5px] font-bold hover:underline leading-snug block">
                                  {e.company}
                                </Link>
                              ) : (
                                <div className="text-[12.5px] font-bold leading-snug">{e.company}</div>
                              )}
                              <div className="muted text-[9.5px] mt-0.5">{e.symbol || "—"}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-2.5 py-3">
                          <span className={`chip !text-[9px] whitespace-nowrap ${TAB_TONE[e.tab] || ""}`}>
                            {e.tab === "BOARD MEETINGS & EARNINGS" ? "Board / earnings" : e.tab.replace(/S$/, "").toLowerCase()}
                          </span>
                        </td>
                        <td className="px-2.5 py-3">
                          <div className="text-[11.5px] leading-snug">{e.announcement}</div>
                          <div className="flex flex-wrap gap-1.5 mt-1">
                            {dy != null && (
                              <span className="chip !text-[8.5px] text-up">yield {dy.toFixed(2)}%</span>
                            )}
                            {premium != null && (
                              <span className={`chip !text-[8.5px] ${premium >= 0 ? "text-up" : "text-down"}`}>
                                {premium >= 0 ? "+" : ""}{premium.toFixed(1)}% vs CMP
                              </span>
                            )}
                            {e.split_ratio != null && (
                              <span className="chip !text-[8.5px]">{e.split_ratio}:1 split</span>
                            )}
                            {e.bonus_ratio && (
                              <span className="chip !text-[8.5px]">{e.bonus_ratio} bonus</span>
                            )}
                          </div>
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          <div className="knum text-[11.5px] font-semibold">{e.ex_date?.value ? fmtDate(e.ex_date.value) : "—"}</div>
                          <div className={`text-[9.5px] font-semibold mt-0.5 ${
                            cd == null ? "muted" : cd === 0 ? "text-warn" : cd > 0 ? "accent" : "muted"
                          }`}>
                            {e.countdown_badge}
                          </div>
                        </td>
                        <td className="px-2.5 py-3 text-right knum text-[11px]">
                          {e.record_date?.value ? fmtDate(e.record_date.value) : "—"}
                        </td>
                        <td className="px-2.5 py-3 text-right">
                          <div className="knum text-[12px] font-bold">{price != null ? inr(price) : "—"}</div>
                          <div className={`knum text-[9.5px] font-semibold ${(chg || 0) >= 0 ? "text-up" : "text-down"}`}>
                            {chg != null ? pct(chg) : "—"}
                          </div>
                        </td>
                        <td className="px-2.5 py-3 text-right knum text-[11px]">
                          {mcap != null ? bigCrude(mcap) : "—"}
                        </td>
                        <td className="px-3 py-3 text-right">
                          {e.calc_prefill ? (
                            <button onClick={() => prefill(e)}
                                    className="accent text-[10.5px] font-bold hover:underline whitespace-nowrap">
                              Calculate Impact →
                            </button>
                          ) : (
                            <span className="muted text-[9.5px] whitespace-nowrap">Calendar only</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {events.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 muted text-[12.5px] text-center">
                        No events match this window. Try “This Month” or “All”, or clear the search.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-3.5 py-2.5 muted text-[10.5px] leading-relaxed flex flex-wrap gap-x-4 gap-y-1"
                 style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <span>{data.note}</span>
              <span>Ex-date is the first session without the entitlement; buy before it to qualify.</span>
            </div>
          </div>

          <div ref={calcRef} className="scroll-mt-24">
            <SectionTitle title="Five corporate-action calculators"
                        sub="Dividend TDS, split adjustment, bonus FIFO, retail buyback arbitrage and demerger cost allocation. Pick an event above to prefill the matching one." />
            {prefilled && (
              <div className="rounded-lg px-3 py-2 mb-3 text-[11.5px]"
                   style={{ border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
                            background: "color-mix(in srgb, var(--accent) 7%, transparent)" }}>
                <span className="accent font-bold">Prefilled from:</span> {prefilled}
              </div>
            )}
            <div className="flex flex-wrap gap-1.5 mb-3">
              {[
                ["dividend", "Dividend & TDS"], ["split", "Stock split"],
                ["bonus", "Bonus & FIFO"], ["buyback", "Buyback arbitrage"],
                ["demerger", "Demerger & rights"],
              ].map(([k, label]) => (
                <button key={k} onClick={() => { setTab(k); setR(null); setCalcErr(null); }}
                        className={`chip !text-[10.5px] ${tab === k ? "chip-active" : ""}`}>{label}</button>
              ))}
            </div>

            {tab === "dividend" && (
              <div className="grid lg:grid-cols-[360px_1fr] gap-3">
                <div className="card p-4">
                  <div className="text-[13px] font-bold">Dividend &amp; 10% TDS</div>
                  <p className="muted text-[11px] mt-0.5">TDS applies above ₹5,000 in a financial year; the final liability is your slab.</p>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Field label="Dividend / share" value={dividend.dps} set={(v) => setDividend({ ...dividend, dps: v })} />
                    <Field label="Shares held" value={dividend.shares} set={(v) => setDividend({ ...dividend, shares: v })} />
                    <Field label="Tax slab %" value={dividend.slab} set={(v) => setDividend({ ...dividend, slab: v })} />
                  </div>
                  <button onClick={() => run("/events/calc/dividend", { dividend_per_share: Number(dividend.dps), shares: Number(dividend.shares), tax_slab_pct: Number(dividend.slab) })}
                          className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">Compute post-tax dividend</button>
                </div>
                <Result r={r} err={calcErr} />
              </div>
            )}

            {tab === "split" && (
              <div className="grid lg:grid-cols-[360px_1fr] gap-3">
                <div className="card p-4">
                  <div className="text-[13px] font-bold">Stock split adjustment</div>
                  <p className="muted text-[11px] mt-0.5">Face-value change drives the share count and theoretical price.</p>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Field label="Shares held" value={split.shares} set={(v) => setSplit({ ...split, shares: v })} />
                    <Field label="Pre-split price" value={split.price} set={(v) => setSplit({ ...split, price: v })} />
                    <Field label="Old face value" value={split.oldFace} set={(v) => setSplit({ ...split, oldFace: v })} />
                    <Field label="New face value" value={split.newFace} set={(v) => setSplit({ ...split, newFace: v })} />
                  </div>
                  <button onClick={() => run("/events/calc/split", { shares: Number(split.shares), pre_split_price: Number(split.price), old_face_value: Number(split.oldFace), new_face_value: Number(split.newFace) })}
                          className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">Adjust shares &amp; price</button>
                </div>
                <Result r={r} err={calcErr} />
              </div>
            )}

            {tab === "bonus" && (
              <div className="grid lg:grid-cols-[360px_1fr] gap-3">
                <div className="card p-4">
                  <div className="text-[13px] font-bold">Bonus issue &amp; FIFO tax</div>
                  <p className="muted text-[11px] mt-0.5">FIFO sells original shares first; bonus shares carry zero cost.</p>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Field label="Original shares" value={bonus.shares} set={(v) => setBonus({ ...bonus, shares: v })} />
                    <Field label="Original cost/share" value={bonus.cost} set={(v) => setBonus({ ...bonus, cost: v })} />
                    <Field label="Bonus ratio num" value={bonus.num} set={(v) => setBonus({ ...bonus, num: v })} />
                    <Field label="Bonus ratio den" value={bonus.den} set={(v) => setBonus({ ...bonus, den: v })} />
                    <Field label="Current price" value={bonus.price} set={(v) => setBonus({ ...bonus, price: v })} />
                    <Field label="Shares sold" value={bonus.sold} set={(v) => setBonus({ ...bonus, sold: v })} />
                  </div>
                  <button onClick={() => run("/events/calc/bonus", {
                    original_shares: Number(bonus.shares), original_cost_per_share: Number(bonus.cost),
                    bonus_ratio_num: Number(bonus.num), bonus_ratio_den: Number(bonus.den),
                    current_price: Number(bonus.price), shares_sold: Number(bonus.sold),
                  })} className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">Compute bonus &amp; FIFO tax</button>
                </div>
                <Result r={r} err={calcErr} />
              </div>
            )}

            {tab === "buyback" && (
              <div className="grid lg:grid-cols-[360px_1fr] gap-3">
                <div className="card p-4">
                  <div className="text-[13px] font-bold">Retail buyback arbitrage</div>
                  <p className="muted text-[11px] mt-0.5">Pro-rata acceptance on the 15% retail quota; arbitrage exists only on accepted shares.</p>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Field label="Buyback price" value={buyback.price} set={(v) => setBuyback({ ...buyback, price: v })} />
                    <Field label="Current market price" value={buyback.cmp} set={(v) => setBuyback({ ...buyback, cmp: v })} />
                    <Field label="Shares held" value={buyback.held} set={(v) => setBuyback({ ...buyback, held: v })} />
                    <Field label="Acceptance %" value={buyback.acceptance} set={(v) => setBuyback({ ...buyback, acceptance: v })} />
                  </div>
                  <button onClick={() => run("/events/calc/buyback", {
                    buyback_price: Number(buyback.price), cmp: Number(buyback.cmp),
                    shares_held: Number(buyback.held), acceptance_ratio_pct: Number(buyback.acceptance),
                  })} className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">Compute arbitrage</button>
                </div>
                <Result r={r} err={calcErr} />
              </div>
            )}

            {tab === "demerger" && (
              <div className="grid lg:grid-cols-[360px_1fr] gap-3">
                <div className="card p-4">
                  <div className="text-[13px] font-bold">Demerger cost split &amp; rights</div>
                  <p className="muted text-[11px] mt-0.5">Allocate the original cost by fair value, then value the rights entitlement.</p>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Field label="Original cost" value={demerger.cost} set={(v) => setDemerger({ ...demerger, cost: v })} />
                    <Field label="Shares held" value={demerger.held} set={(v) => setDemerger({ ...demerger, held: v })} />
                    <Field label="Demerged value %" value={demerger.demerged} set={(v) => setDemerger({ ...demerger, demerged: v })} />
                    <Field label="Remaining value %" value={demerger.remaining} set={(v) => setDemerger({ ...demerger, remaining: v })} />
                    <Field label="Rights ratio num" value={demerger.num} set={(v) => setDemerger({ ...demerger, num: v })} />
                    <Field label="Rights ratio den" value={demerger.den} set={(v) => setDemerger({ ...demerger, den: v })} />
                    <Field label="Rights price" value={demerger.sub} set={(v) => setDemerger({ ...demerger, sub: v })} />
                    <Field label="Rights CMP" value={demerger.cmp} set={(v) => setDemerger({ ...demerger, cmp: v })} />
                  </div>
                  <button onClick={() => run("/events/calc/demerger", {
                    original_cost: Number(demerger.cost), shares_held: Number(demerger.held),
                    demerged_company_value_pct: Number(demerger.demerged),
                    remaining_company_value_pct: Number(demerger.remaining),
                    rights_ratio_num: Number(demerger.num), rights_ratio_den: Number(demerger.den),
                    rights_subscription_price: Number(demerger.sub), rights_cmp: Number(demerger.cmp),
                  })} className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">Split cost &amp; value rights</button>
                </div>
                <Result r={r} err={calcErr} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
