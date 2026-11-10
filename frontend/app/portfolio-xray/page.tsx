import type { Metadata } from "next";
import PortfolioXRay from "@/components/PortfolioXRay";

export const metadata: Metadata = {
  title: "Portfolio X-Ray | Fintech Intelligence",
  description:
    "Manual holdings X-ray: asset allocation, look-through sector weights, cross-fund stock overlap and expense-ratio fee drag over 1/3/5/10 years.",
};

export default function PortfolioXRayPage() {
  return <PortfolioXRay />;
}
