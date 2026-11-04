"use client";

export default function Tabs({
  tabs, active, onChange,
}: {
  tabs: { key: string; label: string }[];
  active: string;
  onChange: (k: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`chip !text-[11.5px] !px-3.5 !py-1.5 ${active === t.key ? "chip-active" : "hover:opacity-80"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
