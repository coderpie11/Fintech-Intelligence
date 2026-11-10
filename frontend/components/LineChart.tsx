"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { pct } from "@/lib/format";

export type ChartHoverPoint = {
  price: number;
  change: number;
  pctChange: number;
  label: string;
};

export type ChartPoint = {
  date?: string;
  close?: number;
  open?: number;
  high?: number;
  low?: number;
  time?: string;
  datetime?: string;
  volume?: number;
  // Raw market candle fields are accepted too, so pages can pass the payload
  // straight through without a mapping layer.
  c?: number;
  o?: number;
  h?: number;
  l?: number;
  v?: number;
};

type Norm = {
  date: string;
  time: string | null;
  datetime: string | null;
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number | null;
};

// Point counts, not intervals: including the anchor session keeps the chart's
// period return identical to the performance ladder.
const RANGES: { key: string; label: string; days: number | null }[] = [
  { key: "1D", label: "1D", days: 2 },
  { key: "1W", label: "1W", days: 6 },
  { key: "1M", label: "1M", days: 22 },
  { key: "3M", label: "3M", days: 64 },
  { key: "6M", label: "6M", days: 127 },
  { key: "1Y", label: "1Y", days: 253 },
  { key: "3Y", label: "3Y", days: 757 },
  { key: "5Y", label: "5Y", days: null },
];

const MAX_POINTS = 700;

function num(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function normalise(p: ChartPoint | null | undefined): Norm | null {
  if (!p) return null;
  const close = num(p.close) ?? num(p.c);
  if (close == null) return null;
  const open = num(p.open) ?? num(p.o) ?? close;
  const high = num(p.high) ?? num(p.h) ?? Math.max(open, close);
  const low = num(p.low) ?? num(p.l) ?? Math.min(open, close);
  return {
    date: p.date || p.datetime || "",
    time: p.time || null,
    datetime: p.datetime || null,
    close, open, high, low,
    volume: num(p.volume) ?? num(p.v),
  };
}

/** Grouped Indian digit formatting without a currency symbol. */
function fmtNum(n: number, dec = 2): string {
  if (!Number.isFinite(n)) return "—";
  const [int, frac] = Math.abs(n).toFixed(dec).split(".");
  const tail = int.length > 3 ? int.slice(-3) : int;
  const head = int.length > 3 ? int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",") : "";
  return `${n < 0 ? "-" : ""}${head ? head + "," : ""}${tail}${frac ? "." + frac : ""}`;
}

function fmtAxis(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e7) return `${(n / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `${(n / 1e5).toFixed(1)}L`;
  if (a >= 1e4) return `${(n / 1e3).toFixed(1)}k`;
  if (a >= 100) return n.toFixed(0);
  return n.toFixed(2);
}

function fmtVolume(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)} K`;
  return n.toLocaleString("en-IN");
}

function fmtDateShort(d: string): string {
  if (!d) return "";
  try {
    return new Date(d).toLocaleDateString("en-IN", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return d;
  }
}

function fmtClock(d: string | null | undefined): string | null {
  if (!d || !/[T:]/.test(d)) return null;
  try {
    return new Date(d).toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
    }) + " IST";
  } catch {
    return null;
  }
}

/**
 * Keep first/last, every extreme, and an even sample of the rest.
 *
 * The old chart passed 1,200+ points straight into one SVG path and animated
 * `strokeDasharray: 2400`, which cut the stroke after a fixed length and made
 * the 5-year gold/silver line disappear over most of the width. Extreme
 * preservation means the peak/trough markers still sit on real prices.
 */
function downsample(points: Norm[], limit = MAX_POINTS): Norm[] {
  const n = points.length;
  if (n <= limit) return points;
  const keep = new Set<number>([0, n - 1]);
  let hi = 0, lo = 0, hiHigh = 0, loLow = 0;
  for (let i = 1; i < n; i++) {
    if (points[i].close > points[hi].close) hi = i;
    if (points[i].close < points[lo].close) lo = i;
    if (points[i].high > points[hiHigh].high) hiHigh = i;
    if (points[i].low < points[loLow].low) loLow = i;
  }
  keep.add(hi); keep.add(lo); keep.add(hiHigh); keep.add(loLow);
  const step = (n - 1) / (limit - keep.size - 1);
  for (let k = 0; k < limit - keep.size; k++) keep.add(Math.round(k * step));
  return Array.from(keep).sort((a, b) => a - b).map((i) => points[i]);
}

