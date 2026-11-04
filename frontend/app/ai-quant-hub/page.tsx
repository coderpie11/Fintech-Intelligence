"use client";

import { useEffect, useState } from "react";
import { getJSON } from "@/lib/api";
import { ErrLine, Loading, Note, Panel, Pill, num } from "@/components/quant/Kit";
import RangeCast from "@/components/quant/RangeCast";
import StreetPulse from "@/components/quant/StreetPulse";
import XRay from "@/components/quant/XRay";
import AskDalal from "@/components/quant/AskDalal";
import MetricTip from "@/components/MetricTip";

type Workspace = { id: string; name: string; fact: string };
type Provider = {
  provider: string;
  tier: number;
  label: string;
  note: string;
  configured: boolean;
  models: string[];
  circuit_open: boolean;
  probe_ok?: boolean;
  probe_model?: string;
  probe_ms?: number;
  probe_error?: string | null;
};
type Health = {
  platform: string;
  workspaces: Workspace[];
  llm: { providers: Provider[]; tiers: number; active_tier: number | null; order: string[] };
  sentiment: { engine: string; state: string; error?: string | null; note?: string };
  rag: { engine: string; state: string; dim?: number; error?: string | null };
  data_note: string;
  disclaimer: string;
};

const TABS = [
  { key: "rangecast", name: "RangeCast AI", short: "7/14-day 80% bands", fact: "Probabilistic price envelope from realised volatility, clipped at live F&O open-interest walls." },
  { key: "streetpulse", name: "StreetPulse Matrix", short: "Flows vs delivery", fact: "Official FII/DII rupee flows read against exchange delivery and public-headline tone." },
  { key: "xray", name: "4 PM Market X-Ray", short: "Money-flow chain", fact: "Four-step institutional money-flow synthesis plus volume shockers, each step labelled with what it can prove." },
  { key: "ask-dalal", name: "Ask Dalal AI", short: "Guarded data Q&A", fact: "Read-only text-to-SQL screener, grounded document answers, say-vs-do ledger and filing diffs." },
];

