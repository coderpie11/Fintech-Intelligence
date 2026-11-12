# Fintech Intelligence — India Market Research Terminal

[![CI](https://github.com/coderpie11/Fintech-Intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/coderpie11/Fintech-Intelligence/actions/workflows/ci.yml)

A local-first, facts-first market intelligence platform for Indian capital
markets. It unifies equities, indices, F&O, IPOs, mutual funds, ETFs, bonds,
commodities, REITs/InvITs, corporate events, a 4 PM market pulse, an AI-quant
workspace, a portfolio X-Ray and a 120-lesson Market Academy in one terminal.

Everything runs on your machine with **SQLite + FastAPI + Next.js**. There is no
Docker, PostgreSQL, Redis, Cloudflare tunnel or external queue in the runtime.

> Educational and analytical tool. Nothing in this repository is a buy/sell
> recommendation.

---

## 1. Project Overview & Institutional Architecture

The platform follows a three-layer design so a free data source can fail without
taking the product down:

```
Next.js 14 (App Router, TypeScript)
        │  /bff/* rewrite (same-origin, no CORS)
        ▼
FastAPI 0.122  ──  routers: indices, equities, fno, ipos, funds, etfs,
        │                    bonds, commodities, events, reits, pulse,
        │                    quant-hub, academy, sandbox, portfolio-xray, calc
        │
        ├── Services: calc (pure Python quant), fundamentals, live_quote,
        │             context envelopes, AI engines
        │
        ├── Adapters: NSE, Yahoo Finance, AMFI/mfapi, Groww, InvestorGain
        │             (each is swappable behind one module)
        │
        └── SQLite  backend/data/bfi.db
                   instruments · indexes · F&O snapshots · IPOs · funds ·
                   bonds · events · delivery stats · knowledge chunks ·
                   sandbox orders · watchlist · academy cache
```

**Design rules kept in code**

1. **Zero raw nulls** — metrics ship as `{value, status, note}`. The UI renders
   an explained reason instead of an unexplained dash.
2. **No fabricated data** — when a free source refuses, the row is labelled
   `SOURCE-UNAVAILABLE`; the platform shows a refresh path rather than inventing
   a number.
3. **Own computation** — exchanges supply primitives; Greeks, DCF, XIRR,
   statutory charges, overlap, fee drag and drawdown math are computed locally.
4. **Graceful degradation** — a live quote overlays a stored snapshot; if the
   overlay fails the snapshot still paints, labelled with its source date.
5. **Local-first by construction** — one SQLite file, two local processes, no
   infrastructure dependency.

---

## 2. Tech Stack & Local Run Instructions

### Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Pydantic 2, Uvicorn |
| Quant | NumPy, SciPy, pandas + the platform's own pure-Python `calc.py` |
| Data | SQLite (`backend/data/bfi.db`), adapters for NSE / Yahoo / AMFI / Groww / InvestorGain |
| Frontend | Next.js 14 App Router, React 18, TypeScript 5.5, Tailwind CSS |
| AI | Local-first RAG corpus + three-tier LLM failover (Gemini → Groq → OpenRouter) |
| Tests | pytest + FastAPI TestClient |

Pinned runtime versions live in `backend/requirements.txt`. Test tooling is in
`backend/requirements-dev.txt`.

### Run it (two terminals)

**Terminal 1 — backend (port 8001)**

```bash
cd backend
python -m pip install -r requirements.txt
python -m app.seed.seed          # one-time / resumable real-data seed
python run.py                    # http://127.0.0.1:8001  (docs at /docs)
```

**Terminal 2 — frontend (port 3000)**

```bash
cd frontend
npm install
npm run dev                      # http://127.0.0.1:3000
```

The Next rewrite `/bff/:path* → http://127.0.0.1:8001/:path*` keeps the browser
on one origin. No environment variables are required for the local default.

### Tests and production build

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q              # 49 tests, 100% pass

cd ../frontend
npx tsc --noEmit                 # type-check
npm run build                    # production build
npm run start                    # serve the built app on :3000
```

Health checks:

```bash
curl http://127.0.0.1:8001/api/v1/health   # {"status":"ok", ...}
curl http://127.0.0.1:3000                  # HTTP 200
```

---

## 3. Complete Module & Quantitative Engine Breakdown

### Market desks

| Module | What it does |
|---|---|
| **Home** | Benchmark strip, 12-month NIFTY chart, breadth mood, movers |
| **Indices** | 18 NSE/BSE indices, live last/OHLC/52-week, constituents, F&O tab, GIFT Nifty + ADR pre-market strip, India VIX ranges |
| **Equities** | 195+ companies with NSE fundamentals, sector P/E, delivery %, free-float, peer sets, 1/3/5-year stats, own DCF |
| **F&O Terminal** | Option chain with platform Greeks/POP, max pain, futures 4-quadrant/rollover, MWPL 95% meter and official ban-list state, delivery-margin traps, 4-leg payoff builder |
| **IPOs** | Mainboard/SME archive, GMP, subscription, anchor lock-in countdown, BRLM track record, pre-IPO unlisted comparison, DRHP/RHP context |
| **Mutual Funds** | 38k AMFI schemes, NAV history, 1/3/5-year metrics, monthly churn (additions/exits/increases/trims), two-tier AI reason engine, SIP/SWP/LTCG calculators |
| **ETFs** | Curated universe, tracking error, premium/discount, live iNAV deviation, impact-cost and liquidity scanner |
| **Bonds** | G-Sec / T-Bill / SDL / corporate structure, YTM solver, clean-vs-dirty price, fixed-vs-floating comparison |
| **Gold & Silver** | International spot, INR per gram/10 g, 22K derivation, gold/silver ratio, SGB view |
| **REITs & InvITs** | Trust table, occupancy/WALE/cap rate/debt-to-GAV, 90% NDCF rule, distribution calculator |
| **Events** | Dividends, splits, bonuses, buybacks, demergers, board meetings from NSE corporate actions |
| **Market Pulse** | 4 PM breadth, A/D ratio, sector money flow, volume/delivery shockers, action items |
| **AI Quant Hub** | RangeCast probabilistic bands, StreetPulse delivery matrix, 4 PM X-Ray, Ask Dalal grounded RAG |
| **Portfolio X-Ray** | Manual holdings parser, allocation/sector look-through, cross-fund overlap matrix, TER fee drag over 1/3/5/10 years |
| **Market Academy** | 13 tracks / 120 lessons, including six advanced forensic masterclasses |
| **Sandbox** | Real CRUD paper trading with session-isolated books, ₹10,00,000 virtual cash, charges engine, watchlist |

### Quantitative engines (`backend/app/services/calc.py` + peers)

- **Black-Scholes-Merton** — call/put premium, delta, gamma, theta, vega,
  probability of profit.
- **DCF & reverse DCF** — two-stage FCFF model with explicit and terminal value
  split; reverse solver for implied growth.
- **Net-in-the-pocket** — STT, NSE turnover charge (0.00297%), SEBI fee, stamp
  duty, DP charge and 18% GST for delivery trades; separate F&O charge engine.
- **Returns** — CAGR, XIRR (bisection), rolling returns, annualised volatility,
  maximum drawdown, tracking error.
- **Piotroski F-Score** — nine fundamental signals; unavailable inputs are
  excluded from the denominator rather than counted as failures.
- **Altman Z-Score** — sector-aware variant, with a bank-specific path.
- **Index P/E** — harmonic, free-float-weight-weighted member P/E.
- **Bond YTM** — bisection solver, accrued interest, clean/dirty price.
- **Portfolio X-Ray** — `sum(min(weight))` cross-fund overlap, aggregate stock
  exposure and compounded fee-drag opportunity cost.
- **Market structure** — India VIX daily/weekly/monthly ranges, GIFT Nifty gap
  chain, max pain, MWPL ban-list state, rollover quadrant.

### AI layer

- Local RAG corpus built from stored annual statements, filings and DRHP fields.
- Text-to-SQL and document search are grounded in SQLite; the model never
  invents a price.
- Three-tier failover with a live probe, cached health state and a failover
  latency metric. When no provider answers, the UI says so.

---

## 4. Verified Performance Benchmarks

Measured in-process on the reference local build (Windows, Python 3.13,
warm SQLite page cache, median of 25 runs):

| Operation | Median | Min | Max |
|---|---:|---:|---:|
| Academy synonym search (`/academy/search`) | **4.6 ms** | 3.7 ms | 6.1 ms |
| Portfolio X-Ray analyze (4 holdings, overlap + fee drag) | **10.9 ms** | 8.0 ms | 12.6 ms |
| DCF / BSM / XIRR pure functions | sub-millisecond | — | — |
| Route smoke suite (49 tests, full app lifespan) | **23.8 s total** | — | — |

Both interactive paths sit comfortably inside the project target of **<20 ms for
search** and **<31 ms for a portfolio X-Ray**. The global multi-source search is
intentionally slower when it has to reach Yahoo for an unknown symbol; local
hits stay on the fast path.

---

## 5. Repository Structure

```
.
├── README.md
├── .env                         # local API keys (git-ignored values)
├── backend
│   ├── run.py                   # uvicorn launcher, 127.0.0.1:8001
│   ├── requirements.txt         # pinned runtime
│   ├── requirements-dev.txt     # pytest
│   ├── data/bfi.db              # local SQLite store (git-ignored)
│   ├── tests
│   │   ├── conftest.py          # offline adapter stubs + TestClient
│   │   ├── test_quant.py        # BSM, DCF, charges, XIRR, Piotroski
│   │   └── test_routes.py       # 16-module API contract suite
│   └── app
│       ├── main.py              # FastAPI assembly + lifespan
│       ├── core/                # config, SQLite session, migrations
│       ├── models/              # SQLAlchemy models
│       ├── seed/                # universe + resumable seeding
│       ├── data/adapters/       # NSE, Yahoo, AMFI, Groww, InvestorGain
│       ├── services/            # calc, fundamentals, live_quote, AI engines
│       └── routes/              # 16 routers under /api/v1
└── frontend
    ├── app/                     # App Router pages (stocks, fno, ipos, …)
    ├── components/              # desk UIs, charts, lesson cards, kit
    ├── lib/                     # api client, formatters, nav, types
    └── next.config.mjs          # /bff rewrite + legacy redirects
```

### Honest limitations

- Free NSE/Yahoo/AMFI feeds are throttled and occasionally unavailable; rows
  remain visible with an explicit source status.
- GIFT Nifty has no free live ticker on this account, so the gap engine labels
  the NSE NIFTY futures proxy or a cost-of-carry model instead of pretending.
- MWPL is not published contract-wise on the free feed; the 95% meter shows the
  official ban-list state rather than inventing utilisation.
- Fund holdings and TERs come from disclosed monthly portfolios and lag by up to
  a month.
- The paper-trading sandbox never touches a broker or a real order book.

---

## Verification

The 4 PM Market X-Ray and StreetPulse Matrix are the two surfaces most likely to
go half-empty: they depend on a sector taxonomy that is NULL for most of the
universe and on a NSE flow feed that blocks datacenter IPs. Both now fail loudly
instead of silently.

```bash
# In-process: asserts the whole payload contract from the stored snapshot
python backend/scripts/verify_xray.py

# Against any running instance (stdlib only; waits for a cold deploy to wake)
python backend/scripts/verify_xray.py --url https://<host> --attempts 10 --wait 30
```

The check covers, for ALL SECTORS and each of the six sector pills:

- Step 1 carries non-null FII and DII net, buy and sell legs, and a combined
  net — including when NSE returns 403 (simulated on every offline run).
- The status badge is never `WARMING UP` and the summary has all 4 bullets.
- No stock is left in the old `Diversified` bucket.
- Leaders and laggards each have >= 3 sectors above ₹100 Cr turnover.
- Every pill has >= 5 Step 3 rows and >= 1 volume shocker.
- Step 4 has >= 5 grounded context cards and a populated index tape.

`.github/workflows/ci.yml` runs the tests, the offline contract check, the
frontend typecheck and build, and then — on `main` only — the same contract
check against the live Render deployment once it settles.

---

## License

Private research project. Add a license before publishing publicly.
