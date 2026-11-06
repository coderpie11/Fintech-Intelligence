/**
 * Fintech Intelligence brand mark — a bull/bear split from one shared origin.
 * Both trend lines leave the exact same point (5,16): emerald breaks upward,
 * crimson sweeps down. Rendered inside a graphite rounded square so it reads
 * the same in light and dark mode.
 */
export default function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="grid shrink-0 place-items-center rounded-lg"
      style={{
        width: size,
        height: size,
        background: "#121214",
        border: "1px solid #27272A",
        boxShadow: "0 6px 18px -10px rgba(16,185,129,.55)",
      }}
      aria-hidden
    >
      <svg width={size - 6} height={size - 6} viewBox="0 0 32 32" fill="none">
        {/* bear — same origin, sweeping down to a crimson point */}
        <path
          d="M5 16 L12 21 L17 18 L26 26"
          stroke="#F43F5E"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M21.5 26 L26 26 L26 21.5"
          stroke="#F43F5E"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* bull — same origin, sharp breakout to an emerald horn */}
        <path
          d="M5 16 L12 11 L17 14 L26 6"
          stroke="#10B981"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M21.5 6 L26 6 L26 10.5"
          stroke="#10B981"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* bright shared origin */}
        <circle cx="5" cy="16" r="2.1" fill="#F4F4F5" />
        <circle cx="5" cy="16" r="1" fill="#10B981" />
      </svg>
    </span>
  );
}
