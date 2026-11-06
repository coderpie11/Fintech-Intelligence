import Link from "next/link";
import { Legal } from "@/components/LegalPage";

const blocks: [string, string][] = [
  ["Nature of the service",
    "Fintech Intelligence is a factual market database and educational platform. It aggregates publicly available exchange and fund data, performs its own mathematical computations, and presents everything alongside explanation. It is not a broker, investment adviser, portfolio manager, or research analyst, and is not registered with SEBI for any advisory activity."],
  ["No advice",
    "Nothing on this platform — numbers, charts, scores, bands, calculators or AI-generated summaries — is investment advice or a buy/sell recommendation. Outputs are mathematical and historical, computed from user or platform inputs under stated assumptions. Decisions are entirely the user's."],
  ["Data accuracy",
    "Data is aggregated from public exchange and fund records and may be indicative or lag the latest session. While the platform validates and labels data status, absolute accuracy or completeness cannot be guaranteed. Always verify with the exchange or official filings before acting on any figure."],
  ["Sandbox",
    "The paper-trading sandbox uses virtual money only. Fills occur at end-of-day marks and do not reflect live microstructure, slippage or real-world execution."],
  ["Liability",
    "Use of the platform is at the user's own risk. Fintech Intelligence is not liable for losses arising from the use of, or decisions made on the basis of, platform content."],
];

export default function TermsPage() {
  return <Legal title="Terms of Use" updated="Effective: November 2026" blocks={blocks} />;
}
