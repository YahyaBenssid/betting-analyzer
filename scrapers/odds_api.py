"""
Client pour The Odds API (https://the-odds-api.com).
Utilisé comme fallback si 1XBET est inaccessible.
Clé gratuite : 500 requêtes/mois.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from config import settings
from models.bet import Sport

from .base_scraper import BaseScraper, ScrapedMatch, ScrapedOdd, ScraperError

# Mapping sport → clé The Odds API
SPORT_KEY_MAP = {
    Sport.FOOTBALL: [
        "soccer_epl",                       # Premier League
        "soccer_spain_la_liga",             # La Liga
        "soccer_germany_bundesliga",        # Bundesliga
        "soccer_italy_serie_a",             # Serie A
        "soccer_france_ligue1",             # Ligue 1
        "soccer_uefa_champs_league",        # Champions League
        "soccer_uefa_europa_league",        # Europa League
        "soccer_portugal_primeira_liga",    # Primeira Liga
        "soccer_netherlands_eredivisie",    # Eredivisie
        "soccer_england_efl_champ",         # Championship
        "soccer_turkey_super_league",       # Süper Lig
        "soccer_brazil_campeonato",         # Brasileirão
        "soccer_usa_mls",                   # MLS
        "soccer_argentina_primera_division",# Primera División
        "soccer_mexico_ligamx",             # Liga MX
    ],
    Sport.TENNIS: [
        "tennis_atp_french_open",           # Roland Garros ATP
        "tennis_wta_french_open",           # Roland Garros WTA
        "tennis_atp_rome",                  # Rome Masters
        "tennis_atp_queens",                # Queens Club
        "tennis_atp_halle",                 # Halle Open
        "tennis_wta_rome",                  # WTA Rome
        "tennis_atp_us_open",               # US Open
        "tennis_wta_us_open",               # WTA US Open
        "tennis_atp_wimbledon",             # Wimbledon
        "tennis_wta_wimbledon",             # Wimbledon WTA
    ],
    Sport.BASKETBALL: [
        "basketball_nba",                   # NBA
        "basketball_nba_championship_winner",  # NBA futures
        "basketball_euroleague",            # EuroLeague
        "basketball_ncaab",                 # NCAA Basketball
    ],
    Sport.HOCKEY: ["icehockey_nhl", "icehockey_nhl_championship_winner"],
}

BASE_URL = "https://api.the-odds-api.com/v4"


class OddsAPIClient(BaseScraper):
    """Client HTTP pour The Odds API (fallback officiel)."""

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
            raise ScraperError("ODDS_API_KEY manquante dans .env")

        sports_to_fetch = SPORT_KEY_MAP.get(sport, []) if sport else [
            key for keys in SPORT_KEY_MAP.values() for key in keys
        ]

        all_matches: list[ScrapedMatch] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for sport_key in sports_to_fetch:
                try:
                    matches = await self._retry(
                        lambda sk=sport_key: self._fetch_sport(client, sk),
                        label=f"OddsAPI/{sport_key}",
                    )
                    all_matches.extend(matches)
                    await self._polite_delay()
                except ScraperError as exc:
                    logger.error(f"[OddsAPI] {exc}")

        logger.info(f"[OddsAPI] {len(all_matches)} matchs récupérés")
        return all_matches

    async def _fetch_sport(self, client: httpx.AsyncClient, sport_key: str) -> list[ScrapedMatch]:
        url = f"{BASE_URL}/sports/{sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        resp = await client.get(url, params=params)
        resp.raise_for_status()

        remaining = resp.headers.get("x-requests-remaining", "?")
        logger.debug(f"[OddsAPI] {sport_key} — requêtes restantes: {remaining}")

        return self._parse_response(resp.json(), sport_key)

    def _parse_response(self, data: list[dict], sport_key: str) -> list[ScrapedMatch]:
        matches = []
        sport = self._infer_sport(sport_key)

        for event in data:
            try:
                match = self._parse_event(event, sport, sport_key)
                if match:
                    matches.append(match)
            except Exception as exc:
                logger.debug(f"[OddsAPI] Event ignoré: {exc}")

        return matches

    @staticmethod
    def _parse_event(event: dict, sport: Sport, sport_key: str) -> Optional[ScrapedMatch]:
        match_id = event.get("id", "")
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        league = event.get("sport_title", sport_key)
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
                if market_key != "h2h":
                    continue

                odds_list = []
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = float(outcome.get("price", 0))
                    if price <= 1.0:
                        continue

                    # Normalise les noms d'outcomes
                    if name == home:
                        label = "Home"
                    elif name == away:
                        label = "Away"
                    else:
                        label = "Draw"

                    odds_list.append(ScrapedOdd(label, price, bk_name))

                if odds_list:
                    markets["1X2"] = odds_list
                    break  # Prend le premier bookmaker disponible

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
