"use client";

import { useParams } from "next/navigation";
import { IpoDetail } from "@/components/IpoDesk";

export default function IpoDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  return <IpoDetail slug={slug} />;
}
