"""
Détecteur de value bets.

Hiérarchie des sources de probabilités (par ordre de fiabilité) :
  1. Poisson calibré sur stats réelles football-data.org  (football 1X2)
  2. Poisson avec équipes moyennes                        (football 1X2, pas de clé API)
  3. Probabilités équilibrées (fair_probs = sans vig)     (tous sports, fallback final)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from config import settings
from models.bet import Sport
from models.expected_value import EVResult, compute_ev, remove_vig
from models.kelly import KellyResult, kelly_criterion
from models.poisson import PoissonResult, TeamStats, poisson_match_probabilities
from scrapers.base_scraper import ScrapedMatch, ScrapedOdd


@dataclass
class ValueBetResult:
    match: ScrapedMatch
    market_name: str
    outcome: str
    odd_value: float
    ev: EVResult
    kelly: KellyResult
    confidence_score: float = 0.0
    poisson_result: Optional[PoissonResult] = None
    stats_source: str = "fair_prob"   # "real_stats" | "poisson_avg" | "fair_prob"

    @property
    def is_recommended(self) -> bool:
        return (
            self.ev.is_value_bet
            and self.ev.ev_pct >= settings.min_ev_threshold
            and self.confidence_score >= settings.min_confidence_score
        )

    def __str__(self) -> str:
        return (
            f"{self.match.label} | {self.market_name} → {self.outcome} "
            f"@ {self.odd_value:.2f} | EV={self.ev.ev_pct:+.1f}% | "
            f"Kelly={self.kelly.fractional_kelly*100:.1f}% | "
            f"Conf={self.confidence_score:.0f}/100 [{self.stats_source}]"
        )


class ValueBetDetector:
    """
    Analyse une liste de matchs scrappés et retourne les value bets détectés.

    Args:
        bankroll: Capital de référence pour le calcul des mises Kelly.
        kelly_fraction: Diviseur Kelly (0.25 = Kelly/4).
        use_poisson: Active le modèle de Poisson pour le football.
        use_real_stats: Active l'intégration football-data.org (requiert clé API).
    """

    def __init__(
        self,
        bankroll: float = 1000.0,
        kelly_fraction: float = 0.25,
        use_poisson: bool = True,
        use_real_stats: bool = True,
    ) -> None:
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.use_poisson = use_poisson
        self.use_real_stats = use_real_stats and bool(settings.football_data_api_key)

        self._stats_provider = None
        if self.use_real_stats:
            from analyzers.stats_provider import get_stats_provider
            self._stats_provider = get_stats_provider()

    def analyze(self, matches: list[ScrapedMatch]) -> list[ValueBetResult]:
        """
        Analyse tous les matchs et retourne les value bets triés par EV décroissant.
        Si des stats réelles sont disponibles, les charge de façon asynchrone.
        """
        # Pré-charge les stats de ligue pour tous les matchs football en une passe
        if self.use_real_stats and self._stats_provider:
            self._prefetch_leagues(matches)

        results: list[ValueBetResult] = []
        for match in matches:
            for market_name, odds in match.markets.items():
                try:
                    vbs = self._analyze_market(match, market_name, odds)
                    results.extend(vbs)
                except Exception as exc:
                    logger.debug(f"Marché ignoré [{match.label} / {market_name}]: {exc}")

        results.sort(key=lambda r: r.ev.ev_pct, reverse=True)
        logger.info(
            f"[ValueBet] {len(results)} résultats sur {len(matches)} matchs | "
            f"stats_source={'real' if self.use_real_stats else 'fair_prob'}"
        )
        return results

    def _prefetch_leagues(self, matches: list[ScrapedMatch]) -> None:
        """
        Charge les stats de ligue en avance pour éviter de multiplier les appels API.
        Un seul appel par code de compétition, résultats mis en cache.
        """
        from analyzers.stats_provider import _guess_competition

        leagues_needed = set()
        for m in matches:
            if m.sport == Sport.FOOTBALL:
                code = _guess_competition(m.league)
                if code:
                    leagues_needed.add(code)

        if not leagues_needed:
            return

        logger.info(f"[ValueBet] Pré-chargement stats pour: {', '.join(leagues_needed)}")
        for code in leagues_needed:
            try:
                asyncio.get_event_loop().run_until_complete(
                    self._stats_provider._load_league(code)
                )
            except RuntimeError:
                # Déjà dans une event loop (ex: Streamlit) — utilise run_coroutine_threadsafe
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self._stats_provider._load_league(code)
                    )
                    future.result(timeout=30)
            except Exception as exc:
                logger.debug(f"Pré-chargement {code} échoué: {exc}")

    # ------------------------------------------------------------------ #

    def _analyze_market(
        self,
        match: ScrapedMatch,
        market_name: str,
        odds: list[ScrapedOdd],
    ) -> list[ValueBetResult]:
        valid_odds = [o for o in odds if o.value > 1.0]
        if len(valid_odds) < 2:
            return []

        impl_probs = [1.0 / o.value for o in valid_odds]
        fair_probs = remove_vig(impl_probs)

        real_probs, poisson_result, source = self._estimate_real_probabilities(
            match, market_name, valid_odds, fair_probs
        )

        results = []
        for i, odd in enumerate(valid_odds):
            real_p = real_probs[i]
            raw_ev = compute_ev(odd.value, real_p)
            ev = EVResult(
                outcome=odd.outcome,
                odd_value=raw_ev.odd_value,
                implied_prob=raw_ev.implied_prob,
                fair_prob=fair_probs[i],
                real_prob=real_p,
                ev_pct=raw_ev.ev_pct,
                is_value_bet=raw_ev.is_value_bet,
            )
            kelly = kelly_criterion(odd.value, real_p, self.bankroll, self.kelly_fraction)
            results.append(ValueBetResult(
                match=match,
                market_name=market_name,
                outcome=odd.outcome,
                odd_value=odd.value,
                ev=ev,
                kelly=kelly,
                poisson_result=poisson_result,
                stats_source=source,
            ))

        return results

    def _estimate_real_probabilities(
        self,
        match: ScrapedMatch,
        market_name: str,
        odds: list[ScrapedOdd],
        fair_probs: list[float],
    ) -> tuple[list[float], Optional[PoissonResult], str]:
        is_football = match.sport == Sport.FOOTBALL
        is_1x2 = market_name == "1X2" and len(odds) == 3
        is_ou = market_name.startswith("O/U") and len(odds) == 2
        is_hc = market_name == "Handicap" and len(odds) == 2

        if is_football and self.use_poisson and (is_1x2 or is_ou or is_hc):
            # Tentative stats réelles (1X2 seulement)
            if is_1x2 and self._stats_provider:
                result = self._poisson_with_real_stats(match, odds, fair_probs)
                if result:
                    probs, poisson = result
                    return probs, poisson, "real_stats"

            # Poisson équipes moyennes
            poisson = self._get_average_poisson(match)

            if is_1x2:
                probs = self._blend_poisson_fair(poisson, [o.outcome for o in odds], fair_probs)
                return probs, poisson, "poisson_avg"

            if is_ou:
                probs = self._ou_probs_from_poisson(market_name, odds, poisson, fair_probs)
                return probs, poisson, "poisson_avg"

            if is_hc:
                probs = self._handicap_probs_from_poisson(odds, poisson, fair_probs)
                return probs, poisson, "poisson_avg"

        return fair_probs, None, "fair_prob"

    def _poisson_with_real_stats(
        self,
        match: ScrapedMatch,
        odds: list[ScrapedOdd],
        fair_probs: list[float],
    ) -> Optional[tuple[list[float], PoissonResult]]:
        """
        Calcule Poisson en utilisant les vraies forces d'équipe (football-data.org).
        Retourne None si l'une des deux équipes est introuvable.
        """
        try:
            # Appel synchrone — les stats sont déjà dans le cache mémoire (pré-chargées)
            loop = asyncio.new_event_loop()
            home_stats, away_stats, home_avg, away_avg = loop.run_until_complete(
                self._fetch_both_stats(match)
            )
            loop.close()

            if home_stats is None or away_stats is None:
                return None

            poisson = poisson_match_probabilities(
                home=home_stats,
                away=away_stats,
                home_goals_avg=home_avg,
                away_goals_avg=away_avg,
            )
            probs = self._blend_poisson_fair(poisson, [o.outcome for o in odds], fair_probs)
            logger.debug(
                f"[Poisson/real] {match.label}: "
                f"1={poisson.prob_home_win:.1%} X={poisson.prob_draw:.1%} "
                f"2={poisson.prob_away_win:.1%} (λ={poisson.lambda_home:.2f}/{poisson.lambda_away:.2f})"
            )
            return probs, poisson
        except Exception as exc:
            logger.debug(f"Poisson real_stats échoué pour {match.label}: {exc}")
            return None

    async def _fetch_both_stats(
        self, match: ScrapedMatch
    ) -> tuple[Optional[TeamStats], Optional[TeamStats], float, float]:
        """Coroutine : charge home_stats, away_stats et les moyennes de ligue en parallèle."""
        home_task = self._stats_provider.get_team_stats(match.home_team, match.league, is_home=True)
        away_task = self._stats_provider.get_team_stats(match.away_team, match.league, is_home=False)
        avgs_task = self._stats_provider.get_league_averages(match.league)

        home_stats, away_stats, (home_avg, away_avg) = await asyncio.gather(
            home_task, away_task, avgs_task
        )
        return home_stats, away_stats, home_avg, away_avg

    def _get_average_poisson(self, match: ScrapedMatch) -> PoissonResult:
        """Poisson sans stats réelles — équipes moyennes (force = 1.0)."""
        return poisson_match_probabilities(
            home=TeamStats.average(match.home_team),
            away=TeamStats.average(match.away_team),
        )

    @staticmethod
    def _ou_probs_from_poisson(
        market_name: str,
        odds: list[ScrapedOdd],
        poisson: PoissonResult,
        fair_probs: list[float],
        blend: float = 0.60,
    ) -> list[float]:
        """Calcule P(Over) / P(Under) via la matrice de scores Poisson."""
        try:
            threshold = float(market_name.split()[-1])  # "O/U 2.5" → 2.5
        except (ValueError, IndexError):
            threshold = 2.5

        p_over = sum(
            p for (h, a), p in poisson.score_matrix.items()
            if h + a > threshold
        )
        p_under = 1.0 - p_over

        # Associe Over/Under aux bonnes cotes
        probs_poisson = []
        for o in odds:
            lbl = o.outcome.lower()
            if "over" in lbl:
                probs_poisson.append(p_over)
            else:
                probs_poisson.append(p_under)

        # Blend Poisson 60% + fair_prob 40%
        blended = [blend * pp + (1 - blend) * fp for pp, fp in zip(probs_poisson, fair_probs)]
        total = sum(blended)
        return [p / total for p in blended]

    @staticmethod
    def _handicap_probs_from_poisson(
        odds: list[ScrapedOdd],
        poisson: PoissonResult,
        fair_probs: list[float],
        blend: float = 0.55,
    ) -> list[float]:
        """Calcule les probabilités de handicap via la matrice de scores Poisson."""
        # Extrait le handicap depuis le label (ex: "Dom -1.5" → -1.5)
        hc_home = 0.0
        for o in odds:
            parts = o.outcome.split()
            for part in parts:
                try:
                    hc_home = float(part)
                    break
                except ValueError:
                    continue
            if "dom" in o.outcome.lower():
                break

        p_home_hc = sum(
            p for (h, a), p in poisson.score_matrix.items()
            if (h - a + hc_home) > 0
        )
        p_away_hc = 1.0 - p_home_hc

        probs_poisson = []
        for o in odds:
            if "dom" in o.outcome.lower():
                probs_poisson.append(p_home_hc)
            else:
                probs_poisson.append(p_away_hc)

        blended = [blend * pp + (1 - blend) * fp for pp, fp in zip(probs_poisson, fair_probs)]
        total = sum(blended)
        return [p / total for p in blended]

    @staticmethod
    def _blend_poisson_fair(
        poisson: PoissonResult,
        outcome_order: list[str],
        fair_probs: list[float],
        poisson_weight: float = 0.65,
    ) -> list[float]:
        """
        Blend 65% Poisson + 35% fair_probs.
        Quand les stats sont réelles, le Poisson est plus fiable → poids plus haut.
        Quand c'est des équipes moyennes, c'est quasi-inutile → le blend reste léger.
        """
        poisson_map = {
            "home": poisson.prob_home_win,
            "domicile": poisson.prob_home_win,
            "draw": poisson.prob_draw,
            "nul": poisson.prob_draw,
            "away": poisson.prob_away_win,
            "extérieur": poisson.prob_away_win,
        }
        blended = [
            poisson_weight * poisson_map.get(o.lower(), fp) + (1 - poisson_weight) * fp
            for o, fp in zip(outcome_order, fair_probs)
        ]
        total = sum(blended)
        return [p / total for p in blended]
