import { Legal } from "@/components/LegalPage";

const blocks: [string, string][] = [
  ["Local-first by design",
    "Your paper-trading sandbox orders, watchlists and preferences are stored in your own local application database on your machine. This version of the platform does not transmit your personal data to any third party for marketing."],
  ["Data the platform fetches",
    "Market data is fetched from public exchanges and public fund feeds. These sources see requests coming from your machine when a refresh runs, and may log the request IP as with any web request."],
  ["Cookies & storage",
    "The platform uses browser localStorage to remember your theme choice. No advertising, tracking or analytics cookies are set in this build."],
  ["Future SaaS version",
    "If a hosted SaaS deployment launches later, its privacy policy will be published there, disclosing any account data collected — before that version exists, none of this applies."],
];

export default function PrivacyPage() {
  return <Legal title="Privacy Policy" updated="Effective: November 2026" blocks={blocks} />;
}
