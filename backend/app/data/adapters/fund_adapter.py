"""Mutual fund / ETF adapter — mfapi.in (schemes, NAVs) + AMFI-derived
categorization. Purely free; swappable behind the same interface."""
from __future__ import annotations

import json
import re

import httpx

from app.core.config import cache_get, cache_set

BASE = "https://api.mfapi.in"

ALL_SCHEMES: list[dict] | None = None


def all_schemes(force: bool = False) -> list[dict]:
    """The complete AMFI-mapped scheme list: [{schemeCode, schemeName}] (~76k)."""
    global ALL_SCHEMES
    if ALL_SCHEMES is not None and not force:
        return ALL_SCHEMES
    hit = cache_get("mfapi:all")
    if hit is not None and not force:
        ALL_SCHEMES = hit
        return hit
    r = httpx.get(f"{BASE}/mf", timeout=60)
    data = r.json()
    cache_set("mfapi:all", data, ttl=24 * 3600)
    ALL_SCHEMES = data
    return data


def classify(name: str) -> dict:
    """Parse plan option and a category guess purely from the scheme name."""
    low = name.lower()
    plan = "Direct" if "direct" in low else ("Regular" if "regular" else None)
    option = "IDCW" if ("idcw" in low or "dividend" in low or "payout" in low) else "Growth"
    category = None
    cat_map = [("Flexi Cap", r"flexi cap"), ("Large Cap", r"large cap"),
               ("Mid Cap", r"mid cap"), ("Small Cap", r"small cap"),
               ("Large & Midcap", r"large.?&.?mid"), ("Multi Asset", r"multi asset"),
               ("Nifty 50 Index", r"nifty ?50 index"), ("Nifty Next 50", r"next 50"),
               ("Sensex Index", r"sensex"), ("Gold Fund", r"gold "),
               ("Silver", r"silver"), ("Debt - Gilt", r"gilt"),
               ("Liquid", r"liquid"), ("Overnight", r"overnight"),
               ("Value Fund", r"value fund"), ("ELSS", r"\belss\b|tax saver"),
               ("Focused", r"focused"), ("Balanced Advantage", r"balanced advantage|dynamic asset"),
               ("Equity Savings", r"equity savings"), ("International", r"global|international|nasdaq|tech-?usa|developed"),
               ("Hybrid", r"hybrid|aggressive|conservative"), ("Sectoral", r"(pharma|banking|bank|healthcare|it |technology|energy|psu|infrastructure|manufacturing)")]
    for label, pattern in cat_map:
        if re.search(pattern, low):
            category = label
            break
    if category is None and "index fund" in low:
        category = "Index Fund"
    if category is None and ("debt" in low or " corporate bond" in low or "government" in low):
        category = "Debt"
    if category is None and ("equity" in low):
        category = "Equity - Other"
    if category is None:
        category = "Other"
    return {"plan": plan, "option": option, "category": category}


def scheme_search(term: str, limit: int = 40) -> list[dict]:
    """Search the static list client-side (no rate cost)."""
    term_low = term.lower()
    hits = [s for s in all_schemes() if term_low in s["schemeName"].lower()]
    return hits[:limit]


def scheme_nav_full(code: str) -> dict | None:
    hit = cache_get(f"mf:{code}")
    if hit is not None:
        return hit
    try:
        r = httpx.get(f"{BASE}/mf/{code}", timeout=60)
        if r.status_code != 200:
            return None
        data = r.json()
        cache_set(f"mf:{code}", data, ttl=6 * 3600)
        return data
    except Exception:  # noqa: BLE001
        return None


def _iso(d: str) -> str:
    """mfapi dates are DD-MM-YYYY; store ISO so lexical sort == chronological."""
    try:
        dd, mm, yy = (d or "").split("-")
        return f"{yy}-{mm}-{dd}"
    except ValueError:
        return d


def nav_series(code: str) -> list[dict]:
    """Cleaned [{date, nav}] series, oldest→newest, ISO dates."""
    raw = scheme_nav_full(code)
    if not raw:
        return []
    data = raw.get("data") or []
    series = [{"date": _iso(r["date"]), "nav": float(r["nav"])}
              for r in data if r.get("nav") not in (None, "")]
    series.sort(key=lambda x: x["date"])
    return series


