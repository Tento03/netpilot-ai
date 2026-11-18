"""Manual check on the real network:  python scripts/run_tool.py ping_host 8.8.8.8 4"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.base import ToolContext  # noqa: E402
from app.tools.dns_check import check_dns  # noqa: E402
from app.tools.download import measure_download  # noqa: E402
from app.tools.http_timing import http_timing  # noqa: E402
from app.tools.network_info import get_network_info  # noqa: E402
from app.tools.ping import ping_host  # noqa: E402
from app.tools.tcp_port import check_tcp_port  # noqa: E402
from app.tools.wifi_link import get_wifi_link_info  # noqa: E402

USAGE = ("tools: get_network_info | get_wifi_link_info | ping_host <host> [count] | "
         "check_dns <domain> [resolver] | check_tcp_port <host> <port> | "
         "http_timing <url> | measure_download <url> [max_bytes]")


def main(argv: list[str]) -> int:
    if not argv:
        print(USAGE)
        return 2
    name, rest = argv[0], argv[1:]
    info = get_network_info().data or {}
    ctx = ToolContext(gateway=info.get("default_gateway"),
                      system_dns=tuple(info.get("dns_servers") or ()))
    if name == "get_network_info":
        r = get_network_info(ctx)
    elif name == "get_wifi_link_info":
        r = get_wifi_link_info(ctx)
    elif name == "ping_host" and rest:
        r = ping_host(rest[0], int(rest[1]) if len(rest) > 1 else 4, ctx)
    elif name == "check_dns" and rest:
        r = check_dns(rest[0], rest[1] if len(rest) > 1 else None, ctx)
    elif name == "check_tcp_port" and len(rest) == 2:
        r = check_tcp_port(rest[0], int(rest[1]), ctx)
    elif name == "http_timing" and rest:
        r = http_timing(rest[0], ctx)
    elif name == "measure_download" and rest:
        r = measure_download(rest[0], int(rest[1]) if len(rest) > 1 else 1_000_000, ctx)
    else:
        print(USAGE)
        return 2
    print(json.dumps(r.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))