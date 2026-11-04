"use client";

import { useParams } from "next/navigation";
import { ReitDetail } from "@/components/TrustDesk";

export default function TrustDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  return <ReitDetail symbol={symbol} />;
}