def latest_navs() -> list[dict]:
    """All schemes' latest NAV (meta carve-out of /mf + per-code fetch is too
    heavy, so this uses the daily full-list NAV dump endpoint)."""
    hit = cache_get("mfapi:navall")
    if hit is not None:
        return hit
    r = httpx.get(f"{BASE}/mf/latest", timeout=120)
    data = r.json()
    cache_set("mfapi:navall", data, ttl=12 * 3600)
    return data


def latest_nav_map() -> dict[str, float]:
    """schemeCode → latest NAV, cached for 12 hours.

    Search results use this when a scheme has no locally stored series yet;
    the full on-demand series is still fetched when the scheme is opened.
    """
    hit = cache_get("mfapi:latestmap")
    if hit is not None:
        return hit
    out: dict[str, float] = {}
    try:
        for row in latest_navs():
            try:
                out[str(row.get("schemeCode") or "")] = float(row.get("nav"))
            except (TypeError, ValueError):
                continue
    except Exception:  # noqa: BLE001
        out = {}
    if out:
        cache_set("mfapi:latestmap", out, ttl=12 * 3600)
    return out



# ---------------------------------------------------------------- Groww
# Groww's scheme pages expose TER, AUM, exit load, holdings and category
# statistics in the embedded __NEXT_DATA__ blob. We only use the HTML pages
# (their internal JSON APIs return 404/500 for this client) and map fund names
# to page slugs with the official sitemap.
_GROWW_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
_GROWW_SLUGS: dict[str, str] | None = None


def _norm_name(text: str) -> str:
    s = (text or "").lower()
    for token in ("mutual fund", "fund", "direct plan", "regular plan",
                  "direct", "regular", "growth option", "growth", "idcw",
                  "option", "plan", "-"):
        s = s.replace(token, " ")
    return re.sub(r"[^a-z0-9]", "", s)


def groww_slugs() -> dict[str, str]:
    global _GROWW_SLUGS
    if _GROWW_SLUGS is not None:
        return _GROWW_SLUGS
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "data" / "groww_mf_sitemap.xml"
    out: dict[str, str] = {}
    try:
        xml = path.read_text(encoding="utf-8")
        for url in re.findall(r"<loc>(.*?)</loc>", xml):
            if "/mutual-funds/" not in url:
                continue
            slug = url.rstrip("/").split("/mutual-funds/")[-1]
            key = _norm_name(slug.replace("-", " "))
            out.setdefault(key, slug)
    except Exception:  # noqa: BLE001
        out = {}
    _GROWW_SLUGS = out
    return out


def groww_slug(name: str) -> str | None:
    key = _norm_name(name)
    slugs = groww_slugs()
    if key in slugs:
        return slugs[key]
    # Schemes renamed by the AMC keep an older Groww page slug.
    for needle, slug in _GROWW_ALIASES.items():
        if needle in key:
            return slug
    # tolerate small naming differences ("Fund" / "Scheme", ampersands)
    import difflib

    best = difflib.get_close_matches(key, list(slugs.keys()), n=1, cutoff=0.93)
    return slugs[best[0]] if best else None


# Groww still hosts some schemes under their former names.
_GROWW_ALIASES = {
    "paragparikhflexicap": "parag-parikh-long-term-value-fund-direct-growth",
    "paragparikholtvalue": "parag-parikh-long-term-value-fund-direct-growth",
    "hdfcmidcapopportunities": "hdfc-mid-cap-fund-direct-growth",
}


def groww_page(slug: str) -> dict | None:
    key = f"groww:page:{slug}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    try:
        r = httpx.get(f"https://groww.in/mutual-funds/{slug}",
                      headers={"User-Agent": _GROWW_UA}, timeout=35,
                      follow_redirects=True)
        if r.status_code != 200:
            return None
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      r.text, re.S)
        if not m:
            return None
        data = json.loads(m.group(1))
        mf = (data.get("props", {}).get("pageProps", {})
                  .get("mfServerSideData") or {})
        if not mf:
            return None
        out = _normalise_groww(mf)
        cache_set(key, out, ttl=24 * 3600)
        return out
    except Exception:  # noqa: BLE001
        return None


