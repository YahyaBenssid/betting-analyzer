"""
Dashboard Streamlit — Betting Analyzer Pro.
Lancement : streamlit run dashboard/app.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Ajoute le dossier parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st

from analyzers.arbitrage_detector import ArbitrageDetector
from analyzers.confidence_scorer import ConfidenceScorer
from analyzers.value_bet_detector import ValueBetDetector, ValueBetResult
from config import settings
from models.bet import Sport
from utils.logger import setup_logging

setup_logging("WARNING")

# ------------------------------------------------------------------ #
# Config Streamlit

st.set_page_config(
    page_title="Betting Analyzer Pro",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.metric-card {background:#1e293b; border-radius:8px; padding:1rem; margin:.5rem 0}
.ev-positive {color:#22c55e; font-weight:bold}
.ev-negative {color:#ef4444}
.stDataFrame {font-size:0.85rem}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Sidebar — Filtres

with st.sidebar:
    st.title("🏆 Betting Analyzer")
    st.caption("⚠ Outil éducatif — risque financier")
    st.divider()

    sport_choice = st.selectbox("Sport", ["football", "tennis", "basketball", "hockey", "all"])
    min_ev = st.slider("EV minimum (%)", 0.0, 20.0, float(settings.min_ev_threshold), 0.5)
    min_conf = st.slider("Confiance minimum", 0, 100, int(settings.min_confidence_score), 5)
    bankroll = st.number_input("Bankroll (€)", 100.0, 1_000_000.0, float(settings.default_bankroll), 100.0)
    live_only = st.checkbox("Matchs en direct uniquement")
    use_fallback = st.checkbox("Utiliser The Odds API (fallback)")

    refresh = st.button("🔄 Actualiser", use_container_width=True)
    st.caption(f"Auto-refresh toutes les {settings.refresh_interval}s")

# ------------------------------------------------------------------ #
# Chargement des données (avec cache Streamlit)

sport_map = {
    "football": Sport.FOOTBALL, "tennis": Sport.TENNIS,
    "basketball": Sport.BASKETBALL, "hockey": Sport.HOCKEY, "all": None,
}


@st.cache_data(ttl=settings.refresh_interval)
def load_data(sport_key: str, live: bool, fallback: bool, _bankroll: float):
    """Charge et analyse les matchs (résultat mis en cache TTL=refresh_interval)."""
    async def _run():
        if not fallback:
            try:
                from scrapers.xbet_scraper import XBetScraper
                scraper = XBetScraper()
                matches = await scraper.fetch_matches(sport=sport_map[sport_key], live_only=live)
                if matches:
                    return matches
            except Exception:
                pass

        from scrapers.odds_api import OddsAPIClient
        client = OddsAPIClient()
        return await client.fetch_matches(sport=sport_map[sport_key], live_only=live)

    matches = asyncio.run(_run())

    use_poisson = sport_key == "football"
    detector = ValueBetDetector(bankroll=_bankroll, use_poisson=use_poisson)
    results = detector.analyze(matches)
    ConfidenceScorer().score_all(results)

    arb_detector = ArbitrageDetector(bankroll=_bankroll)
    arbs = arb_detector.detect(matches)

    return matches, results, arbs


# ------------------------------------------------------------------ #
# Chargement

try:
    with st.spinner("Chargement des données…"):
        matches, all_results, arbs = load_data(sport_choice, live_only, use_fallback, bankroll)
except Exception as exc:
    st.error(f"Erreur de chargement : {exc}")
    st.stop()

# ------------------------------------------------------------------ #
# Filtrage

filtered = [
    r for r in all_results
    if r.ev.ev_pct >= min_ev and r.confidence_score >= min_conf
]

# ------------------------------------------------------------------ #
# KPIs en haut

st.title("🏆 Betting Analyzer Pro")
st.caption(f"Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')} | {len(matches)} matchs analysés")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Matchs analysés", len(matches))
col2.metric("Value bets détectés", len(all_results))
col3.metric(f"≥ EV {min_ev:.0f}% & conf {min_conf:.0f}", len(filtered))
col4.metric("Arbitrages", len(arbs))
best_ev = max((r.ev.ev_pct for r in all_results), default=0.0)
col5.metric("Meilleur EV", f"{best_ev:+.1f}%")

st.divider()

# ------------------------------------------------------------------ #
# Onglets principaux

tab1, tab2, tab3, tab4 = st.tabs(["📊 Value Bets", "⚡ Arbitrages", "📈 Distribution EV", "💰 Bankroll"])

# --- Tab 1 : Value Bets ---
with tab1:
    if not filtered:
        st.info("Aucun value bet avec ces critères. Baissez les seuils dans la sidebar.")
    else:
        rows = []
        for r in filtered[:50]:
            rows.append({
                "Match": r.match.label,
                "Marché": r.market_name,
                "Outcome": r.outcome,
                "Cote": round(r.odd_value, 2),
                "EV (%)": round(r.ev.ev_pct, 2),
                "P implicite": f"{r.ev.implied_prob:.1%}",
                "P réelle": f"{r.ev.real_prob:.1%}",
                "Kelly (%)": round(r.kelly.fractional_kelly * 100, 2),
                "Mise €": round(r.kelly.stake_amount, 2),
                "Confiance": round(r.confidence_score, 0),
                "✓": "✅" if r.is_recommended else "⚠️",
            })

        df = pd.DataFrame(rows)

        def color_ev(val):
            if isinstance(val, (int, float)):
                return "color: #22c55e" if val > 0 else "color: #ef4444"
            return ""

        st.dataframe(
            df.style.map(color_ev, subset=["EV (%)"]),
            use_container_width=True,
            hide_index=True,
        )

# --- Tab 2 : Arbitrages ---
with tab2:
    if not arbs:
        st.info("Aucune opportunité d'arbitrage trouvée.")
    else:
        for arb in arbs:
            profit = arb.bankroll * arb.profit_pct / 100
            with st.expander(f"⚡ {arb.match.label} — +{arb.profit_pct:.2f}% = +€{profit:.2f}"):
                cols = st.columns(len(arb.outcomes))
                for col, outcome, odd, stake, bk in zip(
                    cols, arb.outcomes, arb.odds, arb.optimal_stakes, arb.bookmakers
                ):
                    col.metric(f"{outcome} ({bk})", f"@{odd:.2f}", f"Mise: €{stake:.2f}")

# --- Tab 3 : Distribution EV ---
with tab3:
    if all_results:
        import altair as alt

        ev_data = pd.DataFrame({
            "EV (%)": [r.ev.ev_pct for r in all_results],
            "Confiance": [r.confidence_score for r in all_results],
            "Match": [r.match.label for r in all_results],
            "Cote": [r.odd_value for r in all_results],
        })

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Distribution des EV")
            hist = alt.Chart(ev_data).mark_bar(color="#3b82f6", opacity=0.8).encode(
                x=alt.X("EV (%):Q", bin=alt.Bin(maxbins=30), title="Expected Value (%)"),
                y=alt.Y("count():Q", title="Nombre de paris"),
                tooltip=["count()"],
            ).properties(height=300)
            st.altair_chart(hist, use_container_width=True)

        with col_b:
            st.subheader("EV vs Confiance")
            scatter = alt.Chart(ev_data).mark_circle(size=60, opacity=0.7).encode(
                x=alt.X("EV (%):Q"),
                y=alt.Y("Confiance:Q"),
                color=alt.Color("EV (%):Q", scale=alt.Scale(scheme="redyellowgreen")),
                tooltip=["Match", "EV (%)", "Confiance", "Cote"],
            ).properties(height=300)
            st.altair_chart(scatter, use_container_width=True)
    else:
        st.info("Pas de données à afficher.")

# --- Tab 4 : Bankroll Tracker ---
with tab4:
    st.subheader("💰 Suivi de Bankroll")
    st.info("Le suivi de bankroll nécessite d'enregistrer vos paris réels. Fonctionnalité en développement.")

    # Formulaire d'ajout de pari
    with st.form("add_bet"):
        c1, c2, c3, c4 = st.columns(4)
        bet_match = c1.text_input("Match")
        bet_outcome = c2.text_input("Outcome")
        bet_odds = c3.number_input("Cote", 1.01, 100.0, 2.0)
        bet_stake = c4.number_input("Mise (€)", 1.0, float(bankroll), 10.0)
        submitted = st.form_submit_button("Enregistrer le pari")
        if submitted and bet_match:
            st.success(f"Pari enregistré : {bet_match} | {bet_outcome} @ {bet_odds} | €{bet_stake}")
