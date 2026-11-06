"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { PageHeader, RefreshButton } from "@/components/PageKit";
import { ErrLine, Metric, Note, Panel, Pill, num, signed } from "@/components/quant/Kit";
import type { Tip } from "@/components/MetricTip";

type LivePosition = {
  id: number;
  symbol: string;
  label: string;
  asset_class: "EQUITY" | "DERIVATIVE";
  underlying: string | null;
  option_type: string | null;
  strike: number | null;
  expiry: string | null;
  lot_size: number | null;
  lots: number | null;
  side: "BUY" | "SELL";
  qty: number;
  entry: number;
  mark: number;
  mark_source: string;
  charges: number;
  pnl: number;
  pnl_gross: number;
  pnl_pct: number | null;
  opened_at: string | null;
  href: string | null;
};

type ClosedPosition = {
  id: number;
  symbol: string;
  label: string;
  asset_class: "EQUITY" | "DERIVATIVE";
  side: "BUY" | "SELL";
  qty: number;
  entry: number;
  exit: number;
  charges: number;
  realized_pnl: number;
  opened_at: string | null;
  closed_at: string | null;
};

type Summary = {
  starting_cash: number;
  cash_available: number;
  market_value: number;
  equity_value: number;
  exposure: number;
  live_positions: LivePosition[];
  closed_positions: ClosedPosition[];
  pnl: { realized: number; unrealized: number; total: number };
  allocation: { equity_pct: number; derivative_pct: number };
  margin_note: string;
  marking_note: { value: string };
};

type HistoryPoint = { date: string; equity_value: number; realized_cum: number; open_market_value: number };
type History = { start?: string; points: HistoryPoint[]; note: string };
type Watch = { symbol: string; name: string; kind: string; last: number | null; changepct: number | null; href: string };
type Pick = { kind: string; symbol: string; name: string; label: string; sublabel?: string; price?: number | null; aliases?: string };
type Quote = {
  asset_class: string; symbol: string; name: string; kind: string;
  price: number; quantity: number; lot_size: number; lots: number | null;
  value: number; charges: number; cash_available: number; cash_after: number;
  source: string;
};

const FNO_KEY: Record<string, string> = {
  "NIFTY 50": "NIFTY", "NIFTY BANK": "BANKNIFTY", "BANK NIFTY": "BANKNIFTY",
  "SENSEX": "SENSEX", "NIFTY IT": "NIFTYIT", "NIFTY NEXT 50": "NIFTYNXT50",
  "NIFTY FIN SERVICE": "FINNIFTY", "NIFTY MIDCAP 100": "MIDCPNIFTY",
};
const fnoKey = (s: string) => FNO_KEY[s.trim().toUpperCase()] || s.trim().toUpperCase();

const QUICK: { label: string; value: string; kind: "INDEX" | "EQUITY" }[] = [
  { label: "NIFTY 50", value: "NIFTY 50", kind: "INDEX" },
  { label: "SENSEX", value: "SENSEX", kind: "INDEX" },
  { label: "BANK NIFTY", value: "NIFTY BANK", kind: "INDEX" },
  { label: "RELIANCE", value: "RELIANCE", kind: "EQUITY" },
  { label: "PARAS (Paras Defence)", value: "PARAS", kind: "EQUITY" },
  { label: "TCS", value: "TCS", kind: "EQUITY" },
  { label: "HDFCBANK", value: "HDFCBANK", kind: "EQUITY" },
  { label: "ZOMATO", value: "ZOMATO", kind: "EQUITY" },
  { label: "GOLDBEES", value: "GOLDBEES", kind: "EQUITY" },
  { label: "SILVERBEES", value: "SILVERBEES", kind: "EQUITY" },
];

const TIPS: Record<string, Tip> = {
  corpus: {
    meaning: "The virtual starting corpus. Every paper fill debits or credits this cash balance, so the equity value is real arithmetic on stored prices — not a decorative number.",
    formula: "Equity value = cash available + market value of open legs",
    example: "₹10,00,000 start; buy ₹1,16,490 of Reliance and cash falls to about ₹8,83,400 after statutory charges.",
  },
  realized: {
    meaning: "Profit or loss already booked by closing a paper position, net of both legs' statutory charges.",
    formula: "Realised = (exit − entry) × qty − total charges (for a long leg)",
  },
  unrealized: {
    meaning: "Profit or loss on positions still open, marked at the last available free-feed price. It can reverse before you close.",
  },
  exposure: {
    meaning: "Gross absolute market value of all open legs, long and short added together. It can exceed cash when shorts are open.",
  },
  delivery: {
    meaning: "Disclaimer: this sandbox does not model SPAN or exposure margin, so an F&O premium value understates the capital a real broker would block.",
  },
};