def _normalise_groww(mf: dict) -> dict:
    holdings = []
    for h in (mf.get("holdings") or []):
        weight = h.get("corpus_per")
        if weight is None:
            continue
        holdings.append({
            "name": h.get("company_name"),
            "sector": h.get("sector_name"),
            "instrument": h.get("instrument_name"),
            "weight": round(float(weight), 4),
            "market_value": h.get("market_value"),
            "portfolio_date": (h.get("portfolio_date") or "")[:10],
            "stock_search_id": h.get("stock_search_id"),
        })
    holdings.sort(key=lambda x: -x["weight"])
    rs = (mf.get("return_stats") or [{}])[0] or {}
    stats = mf.get("stats") or []
    category_avg = next((s for s in stats if s.get("type") == "CATEGORY_AVG_RETURN"), {})
    rank = next((s for s in stats if s.get("type") == "RANK_WITHIN_CATEGORY"), {})
    return {
        "slug": mf.get("search_id"),
        "name": mf.get("scheme_name"),
        "amc": mf.get("fund_house"),
        "category": mf.get("category"),
        "sub_category": mf.get("sub_category"),
        "plan": mf.get("plan_type"),
        "option": mf.get("scheme_type"),
        "ter": mf.get("expense_ratio"),
        "aum_crore": mf.get("aum"),
        "exit_load": mf.get("exit_load"),
        "benchmark": mf.get("benchmark_name"),
        "portfolio_turnover_pct": mf.get("portfolio_turnover"),
        "fund_manager": mf.get("fund_manager"),
        "launch_date": mf.get("launch_date"),
        "nav": mf.get("nav"),
        "nav_date": mf.get("nav_date"),
        "risk": rs.get("risk"),
        "sharpe": rs.get("sharpe_ratio"),
        "sortino": rs.get("sortino_ratio"),
        "beta": rs.get("beta"),
        "alpha": rs.get("alpha"),
        "std_dev": rs.get("standard_deviation"),
        "information_ratio": rs.get("information_ratio"),
        "category_avg": {
            "1y": category_avg.get("stat_1y"), "3y": category_avg.get("stat_3y"),
            "5y": category_avg.get("stat_5y"),
        },
        "rank": {"1y": rank.get("stat_1y"), "3y": rank.get("stat_3y"),
                 "5y": rank.get("stat_5y")},
        "returns_reported": {
            "1m": rs.get("return1m"), "3m": rs.get("return3m"),
            "6m": rs.get("return6m"), "1y": rs.get("return1y"),
            "3y": rs.get("return3y"), "5y": rs.get("return5y"),
        },
        "holdings": holdings,
        "portfolio_date": holdings[0]["portfolio_date"] if holdings else None,
        "source": "Groww scheme page (__NEXT_DATA__)",
        "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------- modelled fallback
# Groww does not publish a page for every AMFI scheme. Rather than leaving the
# list full of blanks, the seeder fills TER/AUM/holdings with deterministic
# category benchmarks and explicitly labels every such value as modelled. No
# number here is presented as an AMC disclosure.

CATEGORY_TER = {
    "Large Cap": 0.65, "Mid Cap": 0.72, "Small Cap": 0.82, "Flexi Cap": 0.68,
    "ELSS": 0.85, "Index Fund": 0.20, "Nifty 50 Index": 0.18,
    "Sensex Index": 0.18, "Debt": 0.35, "Debt - Gilt": 0.32, "Liquid": 0.20,
    "Overnight": 0.12, "Hybrid": 0.65, "Balanced Advantage": 0.70,
    "Value Fund": 0.70, "Focused": 0.66, "Large & Midcap": 0.70,
    "Multi Asset": 0.72, "International": 0.52, "Gold Fund": 0.50,
    "Silver": 0.60, "Sectoral": 0.78, "Equity Savings": 0.60,
    "Equity - Other": 0.70, "Other": 0.72,
}

AMC_SCALE = {
    "SBI": 9.2, "HDFC": 7.8, "ICICI": 8.4, "Nippon": 4.8, "Kotak": 4.2,
    "Axis": 3.1, "Aditya": 3.6, "UTI": 2.8, "Mirae": 1.9, "DSP": 1.6,
    "Franklin": 1.1, "Canara": 1.0, "Tata": 1.2, "Bandhan": 1.1,
    "Quant": 0.9, "Motilal": 1.0, "Parag": 0.8, "Edelweiss": 0.7,
    "Union": 0.6, "Invesco": 0.7,
}

# Real NSE names used as sector-aligned representative holdings. They are
# representative, not a claim about any specific scheme's actual portfolio.
SECTOR_HOLDINGS = {
    "Banking": [("HDFCBANK", "Banks"), ("ICICIBANK", "Banks"), ("SBIN", "Banks"),
                ("KOTAKBANK", "Banks"), ("AXISBANK", "Banks"), ("INDUSINDBK", "Banks")],
    "IT": [("TCS", "IT Services"), ("INFY", "IT Services"), ("HCLTECH", "IT Services"),
           ("WIPRO", "IT Services"), ("TECHM", "IT Services"), ("LTIM", "IT Services")],
    "FMCG": [("HINDUNILVR", "FMCG"), ("ITC", "FMCG"), ("NESTLEIND", "FMCG"),
             ("BRITANNIA", "FMCG"), ("DABUR", "FMCG"), ("GODREJCP", "FMCG")],
    "Pharma": [("SUNPHARMA", "Pharma"), ("DRREDDY", "Pharma"), ("CIPLA", "Pharma"),
               ("DIVISLAB", "Pharma"), ("LUPIN", "Pharma"), ("AUROPHARMA", "Pharma")],
    "Auto": [("MARUTI", "Auto"), ("M&M", "Auto"), ("TATAMOTORS", "Auto"),
             ("BAJAJ-AUTO", "Auto"), ("EICHERMOT", "Auto"), ("HEROMOTOCO", "Auto")],
    "Energy": [("RELIANCE", "Energy"), ("ONGC", "Energy"), ("BPCL", "Energy"),
               ("IOC", "Energy"), ("NTPC", "Power"), ("POWERGRID", "Power")],
    "Metals": [("TATASTEEL", "Metals"), ("JSWSTEEL", "Metals"), ("HINDALCO", "Metals"),
               ("VEDL", "Metals"), ("COALINDIA", "Mining"), ("SAIL", "Metals")],
    "Infra": [("LT", "Infrastructure"), ("ADANIPORTS", "Infrastructure"),
              ("ULTRACEMCO", "Cement"), ("GRASIM", "Cement"), ("DLF", "Realty"),
              ("SHREECEM", "Cement")],
    "Consumption": [("HINDUNILVR", "FMCG"), ("ITC", "FMCG"), ("TITAN", "Consumer"),
                    ("DMART", "Retail"), ("ASIANPAINT", "Paints"), ("BHARTIARTL", "Telecom")],
    "Broad": [("HDFCBANK", "Banks"), ("RELIANCE", "Energy"), ("ICICIBANK", "Banks"),
              ("INFY", "IT Services"), ("TCS", "IT Services"), ("BHARTIARTL", "Telecom"),
              ("ITC", "FMCG"), ("LT", "Infrastructure"), ("SBIN", "Banks"),
              ("HINDUNILVR", "FMCG")],
    "Midcap": [("FEDERALBNK", "Banks"), ("AUROPHARMA", "Pharma"), ("MPHASIS", "IT Services"),
               ("CUMMINSIND", "Industrials"), ("SUPREMEIND", "Industrials"),
               ("OBEROIRLTY", "Realty"), ("PERSISTENT", "IT Services"),
               ("ASHOKLEY", "Auto"), ("BHARATFORG", "Auto"), ("IDFCFIRSTB", "Banks")],
    "Smallcap": [("CAPLIPOINT", "Pharma"), ("KIRLOSENG", "Industrials"),
                 ("TEJASNET", "Telecom"), ("CERA", "Consumer"), ("FINEORG", "Chemicals"),
                 ("APARINDS", "Industrials"), ("KPITTECH", "IT Services"),
                 ("JYOTHYLAB", "FMCG"), ("RALLIS", "Chemicals"), ("GRAVITA", "Metals")],
    "Debt": [("7.18% GS 2033", "G-Sec"), ("7.10% GS 2034", "G-Sec"),
             ("364-Day T-Bill", "T-Bill"), ("7.64% Maharashtra SDL 2034", "SDL"),
             ("8.35% REC Bond 2030", "PSU Bond"), ("7.95% HDFC Bank Bond 2029", "Corporate")],
    "Gold": [("GOLDBEES", "Gold ETF"), ("Physical gold (995)", "Commodity"),
             ("Gold futures (MCX)", "Commodity")],
    "International": [("AAPL", "Technology"), ("MSFT", "Technology"), ("NVDA", "Semis"),
                      ("AMZN", "Consumer"), ("GOOGL", "Technology"), ("META", "Technology")],
}


def _sector_bucket(category: str, name: str) -> str:
    low = f"{category or ''} {name or ''}".lower()
    for key, words in {
        "Banking": ("bank",), "IT": ("information technology", "technology", "it "),
        "Pharma": ("pharma", "health"), "Auto": ("auto",), "Metals": ("metal",),
        "Energy": ("energy", "power", "oil"), "FMCG": ("fmcg", "consumption"),
        "Infra": ("infra", "realty"), "Midcap": ("mid cap", "midcap"),
        "Smallcap": ("small cap", "smallcap"), "Gold": ("gold", "silver"),
        "Debt": ("debt", "liquid", "gilt", "overnight", "bond"),
        "International": ("international", "global", "nasdaq"),
    }.items():
        if any(w in low for w in words):
            return key
    if "index" in low or "large cap" in low or "flexi" in low or "value" in low or "elss" in low or "focused" in low:
        return "Broad"
    return "Broad"


def _month_end(offset: int) -> str:
    import datetime as _dt
    d = _dt.date.today().replace(day=1)
    for _ in range(max(offset, 0)):
        d = (d - _dt.timedelta(days=1)).replace(day=1)
    nxt = (d.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
    return (nxt - _dt.timedelta(days=1)).isoformat()


def modelled_groww(name: str, amc: str, category: str) -> dict:
    """Deterministic category-benchmarked facts, clearly labelled modelled."""
    bucket = _sector_bucket(category, name)
    ter = CATEGORY_TER.get(category, 0.70)
    scale = next((v for k, v in AMC_SCALE.items() if k.lower() in (amc or "").lower()), 1.0)
    # Deterministic ticker spread so two funds in the same bucket differ.
    seed = sum(ord(c) for c in (name or "")) % 1000
    aum = round(scale * 1000 * (0.08 + (seed % 37) / 100), 1)
    exit_load = ("Nil" if bucket in ("Debt",) else
                 "1% if redeemed within 365 days; Nil thereafter")
    names = SECTOR_HOLDINGS.get(bucket, SECTOR_HOLDINGS["Broad"])
    raw = [((seed * (i + 7)) % 53) / 10 + 4.0 for i in range(len(names))]
    total = sum(raw) or 1
    weights = [round(w / total * 78, 2) for w in raw]  # ~78% in holdings, rest cash
    date_now = _month_end(0)
    holdings = [{
        "name": n, "sector": s, "instrument": "Equity" if bucket not in ("Debt", "Gold") else "Debt",
        "weight": weights[i], "portfolio_date": date_now,
        "reason": "Representative sector holding in the benchmark model.",
    } for i, (n, s) in enumerate(names)]

    # Two snapshots so the churn engine has a real month-on-month comparison.
    prev_names = names[:-1] + [("CASH", "Cash")]
    prev_weights = weights[:-1] + [round(weights[-1] + 3.0, 2)]
    prev = [{
        "name": n, "sector": s, "instrument": "Cash" if n == "CASH" else
        ("Equity" if bucket not in ("Debt", "Gold") else "Debt"),
        "weight": prev_weights[i], "portfolio_date": _month_end(1),
        "reason": "Prior-month benchmark snapshot.",
    } for i, (n, s) in enumerate(prev_names)]

    return {
        "name": name, "amc": amc, "category": category,
        "sub_category": category, "plan": "Direct", "option": "Growth",
        "ter": ter, "ter_modelled": True,
        "aum_crore": aum, "aum_modelled": True,
        "exit_load": exit_load, "benchmark": f"{category} benchmark",
        "portfolio_turnover_pct": None, "fund_manager": None,
        "launch_date": None, "risk": "Moderate",
        "sharpe": None, "sortino": None, "beta": None, "alpha": None,
        "std_dev": None, "information_ratio": None,
        "category_avg": {}, "rank": {},
        "holdings": holdings,
        "portfolio_date": date_now,
        "source": "Category benchmark model (Groww page unavailable)",
        "modelled": True,
        "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "prior_snapshot": {
            "portfolio_date": _month_end(1), "holdings": prev, "modelled": True,
        },
    }

