"use client";

import { useEffect, useState } from "react";

type IstParts = { weekday: string; hour: number; minute: number; second: number; label: string };

function readIst(d: Date): IstParts {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
  const hour = parseInt(get("hour"), 10) || 0;
  const minute = parseInt(get("minute"), 10) || 0;
  const second = parseInt(get("second"), 10) || 0;
  return {
    weekday: get("weekday"),
    hour, minute, second,
    label: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
  };
}

function isLive(p: IstParts): boolean {
  const day = p.weekday;
  if (day === "Sat" || day === "Sun") return false;
  const mins = p.hour * 60 + p.minute;
  return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
}

/**
 * Real IST market-status badge. Green ONLY Monday–Friday 09:15–15:30 IST;
 * amber on weekends and after hours. Computed from Asia/Kolkata, not the
 * visitor's local clock.
 */
export default function MarketClock({
  showSeconds = false,
  compact = false,
}: {
  showSeconds?: boolean;
  compact?: boolean;
}) {
  const [now, setNow] = useState<IstParts | null>(null);

  useEffect(() => {
    const tick = () => setNow(readIst(new Date()));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  if (!now) {
    return (
      <span className="chip !text-[10px] !py-1.5" aria-label="Market status loading">
        <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-[var(--muted)] inline-block" />
        IST —
      </span>
    );
  }

  const live = isLive(now);
  const time = showSeconds
    ? `${now.label}:${String(now.second).padStart(2, "0")}`
    : now.label;

  return (
    <span
      className={`chip !py-1.5 ${live ? "chip-live" : "chip-warn"} ${compact ? "!text-[9.5px]" : "!text-[10px]"}`}
      title={`Asia/Kolkata ${time} · ${live ? "NSE/BSE capital market session open" : "outside the 09:15–15:30 IST session"}`}
    >
      <span
        className={`mr-1.5 h-1.5 w-1.5 rounded-full inline-block ${live ? "bg-[var(--up)] animate-pulseSoft" : "bg-[var(--warn)]"}`}
      />
      {live ? "MARKET LIVE" : "MARKET CLOSED"}
      <span className="mx-1.5 opacity-40">·</span>
      <span className="knum">{time} IST</span>
    </span>
  );
}
