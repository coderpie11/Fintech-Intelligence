"use client";

import { useEffect, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";

/**
 * Star toggle backed by the platform's real watchlist table (`WatchItem`).
 * The state is read from `/watchlist/check/{symbol}` on mount so a second
 * browser tab shows the same answer, not a local guess.
 */
export default function WatchlistButton({
  symbol,
  kind = "EQUITY",
  href,
  compact = false,
}: {
  symbol: string;
  kind?: "EQUITY" | "INDEX" | "ETF" | "FUND";
  href?: string;
  compact?: boolean;
}) {
  const [watched, setWatched] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const sym = encodeURIComponent(symbol.toUpperCase());
    getJSON<{ watched: boolean }>(`/watchlist/check/${sym}`)
      .then((r) => { if (live) setWatched(!!r.watched); })
      .catch(() => { if (live) setWatched(false); });
    return () => { live = false; };
  }, [symbol]);

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    const sym = symbol.toUpperCase();
    try {
      if (watched) {
        await postJSON(`/watchlist/${encodeURIComponent(sym)}`, undefined, "DELETE");
        setWatched(false);
      } else {
        await postJSON("/watchlist", { symbol: sym, kind, href });
        setWatched(true);
      }
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 90));
    }
    setBusy(false);
  };

  const on = watched === true;
  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        onClick={toggle}
        disabled={busy || watched === null}
        aria-pressed={on}
        title={on ? `Remove ${symbol} from the watchlist` : `Add ${symbol} to the watchlist`}
        className={on ? "btn-primary !py-2 !text-[12.5px]" : "btn-secondary !py-2 !text-[12.5px]"}
        style={on ? undefined : { borderColor: "color-mix(in srgb, var(--accent) 35%, var(--line))" }}
      >
        <span aria-hidden className="text-[14px] leading-none">{on ? "★" : "☆"}</span>
        {!compact && (busy ? "Saving…" : on ? "On Watchlist" : "Add to Watchlist")}
      </button>
      {err && <span className="text-[10px] text-[var(--warn)]">{err}</span>}
    </span>
  );
}
