"use client";

import { useEffect, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { inr } from "@/lib/format";
import { Bar, ErrLine, Loading, Metric, Note, Panel, Pill, num, signed } from "./Kit";

type AskResponse = { intent: string; data: any };

const EXAMPLES: { label: string; question: string; symbol: string }[] = [
  { label: "Bank screener", question: "banks with ROE above 15 and PE below 20", symbol: "" },
  { label: "Single stock", question: "show me RELIANCE", symbol: "RELIANCE" },
  { label: "Grounded filing Q&A", question: "What did the company report for revenue and cash flow from operations?", symbol: "RELIANCE" },
  { label: "Say-vs-Do", question: "Did management walk the talk on its guidance?", symbol: "SBIN" },
  { label: "Filing diff", question: "What changed in the annual statement year over year?", symbol: "RELIANCE" },
  { label: "Dividend screen", question: "companies with dividend yield above 2", symbol: "" },
];

const STATUS_TONE: Record<string, "up" | "down" | "warn" | "neutral"> = {
  met: "up",
  missed: "down",
  pending: "warn",
  unverifiable: "neutral",
};

function ScreenerResult({ d }: { d: any }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={d.mode === "llm" ? "accent" : "neutral"}>
          {d.mode === "llm" ? "LLM-generated SQL" : "Deterministic SQL"}
        </Pill>
        <span className="muted text-[11px]">{num(d.row_count, 0)} rows</span>
        {d.llm?.provider && <span className="muted text-[11px]">· answered by {d.llm.provider} / {d.llm.model}</span>}
        {d.error && <Pill tone="down">{d.error}</Pill>}
      </div>
      <pre className="rounded-lg p-3 text-[11px] overflow-x-auto knum"
           style={{ background: "var(--surface-2)", border: "1px solid var(--line)", color: "var(--accent)" }}>
        {d.sql}
      </pre>
      {(d.rows || []).length > 0 ? (
        <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--line)" }}>
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {(d.columns || []).map((c: string) => (
                  <th key={c} className="table-head px-3 py-2 text-left whitespace-nowrap">{c.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(d.rows || []).map((row: any[], i: number) => (
                <tr key={i} className="table-row">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2 knum text-[11.5px] whitespace-nowrap">
                      {typeof cell === "number"
                        ? (d.columns[j] === "market_cap" ? inr(cell, 0) : num(cell, 2))
                        : String(cell ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted text-[12px]">No rows matched. The SQL is shown above so the filter can be checked, not guessed at.</p>
      )}
      <Note>{d.guard}</Note>
    </div>
  );
}

function DocumentsResult({ d }: { d: any }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={d.llm?.used ? "accent" : "neutral"}>
          {d.llm?.used ? `LLM answer · ${d.llm.provider}` : "Extractive answer"}
        </Pill>
        <Pill tone={d.dense ? "up" : "warn"}>{d.dense ? "Dense + lexical retrieval" : "Lexical retrieval"}</Pill>
        {d.scanned != null && <span className="muted text-[11px]">{num(d.scanned, 0)} chunks scanned</span>}
      </div>
      {d.answer ? (
        <div className="rounded-lg p-3.5 text-[13px] leading-relaxed"
             style={{ border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
                      background: "color-mix(in srgb, var(--accent) 5%, transparent)" }}>
          {d.answer}
        </div>
      ) : (
        <p className="muted text-[12.5px]">{d.note || "No indexed document matches this question."}</p>
      )}
      {(d.hits || []).length > 0 && (
        <div className="space-y-1.5">
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Retrieved passages</div>
          {(d.hits || []).map((h: any, i: number) => (
            <div key={`${h.doc_id}-${h.ordinal}`} className="rounded-lg px-3 py-2"
                 style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <div className="flex flex-wrap items-center gap-2 text-[10.5px]">
                <span className="knum accent font-bold">[{i + 1}]</span>
                <span className="font-semibold">{h.title}</span>
                <Pill>{h.doc_kind}</Pill>
                {h.asof && <span className="muted">{h.asof}</span>}
                <span className="muted ml-auto knum">score {num(h.score, 3)}</span>
              </div>
              <p className="text-[11.5px] leading-relaxed mt-1">{h.text}</p>
              {h.source_url && (
                <a href={h.source_url} target="_blank" rel="noopener noreferrer"
                   className="accent text-[10.5px] underline inline-block mt-1">Open source filing</a>
              )}
            </div>
          ))}
        </div>
      )}
      {d.llm?.error && <Note>LLM unavailable, so the passages were returned verbatim: {d.llm.error}</Note>}
    </div>
  );
}

function CredibilityResult({ d }: { d: any }) {
  const cov = d.coverage || {};
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <Metric label="Commitments found" value={num(cov.quantified_commitments, 0)}
                tip={{ meaning: "Guidance sentences in the company's own filings that state an explicit numeric target. Only explicit percentages are counted; vague intent is not." }}
                sub={`${num(cov.announcements_scanned, 0)} announcements scanned`} />
        <Metric label="Met" value={num(cov.met, 0)} tone="up"
                tip={{ meaning: "Commitments where the later reported actual figure reached the stated target." }} />
        <Metric label="Missed" value={num(cov.missed, 0)} tone="down"
                tip={{ meaning: "Commitments where the reported actual figure fell short of the stated target." }} />
        <Metric label="Credibility score" value={d.credibility_score_pct == null ? "No score" : `${num(d.credibility_score_pct, 1)}%`}
                tip={{ meaning: "Share of scoreable commitments that were met. It is left blank rather than invented when free filings contain no checkable numeric target.",
                       formula: "Score % = Met ÷ (Met + Missed) × 100" }}
                tone={d.credibility_score_pct == null ? "warn" : "accent"} sub={d.credibility_score_pct == null ? "Not a clean record" : "of scoreable commitments"} />
      </div>
      <Note>{d.score_note}</Note>

      {d.realized?.available ? (
        <div className="rounded-lg p-3" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-[11.5px] font-bold">The “did” side</span>
            <Pill tone="accent">{d.realized.latest_period} vs {d.realized.prior_period}</Pill>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Metric label="Revenue growth" value={`${signed(d.realized.revenue_growth_pct, 2)}%`} tone={(d.realized.revenue_growth_pct || 0) >= 0 ? "up" : "down"} />
            <Metric label="Operating margin" value={d.realized.operating_margin_pct == null ? "—" : `${num(d.realized.operating_margin_pct, 2)}%`} />
            <Metric label="Borrowings change" value={`${signed(d.realized.borrowings_change_pct, 2)}%`} />
            <Metric label="CFO ÷ net income" value={`${num(d.realized.cfo_to_net_income, 2)}×`} />
          </div>
          <Note>{d.realized.note}</Note>
        </div>
      ) : (
        <Note>{d.realized?.note}</Note>
      )}

      {(d.commitments || []).length > 0 ? (
        <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--line)" }}>
          <table className="w-full min-w-[860px] border-collapse">
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {["Status", "Metric", "Stated target", "Reported actual", "Source quote"].map((h) => (
                  <th key={h} className="table-head px-3 py-2 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(d.commitments || []).map((c: any, i: number) => (
                <tr key={i} className="table-row">
                  <td className="px-3 py-2.5"><Pill tone={STATUS_TONE[c.status] || "neutral"}>{c.status}</Pill></td>
                  <td className="px-3 py-2.5 text-[11.5px]">{c.metric || "—"}{c.metric_cue ? ` · ${c.metric_cue}` : ""}</td>
                  <td className="px-3 py-2.5 knum text-[11.5px]">{c.target != null ? `${num(c.target, 2)}%` : (c.target_text || "—")}</td>
                  <td className="px-3 py-2.5 knum text-[11.5px]">{c.actual != null ? `${num(c.actual, 2)} ${c.unit || ""}` : "—"}</td>
                  <td className="px-3 py-2.5 text-[10.5px] muted max-w-[360px]">
                    “{c.quote}”
                    {c.source_url && (
                      <a href={c.source_url} target="_blank" rel="noopener noreferrer"
                         className="accent underline block mt-0.5">source document</a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted text-[12px]">
          No quantified guidance sentence was found in this company's latest transcripts or presentations.
          Nothing is invented to fill the table.
        </p>
      )}

      {(d.documents_scanned || []).length > 0 && (
        <div>
          <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] mb-1.5">Documents read</div>
          <div className="flex flex-wrap gap-1.5">
            {(d.documents_scanned || []).map((doc: any, i: number) => (
              <Pill key={i} tone="accent" title={doc.announced || ""}>{doc.category} · {num(doc.characters, 0)} chars</Pill>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilingDiffResult({ d }: { d: any }) {
  if (!d.available) {
    return (
      <div className="space-y-2">
        <Pill tone="warn">Not available</Pill>
        <p className="muted text-[12.5px] leading-relaxed">{d.note}</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="accent">{d.granularity || "annual"}</Pill>
        <span className="muted text-[11.5px]">Comparing {d.compared?.[0]} against {d.compared?.[1]}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {(d.themes || []).map((t: any) => (
          <Pill key={t.theme} tone={(t.change_pct || 0) >= 0 ? "up" : "down"}>
            {t.theme}{t.change_pct != null ? ` ${signed(t.change_pct, 1)}%` : ""}
          </Pill>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--line)" }}>
        <table className="w-full min-w-[680px] border-collapse">
          <thead>
            <tr style={{ background: "var(--surface-2)" }}>
              {["Section", "Line item", d.compared?.[1] ?? "Prior", d.compared?.[0] ?? "Latest", "Change"].map((h) => (
                <th key={h} className={`table-head px-3 py-2 ${h === "Section" || h === "Line item" ? "text-left" : "text-right"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(d.changes || []).map((c: any, i: number) => (
              <tr key={i} className="table-row">
                <td className="px-3 py-2 text-[11px] muted">{c.section}</td>
                <td className="px-3 py-2 text-[11.5px] font-semibold">{c.item.replace(/_/g, " ")}</td>
                <td className="px-3 py-2 text-right knum text-[11.5px]">{c.prior == null ? "—" : num(c.prior, 2)}</td>
                <td className="px-3 py-2 text-right knum text-[11.5px]">{c.current == null ? "—" : num(c.current, 2)}</td>
                <td className={`px-3 py-2 text-right knum text-[11.5px] font-bold ${(c.change_pct || 0) >= 0 ? "text-up" : "text-down"}`}>
                  {c.change_pct == null ? "—" : `${signed(c.change_pct, 2)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note>{d.note}</Note>
    </div>
  );
}

export default function AskDalal() {
  const [question, setQuestion] = useState(EXAMPLES[0].question);
  const [symbol, setSymbol] = useState("");
  const [preferLlm, setPreferLlm] = useState(true);
  const [res, setRes] = useState<AskResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [corpus, setCorpus] = useState<any>(null);

  useEffect(() => {
    getJSON("/quant-hub/ask-dalal/corpus").then(setCorpus).catch(() => {});
  }, []);

  const ask = async (q = question, sym = symbol) => {
    if (!q.trim()) return;
    setBusy(true);
    setErr(null);
    setRes(null);
    try {
      const r = await postJSON<AskResponse>("/quant-hub/ask-dalal", {
        question: q.trim(),
        symbol: sym.trim() ? sym.trim().toUpperCase() : null,
        prefer_llm: preferLlm,
      });
      setRes(r);
    } catch (e: any) {
      setErr(String(e.message || e).slice(0, 220));
    }
    setBusy(false);
  };

  return (
    <div className="space-y-3">
      <Panel
        title="Ask Dalal AI — guarded data questions"
        sub="A text-to-SQL screener over read-only views, a grounded document answerer, a CEO say-vs-do tracker and a filing diff. Every answer shows its SQL, its sources or its score logic — no hidden model opinion."
      >
        <div className="space-y-2">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(); }}
            rows={2}
            placeholder="e.g. banks with ROE above 15 and PE below 20"
            className="surface rounded-lg px-3 py-2.5 w-full text-[13px] resize-y"
            style={{ color: "var(--ink)" }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <label className="block">
              <span className="muted text-[9.5px] font-bold uppercase tracking-[0.13em] block mb-1">Symbol (for filing / say-vs-do)</span>
              <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                     placeholder="RELIANCE"
                     className="surface rounded-lg px-3 py-2 knum w-40 text-[12.5px]" style={{ color: "var(--ink)" }} />
            </label>
            <label className="flex items-center gap-2 text-[11.5px] muted mt-4">
              <input type="checkbox" checked={preferLlm} onChange={(e) => setPreferLlm(e.target.checked)} />
              Use the LLM tier when it is available
            </label>
            <button onClick={() => ask()} disabled={busy} className="btn-primary !py-2 !text-[12.5px] ml-auto mt-4">
              {busy ? "Thinking…" : "Ask Dalal"}
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {EXAMPLES.map((ex) => (
              <button key={ex.label} className="chip !text-[9.5px] hover:opacity-80"
                      onClick={() => { setQuestion(ex.question); setSymbol(ex.symbol); ask(ex.question, ex.symbol); }}>
                {ex.label}
              </button>
            ))}
          </div>
        </div>
        {corpus && (
          <div className="flex flex-wrap items-center gap-2 mt-3 pt-3" style={{ borderTop: "1px solid var(--line)" }}>
            <Pill tone="accent">{num(corpus.documents, 0)} documents</Pill>
            <Pill>{num(corpus.chunks, 0)} chunks</Pill>
            <Pill tone={corpus.embedded_chunks > 0 ? "up" : "warn"}>
              {corpus.embedded_chunks > 0 ? `${num(corpus.embedded_chunks, 0)} embedded` : "lexical only"}
            </Pill>
            <Pill>{corpus.encoder?.state || "encoder idle"}</Pill>
            {corpus.encoder?.state === "ready" && <span className="muted text-[10.5px]">{corpus.encoder.dim}-d · {corpus.encoder.engine}</span>}
          </div>
        )}
      </Panel>

      {err && <ErrLine message={`Ask Dalal could not answer: ${err}`} onRetry={() => ask()} />}
      {busy && <Loading label="Routing the question, then running the guard…" />}

      {res && (
        <Panel
          title={
            res.intent === "screener" ? "Screener result" :
            res.intent === "documents" ? "Grounded document answer" :
            res.intent === "credibility" ? `${res.data?.symbol || "Company"} — Say-vs-Do ledger` :
            `${res.data?.symbol || "Company"} — filing diff`
          }
          right={<Pill tone="accent">{res.intent}</Pill>}
        >
          {res.intent === "screener" && <ScreenerResult d={res.data} />}
          {res.intent === "documents" && <DocumentsResult d={res.data} />}
          {res.intent === "credibility" && <CredibilityResult d={res.data} />}
          {res.intent === "filing-diff" && <FilingDiffResult d={res.data} />}
        </Panel>
      )}
    </div>
  );
}
