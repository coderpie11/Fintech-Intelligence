import { Legal } from "@/components/LegalPage";

const blocks: [string, string][] = [
  ["Exchange live data",
    "NSE market status, live index values, equity quotes with P/E and face-value metrics, index constituents, full option chains and corporate-action announcements, fetched through a cookie-aware session client (jugaad-data). BSE index (SENSEX) via the same exchange session where offered."],
  ["Historical prices",
    "Daily OHLCV history for equities, indices, international gold/silver and USD/INR from Yahoo Finance (end-of-day)."],
  ["Mutual funds & ETFs",
    "Complete AMFI-mapped scheme list (75,000+ codes) and NAV histories from mfapi.in; scheme categorisation derived from AMFI naming."],
  ["What swaps in later",
    "The adapter-registry design means a broker feed (Dhan/Groww/Upstox/Angel One) can replace any source by registering a new adapter — routers and math never change."],
  ["Known free-feed limits",
    "NSE throttles aggressive clients: IPO central and occasional quotes may return nothing — the platform then labels the metric SOURCE-UNAVAILABLE rather than inventing data. Some REIT/InvIT trust units are not served by any free feed; they show as explicit unavailable rows, never fake ones."],
  ["Greeks & band math",
    "Black-Scholes Greeks, probability-of-touch bands, DCF, CAGR/vol/drawdown, SIP/SWP/LTCG and statutory-charge engines are all computed platform-side in Python (NumPy/SciPy)."],
];

export default function DataSourcesPage() {
  return <Legal title="Data Sources" updated="Current free-source stack" blocks={blocks} />;
}
