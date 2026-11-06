export type NavItem = { label: string; href: string; key: string; desc?: string };

export type NavGroup = {
  key: string;
  label: string;
  items: NavItem[];
};

/** Grouped desktop navigation. Direct links sit beside the three menus. */
export const NAV_GROUPS: NavGroup[] = [
  {
    key: "markets",
    label: "Markets",
    items: [
      { label: "Indices", href: "/indices", key: "indices", desc: "Benchmarks, sectorals and India VIX" },
      { label: "Equities Desk", href: "/stocks", key: "stocks", desc: "2,400+ NSE companies, fundamentals and DCF" },
      { label: "IPOs", href: "/ipos", key: "ipos", desc: "Mainboard and SME issues" },
      { label: "Market Pulse 4 PM", href: "/market-pulse", key: "pulse", desc: "End-of-day breadth and flows" },
      { label: "Corporate Events", href: "/events", key: "events", desc: "Dividends, splits and board meetings" },
    ],
  },
  {
    key: "funds",
    label: "Funds & ETFs",
    items: [
      { label: "Mutual Funds", href: "/mutual-funds", key: "mf", desc: "All 38,000+ AMFI schemes" },
      { label: "ETFs", href: "/etfs", key: "etf", desc: "Exchange-traded funds and iNAV context" },
    ],
  },
  {
    key: "fixed",
    label: "Fixed Income & Real Assets",
    items: [
      { label: "Bonds & Debt", href: "/bonds", key: "bonds", desc: "G-Secs, YTM and dirty price" },
      { label: "Gold & Silver", href: "/commodities", key: "metals", desc: "Spot, ₹ conversion and SGBs" },
      { label: "REITs & InvITs", href: "/reits", key: "reits", desc: "Listed trusts and distribution yields" },
    ],
  },
];

export const NAV_DIRECT: NavItem[] = [
  { label: "AI Quant Hub", href: "/ai-quant-hub", key: "quant" },
  { label: "Calculators", href: "/calculators", key: "calculators" },
  { label: "Academy", href: "/learn", key: "academy" },
  { label: "Sandbox", href: "/sandbox", key: "sandbox" },
];

/** Flat list kept for search, mobile menus and cross-links. */
export const NAV_ITEMS: NavItem[] = [
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...NAV_DIRECT,
];
