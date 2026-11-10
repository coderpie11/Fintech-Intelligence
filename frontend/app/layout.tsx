import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

// Cloudflare Pages: render the whole App Router tree on the edge runtime.
// Static segments are still prerendered at build time; this only decides the
// runtime for anything evaluated on request (e.g. dynamic segments, 404).
export const runtime = "edge";

export const metadata: Metadata = {
  title: "Fintech Intelligence — India's Facts-First Market Database",
  description:
    "Institutional-grade Indian market encyclopedia: equities, indices, F&O, IPOs, mutual funds, ETFs, bonds, gold, silver, REITs and education. Not a buy/sell recommendation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("bfi-theme")||"dark";document.documentElement.classList.toggle("dark",t==="dark");}catch(e){}})();`,
          }}
        />
      </head>
      <body>
        <Navbar />
        <main className="pt-[62px] min-h-screen">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
