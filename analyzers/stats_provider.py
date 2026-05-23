"""
StatsProvider — résout un nom d'équipe en TeamStats calibrées.

Responsabilités :
  1. Charge les LeagueStats depuis football-data.org (avec cache 24h).
  2. Effectue le fuzzy-matching nom de match → TeamRecord.
  3. Convertit TeamRecord → TeamStats pour le modèle de Poisson.
  4. Détermine la ligue la plus probable à partir du nom de compétition du match.

Le cache 24h est justifié : les stats de buts saison et les 10 derniers matchs
ne changent qu'à chaque journée de championnat (tous les 3-7 jours).
"""
from __future__ import annotations

import asyncio
import json
import shelve
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from models.poisson import TeamStats
from scrapers.football_data import (
    COMPETITIONS,
    FootballDataClient,
    LeagueStats,
    TeamRecord,
)

# TTL du cache stats : 24h
_STATS_CACHE_TTL = 86_400
_STATS_CACHE_PATH = ".cache/league_stats"

# Mots-clés dans le nom de ligue → code compétition
_LEAGUE_KEYWORDS: list[tuple[str, str]] = [
    ("premier league", "PL"),
    ("epl", "PL"),
    ("la liga", "PD"),
    ("bundesliga", "BL1"),
    ("serie a", "SA"),
    ("ligue 1", "FL1"),
    ("ligue1", "FL1"),
    ("champions league", "CL"),
    ("ucl", "CL"),
    ("eredivisie", "DED"),
    ("championship", "ELC"),
    ("primeira liga", "PPL"),
]


def _guess_competition(league_name: str) -> Optional[str]:
    """Devine le code compétition football-data à partir du nom de ligue brut."""
    low = league_name.lower()
    for keyword, code in _LEAGUE_KEYWORDS:
        if keyword in low:
            return code
    return None


