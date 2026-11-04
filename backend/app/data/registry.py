"""Adapter registry — the single place that maps a data need to a provider.
When broker feeds (Dhan/Groww/Upstox) are attached later, only this registry
changes; routers and services never import an adapter directly."""
from dataclasses import dataclass
from enum import Enum


class SourceKind(str, Enum):
    NSE_LIVE = "nse-live"
    YAHOO_HISTORY = "yahoo-history"
    MFAPI = "mfapi-amfi"
    FREE_PROXY = "free-proxy"


@dataclass
class SourceInfo:
    kind: SourceKind
    name: str
    swappable_to: list[str]


REGISTRY = {
    "quotes": SourceInfo(SourceKind.NSE_LIVE, "NSE via session client",
                         ["Dhan", "Groww", "Upstox", "Angel One"]),
    "history": SourceInfo(SourceKind.YAHOO_HISTORY, "Yahoo Finance EOD",
                          ["Dhan historical", "Kite historical"]),
    "funds": SourceInfo(SourceKind.MFAPI, "mfapi.in + AMFI mapping",
                        ["AMFI official", "RapidAPI AMFI+"]),
    "derivatives": SourceInfo(SourceKind.NSE_LIVE, "NSE option-chain API",
                              ["broker chain APIs"]),
    "commodities": SourceInfo(SourceKind.FREE_PROXY, "Yahoo international front month",
                              ["MCX feed via broker"]),
    "ipos": SourceInfo(SourceKind.FREE_PROXY, "NSE IPO central (throttled)",
                       ["BSE IPO API", "Chittorgarh"]),
}
