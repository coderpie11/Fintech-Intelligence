"use client";

import MetricTip from "@/components/MetricTip";
import { Note, Pill } from "@/components/quant/Kit";

export type ThumbRule = { good?: string[]; careful?: string[] };

export type Lesson = {
  id: string;
  title: string;
  one_liner?: string;
  hinglish?: string;
  simple?: { en?: string; hi?: string };
  analogy?: string;
  formula?: {
    expression?: string;
    plain?: string;
    note?: string;
    variables?: [string, string][] | string[];
  };
  example?: {
    title?: string;
    lines?: string[];
    calculation?: string;
    result?: string;
    asof?: string;
  };
  thumb_rule?: ThumbRule;
  pitfall?: string;
  link?: { label: string; href: string };
  ai_generated?: boolean;
  provider?: string | null;
  cached?: boolean;
};

function StepCard({
  n,
  label,
  tone = "accent",
  children,
}: {
  n: string;
  label: string;
  tone?: "accent" | "warn";
  children: React.ReactNode;
}) {
  const color = tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div className="card p-4 sm:p-5">
      <div className="flex items-center gap-2.5 mb-3">
        <span
          className="knum text-[12px] font-black h-6 w-6 rounded-full grid place-items-center shrink-0"
          style={{
            color,
            border: `1px solid color-mix(in srgb, ${color} 38%, var(--line))`,
            background: `color-mix(in srgb, ${color} 10%, transparent)`,
          }}
        >
          {n}
        </span>
        <span className="text-[11px] font-bold uppercase tracking-[0.15em]" style={{ color }}>
          {label}
        </span>
      </div>
      {children}
    </div>
  );
}

export function LessonBody({ l }: { l: Lesson }) {
  const en = l.simple?.en || l.one_liner || "";
  const hi = l.simple?.hi || l.hinglish || "";
  const lines = (l.example?.lines || []).filter(Boolean);
  return (
    <div className="space-y-3">
      {/* 1 — simple meaning */}
      <StepCard n="1" label="Simple meaning">
        <div className="grid sm:grid-cols-2 gap-2.5">
          <div
            className="rounded-lg px-3.5 py-3"
            style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
          >
            <div className="muted text-[9px] font-bold uppercase tracking-[0.14em]">
              <MetricTip
                label="In simple English"
                tip={{ meaning: "The idea in friendly English. Read this line first — nothing else is needed to follow the rest." }}
              >
                In simple English
              </MetricTip>
            </div>
            <p className="text-[13px] leading-relaxed mt-1.5">{en || "—"}</p>
          </div>
          <div
            className="rounded-lg px-3.5 py-3"
            style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
          >
            <div className="muted text-[9px] font-bold uppercase tracking-[0.14em]">
              <MetricTip
                label="Hinglish mein"
                tip={{ meaning: "The same idea in everyday Hinglish, for readers who think in Hindi mixed with English market words." }}
              >
                Hinglish mein
              </MetricTip>
            </div>
            <p className="text-[13px] leading-relaxed mt-1.5">{hi || "—"}</p>
          </div>
        </div>
      </StepCard>

      {/* 2 — real-life analogy */}
      {l.analogy && (
        <StepCard n="2" label="Real-life example">
          <p className="text-[13px] leading-[1.8]">{l.analogy}</p>
        </StepCard>
      )}

      {/* 3 — formula in plain words */}
      <StepCard n="3" label="Formula in plain words">
        <div
          className="rounded-lg px-3.5 py-3 knum text-[13.5px] font-semibold break-words"
          style={{
            border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
            background: "color-mix(in srgb, var(--accent) 7%, transparent)",
          }}
        >
          {l.formula?.expression || "No formula — this is a concept, not a ratio."}
        </div>
        {l.formula?.plain && (
          <p className="text-[12.5px] leading-relaxed mt-2">
            <span className="muted">In words: </span>
            {l.formula.plain}
          </p>
        )}
        {l.formula?.note && <Note>{l.formula.note}</Note>}
      </StepCard>

      {/* 4 — 3-line example */}
      <StepCard n="4" label={`Example — ${l.example?.title || "3 easy lines"}`}>
        {lines.length > 0 ? (
          <ol className="space-y-1.5">
            {lines.map((line, i) => (
              <li key={i} className="flex gap-2.5 text-[12.5px] leading-relaxed">
                <span className="knum accent font-black shrink-0">{i + 1}.</span>
                <span className="knum">{line}</span>
              </li>
            ))}
          </ol>
        ) : (
          <>
            <div className="knum text-[12.5px] break-words">
              <span className="muted">Calculation: </span>
              {l.example?.calculation}
            </div>
            <p className="text-[12.5px] font-semibold mt-1.5">{l.example?.result}</p>
          </>
        )}
        {l.example?.asof && (
          <div className="mt-2.5">
            <Pill tone="accent">illustrative · as of {l.example.asof}</Pill>
          </div>
        )}
      </StepCard>

      {/* 5 — thumb rule */}
      {(l.thumb_rule?.good?.length || l.thumb_rule?.careful?.length || l.pitfall) && (
        <StepCard n="5" label="Quick thumb rule">
          <div className="grid sm:grid-cols-2 gap-2.5">
            <div
              className="rounded-lg px-3.5 py-3"
              style={{
                border: "1px solid color-mix(in srgb, var(--up) 32%, var(--line))",
                background: "color-mix(in srgb, var(--up) 7%, transparent)",
              }}
            >
              <div className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "var(--up)" }}>
                When is it good?
              </div>
              <ul className="mt-1.5 space-y-1 text-[12.5px] leading-snug list-disc pl-4">
                {(l.thumb_rule?.good || []).map((g) => <li key={g}>{g}</li>)}
              </ul>
            </div>
            <div
              className="rounded-lg px-3.5 py-3"
              style={{
                border: "1px solid color-mix(in srgb, var(--warn) 34%, var(--line))",
                background: "color-mix(in srgb, var(--warn) 7%, transparent)",
              }}
            >
              <div className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: "var(--warn)" }}>
                When should you be careful?
              </div>
              <ul className="mt-1.5 space-y-1 text-[12.5px] leading-snug list-disc pl-4">
                {(l.thumb_rule?.careful || (l.pitfall ? [l.pitfall] : [])).map((c) => <li key={c}>{c}</li>)}
              </ul>
            </div>
          </div>
        </StepCard>
      )}
    </div>
  );
}