class StatsProvider:
    """
    Singleton-like provider de stats équipe, avec cache disque.
    Utilisé par ValueBetDetector pour obtenir les TeamStats réels.
    """

    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = _STATS_CACHE_TTL) -> None:
        self._client = FootballDataClient(api_key=api_key)
        self._cache_ttl = cache_ttl
        self._memory: dict[str, LeagueStats] = {}  # Cache mémoire session
        Path(_STATS_CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # API publique

    async def get_team_stats(
        self,
        team_name: str,
        league_name: str,
        is_home: bool,
    ) -> Optional[TeamStats]:
        """
        Retourne un TeamStats calibré pour l'équipe donnée.
        Retourne None si l'équipe est introuvable (le détecteur utilisera alors le fallback).
        """
        code = _guess_competition(league_name)
        if not code:
            logger.debug(f"Ligue inconnue: '{league_name}' — pas de stats")
            return None

        league = await self._load_league(code)
        if league is None:
            return None

        record = league.find_team(team_name)
        if record is None:
            return None

        return self._record_to_stats(record, league, is_home)

    async def get_league_averages(self, league_name: str) -> tuple[float, float]:
        """Retourne (home_avg, away_avg) pour calibrer λ Poisson."""
        code = _guess_competition(league_name)
        if not code:
            return 1.53, 1.12  # Valeurs par défaut multi-ligues

        league = await self._load_league(code)
        if league is None:
            return 1.53, 1.12

        return league.home_goals_avg, league.away_goals_avg

    # ------------------------------------------------------------------ #
    # Chargement avec cache

    async def _load_league(self, code: str) -> Optional[LeagueStats]:
        """Charge depuis la mémoire → disque → API (dans cet ordre)."""
        # 1. Mémoire session (la plus rapide)
        if code in self._memory:
            return self._memory[code]

        # 2. Cache disque (valide 24h)
        cached = self._disk_get(code)
        if cached is not None:
            self._memory[code] = cached
            return cached

        # 3. Appel API
        if not self._client.api_key:
            logger.debug(f"FOOTBALL_DATA_API_KEY manquante — stats {code} indisponibles")
            return None

        try:
            league = await self._client.fetch_league_stats(code)
            self._memory[code] = league
            self._disk_set(code, league)
            return league
        except Exception as exc:
            logger.warning(f"[StatsProvider] Impossible de charger {code}: {exc}")
            return None

    # ------------------------------------------------------------------ #
    # Sérialisation cache disque (shelve)

    def _disk_get(self, code: str) -> Optional[LeagueStats]:
        try:
            with shelve.open(_STATS_CACHE_PATH) as db:
                entry = db.get(f"stats_{code}")
                if entry and time.time() < entry.get("expires", 0):
                    return self._deserialize(entry["data"])
        except Exception as exc:
            logger.debug(f"Cache disque illisible pour {code}: {exc}")
        return None

    def _disk_set(self, code: str, league: LeagueStats) -> None:
        try:
            with shelve.open(_STATS_CACHE_PATH) as db:
                db[f"stats_{code}"] = {
                    "expires": time.time() + self._cache_ttl,
                    "data": self._serialize(league),
                }
        except Exception as exc:
            logger.debug(f"Échec écriture cache disque {code}: {exc}")

    @staticmethod
    def _serialize(league: LeagueStats) -> dict:
        return {
            "competition_code": league.competition_code,
            "competition_name": league.competition_name,
            "home_goals_avg": league.home_goals_avg,
            "away_goals_avg": league.away_goals_avg,
            "teams": {
                str(tid): {
                    "team_id": t.team_id,
                    "name": t.name,
                    "season_goals_scored": t.season_goals_scored,
                    "season_goals_conceded": t.season_goals_conceded,
                    "season_matches": t.season_matches,
                    "recent_goals_scored": t.recent_goals_scored,
                    "recent_goals_conceded": t.recent_goals_conceded,
                    "competition_code": t.competition_code,
                }
                for tid, t in league.teams.items()
            },
        }

    @staticmethod
    def _deserialize(data: dict) -> LeagueStats:
        from scrapers.football_data import TeamRecord
        teams = {
            int(tid): TeamRecord(**vals)
            for tid, vals in data["teams"].items()
        }
        league = LeagueStats(
            competition_code=data["competition_code"],
            competition_name=data["competition_name"],
            home_goals_avg=data["home_goals_avg"],
            away_goals_avg=data["away_goals_avg"],
            teams=teams,
        )
        league.build_name_index()
        return league

    # ------------------------------------------------------------------ #
    # Conversion TeamRecord → TeamStats

    @staticmethod
    def _record_to_stats(
        record: TeamRecord,
        league: LeagueStats,
        is_home: bool,
    ) -> TeamStats:
        """
        Convertit un TeamRecord en TeamStats (forces normalisées).
        Les forces sont calculées par rapport aux moyennes de la ligue.
        On pondère : 65% forme récente + 35% saison complète.
        """
        ref_scored = league.home_goals_avg if is_home else league.away_goals_avg
        ref_conceded = league.away_goals_avg if is_home else league.home_goals_avg

        blended_scored = record.blended_scored()
        blended_conceded = record.blended_conceded()

        # Normalisation : force > 1 = meilleure que la moyenne
        attack_strength = blended_scored / ref_scored if ref_scored > 0 else 1.0
        defense_strength = blended_conceded / ref_conceded if ref_conceded > 0 else 1.0

        # Clamp : évite les forces aberrantes sur petits échantillons
        attack_strength = max(0.3, min(3.0, attack_strength))
        defense_strength = max(0.3, min(3.0, defense_strength))

        return TeamStats(
            name=record.name,
            attack_strength=attack_strength,
            defense_strength=defense_strength,
        )


# Instance partagée dans le process (évite de recharger les stats à chaque appel)
_shared_provider: Optional[StatsProvider] = None


def get_stats_provider() -> StatsProvider:
    global _shared_provider
    if _shared_provider is None:
        _shared_provider = StatsProvider()
    return _shared_provider
