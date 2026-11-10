import Link from "next/link";
import MetricTip from "@/components/MetricTip";

export function Legal({ title, updated, blocks }: { title: string; updated: string; blocks: [string, string][] }) {
  return (
    <div className="max-w-[900px] mx-auto px-4 sm:px-6 pt-12 pb-16">
      <Link href="/" className="text-[12.5px] accent hover:underline">← home</Link>
      <h1 className="text-[34px] font-black tracking-tight mt-3">{title}</h1>
      <p className="muted text-[12.5px] mt-1">
        <MetricTip label="Last updated" tip={{
          meaning: "The date this page was last revised. It is a policy revision date, not the as-of date of any market data.",
        }}>{updated}</MetricTip>
      </p>
      <div className="mt-8 space-y-8">
        {blocks.map(([h, b]) => (
          <section key={h}>
            <h2 className="text-[15px] font-extrabold mb-2">{h}</h2>
            <p className="text-[13.5px] leading-[1.8] muted">{b}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
