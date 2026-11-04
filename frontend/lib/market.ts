/** NSE cash-market session helper (IST). */
export function istParts(now: Date = new Date()) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(fmt.formatToParts(now).map((p) => [p.type, p.value]));
  const minutes = Number(parts.hour) * 60 + Number(parts.minute);
  const weekday = String(parts.weekday || "");
  const tradingDay = !["Sat", "Sun"].includes(weekday);
  return { minutes, weekday, tradingDay };
}

/** 09:15–15:30 IST, Monday–Friday. */
export function isMarketOpenIST(now: Date = new Date()): boolean {
  const { minutes, tradingDay } = istParts(now);
  return tradingDay && minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 30;
}

/** Short label used in the live/scrub header. */
export function istClock(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(now) + " IST";
}
