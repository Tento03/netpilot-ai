from __future__ import annotations

from app.config import load_settings
from app.tools.base import ToolContext, ToolFailure, execute_tool
from app.tools.https_client import connect, fetch
from app.tools.models import ToolResult
from app.tools.validation import ValidationFailure

DOWNLOAD_DEADLINE_S = 15.0
LOW_CONFIDENCE_BYTES = 100_000


def measure_download(url: str, max_bytes: int = 1_000_000, ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()

    def work() -> dict:
        cap = load_settings().download_max_bytes
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= cap:
            raise ValidationFailure("invalid_max_bytes", f"max_bytes must be an integer 1..{cap}")
        conn = connect(url, ctx)
        try:
            r = fetch(conn, max_bytes, DOWNLOAD_DEADLINE_S)
        finally:
            conn.sock.close()
        if r["status_code"] != 200:
            raise ToolFailure("http_status", f"server returned {r['status_code']}")
        return {
            "host": conn.host,
            "ip": conn.ip,
            "status_code": r["status_code"],
            "bytes_received": r["body_bytes"],
            "measured_bytes": r["measured_bytes"],  # bytes after the first read; basis of mbps
            "transfer_ms": r["transfer_ms"],
            "throughput_mbps": r["mbps"],
            "max_bytes": max_bytes,
            "limit_reached": r["limit_reached"],
            "truncated": r["truncated"],  # None | deadline | read_timeout | connection_error
            "low_confidence": r["mbps"] is None or r["measured_bytes"] < LOW_CONFIDENCE_BYTES,
            "ttfb_ms": r["ttfb_ms"],
            "dns_ms": conn.dns_ms,
            "tcp_ms": conn.tcp_ms,
            "tls_ms": conn.tls_ms,
        }

    return execute_tool("measure_download", {"url": url, "max_bytes": max_bytes}, work)