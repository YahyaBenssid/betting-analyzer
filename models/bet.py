"""
Dataclasses centrales : Odd, Market, Bet.
Tout le système manipule ces types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Sport(str, Enum):
    FOOTBALL = "football"
    TENNIS = "tennis"
    BASKETBALL = "basketball"
    HOCKEY = "hockey"
    OTHER = "other"


class BetStatus(str, Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"


@dataclass(frozen=True)
class Odd:
    """Cote pour un outcome donné (ex: victoire domicile)."""
    outcome: str          # "Home" | "Draw" | "Away" | "Over 2.5" ...
    value: float          # cote décimale (ex: 2.15)
    bookmaker: str = "1xbet"

    def __post_init__(self) -> None:
        if self.value <= 1.0:
            raise ValueError(f"Cote invalide: {self.value} — doit être > 1.0")

    @property
    def implied_probability(self) -> float:
        """Probabilité implicite brute (avec marge bookmaker)."""
        return 1.0 / self.value

    @property
    def net_odd(self) -> float:
        """Gain net par unité misée (b dans Kelly)."""
        return self.value - 1.0


@dataclass
class Market:
    """Un marché de pari (ex: 1X2, Over/Under, Both Teams Score)."""
    name: str                     # "1X2", "Over/Under 2.5", "BTTS"
    odds: list[Odd]               # liste de tous les outcomes du marché
    match_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def overround(self) -> float:
        """Surround (marge bookmaker) = somme des probabilités implicites."""
        return sum(o.implied_probability for o in self.odds)

    @property
    def vig_pct(self) -> float:
        """Marge bookmaker en pourcentage."""
        return (self.overround - 1.0) * 100.0

    def fair_probabilities(self) -> dict[str, float]:
        """Probabilités équilibrées après suppression de la vig."""
        total = self.overround
        return {o.outcome: o.implied_probability / total for o in self.odds}

    def get_odd(self, outcome: str) -> Optional[Odd]:
        for o in self.odds:
            if o.outcome.lower() == outcome.lower():
                return o
        return None


@dataclass
class Bet:
    """Un pari complet avec toutes ses métadonnées analytiques."""
    match_id: str
    home_team: str
    away_team: str
    sport: Sport
    league: str
    market: Market
    selected_outcome: str         # outcome choisi
    start_time: datetime

    # Résultats d'analyse (remplis par les analyzers)
    ev_pct: float = 0.0           # Expected Value en %
    kelly_fraction: float = 0.0   # Fraction Kelly recommandée
    confidence_score: float = 0.0 # Score 0-100
    real_probability: float = 0.0 # Probabilité estimée "réelle"

    # Tracking bankroll
    stake: float = 0.0
    status: BetStatus = BetStatus.PENDING
    result_profit: Optional[float] = None

    @property
    def selected_odd(self) -> Optional[Odd]:
        return self.market.get_odd(self.selected_outcome)

    @property
    def match_label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    @property
    def is_value_bet(self) -> bool:
        return self.ev_pct > 0

    def __repr__(self) -> str:
        odd = self.selected_odd
        cote = odd.value if odd else "?"
        return (
            f"Bet({self.match_label} | {self.market.name} → {self.selected_outcome} "
            f"@ {cote} | EV={self.ev_pct:+.1f}% | Conf={self.confidence_score:.0f}/100)"
        )
