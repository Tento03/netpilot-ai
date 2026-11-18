from __future__ import annotations

import socket
import time

from app.config import load_settings
from app.tools.base import ToolContext, ToolFailure, ToolTimeout, execute_tool, resolve_host
from app.tools.models import ToolResult
from app.tools.validation import check_resolved_ips, validate_host, validate_port

CONNECT_TIMEOUT_S = 3.0
MAX_IPS = 3


def _attempt(ip: str, port: int) -> dict:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT_S):
            outcome = "open"
    except socket.timeout:
        outcome = "timeout"
    except ConnectionRefusedError:
        outcome = "refused"
    except OSError as e:
        outcome = f"error:{type(e).__name__}"
    return {"ip": ip, "outcome": outcome, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def check_tcp_port(host: str, port: int, ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()

    def work() -> dict:
        h = validate_host(host, ctx.allowed_private)
        p = validate_port(port, load_settings().allowed_ports)
        ips = resolve_host(h)
        check_resolved_ips(ips, ctx.allowed_private)

        attempts: list[dict] = []
        for ip in ips[:MAX_IPS]:  # always connect to a checked IP, never re-resolve the name
            attempts.append(_attempt(ip, p))
            if attempts[-1]["outcome"] == "open":
                break

        base = {"host": h, "port": p, "attempts": attempts}
        last = attempts[-1]
        if last["outcome"] == "open":
            return {**base, "ip": last["ip"], "open": True, "reason": None, "connect_ms": last["ms"]}
        refused = next((a for a in attempts if a["outcome"] == "refused"), None)
        if refused:
            return {**base, "ip": refused["ip"], "open": False, "reason": "refused",
                    "connect_ms": refused["ms"]}
        tried = ", ".join(a["ip"] for a in attempts)
        if all(a["outcome"] == "timeout" for a in attempts):
            raise ToolTimeout(f"connect to port {p} timed out on all tried IPs: {tried}")
        raise ToolFailure("connect_failed", f"could not connect to {tried}: "
                          + ", ".join(a["outcome"] for a in attempts))

    return execute_tool("check_tcp_port", {"host": host, "port": port}, work)