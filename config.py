"""
Configuration centralisée via pydantic-settings.
Lit les variables depuis .env ou l'environnement système.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- APIs externes ---
    odds_api_key: str = Field(default="", description="Clé The Odds API")
    football_data_api_key: str = Field(default="", description="Clé football-data.org")

    # --- Cache ---
    cache_backend: str = Field(default="shelve", pattern="^(redis|shelve)$")
    redis_url: str = Field(default="redis://localhost:6379/0")
    cache_ttl_seconds: int = Field(default=60, ge=10)

    # --- Scraper ---
    scraper_headless: bool = Field(default=True)
    scraper_timeout_ms: int = Field(default=30_000, ge=5_000)
    scraper_delay_min: float = Field(default=2.0, ge=0.5)
    scraper_delay_max: float = Field(default=5.0, ge=1.0)
    scraper_max_retries: int = Field(default=3, ge=1, le=10)

    # --- Analyse ---
    min_ev_threshold: float = Field(default=3.0, ge=0.0)
    min_confidence_score: float = Field(default=60.0, ge=0.0, le=100.0)
    kelly_fraction: float = Field(default=0.25, gt=0.0, le=1.0)
    default_bankroll: float = Field(default=1000.0, gt=0.0)

    # --- Dashboard ---
    dashboard_host: str = Field(default="0.0.0.0")
    dashboard_port: int = Field(default=8501, ge=1024, le=65535)
    refresh_interval: int = Field(default=60, ge=10)

    # --- Logs ---
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/betting_analyzer.log")


# Instance singleton utilisée partout dans le projet
settings = Settings()
