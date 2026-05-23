"""
Client pour football-data.org (v4).
Gratuite jusqu'à 10 req/min, 100 req/jour.

Données extraites :
  - Classement de ligue  → buts marqués/encaissés de la saison par équipe
  - 10 derniers matchs   → forme récente (pondération plus forte que saison entière)
  - Moyenne buts domicile/extérieur de la ligue → calibration λ Poisson

Endpoints utilisés :
  GET /v4/competitions/{code}/standings
  GET /v4/competitions/{code}/matches?status=FINISHED
  GET /v4/teams/{id}/matches?status=FINISHED&limit=10
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

import httpx
from loguru import logger

from config import settings

BASE_URL = "https://api.football-data.org/v4"

# Codes de compétition supportés → (label, home_avg, away_avg saison 23-24)
# Les moyennes sont des seeds ; elles seront recalculées dynamiquement si possible.
COMPETITIONS: dict[str, tuple[str, float, float]] = {
    "PL":  ("Premier League",      1.55, 1.18),
    "PD":  ("La Liga",             1.53, 1.14),
    "BL1": ("Bundesliga",          1.71, 1.32),
    "SA":  ("Serie A",             1.48, 1.10),
    "FL1": ("Ligue 1",             1.43, 1.08),
    "CL":  ("Champions League",    1.62, 1.21),
    "PPL": ("Primeira Liga",       1.46, 1.09),
    "ELC": ("Championship",        1.50, 1.15),
    "DED": ("Eredivisie",          1.72, 1.30),
}


@dataclass
class TeamRecord:
    """Stats saisonnières + forme récente d'une équipe."""
    team_id: int
    name: str
    # Stats saison complète (toutes compétitions confondues dans la ligue)
    season_goals_scored: float = 0.0
    season_goals_conceded: float = 0.0
    season_matches: int = 0
    # Stats sur les 10 derniers matchs (pondération plus haute)
    recent_goals_scored: list[int] = field(default_factory=list)
    recent_goals_conceded: list[int] = field(default_factory=list)
    competition_code: str = ""

    @property
    def avg_scored_season(self) -> float:
        if self.season_matches == 0:
            return 1.3
        return self.season_goals_scored / self.season_matches

    @property
    def avg_conceded_season(self) -> float:
        if self.season_matches == 0:
            return 1.3
        return self.season_goals_conceded / self.season_matches

    @property
    def avg_scored_recent(self) -> float:
        if not self.recent_goals_scored:
            return self.avg_scored_season
        return sum(self.recent_goals_scored) / len(self.recent_goals_scored)

    @property
    def avg_conceded_recent(self) -> float:
        if not self.recent_goals_conceded:
            return self.avg_conceded_season
        return sum(self.recent_goals_conceded) / len(self.recent_goals_conceded)

    def blended_scored(self, recent_weight: float = 0.65) -> float:
        """Moyenne pondérée saison (35%) + forme récente (65%)."""
        return recent_weight * self.avg_scored_recent + (1 - recent_weight) * self.avg_scored_season

    def blended_conceded(self, recent_weight: float = 0.65) -> float:
        return recent_weight * self.avg_conceded_recent + (1 - recent_weight) * self.avg_conceded_season


@dataclass
class LeagueStats:
    """Stats agrégées d'une ligue pour calibrer les λ Poisson."""
    competition_code: str
    competition_name: str
    home_goals_avg: float
    away_goals_avg: float
    teams: dict[int, TeamRecord] = field(default_factory=dict)   # team_id → TeamRecord
    _name_index: dict[str, int] = field(default_factory=dict, repr=False)  # nom normalisé → team_id

    def find_team(self, name: str, threshold: float = 0.72) -> Optional[TeamRecord]:
        """
        Trouve un TeamRecord par nom approximatif (fuzzy match).
        Gère les variations : "Man City" / "Manchester City", "PSG" / "Paris Saint-Germain"…
        """
        norm = _normalize(name)

        # 1. Correspondance exacte
        if norm in self._name_index:
            return self.teams.get(self._name_index[norm])

        # 2. Fuzzy match
        best_score = 0.0
        best_id: Optional[int] = None
        for stored_norm, tid in self._name_index.items():
            score = SequenceMatcher(None, norm, stored_norm).ratio()
            if score > best_score:
                best_score = score
                best_id = tid

        if best_score >= threshold and best_id is not None:
            matched = self.teams[best_id]
            logger.debug(f"Fuzzy match '{name}' → '{matched.name}' (score={best_score:.2f})")
            return matched

        logger.debug(f"Équipe non trouvée: '{name}' (meilleur score={best_score:.2f})")
        return None

    def build_name_index(self) -> None:
        self._name_index = {_normalize(t.name): tid for tid, t in self.teams.items()}


