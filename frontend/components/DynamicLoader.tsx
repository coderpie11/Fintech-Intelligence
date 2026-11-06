"use client";

import { useEffect, useState, type ReactNode } from "react";

/**
 * Fifteen hand-drawn SVG loading animations for the terminal. A module-level
 * shuffled queue hands out a different one on every mount and never repeats
 * the same animation twice in a row — page loads, desks, search and the AI
 * teacher all draw from the same deck.
 */

const EM = "#10B981";
const CR = "#F43F5E";
const AM = "#F59E0B";
const ZN = "#52525B";
const MUT = "#A1A1AA";

export const ANIMATION_NAMES = [
  "Live Candlestick Surge",
  "Bull & Bear Pulse",
  "Compounding Coins",
  "Orderbook Wave",
  "Radar Scanner",
  "Wealth Staircase",
  "Ticker Stream",
  "Portfolio Ring",
  "Option Curve Sweep",
  "Yield Pendulum",
  "Breakout Rocket",
  "Quant Neural Nodes",
  "Balance Scale",
  "Volume Equalizer",
  "Market Compass",
] as const;

/* ---------------------------------------------------------------- animations */

function CandlestickSurge() {
  const bars = [
    { x: 7, hi: 34, lo: 8, up: true },
    { x: 15, hi: 28, lo: 14, up: false },
    { x: 23, hi: 36, lo: 6, up: true },
    { x: 31, hi: 30, lo: 11, up: true },
    { x: 39, hi: 24, lo: 5, up: false },
  ];
  return (
    <g>
      {bars.map((b, i) => (
        <g key={i} stroke={b.up ? EM : CR} fill={b.up ? EM : CR}>
          <line x1={b.x} x2={b.x} y1={b.lo} y2={b.hi} strokeWidth="1.4" opacity="0.75" />
          <rect x={b.x - 2.6} y={b.hi} width="5.2" height={Math.max(4, b.lo - b.hi - 2)} rx="1">
            <animate attributeName="height" values="4;14;4" dur="1.5s" begin={`${i * 0.12}s`} repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.55;1;0.55" dur="1.5s" begin={`${i * 0.12}s`} repeatCount="indefinite" />
          </rect>
        </g>
      ))}
      <line x1="4" y1="42" x2="44" y2="42" stroke={ZN} strokeWidth="1" />
    </g>
  );
}

