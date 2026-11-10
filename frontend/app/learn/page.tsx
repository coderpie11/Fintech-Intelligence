"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON, postJSON } from "@/lib/api";
import { ErrorBox, PageHeader, Skeleton } from "@/components/PageKit";
import { Pill } from "@/components/quant/Kit";
import MetricTip from "@/components/MetricTip";
import DynamicLoader from "@/components/DynamicLoader";
import { LessonBody, type Lesson } from "@/components/LessonCards";

type Track = {
  id: string;
  title: string;
  level: string;
  summary: string;
  asset: string;
  masterclass?: boolean;
  lesson_count: number;
};

type Hit = {
  id: string;
  title: string;
  one_liner: string;
  track_id: string;
  track_title: string;
  asset: string;
  href: string;
  match_reason?: string;
};

type AiSuggest = {
  label: string;
  endpoint: string;
  auto_generate: boolean;
  cached: boolean;
};

const ASSET_ORDER = ["Universal", "Equities", "F&O", "IPOs", "Mutual Funds", "ETF", "Bonds", "Commodities", "REITs & InvITs", "Forensics"];

const CARD_STEPS: { n: string; title: string; body: string }[] = [
  { n: "1", title: "Simple meaning", body: "One or two friendly sentences in English, repeated in Hinglish." },
  { n: "2", title: "Real-life picture", body: "A dukaan, rent, insurance or token-money story you already know." },
  { n: "3", title: "Formula in words", body: "The maths written the way you would say it out loud." },
  { n: "4", title: "₹1,000 example", body: "Three short lines with round numbers, so the arithmetic is easy to follow." },
  { n: "5", title: "Quick thumb rule", body: "When the idea is useful, and when you should be careful." },
];

