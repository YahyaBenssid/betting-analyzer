"""
Calcul de l'Expected Value (EV) et des probabilités implicites.

EV = (p_réelle × gain_net) - (q_réelle × mise)
   = (p_réelle × (cote - 1)) - ((1 - p_réelle) × 1)
   = p_réelle × cote - 1

En % de la mise : EV% = (p_réelle × cote - 1) × 100
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVResult:
    outcome: str
    odd_value: float
    implied_prob: float       # Probabilité implicite brute
    fair_prob: float          # Probabilité implicite sans vig
    real_prob: float          # Probabilité "réelle" estimée
    ev_pct: float             # Expected Value en %
    is_value_bet: bool        # True si EV > 0

    def __str__(self) -> str:
        sign = "+" if self.ev_pct >= 0 else ""
        tag = "✅ VALUE BET" if self.is_value_bet else "❌"
        return (
            f"{self.outcome} @ {self.odd_value:.2f} | "
            f"EV={sign}{self.ev_pct:.2f}% | "
            f"p_réelle={self.real_prob:.1%} | "
            f"p_juste={self.fair_prob:.1%} | {tag}"
        )


def implied_probability(odd: float) -> float:
    """Probabilité implicite brute d'une cote décimale."""
    if odd <= 1.0:
        raise ValueError(f"Cote invalide: {odd}")
    return 1.0 / odd


def remove_vig(probs: list[float]) -> list[float]:
    """
    Supprime la marge bookmaker (vig) en normalisant la somme à 1.
    Méthode proportionnelle (la plus standard).
    """
    total = sum(probs)
    if total <= 0:
        raise ValueError("Somme des probabilités nulle")
    return [p / total for p in probs]


def compute_ev(odd_value: float, real_probability: float) -> EVResult:
    """
    Calcule l'EV d'un pari.

    Args:
        odd_value: Cote décimale du bookmaker (ex: 2.15)
        real_probability: Probabilité "réelle" estimée (0 < p < 1)

    Returns:
        EVResult avec toutes les métriques calculées.
    """
    if not (0 < real_probability < 1):
        raise ValueError(f"real_probability doit être dans (0,1), reçu: {real_probability}")
    if odd_value <= 1.0:
        raise ValueError(f"Cote invalide: {odd_value}")

    implied = implied_probability(odd_value)

    # EV% = (p_réelle × cote - 1) × 100
    ev_pct = (real_probability * odd_value - 1.0) * 100.0

    return EVResult(
        outcome="",
        odd_value=odd_value,
        implied_prob=implied,
        fair_prob=implied,  # sera mis à jour par l'appelant avec remove_vig
        real_prob=real_probability,
        ev_pct=ev_pct,
        is_value_bet=ev_pct > 0,
    )


def compute_ev_market(
    odd_value: float,
    real_probability: float,
    all_implied_probs: list[float],
    outcome_label: str = "",
) -> EVResult:
    """
    Calcule l'EV en tenant compte de la vig de tout le marché.

    Args:
        odd_value: Cote décimale pour cet outcome
        real_probability: Probabilité estimée pour cet outcome
        all_implied_probs: Probabilités implicites brutes de TOUS les outcomes du marché
        outcome_label: Nom de l'outcome (cosmétique)
    """
    if not (0 < real_probability < 1):
        raise ValueError(f"real_probability doit être dans (0,1), reçu: {real_probability}")

    fair_probs = remove_vig(all_implied_probs)
    # Index de l'outcome = index de sa cote dans la liste (convention appelant)
    idx = 0  # L'appelant passe la prob de l'outcome en premier
    fair_prob = fair_probs[idx] if fair_probs else implied_probability(odd_value)

    ev_pct = (real_probability * odd_value - 1.0) * 100.0

    return EVResult(
        outcome=outcome_label,
        odd_value=odd_value,
        implied_prob=implied_probability(odd_value),
        fair_prob=fair_prob,
        real_prob=real_probability,
        ev_pct=ev_pct,
        is_value_bet=ev_pct > 0,
    )
