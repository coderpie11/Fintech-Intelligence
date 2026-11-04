"""InvestorGain live IPO GMP scraper.

The public InvestorGain report pages are server-rendered HTML, so a normal
HTTP client with browser TLS impersonation is enough. Every value returned here
is scraped from the live page — nothing is invented. When the network or the
markup changes the caller falls back to the versioned offer-document seed and
labels the row accordingly.
"""
from __future__ import annotations

import datetime as dt
import re
from html import unescape
from typing import Any

from curl_cffi import requests as curl_requests

from app.core.config import cache_get, cache_set

BASE = "https://www.investorgain.com"
LIVE_URL = f"{BASE}/report/ipo-gmp-live/331/"
SUB_URL = f"{BASE}/report/ipo-subscription-live/333/"
LIVE_TTL = 600          # 10 minutes: the report itself refreshes a few times an hour
DETAIL_TTL = 6 * 3600   # offer documents do not change minute to minute

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _clean(text: str | None) -> str:
    return unescape(re.sub(r"\s+", " ", text or "")).strip()


def _num(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _date(text: str | None, today: dt.date | None = None) -> str | None:
    """'29-Oct' / '29 Oct 2026' / '2026-10-29' -> ISO date."""
    if not text:
        return None
    today = today or dt.date.today()
    t = _clean(text)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})[\s-]([A-Za-z]{3,9})(?:[\s,-]+(\d{4}))?", t)
    if not m:
        return None
    day, mon = int(m.group(1)), _MONTHS.get(m.group(2)[:3].lower())
    if not mon:
        return None
    year = int(m.group(3)) if m.group(3) else today.year
    try:
        d = dt.date(year, mon, day)
    except ValueError:
        return None
    if not m.group(3) and d > today + dt.timedelta(days=180):
        d = d.replace(year=year - 1)
    return d.isoformat()


def _get(url: str, timeout: int = 12) -> str | None:
    try:
        r = curl_requests.get(url, impersonate="chrome", timeout=timeout,
                              headers={"Accept-Language": "en-IN,en;q=0.9"})
        if r.status_code == 200 and len(r.text) > 5000:
            return r.text
    except Exception:  # noqa: BLE001
        return None
    return None


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def _table_rows(table) -> list[list[str]]:
    out = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True))
                 for c in tr.find_all(["th", "td"])]
        if any(cells):
            out.append(cells)
    return out


