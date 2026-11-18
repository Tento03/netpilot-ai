"""Runtime settings read from environment variables (never hardcode secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass

PING_COUNT_HARD_CAP = 20
DOWNLOAD_BYTES_HARD_CAP = 20_000_000


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    value = default if raw is None or raw.strip() == "" else int(raw)
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _int_set(name: str, default: tuple[int, ...]) -> frozenset[int]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return frozenset(default)
    return frozenset(int(x) for x in raw.split(",") if x.strip())


def _str_set(name: str, default: tuple[str, ...]) -> frozenset[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return frozenset(default)
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    allowed_ports: frozenset[int]
    ping_max_count: int
    allowed_http_hosts: frozenset[str]
    public_resolvers: frozenset[str]
    download_max_bytes: int


def load_settings() -> Settings:
    return Settings(
        allowed_ports=_int_set("ALLOWED_PORTS", (53, 80, 443, 587, 993)),
        ping_max_count=_bounded_int("PING_MAX_COUNT", 10, 1, PING_COUNT_HARD_CAP),
        allowed_http_hosts=_str_set(
            "ALLOWED_HTTP_HOSTS",
            ("example.com", "www.google.com", "www.cloudflare.com", "speed.cloudflare.com"),
        ),
        public_resolvers=_str_set("PUBLIC_RESOLVERS", ("1.1.1.1", "8.8.8.8")),
        download_max_bytes=_bounded_int(
            "DOWNLOAD_MAX_BYTES", 5_000_000, 1, DOWNLOAD_BYTES_HARD_CAP
        ),
    )
