# 🏆 Betting Analyzer Pro

> **⚠ Avertissement** : Cet outil est fourni à des fins **éducatives et d'analyse statistique uniquement**.
> Les paris sportifs comportent des risques financiers élevés. Ne misez jamais plus que ce que vous pouvez vous permettre de perdre.
> Vérifiez la légalité des paris en ligne dans votre pays.

Outil CLI + Dashboard de détection des **value bets** et **arbitrages** sur 1XBET,
basé sur le calcul de l'Expected Value, le Kelly Criterion, et un modèle de Poisson.

---

## Installation rapide

```bash
# 1. Cloner / décompresser le projet
cd betting_analyzer

# 2. Créer et activer le virtualenv
python -m venv venv
source venv/bin/activate       # Linux/Mac
venv\Scripts\activate          # Windows

# 3. Installer les dépendances
pip install -r requirements.txt
playwright install chromium

# 4. Configurer
cp .env.example .env
# Éditer .env et ajouter ODDS_API_KEY (https://the-odds-api.com — gratuit)
```

Ou en une commande :

```bash
chmod +x start.sh && ./start.sh
```

---

## Utilisation

### Scan de value bets (football)
```bash
python main.py scan --sport football --min-ev 5 --min-confidence 65
```

### Matchs en direct
```bash
python main.py scan --sport tennis --live
```

### Détection d'arbitrage
```bash
python main.py arbitrage --sport all
```

### Analyse d'un match précis
```bash
python main.py analyze "PSG vs Real Madrid"
```

### Dashboard web
```bash
python main.py dashboard
# Ouvrir http://localhost:8501
```

### Rapport HTML
```bash
python main.py report --output rapport_du_jour.html
```

---

## Architecture

```
betting_analyzer/
├── main.py                    # CLI (typer + rich)
├── config.py                  # Settings pydantic-settings
├── models/
│   ├── bet.py                 # Dataclasses : Bet, Market, Odd
│   ├── expected_value.py      # EV, probabilité implicite, remove_vig
│   ├── kelly.py               # Kelly Criterion (fractionnel)
│   └── poisson.py             # Modèle de Poisson (football)
├── scrapers/
│   ├── base_scraper.py        # Classe abstraite + retry/backoff
│   ├── xbet_scraper.py        # Playwright + interception XHR 1XBET
│   └── odds_api.py            # The Odds API (fallback officiel)
├── analyzers/
│   ├── value_bet_detector.py  # Détection value bets (EV > 0)
│   ├── arbitrage_detector.py  # Détection arbitrage (Σ1/c < 1)
│   └── confidence_scorer.py   # Score composite 0-100
├── dashboard/
│   └── app.py                 # Streamlit : tableaux, graphiques, filtres
├── utils/
│   ├── cache.py               # Redis ou shelve (fallback)
│   ├── formatter.py           # Tables Rich pour CLI
│   └── logger.py              # Loguru
└── tests/
    ├── test_ev.py             # Tests calcul EV
    ├── test_kelly.py          # Tests Kelly
    ├── test_poisson.py        # Tests modèle Poisson
    └── test_arbitrage.py      # Tests détection arbitrage
```

---

## Modèles mathématiques

### Expected Value
```
EV% = (p_réelle × cote - 1) × 100
```
Un EV > 0 signifie que la cote proposée est supérieure à la valeur "juste".

### Kelly Criterion
```
f* = (b·p - q) / b
```
Où `b = cote - 1`, `p = P(victoire)`, `q = 1 - p`.
On utilise le **Kelly fractionnel** (`f*/4`) pour limiter la variance.

### Modèle de Poisson (football)
```
λ_home = force_att_home × force_def_away × moy_buts_domicile_ligue
λ_away = force_att_away × force_def_home × moy_buts_extérieur_ligue
```
Les buts suivent une loi de Poisson indépendante par équipe.

### Score de confiance (0-100)
| Composante | Max |
|---|---|
| EV positif | 40 pts |
| Kelly fraction élevée | 20 pts |
| Cohérence modèle Poisson | 20 pts |
| Vig faible (marché liquide) | 10 pts |
| Cote dans plage 1.5–4.0 | 10 pts |

---

## Tests

```bash
# Tous les tests
make test

# Avec couverture
make test-cov

# Un test spécifique
pytest tests/test_kelly.py -v
```

---

## Configuration (.env)

| Variable | Défaut | Description |
|---|---|---|
| `ODDS_API_KEY` | — | Clé The Odds API (obligatoire pour fallback) |
| `CACHE_BACKEND` | `shelve` | `redis` ou `shelve` |
| `MIN_EV_THRESHOLD` | `3.0` | EV minimum pour afficher un value bet (%) |
| `MIN_CONFIDENCE_SCORE` | `60` | Score de confiance minimum (0-100) |
| `KELLY_FRACTION` | `0.25` | Diviseur Kelly (0.25 = Kelly/4) |
| `DEFAULT_BANKROLL` | `1000` | Bankroll de référence (€) |
| `SCRAPER_HEADLESS` | `true` | Playwright headless |
