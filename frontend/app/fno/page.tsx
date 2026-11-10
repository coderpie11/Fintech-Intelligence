import type { Metadata } from "next";
import FnoHub from "@/components/FnoHub";

export const metadata: Metadata = {
  title: "F&O Terminal | Fintech Intelligence",
  description:
    "Standalone derivatives terminal: live NSE option chains with max pain, futures 4-quadrant buildup, rollover, MWPL ban meter, physical-delivery alerts and a 4-leg expiry payoff builder.",
};

export default function FnoPage() {
  return <FnoHub />;
}
