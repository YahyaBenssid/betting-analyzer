"""
FastAPI backend — déployé sur Railway.
Expose les endpoints consommés par le frontend Next.js sur Vercel.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Permet d'importer les modules du projet parent
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from models.bet import Sport
from analyzers.value_bet_detector import ValueBetDetector
from analyzers.arbitrage_detector import ArbitrageDetector
from analyzers.confidence_scorer import ConfidenceScorer
from utils.logger import setup_logging

setup_logging("INFO")

app = FastAPI(
    title="Betting Analyzer API",
    description="Value bets & arbitrage detection",
    version="1.0.0",
)

# CORS — autorise le domaine Vercel et localhost
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://*.vercel.app",
    os.getenv("FRONTEND_URL", ""),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restreindre en prod avec ALLOWED_ORIGINS
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ #
# Schémas de réponse

class OddOut(BaseModel):
    outcome: str
    value: float
    implied_prob: float
    fair_prob: float
    real_prob: float

class ValueBetOut(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    sport: str
    market: str
    outcome: str
    odd_value: float
    ev_pct: float
    kelly_pct: float
    stake: float
    confidence: float
    stats_source: str
    is_recommended: bool

class ArbitrageOut(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    market: str
    profit_pct: float
    guaranteed_profit: float
    outcomes: list[str]
    odds: list[float]
    stakes: list[float]
    bookmakers: list[str]

class ScanResponse(BaseModel):
    value_bets: list[ValueBetOut]
    arbitrages: list[ArbitrageOut]
    total_matches: int
    sport: str
    bankroll: float

class HealthResponse(BaseModel):
    status: str
    has_odds_api_key: bool
    has_football_data_key: bool


# ------------------------------------------------------------------ #
# Helper fetch

async def _fetch(sport_filter, live: bool):
    try:
        from scrapers.xbet_scraper import XBetScraper
        scraper = XBetScraper()
        matches = await scraper.fetch_matches(sport=sport_filter, live_only=live)
        if matches:
            return matches
    except Exception:
        pass

    from scrapers.odds_api import OddsAPIClient
    client = OddsAPIClient()
    return await client.fetch_matches(sport=sport_filter, live_only=live)


_SPORT_MAP = {
    "football": Sport.FOOTBALL,
    "tennis": Sport.TENNIS,
    "basketball": Sport.BASKETBALL,
    "hockey": Sport.HOCKEY,
    "all": None,
}


# ------------------------------------------------------------------ #
# Endpoints

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        has_odds_api_key=bool(settings.odds_api_key),
        has_football_data_key=bool(settings.football_data_api_key),
    )


@app.get("/api/scan", response_model=ScanResponse)
async def scan(
    sport: str = Query("football", enum=list(_SPORT_MAP.keys())),
    min_ev: float = Query(3.0, ge=0),
    min_confidence: float = Query(55.0, ge=0, le=100),
    bankroll: float = Query(1000.0, gt=0),
    live: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    sport_filter = _SPORT_MAP.get(sport)

    try:
        matches = await _fetch(sport_filter, live)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Données indisponibles: {exc}")

    if not matches:
        return ScanResponse(value_bets=[], arbitrages=[], total_matches=0, sport=sport, bankroll=bankroll)

    use_poisson = (sport == "football")
    detector = ValueBetDetector(bankroll=bankroll, use_poisson=use_poisson)
    results = detector.analyze(matches)
    ConfidenceScorer().score_all(results)

    filtered = [
        r for r in results
        if r.ev.ev_pct >= min_ev and r.confidence_score >= min_confidence
    ][:limit]

    value_bets = [
        ValueBetOut(
            match_id=r.match.match_id,
            home_team=r.match.home_team,
            away_team=r.match.away_team,
            league=r.match.league,
            sport=r.match.sport.value,
            market=r.market_name,
            outcome=r.outcome,
            odd_value=round(r.odd_value, 2),
            ev_pct=round(r.ev.ev_pct, 2),
            kelly_pct=round(r.kelly.fractional_kelly * 100, 2),
            stake=round(r.kelly.stake_amount, 2),
            confidence=round(r.confidence_score, 1),
            stats_source=r.stats_source,
            is_recommended=r.is_recommended,
        )
        for r in filtered
    ]

    arb_detector = ArbitrageDetector(bankroll=bankroll)
    arbs = arb_detector.detect(matches)

    arbitrages = [
        ArbitrageOut(
            match_id=a.match.match_id,
            home_team=a.match.home_team,
            away_team=a.match.away_team,
            league=a.match.league,
            market=a.market_name,
            profit_pct=round(a.profit_pct, 2),
            guaranteed_profit=round(a.guaranteed_profit, 2),
            outcomes=a.outcomes,
            odds=a.odds,
            stakes=[round(s, 2) for s in a.optimal_stakes],
            bookmakers=a.bookmakers,
        )
        for a in arbs
    ]

    return ScanResponse(
        value_bets=value_bets,
        arbitrages=arbitrages,
        total_matches=len(matches),
        sport=sport,
        bankroll=bankroll,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
