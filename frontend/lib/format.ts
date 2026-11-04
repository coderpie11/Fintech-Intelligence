export function inr(n: number | null | undefined, dec = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  // Indian digit grouping: 12,34,567.89
  const neg = n < 0 ? "-" : "";
  const [int, frac] = Math.abs(n).toFixed(dec).split(".");
  const c = int.length > 3;
  const tail = c ? int.slice(-3) : int;
  const head = c ? int.slice(0, -3) : "";
  const head2 = head.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${neg}₹${head2 ? head2 + "," : ""}${tail}${frac ? "." + frac : ""}`;
}

export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export function bigCrude(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return `₹${(n / 1e12).toFixed(2)} lakh crore`;
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)} crore`;
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(2)} lakh`;
  return inr(n);
}

export function pct(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function chgClass(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "text-neutral-400";
  return n > 0 ? "text-up" : n < 0 ? "text-down" : "text-neutral-400";
}

export function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return d;
  }
}
