"use client";

import MetricTip from "@/components/MetricTip";

type Health = {
  composite?: any;
  piotroski?: any;
  altman?: any;
  beneish?: any;
  dupont?: any;
};

function ScoreRing({ score, max, label }: { score: number | null; max: number; label: string }) {
  const pct = max ? Math.max(0, Math.min(100, (score || 0) / max * 100)) : 0;
  const color = pct >= 75 ? "var(--up)" : pct >= 45 ? "var(--warn)" : "var(--down)";
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-[62px] w-[62px] shrink-0">
        <svg viewBox="0 0 44 44" className="h-full w-full -rotate-90">
          <circle cx="22" cy="22" r="18" fill="none" stroke="var(--line)" strokeWidth="4" />
          <circle cx="22" cy="22" r="18" fill="none" stroke={color} strokeWidth="4"
                  strokeLinecap="round" strokeDasharray={`${(pct / 100) * 113} 113`} />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center knum text-[14px] font-black">
          {score ?? "—"}
          <span className="muted text-[9px] font-semibold">/{max}</span>
        </div>
      </div>
      <div>
        <div className="text-[12px] font-bold">{label}</div>
        <div className="muted text-[10.5px]">{pct.toFixed(0)}% of applicable signals</div>
      </div>
    </div>
  );
}

