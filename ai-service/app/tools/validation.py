"""Central input validation for all tools. Tools must not validate on their own."""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import urlsplit


class ValidationFailure(ValueError):
    """Raised for any rejected input. `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_LABEL = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_TLD = re.compile(r"[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{1,59}")
_BLOCKED_NAMES = frozenset({"localhost"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")


def _normalize_allowed(allowed_private: Iterable[str]) -> set[str]:
    return {str(ipaddress.ip_address(a)) for a in allowed_private}


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allowed: set[str]) -> str:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if str(ip) in allowed:
        return str(ip)
    if ip.is_loopback:
        raise ValidationFailure("blocked_loopback", f"{ip} is a loopback address")
    if ip.is_link_local:
        raise ValidationFailure("blocked_link_local", f"{ip} is a link-local address")
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        raise ValidationFailure("blocked_special_range", f"{ip} is in a special-use range")
    if not ip.is_global:
        raise ValidationFailure("blocked_private_range", f"{ip} is not a public address")
    return str(ip)


def validate_host(host: object, allowed_private: Iterable[str] = ()) -> str:
    """Return a normalized hostname/IP or raise ValidationFailure.

    `allowed_private` holds the only private IPs that may be targeted
    (the detected default gateway). No whitespace stripping on purpose.
    """
    if not isinstance(host, str) or not host or len(host) > 253:
        raise ValidationFailure("invalid_host", "host must be a non-empty string up to 253 chars")
    if host.startswith("-"):
        raise ValidationFailure("invalid_host", "host must not start with '-'")

    allowed = _normalize_allowed(allowed_private)

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return _check_ip(ip, allowed)

    name = host[:-1] if host.endswith(".") else host
    labels = name.split(".")
    if len(labels) < 2:
        raise ValidationFailure("invalid_host", "single-label hostnames are not allowed")
    if not all(_LABEL.fullmatch(label) for label in labels):
        raise ValidationFailure("invalid_host", "hostname contains invalid characters")
    if not _TLD.fullmatch(labels[-1]):
        raise ValidationFailure("invalid_host", "hostname must end in an alphabetic TLD")

    name = name.lower()
    if name in _BLOCKED_NAMES or name.endswith(_BLOCKED_SUFFIXES):
        raise ValidationFailure("blocked_internal_name", f"{name} is an internal name")
    return name


def check_resolved_ips(ips: Iterable[str], allowed_private: Iterable[str] = ()) -> None:
    """Re-check IPs a hostname resolved to (guards against DNS rebinding to internal ranges)."""
    allowed = _normalize_allowed(allowed_private)
    for raw in ips:
        _check_ip(ipaddress.ip_address(raw), allowed)


def validate_port(port: object, allowed_ports: Iterable[int]) -> int:
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValidationFailure("invalid_port", "port must be an integer")
    if port not in set(allowed_ports):
        raise ValidationFailure("port_not_allowed", f"port {port} is not in the allowlist")
    return port


def validate_count(count: object, max_count: int) -> int:
    """Reject (not clamp) out-of-range counts so the caller sees the mistake."""
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValidationFailure("invalid_count", "count must be an integer")
    if not 1 <= count <= max_count:
        raise ValidationFailure("invalid_count", f"count must be between 1 and {max_count}")
    return count


def validate_url(url: object, allowed_hosts: Iterable[str]) -> str:
    """HTTPS only, no credentials, port 443 only, host must be on the allowlist."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValidationFailure("invalid_url", "url must be a non-empty string up to 2048 chars")
    if any(c.isspace() or ord(c) < 32 for c in url):
        raise ValidationFailure("invalid_url", "url must not contain whitespace or control chars")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ValidationFailure("invalid_url", "url could not be parsed") from None
    if parts.scheme != "https":
        raise ValidationFailure("url_scheme_not_allowed", "only https is allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValidationFailure("url_credentials_not_allowed", "credentials in url are not allowed")
    if not parts.hostname:
        raise ValidationFailure("invalid_url", "url has no host")
    if port not in (None, 443):
        raise ValidationFailure("url_port_not_allowed", "only port 443 is allowed")
    host = validate_host(parts.hostname)
    if host not in {h.lower() for h in allowed_hosts}:
        raise ValidationFailure("host_not_allowed", f"{host} is not in the http allowlist")
    return url
