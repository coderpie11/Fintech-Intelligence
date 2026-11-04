import type { Env } from "@/lib/api";
import { chgClass, pct } from "@/lib/format";

/** Renders the contextual data envelope honestly: value when REPORTED,
    or the status + explanation when unavailable. Never a bare dash. */
export function EnvVal({
  env,
  fmt,
  className = "",
  showNote = false,
}: {
  env?: Env;
  fmt: (v: any) => string;
  className?: string;
  showNote?: boolean;
}) {
  if (!env) return <span className={`muted ${className}`}>—</span>;
  if (env.value !== null && env.status === "REPORTED") {
    return <span className={`knum ${className}`}>{fmt(env.value)}</span>;
  }
  return (
    <span
      title={env.note}
      className={`text-[12px] muted ${className}`}
      style={{ cursor: "help", borderBottom: "1px dotted var(--line)" }}
    >
      {friendlyStatus(env.status)}
      {showNote && (
        <span className="block muted text-[11px] font-normal normal-case mt-0.5 max-w-[280px]">
          {env.note}
        </span>
      )}
    </span>
  );
}

export function friendlyStatus(s: string): string {
  return s
    .replace("LISTED-RECENTLY-UNAVAILABLE", "New listing")
    .replace("NOT-APPLICABLE-FOR-SECTOR", "N/A sector")
    .replace("NOT-DISCLOSED-BY-COMPANY", "Not disclosed")
    .replace("SOURCE-UNAVAILABLE-RETRY-LATER", "Source pending");
}

export default EnvVal;

/** Coloured percent with sign */
export function PctVal({ env }: { env?: Env }) {
  if (!env || env.value === null || env.value === undefined)
    return <span className="text-[12px] muted">—</span>;
  if (env.status !== "REPORTED")
    return <EnvVal env={env} fmt={pct} />;
  return (
    <span className={`knum font-semibold ${chgClass(env.value)}`}>{pct(env.value)}</span>
  );
}
