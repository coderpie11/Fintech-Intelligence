"use client";

import { useState } from "react";
import RangeCast from "@/components/quant/RangeCast";
import StreetPulse from "@/components/quant/StreetPulse";
import XRay from "@/components/quant/XRay";
import AskDalal from "@/components/quant/AskDalal";

const TABS = [
  { key: "rangecast", name: "RangeCast AI", short: "7/14-day 80% bands", fact: "Probabilistic price envelope from realised volatility, clipped at live F&O open-interest walls." },
  { key: "streetpulse", name: "StreetPulse Matrix", short: "Flows vs delivery", fact: "Official FII/DII rupee flows read against exchange delivery and public-headline tone." },
  { key: "xray", name: "4 PM Market X-Ray", short: "Money-flow chain", fact: "Four-step institutional money-flow synthesis plus volume shockers, each step labelled with what it can prove." },
  { key: "ask-dalal", name: "Ask Dalal AI", short: "Research notes & filings", fact: "Five-section institutional research notes, grounded document answers, say-vs-do ledger and filing diffs." },
];

export default function AiQuantHubPage() {
  const [active, setActive] = useState("rangecast");

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
          Indian-market data. Model outputs can be wrong; each workspace states its
          inputs, method and limits next to the answer. We do not know your
          portfolio, goals or risk appetite. Consult a SEBI-registered investment
          adviser before acting on anything.
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