export default function LearnPage() {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [total, setTotal] = useState(0);
  const [asof, setAsof] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [asset, setAsset] = useState<string>("All");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [topLesson, setTopLesson] = useState<Lesson | null>(null);
  const [aiSuggest, setAiSuggest] = useState<AiSuggest | null>(null);
  const [searching, setSearching] = useState(false);

  const [ai, setAi] = useState<Lesson | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const [aiMeta, setAiMeta] = useState<{ source: string; latency: number } | null>(null);
  const [aiStatus, setAiStatus] = useState("");

  const seq = useRef(0);
  const autoRef = useRef<string>("");

  // Rotating status lines keep the AI wait legible without naming providers.
  useEffect(() => {
    if (!aiBusy) {
      setAiStatus("");
      return;
    }
    const phrases = [
      "Reading the term…",
      "Finding a dukaan analogy…",
      "Writing the ₹1,000 example…",
      "Checking the thumb rule…",
      "Polishing the five cards…",
    ];
    let i = 0;
    setAiStatus(phrases[0]);
    const id = window.setInterval(() => {
      i = (i + 1) % phrases.length;
      setAiStatus(phrases[i]);
    }, 1400);
    return () => window.clearInterval(id);
  }, [aiBusy]);

  useEffect(() => {
    getJSON("/academy")
      .then((d) => {
        setTracks(d.tracks || []);
        setTotal(d.total_lessons || 0);
        setAsof(d.asof || "");
        setNote(d.note || "");
      })
      .catch((e) => setErr(String(e.message || e)));
  }, []);

  const generate = async (term: string, force = false) => {
    const text = term.trim();
    if (!text) return;
    setAiBusy(true);
    setAiErr(null);
    setAiMeta(null);
    try {
      const r = await postJSON("/academy/ask-topic", { query: text, force });
      if (r.source === "unavailable") {
        // Never render a blank five-card shell. Keep the generate button so
        // the reader can retry, and say plainly that the model did not answer.
        setAi(null);
        setAiMeta(null);
        setAiErr(r.lesson?.error || "The AI teacher could not build this lesson. Please try again.");
        return;
      }
      setAi(r.lesson || null);
      setAiMeta({ source: r.source || "ai", latency: r.latency_ms || 0 });
    } catch (e: any) {
      setAiErr(String(e.message || e).slice(0, 240));
    } finally {
      setAiBusy(false);
    }
  };

  // Shared search runner: the debounce path and the visible Search button both
  // call this. A zero-match query auto-triggers the AI lesson after 600 ms.
  const runSearch = (text: string) => {
    const mine = ++seq.current;
    setSearching(true);
    getJSON(`/academy/search?q=${encodeURIComponent(text)}`)
      .then((d) => {
        if (seq.current !== mine) return;
        setHits(d.lessons || []);
        setTopLesson(d.top_lesson || null);
        setAiSuggest(d.ai_suggest || null);
        if (d.cached_topic) {
          setAi(d.cached_topic);
          setAiMeta({ source: "cache", latency: 0 });
        } else if (d.ai_suggest?.auto_generate && autoRef.current !== text) {
          autoRef.current = text;
          window.setTimeout(() => generate(text), 600);
        }
      })
      .catch(() => {
        if (seq.current === mine) {
          setHits([]);
          setTopLesson(null);
        }
      })
      .finally(() => {
        if (seq.current === mine) setSearching(false);
      });
  };

  // Debounced beginner search. Typing “pe”, “rent” or “sip” should find a
  // topic even if the reader does not know the technical name.
  useEffect(() => {
    const text = q.trim();
    if (text.length < 2) {
      setHits(null);
      setTopLesson(null);
      setAiSuggest(null);
      setAi(null);
      setAiErr(null);
      setAiMeta(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    setAi(null);
    setAiErr(null);
    setAiMeta(null);
    const id = window.setTimeout(() => runSearch(text), 220);
    return () => window.clearTimeout(id);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const assets = useMemo(() => {
    const found = new Set((tracks || []).map((t) => t.asset));
    const ordered = ASSET_ORDER.filter((a) => found.has(a));
    const extra = Array.from(found).filter((a) => !ASSET_ORDER.includes(a));
    return ["All", ...ordered, ...extra];
  }, [tracks]);

  const shown = (tracks || []).filter((t) => asset === "All" || t.asset === asset);
  const searchMode = q.trim().length >= 2;
  const query = q.trim();

  // Visible Search button / Enter key: run the lookup immediately, bypassing
  // the 220 ms typing debounce.
  const submit = () => {
    if (query.length < 1) return;
    autoRef.current = "";
    runSearch(query);
  };

  return (
    <div className="mx-auto max-w-[1400px] px-4 sm:px-6 pb-16">
      <PageHeader
        eyebrow="Market Academy"
        title="Learn the market, one small card at a time"
        sub="No jargon, no long chapters. Every topic is one card with five short parts: a simple meaning in English and Hinglish, an everyday Indian example, the formula in plain words, a quick ₹1,000 example, and a thumb rule. Type any term — if it is not in the library, the AI teacher builds the same five-card lesson."
      />

      <div
        className="rounded-xl px-4 py-3 mb-4"
        style={{
          border: "1px solid color-mix(in srgb, var(--accent) 30%, var(--line))",
          background: "color-mix(in srgb, var(--accent) 6%, transparent)",
        }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="accent">
            <MetricTip label="Topics" tip={{
              meaning: "Short tutorials. Each one teaches a single idea from start to finish, in about two minutes.",
            }}>{total || "—"} topics</MetricTip>
          </Pill>
          <Pill>
            <MetricTip label="Tracks" tip={{
              meaning: "Topic groups. Start with Market Basics, then follow the area you are curious about.",
            }}>{(tracks || []).length} tracks</MetricTip>
          </Pill>
          {asof && (
            <Pill>
              <MetricTip label="Examples as of" tip={{
                meaning: "The date behind the worked examples. The numbers are illustrations, not live prices.",
              }}>Examples as of {asof}</MetricTip>
            </Pill>
          )}
        </div>
        <p className="muted text-[11.5px] leading-relaxed mt-2">
          {note ||
            "Every example is simple arithmetic on illustrative numbers. Educational only — not investment advice."}
        </p>
      </div>

      {/* search */}
      <div className="card p-3.5 sm:p-4 mb-4">
        <label className="block">
          <span className="muted text-[10px] font-bold uppercase tracking-[0.16em]">
            <MetricTip label="Quick search" tip={{
              meaning: "Type any word you already know — “rent”, “sip”, “gold”, “tax”, “profit to book value” — and we will find the topic that explains it. If it is new, the AI teacher writes a fresh five-card lesson.",
            }}>Quick search</MetricTip>
          </span>
          <div className="flex items-center gap-2 mt-1.5">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="Try “P/E”, “profit to book value”, “upper circuit”, “SIP”…"
              className="w-full rounded-lg px-3 py-2.5 text-[13px] outline-none"
              style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
            />
            {q && (
              <button onClick={() => setQ("")} className="chip !text-[11px] !px-3 !py-2 shrink-0">
                Clear
              </button>
            )}
            <button
              onClick={submit}
              disabled={!query}
              className="btn-primary !px-3.5 !py-2.5 !text-[12px] shrink-0"
              title="Search the Academy (or press Enter)"
            >
              Search →
            </button>
          </div>
        </label>

        {/* instant autocomplete suggestions */}
        {searchMode && !searching && hits && hits.length > 0 && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="muted text-[10px] font-bold uppercase tracking-[0.14em] mr-0.5">
              Suggestions
            </span>
            {hits.slice(0, 5).map((h) => (
              <button
                key={`${h.track_id}-${h.id}`}
                onClick={() => setQ(h.title)}
                className="chip !text-[10px] !normal-case hover:!text-[var(--ink)]"
                title={h.one_liner}
              >
                {h.title}
              </button>
            ))}
          </div>
        )}

        {searchMode && (
          <div className="mt-3">
            {searching && <DynamicLoader size={26} status="Searching topics…" className="mb-2" />}

            {!searching && topLesson && (
              <div className="mb-3">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="chip chip-live !text-[10px]">Best match</span>
                    <span className="text-[13px] font-bold">{topLesson.title}</span>
                  </div>
                  <Link href={`/learn/market-jargon?topic=${topLesson.id}`}
                        className="accent text-[11.5px] font-semibold hover:underline">
                    Open in track →
                  </Link>
                </div>
                <LessonBody l={topLesson} />
              </div>
            )}

            {!searching && hits && hits.length === 0 && (
              <p className="muted text-[12px]">
                No built-in topic matched “{query}”. The AI teacher will build one below.
              </p>
            )}

            {!searching && hits && hits.length > 1 && (
              <>
                <p className="muted text-[11px] mb-2">
                  {hits.length} matching topic{hits.length === 1 ? "" : "s"}
                </p>
                <div className="space-y-2">
                  {hits.filter((h) => h.id !== topLesson?.id).map((h) => (
                    <Link
                      key={`${h.track_id}-${h.id}`}
                      href={h.href}
                      className="block rounded-lg px-3 py-2.5 card-hover"
                      style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="text-[13px] font-bold">{h.title}</span>
                        <span className="muted text-[10.5px]">{h.track_title}</span>
                      </div>
                      <p className="muted text-[11.5px] leading-snug mt-1">{h.one_liner}</p>
                    </Link>
                  ))}
                </div>
              </>
            )}

            {/* live AI topic generator */}
            <div className="mt-3">
              {!ai && !aiBusy && (
                <button
                  onClick={() => generate(query, true)}
                  className="btn-primary !px-4 !py-2.5 !text-[12.5px]"
                >
                  ✨ Generate Simple Lesson for “{query}” with AI
                </button>
              )}

              {aiBusy && (
                <div className="card p-4">
                  <DynamicLoader
                    size={44}
                    label={`Building a five-card lesson for “${query}”`}
                    status={aiStatus || "Reading the term…"}
                  />
                  <p className="muted text-[11px] mt-2">
                    The lesson is cached after the first run, so the next search opens instantly.
                  </p>
                </div>
              )}

              {aiErr && (
                <div className="rounded-lg px-3 py-2.5 text-[11.5px] text-down"
                     style={{ border: "1px solid var(--line)" }}>
                  {aiErr}
                </div>
              )}

              {ai && (
                <div className="mt-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="chip chip-live !text-[10px]">✨ AI lesson</span>
                    <span className="text-[13px] font-bold">{ai.title}</span>
                    {aiMeta && (
                      <span className="muted text-[10.5px]">
                        {aiMeta.source === "cache" ? "cached · 0 ms" : `${aiMeta.source} · ${(aiMeta.latency / 1000).toFixed(1)} s`}
                      </span>
                    )}
                    <button
                      onClick={() => generate(query, true)}
                      className="chip !text-[10px] ml-auto"
                    >
                      Regenerate
                    </button>
                  </div>
                  <LessonBody l={ai} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {err && <ErrorBox message={err} stage="academy" />}
      {!tracks && !err && <Skeleton rows={6} />}

      {tracks && !searchMode && (
        <>
          {/* how a topic looks */}
          <div className="card p-4 mb-4">
            <div className="muted text-[10px] font-bold uppercase tracking-[0.16em] mb-2">
              How every topic is laid out
            </div>
            <div className="grid sm:grid-cols-2 xl:grid-cols-5 gap-2">
              {CARD_STEPS.map((s) => (
                <div
                  key={s.n}
                  className="rounded-lg px-3 py-2.5"
                  style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
                >
                  <div className="flex items-center gap-2">
                    <span className="knum accent text-[11px] font-black">{s.n}</span>
                    <span className="text-[11.5px] font-bold">{s.title}</span>
                  </div>
                  <p className="muted text-[11px] leading-snug mt-1">{s.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5 mb-3">
            {assets.map((a) => (
              <button
                key={a}
                onClick={() => setAsset(a)}
                className={`chip !text-[11px] !px-3 !py-1.5 ${asset === a ? "chip-active" : "hover:opacity-80"}`}
              >
                {a}
                {a !== "All" && (
                  <span className="muted ml-1.5">
                    {tracks.filter((t) => t.asset === a).reduce((n, t) => n + t.lesson_count, 0)}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
            {shown.map((t, i) => (
              <Link key={t.id} href={`/learn/${t.id}`} className="card card-hover p-4 block">
                <div className="flex items-start justify-between gap-2">
                  <span className="muted text-[10px] font-bold uppercase tracking-[0.14em]">
                    {t.asset} · {t.level}
                  </span>
                  {t.masterclass ? (
                    <Pill tone="warn">Masterclass</Pill>
                  ) : (
                    <span className="knum muted text-[10.5px]">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  )}
                </div>
                <h3 className="text-[15px] font-extrabold tracking-tight mt-1.5 leading-snug">{t.title}</h3>
                <p className="muted text-[12px] leading-relaxed mt-2">{t.summary}</p>
                <div className="flex items-center justify-between gap-2 mt-3.5">
                  <Pill tone="accent">{t.lesson_count} topics</Pill>
                  <span className="accent text-[12px] font-semibold">Start the track →</span>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
