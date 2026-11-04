"use client";

import { useParams } from "next/navigation";
import { EtfDetail } from "@/components/EtfDesk";

export default function EtfDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  return <EtfDetail symbol={symbol} />;
}
