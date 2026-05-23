"""
Classe abstraite dont héritent tous les scrapers.
Définit le contrat commun : fetch_matches() → list[ScrapedMatch].
"""
from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger

from models.bet import Sport


@dataclass
class ScrapedOdd:
    outcome: str
    value: float
    bookmaker: str = "unknown"


@dataclass
class ScrapedMatch:
    match_id: str
    home_team: str
    away_team: str
    sport: Sport
    league: str
    start_time: datetime
    markets: dict[str, list[ScrapedOdd]] = field(default_factory=dict)
    source: str = "unknown"

    @property
    def label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


class ScraperError(Exception):
    """Erreur levée lors d'un échec de scraping non récupérable."""


class BaseScraper(ABC):
    """Classe de base pour tous les scrapers de cotes."""

    def __init__(self, max_retries: int = 3, delay_min: float = 2.0, delay_max: float = 5.0) -> None:
        self.max_retries = max_retries
        self.delay_min = delay_min
        self.delay_max = delay_max

    async def _polite_delay(self) -> None:
        """Délai aléatoire pour ne pas surcharger les serveurs cibles."""
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"[{self.__class__.__name__}] Délai poli: {delay:.1f}s")
        await asyncio.sleep(delay)

    async def _retry(self, coro_factory, label: str = "request"):
        """
        Exécute une coroutine avec retry et backoff exponentiel.
        coro_factory est un callable qui retourne une coroutine.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await coro_factory()
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt + random.random()
                logger.warning(
                    f"[{self.__class__.__name__}] {label} — tentative {attempt}/{self.max_retries} "
                    f"échouée: {exc}. Retry dans {wait:.1f}s"
                )
                await asyncio.sleep(wait)
        raise ScraperError(f"{label} échoué après {self.max_retries} tentatives") from last_exc

    @abstractmethod
    async def fetch_matches(
        self,
        sport: Optional[Sport] = None,
        live_only: bool = False,
    ) -> list[ScrapedMatch]:
        """
        Récupère la liste des matchs avec leurs cotes.

        Args:
            sport: Filtrer par sport (None = tous)
            live_only: True = matchs en cours seulement
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Nom du scraper pour les logs."""
        ...
