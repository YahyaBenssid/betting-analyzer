"""
Scraper 1XBET via Playwright.

Stratégie :
  1. Ouvrir la page en mode headless avec interception réseau.
  2. Capturer les appels XHR vers l'API interne de 1XBET
     (endpoints /LineFeed/, /LiveFeed/, /LineFeedSports/).
  3. Parser la réponse JSON pour extraire cotes et matchs.
  4. Fallback vers OddsAPIClient si 1XBET est inaccessible.

Note légale : Scraping à des fins analytiques personnelles uniquement.
Ne pas utiliser en violation des CGU de 1XBET.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from models.bet import Sport

from .base_scraper import BaseScraper, ScrapedMatch, ScrapedOdd, ScraperError

# --- Rotation de User-Agents ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Endpoints API interne 1XBET (reverse-engineered — peuvent changer)
XBET_BASE = "https://1xbet.com"
XBET_LINE_FEED = "/LineFeed/GetCategoryByCountry"
XBET_LIVE_FEED = "/LiveFeed/Get1x2_VZip"

SPORT_ID_MAP = {
    Sport.FOOTBALL: 1,
    Sport.TENNIS: 3,
    Sport.BASKETBALL: 2,
    Sport.HOCKEY: 4,
}


class XBetScraper(BaseScraper):
    """Scraper Playwright pour 1XBET avec interception XHR."""

    def name(self) -> str:
        return "1xbet"

    async def fetch_matches(
        self,
        sport: Optional[Sport] = None,
        live_only: bool = False,
    ) -> list[ScrapedMatch]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ScraperError(
                "playwright non installé. Exécutez: pip install playwright && playwright install chromium"
            )

        captured_data: list[dict] = []

        async def _scrape() -> list[ScrapedMatch]:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    locale="fr-FR",
                    timezone_id="Europe/Paris",
                )
                page = await context.new_page()

                # Interception des réponses XHR de l'API interne
                async def handle_response(response):
                    url = response.url
                    if any(ep in url for ep in ["/LineFeed/", "/LiveFeed/", "GetCategoryByCountry"]):
                        try:
                            body = await response.json()
                            if isinstance(body, dict) and "Value" in body:
                                captured_data.append(body)
                                logger.debug(f"XHR capturé: {url[:80]}")
                        except Exception:
                            pass

                page.on("response", handle_response)

                target_url = f"{XBET_BASE}/fr/line/football" if not live_only else f"{XBET_BASE}/fr/live/football"
                logger.info(f"[1xbet] Navigation vers {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=30_000)
                await self._polite_delay()

                # Scroll pour charger plus de matchs
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await self._polite_delay()

                await browser.close()

            return self._parse_captured(captured_data, sport)

        return await self._retry(_scrape, label="fetch_matches")

    def _parse_captured(
        self, raw_responses: list[dict], sport_filter: Optional[Sport]
    ) -> list[ScrapedMatch]:
        """Parse les réponses JSON interceptées de l'API 1XBET."""
        matches: list[ScrapedMatch] = []

        for response in raw_responses:
            events = response.get("Value", [])
            if not isinstance(events, list):
                continue

            for event in events:
                try:
                    match = self._parse_event(event, sport_filter)
                    if match:
                        matches.append(match)
                except Exception as exc:
                    logger.debug(f"[1xbet] Event ignoré: {exc}")

        logger.info(f"[1xbet] {len(matches)} matchs parsés")
        return matches

    def _parse_event(self, event: dict, sport_filter: Optional[Sport]) -> Optional[ScrapedMatch]:
        """Parse un event individuel de l'API 1XBET."""
        sport_id = event.get("SI", 0)
        sport = self._map_sport_id(sport_id)
        if sport_filter and sport != sport_filter:
            return None

        match_id = str(event.get("I", ""))
        home = event.get("HE", "") or event.get("O1", "")
        away = event.get("AE", "") or event.get("O2", "")
        league = event.get("LN", "") or event.get("SN", "")
        start_ts = event.get("S", 0)

        if not home or not away:
            return None

        start_time = datetime.fromtimestamp(start_ts, tz=timezone.utc) if start_ts else datetime.utcnow()

        # Extraction des cotes 1X2
        markets: dict[str, list[ScrapedOdd]] = {}
        raw_odds = event.get("E", [])
        if isinstance(raw_odds, list):
            home_win = away_win = draw = None
            for odd_block in raw_odds:
                t = odd_block.get("T", 0)
                val = odd_block.get("C", 0.0)
                if isinstance(val, str):
                    try:
                        val = float(val)
                    except ValueError:
                        continue
                if val <= 1.0:
                    continue
                if t == 1:
                    home_win = ScrapedOdd("Home", val, "1xbet")
                elif t == 2:
                    draw = ScrapedOdd("Draw", val, "1xbet")
                elif t == 3:
                    away_win = ScrapedOdd("Away", val, "1xbet")

            if home_win and away_win:
                outcomes = [home_win, away_win]
                if draw:
                    outcomes.insert(1, draw)
                markets["1X2"] = outcomes

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
            source="1xbet",
        )

    @staticmethod
    def _map_sport_id(sport_id: int) -> Sport:
        mapping = {1: Sport.FOOTBALL, 2: Sport.BASKETBALL, 3: Sport.TENNIS, 4: Sport.HOCKEY}
        return mapping.get(sport_id, Sport.OTHER)
