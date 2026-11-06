# Fintech Intelligence

India's facts-first market database — equities, indices, F&O chains, IPOs,
mutual funds, ETFs, bonds, gold & silver, corporate events, REITs/InvITs,
a 4 PM market pulse, an AI-quant workspace and a full Market Academy.
Runs locally without Docker. Not a buy/sell recommendation.

## Run it (2 terminals)

**Terminal 1 — backend (FastAPI + SQLite, port 8000)**

```
cd backend
pip install -r requirements.txt   # once
python -m app.seed.seed           # one-time real-data seed (resumable)
python run.py                     # API on http://127.0.0.1:8000 (docs at /docs)
```

**Terminal 2 — frontend (Next.js, port 3000)**

```
cd frontend
npm install        # once
npm run dev        # site on http://localhost:3000
```

The frontend talks to the backend through the `/bff/...` rewrite in
`next.config.mjs` (backend on port 8001) — no CORS pain, no environment
variables needed locally.

## What is real right now

| Desk | What you get |
|---|---|
| Home | Live benchmark index strip, 12-month NIFTY chart, breadth mood line, movers |
| Indices | 18 NSE/BSE indices, live last/ohlc/52w, top-6 default + Expand All, click-through desks with constituents & F&O tab |
| Equities | 195 companies with NSE fundamentals (P/E, sector P/E, face value, m-cap, free-float, delivery %, 52w) + Yahoo-derived P/B, ROE, margins, EPS, beta, D/E |
| Stock detail | Full deep-dive: price book, 1/3/5y chart, CAGR/vol/drawdown stats, sector peers, own-DCF calculator with editable assumptions, F&O chain tab, one-click sandbox orders |
| F&O | Live NSE option chains for 6 indices option-able + stocks, PCR/OI support-resistance, platform-computed Greeks & POP (Black-Scholes) |
| IPOs | Honest feed status (free IPO central is heavily throttled; rows flow in when it answers, never fabricated) |
| Mutual funds | 38k AMFI schemes; NAV history + 1/3/5y stats for seeded majors; fund detail with charts, SIP calculator, same-AMC peers |
| ETFs | Same engine with ETF filter |
| Bonds & debt | G-Sec reference structure + YTM solver (bisection) |
| Gold & Silver | International spot, ₹/gram conversions incl. 22K derivation, 5y charts, vol/DD/CAGR |
| Events | Dividends/splits/bonus/buybacks from NSE corporate actions |
| REITs & InvITs | Trust table + SEBI 90% NDCA explanation; unknown-free-feed trusts shown as explicit unavailable rows |
| Market Pulse | The 4 PM x-ray: status, breadth, A/D ratio, sector flows, action items, index scoreboard |
| AI Quant | RangeCast statistical bands with touch probabilities (reflection principle), StreetPulse delivery-flow matrix |
| Academy | 5 tracks · 20 lessons, from "what is a share" to Greeks and open interest |
| Sandbox | Real CRUD paper trading: place/hold/close/delete orders at EOD marks, ₹10L virtual, P&L engine |
| Theme | Top-right toggle; dark = near-black instrument theme (gold accents), light = minimal 3-colour paper/ink/teal. No gradients anywhere |

## Guardrails kept in code

1. **Zero raw nulls** — every metric ships as `{value, status, note}`; the UI
   renders an explained reason instead of a bare dash.
2. **No fabricated data** — when a free source refuses, rows/metrics are
   labelled `SOURCE-UNAVAILABLE` with a Refresh button, never invented.
3. **Own computation** — exchanges only supply primitives; ratios, Greeks,
   bands, DCF and statutory charges are computed by this platform's engines.
4. **Adapter registry** — all sources sit behind `app/data`; broker feeds
   (Dhan/Groww/Upstox) replace them without touching routers or math.

## Refresh model

Every desk has a Refresh button hitting `POST /api/v1/refresh/{stage}` and a
nightly 18:30 IST scheduler re-runs stages. Seeding is resumable & idempotent.

> **This is a factual database and learning tool. It is not investment advice,
> not a buy/sell recommendation, and the operators are not SEBI-registered
> advisers. Consult a registered adviser before any real decision.**

© Kishlay Choudhary — Fintech Intelligence.
