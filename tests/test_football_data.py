"""
Tests pour le client football-data.org et le StatsProvider.
Tous les appels HTTP sont mockés — aucun accès réseau réel.
"""
from __future__ import annotations

import asyncio
import pytest

from scrapers.football_data import (
    FootballDataClient,
    LeagueStats,
    TeamRecord,
    _normalize,
)
from analyzers.stats_provider import StatsProvider, _guess_competition


# ------------------------------------------------------------------ #
# Fixtures

SAMPLE_STANDINGS = {
    "standings": [{
        "type": "TOTAL",
        "table": [
            {
                "team": {"id": 1, "name": "Manchester City"},
                "goalsFor": 72, "goalsAgainst": 28, "playedGames": 32,
            },
            {
                "team": {"id": 2, "name": "Arsenal"},
                "goalsFor": 68, "goalsAgainst": 29, "playedGames": 32,
            },
        ]
    }]
}

SAMPLE_MATCHES = {
    "matches": [
        {
            "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
            "score": {"fullTime": {"home": 3, "away": 1}},
        },
        {
            "homeTeam": {"id": 2}, "awayTeam": {"id": 1},
            "score": {"fullTime": {"home": 2, "away": 2}},
        },
        {
            "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
            "score": {"fullTime": {"home": 4, "away": 0}},
        },
    ]
}


# ------------------------------------------------------------------ #
# Tests _normalize

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Arsenal") == "arsenal"

    def test_manchester_abbreviation(self):
        assert _normalize("Manchester City") == "man city"

    def test_psg_normalization(self):
        assert _normalize("Paris Saint-Germain") == "psg"

    def test_removes_special_chars(self):
        result = _normalize("Atlético Madrid")
        assert "é" not in result


# ------------------------------------------------------------------ #
# Tests _guess_competition

class TestGuessCompetition:
    def test_premier_league(self):
        assert _guess_competition("Premier League") == "PL"

    def test_ligue1(self):
        assert _guess_competition("Ligue 1 - France") == "FL1"

    def test_champions_league(self):
        assert _guess_competition("UEFA Champions League") == "CL"

    def test_bundesliga(self):
        assert _guess_competition("Bundesliga") == "BL1"

    def test_unknown_returns_none(self):
        assert _guess_competition("Unknown Championship XYZ") is None


# ------------------------------------------------------------------ #
# Tests parsing standings

class TestParseStandings:
    def test_parses_team_ids(self):
        teams = FootballDataClient._parse_standings(SAMPLE_STANDINGS, "PL")
        assert 1 in teams
        assert 2 in teams

    def test_parses_goals(self):
        teams = FootballDataClient._parse_standings(SAMPLE_STANDINGS, "PL")
        mancity = teams[1]
        assert mancity.season_goals_scored == 72
        assert mancity.season_goals_conceded == 28
        assert mancity.season_matches == 32

    def test_team_names(self):
        teams = FootballDataClient._parse_standings(SAMPLE_STANDINGS, "PL")
        assert teams[1].name == "Manchester City"
        assert teams[2].name == "Arsenal"

    def test_empty_standings(self):
        teams = FootballDataClient._parse_standings({"standings": []}, "PL")
        assert teams == {}


# ------------------------------------------------------------------ #
# Tests calcul moyennes ligue

class TestLeagueAverages:
    def test_averages_computed(self):
        home_avg, away_avg = FootballDataClient._compute_league_averages(SAMPLE_MATCHES)
        # Buts domicile : 3+2+4=9 sur 3 matchs = 3.0
        assert home_avg == pytest.approx(3.0)
        # Buts extérieur : 1+2+0=3 sur 3 matchs = 1.0
        assert away_avg == pytest.approx(1.0)

    def test_empty_matches(self):
        home_avg, away_avg = FootballDataClient._compute_league_averages({"matches": []})
        assert home_avg == 0.0
        assert away_avg == 0.0

    def test_missing_scores_ignored(self):
        data = {"matches": [
            {"homeTeam": {"id": 1}, "awayTeam": {"id": 2},
             "score": {"fullTime": {"home": None, "away": None}}},
            {"homeTeam": {"id": 1}, "awayTeam": {"id": 2},
             "score": {"fullTime": {"home": 2, "away": 1}}},
        ]}
        home_avg, away_avg = FootballDataClient._compute_league_averages(data)
        assert home_avg == pytest.approx(2.0)
        assert away_avg == pytest.approx(1.0)


# ------------------------------------------------------------------ #
# Tests form récente

class TestRecentForm:
    def test_attaches_form(self):
        teams = FootballDataClient._parse_standings(SAMPLE_STANDINGS, "PL")
        FootballDataClient._attach_recent_form(teams, SAMPLE_MATCHES, n_recent=10)
        mancity = teams[1]
        assert len(mancity.recent_goals_scored) > 0
        assert len(mancity.recent_goals_conceded) > 0

    def test_correct_perspective(self):
        teams = FootballDataClient._parse_standings(SAMPLE_STANDINGS, "PL")
        FootballDataClient._attach_recent_form(teams, SAMPLE_MATCHES, n_recent=10)
        # Man City domicile match 1 : scored=3, conceded=1
        mancity = teams[1]
        assert 3 in mancity.recent_goals_scored
        assert 1 in mancity.recent_goals_conceded


