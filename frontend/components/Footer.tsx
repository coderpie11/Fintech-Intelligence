import Link from "next/link";
import DisclaimerBand from "./DisclaimerBand";

export default function Footer() {
  return (
    <footer className="mt-16 border-t border-rule" style={{ borderColor: "var(--line)" }}>
      <div className="mx-auto max-w-[1600px] px-6 py-10 grid gap-10 md:grid-cols-3">
        <div>
          <div className="text-[15px] font-black mb-2">
            Bharat Fintech<span className="accent"> Intelligence</span>
          </div>
          <p className="muted text-[12.5px] leading-relaxed">
            An Indian capitals-markets India encyclopedia: equities, indices,
            derivatives, IPOs, mutual funds, ETFs, bonds, metals, REITs and
            market pulses — facts, math and education, computed on our own
            engine for free public sources.
          </p>
          <div className="mt-4">
            <DisclaimerBand />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] muted mb-3">
              Explore
            </div>
            <ul className="space-y-2 text-[13px]">
              <li><Link className="hover:opacity-75" href="/indices">Indices</Link></li>
              <li><Link className="hover:opacity-75" href="/stocks">Equities</Link></li>
              <li><Link className="hover:opacity-75" href="/ipos">IPO</Link></li>
              <li><Link className="hover:opacity-75" href="/mutual-funds">Mutual Funds</Link></li>
              <li><Link className="hover:opacity-75" href="/etfs">ETF</Link></li>
              <li><Link className="hover:opacity-75" href="/bonds">Bonds &amp; Debt</Link></li>
              <li><Link className="hover:opacity-75" href="/gold-silver">Gold &amp; Silver</Link></li>
              <li><Link className="hover:opacity-75" href="/events">Corporate Events</Link></li>
              <li><Link className="hover:opacity-75" href="/reits">REITs</Link></li>
              <li><Link className="hover:opacity-75" href="/market-pulse">Market Pulse</Link></li>
              <li><Link className="hover:opacity-75" href="/ai-quant-hub">AI Quant</Link></li>
              <li><Link className="hover:opacity-75" href="/learn">Academy</Link></li>
            </ul>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] muted mb-3">
              Legal
            </div>
            <ul className="space-y-2 text-[13px]">
              <li><Link className="hover:opacity-75" href="/terms">Terms of Use</Link></li>
              <li><Link className="hover:opacity-75" href="/privacy">Privacy Policy</Link></li>
              <li><Link className="hover:opacity-75" href="/data-sources">Data Sources</Link></li>
              <li><Link className="hover:opacity-75" href="/contact">Contact</Link></li>
            </ul>
          </div>
        </div>

        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.18em] muted mb-3">
            Built by
          </div>
          <p className="text-[13.5px] font-semibold">Kishlay Choudhary</p>
          <p className="muted text-[12.5px] mt-1 leading-relaxed">
            Design, architecture and code — © {new Date().getFullYear()} Bharat
            Fintech Intelligence. All rights reserved.
          </p>
          <p
            className="blink-red text-[12px] font-extrabold mt-4"
            style={{ color: "var(--down)" }}
          >
            Not a buy or sell recommendation. Educational &amp; research use only.
          </p>
        </div>
      </div>
      <div
        className="border-t text-center py-3 muted text-[11.5px]"
        style={{ borderColor: "var(--line)" }}
      >
        Free public sources: NSE · BSE · AMFI/mfapi.in · Yahoo Finance — end-of-day or delayed data.
        &nbsp;F&amp;O Greeks computed platform-side.
      </div>
    </footer>
  );
}
