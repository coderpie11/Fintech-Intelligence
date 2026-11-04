"""Static factual universe definitions (slug maps, board lists). These are
reference constants — the actual live values/constituents are always fetched
from the exchanges at seed time.

`yahoo` tickers below were verified live against Yahoo Finance on this machine.
`fallback_names` are the exact row labels in NSE's official daily index
snapshot archive (used only when Yahoo has no multi-year series).
"""
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

# Curated, factual NSE-listed ETFs. `benchmark` is the NSE index symbol used
# for tracking-error maths; `proxy` flags an approximate benchmark; `no_bench`
# means no honest benchmark exists on a free feed.
ETF_UNIVERSE = [
    {"symbol": "NIFTYBEES", "name": "Nippon India Nifty 50 BeES",
     "category": "Large Cap · Nifty 50", "benchmark": "NIFTY 50",
     "issuer": "Nippon India Mutual Fund",
     "about": "India's largest ETF by assets; tracks the NIFTY 50 Total Return Index."},
    {"symbol": "SETFNIF50", "name": "SBI Nifty 50 ETF",
     "category": "Large Cap · Nifty 50", "benchmark": "NIFTY 50",
     "issuer": "SBI Mutual Fund",
     "about": "Tracks the NIFTY 50; one of the largest index ETFs in India."},
    {"symbol": "BANKBEES", "name": "Nippon India Nifty Bank BeES",
     "category": "Sectoral · Bank Nifty", "benchmark": "NIFTY BANK",
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks the NIFTY BANK index of India's most liquid banking stocks."},
    {"symbol": "ITBEES", "name": "Nippon India Nifty IT BeES",
     "category": "Sectoral · Nifty IT", "benchmark": "NIFTY IT",
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks the NIFTY IT index of large Indian software-services companies."},
    {"symbol": "JUNIORBEES", "name": "Nippon India Nifty Next 50 Junior BeES",
     "category": "Large Cap · Nifty Next 50", "benchmark": "NIFTY NEXT 50",
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks the NIFTY Next 50 — the 50 large caps immediately below the NIFTY 50."},
    {"symbol": "GOLDBEES", "name": "Nippon India Gold BeES",
     "category": "Commodity · Gold", "benchmark": "GOLD_INR_PROXY",
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks domestic gold prices; backed by physical gold held by the fund."},
    {"symbol": "SILVERBEES", "name": "Nippon India Silver BeES",
     "category": "Commodity · Silver", "benchmark": "SILVER_INR_PROXY",
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks domestic silver prices; backed by physical silver."},
    {"symbol": "LIQUIDBEES", "name": "Nippon India Liquid BeES",
     "category": "Debt · Liquid", "benchmark": None, "no_bench": True,
     "issuer": "Nippon India Mutual Fund",
     "about": "A liquid ETF used for cash parking; daily dividend reinvestment units."},
    {"symbol": "CPSEETF", "name": "CPSE ETF",
     "category": "Thematic · CPSE", "benchmark": "NIFTY PSE", "proxy": True,
     "issuer": "Nippon India Mutual Fund",
     "about": "Tracks the NIFTY CPSE index of central public-sector enterprises; "
              "NIFTY PSE is used as a proxy benchmark here."},
    {"symbol": "ICICIB22", "name": "ICICI Prudential Bharat 22 ETF",
     "category": "Thematic · Bharat 22", "benchmark": None, "no_bench": True,
     "issuer": "ICICI Prudential Mutual Fund",
     "about": "Tracks the BSE Bharat 22 index of CPSEs, PSBs and strategic holdings."},
    {"symbol": "MON100", "name": "Motilal Oswal Nasdaq 100 ETF",
     "category": "International · Nasdaq 100", "benchmark": "NASDAQ100",
     "issuer": "Motilal Oswal Mutual Fund",
     "about": "Feeds Indian investors into the Nasdaq 100 index of US technology leaders."},
    {"symbol": "MOM100", "name": "Motilal Oswal Nifty Midcap 100 ETF",
     "category": "Mid Cap · Nifty Midcap 100", "benchmark": "NIFTY MIDCAP 100",
     "issuer": "Motilal Oswal Mutual Fund",
     "about": "Tracks the NIFTY Midcap 100 index."},
]

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
