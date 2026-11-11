"use client";

import { useId } from "react";

type Props = {
  points?: number[] | null;
  width?: number;
  height?: number;
  className?: string;
};

/**
 * One sparkline implementation for every list card.
 *
 * Safely normalises the series (a flat line never divides by zero), draws an
 * explicit-size SVG so it cannot collapse to an empty box, and follows the same
 * colour rule as the full chart: green when the window closes at or above where
 * it opened, red otherwise.
 */
export default function Sparkline({
  points,
  width = 140,
  height = 36,
  className = "",
}: Props) {
  const gid = useId().replace(/:/g, "");
  const clean = (points || []).filter(
    (p): p is number => typeof p === "number" && Number.isFinite(p),
  );

  if (clean.length < 2) {
    // A brand-new instrument still renders a visible, honest baseline instead
    // of an empty dark rectangle.
    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        className={`block max-w-full ${className}`}
        role="img"
        aria-label="Price sparkline unavailable"
      >
        <line
          x1={2}
          x2={width - 2}
          y1={height / 2}
          y2={height / 2}
          stroke="var(--muted)"
          strokeWidth="1"
          strokeDasharray="3 4"
          opacity="0.45"
        />
      </svg>
    );
  }

  const pad = 3;
  const lo = Math.min(...clean);
  const hi = Math.max(...clean);
  // Flat series: use a fixed positive span so the line sits on the midline.
  const span = hi - lo > 0 ? hi - lo : Math.max(Math.abs(hi) * 0.01, 1);
  const x = (i: number) =>
    pad + (i / (clean.length - 1)) * (width - pad * 2);
  const y = (v: number) =>
    pad + (1 - (v - lo) / span) * (height - pad * 2);
  const line = clean
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(v).toFixed(2)}`)
    .join(" ");
  const area = `${line} L${x(clean.length - 1).toFixed(2)},${height - pad} L${x(0).toFixed(2)},${height - pad} Z`;
  const up = clean[clean.length - 1] >= clean[0];
  const color = up ? "#10b981" : "#ef4444";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={`block max-w-full ${className}`}
      role="img"
      aria-label={up ? "Rising price sparkline" : "Falling price sparkline"}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${gid})`} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
