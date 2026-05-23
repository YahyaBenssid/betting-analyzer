"""
Formatage Rich pour la sortie CLI.
Toutes les tables et panneaux passent par ce module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from analyzers.arbitrage_detector import ArbitrageOpportunity
from analyzers.value_bet_detector import ValueBetResult

console = Console()


# ------------------------------------------------------------------ #
# Bannière

def print_banner(sport: str = "all", match_count: int = 0) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = f"Scan du {now} | {sport.capitalize()} | {match_count} matchs analysés"
    panel = Panel(
        Text.assemble(
            ("🏆 BETTING ANALYZER PRO", "bold yellow"),
            " — ",
            ("1XBET Intelligence Engine\n", "bold white"),
            (subtitle, "dim"),
        ),
        border_style="yellow",
        padding=(0, 2),
    )
    console.print(panel)


# ------------------------------------------------------------------ #
# Table des value bets

def print_value_bets(results: list[ValueBetResult], max_rows: int = 20) -> None:
    if not results:
        console.print("[dim]Aucun value bet détecté avec ces critères.[/dim]")
        return

    console.print("\n[bold cyan]MEILLEURS VALUE BETS DÉTECTÉS[/bold cyan]")
    console.rule(style="cyan")

    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold white",
        border_style="dim",
        row_styles=["", "dim"],
    )

    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("MATCH", min_width=24)
    table.add_column("MARCHÉ", min_width=12)
    table.add_column("OUTCOME", min_width=8)
    table.add_column("COTE", justify="right", min_width=6)
    table.add_column("EV", justify="right", min_width=7)
    table.add_column("KELLY", justify="right", min_width=7)
    table.add_column("CONF", justify="right", min_width=10)
    table.add_column("✓", width=3, justify="center")

    for i, r in enumerate(results[:max_rows], start=1):
        ev_color = "green" if r.ev.ev_pct >= 5 else "yellow"
        conf_color = "green" if r.confidence_score >= 65 else "yellow" if r.confidence_score >= 50 else "red"
        tick = "✅" if r.is_recommended else "⚠️" if r.ev.is_value_bet else "❌"

        table.add_row(
            str(i),
            r.match.label[:30],
            r.market_name,
            r.outcome,
            f"{r.odd_value:.2f}",
            f"[{ev_color}]{r.ev.ev_pct:+.1f}%[/{ev_color}]",
            f"{r.kelly.fractional_kelly*100:.1f}%",
            f"[{conf_color}]{r.confidence_score:.0f}/100[/{conf_color}]",
            tick,
        )

    console.print(table)
    recommended = sum(1 for r in results if r.is_recommended)
    console.print(
        f"[dim]{recommended} pari(s) recommandé(s) sur {len(results)} value bets détectés[/dim]\n"
    )


# ------------------------------------------------------------------ #
# Table des arbitrages

def print_arbitrages(opportunities: list[ArbitrageOpportunity], bankroll: float = 1000.0) -> None:
    if not opportunities:
        console.print("[dim]Aucune opportunité d'arbitrage détectée.[/dim]")
        return

    console.print("\n[bold magenta]ARBITRAGES DÉTECTÉS[/bold magenta]")
    console.rule(style="magenta")

    for arb in opportunities:
        profit = arb.bankroll * arb.profit_pct / 100.0
        stakes_str = " | ".join(
            f"{o}: €{s:.2f}@{c:.2f}({bk})"
            for o, s, c, bk in zip(arb.outcomes, arb.optimal_stakes, arb.odds, arb.bookmakers)
        )
        console.print(
            f" ⚡ [bold]{arb.match.label}[/bold] | "
            f"Profit: [green]+{arb.profit_pct:.2f}%[/green] = "
            f"[bold green]+€{profit:.2f}[/bold green] sur €{arb.bankroll:.0f}\n"
            f"   [dim]{stakes_str}[/dim]"
        )

    console.print()


# ------------------------------------------------------------------ #
# Affichage d'un seul match analysé

def print_match_analysis(results: list[ValueBetResult], match_label: str) -> None:
    console.print(f"\n[bold]Analyse : {match_label}[/bold]\n")
    for r in results:
        ev_sign = "+" if r.ev.ev_pct >= 0 else ""
        console.print(
            f"  {r.market_name} → [bold]{r.outcome}[/bold] @ {r.odd_value:.2f}\n"
            f"    EV: [{'green' if r.ev.ev_pct > 0 else 'red'}]{ev_sign}{r.ev.ev_pct:.2f}%[/]\n"
            f"    P implicite: {r.ev.implied_prob:.1%}  |  P fair: {r.ev.fair_prob:.1%}  |  P réelle: {r.ev.real_prob:.1%}\n"
            f"    Kelly complet: {r.kelly.full_kelly*100:.2f}%  |  Kelly /4: {r.kelly.fractional_kelly*100:.2f}%\n"
            f"    Mise suggérée: €{r.kelly.stake_amount:.2f}  |  Score: {r.confidence_score:.0f}/100\n"
        )
