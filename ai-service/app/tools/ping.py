from __future__ import annotations

from app.config import load_settings
from app.runner import run_ping
from app.tools.base import ToolContext, execute_tool, require_stdout, resolve_host
from app.tools.models import ToolResult
from app.tools.parsers import parse_ping
from app.tools.validation import check_resolved_ips, validate_count, validate_host


def ping_host(host: str, count: int = 4, ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()

    def work() -> dict:
        h = validate_host(host, ctx.allowed_private)
        n = validate_count(count, load_settings().ping_max_count)
        ips = resolve_host(h)
        check_resolved_ips(ips, ctx.allowed_private)
        data = parse_ping(require_stdout(run_ping(h, n, ctx.allowed_private)))
        data["host"] = h
        data["resolved_ips"] = ips
        return data

    return execute_tool("ping_host", {"host": host, "count": count}, work)