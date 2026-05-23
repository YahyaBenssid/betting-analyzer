"""Tests unitaires pour le Kelly Criterion."""
import pytest

from models.kelly import KellyResult, kelly_criterion, kelly_multi_outcome


class TestKellyCriterion:
    def test_basic_kelly(self):
        # b=1 (cote 2.0), p=0.6 → f* = (1×0.6 - 0.4) / 1 = 0.20
        result = kelly_criterion(2.0, 0.60, bankroll=1000.0, fraction=1.0)
        assert result.full_kelly == pytest.approx(0.20)
        assert result.is_positive is True

    def test_fractional_kelly(self):
        result = kelly_criterion(2.0, 0.60, bankroll=1000.0, fraction=0.25)
        assert result.fractional_kelly == pytest.approx(0.05)  # 0.20 × 0.25
        assert result.stake_amount == pytest.approx(50.0)

    def test_negative_kelly(self):
        # Pari à EV négatif → Kelly négatif → mise = 0
        result = kelly_criterion(2.0, 0.40, bankroll=1000.0, fraction=0.25)
        assert result.full_kelly < 0
        assert result.fractional_kelly == pytest.approx(0.0)
        assert result.stake_amount == pytest.approx(0.0)
        assert result.is_positive is False

    def test_kelly_formula_3way(self):
        # Cote 3.0, prob 0.40 → b=2, f* = (2×0.4 - 0.6) / 2 = 0.10
        result = kelly_criterion(3.0, 0.40, fraction=1.0)
        assert result.full_kelly == pytest.approx(0.10)

    def test_stake_bounded_by_bankroll(self):
        result = kelly_criterion(2.0, 0.90, bankroll=500.0, fraction=0.25)
        assert result.stake_amount <= 500.0

    def test_invalid_probability(self):
        with pytest.raises(ValueError):
            kelly_criterion(2.0, 0.0)

    def test_invalid_probability_over_one(self):
        with pytest.raises(ValueError):
            kelly_criterion(2.0, 1.0)

    def test_invalid_odd(self):
        with pytest.raises(ValueError):
            kelly_criterion(1.0, 0.5)

    def test_invalid_fraction(self):
        with pytest.raises(ValueError):
            kelly_criterion(2.0, 0.5, fraction=0.0)

    def test_invalid_bankroll(self):
        with pytest.raises(ValueError):
            kelly_criterion(2.0, 0.5, bankroll=-100)

    def test_kelly_multi_outcome(self):
        results = kelly_multi_outcome([2.0, 3.0, 4.0], [0.5, 0.33, 0.25])
        assert len(results) == 3
        assert all(isinstance(r, KellyResult) for r in results)

    def test_kelly_multi_outcome_mismatch(self):
        with pytest.raises(ValueError):
            kelly_multi_outcome([2.0, 3.0], [0.5])
