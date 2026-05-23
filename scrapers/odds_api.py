"""
Client pour The Odds API (https://the-odds-api.com).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from config import settings
from models.bet import Sport

from .base_scraper import BaseScraper, ScrapedMatch, ScrapedOdd, ScraperError

# Mapping sport → clés The Odds API
SPORT_KEY_MAP = {
    Sport.FOOTBALL: [
        "soccer_epl",                        # Premier League
        "soccer_spain_la_liga",              # La Liga
        "soccer_germany_bundesliga",         # Bundesliga
        "soccer_italy_serie_a",              # Serie A
        "soccer_france_ligue1",              # Ligue 1
        "soccer_uefa_champs_league",         # Champions League
        "soccer_uefa_europa_league",         # Europa League
        "soccer_portugal_primeira_liga",     # Primeira Liga
        "soccer_netherlands_eredivisie",     # Eredivisie
        "soccer_england_efl_champ",          # Championship
        "soccer_turkey_super_league",        # Süper Lig
        "soccer_brazil_campeonato",          # Brasileirão
        "soccer_usa_mls",                    # MLS
        "soccer_argentina_primera_division", # Primera División
        "soccer_mexico_ligamx",              # Liga MX
    ],
    Sport.TENNIS: [
        "tennis_atp_french_open",
        "tennis_wta_french_open",
        "tennis_atp_rome",
        "tennis_atp_queens",
        "tennis_atp_halle",
        "tennis_wta_rome",
        "tennis_atp_us_open",
        "tennis_wta_us_open",
        "tennis_atp_wimbledon",
        "tennis_wta_wimbledon",
    ],
    Sport.BASKETBALL: [
        "basketball_nba",
        "basketball_euroleague",
        "basketball_ncaab",
    ],
    Sport.HOCKEY: [
        "icehockey_nhl",
    ],
}

# Marchés demandés à l'API
_MARKETS = "h2h,totals,spreads"

BASE_URL = "https://api.the-odds-api.com/v4"


class OddsAPIClient(BaseScraper):
    """Client HTTP pour The Odds API."""

    def __init__(self, api_key: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key or settings.odds_api_key
        if not self.api_key:
            logger.warning("[OddsAPI] Aucune clé API — les requêtes échoueront")

    def name(self) -> str:
        return "the-odds-api"

    async def fetch_matches(
        self,
        sport: Optional[Sport] = None,
        live_only: bool = False,
    ) -> list[ScrapedMatch]:
        if not self.api_key:
            raise ScraperError("ODDS_API_KEY manquante")

        sports_to_fetch = (
            SPORT_KEY_MAP.get(sport, []) if sport
            else [key for keys in SPORT_KEY_MAP.values() for key in keys]
        )

        # Requêtes parallèles avec semaphore (max 5 simultanées)
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(sk: str) -> list[ScrapedMatch]:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        return await self._fetch_sport(client, sk)
                except Exception as exc:
                    logger.warning(f"[OddsAPI] {sk} ignoré: {exc}")
                    return []

        results = await asyncio.gather(*[fetch_one(sk) for sk in sports_to_fetch])
        all_matches = [m for batch in results for m in batch]
        logger.info(f"[OddsAPI] {len(all_matches)} matchs — {len(sports_to_fetch)} ligues")
        return all_matches

    async def _fetch_sport(self, client: httpx.AsyncClient, sport_key: str) -> list[ScrapedMatch]:
        url = f"{BASE_URL}/sports/{sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "eu",
            "markets": _MARKETS,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        resp = await client.get(url, params=params)
        if resp.status_code == 404:
            return []  # tournoi inactif
        resp.raise_for_status()

        remaining = resp.headers.get("x-requests-remaining", "?")
        logger.debug(f"[OddsAPI] {sport_key} — requêtes restantes: {remaining}")
        return self._parse_response(resp.json(), sport_key)

    def _parse_response(self, data: list[dict], sport_key: str) -> list[ScrapedMatch]:
        sport = self._infer_sport(sport_key)
        matches = []
        for event in data:
            try:
                match = self._parse_event(event, sport)
                if match:
                    matches.append(match)
            except Exception as exc:
                logger.debug(f"[OddsAPI] Event ignoré: {exc}")
        return matches

    @staticmethod
    def _parse_event(event: dict, sport: Sport) -> Optional[ScrapedMatch]:
        match_id = event.get("id", "")
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        league = event.get("sport_title", "")
        start_str = event.get("commence_time", "")

        if not home or not away:
            return None

        try:
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            start_time = datetime.now(tz=timezone.utc)

        markets: dict[str, list[ScrapedOdd]] = {}

        for bookmaker in event.get("bookmakers", []):
            bk_name = bookmaker.get("title", "unknown")
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                market_label, odds_list = OddsAPIClient._parse_market(
                    market_key, market.get("outcomes", []), home, away, bk_name
                )
                if market_label and odds_list and market_label not in markets:
                    markets[market_label] = odds_list

        if not markets:
            return None

        return ScrapedMatch(
            match_id=match_id,
            home_team=home,
            away_team=away,
            sport=sport,
            league=league,
            start_time=start_time,
            markets=markets,
            source="the-odds-api",
        )

    @staticmethod
    def _parse_market(
        key: str,
        outcomes: list[dict],
        home: str,
        away: str,
        bk_name: str,
    ) -> tuple[str, list[ScrapedOdd]]:
        if key == "h2h":
            return OddsAPIClient._parse_h2h(outcomes, home, away, bk_name)
        if key == "totals":
            return OddsAPIClient._parse_totals(outcomes, bk_name)
        if key == "spreads":
            return OddsAPIClient._parse_spreads(outcomes, home, away, bk_name)
        return "", []

    @staticmethod
    def _parse_h2h(outcomes, home, away, bk_name) -> tuple[str, list[ScrapedOdd]]:
        odds_list = []
        for o in outcomes:
            name = o.get("name", "")
            price = float(o.get("price", 0))
            if price <= 1.0:
                continue
            if name == home:
                label = "Domicile"
            elif name == away:
                label = "Extérieur"
            else:
                label = "Nul"
            odds_list.append(ScrapedOdd(label, price, bk_name))
        return ("1X2", odds_list) if len(odds_list) >= 2 else ("", [])

    @staticmethod
    def _parse_totals(outcomes, bk_name) -> tuple[str, list[ScrapedOdd]]:
        odds_list = []
        point = ""
        for o in outcomes:
            name = o.get("name", "")          # "Over" or "Under"
            price = float(o.get("price", 0))
            point = o.get("point", "")        # e.g. 2.5
            if price <= 1.0:
                continue
            label = f"{name} {point}" if point else name
            odds_list.append(ScrapedOdd(label, price, bk_name))
        label = f"O/U {point}" if point else "O/U"
        return (label, odds_list) if len(odds_list) == 2 else ("", [])

    @staticmethod
    def _parse_spreads(outcomes, home, away, bk_name) -> tuple[str, list[ScrapedOdd]]:
        odds_list = []
        for o in outcomes:
            name = o.get("name", "")
            price = float(o.get("price", 0))
            if price <= 1.0:
                continue
            try:
                pt = float(o.get("point", 0))
                pt_str = f"{pt:+.1f}"
            except (TypeError, ValueError):
                pt_str = ""
            if name == home:
                label = f"Dom {pt_str}" if pt_str else "Dom HC"
            elif name == away:
                label = f"Ext {pt_str}" if pt_str else "Ext HC"
            else:
                label = name
            odds_list.append(ScrapedOdd(label, price, bk_name))
        return ("Handicap", odds_list) if len(odds_list) == 2 else ("", [])

    @staticmethod
    def _infer_sport(sport_key: str) -> Sport:
        if sport_key.startswith("soccer"):
            return Sport.FOOTBALL
        if sport_key.startswith("tennis"):
            return Sport.TENNIS
        if sport_key.startswith("basketball"):
            return Sport.BASKETBALL
        if sport_key.startswith("icehockey"):
            return Sport.HOCKEY
        return Sport.OTHER
