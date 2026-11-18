"""Shared HTTPS plumbing for http_timing and measure_download.

No redirects, no cookies, certificate verification on, fixed request template.
Always connects to an IP that passed check_resolved_ips.
"""
from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
import truststore

from app.config import load_settings
from app.tools.base import ToolContext, ToolFailure, ToolTimeout, resolve_host
from app.tools.validation import ValidationFailure, check_resolved_ips, validate_url

CONNECT_TIMEOUT_S = 3.0
READ_TIMEOUT_S = 5.0
MAX_IPS = 3
MAX_HEADER_BYTES = 16384
CHUNK = 16384


@dataclass
class Connection:
    sock: Any
    host: str
    ip: str
    path: str
    dns_ms: float
    tcp_ms: float
    tls_ms: float
    tls_version: str | None
    ips_tried: int


def _ms(a: float, b: float) -> float:
    return round((b - a) * 1000, 1)

def _make_context() -> ssl.SSLContext:
    """Verify against the OS trust store (as curl and browsers do), not Python's static bundle."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

def connect(url: str, ctx: ToolContext) -> Connection:
    url = validate_url(url, load_settings().allowed_http_hosts)
    parts = urlsplit(url)
    host = parts.hostname.lower()
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    if not path.isascii():
        raise ValidationFailure("invalid_url", "url path must be ASCII")

    t0 = time.perf_counter()
    ips = resolve_host(host)
    dns_ms = _ms(t0, time.perf_counter())
    check_resolved_ips(ips, ctx.allowed_private)

    raw = None
    ip = ips[0]
    tried = 0
    last = "none"
    tcp_ms = 0.0
    for ip in ips[:MAX_IPS]:
        tried += 1
        t1 = time.perf_counter()
        try:
            raw = socket.create_connection((ip, 443), timeout=CONNECT_TIMEOUT_S)
            tcp_ms = _ms(t1, time.perf_counter())
            break
        except TimeoutError:
            last = "timeout"
        except OSError as e:
            last = type(e).__name__
    if raw is None:
        if last == "timeout":
            raise ToolTimeout(f"tcp connect timed out on all tried IPs ({tried})")
        raise ToolFailure("connect_failed", f"tcp connect failed: {last}")

    t2 = time.perf_counter()
    try:
        raw.settimeout(CONNECT_TIMEOUT_S)
        tls = _make_context().wrap_socket(raw, server_hostname=host)
    except TimeoutError:
        raw.close()
        raise ToolTimeout("tls handshake timed out") from None
    except ssl.SSLCertVerificationError as e:
        raw.close()
        reason = getattr(e, "verify_message", "") or "unknown"
        raise ToolFailure("tls_verification_failed",
                          f"certificate verification failed for {ip}: {reason[:100]}") from None
    except (ssl.SSLError, OSError) as e:
        raw.close()
        raise ToolFailure("tls_error", type(e).__name__) from None
    tls_ms = _ms(t2, time.perf_counter())

    return Connection(tls, host, ip, path, dns_ms, tcp_ms, tls_ms,
                      tls.version() if hasattr(tls, "version") else None, tried)


def fetch(conn: Connection, body_limit: int, deadline_s: float) -> dict[str, Any]:
    """Send one GET, read headers and up to body_limit body bytes."""
    sock = conn.sock
    request = (
        f"GET {conn.path} HTTP/1.1\r\nHost: {conn.host}\r\n"
        "User-Agent: NetPilot/0.1\r\nAccept: */*\r\n"
        "Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
    ).encode("ascii")

    sock.settimeout(READ_TIMEOUT_S)
    started = time.perf_counter()
    try:
        sock.sendall(request)
    except TimeoutError:
        raise ToolTimeout("sending request timed out") from None
    except OSError as e:
        raise ToolFailure("send_failed", type(e).__name__) from None
    t_sent = time.perf_counter()

    buf = b""
    t_first = None
    while b"\r\n\r\n" not in buf:
        if len(buf) > MAX_HEADER_BYTES:
            raise ToolFailure("bad_response", "response headers too large")
        try:
            chunk = sock.recv(CHUNK)
        except TimeoutError:
            raise ToolTimeout("no response before read timeout") from None
        except OSError as e:
            raise ToolFailure("connection_error", type(e).__name__) from None
        if not chunk:
            raise ToolFailure("bad_response", "connection closed before response headers")
        if t_first is None:
            t_first = time.perf_counter()
        buf += chunk

    head, _, rest = buf.partition(b"\r\n\r\n")
    parts = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
        raise ToolFailure("bad_response", "invalid HTTP status line")
    status = int(parts[1])

    initial = len(rest)
    body = initial
    truncated = None
    t_end = time.perf_counter()
    while body < body_limit:
        if time.perf_counter() - started > deadline_s:
            truncated = "deadline"
            break
        try:
            chunk = sock.recv(CHUNK)
        except TimeoutError:
            truncated = "read_timeout"
            break
        except OSError:
            truncated = "connection_error"
            break
        if not chunk:
            break
        body += len(chunk)
        t_end = time.perf_counter()

    measured = body - initial
    dur = t_end - t_first
    mbps = round(measured * 8 / 1e6 / dur, 2) if measured > 0 and dur > 0 else None
    return {
        "status_code": status,
        "ttfb_ms": _ms(t_sent, t_first),
        "response_ms": _ms(t_sent, t_end),
        "body_bytes": body,
        "measured_bytes": measured,
        "transfer_ms": _ms(t_first, t_end),
        "mbps": mbps,
        "limit_reached": body >= body_limit,
        "truncated": truncated,
    }