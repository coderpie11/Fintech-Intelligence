import { Legal } from "@/components/LegalPage";
import MetricTip from "@/components/MetricTip";

export default function ContactPage() {
  return (
    <div className="max-w-[900px] mx-auto px-6 pt-12 pb-16">
      <h1 className="text-[34px] font-black tracking-tight mt-8">Contact</h1>
      <div className="card p-6 mt-6 text-[13.5px] leading-relaxed">
        <p className="font-bold">Built by Kishlay Choudhary</p>
        <p className="muted mt-2">
          Feedback, data corrections, and licence enquiries about the platform:
          raise issues in the project repository or reach out through the
          deployment owner once the site is on its public domain.
        </p>
        <p className="muted mt-4">
          The platform is a{" "}
          <MetricTip label="Facts database" tip={{
            meaning: "A system that stores, computes and explains public Indian-market data. It does not choose securities for you and does not execute trades.",
          }}>facts database</MetricTip>
          . It cannot and will not respond to
          “which stock should I buy” questions — that is by design, not rudeness.
        </p>
      </div>
    </div>
  );
}
