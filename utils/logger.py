"""
Configuration Loguru centralisée.
Appeler setup_logging() une fois au démarrage.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO", log_file: str = "logs/betting_analyzer.log") -> None:
    logger.remove()

    # Console — format lisible couleur
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Fichier — format structuré, rotation 10 MB
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
    )

    logger.info(f"Logging initialisé — niveau={level}, fichier={log_file}")
