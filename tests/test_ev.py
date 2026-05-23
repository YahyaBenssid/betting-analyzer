"""Tests unitaires pour le module expected_value."""
import pytest

from models.expected_value import (
    EVResult,
    compute_ev,
    compute_ev_market,
    implied_probability,
    remove_vig,
)


class TestImpliedProbability:
    def test_even_money(self):
        assert implied_probability(2.0) == pytest.approx(0.5)

    def test_favourite(self):
        assert implied_probability(1.5) == pytest.approx(0.6667, abs=1e-4)

    def test_outsider(self):
        assert implied_probability(4.0) == pytest.approx(0.25)

    def test_invalid_odd_one(self):
        with pytest.raises(ValueError):
            implied_probability(1.0)

    def test_invalid_odd_below_one(self):
        with pytest.raises(ValueError):
            implied_probability(0.9)


class TestRemoveVig:
    def test_fair_market_unchanged(self):
        probs = [0.5, 0.5]
        result = remove_vig(probs)
        assert sum(result) == pytest.approx(1.0)
        assert result[0] == pytest.approx(0.5)

    def test_removes_overround(self):
        # Marché 1X2 type avec 108% de surround
        raw_probs = [1/2.0, 1/3.5, 1/3.8]
        fair = remove_vig(raw_probs)
        assert sum(fair) == pytest.approx(1.0, abs=1e-6)
        # Toutes les probs doivent être proportionnellement réduites
        assert all(f < r for f, r in zip(fair, raw_probs))

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            remove_vig([])

    def test_zero_sum_raises(self):
        with pytest.raises(ValueError):
            remove_vig([0.0, 0.0])


class TestComputeEV:
    def test_positive_ev(self):
        # Cote 2.20, probabilité réelle 50% → EV = (0.5×2.20 - 1) × 100 = +10%
        result = compute_ev(2.20, 0.50)
        assert result.ev_pct == pytest.approx(10.0)
        assert result.is_value_bet is True

    def test_negative_ev(self):
        # Cote 1.90, probabilité réelle 50% → EV = (0.5×1.90 - 1) × 100 = -5%
        result = compute_ev(1.90, 0.50)
        assert result.ev_pct == pytest.approx(-5.0)
        assert result.is_value_bet is False

    def test_zero_ev(self):
        # Cote 2.0, probabilité réelle 50% → EV = 0%
        result = compute_ev(2.0, 0.50)
        assert result.ev_pct == pytest.approx(0.0, abs=1e-10)

    def test_invalid_probability_zero(self):
        with pytest.raises(ValueError):
            compute_ev(2.0, 0.0)

    def test_invalid_probability_one(self):
        with pytest.raises(ValueError):
            compute_ev(2.0, 1.0)

    def test_invalid_probability_above_one(self):
        with pytest.raises(ValueError):
            compute_ev(2.0, 1.1)

    def test_invalid_odd(self):
        with pytest.raises(ValueError):
            compute_ev(0.5, 0.5)

    def test_strong_value_bet(self):
        # Bookie sous-estime fortement : cote 3.0 pour un événement à 50% de chance réelle
        result = compute_ev(3.0, 0.50)
        assert result.ev_pct == pytest.approx(50.0)

    def test_implied_prob_stored(self):
        result = compute_ev(2.0, 0.5)
        assert result.implied_prob == pytest.approx(0.5)
