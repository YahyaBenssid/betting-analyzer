"""
FastAPI backend — déployé sur Railway.
Expose les endpoints consommés par le frontend Next.js sur Vercel.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

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

# ------------------------------------------------------------------ #
# In-memory cache — évite de brûler les requêtes API (500/mois free)
_CACHE_TTL = 900  # 15 minutes

_cache: dict[str, dict[str, Any]] = {}

def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None

def _cache_set(key: str, data: Any) -> None:
    _cache[key] = {"ts": time.time(), "data": data}


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
# Demo data — used when no API keys are configured

import random
from datetime import datetime, timedelta

_FOOTBALL_MATCHES = [
    ("Real Madrid", "Barcelona", "La Liga"),
    ("Manchester City", "Arsenal", "Premier League"),
    ("PSG", "Marseille", "Ligue 1"),
    ("Bayern Munich", "Borussia Dortmund", "Bundesliga"),
    ("Inter Milan", "AC Milan", "Serie A"),
    ("Atletico Madrid", "Sevilla", "La Liga"),
    ("Liverpool", "Chelsea", "Premier League"),
    ("Juventus", "Napoli", "Serie A"),
    ("Benfica", "Porto", "Primeira Liga"),
    ("Ajax", "PSV", "Eredivisie"),
    ("Leicester City", "Tottenham", "Premier League"),
    ("Bayer Leverkusen", "RB Leipzig", "Bundesliga"),
    ("Lyon", "Monaco", "Ligue 1"),
    ("Roma", "Lazio", "Serie A"),
    ("Celtic", "Rangers", "Scottish Premiership"),
]

_TENNIS_MATCHES = [
    ("Carlos Alcaraz", "Novak Djokovic", "ATP Masters"),
    ("Jannik Sinner", "Daniil Medvedev", "ATP Tour"),
    ("Rafael Nadal", "Stefanos Tsitsipas", "Roland Garros"),
]

_BASKETBALL_MATCHES = [
    ("LA Lakers", "Boston Celtics", "NBA"),
    ("Golden State Warriors", "Miami Heat", "NBA"),
    ("Milwaukee Bucks", "Phoenix Suns", "NBA"),
]

def _make_demo_data(sport_filter, bankroll: float, min_ev: float, min_confidence: float):
    rng = random.Random(int(datetime.now().timestamp() / 300))  # changes every 5 min

    sport_pool = {
        Sport.FOOTBALL: _FOOTBALL_MATCHES,
        Sport.TENNIS: _TENNIS_MATCHES,
        Sport.BASKETBALL: _BASKETBALL_MATCHES,
        None: _FOOTBALL_MATCHES + _TENNIS_MATCHES + _BASKETBALL_MATCHES,
    }
    pool = sport_pool.get(sport_filter, _FOOTBALL_MATCHES)
    matches_sample = rng.sample(pool, min(len(pool), 12))

    value_bets: list[ValueBetOut] = []
    arbitrages: list[ArbitrageOut] = []

    outcomes_map = {
        "La Liga": ["1X2"], "Premier League": ["1X2"], "Ligue 1": ["1X2"],
        "Bundesliga": ["1X2"], "Serie A": ["1X2"], "ATP Masters": ["H2H"],
        "ATP Tour": ["H2H"], "Roland Garros": ["H2H"], "NBA": ["H2H"],
        "Primeira Liga": ["1X2"], "Eredivisie": ["1X2"],
        "Scottish Premiership": ["1X2"], "Scottish premiership": ["1X2"],
    }

    for i, (home, away, league) in enumerate(matches_sample):
        sport_val = "football"
        if league in ("ATP Masters", "ATP Tour", "Roland Garros"):
            sport_val = "tennis"
        elif league == "NBA":
            sport_val = "basketball"

        base_ev = rng.uniform(2.5, 18.0)
        odd = round(rng.uniform(1.5, 4.8), 2)
        kelly = round((base_ev / 100) / (odd - 1), 4)
        stake = round(bankroll * kelly * 0.25, 2)
        conf = round(max(30, min(90, 85 - (odd - 1.5) * 12 + rng.uniform(-8, 8))), 1)
        source = rng.choice(["real_stats", "real_stats", "poisson_avg", "fair_prob"])
        is_rec = conf >= 65 and base_ev >= 5

        if base_ev >= min_ev and conf >= min_confidence:
            outcomes_list = ["Domicile", "Nul", "Extérieur"] if sport_val == "football" else [home, away]
            outcome = rng.choice(outcomes_list)
            value_bets.append(ValueBetOut(
                match_id=f"demo_{i}",
                home_team=home, away_team=away, league=league, sport=sport_val,
                market="1X2" if sport_val == "football" else "H2H",
                outcome=outcome, odd_value=odd,
                ev_pct=round(base_ev, 2), kelly_pct=round(kelly * 100, 2),
                stake=stake, confidence=conf, stats_source=source, is_recommended=is_rec,
            ))

        # ~25% chance of arbitrage per match
        if rng.random() < 0.25:
            profit = round(rng.uniform(0.5, 3.5), 2)
            o1 = round(rng.uniform(1.8, 2.5), 2)
            o2 = round(rng.uniform(1.8, 2.5), 2)
            s1 = round(bankroll / (1 + o1 / o2), 2)
            s2 = round(bankroll - s1, 2)
            arb_profit = round(min(s1 * o1, s2 * o2) - bankroll, 2)
            arbitrages.append(ArbitrageOut(
                match_id=f"arb_{i}", home_team=home, away_team=away, league=league,
                market="1X2", profit_pct=profit, guaranteed_profit=max(0, arb_profit),
                outcomes=[home, away], odds=[o1, o2], stakes=[s1, s2],
                bookmakers=["1xBet", rng.choice(["Betway", "Unibet", "Bet365", "Winamax"])],
            ))

    value_bets.sort(key=lambda x: x.ev_pct, reverse=True)
    return value_bets[:50], arbitrages, len(matches_sample)


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

    cache_key = f"{sport}:{live}"
    matches = _cache_get(cache_key)
    if matches is None:
        try:
            matches = await _fetch(sport_filter, live)
            if matches:
                _cache_set(cache_key, matches)
        except Exception:
            pass

    # No real data available → use demo mode
    if not matches:
        value_bets, arbitrages, total = _make_demo_data(sport_filter, bankroll, min_ev, min_confidence)
        return ScanResponse(value_bets=value_bets, arbitrages=arbitrages,
                            total_matches=total, sport=sport, bankroll=bankroll)

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
