"use client";

/** The compact, non-advisory banner. Bold, highlighted, small — details
    expand ONLY when the user clicks. Never spans the page. */
export default function DisclaimerBand() {
  return (
    <details className="dsc group">
      <summary
        className="select-none rounded-xl px-4 py-2.5 surface inline-flex items-center gap-2"
        style={{ borderColor: "var(--accent-2)" }}
      >
        <span className="blink-red text-[12.5px] font-extrabold tracking-wide" style={{ color: "var(--down)" }}>
          NOT A BUY OR SELL RECOMMENDATION
        </span>
        <span className="muted text-[11px] hidden sm:inline">
          · Data &amp; quantitative analysis only — not investment advice
        </span>
        <span className="muted text-[10px]">▾ click to read the full disclaimer</span>
      </summary>
      <div className="card mt-2 p-4 text-[12.5px] leading-relaxed muted">
        <p>
          <strong className="text-ink" style={{ color: "var(--ink)" }} >
            This platform is a factual market database and educational tool.
          </strong>{" "}
          Every number, chart, score, probabilistic band, or AI-generated
          summary on this site is a mathematical or historical output computed
          from public exchange data. Nothing here constitutes, or should be
          read as, a buy or sell recommendation.
        </p>
        <p className="mt-2">
          We do not know your financial position, goals, tax situation or risk
          appetite. Markets involve both profits and losses. Always consult a
          SEBI-registered investment adviser before acting on anything. Use of
          this platform is for engineering, learning and research purposes
          only.
        </p>
      </div>
    </details>
  );
}
