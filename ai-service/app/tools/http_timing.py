from __future__ import annotations

from app.tools.base import ToolContext, execute_tool
from app.tools.https_client import connect, fetch
from app.tools.models import ToolResult

BODY_LIMIT = 16384
DEADLINE_S = 8.0


def http_timing(url: str, ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()

    def work() -> dict:
        conn = connect(url, ctx)
        try:
            r = fetch(conn, BODY_LIMIT, DEADLINE_S)
        finally:
            conn.sock.close()
        total = round(conn.dns_ms + conn.tcp_ms + conn.tls_ms + r["response_ms"], 1)
        return {
            "host": conn.host,
            "ip": conn.ip,
            "status_code": r["status_code"],
            "redirected": 300 <= r["status_code"] < 400,  # never followed
            "dns_ms": conn.dns_ms,
            "tcp_ms": conn.tcp_ms,
            "tls_ms": conn.tls_ms,
            "tls_version": conn.tls_version,
            "ttfb_ms": r["ttfb_ms"],  # request sent -> first response byte
            "total_ms": total,        # dns + tcp + tls + response (headers + up to 16 KB body)
            "body_bytes": r["body_bytes"],
            "ips_tried": conn.ips_tried,
        }

    return execute_tool("http_timing", {"url": url}, work)