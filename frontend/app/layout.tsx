import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Bharat Fintech Intelligence — India's Facts-First Market Database",
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
