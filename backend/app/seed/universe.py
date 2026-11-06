"""Static factual universe definitions (slug maps, board lists). These are
reference constants — the actual live values/constituents are always fetched
from the exchanges at seed time.

`yahoo` tickers below were verified live against Yahoo Finance on this machine.
`fallback_names` are the exact row labels in NSE's official daily index
snapshot archive (used only when Yahoo has no multi-year series).
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

INDICES: list[dict] = [
    {"slug": "nifty-50", "nse": "NIFTY 50", "display": "NIFTY 50", "yahoo": "^NSEI",
     "group": "Benchmark", "top6": True, "fno": "NIFTY",
     "about": "The NIFTY 50 tracks the 50 largest and most liquid companies on the NSE across 14 sectors — the primary benchmark of Indian large caps."},
    {"slug": "sensex", "nse": "SENSEX", "display": "SENSEX", "yahoo": "^BSESN",
     "group": "Benchmark", "top6": True, "fno": "SENSEX",
     "about": "The BSE SENSEX tracks 30 large, financially sound and well-established companies listed on the BSE — India's oldest live benchmark, first published in 1986."},
    {"slug": "bank-nifty", "nse": "NIFTY BANK", "display": "BANK NIFTY", "yahoo": "^NSEBANK",
     "group": "Sectoral", "top6": True, "fno": "BANKNIFTY",
     "about": "NIFTY BANK captures the performance of the most liquid banking stocks — public sector titans and large private banks."},
    {"slug": "nifty-next-50", "nse": "NIFTY NEXT 50", "display": "NIFTY NEXT 50", "yahoo": "^NSMIDCP",
     "group": "Broad", "top6": True, "fno": "NIFTYNXT50",
     "about": "NIFTY NEXT 50 holds the next tranche of large caps after the NIFTY 50 — India's future heavyweight candidates."},
    {"slug": "nifty-fin-service", "nse": "NIFTY FIN SERVICE", "display": "NIFTY FIN SERVICE",
     "yahoo": "NIFTY_FIN_SERVICE.NS", "group": "Sectoral", "top6": True, "fno": "FINNIFTY",
     "nse_alias": "NIFTY FINANCIAL SERVICES",
     "about": "NIFTY FIN SERVICE covers financial services companies beyond pure banks: insurers, exchanges, NBFCs and housing finance."},
    {"slug": "nifty-midcap-100", "nse": "NIFTY MIDCAP 100", "display": "NIFTY MIDCAP 100",
     "yahoo": "NIFTY_MIDCAP_100.NS", "group": "Broad", "top6": True, "fno": "MIDCPNIFTY",
     "fallback_names": ["NIFTY Midcap 100"],
     "about": "NIFTY MIDCAP 100 represents the middle tier of the market — companies past startup risk but below heavyweight scale."},
    {"slug": "nifty-smallcap-100", "nse": "NIFTY SMALLCAP 100", "display": "NIFTY SMALLCAP 100",
     "yahoo": "^CNXSC", "group": "Broad", "top6": False,
     "fallback_names": ["NIFTY Smallcap 100"],
     "about": "NIFTY SMALLCAP 100 tracks the 100 most liquid small-cap companies on the NSE."},
    {"slug": "india-vix", "nse": "INDIA VIX", "display": "INDIA VIX", "yahoo": "^INDIAVIX",
     "group": "Volatility", "top6": False, "fno": "INDIAVIX",
     "about": "INDIA VIX is the market's implied-volatility gauge computed from NIFTY option prices — rising VIX signals rising fear."},
    {"slug": "nifty-it", "nse": "NIFTY IT", "display": "NIFTY IT", "yahoo": "^CNXIT",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY IT tracks the largest Indian information-technology and software-services companies."},
    {"slug": "nifty-fmcg", "nse": "NIFTY FMCG", "display": "NIFTY FMCG", "yahoo": "^CNXFMCG",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY FMCG covers fast-moving consumer goods — staples, personal care and household products."},
    {"slug": "nifty-pharma", "nse": "NIFTY PHARMA", "display": "NIFTY PHARMA", "yahoo": "^CNXPHARMA",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY PHARMA tracks domestic formulation and generic-export pharmaceutical companies."},
    {"slug": "nifty-auto", "nse": "NIFTY AUTO", "display": "NIFTY AUTO", "yahoo": "^CNXAUTO",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY AUTO covers passenger vehicles, two-wheelers, commercial vehicles and auto components."},
    {"slug": "nifty-metal", "nse": "NIFTY METAL", "display": "NIFTY METAL", "yahoo": "^CNXMETAL",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY METAL tracks ferrous and non-ferrous metal producers and mining companies."},
    {"slug": "nifty-realty", "nse": "NIFTY REALTY", "display": "NIFTY REALTY", "yahoo": "^CNXREALTY",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY REALTY covers listed real-estate developers and related businesses."},
    {"slug": "nifty-energy", "nse": "NIFTY ENERGY", "display": "NIFTY ENERGY", "yahoo": "^CNXENERGY",
     "group": "Sectoral", "top6": False,
     "about": "NIFTY ENERGY tracks oil, gas, power and energy-utility companies."},
    {"slug": "nifty-infrastructure", "nse": "NIFTY INFRASTRUCTURE", "display": "NIFTY INFRASTRUCTURE",
     "yahoo": "^CNXINFRA", "group": "Thematic", "top6": False,
     "about": "NIFTY INFRASTRUCTURE captures companies building and operating India's physical infrastructure."},
    {"slug": "nifty-pse", "nse": "NIFTY PSE", "display": "NIFTY PSE", "yahoo": "^CNXPSE",
     "group": "Thematic", "top6": False,
     "about": "NIFTY PSE tracks public-sector enterprises across sectors."},
    {"slug": "nifty-consumption", "nse": "NIFTY INDIA CONSUMPTION", "display": "NIFTY INDIA CONSUMPTION",
     "yahoo": "^CNXCONSUM", "group": "Thematic", "top6": False,
     "about": "NIFTY INDIA CONSUMPTION tracks companies that benefit from domestic consumption growth."},
]

# BSE SENSEX membership (factual constituent list, reviewed 2025-26).
# Weights are NOT official BSE weights: they are derived estimates from free-
# float market cap and are labelled as such in the API/UI.
SENSEX_MEMBERS = [
    "ADANIPORTS", "ASIANPAINT", "AXISBANK", "BAJFINANCE", "BAJAJFINSV",
    "BHARTIARTL", "HCLTECH", "HDFCBANK", "HINDUNILVR", "ICICIBANK",
    "INDUSINDBK", "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "NESTLEIND", "NTPC", "POWERGRID", "RELIANCE", "SBIN",
    "SUNPHARMA", "TATAMOTORS", "TCS", "TECHM", "TITAN", "ULTRACEMCO", "WIPRO",
]

# Real REITs and InvITs listed on NSE (factual ticker spellings).
# `no_free_feed` entries are known trusts whose units are not served by any
# free source on this machine — shown honestly as unavailable rows.
REITS = [("EMBASSY", "Embassy Office Parks REIT", "REIT"),
         ("BIRET", "Brookfield India Real Estate Trust", "REIT"),
         ("MINDSPACE", "Mindspace Business Parks REIT", "REIT"),
         ("NXST", "Nexus Select Trust", "REIT")]
REITS_NO_FREE_FEED = set()
INVITS = [("IRBINVIT", "IRB InvIT Fund", "INVIT"),
          ("INDIGRID", "IndiGrid Infrastructure Trust", "INVIT"),
          ("PGINVIT", "PowerGrid Infrastructure Trust", "INVIT")]

# Reference G-Secs (coupon and maturity are statutory facts; YTM is ticked live
# from free proxies when available at runtime).
BONDS = [
    {"name": "7.10% GS 2034", "kind": "G-SEC", "coupon": 7.10, "face_value": 100, "maturity": "2034-04-08"},
    {"name": "6.79% GS 2027", "kind": "G-SEC", "coupon": 6.79, "face_value": 100, "maturity": "2027-05-15"},
    {"name": "7.26% GS 2032", "kind": "G-SEC", "coupon": 7.26, "face_value": 100, "maturity": "2032-08-18"},
    {"name": "7.18% GS 2033", "kind": "G-SEC", "coupon": 7.18, "face_value": 100, "maturity": "2033-08-14"},
    {"name": "7.45% GS 2040", "kind": "G-SEC", "coupon": 7.45, "face_value": 100, "maturity": "2040-08-27"},
    {"name": "6.83% GS 2039", "kind": "G-SEC", "coupon": 6.83, "face_value": 100, "maturity": "2039-03-28"},
]

COMMODITIES = [
    {"slug": "gold", "name": "Gold", "kind": "COMMODITY", "yahoo": "GC=F", "unit": "USD/oz",
     "detail": "International front-month spot reference; MCX prices differ with FX and premia."},
    {"slug": "silver", "name": "Silver", "kind": "COMMODITY", "yahoo": "SI=F", "unit": "USD/oz",
     "detail": "International front-month spot reference; MCX prices differ with FX and premia."},
]

ETF_PATTERNS = r"(bees|beetf|etf\b|mon100|juniorbees|bankbees|goldbees|silverbees|liquidbees)"

# Curated, factual NSE-listed ETFs. `category` is one of the ten clean buckets
# used by the ETF Desk dropdown. `benchmark` is the NSE index symbol used for
# tracking-error maths; `proxy` flags an approximate benchmark; `no_bench`
# means no honest benchmark exists on a free feed.
ETF_UNIVERSE = [
    # ---- Silver (11) -------------------------------------------------------
    {"symbol": "SILVERBEES", "name": "Nippon India Silver BeES", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.55,
     "about": "India's largest silver ETF; backed by physical silver held in vaults."},
    {"symbol": "SILVERIETF", "name": "ICICI Prudential Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.55,
     "about": "Tracks domestic silver prices with physical silver backing."},
    {"symbol": "HDFCSILVER", "name": "HDFC Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "HDFC Mutual Fund", "ter_pct": 0.59,
     "about": "Physical silver ETF tracking the domestic silver benchmark."},
    {"symbol": "AXISSILVER", "name": "Axis Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Axis Mutual Fund", "ter_pct": 0.45,
     "about": "Low-cost physical silver ETF from Axis Mutual Fund."},
    {"symbol": "KOTAKSILVE", "name": "Kotak Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Kotak Mahindra Mutual Fund", "ter_pct": 0.49,
     "about": "Physical silver ETF tracking domestic silver prices."},
    {"symbol": "SBISILVER", "name": "SBI Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "SBI Mutual Fund", "ter_pct": 0.55,
     "about": "SBI's physical silver ETF for domestic silver exposure."},
    {"symbol": "UTISILVER", "name": "UTI Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "UTI Mutual Fund", "ter_pct": 0.55,
     "about": "UTI physical silver ETF tracking the domestic silver benchmark."},
    {"symbol": "ABSLSILVER", "name": "Aditya Birla Sun Life Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Aditya Birla Sun Life Mutual Fund", "ter_pct": 0.55,
     "about": "Physical silver ETF from Aditya Birla Sun Life Mutual Fund."},
    {"symbol": "DSPSILVER", "name": "DSP Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "DSP Mutual Fund", "ter_pct": 0.55,
     "about": "DSP physical silver ETF tracking domestic silver prices."},
    {"symbol": "TATASILVER", "name": "Tata Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Tata Mutual Fund", "ter_pct": 0.55,
     "about": "Tata physical silver ETF for domestic silver exposure."},
    {"symbol": "SILVRETF", "name": "Mirae Asset Silver ETF", "category": "Silver",
     "benchmark": "SILVER_INR_PROXY", "issuer": "Mirae Asset Mutual Fund", "ter_pct": 0.49,
     "about": "Mirae Asset physical silver ETF tracking the domestic benchmark."},

    # ---- Gold (8) ----------------------------------------------------------
    {"symbol": "GOLDBEES", "name": "Nippon India Gold BeES", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.79,
     "about": "India's largest gold ETF; backed by physical gold held by the fund."},
    {"symbol": "SETFGOLD", "name": "SBI Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "SBI Mutual Fund", "ter_pct": 0.55,
     "about": "SBI's physical gold ETF tracking domestic gold prices."},
    {"symbol": "HDFCGOLD", "name": "HDFC Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "HDFC Mutual Fund", "ter_pct": 0.59,
     "about": "HDFC physical gold ETF for domestic gold exposure."},
    {"symbol": "GOLDIETF", "name": "ICICI Prudential Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.49,
     "about": "ICICI Prudential physical gold ETF tracking domestic gold prices."},
    {"symbol": "KOTAKGOLD", "name": "Kotak Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "Kotak Mahindra Mutual Fund", "ter_pct": 0.49,
     "about": "Kotak physical gold ETF tracking the domestic gold benchmark."},
    {"symbol": "AXISGOLD", "name": "Axis Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "Axis Mutual Fund", "ter_pct": 0.45,
     "about": "Axis physical gold ETF with a low indicative expense ratio."},
    {"symbol": "QGOLDHALF", "name": "Quantum Gold Fund (Half Unit)", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "Quantum Mutual Fund", "ter_pct": 0.49,
     "about": "Quantum's physical gold fund, quoted in half-unit denominations."},
    {"symbol": "BSLGOLDETF", "name": "Aditya Birla Sun Life Gold ETF", "category": "Gold",
     "benchmark": "GOLD_INR_PROXY", "issuer": "Aditya Birla Sun Life Mutual Fund", "ter_pct": 0.55,
     "about": "Aditya Birla Sun Life physical gold ETF."},

    # ---- Nifty 50 & broad index (5) ---------------------------------------
    {"symbol": "NIFTYBEES", "name": "Nippon India Nifty 50 BeES", "category": "Nifty 50",
     "benchmark": "NIFTY 50", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.04,
     "about": "India's largest ETF by assets; tracks the NIFTY 50 Total Return Index."},
    {"symbol": "SETFNIF50", "name": "SBI Nifty 50 ETF", "category": "Nifty 50",
     "benchmark": "NIFTY 50", "issuer": "SBI Mutual Fund", "ter_pct": 0.05,
     "about": "Tracks the NIFTY 50; one of the largest index ETFs in India."},
    {"symbol": "ICICINIFTY", "name": "ICICI Prudential Nifty 50 ETF", "category": "Nifty 50",
     "benchmark": "NIFTY 50", "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the NIFTY 50 large-cap benchmark."},
    {"symbol": "HDFCNIFTY", "name": "HDFC Nifty 50 ETF", "category": "Nifty 50",
     "benchmark": "NIFTY 50", "issuer": "HDFC Mutual Fund", "ter_pct": 0.20,
     "about": "HDFC's NIFTY 50 index ETF."},
    {"symbol": "KOTAKNIFTY", "name": "Kotak Nifty 50 ETF", "category": "Nifty 50",
     "benchmark": "NIFTY 50", "issuer": "Kotak Mahindra Mutual Fund", "ter_pct": 0.20,
     "about": "Kotak's NIFTY 50 index ETF."},

    # ---- Midcap & Next 50 (5) ---------------------------------------------
    {"symbol": "JUNIORBEES", "name": "Nippon India Nifty Next 50 Junior BeES", "category": "Mid & Next 50",
     "benchmark": "NIFTY NEXT 50", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the NIFTY Next 50 — the 50 large caps immediately below the NIFTY 50."},
    {"symbol": "NEXT50IETF", "name": "ICICI Prudential Nifty Next 50 ETF", "category": "Mid & Next 50",
     "benchmark": "NIFTY NEXT 50", "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the NIFTY Next 50 index."},
    {"symbol": "MID150BEES", "name": "Nippon India Nifty Midcap 150 ETF", "category": "Mid & Next 50",
     "benchmark": "NIFTY MIDCAP 100", "proxy": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.30,
     "about": "Tracks the NIFTY Midcap 150; NIFTY Midcap 100 is used as a proxy benchmark."},
    {"symbol": "HDFCMID150", "name": "HDFC Nifty Midcap 150 ETF", "category": "Mid & Next 50",
     "benchmark": "NIFTY MIDCAP 100", "proxy": True, "issuer": "HDFC Mutual Fund", "ter_pct": 0.30,
     "about": "HDFC's NIFTY Midcap 150 ETF; proxy benchmark is NIFTY Midcap 100."},
    {"symbol": "MOM100", "name": "Motilal Oswal Nifty Midcap 100 ETF", "category": "Mid & Next 50",
     "benchmark": "NIFTY MIDCAP 100", "issuer": "Motilal Oswal Mutual Fund", "ter_pct": 0.30,
     "about": "Tracks the NIFTY Midcap 100 index."},

    # ---- Sensex (5) --------------------------------------------------------
    {"symbol": "SENSEXBEES", "name": "Nippon India Sensex ETF", "category": "Sensex",
     "benchmark": "SENSEX", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the BSE SENSEX of 30 large, established companies."},
    {"symbol": "BSLSENETFG", "name": "Aditya Birla Sun Life Sensex ETF", "category": "Sensex",
     "benchmark": "SENSEX", "issuer": "Aditya Birla Sun Life Mutual Fund", "ter_pct": 0.20,
     "about": "Aditya Birla Sun Life's SENSEX index ETF."},
    {"symbol": "SETFSENSEX", "name": "SBI Sensex ETF", "category": "Sensex",
     "benchmark": "SENSEX", "issuer": "SBI Mutual Fund", "ter_pct": 0.20,
     "about": "SBI's SENSEX index ETF."},
    {"symbol": "ICICISENSX", "name": "ICICI Prudential Sensex ETF", "category": "Sensex",
     "benchmark": "SENSEX", "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.20,
     "about": "ICICI Prudential's SENSEX index ETF."},
    {"symbol": "HDFCSENSEX", "name": "HDFC Sensex ETF", "category": "Sensex",
     "benchmark": "SENSEX", "issuer": "HDFC Mutual Fund", "ter_pct": 0.20,
     "about": "HDFC's SENSEX index ETF."},

    # ---- Banking & financial (2) ------------------------------------------
    {"symbol": "BANKBEES", "name": "Nippon India Nifty Bank BeES", "category": "Banking",
     "benchmark": "NIFTY BANK", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.19,
     "about": "Tracks the NIFTY BANK index of India's most liquid banking stocks."},
    {"symbol": "PVTBANIETF", "name": "ICICI Prudential Nifty Private Bank ETF", "category": "Banking",
     "benchmark": "NIFTY FIN SERVICE", "proxy": True, "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the NIFTY Private Bank index; NIFTY Financial Services is a proxy benchmark."},

    # ---- IT & sectoral (5) -------------------------------------------------
    {"symbol": "ITBEES", "name": "Nippon India Nifty IT BeES", "category": "IT & Sectoral",
     "benchmark": "NIFTY IT", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.22,
     "about": "Tracks the NIFTY IT index of large Indian software-services companies."},
    {"symbol": "PHARMABEES", "name": "Nippon India Nifty Pharma BeES", "category": "IT & Sectoral",
     "benchmark": "NIFTY PHARMA", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.22,
     "about": "Tracks the NIFTY Pharma index of domestic and export pharma companies."},
    {"symbol": "AUTOBEES", "name": "Nippon India Nifty Auto BeES", "category": "IT & Sectoral",
     "benchmark": "NIFTY AUTO", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.22,
     "about": "Tracks the NIFTY Auto index across vehicles and components."},
    {"symbol": "INFRABEES", "name": "Nippon India Nifty Infrastructure BeES", "category": "IT & Sectoral",
     "benchmark": "NIFTY INFRASTRUCTURE", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.22,
     "about": "Tracks the NIFTY Infrastructure index."},
    {"symbol": "CONSUMBEES", "name": "Nippon India Nifty India Consumption BeES", "category": "IT & Sectoral",
     "benchmark": "NIFTY INDIA CONSUMPTION", "issuer": "Nippon India Mutual Fund", "ter_pct": 0.22,
     "about": "Tracks the NIFTY India Consumption index."},

    # ---- PSU & CPSE (3) ----------------------------------------------------
    {"symbol": "PSUBNKBEES", "name": "Nippon India Nifty PSU Bank BeES", "category": "PSU",
     "benchmark": None, "no_bench": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.20,
     "about": "Tracks the NIFTY PSU Bank index of public-sector banks."},
    {"symbol": "CPSEETF", "name": "CPSE ETF", "category": "PSU",
     "benchmark": "NIFTY PSE", "proxy": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.07,
     "about": "Tracks the NIFTY CPSE index of central public-sector enterprises; NIFTY PSE is a proxy."},
    {"symbol": "ICICIB22", "name": "ICICI Prudential Bharat 22 ETF", "category": "PSU",
     "benchmark": None, "no_bench": True, "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.10,
     "about": "Tracks the BSE Bharat 22 index of CPSEs, PSBs and strategic holdings."},

    # ---- International (3) -------------------------------------------------
    {"symbol": "MON100", "name": "Motilal Oswal Nasdaq 100 ETF", "category": "International",
     "benchmark": "NASDAQ100", "issuer": "Motilal Oswal Mutual Fund", "ter_pct": 0.51,
     "about": "Feeds Indian investors into the Nasdaq 100 index of US technology leaders."},
    {"symbol": "MAFANG", "name": "Mirae Asset NYSE FANG+ ETF", "category": "International",
     "benchmark": None, "no_bench": True, "issuer": "Mirae Asset Mutual Fund", "ter_pct": 0.55,
     "about": "Tracks the NYSE FANG+ index of large US technology and growth companies."},
    {"symbol": "HNGSNGBEES", "name": "Nippon India Hang Seng BeES", "category": "International",
     "benchmark": None, "no_bench": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.60,
     "about": "Tracks the Hang Seng index of Hong Kong-listed companies."},

    # ---- Liquid & debt (4) -------------------------------------------------
    {"symbol": "LIQUIDBEES", "name": "Nippon India Liquid BeES", "category": "Liquid & Debt",
     "benchmark": None, "no_bench": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.29,
     "about": "A liquid ETF used for cash parking; daily dividend reinvestment units."},
    {"symbol": "LIQUIDIETF", "name": "ICICI Prudential Liquid ETF", "category": "Liquid & Debt",
     "benchmark": None, "no_bench": True, "issuer": "ICICI Prudential Mutual Fund", "ter_pct": 0.20,
     "about": "ICICI Prudential's liquid ETF for short-term cash management."},
    {"symbol": "GILT5YBEES", "name": "Nippon India Nifty 5Y G-Sec BeES", "category": "Liquid & Debt",
     "benchmark": None, "no_bench": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.30,
     "about": "Tracks a 5-year government-securities index."},
    {"symbol": "SDL26BEES", "name": "Nippon India Nifty SDL 2026 Maturity BeES", "category": "Liquid & Debt",
     "benchmark": None, "no_bench": True, "issuer": "Nippon India Mutual Fund", "ter_pct": 0.30,
     "about": "Target-maturity ETF holding state development loans maturing in 2026."},
]

# Fallback profiles keep every ETF row populated when a free live feed misses a
# symbol. The numbers are clearly labelled as modelled on the desk; they are not
# presented as live quotes.
_CATEGORY_PROFILE = {
    "Silver": {"price": 108.0, "ter": 0.55, "te": 0.62,
               "ret": (2.1, 9.4, 18.2, 33.5, 16.9, 14.6)},
    "Gold": {"price": 76.0, "ter": 0.55, "te": 0.48,
             "ret": (1.6, 6.8, 13.1, 27.2, 13.4, 12.6)},
    "Nifty 50": {"price": 268.0, "ter": 0.20, "te": 0.22,
                 "ret": (1.2, 4.6, 9.8, 15.4, 11.8, 12.6)},
    "Sensex": {"price": 94.0, "ter": 0.20, "te": 0.25,
               "ret": (1.1, 4.3, 9.2, 14.8, 11.5, 12.4)},
    "Mid & Next 50": {"price": 62.0, "ter": 0.28, "te": 0.35,
                      "ret": (1.8, 6.9, 14.2, 22.6, 15.8, 15.2)},
    "Banking": {"price": 520.0, "ter": 0.20, "te": 0.30,
                "ret": (1.4, 5.1, 10.6, 17.8, 12.9, 12.1)},
    "IT & Sectoral": {"price": 46.0, "ter": 0.22, "te": 0.42,
                      "ret": (0.9, 3.8, 8.6, 14.2, 12.4, 13.1)},
    "PSU": {"price": 82.0, "ter": 0.12, "te": 0.28,
            "ret": (1.6, 6.2, 12.4, 21.4, 17.2, 14.8)},
    "International": {"price": 36.0, "ter": 0.55, "te": 0.65,
                      "ret": (2.2, 8.4, 16.8, 28.4, 18.6, 17.2)},
    "Liquid & Debt": {"price": 1000.0, "ter": 0.25, "te": 0.06,
                      "ret": (0.5, 1.6, 3.2, 6.6, 5.8, 5.2)},
}

_PERIOD_KEYS = ("1m", "3m", "6m", "1y", "3y", "5y")


def _attach_etf_fallbacks() -> None:
    for spec in ETF_UNIVERSE:
        prof = _CATEGORY_PROFILE[spec["category"]]
        seed = int(hashlib.sha1(spec["symbol"].encode()).hexdigest()[:6], 16)
        jitter = (seed % 1000) / 1000.0 - 0.5
        price = round(prof["price"] * (1 + jitter * 0.12), 2)
        nav = round(price * (1 - 0.0015), 2)
        returns = {k: round(v + jitter * 2.4, 2)
                   for k, v in zip(_PERIOD_KEYS, prof["ret"])}
        spec.setdefault("ter_pct", round(prof["ter"] + abs(jitter) * 0.10, 2))
        spec["fallback"] = {
            "price": price,
            "nav": nav,
            "returns": returns,
            "tracking_error_pct": round(prof["te"] + abs(jitter) * 0.12, 2),
        }


_attach_etf_fallbacks()


def fallback_history(spec: dict, points: int = 1261) -> list[dict]:
    """Deterministic 5-year daily series anchored to the spec's fallback
    returns. Used only when the free live/history feed has no series."""
    fb = spec.get("fallback") or {}
    price = float(fb.get("price") or 100.0)
    r = fb.get("returns") or {}

    def ratio(key: str, default: float) -> float:
        return 1 + float(r.get(key, default)) / 100.0

    anchors = [
        (0, price / (ratio("5y", 10.0) ** 5)),
        (504, price / (ratio("3y", 10.0) ** 3)),
        (1008, price / ratio("1y", 10.0)),
        (1134, price / ratio("6m", 8.0)),
        (1197, price / ratio("3m", 5.0)),
        (1239, price / ratio("1m", 2.0)),
        (1260, price),
    ]

    def value_at(i: int) -> float:
        for (i0, p0), (i1, p1) in zip(anchors, anchors[1:]):
            if i0 <= i <= i1:
                t = (i - i0) / max(i1 - i0, 1)
                return p0 * ((p1 / p0) ** t)
        return price

    seed = int(hashlib.sha1(spec["symbol"].encode()).hexdigest()[:8], 16)
    days: list[date] = []
    cursor = date.today()
    while len(days) < points:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()

    out = []
    for i, day in enumerate(days):
        close = round(value_at(i), 2)
        drift = (((seed >> (i % 19)) & 7) - 3.5) / 10000.0
        open_ = round(close * (1 + drift), 2)
        high = round(max(open_, close) * 1.002, 2)
        low = round(min(open_, close) * 0.998, 2)
        volume = 100000 + ((seed * (i + 7)) % 900000)
        out.append({"date": day.isoformat(), "o": open_, "h": high,
                    "l": low, "c": close, "v": volume})
    return out

# Popular AMC names used to cluster mutual fund schemes (factual AMFI names).
MC_DISPLAY = ["HDFC Asset Management", "ICICI Prudential", "Nippon India",
              "SBI Funds Management", "Axis", "Kotak Mahindra", "UTI",
              "Aditya Birla Sun Life", "Mirae Asset", "Parag Parikh",
              "Quant Mutual", "Motilal Oswal", "DSP", "Franklin Templeton",
              "Canara Robeco", "Tata Asset Management", "Bandhan",
              "Edelweiss", "Union Asset Management", "Invesco India"]

AMC_MATCH = {"HDFC Asset Management": r"^(HDFC| HDFC)\b|^HDFC",
             "ICICI Prudential": r"^ICICI",
             "Nippon India": r"^(Nippon|Reliance)",
             "SBI Funds Management": r"^SBI",
             "Axis": r"^Axis",
             "Kotak Mahindra": r"^Kotak",
             "UTI": r"^UTI",
             "Aditya Birla Sun Life": r"^(Aditya|ABSL)",
             "Mirae Asset": r"^Mirae",
             "Parag Parikh": r"^(Parag|PPFAS)",
             "Quant Mutual": r"^Quant",
             "Motilal Oswal": r"^(Motilal|MOSt)",
             "DSP": r"^DSP",
             "Franklin Templeton": r"^Franklin",
             "Canara Robeco": r"^(Canara|Canara Rob)",
             "Tata Asset Management": r"^Tata",
             "Bandhan": r"^(Bandhan|IDFC)",
             "Edelweiss": r"^Edelweiss",
             "Union Asset Management": r"^Union",
             "Invesco India": r"^Invesco"}
