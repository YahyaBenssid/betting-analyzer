"""
Modèle Elo pour le tennis — estimation de P(victoire) indépendante des bookmakers.

Principe :
  P(A bat B) = 1 / (1 + 10^((Elo_B - Elo_A) / 400))

Les ratings sont spécifiques à la surface (clay/hard/grass).
Ils sont calibrés sur les performances 2023-2025.
"""
from __future__ import annotations
import re

# ── ATP Clay Court Elo (approximatif, calibré Roland Garros 2023-2025) ──────
ATP_CLAY_ELO: dict[str, float] = {
    # Top 10 clay
    "carlos alcaraz": 2240,
    "jannik sinner": 2190,
    "novak djokovic": 2140,
    "rafael nadal": 2120,
    "casper ruud": 2050,
    "stefanos tsitsipas": 2030,
    "alexander zverev": 2060,
    "andrey rublev": 1990,
    "holger rune": 1980,
    "grigor dimitrov": 1960,
    # 11-30
    "taylor fritz": 1910,
    "tommy paul": 1900,
    "alex de minaur": 1910,
    "ugo humbert": 1930,
    "nicolas jarry": 1950,
    "sebastian baez": 1960,
    "francisco cerundolo": 1940,
    "felix auger-aliassime": 1920,
    "ben shelton": 1890,
    "arthur fils": 1960,
    "lorenzo musetti": 1950,
    "jack draper": 1920,
    "matteo berrettini": 1930,
    "karen khachanov": 1910,
    "alejandro davidovich fokina": 1940,
    "gael monfils": 1890,
    "albert ramos-vinolas": 1920,
    "cameron norrie": 1890,
    "diego schwartzman": 1930,
    "pablo carreno busta": 1940,
    # 31-60
    "dominic thiem": 1880,
    "daniel altmaier": 1890,
    "roberto bautista agut": 1910,
    "fabio fognini": 1890,
    "jaume munar": 1910,
    "maxime cressy": 1850,
    "lloyd harris": 1860,
    "christopher eubanks": 1860,
    "luca nardi": 1870,
    "francisco fabian marozsan": 1880,
    "fabian marozsan": 1880,
    "learner tien": 1860,
    "cristian garin": 1890,
    "miomir kecmanovic": 1890,
    "tomas machac": 1870,
    "gabriel diallo": 1850,
    "alexandre muller": 1860,
    "matteo arnaldi": 1880,
    "giovanni mpetshi perricard": 1860,
    "hugo gaston": 1890,
    "corentin moutet": 1880,
    "arthur rinderknech": 1870,
    "quentin halys": 1860,
    "raphael collignon": 1830,
}

# ── WTA Clay Court Elo ───────────────────────────────────────────────────────
WTA_CLAY_ELO: dict[str, float] = {
    "iga swiatek": 2220,
    "aryna sabalenka": 2140,
    "coco gauff": 2080,
    "elena rybakina": 2060,
    "jessica pegula": 2000,
    "caroline wozniacki": 1950,
    "marketa vondrousova": 2020,
    "ons jabeur": 2000,
    "karolina muchova": 2010,
    "beatriz haddad maia": 2030,
    "daria kasatkina": 2000,
    "elina svitolina": 1990,
    "mirra andreeva": 1990,
    "madison keys": 1970,
    "jasmine paolini": 2010,
    "anastasia pavlyuchenkova": 1970,
    "victoria azarenka": 1960,
    "danielle collins": 1950,
    "anna kalinskaya": 1940,
    "elise mertens": 1940,
    "veronika kudermetova": 1930,
    "sara sorribes tormo": 1960,
    "marie bouzkova": 1940,
    "ann li": 1920,
    "clara burel": 1930,
    "oceane dodin": 1920,
    "emma raducanu": 1930,
    "magda linette": 1940,
    "zhu lin": 1920,
    "wang xinyu": 1920,
    "leylah fernandez": 1930,
    "sloane stephens": 1920,
    "petra kvitova": 1940,
    "bianca andreescu": 1930,
    "amanda anisimova": 1930,
    "camila giorgi": 1920,
    "bernarda pera": 1910,
    "irina-camelia begu": 1920,
    "eva lys": 1910,
    "leolia jeanjean": 1910,
    "alexandra eala": 1880,
    "iva jovic": 1900,
    "tereza valentova": 1870,
    "petra marcinko": 1870,
}

DEFAULT_ATP_ELO = 1850.0
DEFAULT_WTA_ELO = 1870.0

# Surface adjustments for non-clay specialists at Roland Garros
SURFACE_BOOST: dict[str, float] = {
    "rafael nadal": 80,      # King of clay
    "carlos alcaraz": 30,
    "casper ruud": 40,
    "sebastian baez": 40,
    "francisco cerundolo": 30,
    "iga swiatek": 60,
    "beatriz haddad maia": 30,
    "daria kasatkina": 20,
    "jasmine paolini": 20,
    # Hard court specialists (negative adjustment on clay)
    "taylor fritz": -30,
    "maxime cressy": -40,
    "ben shelton": -20,
    "elena rybakina": -10,
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower().strip())


def _lookup_elo(name: str, atp: bool) -> float:
    key = _normalize(name)
    table = ATP_CLAY_ELO if atp else WTA_CLAY_ELO
    default = DEFAULT_ATP_ELO if atp else DEFAULT_WTA_ELO

    if key in table:
        return table[key] + SURFACE_BOOST.get(key, 0)

    # Fuzzy: try last name
    last = key.split()[-1] if key.split() else key
    for player_key, elo in table.items():
        if last in player_key:
            return elo + SURFACE_BOOST.get(player_key, 0)

    return default


def tennis_win_probability(
    home: str,
    away: str,
    league: str = "",
) -> tuple[float, float] | None:
    """
    Retourne (p_home, p_away) via modèle Elo surface-adjusted.
    Retourne None si les deux joueurs sont inconnus (Elo par défaut des deux côtés).
    """
    is_wta = "wta" in league.lower() or "women" in league.lower()
    elo_home = _lookup_elo(home, atp=not is_wta)
    elo_away = _lookup_elo(away, atp=not is_wta)

    # Si les deux joueurs ont l'Elo par défaut → pas de signal fiable
    default = DEFAULT_WTA_ELO if is_wta else DEFAULT_ATP_ELO
    if abs(elo_home - default) < 1 and abs(elo_away - default) < 1:
        return None

    p_home = 1.0 / (1.0 + 10.0 ** ((elo_away - elo_home) / 400.0))
    return p_home, 1.0 - p_home
