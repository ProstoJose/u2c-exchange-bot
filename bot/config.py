from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int
    database_url: str
    rate_cache_ttl_seconds: int
    log_level: str


def _get_int_env(name: str, default: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        if default is None:
            raise RuntimeError(name + " is not set")
        return int(default)
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(name + " must be an integer") from e


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    admin_id = _get_int_env("ADMIN_ID")
    ttl = _get_int_env("RATE_CACHE_TTL_SECONDS", default=600)
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return Config(
        bot_token=bot_token,
        admin_id=admin_id,
        database_url=database_url,
        rate_cache_ttl_seconds=ttl,
        log_level=log_level,
    )
