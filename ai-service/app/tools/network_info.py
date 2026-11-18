from __future__ import annotations

from app.runner import RunnerError, run_ipconfig, run_netsh_wlan
from app.tools.base import ToolContext, ToolTimeout, execute_tool, require_stdout
from app.tools.models import ToolResult
from app.tools.parsers import ParserError, parse_ipconfig, parse_netsh_wlan


def get_network_info(ctx: ToolContext | None = None) -> ToolResult:
    def work() -> dict:
        info = parse_ipconfig(require_stdout(run_ipconfig()))
        ssid = None
        try:
            ssid = parse_netsh_wlan(require_stdout(run_netsh_wlan()))["ssid"]
        except (ParserError, RunnerError, ToolTimeout):
            pass  # no WiFi is not a failure of this tool
        return {
            "hostname": info["hostname"],
            "local_ip": info["local_ip"],
            "default_gateway": info["default_gateway"],
            "dns_servers": info["dns_servers"],
            "active_interfaces": info["active_interfaces"],
            "ssid": ssid,
            "adapters": [
                {k: a[k] for k in ("name", "description", "virtual", "active", "media_connected", "ipv4")}
                for a in info["adapters"]
            ],
        }

    return execute_tool("get_network_info", {}, work)