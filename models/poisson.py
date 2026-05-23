"""
Modèle de Poisson pour la prédiction de scores de football.

Principe :
  Les buts marqués par chaque équipe suivent une loi de Poisson indépendante
  (hypothèse de Dixon-Coles, 1997, simplifiée).

  λ_home = force_att_home × force_def_away × moyenne_buts_domicile_ligue
  λ_away = force_att_away × force_def_home × moyenne_buts_extérieur_ligue

  P(score i-j) = Poisson(i; λ_home) × Poisson(j; λ_away)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, factorial, log


# Paramètres de ligue par défaut (moyennes Ligue 1/PL/Liga 2023-24)
DEFAULT_HOME_GOALS_AVG = 1.53
DEFAULT_AWAY_GOALS_AVG = 1.12
MAX_GOALS = 8  # plafond de simulation du score


@dataclass(frozen=True)
class TeamStats:
    """Forces offensives/défensives d'une équipe (normalisées autour de 1.0)."""
    name: str
    attack_strength: float   # > 1 = attaque forte
    defense_strength: float  # < 1 = défense forte (moins de buts encaissés)

    @classmethod
    def average(cls, name: str) -> "TeamStats":
        """Équipe 'moyenne' (force = 1.0)."""
        return cls(name=name, attack_strength=1.0, defense_strength=1.0)

    @classmethod
    def from_goals(
        cls,
        name: str,
        goals_scored: float,
        goals_conceded: float,
        league_avg_scored: float = DEFAULT_HOME_GOALS_AVG,
        league_avg_conceded: float = DEFAULT_AWAY_GOALS_AVG,
    ) -> "TeamStats":
        """Calcule les forces à partir des moyennes de buts."""
        att = goals_scored / league_avg_scored if league_avg_scored > 0 else 1.0
        def_ = goals_conceded / league_avg_conceded if league_avg_conceded > 0 else 1.0
        return cls(name=name, attack_strength=att, defense_strength=def_)


@dataclass
class PoissonResult:
    home_team: str
    away_team: str
    lambda_home: float
    lambda_away: float
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    score_matrix: dict[tuple[int, int], float] = field(default_factory=dict)

    @property
    def most_likely_score(self) -> tuple[int, int]:
        if not self.score_matrix:
            return (0, 0)
        return max(self.score_matrix, key=lambda k: self.score_matrix[k])

    @property
    def over_2_5(self) -> float:
        """P(total buts > 2.5)."""
        return sum(
            p for (h, a), p in self.score_matrix.items() if h + a > 2
        )

    @property
    def btts(self) -> float:
        """P(les deux équipes marquent)."""
        return sum(
            p for (h, a), p in self.score_matrix.items() if h > 0 and a > 0
        )

    def __str__(self) -> str:
        h, a = self.most_likely_score
        return (
            f"{self.home_team} vs {self.away_team} | "
            f"λ_home={self.lambda_home:.2f} λ_away={self.lambda_away:.2f} | "
            f"1={self.prob_home_win:.1%} X={self.prob_draw:.1%} 2={self.prob_away_win:.1%} | "
            f"Score probable: {h}-{a} | "
            f"O2.5={self.over_2_5:.1%} BTTS={self.btts:.1%}"
        )


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) pour X ~ Poisson(λ)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * (lam ** k) / factorial(k)


def poisson_match_probabilities(
    home: TeamStats,
    away: TeamStats,
    home_goals_avg: float = DEFAULT_HOME_GOALS_AVG,
    away_goals_avg: float = DEFAULT_AWAY_GOALS_AVG,
    max_goals: int = MAX_GOALS,
) -> PoissonResult:
    """
    Prédit les probabilités d'un match de football via le modèle de Poisson.

    Args:
        home: Stats de l'équipe à domicile
        away: Stats de l'équipe à l'extérieur
        home_goals_avg: Moyenne de buts par match à domicile dans la ligue
        away_goals_avg: Moyenne de buts par match à l'extérieur dans la ligue
        max_goals: Nombre max de buts simulés par équipe

    Returns:
        PoissonResult avec matrice de scores et probabilités 1X2.
    """
    lambda_home = home.attack_strength * away.defense_strength * home_goals_avg
    lambda_away = away.attack_strength * home.defense_strength * away_goals_avg

    # Construction de la matrice de scores P(home=i, away=j)
    score_matrix: dict[tuple[int, int], float] = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            score_matrix[(i, j)] = _poisson_pmf(i, lambda_home) * _poisson_pmf(j, lambda_away)

    prob_home_win = sum(p for (h, a), p in score_matrix.items() if h > a)
    prob_draw = sum(p for (h, a), p in score_matrix.items() if h == a)
    prob_away_win = sum(p for (h, a), p in score_matrix.items() if h < a)

    return PoissonResult(
        home_team=home.name,
        away_team=away.name,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        prob_home_win=prob_home_win,
        prob_draw=prob_draw,
        prob_away_win=prob_away_win,
        score_matrix=score_matrix,
    )


def estimate_team_strengths_from_form(
    recent_goals_scored: list[int],
    recent_goals_conceded: list[int],
    league_avg_scored: float = DEFAULT_HOME_GOALS_AVG,
    league_avg_conceded: float = DEFAULT_AWAY_GOALS_AVG,
    name: str = "Team",
) -> TeamStats:
    """
    Estime les forces d'une équipe à partir de ses 5-10 derniers matchs.

    Args:
        recent_goals_scored: Buts marqués dans chaque match récent
        recent_goals_conceded: Buts encaissés dans chaque match récent
    """
    if not recent_goals_scored or not recent_goals_conceded:
        return TeamStats.average(name)

    avg_scored = sum(recent_goals_scored) / len(recent_goals_scored)
    avg_conceded = sum(recent_goals_conceded) / len(recent_goals_conceded)

    return TeamStats.from_goals(
        name=name,
        goals_scored=avg_scored,
        goals_conceded=avg_conceded,
        league_avg_scored=league_avg_scored,
        league_avg_conceded=league_avg_conceded,
    )
