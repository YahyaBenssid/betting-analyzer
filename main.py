"""
⚠️  AVERTISSEMENT : Cet outil est fourni à des fins éducatives et d'analyse statistique.
    Les paris sportifs comportent des risques financiers élevés.
    Ne misez jamais plus que ce que vous pouvez vous permettre de perdre.
    Vérifiez la légalité des paris en ligne dans votre pays.
    Les performances passées ne garantissent pas les résultats futurs.

Point d'entrée CLI — Betting Analyzer Pro.
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Optional

import typer
from loguru import logger
from rich.prompt import Confirm

from analyzers.arbitrage_detector import ArbitrageDetector
from analyzers.confidence_scorer import ConfidenceScorer
from analyzers.value_bet_detector import ValueBetDetector
from config import settings
from models.bet import Sport
from utils.cache import get_cache
from utils.formatter import (
    console,
    print_arbitrages,
    print_banner,
    print_match_analysis,
    print_value_bets,
)
from utils.logger import setup_logging

app = typer.Typer(
    name="betting-analyzer",
    help="🏆 Betting Analyzer Pro — Détection de value bets et d'arbitrage sur 1XBET",
    add_completion=False,
)


class SportOption(str, Enum):
    football = "football"
    tennis = "tennis"
    basketball = "basketball"
    hockey = "hockey"
    all = "all"


def _sport_from_option(opt: SportOption) -> Optional[Sport]:
    mapping = {
        SportOption.football: Sport.FOOTBALL,
        SportOption.tennis: Sport.TENNIS,
        SportOption.basketball: Sport.BASKETBALL,
        SportOption.hockey: Sport.HOCKEY,
        SportOption.all: None,
    }
    return mapping[opt]


async def _fetch_matches(sport: Optional[Sport], live_only: bool, use_fallback: bool):
    """Tente 1XBET en premier, replie sur The Odds API si nécessaire."""
    cache = get_cache()
    cache_key = f"matches:{sport}:{live_only}"

    cached = cache.get(cache_key)
    if cached:
        logger.info(f"Cache hit pour {cache_key}")
        return cached

    if not use_fallback:
        try:
            from scrapers.xbet_scraper import XBetScraper
            scraper = XBetScraper(
                max_retries=settings.scraper_max_retries,
                delay_min=settings.scraper_delay_min,
                delay_max=settings.scraper_delay_max,
            )
            matches = await scraper.fetch_matches(sport=sport, live_only=live_only)
            if matches:
                cache.set(cache_key, matches, settings.cache_ttl_seconds)
                return matches
            logger.warning("1XBET: aucun match récupéré — bascule vers The Odds API")
        except Exception as exc:
            logger.warning(f"1XBET scraper échoué: {exc} — bascule vers The Odds API")

    from scrapers.odds_api import OddsAPIClient
    client = OddsAPIClient(
        max_retries=settings.scraper_max_retries,
        delay_min=settings.scraper_delay_min,
    )
    matches = await client.fetch_matches(sport=sport, live_only=live_only)
    cache.set(cache_key, matches, settings.cache_ttl_seconds)
    return matches


# ------------------------------------------------------------------ #
# Commande : scan

@app.command()
def scan(
    sport: SportOption = typer.Option(SportOption.football, "--sport", "-s", help="Sport à analyser"),
    min_ev: float = typer.Option(settings.min_ev_threshold, "--min-ev", help="EV minimum (%)"),
    min_confidence: float = typer.Option(settings.min_confidence_score, "--min-confidence", help="Score de confiance minimum (0-100)"),
    live: bool = typer.Option(False, "--live", help="Matchs en cours uniquement"),
    fallback: bool = typer.Option(False, "--fallback", help="Forcer The Odds API (ignorer 1XBET)"),
    bankroll: float = typer.Option(settings.default_bankroll, "--bankroll", help="Bankroll de référence (€)"),
    top: int = typer.Option(20, "--top", help="Nombre de résultats affichés"),
) -> None:
    """Scanne les matchs et affiche les meilleurs value bets."""
    setup_logging(settings.log_level, settings.log_file)
    sport_filter = _sport_from_option(sport)

    console.print(f"\n[dim]⚠  Cet outil est fourni à des fins éducatives uniquement.[/dim]\n")

    with console.status(f"[cyan]Récupération des matchs ({sport.value})…[/cyan]"):
        matches = asyncio.run(_fetch_matches(sport_filter, live, fallback))

    print_banner(sport.value, len(matches))

    if not matches:
        console.print("[red]Aucun match récupéré. Vérifiez votre connexion ou votre clé API.[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Analyse des cotes…[/cyan]"):
        detector = ValueBetDetector(bankroll=bankroll, use_poisson=(sport == SportOption.football))
        results = detector.analyze(matches)

        scorer = ConfidenceScorer()
        results = scorer.score_all(results)

        # Filtrage selon critères CLI
        filtered = [
            r for r in results
            if r.ev.ev_pct >= min_ev and r.confidence_score >= min_confidence
        ]

    print_value_bets(filtered, max_rows=top)

    # Arbitrages en bonus
    arb_detector = ArbitrageDetector(bankroll=bankroll)
    arbs = arb_detector.detect(matches)
    print_arbitrages(arbs)


# ------------------------------------------------------------------ #
# Commande : arbitrage

@app.command()
def arbitrage(
    sport: SportOption = typer.Option(SportOption.all, "--sport", "-s"),
    bankroll: float = typer.Option(settings.default_bankroll, "--bankroll"),
    min_profit: float = typer.Option(0.5, "--min-profit", help="Profit minimum en %"),
    fallback: bool = typer.Option(False, "--fallback"),
) -> None:
    """Recherche d'opportunités d'arbitrage pur."""
    setup_logging(settings.log_level, settings.log_file)
    sport_filter = _sport_from_option(sport)

    with console.status("[magenta]Scan arbitrage…[/magenta]"):
        matches = asyncio.run(_fetch_matches(sport_filter, False, fallback))

    print_banner(sport.value, len(matches))

    detector = ArbitrageDetector(bankroll=bankroll, min_profit_pct=min_profit)
    opportunities = detector.detect(matches)
    print_arbitrages(opportunities, bankroll=bankroll)

    if not opportunities:
        console.print("[dim]Aucun arbitrage trouvé avec ces paramètres.[/dim]")


# ------------------------------------------------------------------ #
# Commande : analyze (un match précis)

@app.command()
def analyze(
    match: str = typer.Argument(..., help='Ex: "PSG vs Real Madrid"'),
    bankroll: float = typer.Option(settings.default_bankroll, "--bankroll"),
    fallback: bool = typer.Option(False, "--fallback"),
) -> None:
    """Analyse détaillée d'un match spécifique."""
    setup_logging(settings.log_level, settings.log_file)

    with console.status(f"[cyan]Recherche de '{match}'…[/cyan]"):
        matches = asyncio.run(_fetch_matches(None, False, fallback))

    # Recherche approximative par nom
    query = match.lower()
    found = [
        m for m in matches
        if query in m.home_team.lower() or query in m.away_team.lower()
        or all(part in m.label.lower() for part in query.split(" vs "))
    ]

    if not found:
        console.print(f"[red]Match '{match}' non trouvé dans les données courantes.[/red]")
        raise typer.Exit(1)

    target = found[0]
    console.print(f"\n[bold]Match trouvé : {target.label} ({target.league})[/bold]")

    detector = ValueBetDetector(bankroll=bankroll, use_poisson=True)
    results = detector.analyze([target])
    ConfidenceScorer().score_all(results)

    print_match_analysis(results, target.label)


