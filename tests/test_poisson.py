"""Tests unitaires pour le modèle de Poisson."""
import pytest

from models.poisson import (
    PoissonResult,
    TeamStats,
    _poisson_pmf,
    estimate_team_strengths_from_form,
    poisson_match_probabilities,
)


class TestPoissonPMF:
    def test_zero_goals(self):
        # P(X=0 | λ=1.5) = e^-1.5 ≈ 0.2231
        assert _poisson_pmf(0, 1.5) == pytest.approx(0.2231, abs=1e-4)

    def test_one_goal(self):
        # P(X=1 | λ=1.5) = 1.5 × e^-1.5 ≈ 0.3347
        assert _poisson_pmf(1, 1.5) == pytest.approx(0.3347, abs=1e-4)

    def test_lambda_zero(self):
        assert _poisson_pmf(0, 0.0) == pytest.approx(1.0)
        assert _poisson_pmf(1, 0.0) == pytest.approx(0.0)

    def test_probabilities_sum_to_one(self):
        total = sum(_poisson_pmf(k, 2.0) for k in range(100))
        assert total == pytest.approx(1.0, abs=1e-6)


class TestTeamStats:
    def test_average_team(self):
        t = TeamStats.average("Test")
        assert t.attack_strength == 1.0
        assert t.defense_strength == 1.0

    def test_from_goals_strong_attack(self):
        # Équipe qui marque 2 buts/match quand la moyenne ligue est 1.5
        t = TeamStats.from_goals("Attack", goals_scored=2.0, goals_conceded=1.0,
                                 league_avg_scored=1.5, league_avg_conceded=1.5)
        assert t.attack_strength == pytest.approx(2.0 / 1.5)
        assert t.defense_strength == pytest.approx(1.0 / 1.5)


class TestPoissonMatchProbabilities:
    def test_probabilities_sum_to_one(self):
        home = TeamStats.average("Home")
        away = TeamStats.average("Away")
        result = poisson_match_probabilities(home, away)
        total = result.prob_home_win + result.prob_draw + result.prob_away_win
        assert total == pytest.approx(1.0, abs=1e-4)

    def test_home_advantage(self):
        # Avec des paramètres de ligue standard, l'équipe à domicile doit être favorisée
        home = TeamStats.average("Home")
        away = TeamStats.average("Away")
        result = poisson_match_probabilities(home, away,
                                            home_goals_avg=1.53, away_goals_avg=1.12)
        assert result.prob_home_win > result.prob_away_win

    def test_strong_team_wins_more(self):
        strong = TeamStats("Strong", attack_strength=2.0, defense_strength=0.5)
        weak = TeamStats("Weak", attack_strength=0.5, defense_strength=2.0)
        result = poisson_match_probabilities(strong, weak)
        assert result.prob_home_win > 0.5

    def test_score_matrix_populated(self):
        home = TeamStats.average("A")
        away = TeamStats.average("B")
        result = poisson_match_probabilities(home, away)
        assert (0, 0) in result.score_matrix
        assert len(result.score_matrix) > 0

    def test_over_2_5_range(self):
        home = TeamStats.average("A")
        away = TeamStats.average("B")
        result = poisson_match_probabilities(home, away)
        assert 0.0 <= result.over_2_5 <= 1.0

    def test_btts_range(self):
        home = TeamStats.average("A")
        away = TeamStats.average("B")
        result = poisson_match_probabilities(home, away)
        assert 0.0 <= result.btts <= 1.0

    def test_most_likely_score_type(self):
        home = TeamStats.average("A")
        away = TeamStats.average("B")
        result = poisson_match_probabilities(home, away)
        h, a = result.most_likely_score
        assert isinstance(h, int) and isinstance(a, int)
        assert h >= 0 and a >= 0

    def test_lambda_calculation(self):
        # λ_home = 1.0 × 1.0 × 1.5 = 1.5 pour deux équipes moyennes
        home = TeamStats.average("A")
        away = TeamStats.average("B")
        result = poisson_match_probabilities(home, away, home_goals_avg=1.5, away_goals_avg=1.1)
        assert result.lambda_home == pytest.approx(1.5)
        assert result.lambda_away == pytest.approx(1.1)


class TestEstimateStrengths:
    def test_empty_returns_average(self):
        t = estimate_team_strengths_from_form([], [], name="Empty")
        assert t.attack_strength == 1.0
        assert t.defense_strength == 1.0

    def test_high_scoring_team(self):
        t = estimate_team_strengths_from_form(
            recent_goals_scored=[3, 4, 2, 3],
            recent_goals_conceded=[0, 1, 1, 0],
            league_avg_scored=1.5,
            league_avg_conceded=1.1,
        )
        assert t.attack_strength > 1.0   # Meilleure attaque que la moyenne
        assert t.defense_strength < 1.0  # Meilleure défense (moins de buts encaissés)
