"""Universal entity resolution shared by every AI surface.

RangeCast, Ask Dalal and the 4 PM X-Ray all accept free text ("pc jewellers",
"lt finance", "nifty 50", "gold"). Doing that with a single fuzzy score over
"SYMBOL + NAME" mis-resolves short tickers: "LT" beats "L&T Finance" for
"lt finance", and "PC Jewellers" lands on an unrelated company whose name
happens to share letters.

The rules here are token-based and universal:

1. an exact ticker (or index/ETF/commodity) match wins outright;
2. otherwise every word of the query must be found in the instrument's name
   or symbol (prefix / plural / near-prefix), so *coverage* decides;
3. a full-phrase name prefix gives a small bonus, which separates
   "pc jeweller" from "pc ... something else";
4. only when nothing clears the coverage floor does a fuzzy match run.

Nothing is per-ticker: any instrument in the universe is scored the same way.
"""
from __future__ import annotations

import re
import threading

from sqlalchemy.orm import Session, load_only

from app.models.models import Instrument

# Identity-only scan rows, memoised per kind-tuple (see :func:`_scan_rows`).
_NAME_CACHE: dict[tuple[str, ...], list[Instrument]] = {}
_NAME_CACHE_LOCK = threading.Lock()

# Words that carry no entity information in a market question.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "company", "current",
    "do", "does", "for", "from", "give", "how", "in", "is", "it", "its", "latest",
    "me", "much", "now", "of", "on", "or", "please", "price", "quote", "rate",
    "share", "should", "show", "stock", "tell", "than", "that", "the", "their",
    "then", "there", "these", "this", "to", "today", "value", "was", "what",
    "when", "where", "which", "who", "why", "will", "with",
}

_KINDS = ("EQUITY", "INDEX", "ETF", "COMMODITY")


def words(text: str) -> list[str]:
    """Lower-case alphanumeric words with question filler removed."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return [w for w in cleaned.split() if w and w not in STOP_WORDS]


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _word_matches(token: str, target: str) -> bool:
    if token == target:
        return True
    if len(token) < 3 or len(target) < 3:
        return False
    if target.startswith(token) or token.startswith(target):
        return True
    # Plural / morphological variants only: "jewellers" vs "jeweller".
    # Short words must not match on a shared stem, or "sensex" would land on
    # "Senco Gold".
    prefix = _common_prefix(token, target)
    shortest = min(len(token), len(target))
    if shortest >= 7:
        return prefix >= shortest - 2
    if shortest >= 5:
        return prefix >= shortest - 1
    return False


def _coverage(q_words: list[str], row: Instrument) -> float:
    ticker = (row.symbol or "").lower()
    name_words = words(row.name or "")
    compact = "".join(name_words)
    hits = 0
    for token in q_words:
        if token == ticker or (len(token) <= 2 and compact.startswith(token)):
            hits += 1
        elif any(_word_matches(token, w) for w in name_words):
            hits += 1
    return hits / len(q_words)


def score(query_words: list[str], row: Instrument) -> float:
    """Coverage of the query in one instrument, with phrase/ticker bonuses."""
    if not query_words:
        return 0.0
    ticker = (row.symbol or "").lower()
    compact = "".join(words(row.name or ""))
    q_compact = "".join(query_words)
    base = _coverage(query_words, row)
    bonus = 0.0
    if q_compact and (ticker == q_compact or compact.startswith(q_compact)):
        bonus = 0.15
    if len(query_words) == 1 and ticker == query_words[0]:
        bonus = max(bonus, 0.2)
    return base + bonus


def clear_name_cache() -> None:
    """Drop the scan cache (called after a seed writes new instruments)."""
    with _NAME_CACHE_LOCK:
        _NAME_CACHE.clear()


def _scan_rows(db: Session, kinds: tuple[str, ...]) -> list[Instrument]:
    """Name/symbol/ticker columns only for the whole universe.

    ``Instrument.history`` and ``Instrument.meta`` are multi-kilobyte JSON
    columns. Loading full ORM objects for the ~2,500-row universe cost about
    five seconds locally (and far more on a shared vCPU) because SQLAlchemy
    deserialises every one of them just to compare a company name. Scoring only
    needs identity columns, so they are the only ones selected, and the result
    is memoised for repeated questions within one process.
    """
    key = tuple(sorted(kinds))
    with _NAME_CACHE_LOCK:
        hit = _NAME_CACHE.get(key)
    if hit is not None:
        return hit
    rows = (db.query(Instrument)
              .options(load_only(Instrument.id, Instrument.kind,
                                 Instrument.symbol, Instrument.name,
                                 Instrument.sector))
              .filter(Instrument.kind.in_(kinds))
              .all())
    if rows:
        with _NAME_CACHE_LOCK:
            _NAME_CACHE[key] = rows
    return rows


def resolve(db: Session, text: str, *, kinds: tuple[str, ...] = _KINDS,
            min_coverage: float = 0.6, fuzzy_floor: float = 0.7) -> Instrument | None:
    """Best instrument for a free-text query, or None."""
    raw = (text or "").strip()
    if not raw:
        return None
    exact = (db.query(Instrument)
               .filter(Instrument.kind.in_(kinds),
                       Instrument.symbol == raw.upper())
               .one_or_none())
    if exact is not None:
        return exact

    q_words = words(raw)
    if not q_words:
        return None
    rows = _scan_rows(db, kinds)
    if not rows:
        return None

    def best_for(window: list[str]) -> tuple[float, Instrument]:
        top = max(rows, key=lambda r: score(window, r))
        return score(window, top), top

    whole, top = best_for(q_words)
    if whole >= min_coverage:
        return top

    # A question carries filler around the entity ("what is the pe of
    # reliance industries"). Try contiguous spans, longest first, so the
    # company words win and a stray two-letter token never decides alone.
    for size in (4, 3, 2):
        if size >= len(q_words):
            continue
        need = min_coverage
        winner: tuple[float, Instrument] | None = None
        for i in range(len(q_words) - size + 1):
            sc, row = best_for(q_words[i:i + size])
            if sc >= need and (winner is None or sc > winner[0]):
                winner = (sc, row)
        if winner is not None:
            return winner[1]

    # Single words are only trusted when they land exactly (ticker or name
    # word), otherwise "pc" alone would resolve to the first PC company.
    for token in sorted(q_words, key=len, reverse=True):
        if len(token) < 2:
            continue
        sc, row = best_for([token])
        if sc >= 0.99:
            return row

    from app.services import fuzzy

    fallback = fuzzy.rank(raw, rows, lambda r: f"{r.symbol} {r.name}",
                          limit=1, floor=fuzzy_floor)
    return fallback[0] if fallback else None