export default function LineChart({
  points,
  width = 1000,
  height = 300,
  stroke,
  animate = true,
  labelDates = true,
  showPills = true,
  defaultRange = "1Y",
  intraday = false,
  intradayPoints,
  intradaySource,
  title,
  compact = false,
  prevClose,
  valuePrefix = "₹",
  valueSuffix = "",
  onHoverPointChange,
}: {
  points: ChartPoint[];
  width?: number;
  height?: number;
  stroke?: string;
  animate?: boolean;
  labelDates?: boolean;
  showPills?: boolean;
  defaultRange?: string;
  intraday?: boolean;
  intradayPoints?: ChartPoint[];
  intradaySource?: string;
  title?: string;
  compact?: boolean;
  prevClose?: number | null;
  valuePrefix?: string;
  valueSuffix?: string;
  onHoverPointChange?: (point: ChartHoverPoint | null) => void;
}) {
  const [range, setRange] = useState(defaultRange);
  const [mode, setMode] = useState<"line" | "candles">("line");
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const [tipX, setTipX] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const gradId = useId().replace(/:/g, "");

  const daily = useMemo(
    () => (points || []).map(normalise).filter((p): p is Norm => p !== null),
    [points],
  );
  const intradayClean = useMemo(
    () => (intradayPoints || []).map(normalise).filter((p): p is Norm => p !== null),
    [intradayPoints],
  );

  const liveIntraday = range === "1D" && intradayClean.length >= 2;

  const visible = useMemo(() => {
    if (liveIntraday) return downsample(intradayClean);
    const cfg = RANGES.find((r) => r.key === range);
    // 1D without an intraday payload still shows a real curve: the last 60
    // daily closes rather than a two-point straight line.
    const n = range === "1D" ? 60 : cfg?.days;
    const clean = !n || daily.length <= n ? daily : daily.slice(-n);
    return downsample(clean);
  }, [daily, range, intradayClean, liveIntraday]);

  const active = hover ?? pinned;
  const activePoint = active != null ? visible[active] : null;

  // Measure the container so the SVG viewBox matches real CSS pixels. Without
  // this a 1000-unit viewBox is squeezed into ~340px on a phone and every axis
  // label renders at about a third of its intended size.
  const [vw, setVw] = useState(0);
  const ready = visible.length >= 2;
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const apply = () => setVw(el.clientWidth);
    apply();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ready]);

  // Publish the scrubbed candle to the page header (terminal style).
  const hoverPoint = activePoint;
  useEffect(() => {
    if (!onHoverPointChange) return;
    if (!hoverPoint) {
      onHoverPointChange(null);
      return;
    }
    const idx = active ?? 0;
    const base = liveIntraday
      ? (num(prevClose) ?? (idx > 0 ? visible[idx - 1].close : hoverPoint.open))
      : (idx > 0 ? visible[idx - 1].close : hoverPoint.close);
    const change = hoverPoint.close - base;
    const pctChange = base ? (change / base) * 100 : 0;
    const label = [fmtDateShort(hoverPoint.date), hoverPoint.time ||
      fmtClock(hoverPoint.datetime)].filter(Boolean).join(" · ");
    onHoverPointChange({ price: hoverPoint.close, change, pctChange, label });
  }, [active, hoverPoint, visible, liveIntraday, prevClose, onHoverPointChange]);

  if (!visible || visible.length < 2) {
    return (
      <div className="card p-6 muted text-[13px]">
        Chart pending — history will appear once the data feed is seeded/refreshed.
      </div>
    );
  }

  const W = Math.max(280, Math.round(vw || width));
  const H = height;
  const pad = { l: 10, r: 62, t: 18, b: 26 };
  const closes = visible.map((p) => p.close);
  let min = Math.min(...visible.map((p) => p.low));
  let max = Math.max(...visible.map((p) => p.high));
  if (max === min) { max += Math.max(1, max * 0.005); min -= Math.max(1, max * 0.005); }
  const padY = (max - min) * 0.08;
  min -= padY;
  max += padY;

  const hasVolume = visible.some((p) => (p.volume || 0) > 0);
  const showVolume = mode === "candles" && hasVolume;
  const volH = showVolume ? Math.max(18, Math.round((H - pad.t - pad.b) * 0.16)) : 0;
  const priceBottom = H - pad.b - (showVolume ? volH + 10 : 0);
  const maxVolume = Math.max(...visible.map((p) => p.volume || 0), 1);

  const x = (i: number) => pad.l + (i / (visible.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * (priceBottom - pad.t);

  const line = visible.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(p.close).toFixed(2)}`).join(" ");
  const area = `${line} L${x(visible.length - 1).toFixed(2)},${priceBottom} L${x(0).toFixed(2)},${priceBottom} Z`;

  const first = visible[0].close;
  const last = visible[visible.length - 1].close;
  const periodReturn = first ? ((last / first) - 1) * 100 : 0;
  const positive = periodReturn >= 0;
  const color = stroke || (positive ? "var(--up)" : "var(--down)");

  const hi = Math.max(...visible.map((p) => p.high));
  const lo = Math.min(...visible.map((p) => p.low));
  const hiIdx = visible.findIndex((p) => p.high === hi);
  const loIdx = visible.findIndex((p) => p.low === lo);

  const ticks = compact ? 3 : 5;
  const tVals = Array.from({ length: ticks }, (_, i) => min + ((max - min) * i) / (ticks - 1));
  const xTicks = Math.min(compact ? 3 : 5, visible.length);
  const xIdx = Array.from({ length: xTicks }, (_, i) =>
    Math.round((i / Math.max(xTicks - 1, 1)) * (visible.length - 1)));

  // Intraday labels only when the series actually has multiple clock times.
  const distinctTimes = new Set(visible.map((p) => p.time).filter(Boolean));
  const timeAxis = liveIntraday && distinctTimes.size > 1;

  const onMove = (clientX: number) => {
    const el = wrap.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = clientX - r.left;
    const xView = (px / Math.max(r.width, 1)) * W;
    const raw = ((xView - pad.l) / (W - pad.l - pad.r)) * (visible.length - 1);
    const i = Math.max(0, Math.min(visible.length - 1, Math.round(raw)));
    setHover(i);
    setTipX(Math.max(8, Math.min(px, r.width - 8)));
  };

  const val = (v: number | null | undefined, dec = 2) =>
    v == null || !Number.isFinite(v) ? "—" : `${valuePrefix}${fmtNum(v, dec)}${valueSuffix}`;

  const hp = activePoint;
  const hpIdx = active ?? 0;
  const basePrice = liveIntraday
    ? (num(prevClose) ?? (hpIdx > 0 ? visible[hpIdx - 1].close : hp?.open ?? null))
    : (hpIdx > 0 ? visible[hpIdx - 1].close : hp?.close ?? null);
  const change = hp && basePrice != null ? hp.close - basePrice : null;
  const changePct = change != null && basePrice ? (change / basePrice) * 100 : null;
  const hoverPct = hp ? ((hp.close / first) - 1) * 100 : 0;

  const candleW = Math.max(1, ((W - pad.l - pad.r) / visible.length) * 0.62);
  const showWicks = candleW >= 1.6;

  return (
    <div className="w-full">
      {/* ---- pinned header: metrics left, controls top-right ---- */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-start sm:justify-between sm:gap-4 mb-3">
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 min-w-0 flex-1">
          {title && <div className="text-[13px] font-bold tracking-tight">{title}</div>}
          <div>
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">Period high</div>
            <div className="knum text-[13.5px] font-bold">{val(hi)}</div>
          </div>
          <div>
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">Period low</div>
            <div className="knum text-[13.5px] font-bold">{val(lo)}</div>
          </div>
        </div>

        <div className="w-full sm:w-auto sm:ml-auto shrink-0 overflow-x-auto scrollbar-none -mx-0.5 px-0.5">
          <div className="flex items-center gap-2 min-w-max">
          {showPills && (
            <>
              <div className="flex items-center gap-0.5 rounded-lg p-1"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                <button
                  onClick={() => { setMode("line"); setPinned(null); }}
                  aria-pressed={mode === "line"}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                    mode === "line" ? "text-white" : "muted hover:text-[var(--ink)]"
                  }`}
                  style={mode === "line" ? { background: "var(--accent)", color: "#041018" } : undefined}
                >
                  📈 Line
                </button>
                <button
                  onClick={() => { setMode("candles"); setPinned(null); }}
                  aria-pressed={mode === "candles"}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                    mode === "candles" ? "text-white" : "muted hover:text-[var(--ink)]"
                  }`}
                  style={mode === "candles" ? { background: "var(--accent)", color: "#041018" } : undefined}
                >
                  🕯️ Candles
                </button>
              </div>
              <div className="flex items-center gap-0.5 rounded-lg p-1"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                {RANGES.map((r) => (
                  <button
                    key={r.key}
                    onClick={() => { setRange(r.key); setHover(null); setPinned(null); }}
                    aria-pressed={range === r.key}
                    className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                      range === r.key ? "text-white" : "muted hover:text-[var(--ink)]"
                    }`}
                    style={range === r.key
                      ? { background: "var(--accent)", color: "#041018" }
                      : undefined}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </>
          )}
          </div>
        </div>
      </div>

      {/* ---- chart ---- */}
      <div ref={wrap} className="relative w-full select-none">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto touch-none"
          role="img"
          aria-label={title ? `${title} price chart` : "Price history chart"}
          onMouseMove={(e) => onMove(e.clientX)}
          onMouseLeave={() => setHover(null)}
          onClick={() => setPinned((p) => (hover == null ? null : p === hover ? null : hover))}
          onTouchStart={(e) => { onMove(e.touches[0].clientX); setPinned(null); }}
          onTouchMove={(e) => onMove(e.touches[0].clientX)}
          onTouchEnd={() => setHover(null)}
        >
          <defs>
            <linearGradient id={`area-${gradId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.26" />
              <stop offset="55%" stopColor={color} stopOpacity="0.07" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
            <filter id={`glow-${gradId}`} x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="3.2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* horizontal grid + y labels */}
          {tVals.map((v, i) => (
            <g key={`y${i}`}>
              <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)}
                    stroke="var(--line)" strokeWidth="0.7" strokeDasharray="2 5" opacity="0.75" />
              <text x={W - pad.r + 8} y={y(v) + 3} fontSize="10" fill="var(--muted)"
                    fontFamily="var(--font-mono, monospace)">
                {fmtAxis(v)}
              </text>
            </g>
          ))}

          {/* x labels */}
          {labelDates && xIdx.map((i, k) => (
            <text
              key={`x${k}`}
              x={x(i)}
              y={H - 7}
              fontSize="9.5"
              fill="var(--muted)"
              textAnchor={k === 0 ? "start" : k === xIdx.length - 1 ? "end" : "middle"}
              fontFamily="var(--font-mono, monospace)"
            >
              {timeAxis
                ? (visible[i].time || fmtClock(visible[i].datetime) || "")
                : fmtDateShort(visible[i].date)}
            </text>
          ))}

          {/* period high / low guides */}
          <line x1={pad.l} x2={W - pad.r} y1={y(hi)} y2={y(hi)}
                stroke="var(--up)" strokeWidth="0.7" strokeDasharray="3 6" opacity="0.35" />
          <line x1={pad.l} x2={W - pad.r} y1={y(lo)} y2={y(lo)}
                stroke="var(--down)" strokeWidth="0.7" strokeDasharray="3 6" opacity="0.35" />

          {mode === "line" ? (
            <>
              <path d={area} fill={`url(#area-${gradId})`} />
              <path
                d={line}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                style={animate ? { animation: "fadein 0.45s ease-out" } : undefined}
              />
              <circle cx={x(visible.length - 1)} cy={y(last)} r="3.2" fill={color} />
              <circle cx={x(visible.length - 1)} cy={y(last)} r="7" fill={color} opacity="0.14" />
            </>
          ) : (
            <g>
              {visible.map((p, i) => {
                const rising = p.close >= p.open;
                const c = rising ? "var(--up)" : "var(--down)";
                const xc = x(i);
                const top = y(Math.max(p.open, p.close));
                const bottom = y(Math.min(p.open, p.close));
                return (
                  <g key={`c${i}`}>
                    {showWicks && (
                      <line x1={xc} x2={xc} y1={y(p.high)} y2={y(p.low)}
                            stroke={c} strokeWidth={Math.max(0.7, candleW * 0.16)}
                            opacity="0.9" />
                    )}
                    <rect x={xc - candleW / 2} y={top} width={candleW}
                          height={Math.max(1, bottom - top)} fill={c} opacity="0.92" />
                    {showVolume && (
                      <rect x={xc - candleW / 2}
                            y={H - pad.b - ((p.volume || 0) / maxVolume) * volH}
                            width={candleW}
                            height={Math.max(1, ((p.volume || 0) / maxVolume) * volH)}
                            fill={c} opacity="0.35" />
                    )}
                  </g>
                );
              })}
              <text x={W - pad.r + 8} y={H - pad.b - volH / 2} fontSize="9" fill="var(--muted)"
                    fontFamily="var(--font-mono, monospace)">VOL</text>
            </g>
          )}

          {/* extreme markers (always visible, including on downsampled series) */}
          {hiIdx >= 0 && hiIdx !== visible.length - 1 && (
            <circle cx={x(hiIdx)} cy={y(hi)} r="2.4" fill="var(--up)" opacity="0.7" />
          )}
          {loIdx >= 0 && loIdx !== visible.length - 1 && (
            <circle cx={x(loIdx)} cy={y(lo)} r="2.4" fill="var(--down)" opacity="0.7" />
          )}

          {/* crosshair */}
          {hp && active != null && (
            <g>
              <line x1={x(active)} x2={x(active)} y1={pad.t} y2={priceBottom}
                    stroke="var(--muted)" strokeWidth="0.8" strokeDasharray="3 4" opacity="0.8" />
              <line x1={pad.l} x2={W - pad.r} y1={y(hp.close)} y2={y(hp.close)}
                    stroke="var(--muted)" strokeWidth="0.8" strokeDasharray="3 4" opacity="0.8" />
              <circle cx={x(active)} cy={y(hp.close)} r="9" fill={color} opacity="0.18" />
              <circle cx={x(active)} cy={y(hp.close)} r="4" fill={color}
                      filter={`url(#glow-${gradId})`} stroke="var(--surface)" strokeWidth="1.4" />
              <g>
                <rect x={W - pad.r + 2} y={y(hp.close) - 9} width={pad.r - 4} height="18"
                      rx="3" fill={color} opacity="0.92" />
                <text x={W - pad.r + (pad.r - 4) / 2 + 2} y={y(hp.close) + 3.5} fontSize="9.5"
                      textAnchor="middle" fill="#041018" fontWeight="700"
                      fontFamily="var(--font-mono, monospace)">
                  {fmtAxis(hp.close)}
                </text>
              </g>
            </g>
          )}
        </svg>

        {/* floating inspector: full OHLCV, hover or pinned on click */}
        {hp && (
          <div
            className="tip-card absolute z-30 w-[224px] p-3 pointer-events-none"
            style={{
              // Clamp inside the chart wrapper so the inspector can never be
              // clipped off a narrow phone screen.
              left: `clamp(0px, ${
                tipX > (wrap.current?.clientWidth || 600) - 246 ? tipX - 234 : tipX + 14
              }px, calc(100% - 232px))`,
              top: 8,
            }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="knum text-[11px] muted">{fmtDateShort(hp.date)}</span>
              {(hp.time || fmtClock(hp.datetime)) && (
                <span className="knum text-[10.5px] muted">
                  {hp.time || fmtClock(hp.datetime)}
                </span>
              )}
            </div>
            <div className="knum text-[20px] font-black mt-1" style={{ color: "var(--ink)" }}>
              {val(hp.close)}
            </div>
            <div className="mt-1 flex items-center justify-between text-[11px]">
              <span className="muted">Change</span>
              <span className={`knum font-bold ${(change ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                {change == null ? "—" : `${change >= 0 ? "+" : ""}${valuePrefix}${fmtNum(change)}${valueSuffix}`}
                {changePct != null ? ` · ${pct(changePct)}` : ""}
              </span>
            </div>
            <div className="mt-1.5 pt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-[10.5px]"
                 style={{ borderTop: "1px solid var(--line)" }}>
              <Row label="Open" value={val(hp.open)} />
              <Row label="High" value={val(hp.high)} />
              <Row label="Low" value={val(hp.low)} />
              <Row label="Prev close" value={val(basePrice)} />
              <Row label="Volume" value={fmtVolume(hp.volume)} />
              <Row label="Period" value={pct(hoverPct)} tone={hoverPct >= 0 ? "up" : "down"} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <>
      <span className="muted">{label}</span>
      <span className={`knum text-right font-semibold ${tone === "up" ? "text-up" : tone === "down" ? "text-down" : ""}`}
            style={tone ? undefined : { color: "var(--ink)" }}>
        {value}
      </span>
    </>
  );
}