# ------------------------------------------------------------------ #
# Commande : dashboard

@app.command()
def dashboard() -> None:
    """Lance le dashboard Streamlit."""
    import subprocess
    import sys
    from pathlib import Path

    setup_logging(settings.log_level, settings.log_file)
    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"

    console.print(f"[cyan]Lancement du dashboard sur http://localhost:{settings.dashboard_port}[/cyan]")
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(dashboard_path),
            "--server.port", str(settings.dashboard_port),
            "--server.address", settings.dashboard_host,
            "--server.headless", "true",
        ],
        check=True,
    )


# ------------------------------------------------------------------ #
# Commande : report

@app.command()
def report(
    output: str = typer.Option("report.html", "--output", "-o", help="Fichier de sortie (.html)"),
    sport: SportOption = typer.Option(SportOption.football, "--sport", "-s"),
    bankroll: float = typer.Option(settings.default_bankroll, "--bankroll"),
) -> None:
    """Génère un rapport HTML avec tous les value bets du jour."""
    setup_logging(settings.log_level, settings.log_file)
    sport_filter = _sport_from_option(sport)

    with console.status("[cyan]Génération du rapport…[/cyan]"):
        matches = asyncio.run(_fetch_matches(sport_filter, False, False))
        detector = ValueBetDetector(bankroll=bankroll)
        results = detector.analyze(matches)
        ConfidenceScorer().score_all(results)

    _write_html_report(results, output)
    console.print(f"[green]Rapport généré : {output}[/green]")


def _write_html_report(results, output_path: str) -> None:
    from datetime import datetime
    rows = ""
    for i, r in enumerate(results[:50], 1):
        ev_color = "#22c55e" if r.ev.ev_pct > 0 else "#ef4444"
        rows += (
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{r.match.label}</td>"
            f"<td>{r.market_name}</td>"
            f"<td>{r.outcome}</td>"
            f"<td>{r.odd_value:.2f}</td>"
            f"<td style='color:{ev_color}'>{r.ev.ev_pct:+.1f}%</td>"
            f"<td>{r.kelly.fractional_kelly*100:.1f}%</td>"
            f"<td>{r.confidence_score:.0f}/100</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<title>Betting Analyzer Report — {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
  body{{font-family:system-ui;background:#0f172a;color:#e2e8f0;padding:2rem}}
  h1{{color:#fbbf24}} table{{border-collapse:collapse;width:100%}}
  th{{background:#1e293b;padding:10px;text-align:left;color:#94a3b8}}
  td{{padding:8px 10px;border-bottom:1px solid #1e293b}}
  tr:hover{{background:#1e293b}}
</style></head>
<body>
<h1>🏆 Betting Analyzer Pro — Rapport du {datetime.now().strftime('%Y-%m-%d %H:%M')}</h1>
<p style="color:#ef4444">⚠ Outil éducatif uniquement. Les paris comportent des risques financiers.</p>
<table>
<thead><tr><th>#</th><th>Match</th><th>Marché</th><th>Outcome</th><th>Cote</th><th>EV</th><th>Kelly</th><th>Confiance</th></tr></thead>
<tbody>{rows}</tbody>
</table></body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    app()