export default function AiQuantHubPage() {
  const [active, setActive] = useState("rangecast");
  const [health, setHealth] = useState<Health | null>(null);
  const [hErr, setHErr] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  const load = (probe = false) => {
    setHErr(null);
    if (probe) setProbing(true);
    getJSON<Health>(`/quant-hub/health${probe ? "?probe=true" : ""}`)
      .then(setHealth)
      .catch((e) => setHErr(String(e.message || e).slice(0, 200)))
      .finally(() => setProbing(false));
  };

  useEffect(() => { load(false); }, []);

  const llm = health?.llm;
  const activeTier = llm?.providers?.find((p) => p.tier === llm.active_tier) || null;

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      {/* Static, always-visible, non-advisory header. Deliberately not collapsible:
          on an AI page the disclaimer must travel with every tab. */}
      <div
        className="mt-6 rounded-xl px-4 py-3"
        style={{
          border: "1px solid color-mix(in srgb, var(--warn) 45%, var(--line))",
          background: "color-mix(in srgb, var(--warn) 7%, transparent)",
        }}
        role="note"
        aria-label="Non-advisory disclosure"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-black uppercase tracking-[0.16em]" style={{ color: "var(--warn)" }}>
            Factual &amp; statistical output only
          </span>
          <span className="muted text-[11px]">· not investment advice · no buy or sell recommendations</span>
        </div>
        <p className="text-[12px] leading-relaxed mt-1.5" style={{ color: "var(--ink)" }}>
          Every band, score, flow reading and generated sentence on this page is a
          mathematical, historical or source-quoted output computed from public
          Indian-market data. Model outputs can be wrong and are always shown with
          the provider, the SQL or the source passages that produced them. We do not
          know your portfolio, goals or risk appetite. Consult a SEBI-registered
          investment adviser before acting on anything.
        </p>
      </div>

      {/* Brand header */}
      <div className="flex flex-wrap items-end justify-between gap-4 pt-7 pb-4">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[0.18em] accent mb-3"
               style={{ border: "1px solid color-mix(in srgb, var(--accent) 32%, var(--line))",
                        background: "color-mix(in srgb, var(--accent) 9%, transparent)" }}>
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] inline-block" />
            AI Quant Hub
          </div>
          <h1 className="text-[26px] sm:text-[32px] font-black tracking-tight leading-tight">
            Four workspaces, one evidence trail
          </h1>
          <p className="muted text-[13px] mt-2 leading-relaxed">
            Each workspace answers a different question with a different method — and
            prints its method, its inputs and its limits next to the answer. Where a
            free source cannot supply a number, the workspace says so instead of
            filling the gap.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone="accent">{health?.platform || "Bharat Fintech Intelligence"}</Pill>
          {activeTier && <Pill tone="up">Tier {activeTier.tier} · {activeTier.label}</Pill>}
        </div>
      </div>

      {/* Workspace tabs */}
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2 mb-3" role="tablist" aria-label="AI Quant Hub workspaces">
        {TABS.map((t) => {
          const on = active === t.key;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={on}
              onClick={() => setActive(t.key)}
              className="card card-hover p-3 text-left transition-colors"
              style={on ? {
                borderColor: "color-mix(in srgb, var(--accent) 55%, var(--line))",
                background: "color-mix(in srgb, var(--accent) 7%, var(--surface))",
              } : undefined}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold tracking-tight">{t.name}</span>
                <span className="h-1.5 w-1.5 rounded-full shrink-0"
                      style={{ background: on ? "var(--accent)" : "var(--line)" }} />
              </div>
              <div className="muted text-[10.5px] font-bold uppercase tracking-[0.1em] mt-0.5">{t.short}</div>
              <div className="muted text-[11px] leading-snug mt-1.5">{t.fact}</div>
            </button>
          );
        })}
      </div>

      {/* Transparency strip */}
      <Panel
        title="Transparency strip — what is actually running"
        sub="Provider configuration, live probe, the local sentiment model and the retrieval index. Nothing on this page hides which engine produced an answer."
        right={
          <button onClick={() => load(true)} disabled={probing} className="btn-secondary !py-1.5 !px-3 !text-[11.5px]">
            {probing ? "Probing providers…" : "Probe all providers"}
          </button>
        }
      >
        {hErr && <ErrLine message={`Health endpoint failed: ${hErr}`} onRetry={() => load(false)} />}
        {!health && !hErr && <Loading label="Reading provider and index status…" />}
        {health && (
          <div className="space-y-3">
            <div className="grid sm:grid-cols-3 gap-2.5">
              {(llm?.providers || []).map((p) => {
                const state = !p.configured
                  ? "not configured"
                  : p.circuit_open
                  ? "circuit open"
                  : p.probe_ok === undefined
                  ? "ready"
                  : p.probe_ok
                  ? "live"
                  : "probe failed";
                const tone: "up" | "down" | "warn" | "neutral" | "accent" =
                  state === "live" ? "up" : state === "probe failed" || state === "circuit open" ? "down" : state === "ready" ? "accent" : "warn";
                return (
                  <div key={p.provider} className="rounded-lg px-3 py-2.5"
                       style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12.5px] font-bold">{p.label}</span>
                      <Pill tone={tone}>{state}</Pill>
                    </div>
                    <div className="muted text-[10px] mt-0.5">
                      <MetricTip label="Failover tier" tip={{
                        meaning: "Providers are tried in this order. Tier 0 runs first; if it is missing, rate-limited or circuit-broken, the next configured tier answers the same request.",
                      }}>tier {p.tier}</MetricTip>
                      {" · "}{p.models.length} models · {p.note}
                    </div>
                    <div className="knum text-[10.5px] mt-1.5 truncate" title={p.probe_model || p.models[0]}>
                      {p.probe_model || p.models[0]}
                    </div>
                    {p.probe_ms != null && <div className="muted text-[10px] knum">probe {p.probe_ms} ms</div>}
                    {p.probe_ok === false && p.probe_error && (
                      <div className="text-[10px] leading-snug mt-1" style={{ color: "var(--warn)" }}>
                        {p.probe_error}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="grid sm:grid-cols-2 gap-2.5">
              <div className="rounded-lg px-3 py-2.5"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Sentiment engine</div>
                <div className="text-[12.5px] font-bold mt-0.5">{health.sentiment?.engine || "—"}</div>
                <div className="muted text-[10.5px] mt-0.5">
                  {health.sentiment?.state || "idle"}
                  {health.sentiment?.note ? ` · ${health.sentiment.note}` : ""}
                </div>
              </div>
              <div className="rounded-lg px-3 py-2.5"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Retrieval index</div>
                <div className="text-[12.5px] font-bold mt-0.5">
                  {health.rag?.state || "idle"}
                  {health.rag?.dim ? ` · ${num(health.rag.dim, 0)}-d` : ""}
                </div>
                <div className="muted text-[10.5px] mt-0.5 truncate" title={health.rag?.engine || ""}>
                  {health.rag?.engine || "—"}
                </div>
              </div>
            </div>

            <Note>{health.data_note}</Note>
            <Note>{health.disclaimer}</Note>
          </div>
        )}
      </Panel>

      {/* Active workspace — mounted only when selected so the hub does not
          fire four heavy analyses on first paint. */}
      <div className="mt-3">
        {active === "rangecast" && <RangeCast />}
        {active === "streetpulse" && <StreetPulse />}
        {active === "xray" && <XRay />}
        {active === "ask-dalal" && <AskDalal />}
      </div>
    </div>
  );
}
