"use client";

import { useParams } from "next/navigation";
import { FundDetail } from "@/components/FundsDesk";

export default function FundDetailPage() {
  const { code } = useParams<{ code: string }>();
  return <FundDetail code={code} />;
}