export default function HealthScorecard({ health }: { health?: Health }) {
  const pio = health?.piotroski || {};
  const alt = health?.altman || {};
  const ben = health?.beneish || {};
  const dup = health?.dupont || {};
  const composite = health?.composite?.value ?? null;

  const compositeColor = composite == null ? "var(--muted)"
    : composite >= 65 ? "var(--up)" : composite >= 40 ? "var(--warn)" : "var(--down)";

  return (
    <div className="space-y-3">
      <div className="grid md:grid-cols-3 gap-3">
        {/* Piotroski */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">
              <MetricTip label="Piotroski F-Score" tip={{
                meaning: "Nine binary fundamental signals covering profitability, leverage/liquidity and operating efficiency. A higher score means the reported fundamentals improved on more tests.",
                formula: "F = sum of 9 pass/fail signals",
                example: "Positive ROA, positive CFO, falling leverage and improving margins each add 1 point.",
              }}>Piotroski F-Score</MetricTip>
            </div>
            <span className="chip !text-[9px]">{pio.label || "—"}</span>
          </div>
          <ScoreRing score={pio.score ?? null} max={pio.max || 9} label="Fundamental momentum" />
          <div className="mt-3 space-y-1.5">
            {(pio.signals || []).slice(0, 9).map((s: any) => (
              <div key={s.name} className="flex items-start gap-2 text-[11px]">
                <span className={`mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full flex items-center justify-center text-[8px] font-black ${s.pass ? "text-up" : "text-down"}`}
                      style={{ border: `1px solid ${s.pass ? "var(--up)" : "var(--down)"}` }}>
                  {s.pass ? "✓" : "✕"}
                </span>
                <span className={s.pass ? "" : "muted"}>{s.name}</span>
              </div>
            ))}
          </div>
          {pio.note && <p className="muted text-[10px] mt-3 leading-relaxed">{pio.note}</p>}
        </div>

        {/* Altman */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">
              <MetricTip label="Altman Z-Score" tip={{
                meaning: "A bankruptcy-risk screen combining working capital, retained earnings, operating profit, market value of equity and asset turnover.",
                formula: "Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5",
                example: "A Z of 3.4 sits above the 2.99 safe threshold for a manufacturer.",
              }}>Altman Z-Score</MetricTip>
            </div>
            {alt.applicable && <span className="chip !text-[9px]">{alt.variant || "Z"}</span>}
          </div>
          {alt.applicable ? (
            <>
              <div className="knum text-[34px] font-black leading-none">{alt.score ?? "—"}</div>
              <div className="flex items-center gap-2 mt-2">
                <span className={`chip !text-[9px] ${alt.zone === "Safe" ? "chip-live" : alt.zone === "Grey" ? "chip-warn" : ""}`}
                      style={alt.zone === "Distress"
                        ? { color: "var(--down)", borderColor: "color-mix(in srgb, var(--down) 40%, var(--line))",
                            background: "color-mix(in srgb, var(--down) 10%, transparent)" } : undefined}>
                  {alt.zone} zone
                </span>
                <span className="muted text-[10px]">
                  safe above {alt.thresholds?.safe_above ?? "—"}
                </span>
              </div>
              <div className="mt-3 space-y-1">
                {Object.entries(alt.components || {}).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-[10.5px]">
                    <span className="muted">{k.replace(/_/g, " ")}</span>
                    <span className="knum font-semibold">{Number(v).toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="muted text-[12px] leading-relaxed mt-1">{alt.note}</p>
          )}
          {alt.applicable && alt.note && <p className="muted text-[10px] mt-3 leading-relaxed">{alt.note}</p>}
        </div>

        {/* Beneish */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">
              <MetricTip label="Beneish M-Score" tip={{
                meaning: "An eight-variable screen for earnings manipulation. It compares accruals, receivables, margins, asset quality and leverage against the prior year.",
                formula: "M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI",
                example: "An M-Score above −1.78 is the conventional flag for possible manipulation.",
              }}>Beneish M-Score</MetricTip>
            </div>
            {ben.applicable && (
              <span className={`chip !text-[9px] ${ben.score > -1.78 ? "chip-warn" : "chip-live"}`}>
                {ben.score > -1.78 ? "Review" : "No flag"}
              </span>
            )}
          </div>
          {ben.applicable ? (
            <>
              <div className="knum text-[34px] font-black leading-none">{ben.score ?? "—"}</div>
              <div className="muted text-[11px] mt-1.5">
                {ben.flag} · threshold {ben.threshold ?? -1.78}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1">
                {Object.entries(ben.components || {}).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-[10.5px]">
                    <span className="muted">{k}</span>
                    <span className="knum font-semibold">{Number(v).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="muted text-[12px] leading-relaxed mt-1">{ben.note}</p>
          )}
          {ben.applicable && ben.note && <p className="muted text-[10px] mt-3 leading-relaxed">{ben.note}</p>}
        </div>
      </div>

      {/* DuPont */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <div className="text-[13px] font-bold">
              <MetricTip label="Three-step DuPont" tip={{
                meaning: "Splits return on equity into what drives it: how profitable each sale is, how efficiently assets generate sales, and how much leverage is used.",
                formula: "ROE = Net margin × Asset turnover × Equity multiplier",
                example: "10% margin × 1.4× turnover × 2.0× leverage = 28% ROE.",
              }}>Three-step DuPont</MetricTip>
            </div>
            <p className="muted text-[11px] mt-0.5">ROE = net margin × asset turnover × equity multiplier.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="muted text-[10px] font-bold uppercase tracking-wider">Composite</span>
            <span className="knum text-[22px] font-black" style={{ color: compositeColor }}>
              {composite != null ? `${composite}/100` : "—"}
            </span>
          </div>
        </div>

        <div className="grid sm:grid-cols-3 gap-2">
          {[
            { label: "Net profit margin", value: dup.net_margin_pct, fmt: (v: number) => `${v.toFixed(2)}%`, note: "Net profit ÷ revenue" },
            { label: "Asset turnover", value: dup.asset_turnover, fmt: (v: number) => `${v.toFixed(2)}×`, note: "Revenue ÷ total assets" },
            { label: "Equity multiplier", value: dup.equity_multiplier, fmt: (v: number) => `${v.toFixed(2)}×`, note: "Total assets ÷ equity" },
          ].map((x) => (
            <div key={x.label} className="rounded-lg p-3"
                 style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <div className="muted text-[9.5px] font-bold uppercase tracking-wider">{x.label}</div>
              <div className="knum text-[19px] font-black mt-1">
                {x.value != null ? x.fmt(Number(x.value)) : "—"}
              </div>
              <div className="muted text-[10px] mt-0.5">{x.note}</div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-3">
          <span className="muted text-[11px]">Resulting ROE</span>
          <span className="knum text-[17px] font-black accent">
            {dup.roe_pct != null ? `${Number(dup.roe_pct).toFixed(2)}%` : "—"}
          </span>
          <span className="muted text-[10.5px]">· computed from the same reported statements</span>
        </div>
      </div>
    </div>
  );
}
