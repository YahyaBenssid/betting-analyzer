#!/usr/bin/env bash
# ============================================================
# Script de démarrage rapide — Betting Analyzer Pro
# ============================================================
set -euo pipefail

echo "🏆 Betting Analyzer Pro — Démarrage"
echo "⚠  Outil éducatif. Les paris comportent des risques financiers."
echo ""

# Vérifie Python 3.11+
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
required="3.11"
if [[ "$(printf '%s\n' "$required" "$python_version" | sort -V | head -n1)" != "$required" ]]; then
    echo "❌ Python $required+ requis. Version actuelle: $python_version"
    exit 1
fi

# Crée le venv si nécessaire
if [ ! -d "venv" ]; then
    echo "📦 Création du virtualenv..."
    python3 -m venv venv
fi

source venv/bin/activate

# Installation des dépendances
echo "📦 Installation des dépendances..."
pip install -r requirements.txt --quiet
playwright install chromium --quiet 2>/dev/null || true

# Copie .env si absent
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚙  Fichier .env créé depuis .env.example"
    echo "   → Éditez .env pour ajouter votre clé ODDS_API_KEY"
    echo ""
fi

# Lance la commande passée en argument, ou le scan par défaut
CMD=${1:-"scan --sport football --min-ev 3"}
echo "🚀 Lancement : python main.py $CMD"
echo ""
python main.py $CMD
