"""
Kelly Criterion — calcul de la fraction optimale du bankroll à miser.

Formule complète :
    f* = (b·p - q) / b
    où b = cote nette (cote - 1), p = P(victoire), q = 1 - p

On utilise le Kelly fractionnel f*/fraction (par défaut /4) pour
réduire la variance et la ruine potentielle.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KellyResult:
    odd_value: float
    real_probability: float
    full_kelly: float       # f* brut
    fractional_kelly: float # f* / fraction (recommandé pour miser)
    fraction_used: float    # diviseur appliqué (ex: 0.25 = Kelly/4)
    stake_amount: float     # montant en € pour un bankroll donné
    bankroll: float

    @property
    def is_positive(self) -> bool:
        return self.full_kelly > 0

    def __str__(self) -> str:
        if not self.is_positive:
            return f"Kelly négatif ({self.full_kelly:.4f}) — pari déconseillé"
        return (
            f"Kelly: {self.full_kelly:.4f} ({self.full_kelly*100:.2f}%) | "
            f"Fractionnel ({self.fraction_used:.0%}): {self.fractional_kelly*100:.2f}% | "
            f"Mise: €{self.stake_amount:.2f} sur €{self.bankroll:.2f}"
        )


def kelly_criterion(
    odd_value: float,
    real_probability: float,
    bankroll: float = 1000.0,
    fraction: float = 0.25,
) -> KellyResult:
    """
    Calcule la mise optimale par Kelly Criterion.

    Args:
        odd_value: Cote décimale (ex: 2.15)
        real_probability: Probabilité estimée de victoire (0 < p < 1)
        bankroll: Capital disponible en €
        fraction: Diviseur Kelly (0.25 = Kelly quart, recommandé)

    Returns:
        KellyResult avec mise recommandée.
    """
    if not (0 < real_probability < 1):
        raise ValueError(f"real_probability doit être dans (0,1), reçu: {real_probability}")
    if odd_value <= 1.0:
        raise ValueError(f"Cote invalide: {odd_value}")
    if bankroll <= 0:
        raise ValueError(f"Bankroll invalide: {bankroll}")
    if not (0 < fraction <= 1):
        raise ValueError(f"Fraction invalide: {fraction}")

    b = odd_value - 1.0          # gain net par unité misée
    p = real_probability
    q = 1.0 - p

    full_kelly = (b * p - q) / b

    # Kelly négatif → ne pas parier
    fractional = max(0.0, full_kelly) * fraction
    stake = fractional * bankroll

    return KellyResult(
        odd_value=odd_value,
        real_probability=real_probability,
        full_kelly=full_kelly,
        fractional_kelly=fractional,
        fraction_used=fraction,
        stake_amount=stake,
        bankroll=bankroll,
    )


def kelly_multi_outcome(
    odds: list[float],
    real_probs: list[float],
    bankroll: float = 1000.0,
    fraction: float = 0.25,
) -> list[KellyResult]:
    """Calcule Kelly pour chaque outcome d'un marché complet."""
    if len(odds) != len(real_probs):
        raise ValueError("odds et real_probs doivent avoir la même longueur")
    return [
        kelly_criterion(o, p, bankroll, fraction)
        for o, p in zip(odds, real_probs)
    ]