function BullBearPulse() {
  return (
    <g fill="none" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 24 L16 15 L23 19 L40 7" stroke={EM} strokeDasharray="80" strokeDashoffset="80">
        <animate attributeName="stroke-dashoffset" values="80;0" dur="1.3s" repeatCount="indefinite" />
      </path>
      <path d="M6 24 L16 33 L23 29 L40 41" stroke={CR} strokeDasharray="80" strokeDashoffset="80">
        <animate attributeName="stroke-dashoffset" values="80;0" dur="1.3s" repeatCount="indefinite" />
      </path>
      <circle cx="6" cy="24" r="2.6" fill="#F4F4F5" stroke="none">
        <animate attributeName="r" values="2.2;3.4;2.2" dur="1.3s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function CompoundingCoins() {
  const coins = [
    { cx: 14, cy: 35, r: 5, d: "0s", c: AM },
    { cx: 24, cy: 27, r: 6, d: "0.35s", c: EM },
    { cx: 35, cy: 17, r: 7, d: "0.7s", c: AM },
  ];
  return (
    <g>
      {coins.map((c, i) => (
        <g key={i}>
          <circle cx={c.cx} cy={c.cy} r={c.r} fill="none" stroke={c.c} strokeWidth="2">
            <animate attributeName="opacity" values="0.25;1;0.25" dur="1.8s" begin={c.d} repeatCount="indefinite" />
          </circle>
          <text x={c.cx} y={c.cy + 3} textAnchor="middle" fontSize="7" fill={c.c} fontWeight="700">
            ₹
            <animate attributeName="opacity" values="0.25;1;0.25" dur="1.8s" begin={c.d} repeatCount="indefinite" />
          </text>
        </g>
      ))}
    </g>
  );
}

function OrderbookWave() {
  const rows = [0, 1, 2, 3, 4, 5];
  return (
    <g>
      <line x1="24" y1="6" x2="24" y2="42" stroke={ZN} strokeWidth="1" strokeDasharray="2 3" />
      {rows.map((r) => {
        const bid = r % 2 === 0;
        const y = 9 + r * 5.4;
        return (
          <rect key={r} x={bid ? 24 : 24} y={y} height="3.2" rx="1.4" fill={bid ? EM : CR} opacity="0.85">
            <animate attributeName="width" values={bid ? "5;17;5" : "5;15;5"} dur="1.4s" begin={`${r * 0.1}s`} repeatCount="indefinite" />
            <animate attributeName="x" values={bid ? "19;7;19" : "24;24;24"} dur="1.4s" begin={`${r * 0.1}s`} repeatCount="indefinite" />
          </rect>
        );
      })}
    </g>
  );
}

function RadarScanner() {
  return (
    <g>
      <circle cx="24" cy="24" r="17" fill="none" stroke={ZN} strokeWidth="1.2" />
      <circle cx="24" cy="24" r="10" fill="none" stroke={ZN} strokeWidth="1" opacity="0.7" />
      <circle cx="24" cy="24" r="3" fill="none" stroke={ZN} strokeWidth="1" opacity="0.5" />
      <g>
        <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="2.1s" repeatCount="indefinite" />
        <line x1="24" y1="24" x2="24" y2="7" stroke={EM} strokeWidth="2" strokeLinecap="round" />
        <circle cx="24" cy="7" r="2.4" fill={EM} />
      </g>
      <circle cx="33" cy="17" r="2" fill={AM}>
        <animate attributeName="opacity" values="0;1;0" dur="2.1s" repeatCount="indefinite" />
      </circle>
      <circle cx="15" cy="31" r="1.7" fill={EM}>
        <animate attributeName="opacity" values="0;0.9;0" dur="2.1s" begin="0.9s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function WealthStaircase() {
  const steps = [
    { x: 6, y: 34, h: 8 },
    { x: 16, y: 28, h: 14 },
    { x: 26, y: 21, h: 21 },
    { x: 36, y: 13, h: 29 },
  ];
  return (
    <g>
      {steps.map((s, i) => (
        <rect key={i} x={s.x} y={s.y} width="7" height={s.h} rx="1.5" fill={i === 3 ? EM : AM} opacity="0.9">
          <animate attributeName="opacity" values="0.15;0.95;0.15" dur="2s" begin={`${i * 0.22}s`} repeatCount="indefinite" />
        </rect>
      ))}
      <line x1="4" y1="42" x2="44" y2="42" stroke={ZN} strokeWidth="1" />
    </g>
  );
}

function TickerStream() {
  return (
    <g>
      <rect x="3" y="17" width="42" height="14" rx="4" fill="none" stroke={ZN} strokeWidth="1" />
      <clipPath id="dl-ticker">
        <rect x="5" y="18" width="38" height="12" rx="3" />
      </clipPath>
      <g clipPath="url(#dl-ticker)">
        <g>
          <animateTransform attributeName="transform" type="translate" from="0 0" to="-26 0" dur="1.6s" repeatCount="indefinite" />
          <text x="7" y="27" fontSize="8" fontWeight="700" fill={EM}>▲ 24,680</text>
          <text x="33" y="27" fontSize="8" fontWeight="700" fill={CR}>▼ 18,240</text>
        </g>
      </g>
    </g>
  );
}

function PortfolioRing() {
  return (
    <g transform="rotate(-90 24 24)" fill="none" strokeLinecap="round">
      <circle cx="24" cy="24" r="14" stroke={ZN} strokeWidth="5" opacity="0.5" />
      <circle cx="24" cy="24" r="14" stroke={EM} strokeWidth="5" strokeDasharray="88" strokeDashoffset="88">
        <animate attributeName="stroke-dashoffset" values="88;22" dur="1.7s" repeatCount="indefinite" />
      </circle>
      <circle cx="24" cy="24" r="14" stroke={AM} strokeWidth="5" strokeDasharray="88" strokeDashoffset="88" opacity="0.85">
        <animate attributeName="stroke-dashoffset" values="88;62" dur="1.7s" repeatCount="indefinite" />
      </circle>
      <circle cx="24" cy="24" r="14" stroke={CR} strokeWidth="5" strokeDasharray="88" strokeDashoffset="88" opacity="0.8">
        <animate attributeName="stroke-dashoffset" values="88;74" dur="1.7s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function OptionCurveSweep() {
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="38" x2="43" y2="38" stroke={ZN} strokeWidth="1" />
      <line x1="5" y1="38" x2="5" y2="7" stroke={ZN} strokeWidth="1" />
      <path d="M6 37 C15 37 18 12 24 12 C30 12 33 37 42 37" stroke={EM} strokeWidth="2.2" strokeDasharray="120" strokeDashoffset="120">
        <animate attributeName="stroke-dashoffset" values="120;0" dur="1.5s" repeatCount="indefinite" />
      </path>
      <circle cx="24" cy="12" r="2.6" fill={AM} stroke="none">
        <animate attributeName="opacity" values="0;1;1" dur="1.5s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function YieldPendulum() {
  return (
    <g>
      <line x1="24" y1="6" x2="24" y2="10" stroke={ZN} strokeWidth="2" />
      <g>
        <animateTransform attributeName="transform" type="rotate" values="-22 24 9;22 24 9;-22 24 9" dur="1.8s" repeatCount="indefinite" />
        <line x1="24" y1="9" x2="24" y2="33" stroke={MUT} strokeWidth="1.4" />
        <circle cx="24" cy="35" r="5" fill="none" stroke={AM} strokeWidth="2.4" />
        <circle cx="24" cy="35" r="1.8" fill={AM} />
      </g>
      <circle cx="24" cy="9" r="2" fill={EM} />
    </g>
  );
}

function BreakoutRocket() {
  return (
    <g>
      <line x1="4" y1="42" x2="44" y2="42" stroke={ZN} strokeWidth="1" />
      <g>
        <animateTransform attributeName="transform" type="translate" values="0 8;0 -6;0 8" dur="1.6s" repeatCount="indefinite" />
        <path d="M24 6 C30 13 31 22 24 31 C17 22 18 13 24 6 Z" fill="none" stroke={EM} strokeWidth="2.2" strokeLinejoin="round" />
        <circle cx="24" cy="17" r="2.6" fill={AM} />
        <path d="M20 30 L24 38 L28 30" fill={AM} opacity="0.85">
          <animate attributeName="opacity" values="0.25;0.95;0.25" dur="0.6s" repeatCount="indefinite" />
        </path>
      </g>
    </g>
  );
}

function QuantNeuralNodes() {
  const nodes = [
    { cx: 10, cy: 14 }, { cx: 10, cy: 34 }, { cx: 24, cy: 24 },
    { cx: 38, cy: 12 }, { cx: 38, cy: 36 }, { cx: 24, cy: 9 },
  ];
  const links: [number, number][] = [[0, 2], [1, 2], [2, 3], [2, 4], [0, 5], [5, 3], [1, 4]];
  return (
    <g>
      {links.map(([a, b], i) => (
        <line key={i} x1={nodes[a].cx} y1={nodes[a].cy} x2={nodes[b].cx} y2={nodes[b].cy}
              stroke={EM} strokeWidth="1" opacity="0.35">
          <animate attributeName="opacity" values="0.12;0.7;0.12" dur="1.9s" begin={`${i * 0.14}s`} repeatCount="indefinite" />
        </line>
      ))}
      {nodes.map((n, i) => (
        <circle key={i} cx={n.cx} cy={n.cy} r="3" fill={i % 2 ? AM : EM}>
          <animate attributeName="r" values="2.2;3.6;2.2" dur="1.5s" begin={`${i * 0.18}s`} repeatCount="indefinite" />
        </circle>
      ))}
    </g>
  );
}

function BalanceScale() {
  return (
    <g>
      <line x1="24" y1="10" x2="24" y2="40" stroke={ZN} strokeWidth="2" />
      <line x1="12" y1="40" x2="36" y2="40" stroke={ZN} strokeWidth="2" strokeLinecap="round" />
      <g>
        <animateTransform attributeName="transform" type="rotate" values="-9 24 14;9 24 14;-9 24 14" dur="2s" repeatCount="indefinite" />
        <line x1="8" y1="14" x2="40" y2="14" stroke={MUT} strokeWidth="2" strokeLinecap="round" />
        <path d="M8 14 L4 24 L12 24 Z" fill="none" stroke={CR} strokeWidth="1.8" />
        <path d="M40 14 L36 24 L44 24 Z" fill="none" stroke={EM} strokeWidth="1.8" />
      </g>
      <circle cx="24" cy="14" r="2" fill={AM} />
    </g>
  );
}

function VolumeEqualizer() {
  const bars = [10, 18, 26, 34, 42];
  return (
    <g>
      {bars.map((x, i) => (
        <rect key={i} x={x - 2.4} y="12" width="4.8" height="24" rx="2" fill={i % 2 ? AM : EM}>
          <animate attributeName="height" values={i % 2 ? "10;30;10" : "26;8;26"} dur="1.2s" begin={`${i * 0.1}s`} repeatCount="indefinite" />
          <animate attributeName="y" values={i % 2 ? "26;8;26" : "12;32;12"} dur="1.2s" begin={`${i * 0.1}s`} repeatCount="indefinite" />
        </rect>
      ))}
    </g>
  );
}

function MarketCompass() {
  return (
    <g>
      <circle cx="24" cy="24" r="17" fill="none" stroke={ZN} strokeWidth="1.4" />
      <circle cx="24" cy="24" r="2" fill={MUT} />
      <g>
        <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="2.4s" repeatCount="indefinite" />
        <path d="M24 9 L28 24 L24 39 L20 24 Z" fill="none" stroke={EM} strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M24 9 L28 24 L24 24 Z" fill={EM} />
        <path d="M24 39 L20 24 L24 24 Z" fill={CR} />
      </g>
      <text x="24" y="6" textAnchor="middle" fontSize="5" fill={MUT}>N</text>
    </g>
  );
}

const ANIMATIONS: (() => ReactNode)[] = [
  CandlestickSurge, BullBearPulse, CompoundingCoins, OrderbookWave, RadarScanner,
  WealthStaircase, TickerStream, PortfolioRing, OptionCurveSweep, YieldPendulum,
  BreakoutRocket, QuantNeuralNodes, BalanceScale, VolumeEqualizer, MarketCompass,
];

/* ------------------------------------------------------------- shuffle queue */

let queue: number[] = [];
let lastIndex = -1;

function nextAnimationIndex(): number {
  if (queue.length === 0) {
    queue = Array.from({ length: ANIMATIONS.length }, (_, i) => i);
    for (let i = queue.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [queue[i], queue[j]] = [queue[j], queue[i]];
    }
    // Never open a fresh shuffle with the animation that just played.
    if (queue[0] === lastIndex && queue.length > 1) {
      [queue[0], queue[1]] = [queue[1], queue[0]];
    }
  }
  lastIndex = queue.shift() as number;
  return lastIndex;
}

export default function DynamicLoader({
  size = 40,
  label,
  status,
  className = "",
}: {
  size?: number;
  label?: string;
  status?: string;
  className?: string;
}) {
  const [idx, setIdx] = useState(0);
  useEffect(() => setIdx(nextAnimationIndex()), []);

  const name = ANIMATION_NAMES[idx] || ANIMATION_NAMES[0];
  const Animation = ANIMATIONS[idx] || ANIMATIONS[0];

  return (
    <div className={`flex items-center gap-2.5 ${className}`} role="status" aria-live="polite" aria-label={`${name} loading`}>
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden>
        {Animation()}
      </svg>
      {(label || status) && (
        <div className="min-w-0">
          {label && <div className="text-[12.5px] font-semibold" style={{ color: "var(--ink)" }}>{label}</div>}
          {status && <div className="muted text-[11px] truncate">{status}</div>}
        </div>
      )}
    </div>
  );
}
