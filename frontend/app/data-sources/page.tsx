import { Legal } from "@/components/LegalPage";

const blocks: [string, string][] = [
  ["Market data",
    "Exchange market status, index values, equity quotes, index constituents, option chains and corporate-action announcements are fetched through a resilient session client that handles exchange cookies and throttling."],
  ["Historical prices",
    "Daily OHLCV history for equities, indices, international gold/silver and USD/INR, used for charts, performance ladders and risk statistics."],
  ["Mutual funds & ETFs",
    "A complete AMFI-mapped scheme list (75,000+ codes) with NAV histories; scheme categorisation is derived from AMFI naming conventions."],
  ["Pluggable adapters",
    "The adapter-registry design means any upstream feed can be replaced by registering a new adapter — routers and math never change. Provider identities stay private inside the backend."],
  ["Unavailable data",
    "When an upstream feed throttles or omits a field, the platform labels that metric as unavailable rather than inventing a number. Some trust units are not served by any public feed and show as explicit unavailable rows."],
  ["Greeks & band math",
    "Black-Scholes Greeks, probability-of-touch bands, DCF, CAGR/vol/drawdown, SIP/SWP/LTCG and statutory-charge engines are all computed platform-side in Python (NumPy/SciPy)."],
];

export default function DataSourcesPage() {
  return <Legal title="Data Sources" updated="How the platform sources and computes data" blocks={blocks} />;
}
