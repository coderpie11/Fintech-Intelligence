"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import Drawer from "@/components/Drawer";

type Peer = {
  code: string;
  name: string;
  amc?: string;
  category?: string;
  plan?: string;
  option?: string;
  ter?: number | null;
  aum_crore?: number | null;
  perf_1y?: number | null;
  perf_3y?: number | null;
  perf_5y?: number | null;
  href?: string;
};

export default function FundPeerDrawer({
  code, open, onClose,
}: {
  code: string;
  open: boolean;
  onClose: () => void;
}) {
  const [peers, setPeers] = useState<Peer[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [amount, setAmount] = useState("1000000");
  const [years, setYears] = useState("5");
  const [result, setResult] = useState<any>(null);
  const [calcErr, setCalcErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setErr(null);
    getJSON(`/mutual-funds/${encodeURIComponent(code)}/peers?limit=12`)
      .then((r) => {
        const list: Peer[] = r.peers || [];
        setPeers(list);
        setSelected((prev) => prev || list[0]?.code || "");
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [open, code]);

  const run = async () => {
    if (!selected) return;
    setBusy(true);
    setCalcErr(null);
    setResult(null);
    try {
      const r = await postJSON(`/mutual-funds/${encodeURIComponent(code)}/fee-drag`, {
        amount: Number(amount) || 0,
        years: Number(years) || 1,
        peer_code: selected,
      });
      setResult(r);
    } catch (e: any) {
      setCalcErr(String(e.message || e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  const chosen = peers.find((p) => p.code === selected);

  return (
    <Drawer open={open} onClose={onClose} width={760}
            eyebrow={`Fund peer set · ${code}`}
            title="Compare with peers">
      <div className="space-y-4">
        <p className="muted text-[12px] leading-relaxed">
          Same-category Direct-Growth schemes with a live NAV series. Pick a peer to
          compare the actual wealth outcome, the annual fee drag and the alpha
          contribution over your horizon.
        </p>

        {loading && (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-10" />)}
          </div>
        )}
        {err && (
          <div className="card p-3 text-[12px]"
               style={{ borderColor: "color-mix(in srgb, var(--warn) 40%, var(--line))" }}>
            {err}
          </div>
        )}

        {peers.length > 0 && (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2">Compare</th>
                    <th className="table-head text-left px-3 py-2">Scheme</th>
                    <th className="table-head text-right px-2.5 py-2">TER</th>
                    <th className="table-head text-right px-2.5 py-2">3Y</th>
                    <th className="table-head text-right px-2.5 py-2">5Y</th>
                    <th className="table-head text-right px-3 py-2">AUM</th>
                  </tr>
                </thead>
                <tbody>
                  {peers.map((p) => (
                    <tr key={p.code} className="table-row"
                        style={p.code === selected
                          ? { background: "color-mix(in srgb, var(--accent) 7%, transparent)" }
                          : undefined}>
                      <td className="px-3 py-2">
                        <input type="radio" name="fund-peer" checked={p.code === selected}
                               onChange={() => setSelected(p.code)}
                               aria-label={`Select ${p.name}`} />
                      </td>
                      <td className="px-3 py-2 min-w-[230px]">
                        <Link href={p.href || `/mutual-funds/${p.code}`}
                              className="text-[12px] font-bold hover:underline">
                          {p.name.length > 58 ? p.name.slice(0, 58) + "…" : p.name}
                        </Link>
                        <div className="muted text-[10px] truncate max-w-[260px]">
                          {p.amc} · {p.category}
                        </div>
                      </td>
                      <td className="px-2.5 py-2 text-right knum text-[11.5px]">
                        {p.ter != null ? `${p.ter.toFixed(2)}%` : "—"}
                      </td>
                      <td className={`px-2.5 py-2 text-right knum text-[11.5px] ${(p.perf_3y || 0) >= 0 ? "text-up" : "text-down"}`}>
                        {p.perf_3y != null ? pct(p.perf_3y) : "—"}
                      </td>
                      <td className={`px-2.5 py-2 text-right knum text-[11.5px] ${(p.perf_5y || 0) >= 0 ? "text-up" : "text-down"}`}>
                        {p.perf_5y != null ? pct(p.perf_5y) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right knum text-[11.5px]">
                        {p.aum_crore != null ? `₹${p.aum_crore.toLocaleString("en-IN")} Cr` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="card p-4">
          <div className="text-[13px] font-bold">Fee drag &amp; alpha wealth calculator</div>
          <p className="muted text-[11px] mt-0.5 leading-relaxed">
            Compounds each scheme's actual 3Y CAGR (or 5Y when 3Y is unavailable)
            on the same starting amount. Fee drag is the annual rupee difference at
            the two disclosed TERs.
          </p>
          <div className="grid sm:grid-cols-3 gap-2 items-end mt-3">
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Amount ₹</span>
              <input value={amount} onChange={(e) => setAmount(e.target.value)}
                     inputMode="numeric"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Years</span>
              <input value={years} onChange={(e) => setYears(e.target.value)}
                     inputMode="decimal"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <button onClick={run} disabled={busy || !selected}
                    className="btn-primary w-full justify-center !py-2 !text-[12px]">
              {busy ? "Calculating…" : "Compare wealth"}
            </button>
          </div>

          {chosen && (
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              <span className="chip !text-[9px]">Peer: {chosen.name.slice(0, 40)}</span>
              <span className="chip !text-[9px]">Peer TER {chosen.ter != null ? `${chosen.ter.toFixed(2)}%` : "—"}</span>
              <span className="chip !text-[9px]">Peer 3Y {chosen.perf_3y != null ? pct(chosen.perf_3y) : "—"}</span>
            </div>
          )}
          {calcErr && <p className="text-[11.5px] text-down font-semibold mt-2">{calcErr}</p>}

          {result && (
            <div className="mt-3 space-y-2">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  ["This fund", result.fund_value, result.fund?.cagr_pct, result.fund?.ter],
                  ["Peer", result.peer_value, result.peer?.cagr_pct, result.peer?.ter],
                  ["Alpha wealth", result.alpha_wealth, null, null],
                  ["Fee drag / year", result.fee_drag_per_year, null, null],
                ].map(([label, value, cagr, ter]: any) => (
                  <div key={label} className="rounded-md px-2.5 py-2"
                       style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                    <div className={`knum text-[14px] font-black mt-0.5 ${label === "Alpha wealth" && Number(value) < 0 ? "text-down" : ""}`}>
                      {inr(value)}
                    </div>
                    {(cagr != null || ter != null) && (
                      <div className="muted text-[9.5px] mt-0.5">
                        {cagr != null ? `CAGR ${pct(cagr)}` : ""}
                        {cagr != null && ter != null ? " · " : ""}
                        {ter != null ? `TER ${Number(ter).toFixed(2)}%` : ""}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <p className="muted text-[10.5px] leading-relaxed">{result.note}</p>
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
}
