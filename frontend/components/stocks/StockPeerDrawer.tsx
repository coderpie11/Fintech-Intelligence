"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import Drawer from "@/components/Drawer";

type Peer = {
  symbol: string;
  name: string;
  sector?: string | null;
  last?: number | null;
  changepct?: number | null;
  market_cap?: number | null;
  pe?: number | null;
  pb?: number | null;
  roe?: number | null;
  debt_equity?: number | null;
  cagr_5y?: number | null;
  return_1y?: number | null;
  href?: string;
  badges?: string[];
  is_subject?: boolean;
};

const STORE = (symbol: string) => `bfi-peers:${symbol.toUpperCase()}`;

function loadStore(symbol: string): { custom: string[]; selected: string[] } {
  if (typeof window === "undefined") return { custom: [], selected: [] };
  try {
    const raw = window.sessionStorage.getItem(STORE(symbol));
    if (!raw) return { custom: [], selected: [] };
    const parsed = JSON.parse(raw);
    return {
      custom: Array.isArray(parsed.custom) ? parsed.custom : [],
      selected: Array.isArray(parsed.selected) ? parsed.selected : [],
    };
  } catch {
    return { custom: [], selected: [] };
  }
}

function saveStore(symbol: string, value: { custom: string[]; selected: string[] }) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORE(symbol), JSON.stringify(value));
  } catch {
    /* storage full or blocked — the drawer still works for this visit */
  }
}