# ------------------------------------------------------------------ #
# Tests TeamRecord

class TestTeamRecord:
    def _make_record(self) -> TeamRecord:
        r = TeamRecord(
            team_id=1, name="Test",
            season_goals_scored=40.0, season_goals_conceded=20.0,
            season_matches=20,
            recent_goals_scored=[2, 3, 1, 2, 2],
            recent_goals_conceded=[0, 1, 1, 2, 0],
        )
        return r

    def test_avg_scored_season(self):
        r = self._make_record()
        assert r.avg_scored_season == pytest.approx(2.0)

    def test_avg_conceded_season(self):
        r = self._make_record()
        assert r.avg_conceded_season == pytest.approx(1.0)

    def test_avg_scored_recent(self):
        r = self._make_record()
        assert r.avg_scored_recent == pytest.approx(2.0)

    def test_blended_is_between_season_and_recent(self):
        r = self._make_record()
        blended = r.blended_scored()
        assert min(r.avg_scored_season, r.avg_scored_recent) <= blended <= max(r.avg_scored_season, r.avg_scored_recent)

    def test_fallback_when_no_recent(self):
        r = TeamRecord(team_id=1, name="T", season_goals_scored=30, season_goals_conceded=15, season_matches=15)
        assert r.avg_scored_recent == r.avg_scored_season

    def test_fallback_when_no_matches(self):
        r = TeamRecord(team_id=1, name="T")
        assert r.avg_scored_season == 1.3  # Valeur par défaut


# ------------------------------------------------------------------ #
# Tests LeagueStats.find_team (fuzzy matching)

class TestLeagueFuzzyMatch:
    def _make_league(self) -> LeagueStats:
        teams = {
            1: TeamRecord(team_id=1, name="Manchester City"),
            2: TeamRecord(team_id=2, name="Arsenal"),
            3: TeamRecord(team_id=3, name="Paris Saint-Germain"),
        }
        league = LeagueStats(
            competition_code="PL", competition_name="Test",
            home_goals_avg=1.5, away_goals_avg=1.1, teams=teams,
        )
        league.build_name_index()
        return league

    def test_exact_match(self):
        league = self._make_league()
        result = league.find_team("Manchester City")
        assert result is not None
        assert result.team_id == 1

    def test_fuzzy_abbreviation(self):
        league = self._make_league()
        result = league.find_team("Man City")
        assert result is not None
        assert result.team_id == 1

    def test_psg_normalization(self):
        league = self._make_league()
        result = league.find_team("PSG")
        assert result is not None
        assert result.team_id == 3

    def test_unknown_returns_none(self):
        league = self._make_league()
        result = league.find_team("Udinese Calcio Xyz")
        assert result is None


# ------------------------------------------------------------------ #
# Tests StatsProvider._record_to_stats

class TestRecordToStats:
    def test_above_average_attack(self):
        record = TeamRecord(
            team_id=1, name="Strong",
            season_goals_scored=60, season_goals_conceded=20, season_matches=30,
        )
        league = LeagueStats("PL", "Test", home_goals_avg=1.5, away_goals_avg=1.1, teams={})
        stats = StatsProvider._record_to_stats(record, league, is_home=True)
        # 60/30 = 2.0 buts/match vs 1.5 ligue → attack_strength > 1
        assert stats.attack_strength > 1.0

    def test_strong_defense(self):
        record = TeamRecord(
            team_id=1, name="Defensive",
            season_goals_scored=20, season_goals_conceded=10, season_matches=30,
        )
        league = LeagueStats("PL", "Test", home_goals_avg=1.5, away_goals_avg=1.1, teams={})
        stats = StatsProvider._record_to_stats(record, league, is_home=True)
        # Encaisse peu → defense_strength faible
        assert stats.defense_strength < 1.0

    def test_strengths_clamped(self):
        record = TeamRecord(
            team_id=1, name="Extreme",
            season_goals_scored=200, season_goals_conceded=0, season_matches=1,
        )
        league = LeagueStats("PL", "Test", home_goals_avg=1.5, away_goals_avg=1.1, teams={})
        stats = StatsProvider._record_to_stats(record, league, is_home=True)
        assert stats.attack_strength <= 3.0
        assert stats.defense_strength >= 0.3

    def test_average_team_near_one(self):
        record = TeamRecord(
            team_id=1, name="Average",
            season_goals_scored=45, season_goals_conceded=33, season_matches=30,
        )
        league = LeagueStats("PL", "Test", home_goals_avg=1.5, away_goals_avg=1.1, teams={})
        stats = StatsProvider._record_to_stats(record, league, is_home=True)
        assert 0.8 <= stats.attack_strength <= 1.2