function HistoryChart({ points, baseline }: { points: HistoryPoint[]; baseline: number }) {
  const W = 1000;
  const H = 190;
  const pad = { l: 8, r: 8, t: 14, b: 22 };
  if (points.length < 2) {
    return <p className="muted text-[12px]">Not enough events yet to draw a curve — place a paper order first.</p>;
  }
  const vals = points.map((p) => p.equity_value).concat([baseline]);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad.l + (i / (points.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / span) * (H - pad.t - pad.b);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.equity_value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - pad.b} L${x(0).toFixed(1)},${H - pad.b} Z`;
  const last = points[points.length - 1];
  const up = last.equity_value >= baseline;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Sandbox portfolio equity curve">
        <defs>
          <linearGradient id="sbx-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={up ? "var(--up)" : "var(--down)"} stopOpacity="0.28" />
            <stop offset="100%" stopColor={up ? "var(--up)" : "var(--down)"} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <line x1={pad.l} x2={W - pad.r} y1={y(baseline)} y2={y(baseline)}
              stroke="var(--line)" strokeDasharray="4 4" strokeWidth="1" />
        <path d={area} fill="url(#sbx-grad)" />
        <path d={line} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="2.2" />
        <circle cx={x(points.length - 1)} cy={y(last.equity_value)} r="3.5"
                fill={up ? "var(--up)" : "var(--down)"} />
      </svg>
      <div className="flex flex-wrap items-center justify-between gap-2 muted text-[10.5px] knum mt-1">
        <span>{points[0].date}</span>
        <span>
          low {inr(min)} · high {inr(max)}
        </span>
        <span>{last.date}</span>
      </div>
    </div>
  );
}

export default function SandboxPage() {
  const [sum, setSum] = useState<Summary | null>(null);
  const [hist, setHist] = useState<History | null>(null);
  const [watch, setWatch] = useState<Watch[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // equity ticket
  const [sym, setSym] = useState("RELIANCE");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [qty, setQty] = useState(1);
  const [category, setCategory] = useState<"EQUITY" | "INDEX" | "FNO">("EQUITY");
  const [pickerQ, setPickerQ] = useState("RELIANCE");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [preload, setPreload] = useState<Pick[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteBusy, setQuoteBusy] = useState(false);

  // F&O ticket
  const [ticket, setTicket] = useState<"EQUITY" | "DERIVATIVE">("EQUITY");
  const [underlying, setUnderlying] = useState("NIFTY");
  const [optType, setOptType] = useState<"CE" | "PE" | "FUT">("CE");
  const [strike, setStrike] = useState<number | "">("");
  const [expiry, setExpiry] = useState<string>("");
  const [lots, setLots] = useState(1);
  const [futPrice, setFutPrice] = useState<number | "">("");
  const [chain, setChain] = useState<any>(null);
  const [chainErr, setChainErr] = useState<string | null>(null);
  const [chainBusy, setChainBusy] = useState(false);

  const load = () => {
    getJSON("/sandbox/summary").then(setSum).catch((e) => setErr(String(e.message || e)));
    getJSON("/sandbox/history").then(setHist).catch(() => {});
    getJSON("/watchlist").then((r) => setWatch(r.items || [])).catch(() => {});
  };
  useEffect(load, []);

  // <20 ms client-side preload index: 2,401 equities + 51 ETFs + indices.
  useEffect(() => {
    getJSON("/search/preload")
      .then((d) => setPreload((d.items || []).filter((x: Pick) =>
        ["EQUITY", "ETF", "INDEX"].includes(x.kind))))
      .catch(() => {});
  }, []);

  const suggestions = useMemo(() => {
    const needle = pickerQ.trim().toLowerCase();
    if (!needle) return [];
    return preload.filter((x) => {
      const hay = `${x.symbol} ${x.name} ${x.label} ${x.aliases || ""}`.toLowerCase();
      return hay.includes(needle);
    }).sort((a, b) => {
      const as = a.symbol.toLowerCase().startsWith(needle) ? 0 : 1;
      const bs = b.symbol.toLowerCase().startsWith(needle) ? 0 : 1;
      return as - bs || a.symbol.localeCompare(b.symbol);
    }).slice(0, 9);
  }, [pickerQ, preload]);

  const chooseCategory = (c: "EQUITY" | "INDEX" | "FNO") => {
    setCategory(c);
    setQuote(null);
    if (c === "EQUITY") {
      setTicket("EQUITY");
      setSym("RELIANCE"); setPickerQ("RELIANCE");
    } else if (c === "INDEX") {
      setTicket("DERIVATIVE");
      setOptType("FUT"); setUnderlying("NIFTY");
      setPickerQ("NIFTY 50");
    } else {
      setTicket("DERIVATIVE");
      setOptType("CE");
      setPickerQ("");
    }
  };

  const pick = (it: Pick) => {
    setPickerOpen(false);
    setQuote(null);
    setPickerQ(it.label || it.symbol);
    if (it.kind === "INDEX") {
      setCategory("INDEX"); setTicket("DERIVATIVE"); setOptType("FUT");
      setUnderlying(fnoKey(it.symbol));
    } else if (category === "FNO") {
      setUnderlying(it.symbol);
    } else {
      setCategory("EQUITY"); setTicket("EQUITY"); setSym(it.symbol);
    }
  };

  const quickPick = (q: { value: string; kind: "INDEX" | "EQUITY" }) => {
    setQuote(null);
    setPickerQ(q.value);
    if (q.kind === "INDEX") {
      setCategory("INDEX"); setTicket("DERIVATIVE"); setOptType("FUT");
      setUnderlying(fnoKey(q.value));
    } else {
      setCategory("EQUITY"); setTicket("EQUITY");
      setSym(q.value);
    }
  };

  // Pull the live chain so the ticket offers real expiries, strikes and spot.
  useEffect(() => {
    if (ticket !== "DERIVATIVE") return;
    let live = true;
    setChainBusy(true);
    setChainErr(null);
    getJSON(`/fno/${encodeURIComponent(fnoKey(underlying))}`)
      .then((d) => {
        if (!live) return;
        setChain(d);
        const ex = d?.expiries?.[0] || d?.active_expiry || "";
        setExpiry((prev) => (prev && (d?.expiries || []).includes(prev) ? prev : ex));
        const spot = d?.underlyingValue ?? d?.spot?.value;
        const strikes = (d?.rows || []).map((r: any) => Number(r.strike)).filter((n: number) => Number.isFinite(n));
        if (spot && strikes.length) {
          const nearest = strikes.reduce((a: number, b: number) => (Math.abs(b - spot) < Math.abs(a - spot) ? b : a), strikes[0]);
          setStrike((prev) => (prev === "" ? nearest : prev));
        }
      })
      .catch((e) => { if (live) setChainErr(String(e.message || e).slice(0, 160)); })
      .finally(() => { if (live) setChainBusy(false); });
    return () => { live = false; };
  }, [ticket, underlying]);

  const spot = useMemo(() => Number(chain?.underlyingValue ?? chain?.spot?.value ?? NaN), [chain]);

  // Live order-cost preview before the user clicks Buy/Sell.
  useEffect(() => {
    let live = true;
    const body: any = { side, asset_class: ticket };
    if (ticket === "EQUITY") {
      body.symbol = sym.trim();
      body.quantity = qty;
    } else {
      body.underlying = underlying.trim();
      body.option_type = optType;
      body.lots = lots;
      if (optType !== "FUT") {
        if (strike !== "") body.strike = Number(strike);
        body.expiry = expiry || null;
      } else if (futPrice !== "") {
        body.price = Number(futPrice);
      }
    }
    const timer = setTimeout(() => {
      setQuoteBusy(true);
      postJSON("/sandbox/quote", body)
        .then((r) => { if (live) setQuote(r); })
        .catch(() => { if (live) setQuote(null); })
        .finally(() => { if (live) setQuoteBusy(false); });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [ticket, sym, qty, side, underlying, optType, strike, expiry, lots, futPrice]);

  const placeEquity = async () => {
    setMsg(null); setErr(null); setBusy(true);
    try {
      const r = await postJSON("/sandbox/orders", {
        symbol: sym.trim().toUpperCase(), side, quantity: qty, asset_class: "EQUITY",
      });
      setMsg(`Paper ${side} filled: ${r.quantity} × ${sym.trim().toUpperCase()} at ${inr(r.fill_price)} · charges ${inr(r.charges)} (${r.source}).`);
      load();
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
    setBusy(false);
  };

  const placeFno = async () => {
    setMsg(null); setErr(null); setBusy(true);
    try {
      const body: any = {
        symbol: underlying.trim().toUpperCase(),
        side,
        asset_class: "DERIVATIVE",
        underlying: underlying.trim().toUpperCase(),
        option_type: optType,
        lots,
      };
      if (optType !== "FUT") {
        if (strike === "") throw new Error("Pick a strike");
        body.strike = Number(strike);
        body.expiry = expiry || null;
      } else {
        if (futPrice === "") throw new Error("Enter the futures price you are filling at");
        body.price = Number(futPrice);
      }
      const r = await postJSON("/sandbox/orders", body);
      setMsg(`Paper ${side} filled: ${r.label} · ${r.lots} lot(s) × ${r.lot_size} = ${r.quantity} units at ${inr(r.fill_price)} · charges ${inr(r.charges)} (${r.source}).`);
      load();
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 260));
    }
    setBusy(false);
  };

  const close = async (id: number) => {
    setMsg(null); setErr(null); setBusy(true);
    try {
      const r = await postJSON(`/sandbox/orders/${id}/close`);
      setMsg(`Closed at ${inr(r.exit_price)} · net P&L ${inr(r.net_pnl)} after ${inr(r.total_charges)} total charges.`);
      load();
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
    setBusy(false);
  };

  const remove = async (id: number, label: string) => {
    if (!window.confirm(`Delete the ${label} sandbox leg permanently? This does not model a trade.`)) return;
    setMsg(null); setErr(null);
    try {
      await postJSON(`/sandbox/orders/${id}`, undefined, "DELETE");
      setMsg(`Deleted ${label} from the sandbox ledger.`);
      load();
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
  };

  const unwatch = async (s: string) => {
    try {
      await postJSON(`/watchlist/${encodeURIComponent(s)}`, undefined, "DELETE");
      setWatch((prev) => prev.filter((w) => w.symbol !== s));
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 160));
    }
  };

  const reset = async () => {
    if (!sum?.live_positions?.length && !sum?.closed_positions?.length) return;
    if (!window.confirm("Delete every sandbox leg and restart from ₹10,00,000 of virtual cash?")) return;
    setBusy(true);
    try {
      for (const o of [...(sum?.live_positions || []), ...(sum?.closed_positions || [])]) {
        await postJSON(`/sandbox/orders/${o.id}`, undefined, "DELETE");
      }
      setMsg("Sandbox reset. Cash is back to the full ₹10,00,000 virtual corpus.");
      load();
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
    setBusy(false);
  };

  const totalPnl = sum?.pnl?.total ?? 0;
  const hasLegs = (sum?.live_positions?.length || 0) + (sum?.closed_positions?.length || 0) > 0;

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Zero-KYC paper trading"
        title="Sandbox"
        sub="₹10,00,000 of virtual cash, real exchange prices and the platform's own statutory charge engines. Cash equities and F&O share one portfolio, and every fill is marked from a stored or live free-feed price."
        right={
          <>
            <RefreshButton stage="sandbox" label="Refresh marks" />
            <button onClick={reset} disabled={busy || !hasLegs} className="btn-secondary !py-2 !text-[12.5px]">
              Reset sandbox
            </button>
          </>
        }
      />

      {/* 3-step beginner guide */}
      <div className="card p-3.5 mb-3">
        <div className="grid sm:grid-cols-3 gap-2">
          {[
            ["1", "Pick an Index, Share, or Option", "Search all 2,401 NSE shares, 51 ETFs, indices and F&O contracts."],
            ["2", "Choose Buy/Sell & Quantity", "Long (Tezi) or Short (Mandi), then check the live cost preview."],
            ["3", "Practise Risk-Free", "₹10,00,000 virtual cash — no KYC, no broker, no real money."],
          ].map(([n, t, s]) => (
            <div key={n} className="flex items-start gap-2.5 rounded-lg px-3 py-2"
                 style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <span className="grid place-items-center h-6 w-6 rounded-full text-[11px] font-black shrink-0"
                    style={{ background: "var(--accent)", color: "#041018" }}>{n}</span>
              <div>
                <div className="text-[12px] font-bold">{t}</div>
                <div className="muted text-[10.5px] leading-snug mt-0.5">{s}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* category + quick picks + instant search */}
      <div className="card p-3.5 mb-3 space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {([
            ["EQUITY", "📈 Shares & ETFs (2,450+)"],
            ["INDEX", "📊 Indices (Nifty 50 / Sensex / Bank Nifty)"],
            ["FNO", "⚡ F&O Options (Call / Put)"],
          ] as const).map(([k, label]) => (
            <button key={k} onClick={() => chooseCategory(k)}
                    className={`chip !text-[11px] !px-3 !py-1.5 ${category === k ? "chip-active" : ""}`}>
              {label}
            </button>
          ))}
        </div>

        <div className="relative">
          <label className="block">
            <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">
              Instant search — symbol or company name
            </span>
            <input value={pickerQ}
                   onChange={(e) => {
                     setPickerQ(e.target.value); setPickerOpen(true);
                     if (category === "EQUITY") setSym(e.target.value.toUpperCase());
                     if (category === "FNO") setUnderlying(e.target.value.toUpperCase());
                   }}
                   onFocus={() => setPickerOpen(true)}
                   placeholder="Try “Paras Defence”, “Silver”, “Nifty” or “Sensex”…"
                   className="surface rounded-lg px-3 py-2 w-full text-[13px]"
                   style={{ color: "var(--ink)" }} />
          </label>
          {pickerOpen && suggestions.length > 0 && (
            <div className="absolute z-40 mt-1 w-full max-h-[280px] overflow-auto rounded-lg p-1.5"
                 style={{ background: "var(--surface)", border: "1px solid var(--line)", boxShadow: "0 12px 32px rgba(0,0,0,.2)" }}>
              {suggestions.map((it) => (
                <button key={`${it.kind}-${it.symbol}`} onClick={() => pick(it)}
                        className="w-full text-left rounded-md px-2.5 py-1.5 hover:opacity-80 flex items-center gap-2"
                        style={{ background: "transparent" }}>
                  <span className="chip !text-[8.5px] shrink-0">{it.kind}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] font-semibold truncate">{it.symbol}</span>
                    <span className="block muted text-[10px] truncate">{it.name}</span>
                  </span>
                  {it.price != null && <span className="knum text-[11px]">{inr(it.price)}</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mr-1">1-click trade</span>
          {QUICK.map((q) => (
            <button key={q.label} onClick={() => quickPick(q)}
                    className={`chip !text-[10px] ${pickerQ.toUpperCase() === q.value ? "chip-active" : ""}`}>
              {q.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className="rounded-xl px-4 py-2.5 mb-4"
        style={{
          border: "1px solid color-mix(in srgb, var(--warn) 38%, var(--line))",
          background: "color-mix(in srgb, var(--warn) 6%, transparent)",
        }}
      >
        <span className="text-[11px] font-bold uppercase tracking-[0.14em]" style={{ color: "var(--warn)" }}>
          Paper only
        </span>
        <span className="muted text-[11.5px] ml-2">
          No broker is connected, no order reaches an exchange, and no margin is blocked. Every number here is simulation.
        </span>
      </div>

      {err && <div className="mb-3"><ErrLine message={err} onRetry={load} /></div>}
      {msg && (
        <div className="mb-3 rounded-lg px-3.5 py-2.5 text-[12px]"
             style={{ border: "1px solid color-mix(in srgb, var(--up) 35%, var(--line))",
                      background: "color-mix(in srgb, var(--up) 7%, transparent)" }}>
          {msg}
        </div>
      )}

      {/* summary */}
      {!sum && !err && <div className="card p-6 muted text-[12.5px]">Loading the paper portfolio…</div>}
      {sum && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5 mb-3">
            <Metric label="Equity value" value={inr(sum.equity_value)} tip={TIPS.corpus}
                    sub={`start ${inr(sum.starting_cash)}`} />
            <Metric label="Cash available" value={inr(sum.cash_available)} sub="after open legs and charges" />
            <Metric label="Realised P&L" value={inr(sum.pnl.realized)} tip={TIPS.realized}
                    tone={sum.pnl.realized >= 0 ? "up" : "down"} />
            <Metric label="Unrealised P&L" value={inr(sum.pnl.unrealized)} tip={TIPS.unrealized}
                    tone={sum.pnl.unrealized >= 0 ? "up" : "down"} />
            <Metric label="Total P&L" value={inr(totalPnl)}
                    tone={totalPnl >= 0 ? "up" : "down"} sub={`${signed((totalPnl / sum.starting_cash) * 100, 2)}% of corpus`} />
            <Metric label="Exposure" value={inr(sum.exposure)} tip={TIPS.exposure}
                    sub={`${num(sum.allocation.equity_pct, 0)}% equity · ${num(sum.allocation.derivative_pct, 0)}% F&O`} />
          </div>

          <div className="card p-3 mb-3">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Allocation by exposure</span>
              <span className="muted text-[10.5px] knum">{inr(sum.exposure)} gross</span>
            </div>
            <div className="h-2 w-full rounded-full overflow-hidden flex" style={{ background: "var(--line)" }}>
              <div style={{ width: `${sum.allocation.equity_pct}%`, background: "var(--accent)" }} />
              <div style={{ width: `${sum.allocation.derivative_pct}%`, background: "var(--accent-2)" }} />
            </div>
            <div className="flex justify-between muted text-[10px] mt-1">
              <span>Equity {num(sum.allocation.equity_pct, 1)}%</span>
              <span>F&O {num(sum.allocation.derivative_pct, 1)}%</span>
            </div>
          </div>
        </>
      )}

      {/* tickets */}
      <div className="grid lg:grid-cols-[1fr_1fr] gap-3 mb-3">
        <Panel
          title="Place a paper order"
          sub="Equity fills use the last stored free-feed price. F&O options fill from the live NSE chain premium; futures require the price you want to fill at."
          right={
            <div className="flex gap-1">
              {(["EQUITY", "DERIVATIVE"] as const).map((k) => (
                <button key={k} onClick={() => setTicket(k)}
                        className={`chip !text-[9.5px] ${ticket === k ? "chip-active" : "hover:opacity-80"}`}>
                  {k === "EQUITY" ? "Cash equity" : "F&O"}
                </button>
              ))}
            </div>
          }
        >
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Side</span>
              <div className="flex gap-1">
                {(["BUY", "SELL"] as const).map((s) => (
                  <button key={s} onClick={() => setSide(s)}
                          className={`chip !text-[10px] ${side === s ? (s === "BUY" ? "chip-live" : "") : "hover:opacity-80"}`}
                          style={side === s && s === "SELL" ? { color: "var(--down)", borderColor: "color-mix(in srgb, var(--down) 35%, var(--line))" } : undefined}>
                    {s}
                  </button>
                ))}
              </div>
            </label>

            {ticket === "EQUITY" ? (
              <>
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Symbol</span>
                  <input value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())}
                         className="surface rounded-lg px-3 py-2 knum w-36 text-[13px]" style={{ color: "var(--ink)" }} />
                </label>
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Quantity</span>
                  <input type="number" min={1} value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))}
                         className="surface rounded-lg px-3 py-2 knum w-24 text-[13px]" style={{ color: "var(--ink)" }} />
                </label>
                <button onClick={placeEquity} disabled={busy} className="btn-primary !py-2 !text-[12.5px]">
                  {busy ? "Filling…" : side === "BUY" ? "Buy / Long (Tezi)" : "Sell / Short (Mandi)"}
                </button>
              </>
            ) : (
              <>
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Underlying</span>
                  <input value={underlying} onChange={(e) => setUnderlying(e.target.value.toUpperCase())}
                         className="surface rounded-lg px-3 py-2 knum w-32 text-[13px]" style={{ color: "var(--ink)" }} />
                </label>
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Type</span>
                  <select value={optType} onChange={(e) => setOptType(e.target.value as any)}
                          className="surface rounded-lg px-2.5 py-2 text-[12.5px]" style={{ color: "var(--ink)" }}>
                    <option value="CE">Call (CE)</option>
                    <option value="PE">Put (PE)</option>
                    <option value="FUT">Futures (FUT)</option>
                  </select>
                </label>
                {optType !== "FUT" && (
                  <>
                    <label className="block">
                      <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Expiry</span>
                      <select value={expiry} onChange={(e) => setExpiry(e.target.value)}
                              className="surface rounded-lg px-2.5 py-2 text-[12px] w-32" style={{ color: "var(--ink)" }}>
                        {(chain?.expiries || []).map((x: string) => <option key={x} value={x}>{x}</option>)}
                        {!chain?.expiries?.length && <option value="">—</option>}
                      </select>
                    </label>
                    <label className="block">
                      <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Strike</span>
                      <input type="number" value={strike} onChange={(e) => setStrike(e.target.value === "" ? "" : Number(e.target.value))}
                             className="surface rounded-lg px-3 py-2 knum w-24 text-[13px]" style={{ color: "var(--ink)" }} />
                    </label>
                  </>
                )}
                {optType === "FUT" && (
                  <label className="block">
                    <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Futures price</span>
                    <input type="number" value={futPrice} onChange={(e) => setFutPrice(e.target.value === "" ? "" : Number(e.target.value))}
                           placeholder="optional · spot"
                           className="surface rounded-lg px-3 py-2 knum w-28 text-[13px]" style={{ color: "var(--ink)" }} />
                  </label>
                )}
                <label className="block">
                  <span className="muted text-[9px] font-bold uppercase tracking-[0.13em] block mb-1">Lots</span>
                  <input type="number" min={1} value={lots} onChange={(e) => setLots(Math.max(1, Number(e.target.value) || 1))}
                         className="surface rounded-lg px-3 py-2 knum w-20 text-[13px]" style={{ color: "var(--ink)" }} />
                </label>
                <button onClick={placeFno} disabled={busy} className="btn-primary !py-2 !text-[12.5px]">
                  {busy ? "Filling…" : side === "BUY" ? "Buy / Long (Tezi)" : "Sell / Short (Mandi)"}
                </button>
              </>
            )}
          </div>

          {/* live order cost & charges preview */}
          <div className="mt-3 rounded-lg p-3"
               style={{ border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
                        background: "color-mix(in srgb, var(--accent) 5%, transparent)" }}>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-[10px] font-black uppercase tracking-[0.13em] accent">Order cost &amp; charges preview</span>
              {quoteBusy && <span className="muted text-[10px]">pricing…</span>}
            </div>
            {quote ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div>
                  <div className="muted text-[9px] uppercase tracking-wider">Instrument</div>
                  <div className="text-[11.5px] font-bold truncate">{quote.symbol}</div>
                  <div className="muted text-[9.5px] truncate">{quote.name}</div>
                </div>
                <div>
                  <div className="muted text-[9px] uppercase tracking-wider">Fill price · qty</div>
                  <div className="knum text-[11.5px] font-bold">{inr(quote.price)} × {num(quote.quantity, 0)}</div>
                  <div className="muted text-[9.5px] truncate">{quote.lot_size > 1 ? `${quote.lots} lot(s) × ${quote.lot_size}` : quote.source}</div>
                </div>
                <div>
                  <div className="muted text-[9px] uppercase tracking-wider">Investment amount</div>
                  <div className="knum text-[11.5px] font-bold">{inr(quote.value)}</div>
                  <div className="muted text-[9.5px]">brokerage/STT {inr(quote.charges)}</div>
                </div>
                <div>
                  <div className="muted text-[9px] uppercase tracking-wider">Remaining virtual cash</div>
                  <div className="knum text-[11.5px] font-bold" style={{ color: quote.cash_after >= 0 ? "var(--up)" : "var(--down)" }}>
                    {inr(quote.cash_after)}
                  </div>
                  <div className="muted text-[9.5px]">from {inr(quote.cash_available)}</div>
                </div>
              </div>
            ) : (
              <p className="muted text-[11px]">Pick an instrument to see the fill value, statutory charges and cash left before you place the order.</p>
            )}
          </div>

          {ticket === "DERIVATIVE" && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {chainBusy && <span className="muted text-[11px]">Reading the NSE chain…</span>}
              {chainErr && <span className="text-[11px]" style={{ color: "var(--warn)" }}>{chainErr}</span>}
              {Number.isFinite(spot) && <Pill tone="accent">spot {inr(spot)}</Pill>}
              {chain?.active_expiry && <Pill>active expiry {chain.active_expiry}</Pill>}
              {chain?.mode && <Pill tone={chain.mode === "live" ? "up" : "warn"}>{chain.mode}</Pill>}
              {chain?.lot_note && <span className="muted text-[10.5px]">{chain.lot_note}</span>}
            </div>
          )}
          <Note>
            Options fill from the live NSE chain and are rejected rather than invented when it does not answer.
            Index futures fall back to the live index spot and are labelled as a spot proxy; you can override
            the fill price above. All 2,401 NSE shares and 51 ETFs resolve by symbol or company name.
          </Note>
        </Panel>

        <Panel
          title="Portfolio history"
          sub="Event-based equity curve. Each point is a date on which the portfolio changed, plus today."
        >
          {hist ? (
            <>
              <HistoryChart points={hist.points || []} baseline={sum?.starting_cash || 1000000} />
              <Note>{hist.note}</Note>
            </>
          ) : (
            <p className="muted text-[12px]">Loading…</p>
          )}
        </Panel>
      </div>

      {/* open positions */}
      <Panel
        title="Open positions"
        sub="Marks come from the last available free feed. An option premium can be stale if the chain has not updated."
        right={<Pill>{sum?.live_positions?.length || 0} open</Pill>}
        className="mb-3"
      >
        {!sum?.live_positions?.length ? (
          <p className="muted text-[12px]">No open paper legs. Place one above to start the ledger.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  {["Contract", "Class", "Side", "Qty", "Entry", "Mark", "Source", "Charges", "P&L", "P&L %", ""].map((h) => (
                    <th key={h} className={`table-head px-3 py-2 ${["Contract", "Class", "Source"].includes(h) ? "text-left" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sum.live_positions.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td className="px-3 py-2.5">
                      {p.href ? (
                        <Link href={p.href} className="text-[12px] font-bold hover:underline">{p.symbol}</Link>
                      ) : (
                        <span className="text-[12px] font-bold">{p.label}</span>
                      )}
                      {p.asset_class === "DERIVATIVE" && (
                        <div className="muted text-[9.5px] knum">
                          {p.underlying} {p.strike ? p.strike : ""} {p.option_type} · {p.expiry || "—"}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-left">
                      <Pill tone={p.asset_class === "DERIVATIVE" ? "accent" : "neutral"}>
                        {p.asset_class === "DERIVATIVE" ? "F&O" : "Equity"}
                      </Pill>
                    </td>
                    <td className={`px-3 py-2.5 text-right text-[11.5px] font-bold ${p.side === "BUY" ? "text-up" : "text-down"}`}>{p.side}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{num(p.qty, 0)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{inr(p.entry)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{inr(p.mark)}</td>
                    <td className="px-3 py-2.5 text-left muted text-[10px] max-w-[160px] truncate" title={p.mark_source}>{p.mark_source}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11px]">{inr(p.charges)}</td>
                    <td className={`px-3 py-2.5 text-right knum text-[11.5px] font-bold ${p.pnl >= 0 ? "text-up" : "text-down"}`}>{inr(p.pnl)}</td>
                    <td className={`px-3 py-2.5 text-right knum text-[11.5px] ${(p.pnl_pct || 0) >= 0 ? "text-up" : "text-down"}`}>{p.pnl_pct == null ? "—" : pct(p.pnl_pct)}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <button onClick={() => close(p.id)} disabled={busy} className="btn-secondary !px-2.5 !py-1 !text-[10.5px] mr-1">Close</button>
                      <button onClick={() => remove(p.id, p.label)} className="muted text-[10.5px] hover:underline">delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {sum?.marking_note?.value && <Note>{sum.marking_note.value}</Note>}
        {sum?.margin_note && <Note>{sum.margin_note}</Note>}
      </Panel>

      {/* closed positions */}
      <Panel
        title="Closed positions"
        sub="Realised P&L is net of both legs' statutory charges."
        right={<Pill>{sum?.closed_positions?.length || 0} closed</Pill>}
        className="mb-3"
      >
        {!sum?.closed_positions?.length ? (
          <p className="muted text-[12px]">Nothing closed yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse">
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  {["Contract", "Class", "Side", "Qty", "Entry", "Exit", "Charges", "Realised P&L", "Closed", ""].map((h) => (
                    <th key={h} className={`table-head px-3 py-2 ${["Contract", "Class"].includes(h) ? "text-left" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sum.closed_positions.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td className="px-3 py-2.5 text-[12px] font-semibold">{p.label}</td>
                    <td className="px-3 py-2.5 text-left">
                      <Pill tone={p.asset_class === "DERIVATIVE" ? "accent" : "neutral"}>
                        {p.asset_class === "DERIVATIVE" ? "F&O" : "Equity"}
                      </Pill>
                    </td>
                    <td className={`px-3 py-2.5 text-right text-[11.5px] font-bold ${p.side === "BUY" ? "text-up" : "text-down"}`}>{p.side}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{num(p.qty, 0)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{inr(p.entry)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11.5px]">{inr(p.exit)}</td>
                    <td className="px-3 py-2.5 text-right knum text-[11px]">{inr(p.charges)}</td>
                    <td className={`px-3 py-2.5 text-right knum text-[11.5px] font-bold ${p.realized_pnl >= 0 ? "text-up" : "text-down"}`}>{inr(p.realized_pnl)}</td>
                    <td className="px-3 py-2.5 text-right muted text-[10.5px] knum">{p.closed_at ? p.closed_at.slice(0, 10) : "—"}</td>
                    <td className="px-3 py-2.5 text-right">
                      <button onClick={() => remove(p.id, p.label)} className="muted text-[10.5px] hover:underline">delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* watchlist */}
      <Panel
        title="Watchlist"
        sub="Saved from any stock or index page with the ☆ button. Removing here updates the same table those pages read."
        right={<Link href="/stocks" className="accent text-[11.5px] hover:underline">Browse equities →</Link>}
      >
        {watch.length === 0 ? (
          <p className="muted text-[12px]">
            Nothing saved yet. Open a stock or index page and press <strong>☆ Add to Watchlist</strong>.
          </p>
        ) : (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2">
            {watch.map((w) => (
              <div key={w.symbol} className="rounded-lg px-3 py-2.5 flex items-center gap-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <Link href={w.href} className="min-w-0 flex-1">
                  <div className="text-[12px] font-bold hover:underline truncate">{w.symbol}</div>
                  <div className="muted text-[10px] truncate">{w.name} · {w.kind}</div>
                </Link>
                <div className="text-right shrink-0">
                  <div className="knum text-[11.5px] font-semibold">{w.last == null ? "—" : inr(w.last)}</div>
                  <div className={`knum text-[10.5px] ${(w.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>
                    {w.changepct == null ? "—" : pct(w.changepct)}
                  </div>
                </div>
                <button onClick={() => unwatch(w.symbol)} title={`Remove ${w.symbol}`}
                        className="muted text-[13px] hover:opacity-70 shrink-0">✕</button>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