def _normalize(name: str) -> str:
    """Normalise un nom d'équipe pour la comparaison (minuscules, sans ponctuation)."""
    import re
    name = name.lower()
    # Remplace les abréviations courantes
    replacements = {
        "manchester": "man", "saint": "st", "athletic": "atletico",
        "borussia": "bvb", "real madrid cf": "real madrid",
        "paris saint-germain": "psg", "paris sg": "psg",
        "inter milan": "inter", "internazionale": "inter",
        "ac milan": "milan", "as roma": "roma",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return re.sub(r"[^a-z0-9 ]", "", name).strip()


class FootballDataClient:
    """Client async pour football-data.org v4."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.football_data_api_key
        self._headers = {"X-Auth-Token": self.api_key} if self.api_key else {}
        self._rate_limit_delay = 6.5  # 10 req/min → 6s entre chaque

    async def _get(self, client: httpx.AsyncClient, endpoint: str, params: Optional[dict] = None) -> dict:
        url = f"{BASE_URL}{endpoint}"
        resp = await client.get(url, headers=self._headers, params=params or {})
        if resp.status_code == 429:
            logger.warning("Rate limit football-data.org — attente 60s")
            await asyncio.sleep(60)
            resp = await client.get(url, headers=self._headers, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def fetch_league_stats(self, competition_code: str) -> LeagueStats:
        """
        Récupère standings + derniers matchs pour toute la ligue.
        Construit les TeamRecord avec stats saison ET forme récente.
        """
        code = competition_code.upper()
        label, default_home_avg, default_away_avg = COMPETITIONS.get(
            code, ("Unknown", 1.5, 1.1)
        )
        logger.info(f"[FootballData] Chargement {label} ({code})…")

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1. Standings → buts saison par équipe
            standings_data = await self._get(client, f"/competitions/{code}/standings")
            teams = self._parse_standings(standings_data, code)
            await asyncio.sleep(self._rate_limit_delay)

            # 2. Derniers matchs de la ligue → forme récente + calcul λ moyen
            matches_data = await self._get(
                client, f"/competitions/{code}/matches",
                params={"status": "FINISHED", "limit": 380},
            )
            await asyncio.sleep(self._rate_limit_delay)

        home_avg, away_avg = self._compute_league_averages(matches_data)
        self._attach_recent_form(teams, matches_data, n_recent=10)

        stats = LeagueStats(
            competition_code=code,
            competition_name=label,
            home_goals_avg=home_avg if home_avg > 0 else default_home_avg,
            away_goals_avg=away_avg if away_avg > 0 else default_away_avg,
            teams=teams,
        )
        stats.build_name_index()
        logger.info(
            f"[FootballData] {label}: {len(teams)} équipes | "
            f"λ_home={stats.home_goals_avg:.2f} λ_away={stats.away_goals_avg:.2f}"
        )
        return stats

    async def fetch_multiple_leagues(
        self, codes: Optional[list[str]] = None
    ) -> dict[str, LeagueStats]:
        """Charge plusieurs ligues séquentiellement (rate limit)."""
        codes = codes or list(COMPETITIONS.keys())[:5]  # Top 5 par défaut
        result: dict[str, LeagueStats] = {}
        for code in codes:
            try:
                result[code] = await self.fetch_league_stats(code)
            except Exception as exc:
                logger.error(f"[FootballData] Échec {code}: {exc}")
            await asyncio.sleep(self._rate_limit_delay)
        return result

    # ------------------------------------------------------------------ #
    # Parsers internes

    @staticmethod
    def _parse_standings(data: dict, competition_code: str) -> dict[int, TeamRecord]:
        teams: dict[int, TeamRecord] = {}
        standings = data.get("standings", [])

        # Priorité : total > home > away
        table = next(
            (s["table"] for s in standings if s.get("type") == "TOTAL"),
            standings[0]["table"] if standings else [],
        )

        for entry in table:
            team_info = entry.get("team", {})
            tid = team_info.get("id", 0)
            if not tid:
                continue
            teams[tid] = TeamRecord(
                team_id=tid,
                name=team_info.get("name", ""),
                season_goals_scored=float(entry.get("goalsFor", 0)),
                season_goals_conceded=float(entry.get("goalsAgainst", 0)),
                season_matches=int(entry.get("playedGames", 0)),
                competition_code=competition_code,
            )
        return teams

    @staticmethod
    def _compute_league_averages(matches_data: dict) -> tuple[float, float]:
        """Calcule les moyennes de buts domicile / extérieur sur la saison."""
        matches = matches_data.get("matches", [])
        home_goals: list[int] = []
        away_goals: list[int] = []

        for m in matches:
            score = m.get("score", {}).get("fullTime", {})
            hg = score.get("home")
            ag = score.get("away")
            if hg is not None and ag is not None:
                home_goals.append(int(hg))
                away_goals.append(int(ag))

        if not home_goals:
            return 0.0, 0.0

        return sum(home_goals) / len(home_goals), sum(away_goals) / len(away_goals)

    @staticmethod
    def _attach_recent_form(
        teams: dict[int, TeamRecord],
        matches_data: dict,
        n_recent: int = 10,
    ) -> None:
        """
        Remplit recent_goals_scored / recent_goals_conceded pour chaque équipe
        à partir des N derniers matchs de la ligue.
        """
        # Accumule les matchs par équipe
        team_matches: dict[int, list[dict]] = {tid: [] for tid in teams}
        for m in matches_data.get("matches", []):
            score = m.get("score", {}).get("fullTime", {})
            hg = score.get("home")
            ag = score.get("away")
            if hg is None or ag is None:
                continue
            ht = m.get("homeTeam", {}).get("id")
            at = m.get("awayTeam", {}).get("id")
            if ht in team_matches:
                team_matches[ht].append({"scored": int(hg), "conceded": int(ag)})
            if at in team_matches:
                team_matches[at].append({"scored": int(ag), "conceded": int(hg)})

        for tid, record in teams.items():
            recent = team_matches.get(tid, [])[-n_recent:]  # Les N plus récents
            record.recent_goals_scored = [r["scored"] for r in recent]
            record.recent_goals_conceded = [r["conceded"] for r in recent]