export default function StockPeerDrawer({
  symbol,
  open,
  onClose,
  initialPeers,
}: {
  symbol: string;
  open: boolean;
  onClose: () => void;
  initialPeers?: Peer[];
}) {
  const [peers, setPeers] = useState<Peer[]>(initialPeers || []);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [custom, setCustom] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [addErr, setAddErr] = useState<string | null>(null);
  const [metric, setMetric] = useState<"pe" | "pb">("pe");
  const [multiple, setMultiple] = useState<string>("");
  const [rel, setRel] = useState<any>(null);
  const [relErr, setRelErr] = useState<string | null>(null);

  useEffect(() => {
    const store = loadStore(symbol);
    setCustom(store.custom);
    setSelected(store.selected.length ? store.selected : []);
  }, [symbol]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setErr(null);
    getJSON(`/stocks/${encodeURIComponent(symbol)}/peers`)
      .then((r) => setPeers(r.peers || []))
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [open, symbol]);

  useEffect(() => {
    if (initialPeers?.length) setPeers(initialPeers);
  }, [initialPeers]);

  useEffect(() => {
    saveStore(symbol, { custom, selected });
  }, [symbol, custom, selected]);

  const allPeers = useMemo(() => {
    const seen = new Set<string>();
    const out: Peer[] = [];
    for (const p of peers) {
      if (seen.has(p.symbol)) continue;
      seen.add(p.symbol);
      out.push(p);
    }
    return out;
  }, [peers]);

  const subject = allPeers.find((p) => p.symbol.toUpperCase() === symbol.toUpperCase());
  const chosen = allPeers.filter((p) => selected.includes(p.symbol));

  const toggle = (s: string) => {
    setSelected((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);
  };

  const addCustom = async () => {
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    setAddErr(null);
    if (allPeers.some((p) => p.symbol === sym)) {
      setInput("");
      return;
    }
    try {
      const d = await getJSON(`/stocks/${encodeURIComponent(sym)}`);
      const peer: Peer = {
        symbol: d.symbol,
        name: d.name,
        sector: d.sector,
        last: d.last?.value,
        changepct: d.changepct?.value,
        market_cap: d.market_cap?.value,
        pe: d.pe?.value,
        pb: d.pb?.value,
        roe: d.fundamentals?.profitability?.roe?.value,
        debt_equity: d.fundamentals?.solvency?.debt_equity?.value,
        cagr_5y: d.returns?.["5y"]?.value,
        return_1y: d.returns?.["1y"]?.value,
        href: `/stocks/${d.symbol}`,
      };
      setPeers((prev) => [...prev, peer]);
      setCustom((prev) => (prev.includes(sym) ? prev : [...prev, sym]));
      setSelected((prev) => (prev.includes(sym) ? prev : [...prev, sym]));
      setInput("");
    } catch (e: any) {
      setAddErr(String(e.message || e).slice(0, 120));
    }
  };

  const runRelative = async () => {
    setRelErr(null);
    setRel(null);
    try {
      const body: any = { metric };
      const n = parseFloat(multiple);
      if (Number.isFinite(n) && n > 0) body.peer_multiple = n;
      const r = await postJSON(`/stocks/${encodeURIComponent(symbol)}/relative-value`, body);
      setRel(r);
    } catch (e: any) {
      setRelErr(String(e.message || e).slice(0, 180));
    }
  };

  const medianMultiple = useMemo(() => {
    const vals = chosen
      .map((p) => (metric === "pe" ? p.pe : p.pb))
      .filter((v): v is number => typeof v === "number" && v > 0)
      .sort((a, b) => a - b);
    if (!vals.length) return null;
    const mid = Math.floor(vals.length / 2);
    return vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
  }, [chosen, metric]);

  return (
    <Drawer open={open} onClose={onClose} width={720}
            eyebrow={`Peer set · ${symbol}`}
            title="Compare with peers">
      <div className="space-y-4">
        <p className="muted text-[12px] leading-relaxed">
          Same-sector companies from the local store. Leader badges are computed
          across this peer set — highest ROE, lowest P/E, lowest D/E and highest
          5-year CAGR. Your selection is kept for this browser session.
        </p>

        {loading && !allPeers.length && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="skeleton h-10" />)}
          </div>
        )}
        {err && (
          <div className="card p-3 text-[12px]"
               style={{ borderColor: "color-mix(in srgb, var(--warn) 40%, var(--line))" }}>
            {err}
          </div>
        )}

        {allPeers.length > 0 && (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[660px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2">Compare</th>
                    <th className="table-head text-left px-3 py-2">Company</th>
                    <th className="table-head text-right px-2.5 py-2">P/E</th>
                    <th className="table-head text-right px-2.5 py-2">P/B</th>
                    <th className="table-head text-right px-2.5 py-2">ROE</th>
                    <th className="table-head text-right px-2.5 py-2">D/E</th>
                    <th className="table-head text-right px-3 py-2">5Y CAGR</th>
                  </tr>
                </thead>
                <tbody>
                  {allPeers.map((p) => {
                    const up = (p.changepct || 0) >= 0;
                    return (
                      <tr key={p.symbol} className="table-row"
                          style={p.is_subject
                            ? { background: "color-mix(in srgb, var(--accent) 7%, transparent)" }
                            : undefined}>
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={selected.includes(p.symbol)}
                                 onChange={() => toggle(p.symbol)}
                                 aria-label={`Include ${p.symbol} in comparison`} />
                        </td>
                        <td className="px-3 py-2 min-w-[180px]">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Link href={p.href || `/stocks/${p.symbol}`}
                                  className="text-[12.5px] font-bold hover:underline">
                              {p.symbol}
                            </Link>
                            {p.is_subject && <span className="chip !text-[8.5px] !py-0.5">This stock</span>}
                            {custom.includes(p.symbol) && (
                              <span className="chip chip-warn !text-[8.5px] !py-0.5">Custom</span>
                            )}
                          </div>
                          <div className="muted text-[10px] truncate max-w-[210px]">{p.name}</div>
                          {(p.badges || []).map((b) => (
                            <span key={b} className="chip chip-live !text-[8px] !py-0.5 mt-1 mr-1">
                              {b}
                            </span>
                          ))}
                        </td>
                        <td className="px-2.5 py-2 text-right knum text-[12px]">{p.pe ?? "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[12px]">{p.pb ?? "—"}</td>
                        <td className="px-2.5 py-2 text-right knum text-[12px]">
                          {p.roe != null ? `${p.roe.toFixed(2)}%` : "—"}
                        </td>
                        <td className="px-2.5 py-2 text-right knum text-[12px]">
                          {p.debt_equity != null ? p.debt_equity.toFixed(2) : "—"}
                        </td>
                        <td className={`px-3 py-2 text-right knum text-[12px] font-semibold ${(p.cagr_5y || 0) >= 0 ? "text-up" : "text-down"}`}>
                          {p.cagr_5y != null ? pct(p.cagr_5y) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="grid sm:grid-cols-[1fr_auto] gap-2 items-end">
          <label className="block">
            <span className="muted text-[10.5px] font-bold uppercase tracking-[0.13em]">
              Add a stock by NSE symbol
            </span>
            <input value={input} onChange={(e) => setInput(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") addCustom(); }}
                   placeholder="e.g. INFY"
                   className="surface rounded-lg w-full mt-1 px-3 py-2 text-[12.5px] knum"
                   style={{ color: "var(--ink)" }} />
          </label>
          <button onClick={addCustom} className="btn-secondary !py-2 !text-[12px]">Add stock</button>
        </div>
        {addErr && <div className="text-[11.5px] text-down">{addErr}</div>}

        <div className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div>
              <div className="text-[13px] font-bold">Relative price at a peer multiple</div>
              <p className="muted text-[11px] mt-0.5">
                Implied price = the chosen peer multiple × this company's per-share
                earnings or book value.
              </p>
            </div>
            <span className="chip !text-[9px]">{chosen.length} selected</span>
          </div>

          <div className="grid sm:grid-cols-3 gap-2 items-end">
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Multiple</span>
              <select value={metric} onChange={(e) => setMetric(e.target.value as "pe" | "pb")}
                      className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px]"
                      style={{ color: "var(--ink)" }}>
                <option value="pe">P/E</option>
                <option value="pb">P/B</option>
              </select>
            </label>
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">
                Peer multiple {medianMultiple != null ? `(median ${medianMultiple.toFixed(2)})` : ""}
              </span>
              <input value={multiple} onChange={(e) => setMultiple(e.target.value)}
                     placeholder={medianMultiple != null ? medianMultiple.toFixed(2) : "peer median"}
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <button onClick={runRelative} className="btn-primary !py-2 !text-[12px]">Calculate</button>
          </div>

          {relErr && <div className="text-[11.5px] text-down mt-2">{relErr}</div>}
          {rel && (
            <div className="grid grid-cols-3 gap-2 mt-3">
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Current</div>
                <div className="knum text-[14px] font-bold mt-0.5">{inr(rel.current_price)}</div>
              </div>
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Implied</div>
                <div className="knum text-[14px] font-black accent mt-0.5">{inr(rel.implied_price)}</div>
              </div>
              <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">Upside</div>
                <div className={`knum text-[14px] font-black mt-0.5 ${rel.upside_pct >= 0 ? "text-up" : "text-down"}`}>
                  {pct(rel.upside_pct)}
                </div>
              </div>
            </div>
          )}
          {rel?.note && <p className="muted text-[10.5px] mt-2 leading-relaxed">{rel.note}</p>}
        </div>

        {subject && (
          <div className="muted text-[10.5px] leading-relaxed">
            This stock: P/E {subject.pe ?? "—"} · P/B {subject.pb ?? "—"} ·
            ROE {subject.roe != null ? `${subject.roe.toFixed(2)}%` : "—"} ·
            5Y CAGR {subject.cagr_5y != null ? pct(subject.cagr_5y) : "—"}.
            Peer metrics are platform-computed from reported statements.
          </div>
        )}
      </div>
    </Drawer>
  );
}
