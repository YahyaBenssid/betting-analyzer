"""
Score de confiance composite (0-100) pour chaque value bet.

Composantes brutes :
  [40 pts] EV positif — magnitude pondérée par la fiabilité de l'estimation
  [20 pts] Kelly fraction — taille recommandée (proxy de confiance)
  [20 pts] Cohérence modèle Poisson
  [10 pts] Vig faible (marché liquide)
  [±pts]   Plage de cote — bonus à 1.4-2.2, pénalité au-delà de 3.0

Bonus source :
  +5 pts si stats_source == "real_stats" (football-data.org)
  −5 pts si stats_source == "fair_prob"  (aucun modèle)

Pourquoi pondérer l'EV par la cote ?
  EV = p_réelle × cote - 1. Une erreur ε sur p_réelle produit une erreur de
  ε × cote sur l'EV. À cote 3.5, une erreur de 3% en probabilité fait varier
  l'EV de ±10.5%. À cote 2.0, la même erreur ne donne que ±6%.
  On atténue donc les points EV par reliability = min(1.0, 1.5 / odd).

Pourquoi pénaliser les cotes > 3 ?
  Les événements à faible probabilité ont moins de données historiques,
  les modèles sont moins précis, et les bookmakers y placent souvent leurs
  marges les plus élevées. La "confiance" doit refléter cette incertitude
  structurelle — pas seulement la magnitude de l'EV.
"""
from __future__ import annotations

import math

from analyzers.value_bet_detector import ValueBetResult


class ConfidenceScorer:
    """Enrichit chaque ValueBetResult avec un score de confiance 0-100."""

    # Seuils EV bruts avant pondération (points 0-40)
    EV_BREAKPOINTS = [
        (3.0,   8),
        (5.0,  16),
        (8.0,  24),
        (12.0, 32),
        (float("inf"), 40),
    ]

    # Seuils Kelly fraction (points 0-20)
    KELLY_BREAKPOINTS = [
        (0.01,  4),
        (0.02,  8),
        (0.035, 12),
        (0.05, 16),
        (float("inf"), 20),
    ]

    def score(self, result: ValueBetResult) -> float:
        """Calcule et attribue le score de confiance."""
        pts = 0.0

        pts += self._ev_points(result.ev.ev_pct, result.odd_value)
        pts += self._kelly_points(result.kelly.fractional_kelly)
        pts += self._poisson_coherence_points(result)
        pts += self._vig_points(result)
        pts += self._odds_range_penalty(result.odd_value)
        pts += self._source_bonus(result)

        score = min(100.0, max(0.0, pts))
        result.confidence_score = score
        return score

    def score_all(self, results: list[ValueBetResult]) -> list[ValueBetResult]:
        """Score une liste entière et retrie par score décroissant."""
        for r in results:
            self.score(r)
        results.sort(key=lambda r: (r.confidence_score, r.ev.ev_pct), reverse=True)
        return results

    # ------------------------------------------------------------------ #
    # Composantes individuelles

    def _ev_points(self, ev_pct: float, odd_value: float) -> float:
        """
        0-40 pts pondérés par la fiabilité de l'estimation.

        reliability = min(1.0, 1.5 / odd_value)
          cote 1.5 → 1.00 (score plein)
          cote 2.0 → 0.75
          cote 3.0 → 0.50
          cote 4.0 → 0.375
          cote 6.0 → 0.25

        Un EV de 12% à cote 3.5 n'est pas aussi fiable qu'un EV de 12% à
        cote 1.8 — la même erreur de probabilité génère 2× plus d'impact.
        """
        if ev_pct <= 0:
            return 0.0

        raw_pts = 0.0
        for threshold, points in self.EV_BREAKPOINTS:
            if ev_pct < threshold:
                raw_pts = float(points)
                break
        else:
            raw_pts = 40.0

        reliability = min(1.0, 1.5 / odd_value)
        return raw_pts * reliability

    def _kelly_points(self, fractional_kelly: float) -> float:
        """0-20 pts selon la fraction Kelly recommandée."""
        if fractional_kelly <= 0:
            return 0.0
        for threshold, points in self.KELLY_BREAKPOINTS:
            if fractional_kelly < threshold:
                return float(points)
        return 20.0

    def _poisson_coherence_points(self, result: ValueBetResult) -> float:
        """
        0-20 pts : cohérence entre l'EV et le modèle de Poisson.
        Sans modèle disponible : 5 pts neutres (pas 10 — l'absence d'info
        n'est pas une confirmation).
        """
        if result.poisson_result is None:
            return 5.0

        poisson = result.poisson_result
        outcome = result.outcome.lower()

        poisson_prob = {
            "home": poisson.prob_home_win,
            "draw": poisson.prob_draw,
            "away": poisson.prob_away_win,
        }.get(outcome)

        if poisson_prob is None:
            return 5.0

        implied_prob = result.ev.implied_prob

        if poisson_prob > implied_prob and result.ev.is_value_bet:
            margin = (poisson_prob - implied_prob) * 100
            return min(20.0, 10.0 + margin * 2)

        # Poisson contredit la value → pénalité
        return max(0.0, 10.0 - (implied_prob - poisson_prob) * 100)

    def _vig_points(self, result: ValueBetResult) -> float:
        """
        0-10 pts : vig faible = marché liquide / bookmaker moins agressif.
        """
        vig_proxy = (
            (result.ev.implied_prob / result.ev.fair_prob - 1.0) * 100
            if result.ev.fair_prob > 0 else 5.0
        )
        if vig_proxy < 3.0:
            return 10.0
        if vig_proxy < 6.0:
            return 5.0
        return 0.0

    @staticmethod
    def _odds_range_penalty(odd_value: float) -> float:
        """
        Bonus/pénalité selon la plage de cote.

        Zone favorable (1.4–2.2) : +8 pts
          Probabilités entre 45% et 71% — zone où les modèles sont précis
          et les données historiques abondantes.

        Zone neutre (2.2–3.0) : 0 pts
          Acceptable, mais l'incertitude commence à monter.

        Zone risquée (3.0–4.5) : −10 pts
          Événements peu probables, estimations moins fiables,
          amplification des erreurs de probabilité.

        Zone très risquée (> 4.5) : −20 pts
          Territoire outsider — la moindre erreur d'estimation annule la value.

        Cote trop basse (< 1.3) : −5 pts
          Quasi-certitude, vig élevée relative, peu de valeur extractible.
        """
        if 1.4 <= odd_value <= 2.2:
            return 8.0
        if 2.2 < odd_value <= 3.0:
            return 0.0
        if 3.0 < odd_value <= 4.5:
            return -10.0
        if odd_value > 4.5:
            return -20.0
        # odd < 1.4
        return -5.0

    @staticmethod
    def _source_bonus(result: "ValueBetResult") -> float:
        """
        Bonus/malus selon la source des probabilités.
        real_stats → données réelles football-data.org → +5
        poisson_avg → équipes moyennes, modèle sans calibration → 0
        fair_prob → aucun modèle → −5
        """
        source = getattr(result, "stats_source", "fair_prob")
        if source == "real_stats":
            return 5.0
        if source == "fair_prob":
            return -5.0
        return 0.0
