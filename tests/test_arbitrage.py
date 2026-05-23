"""Tests pour le détecteur d'arbitrage."""
from datetime import datetime

import pytest

from analyzers.arbitrage_detector import ArbitrageDetector
from models.bet import Sport
from scrapers.base_scraper import ScrapedMatch, ScrapedOdd


def _make_match(home_odd: float, draw_odd: float, away_odd: float) -> ScrapedMatch:
    return ScrapedMatch(
        match_id="test-1",
        home_team="Team A",
        away_team="Team B",
        sport=Sport.FOOTBALL,
        league="Test League",
        start_time=datetime.utcnow(),
        markets={
            "1X2": [
                ScrapedOdd("Home", home_odd, "bk1"),
                ScrapedOdd("Draw", draw_odd, "bk2"),
                ScrapedOdd("Away", away_odd, "bk3"),
            ]
        },
    )


class TestArbitrageDetector:
    def test_no_arb_standard_market(self):
        # Marché typique avec ~5% de vig → pas d'arb
        match = _make_match(2.05, 3.40, 3.60)
        detector = ArbitrageDetector(bankroll=1000.0)
        arbs = detector.detect([match])
        assert len(arbs) == 0

    def test_arb_detected(self):
        # Arbitrage synthétique : Σ(1/c) < 1
        # 1/2.10 + 1/3.80 + 1/4.10 ≈ 0.966 < 1 → profit ~3.4%
        match = _make_match(2.10, 3.80, 4.10)
        detector = ArbitrageDetector(bankroll=1000.0, min_profit_pct=0.1)
        arbs = detector.detect([match])
        assert len(arbs) == 1
        assert arbs[0].profit_pct > 0

    def test_optimal_stakes_sum_to_bankroll(self):
        match = _make_match(2.10, 3.80, 4.10)
        detector = ArbitrageDetector(bankroll=1000.0, min_profit_pct=0.1)
        arbs = detector.detect([match])
        if arbs:
            total_stake = sum(arbs[0].optimal_stakes)
            assert total_stake == pytest.approx(1000.0, abs=0.01)

    def test_profit_identical_for_all_outcomes(self):
        """Les mises optimales doivent donner le même profit pour tout outcome."""
        match = _make_match(2.10, 3.80, 4.10)
        detector = ArbitrageDetector(bankroll=1000.0, min_profit_pct=0.1)
        arbs = detector.detect([match])
        if arbs:
            arb = arbs[0]
            returns = [
                stake * odd
                for stake, odd in zip(arb.optimal_stakes, arb.odds)
            ]
            # Tous les retours doivent être égaux (à flottant près)
            assert max(returns) - min(returns) < 0.01

    def test_min_profit_filter(self):
        match = _make_match(2.10, 3.80, 4.10)
        detector = ArbitrageDetector(bankroll=1000.0, min_profit_pct=10.0)
        arbs = detector.detect([match])
        assert len(arbs) == 0

    def test_compute_arb_across_bookmakers(self):
        odds_map = {
            "Home": [("bk1", 2.20), ("bk2", 2.10)],
            "Away": [("bk1", 1.85), ("bk2", 1.90)],
        }
        profit = ArbitrageDetector.compute_arb_across_bookmakers(odds_map)
        # 1/2.20 + 1/1.90 ≈ 0.981 → profit ~1.9%
        assert profit == pytest.approx((1 - (1/2.20 + 1/1.90)) * 100, abs=0.01)
