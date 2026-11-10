// Cloudflare Pages: every dynamic segment must render on the edge runtime.
// Route segment config cannot live in a `"use client"` page, so it is declared
// here in the (server) layout and inherited by the page below it.
import type { ReactNode } from "react";

export const runtime = "edge";

export default function SegmentLayout({ children }: { children: ReactNode }) {
  return children;
}