def _cfemail(encoded: str) -> str:
    """Decode Cloudflare's obfuscated status/listing-price token."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key)
                       for i in range(2, len(encoded), 2))
    except Exception:  # noqa: BLE001
        return ""


def _status_from_badge(badge: str) -> str:
    b = (badge or "").strip().upper()
    if b.startswith("LT"):
        return "LISTED"
    if b.startswith("CT"):
        return "CLOSED"
    if b.startswith("C"):
        return "CLOSED"
    if b.startswith("O"):
        return "LIVE"
    if b.startswith("U"):
        return "UPCOMING"
    return "UNKNOWN"


def _board_from_badge(badge: str) -> str:
    b = (badge or "").upper()
    return "SME" if "SME" in b else "MAINBOARD"


def live_gmp(force: bool = False) -> list[dict[str, Any]]:
    """Scrape the live IPO GMP report table."""
    key = "ig:live:gmp"
    if not force:
        hit = cache_get(key)
        if hit is not None:
            return hit
    html = _get(LIVE_URL)
    if not html:
        return []
    soup = _soup(html)
    table = soup.find("table", id="reportTable") or soup.find("table")
    if table is None:
        return []
    today = dt.date.today()
    rows: list[dict[str, Any]] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 12:
            continue
        name_cell = tds[0]
        name_a = name_cell.find("a")
        name = _clean(name_a.get_text(" ", strip=True) if name_a
                      else name_cell.get_text(" ", strip=True))
        if not name:
            continue
        href = name_a.get("href", "") if name_a else ""
        badges = [_clean(b.get_text(" ", strip=True))
                  for b in name_cell.find_all("span", class_="badge")]
        board = "SME" if any("SME" in b.upper() for b in badges) else "MAINBOARD"
        status = "UNKNOWN"
        listed_price = listed_gain = None
        for b in badges:
            s = _status_from_badge(b)
            if s != "UNKNOWN":
                status = s
        # Cloudflare hides the live status (and, once listed, the listing
        # price + gain) inside an obfuscated token.
        for cf in name_cell.find_all("a", class_="__cf_email__"):
            decoded = _cfemail(cf.get("data-cfemail", ""))
            if not decoded:
                continue
            lead = decoded.strip()[:3].upper()
            if lead.startswith("L@"):
                status = "LISTED"
            elif lead.startswith("LT"):
                status = "LISTED"
            elif lead.startswith("CT") or lead.startswith("C@"):
                status = "CLOSED"
            elif lead.startswith("O"):
                status = "LIVE"
            elif lead.startswith("U"):
                status = "UPCOMING"
            lm = re.search(r"L@\s*₹?\s*([\d,.]+)", decoded)
            if lm:
                listed_price = _num(lm.group(1))
            gm = re.search(r"\((-?\d+(?:\.\d+)?)%\)", decoded)
            if gm:
                listed_gain = float(gm.group(1))
        cells = [_clean(td.get_text(" ", strip=True)) for td in tds]
        gmp_cell, rating_cell, sub_cell = cells[1], cells[2], cells[3]
        price, size, lot = cells[4], cells[5], cells[6]
        open_, close, boa, listing = cells[7], cells[8], cells[9], cells[10]
        updated, anchor = cells[11], cells[12] if len(cells) > 12 else ""
        gmp = _num(gmp_cell.split("(")[0]) if "--" not in gmp_cell else None
        pm = re.search(r"\((-?\d+(?:\.\d+)?)%\)", gmp_cell)
        fire = rating_cell.count("🔥")
        row = {
            "name": name,
            "board": board,
            "status": status if status != "UNKNOWN" else "CLOSED",
            "price_high": _num(price),
            "gmp": gmp,
            "gmp_pct": float(pm.group(1)) if pm else None,
            "fire_rating": max(1, min(fire, 5)) if fire else None,
            "subscription_total": _num(sub_cell),
            "issue_size": _num(size),
            "lot": int(_num(lot)) if _num(lot) else None,
            "open": _date(open_, today),
            "close": _date(close, today),
            "allotment": _date(boa, today),
            "listing": _date(listing, today),
            "listed_price": listed_price,
            "listed_gain_pct": listed_gain,
            "updated_on": updated,
            "anchor": "✅" in anchor or "✔" in anchor,
            "source": "InvestorGain live GMP report",
            "live": True,
        }
        if href.startswith("/gmp/"):
            row["ig_url"] = BASE + href
            row["ig_slug"] = href.strip("/").split("/")[1]
            row["ig_id"] = href.strip("/").split("/")[-1]
        rows.append(row)
    rows = [r for r in rows if r.get("name") and r.get("price_high")]
    cache_set(key, rows, ttl=LIVE_TTL)
    return rows


def live_subscription(force: bool = False) -> dict[str, dict[str, Any]]:
    """Scrape the live subscription report and key it by company name."""
    key = "ig:live:subscription"
    if not force:
        hit = cache_get(key)
        if hit is not None:
            return hit
    html = _get(SUB_URL)
    if not html:
        return {}
    soup = _soup(html)
    table = soup.find("table")
    if table is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for cells in _table_rows(table)[1:]:
        if len(cells) < 8:
            continue
        raw_name = cells[0]
        m = re.match(r"(.+?)\s+(BSE SME|NSE SME|IPO)\b", raw_name)
        name = (m.group(1) if m else raw_name).strip()
        name = re.split(r"\s+GMP:", name)[0].strip()
        out[name.lower()] = {
            "total": _num(cells[1]),
            "qib": _num(cells[2]),
            "snii": _num(cells[3]),
            "bnii": _num(cells[4]),
            "nii": _num(cells[5]),
            "retail": _num(cells[6]),
            "anchor": "✅" in cells[7] or "✔" in cells[7],
            "issue_size": _num(cells[8]) if len(cells) > 8 else None,
            "price": _num(cells[9]) if len(cells) > 9 else None,
            "pe": _num(cells[10]) if len(cells) > 10 else None,
            "closing": _date(cells[11]) if len(cells) > 11 else None,
        }
    cache_set(key, out, ttl=LIVE_TTL)
    return out


def subscription_for(name: str, subs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    subs = subs if subs is not None else live_subscription()
    key = (name or "").lower().strip()
    if key in subs:
        return subs[key]
    for k, v in subs.items():
        if key and (key in k or k in key):
            return v
    return {}


def _section_text(soup, heading: str, limit: int = 900) -> str | None:
    for h in soup.find_all(["h2", "h3"]):
        if heading.lower() in h.get_text(" ", strip=True).lower():
            nxt = h.find_next(["p", "div"])
            if nxt:
                txt = _clean(nxt.get_text(" ", strip=True))
                if len(txt) > 40:
                    return txt[:limit]
    return None


def ipo_page_detail(ig_slug: str, ig_id: str) -> dict[str, Any]:
    """Scrape the full `/ipo/<slug>/<id>/` page: issue facts, financials, KPIs."""
    key = f"ig:ipo:{ig_slug}:{ig_id}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    html = _get(f"{BASE}/ipo/{ig_slug}/{ig_id}/", timeout=15)
    if not html:
        return {}
    soup = _soup(html)
    tables = soup.find_all("table")
    facts: dict[str, Any] = {}
    if tables:
        for cells in _table_rows(tables[0]):
            if len(cells) >= 2:
                facts[cells[0].lower()] = cells[1]
    # Locate the financials table by its row labels.
    financials: list[dict[str, Any]] = []
    kpis: list[dict[str, Any]] = []
    pre_post: list[dict[str, Any]] = []
    reservation: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    for tb in tables:
        rows = _table_rows(tb)
        if not rows:
            continue
        joined = " ".join(rows[0]).lower()
        if "period ended" in joined:
            header = rows[0]
            for row in rows[1:]:
                if len(row) < 2:
                    continue
                label = row[0].lower()
                vals = row[1:]
                if "amount in" in label:
                    continue
                if "total income" in label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        financials.append({"period": period, "revenue": _num(vals[i])})
                elif "profit after tax" in label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        if i < len(financials):
                            financials[i]["pat"] = _num(vals[i])
                elif "ebitda" in label and "margin" not in label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        if i < len(financials):
                            financials[i]["ebitda"] = _num(vals[i])
                elif "net worth" in label or "networth" in label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        if i < len(financials):
                            financials[i]["net_worth"] = _num(vals[i])
                elif "total borrowing" in label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        if i < len(financials):
                            financials[i]["borrowing"] = _num(vals[i])
                elif "assets" == label:
                    for i, period in enumerate(header[1:1 + len(vals)]):
                        if i < len(financials):
                            financials[i]["assets"] = _num(vals[i])
        elif "kpi" in joined:
            header = rows[0]
            for row in rows[1:]:
                if len(row) >= 2:
                    kpis.append({"kpi": row[0],
                                 "values": [{"period": header[i] if i < len(header) else "",
                                             "value": row[i]}
                                            for i in range(1, len(row))]})
        elif "pre ipo" in joined or "post ipo" in joined:
            for row in rows[1:]:
                if len(row) >= 2:
                    pre_post.append({"metric": row[0],
                                     "values": [{"label": rows[0][i] if i < len(rows[0]) else "",
                                                 "value": row[i]}
                                                for i in range(1, len(row))]})
        elif "investor category" in joined:
            for row in rows[1:]:
                if len(row) >= 2:
                    reservation.append({"category": row[0],
                                        "shares": _num(row[1]),
                                        "pct_net": _num(row[2]) if len(row) > 2 else None,
                                        "pct_total": _num(row[3]) if len(row) > 3 else None,
                                        "max_allottees": _num(row[4]) if len(row) > 4 else None})
        elif "issue objects" in joined:
            for row in rows[1:]:
                if len(row) >= 3 and row[0].isdigit():
                    objects.append({"no": int(row[0]), "object": row[1], "amount_cr": _num(row[2])})
    about = _section_text(soup, "About Company", 1200)
    lead_managers = facts.get("lead managers") or facts.get("book running lead managers")
    registrar = facts.get("registrar")
    price_band = facts.get("price band")
    issue_size = _num(facts.get("issue size"))
    fresh = _num(facts.get("fresh issue"))
    face = _num(facts.get("face value"))
    discount = facts.get("discount")
    data = {
        "facts": facts,
        "about": about,
        "lead_managers": [x.strip() for x in re.split(r",|;", lead_managers or "") if x.strip()],
        "registrar": registrar,
        "price_band_text": price_band,
        "issue_size_cr": issue_size,
        "fresh_issue_cr": fresh,
        "face_value": face,
        "employee_discount": discount,
        "financials": financials,
        "kpis": kpis,
        "pre_post": pre_post,
        "reservation": reservation,
        "objects": objects,
        "source": "InvestorGain offer-document page",
    }
    cache_set(key, data, ttl=DETAIL_TTL)
    return data


def gmp_history(ig_slug: str, ig_id: str) -> list[dict[str, Any]]:
    """Day-wise GMP history from the `/gmp/<slug>/<id>/` page."""
    key = f"ig:gmp:{ig_slug}:{ig_id}"
    hit = cache_get(key)
    if hit is not None:
        return hit
    html = _get(f"{BASE}/gmp/{ig_slug}/{ig_id}/", timeout=15)
    if not html:
        return []
    soup = _soup(html)
    table = soup.find("table")
    if table is None:
        return []
    rows = _table_rows(table)
    out: list[dict[str, Any]] = []
    today = dt.date.today()
    for cells in rows[1:]:
        if len(cells) < 3:
            continue
        day = _date(cells[0], today)
        gmp = _num(cells[1].split("(")[0])
        if day and gmp is not None:
            out.append({"date": day, "gmp": gmp})
    out.sort(key=lambda r: r["date"])
    # Keep the most recent 45 sessions for the chart.
    out = out[-45:]
    cache_set(key, out, ttl=DETAIL_TTL)
    return out


def refresh_all(force: bool = True) -> dict[str, Any]:
    """Convenience wrapper used by the seed stage and the refresh endpoint."""
    rows = live_gmp(force=force)
    subs = live_subscription(force=force)
    for row in rows:
        row["subscription"] = subscription_for(row["name"], subs)
    return {"count": len(rows), "ipos": rows,
            "source": "InvestorGain live GMP report",
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}
