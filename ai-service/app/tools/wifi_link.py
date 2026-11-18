from __future__ import annotations

from app.runner import run_netsh_wlan
from app.tools.base import ToolContext, execute_tool, require_stdout
from app.tools.models import ToolResult
from app.tools.parsers import parse_netsh_wlan


def get_wifi_link_info(ctx: ToolContext | None = None) -> ToolResult:
    return execute_tool(
        "get_wifi_link_info", {},
        lambda: parse_netsh_wlan(require_stdout(run_netsh_wlan())),
    )