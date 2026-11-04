import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        surface2: "var(--surface-2)",
        hover: "var(--hover)",
        line: "var(--line)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        accent2: "var(--accent-2)",
        up: "var(--up)",
        down: "var(--down)",
        warn: "var(--warn)",
        // fixed brand tokens (same in both themes)
        cyan: "#06B6D4",
        royal: "#3B82F6",
        bull: "#10B981",
        bear: "#F43F5E",
        gold: "#F59E0B",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(2, 6, 23, 0.35), inset 0 1px 0 rgba(255,255,255,0.035)",
        lift: "0 18px 40px -18px rgba(2, 6, 23, 0.75)",
        glow: "0 0 0 1px rgba(6,182,212,0.25), 0 0 32px -8px rgba(6,182,212,0.35)",
      },
      borderRadius: {
        xl2: "14px",
      },
      keyframes: {
        draw: {
          from: { strokeDashoffset: "2400" },
          to: { strokeDashoffset: "0" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-600px 0" },
          "100%": { backgroundPosition: "600px 0" },
        },
        floatIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        draw: "draw 1.1s ease-out forwards",
        pulseSoft: "pulseSoft 2.4s ease-in-out infinite",
        shimmer: "shimmer 1.6s linear infinite",
        floatIn: "floatIn .18s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
