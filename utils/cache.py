"""
Système de cache avec backend Redis ou shelve (fallback).
Interface identique quelle que soit l'implémentation.
"""
from __future__ import annotations

import json
import shelve
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from config import settings


class BaseCache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class RedisCache(BaseCache):
    def __init__(self, url: str, default_ttl: int = 60) -> None:
        try:
            import redis
            self._client = redis.from_url(url, decode_responses=True)
            self._client.ping()
            self.default_ttl = default_ttl
            logger.info(f"Cache Redis connecté: {url}")
        except Exception as exc:
            raise RuntimeError(f"Redis indisponible: {exc}") from exc

    def get(self, key: str) -> Optional[Any]:
        raw = self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._client.setex(key, ttl or self.default_ttl, json.dumps(value, default=str))

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:
        self._client.flushdb()


class ShelveCache(BaseCache):
    """Cache sur disque via shelve — zéro dépendance."""

    def __init__(self, path: str = ".cache/betting", default_ttl: int = 60) -> None:
        self._path = path
        self.default_ttl = default_ttl
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache shelve initialisé: {path}")

    def _entry_key(self, key: str) -> str:
        return f"__entry__{key}"

    def _meta_key(self, key: str) -> str:
        return f"__meta__{key}"

    def get(self, key: str) -> Optional[Any]:
        with shelve.open(self._path) as db:
            meta = db.get(self._meta_key(key))
            if meta and time.time() > meta.get("expires", 0):
                return None  # Expiré
            return db.get(self._entry_key(key))

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires = time.time() + (ttl or self.default_ttl)
        with shelve.open(self._path) as db:
            db[self._entry_key(key)] = value
            db[self._meta_key(key)] = {"expires": expires}

    def delete(self, key: str) -> None:
        with shelve.open(self._path) as db:
            db.pop(self._entry_key(key), None)
            db.pop(self._meta_key(key), None)

    def clear(self) -> None:
        with shelve.open(self._path) as db:
            db.clear()


def build_cache() -> BaseCache:
    """Factory — retourne Redis ou shelve selon la config."""
    if settings.cache_backend == "redis":
        try:
            return RedisCache(settings.redis_url, settings.cache_ttl_seconds)
        except RuntimeError as exc:
            logger.warning(f"Fallback shelve: {exc}")

    return ShelveCache(default_ttl=settings.cache_ttl_seconds)


# Singleton
_cache: Optional[BaseCache] = None


def get_cache() -> BaseCache:
    global _cache
    if _cache is None:
        _cache = build_cache()
    return _cache
