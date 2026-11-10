"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { getJSON } from "@/lib/api";
import { ErrorBox, PageHeader, Skeleton } from "@/components/PageKit";
import { Pill } from "@/components/quant/Kit";
import MetricTip from "@/components/MetricTip";
import { LessonBody, type Lesson } from "@/components/LessonCards";

type Track = {
  id: string;
  title: string;
  level: string;
  summary: string;
  asset: string;
  asof: string;
  masterclass?: boolean;
  lessons: Lesson[];
};

function TrackBody() {
  const { track } = useParams<{ track: string }>();
  const params = useSearchParams();
  const topicParam = params?.get("topic") || null;

  const [t, setT] = useState<Track | null>(null);
  const [idx, setIdx] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setT(null);
    setErr(null);
    getJSON(`/academy/${track}`)
      .then((d) => {
        setT(d);
        const start = topicParam ? (d.lessons || []).findIndex((x: Lesson) => x.id === topicParam) : 0;
        setIdx(start >= 0 ? start : 0);
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [track]); // eslint-disable-line react-hooks/exhaustive-deps

  const lessons = useMemo(() => t?.lessons || [], [t]);
  const lesson = lessons[idx];

  const go = (next: number) => {
    if (next < 0 || next >= lessons.length) return;
    setIdx(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="mx-auto max-w-[1000px] px-4 sm:px-6 pb-16">
      <Link href="/learn" className="text-[12.5px] accent hover:underline inline-block pt-8">
        ← all tracks
      </Link>

      {err && <ErrorBox message={err} stage="academy" />}
      {!t && !err && <Skeleton rows={5} />}

      {t && lesson && (
        <>
          <PageHeader
            eyebrow={`${t.asset} · ${t.level}${t.masterclass ? " · Masterclass" : ""}`}
            title={t.title}
            sub={t.summary}
            right={
              <div className="flex flex-wrap gap-1.5">
                <Pill tone="accent">
                  Topic {idx + 1} of {lessons.length}
                </Pill>
                {t.asof && <Pill>Examples as of {t.asof}</Pill>}
              </div>
            }
          />

          {/* progress + topic picker */}
          <div className="card p-3.5 sm:p-4 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="muted text-[10.5px] font-bold uppercase tracking-[0.14em]">
                <MetricTip
                  label="Progress"
                  tip={{ meaning: "You read one topic at a time. Press “Next Topic” when you are ready for the next one." }}
                >
                  Progress through this track
                </MetricTip>
              </div>
              <div className="min-w-[200px] flex-1 max-w-[420px]">
                <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${((idx + 1) / lessons.length) * 100}%`,
                      background: "var(--accent)",
                    }}
                  />
                </div>
              </div>
              <select
                value={lesson.id}
                onChange={(e) => {
                  const at = lessons.findIndex((x) => x.id === e.target.value);
                  if (at >= 0) go(at);
                }}
                className="rounded-lg px-2.5 py-1.5 text-[12px] outline-none max-w-[280px]"
                style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}
                aria-label="Jump to a topic"
              >
                {lessons.map((x, i) => (
                  <option key={x.id} value={x.id}>
                    {i + 1}. {x.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {lessons.map((x, i) => (
                <button
                  key={x.id}
                  onClick={() => go(i)}
                  title={x.title}
                  className={`h-2.5 w-2.5 rounded-full transition-all ${i === idx ? "" : "opacity-40 hover:opacity-80"}`}
                  style={{ background: i === idx ? "var(--accent)" : "var(--ink)" }}
                  aria-label={`Topic ${i + 1}: ${x.title}`}
                />
              ))}
            </div>
          </div>

          {/* topic title */}
          <div className="mb-3">
            <div className="knum muted text-[11px] font-bold">
              Topic {String(idx + 1).padStart(2, "0")} / {String(lessons.length).padStart(2, "0")}
            </div>
            <h2 className="text-[21px] sm:text-[24px] font-extrabold tracking-tight mt-1">
              {lesson.title}
            </h2>
          </div>

          <LessonBody l={lesson} />

          {lesson.link?.href && (
            <Link
              href={lesson.link.href}
              className="inline-block mt-3.5 text-[12.5px] accent font-semibold hover:underline"
            >
              {lesson.link.label} →
            </Link>
          )}

          {/* prev / next */}
          <div className="flex flex-wrap items-center justify-between gap-3 mt-5">
            <button
              onClick={() => go(idx - 1)}
              disabled={idx === 0}
              className="btn-secondary !px-4 !py-2.5 !text-[12.5px] disabled:opacity-40"
            >
              ← Previous Topic
            </button>
            {idx < lessons.length - 1 ? (
              <button onClick={() => go(idx + 1)} className="btn-primary !px-4 !py-2.5 !text-[12.5px]">
                Next Topic →
              </button>
            ) : (
              <Link href={`/learn/${t.id}`} className="chip chip-active !text-[12px] !px-3.5 !py-2">
                ✓ Track complete — restart
              </Link>
            )}
          </div>

          <p className="muted text-[11px] leading-relaxed mt-5">
            Educational material only. The worked examples are simple arithmetic on round numbers,
            not live quotes, and they do not suggest that any instrument is suitable for you.
          </p>
        </>
      )}
    </div>
  );
}

export default function LearnTrackPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1000px] px-4 sm:px-6 pb-16 pt-8"><Skeleton rows={5} /></div>}>
      <TrackBody />
    </Suspense>
  );
}
