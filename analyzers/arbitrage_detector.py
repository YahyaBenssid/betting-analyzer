"""
Détecteur d'arbitrage (surebet).

Condition d'arbitrage : Σ(1/cote_i) < 1
Profit garanti (%) = (1 - Σ(1/cote_i)) × 100

Calcul des mises optimales :
  stake_i = (bankroll / cote_i) / Σ(1/cote_j)

Résultat identique quel que soit l'outcome gagnant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from scrapers.base_scraper import ScrapedMatch, ScrapedOdd


@dataclass
class ArbitrageOpportunity:
    match: ScrapedMatch
    market_name: str
    outcomes: list[str]
    odds: list[float]
    bookmakers: list[str]
    profit_pct: float             # Profit garanti en %
    optimal_stakes: list[float]   # Mises optimales pour €bankroll
    bankroll: float

    @property
    def guaranteed_profit(self) -> float:
        return self.bankroll * self.profit_pct / 100.0

    @property
    def is_profitable(self) -> bool:
        return self.profit_pct > 0

    def __str__(self) -> str:
        parts = " | ".join(
            f"{o}@{c:.2f}({bk})" for o, c, bk in zip(self.outcomes, self.odds, self.bookmakers)
        )
        return (
            f"⚡ ARB [{self.match.label}] {self.market_name}: "
            f"Profit={self.profit_pct:.2f}% (+€{self.guaranteed_profit:.2f} sur €{self.bankroll:.0f}) "
            f"— {parts}"
        )


class ArbitrageDetector:
    """
    Détecte les opportunités d'arbitrage dans une liste de matchs.

    L'arbitrage classique nécessite plusieurs bookmakers pour le même match.
    Ici, on cherche aussi l'arbitrage intra-bookmaker (ex: Over vs Under qui
    ne se somme pas à exactement 1 après vig).
    """

    def __init__(self, bankroll: float = 1000.0, min_profit_pct: float = 0.5) -> None:
        self.bankroll = bankroll
        self.min_profit_pct = min_profit_pct

    def detect(self, matches: list[ScrapedMatch]) -> list[ArbitrageOpportunity]:
        """Retourne toutes les opportunités d'arbitrage trouvées."""
        opportunities: list[ArbitrageOpportunity] = []

        for match in matches:
            for market_name, odds in match.markets.items():
                arb = self._check_market(match, market_name, odds)
                if arb and arb.profit_pct >= self.min_profit_pct:
                    opportunities.append(arb)

        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        logger.info(f"[Arbitrage] {len(opportunities)} opportunités détectées")
        return opportunities

    def _check_market(
        self,
        match: ScrapedMatch,
        market_name: str,
        odds: list[ScrapedOdd],
    ) -> ArbitrageOpportunity | None:
        if len(odds) < 2:
            return None

        valid_odds = [o for o in odds if o.value > 1.0]
        if len(valid_odds) < 2:
            return None

        sum_implied = sum(1.0 / o.value for o in valid_odds)

        if sum_implied >= 1.0:
            return None  # Pas d'arbitrage

        profit_pct = (1.0 - sum_implied) * 100.0

        # Mises optimales : stake_i = bankroll × (1/cote_i) / Σ(1/cote_j)
        optimal_stakes = [
            self.bankroll * (1.0 / o.value) / sum_implied
            for o in valid_odds
        ]

        return ArbitrageOpportunity(
            match=match,
            market_name=market_name,
            outcomes=[o.outcome for o in valid_odds],
            odds=[o.value for o in valid_odds],
            bookmakers=[o.bookmaker for o in valid_odds],
            profit_pct=profit_pct,
            optimal_stakes=optimal_stakes,
            bankroll=self.bankroll,
        )

    @staticmethod
    def compute_arb_across_bookmakers(
        outcomes_odds: dict[str, list[tuple[str, float]]]
    ) -> float:
        """
        Calcule le profit d'arbitrage en prenant la meilleure cote par outcome
        sur plusieurs bookmakers.

        Args:
            outcomes_odds: {outcome: [(bookmaker, cote), ...]}

        Returns:
            Profit en % (négatif si pas d'arbitrage).
        """
        best_odds: dict[str, float] = {}
        for outcome, bk_odds in outcomes_odds.items():
            best = max(bk_odds, key=lambda x: x[1])
            best_odds[outcome] = best[1]

        sum_implied = sum(1.0 / c for c in best_odds.values())
        return (1.0 - sum_implied) * 100.0
