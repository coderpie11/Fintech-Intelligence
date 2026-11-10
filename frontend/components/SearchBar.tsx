"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { pct } from "@/lib/format";

type Hit = {
  kind: string;
  label: string;
  sublabel: string;
  href: string;
  symbol?: string;
  name?: string;
  sector?: string | null;
  exchange?: string;
  changepct?: number | null;
  price?: number | null;
  nav?: number | null;
  unit?: string | null;
};

const KIND_ICON: Record<string, string> = {
  INDEX: "Σ", EQUITY: "◆", ETF: "▤", FUND: "◉", REIT: "▮", INVIT: "▮",
  COMMODITY: "✦", IPO: "↑", ACADEMY: "◇",
};

const KIND_TAG: Record<string, string> = {
  INDEX: "Index", EQUITY: "Stock", ETF: "ETF", FUND: "Fund",
  REIT: "REIT", INVIT: "InvIT", COMMODITY: "Commodity",
  IPO: "IPO", ACADEMY: "Academy",
};

const TABS: { key: string; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "EQUITY", label: "Stocks" },
  { key: "FUND", label: "Mutual Funds" },
  { key: "ETF", label: "ETFs" },
  { key: "INDEX", label: "Indices" },
  { key: "IPO", label: "IPOs" },
  { key: "ACADEMY", label: "Academy" },
];

/* --------------------------------------------------------- instant index ---- */
// The whole searchable universe is fetched once per browser session and kept
// in module memory. Every keystroke filters that array synchronously (<5 ms),
// so the dropdown never waits on the network after the first load.

type PreloadHit = Hit & { aliases?: string };

let PRELOAD: PreloadHit[] | null = null;
let PRELOAD_PROMISE: Promise<PreloadHit[]> | null = null;

function loadPreload(): Promise<PreloadHit[]> {
  if (PRELOAD) return Promise.resolve(PRELOAD);
  if (!PRELOAD_PROMISE) {
    PRELOAD_PROMISE = getJSON<{ items: PreloadHit[] }>("/search/preload")
      .then((r) => {
        PRELOAD = (r.items || []).map((x) => ({
          ...x,
          kind: String(x.kind || "EQUITY").toUpperCase(),
        }));
        return PRELOAD;
      })
      .catch(() => {
        PRELOAD_PROMISE = null;
        return [] as PreloadHit[];
      });
  }
  return PRELOAD_PROMISE;
}

// Phonetic / common-misspelling aliases. The mapped term is searched in
// addition to the raw query, so "nestec" and "nasdak" both find Nasdaq.
const PHONETIC: Record<string, string> = {
  nestec: "nasdaq",
  nasdak: "nasdaq",
  nasdack: "nasdaq",
  nasdaq: "nasdaq",
  niftee: "nifty",
  sentex: "sensex",
  sensix: "sensex",
};

function normText(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
}

function queryVariants(q: string): string[] {
  const key = q.toLowerCase().trim();
  const out = [key];
  if (PHONETIC[key]) out.push(PHONETIC[key]);
  if (key.length >= 3) {
    for (const [k, v] of Object.entries(PHONETIC)) {
      if (k.startsWith(key) || key.startsWith(k)) out.push(v);
    }
  }
  return Array.from(new Set(out));
}

function scorePreload(h: PreloadHit, terms: string[]): number {
  const sym = (h.symbol || "").toLowerCase();
  const name = normText(h.name || h.label || "");
  const alias = normText(h.aliases || "");
  const sector = normText(h.sector || "");
  let best = 0;
  for (const t of terms) {
    let s = 0;
    if (sym === t) s = 120;
    else if (sym.startsWith(t)) s = 100;
    else if (name.startsWith(t)) s = 90;
    else if (name.split(" ").some((w) => w.startsWith(t))) s = 75;
    else if (name.includes(t)) s = 60;
    else if (alias.includes(t)) s = 55;
    else if (sector.includes(t)) s = 30;
    if (s > best) best = s;
  }
  return best;
}

function filterPreload(q: string): Hit[] {
  if (!PRELOAD) return [];
  const terms = queryVariants(q);
  const scored: { h: PreloadHit; s: number }[] = [];
  for (const h of PRELOAD) {
    const s = scorePreload(h, terms);
    if (s > 0) scored.push({ h, s });
  }
  scored.sort((a, b) => b.s - a.s || (a.h.label || "").localeCompare(b.h.label || ""));
  return scored.slice(0, 40).map((x) => x.h);
}

function SearchIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function rupee(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/**
 * Instant market search: one input, categorised tabs, live price/NAV and
 * keyboard navigation. A module-level preloaded index makes the first
 * keystroke instant. The navbar keeps a compact trigger; Ctrl/Cmd+K opens the
 * same panel anywhere.
 */
export default function SearchBar({ compact }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const [tab, setTab] = useState("ALL");
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => input.current?.focus(), 40);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.clearTimeout(id);
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Prime the in-memory index as soon as the navbar mounts. The fetch happens
  // once; every later keystroke is a synchronous array scan.
  useEffect(() => {
    loadPreload();
  }, []);

  useEffect(() => {
    const text = q.trim();
    if (!text) {
      setHits([]);
      setBusy(false);
      return;
    }
    if (PRELOAD) {
      setHits(filterPreload(text));
      setBusy(false);
      return;
    }
    let alive = true;
    setBusy(true);
    loadPreload().then((items) => {
      if (!alive) return;
      if (items.length) {
        setHits(filterPreload(text));
        setBusy(false);
        return;
      }
      // Index unavailable — fall back to the server endpoint.
      getJSON<{ results: Hit[] }>(`/search?q=${encodeURIComponent(text)}&limit=20`)
        .then((r) => { if (alive) setHits(r.results || []); })
        .catch(() => { if (alive) setHits([]); })
        .finally(() => { if (alive) setBusy(false); });
    });
    return () => { alive = false; };
  }, [q]);

  useEffect(() => { setActive(0); }, [tab, q]);

  const counts = useMemo(() => {
    const m: Record<string, number> = { ALL: hits.length };
    hits.forEach((h) => { m[h.kind] = (m[h.kind] || 0) + 1; });
    return m;
  }, [hits]);

  const filtered = useMemo(
    () => (tab === "ALL" ? hits : hits.filter((h) => h.kind === tab)),
    [hits, tab],
  );

  const go = (href: string) => {
    setOpen(false);
    setQ("");
    setHits([]);
    setTab("ALL");
    router.push(href);
    window.dispatchEvent(new CustomEvent("bfi:navigated"));
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Tab") {
      const i = TABS.findIndex((t) => t.key === tab);
      const next = TABS[(i + (e.shiftKey ? TABS.length - 1 : 1)) % TABS.length];
      e.preventDefault();
      setTab(next.key);
    }
    if (e.key === "Enter") {
      const hit = filtered[active] || filtered[0];
      if (hit) go(hit.href);
      else if (q.trim().length >= 1) {
        const term = encodeURIComponent(q.trim());
        go(tab === "FUND" ? `/mutual-funds?q=${term}`
           : tab === "ACADEMY" ? `/learn?q=${term}`
           : `/stocks?q=${term}`);
      }
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Open global search (Ctrl K)"
        className={`btn-secondary !rounded-lg !py-2 ${compact ? "!px-2.5" : "!px-3"}`}
      >
        <SearchIcon />
        {!compact && (
          <>
            <span className="muted hidden xl:inline text-[12.5px] font-medium">Search markets…</span>
            <kbd className="hidden xl:inline knum text-[10px] rounded px-1.5 py-0.5 ml-1"
                 style={{ border: "1px solid var(--line)", color: "var(--muted)" }}>
              Ctrl K
            </kbd>
          </>
        )}
      </button>

      {open && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-[150]">
          <div
            className="absolute inset-0"
            style={{ background: "rgba(2,6,23,0.72)", backdropFilter: "blur(6px)" }}
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="relative mx-auto mt-[5vh] sm:mt-[8vh] w-[calc(100vw-0.75rem)] sm:w-[min(760px,94vw)]">
            <div className="card overflow-hidden shadow-2xl" style={{ background: "var(--surface)" }}>
              <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-3.5" style={{ borderBottom: "1px solid var(--line)" }}>
                <span className="accent shrink-0"><SearchIcon size={18} /></span>
                <input
                  ref={input}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={onKey}
                  placeholder="Search 2,400+ stocks, 38,000+ funds, ETFs, indices, IPOs…"
                  className="w-full min-w-0 bg-transparent text-[16px] sm:text-[15px] outline-none"
                  style={{ color: "var(--ink)" }}
                  aria-label="Global search"
                />
                {busy && <span className="knum muted text-[11px]">…</span>}
                <button onClick={() => setOpen(false)}
                        className="chip !text-[9.5px] shrink-0 hover:!text-[var(--ink)]">ESC</button>
              </div>

              {/* category tabs */}
              <div className="flex items-center gap-1 px-3 py-2 overflow-x-auto scrollbar-none"
                   style={{ borderBottom: "1px solid var(--line)", background: "var(--surface-2)" }}>
                {TABS.map((t) => {
                  const n = counts[t.key] || 0;
                  const on = tab === t.key;
                  return (
                    <button key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold inline-flex items-center gap-1 ${
                              on ? "" : "muted hover:text-[var(--ink)]"
                            }`}
                            style={on ? {
                              background: "color-mix(in srgb, var(--accent) 14%, transparent)",
                              color: "var(--accent)",
                              border: "1px solid color-mix(in srgb, var(--accent) 35%, var(--line))",
                            } : { border: "1px solid transparent" }}>
                      {t.label}
                      {n > 0 && (
                        <span className="knum text-[9px] rounded-full px-1"
                              style={{ background: on ? "color-mix(in srgb, var(--accent) 22%, transparent)" : "var(--surface)" }}>
                          {n}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="max-h-[56vh] overflow-y-auto">
                {q.trim().length < 1 ? (
                  <div className="p-4">
                    <div className="muted text-[10.5px] font-bold uppercase tracking-[0.16em] mb-2.5">
                      Jump to a desk
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                      {NAV_ITEMS.map((item) => (
                        <Link
                          key={item.key}
                          href={item.href}
                          onClick={() => setOpen(false)}
                          className="rounded-lg px-3 py-2.5 text-[12.5px] font-medium card-hover"
                          style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
                        >
                          {item.label}
                        </Link>
                      ))}
                    </div>
                    <p className="muted text-[11.5px] mt-4">
                      Try <b style={{ color: "var(--ink)" }}>Paras Defence</b>,{" "}
                      <b style={{ color: "var(--ink)" }}>Orient</b>,{" "}
                      <b style={{ color: "var(--ink)" }}>Nestec</b> or{" "}
                      <b style={{ color: "var(--ink)" }}>Nasdaq</b> — fuzzy matching
                      covers the full NSE and AMFI lists.
                    </p>
                  </div>
                ) : filtered.length === 0 && !busy ? (
                  <div className="p-6 text-center">
                    <div className="text-[13px] font-semibold">
                      No {tab === "ALL" ? "" : `${TABS.find((t) => t.key === tab)?.label} `}match for “{q}”
                    </div>
                    <p className="muted text-[12px] mt-1">
                      Try a ticker (RELIANCE), a company name (Paras Defence) or a
                      scheme name (Nasdaq 100).
                    </p>
                    {tab !== "ALL" && (
                      <button onClick={() => setTab("ALL")} className="btn-secondary mt-3 !px-3 !py-1.5 !text-[11.5px]">
                        Search all categories
                      </button>
                    )}
                  </div>
                ) : (
                  filtered.map((hit, i) => {
                    const price = hit.kind === "FUND" ? (hit.nav ?? hit.price) : hit.price;
                    return (
                      <button
                        key={hit.kind + hit.href + i}
                        onClick={() => go(hit.href)}
                        onMouseEnter={() => setActive(i)}
                        className="w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors"
                        style={{
                          borderTop: i === 0 ? "none" : "1px solid var(--line-soft)",
                          background: i === active ? "var(--hover)" : "transparent",
                        }}
                      >
                        <span className="knum accent text-[15px] w-6 text-center shrink-0">
                          {KIND_ICON[hit.kind] || "•"}
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block text-[13.5px] font-semibold truncate">
                            {hit.label}
                            {hit.symbol && hit.symbol !== hit.label && (
                              <span className="muted text-[10.5px] font-normal ml-1.5">{hit.symbol}</span>
                            )}
                          </span>
                          <span className="block muted text-[11.5px] truncate">{hit.sublabel}</span>
                        </span>
                        <span className="text-right shrink-0">
                          {price != null && (
                            <span className="block knum text-[12px] font-bold" style={{ color: "var(--ink)" }}>
                              {hit.kind === "FUND" ? price.toFixed(2) : rupee(price)}
                            </span>
                          )}
                          {hit.changepct != null && (
                            <span className={`block knum text-[10.5px] font-semibold ${hit.changepct >= 0 ? "text-up" : "text-down"}`}>
                              {pct(hit.changepct)}
                            </span>
                          )}
                        </span>
                        <span className="chip !text-[9px] shrink-0">{KIND_TAG[hit.kind] || hit.kind}</span>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="px-3 sm:px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 muted text-[10.5px]"
                   style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <span><kbd className="knum">↑↓</kbd> navigate</span>
                <span><kbd className="knum">tab</kbd> category</span>
                <span><kbd className="knum">↵</kbd> open</span>
                <span><kbd className="knum">esc</kbd> close</span>
                <span className="ml-auto hidden sm:inline">Ctrl K anywhere</span>
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
