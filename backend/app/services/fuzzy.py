"""Small, dependency-free fuzzy text matching.

Used by the global search and the mutual-fund screener so a user can type what
they remember instead of the exact legal name. Examples that must work:

    "nestec"  → Nestle India, Nippon India Nasdaq 100 …
    "nasdak"  → Motilal Oswal Nasdaq 100, ICICI Prudential NASDAQ 100, MON100
    "paras"   → Paras Defence and Space Technologies
    "orient"  → Orient Cement / Orient Electric / Orient Paper …

The matcher is deliberately conservative: substring hits always win, and a
fuzzy match must share the leading characters and clear a similarity floor.
That prevents a short query from matching half the database.
"""
from __future__ import annotations

import difflib
import re

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")

# Legal/fund-name noise that should never decide a match.
STOPWORDS = {
    "the", "of", "and", "ltd", "limited", "pvt", "private", "india",
    "fund", "funds", "scheme", "plan", "growth", "direct", "regular",
    "option", "open", "ended", "mutual", "asset", "management", "company",
}


def norm(text: str) -> str:
    s = (text or "").lower().replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def tokens(text: str) -> list[str]:
    return [t for t in norm(text).split() if t]


def _significant(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS] or tokens(text)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        # Reward containment, scaled by how much of the longer word is covered.
        # A 3-letter fragment inside a long name is not a match ("par" inside
        # "paras" is, but "par" inside "parentals" is not).
        cover = min(len(a), len(b)) / max(len(a), len(b))
        if cover >= 0.7:
            return 0.80 + 0.19 * cover
        return difflib.SequenceMatcher(None, a, b).ratio()
    return difflib.SequenceMatcher(None, a, b).ratio()


_PHONETIC_MAP = str.maketrans({
    "c": "k", "q": "k", "x": "ks",
    "d": "t", "z": "s",
    "b": "p", "g": "j", "v": "w",
})


def _skeleton(word: str) -> str:
    """Consonant skeleton so spelling variants collapse to one key.

    ``nestec`` and ``nasdaq`` both become ``nstk``; ``nasdak`` too. That is what
    lets a user type what a fund name sounds like and still find the scheme.
    """
    w = word.translate(_PHONETIC_MAP)
    w = w.replace("ph", "f")
    out = [w[0]] if w else []
    for ch in w[1:]:
        if ch not in "aeiouy" and (not out or out[-1] != ch):
            out.append(ch)
    return "".join(out)


def _token_similarity(term: str, word: str) -> float:
    """Best of direct similarity, shared prefix and phonetic skeleton.

    Indian scheme names put the AMC first ("Motilal Oswal … Nasdaq 100"), so a
    token such as "nasdak" usually compares against "nasdaq", not the whole
    name. Short words (``ne``, ``de``) are ignored: they otherwise swallow every
    query whose first two letters happen to appear in a 60-character name.
    """
    if len(word) < 3:
        return 0.0
    if len(term) >= 3 and term[:3] == word[:3]:
        s = similarity(term, word)
        return s if s >= 0.82 else 0.0
    if len(term) >= 4 and term[:2] == word[:2]:
        s = similarity(term, word)
        # A shared first two letters is weak evidence ("nestec" vs "next");
        # only accept it when the rest of the word really is close.
        return s if s >= 0.78 else 0.0
    if len(term) >= 4 and _skeleton(term) == _skeleton(word):
        return 0.9
    return 0.0


def score(term: str, text: str) -> float:
    """0 = no match, 1 = exact full-name match.

    Tiers:
      1.00  whole phrase appears verbatim
      0.92  every significant query token appears somewhere in the name
      0.55–0.90  one or more query tokens fuzzily match a name token
    """
    q = norm(term)
    n = norm(text)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if q in n:
        return 1.0 - 0.08 * (len(q) / max(len(n), 1))

    q_tokens = _significant(q)
    n_tokens = _significant(n)
    if not q_tokens or not n_tokens:
        return 0.0

    # Every query token appears as a substring of some name token.
    if all(any(qt in nt for nt in n_tokens) for qt in q_tokens):
        return 0.92

    # Fuzzy: each query token must find a decent partner. The weakest partner
    # decides the score, so "orient cement" does not match every Orient company.
    best_per_token = []
    for qt in q_tokens:
        best = max((_token_similarity(qt, nt) for nt in n_tokens), default=0.0)
        best_per_token.append(best)
    weakest = min(best_per_token)
    if weakest >= 0.74:
        return round(0.55 + 0.35 * weakest, 3)
    if len(best_per_token) >= 2 and min(best_per_token[:-1]) >= 0.85:
        # Allow the trailing token to be a partial word ("nasdak 100"). A
        # single-token query must never land here: there is no "rest" of the
        # query to corroborate it.
        return round(0.55 + 0.30 * weakest, 3)
    return 0.0


def rank(term: str, items, text_of, limit: int = 12,
         floor: float = 0.55, prefilter: bool = True):
    """Score and sort ``items`` by how well their text matches ``term``.

    ``prefilter`` cheaply drops names whose first two normalised characters do
    not match the query's. That keeps a 38,000-scheme scan well under a frame
    while still letting the fuzzy tier find "nestec" → "Nestle".
    """
    q = norm(term)
    head = q[:2]
    scored = []
    for item in items:
        text = text_of(item)
        if prefilter and head and head not in norm(text):
            continue
        s = score(q, text)
        if s >= floor:
            scored.append((s, item))
    if not scored and prefilter:
        return rank(term, items, text_of, limit=limit, floor=floor,
                    prefilter=False)
    scored.sort(key=lambda pair: -pair[0])
    return [item for _, item in scored[:limit]]
