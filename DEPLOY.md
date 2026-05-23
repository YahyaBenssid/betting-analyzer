# Déploiement — Betting Analyzer Pro

## Architecture

```
[Vercel] Next.js dashboard  ──→  [Railway] FastAPI Python
  betting-analyzer.vercel.app       betting-api.railway.app
```

---

## Étape 1 — Préparer le dépôt GitHub

```bash
cd Bureau/betting_analyzer
git init
git add .
git commit -m "init: betting analyzer pro"
# Créer un repo sur github.com puis :
git remote add origin https://github.com/TON_USER/betting-analyzer.git
git push -u origin main
```

---

## Étape 2 — Déployer le backend sur Railway

1. Aller sur **railway.app** → Se connecter avec GitHub
2. **New Project** → **Deploy from GitHub repo**
3. Sélectionner `betting-analyzer`
4. Railway détecte automatiquement `railway.toml`

**Variables d'environnement à ajouter dans Railway :**
```
ODDS_API_KEY=ta_cle_the_odds_api
FOOTBALL_DATA_API_KEY=ta_cle_football_data
CACHE_BACKEND=shelve
MIN_EV_THRESHOLD=3.0
KELLY_FRACTION=0.25
DEFAULT_BANKROLL=1000
```

5. Après déploiement → noter l'URL : `https://betting-analyzer-xxx.railway.app`

---

## Étape 3 — Déployer le frontend sur Vercel

1. Aller sur **vercel.com** → Se connecter avec GitHub
2. **New Project** → Importer `betting-analyzer`
3. **Root Directory** : changer en `web`
4. **Framework Preset** : Next.js (auto-détecté)

**Variables d'environnement à ajouter dans Vercel :**
```
NEXT_PUBLIC_API_URL=https://betting-analyzer-xxx.railway.app
```
(Remplacer par l'URL Railway de l'étape 2)

5. **Deploy** → Vercel construit et publie automatiquement

---

## Résultat

- **Dashboard** : `https://betting-analyzer.vercel.app`
- **API** : `https://betting-analyzer-xxx.railway.app/api/health`

Chaque `git push` sur `main` redéploie automatiquement les deux.

---

## Clés API gratuites

| Service | URL | Limite |
|---|---|---|
| The Odds API | https://the-odds-api.com | 500 req/mois |
| football-data.org | https://www.football-data.org | 10 req/min |

---

## Test local avant déploiement

```bash
# Backend
cd api && uvicorn server:app --reload
# → http://localhost:8000/api/health

# Frontend (autre terminal)
cd web && npm install && npm run dev
# → http://localhost:3000
```
