"""AI Quant Hub routes — four branded workspaces + shared transparency panel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import FREE_SOURCE_NOTE
from app.core.db import get_db
from app.services.ai_engine import (askdalal, corpus, llmFailoverRouter as LLM,
                                    rag, rangecast, sentiment, streetpulse, xray)

router = APIRouter(prefix="/quant-hub", tags=["ai quant hub"])


@router.get("/health")
def health(probe: bool = Query(False)):
    """Everything the hub's transparency strip needs, in one request."""
    llm = LLM.health(probe=probe)
    return {
        "platform": "Bharat Fintech Intelligence",
        "workspaces": [
            {"id": "rangecast", "name": "RangeCast AI",
             "fact": "80% probabilistic bands + F&O OI walls + delivery Z"},
            {"id": "streetpulse", "name": "StreetPulse Matrix",
             "fact": "FII/DII rupee flows vs delivery participation vs news tone"},
            {"id": "xray", "name": "4 PM Market X-Ray",
             "fact": "Institutional money-flow synthesis + volume shockers"},
            {"id": "ask-dalal", "name": "Ask Dalal AI",
             "fact": "Guarded text-to-SQL, grounded RAG, say-vs-do tracker"},
        ],
        "llm": llm,
        "sentiment": sentiment.finbert_status(),
        "rag": rag.encoder_status(),
        "data_note": FREE_SOURCE_NOTE,
        "disclaimer": ("All outputs are factual, statistical or educational. "
                       "Nothing is a buy/sell recommendation."),
    }


# ---------------------------------------------------------------- RangeCast
@router.get("/rangecast/{symbol}")
def rangecast_workspace(symbol: str,
                        horizon_days: int = Query(7, ge=1, le=60),
                        db: Session = Depends(get_db)):
    if horizon_days not in (7, 14, 21, 30):
        raise HTTPException(422, "horizon_days must be 7, 14, 21 or 30")
    try:
        return rangecast.build(db, symbol, horizon_days)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


# --------------------------------------------------------------- StreetPulse
@router.get("/streetpulse")
def streetpulse_workspace(limit: int = Query(12, ge=4, le=30),
                          db: Session = Depends(get_db)):
    return streetpulse.build(db, limit=limit)


# -------------------------------------------------------------------- X-Ray
@router.get("/xray")
def xray_workspace(db: Session = Depends(get_db)):
    return xray.build(db)


# ---------------------------------------------------------------- Ask Dalal
class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    symbol: str | None = Field(default=None, max_length=32)
    prefer_llm: bool = True


_INTENT_RULES = (
    ("credibility", ("credibility", "say-vs-do", "say vs do", "promised",
                     "promise", "management committed", "walk the talk")),
    ("filing-diff", ("filing diff", "filing changed", "what changed",
                     "year over year", "yoy change", "line item", "statement diff")),
    ("documents", ("annual report", "drhp", "prospectus", "risk factor",
                   "filing says", "document", "notes to accounts", "management commentary")),
)


def _intent(question: str, symbol: str | None) -> str:
    q = question.lower()
    for name, cues in _INTENT_RULES:
        if any(c in q for c in cues):
            return name
    if symbol and any(c in q for c in ("revenue", "margin", "debt", "cash flow")):
        return "documents"
    return "screener"


@router.post("/ask-dalal")
def ask_dalal(body: AskBody, db: Session = Depends(get_db)):
    intent = _intent(body.question, body.symbol)
    if intent == "credibility":
        if not body.symbol:
            raise HTTPException(422, "A symbol is required for the credibility tracker.")
        try:
            return {"intent": intent,
                    "data": askdalal.credibility(db, body.symbol)}
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
    if intent == "filing-diff":
        if not body.symbol:
            raise HTTPException(422, "A symbol is required for a filing diff.")
        try:
            return {"intent": intent,
                    "data": askdalal.filing_diff(db, body.symbol)}
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
    if intent == "documents":
        return {"intent": intent,
                "data": askdalal.answer_documents(body.question, db,
                                                  symbol=body.symbol,
                                                  prefer_llm=body.prefer_llm)}
    return {"intent": "screener",
            "data": askdalal.ask_screener(body.question, db,
                                          prefer_llm=body.prefer_llm)}


@router.get("/ask-dalal/credibility/{symbol}")
def credibility(symbol: str, db: Session = Depends(get_db)):
    try:
        return askdalal.credibility(db, symbol)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/ask-dalal/filing-diff/{symbol}")
def filing_diff(symbol: str,
                granularity: str = Query("annual", pattern="^(annual|quarterly)$"),
                db: Session = Depends(get_db)):
    try:
        return askdalal.filing_diff(db, symbol, granularity)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/ask-dalal/corpus")
def corpus_stats(db: Session = Depends(get_db)):
    return {**rag.corpus_stats(db), "views": askdalal.ensure_views(),
            "llm_configured": LLM.configured()}


class CorpusBody(BaseModel):
    symbols: list[str] | None = None
    max_symbols: int | None = Field(default=None, ge=1, le=300)


@router.post("/ask-dalal/corpus/build")
def corpus_build(body: CorpusBody | None = None, db: Session = Depends(get_db)):
    body = body or CorpusBody()
    return corpus.build(db, symbols=body.symbols, max_symbols=body.max_symbols)


class DocSearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    symbol: str | None = None
    k: int = Field(default=6, ge=1, le=20)


@router.post("/ask-dalal/documents/search")
def document_search(body: DocSearchBody, db: Session = Depends(get_db)):
    return rag.search(db, body.query, symbol=body.symbol, k=body.k)


@router.post("/llm/probe")
def llm_probe():
    return LLM.health(probe=True)


@router.get("/disclaimer")
def disclaimer():
    return {
        "banner": "NOT A BUY OR SELL RECOMMENDATION",
        "detail": ("RangeCast bands are a statistical projection from realised "
                   "volatility; OI walls are exchange positioning; delivery "
                   "Z-scores compare a stock with its own history; StreetPulse "
                   "tone is a language model applied to public headlines; X-Ray "
                   "sector tilts are participation measures, not rupee flows. "
                   "Ask Dalal answers are grounded in the platform's stored data "
                   "and clearly label any LLM-generated text. None of this is "
                   "investment advice."),
    }
