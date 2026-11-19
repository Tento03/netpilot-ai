"""Replay fixtures: deterministic, synthetic tool payloads for six scenarios.
Every result built from them is labeled simulated=True. Values are synthetic (not office data).
Payload keys: the tool name, except ping_host and check_tcp_port which are split into
':gateway' and ':public' (decided by whether args.host is the gateway)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.tools.models import ToolError, ToolResult, ToolStatus

GATEWAY = "10.1.1.254"
LOCAL_IP = "192.0.2.10"
SYSTEM_DNS = "198.51.100.1"
PUBLIC_PING = "8.8.8.8"
DOMAIN = "www.google.com"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

ALL_KEYS = ("get_network_info", "get_wifi_link_info", "ping_host:gateway", "ping_host:public",
            "check_dns", "check_tcp_port:gateway", "check_tcp_port:public",
            "http_timing", "measure_download")


@dataclass(frozen=True)
class Payload:
    status: ToolStatus = ToolStatus.OK
    data: dict[str, Any] | None = None
    error: tuple[str, str] | None = None
    duration_ms: int = 10


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    payloads: dict[str, Payload]


def key_for(tool: str, args: dict[str, Any], gateway: str = GATEWAY) -> str:
    if tool in ("ping_host", "check_tcp_port"):
        return f"{tool}:{'gateway' if args.get('host') == gateway else 'public'}"
    return tool


def make_result(tool: str, args: dict[str, Any], p: Payload) -> ToolResult:
    return ToolResult(tool=tool, args=args, started_at=T0, duration_ms=p.duration_ms,
                      status=p.status, data=p.data,
                      error=ToolError(code=p.error[0], message=p.error[1]) if p.error else None,
                      simulated=True)


# ---------------------------------------------------------------- data builders

def ping_data(host: str, rtts: list[float], sent: int, unreachable: int = 0) -> dict[str, Any]:
    received = len(rtts)
    lost = sent - received
    diffs = [abs(b - a) for a, b in zip(rtts, rtts[1:])]
    return {"sent": sent, "received": received, "lost": lost,
            "loss_pct": round(lost / sent * 100, 1), "reachable": received > 0,
            "min_ms": min(rtts) if rtts else None,
            "avg_ms": round(sum(rtts) / received, 1) if rtts else None,
            "max_ms": max(rtts) if rtts else None,
            "jitter_ms": round(sum(diffs) / len(diffs), 1) if diffs else None,
            "rtts_ms": rtts, "sub_ms_replies": 0, "unreachable_replies": unreachable,
            "host": host, "resolved_ips": [host]}


def network_data() -> dict[str, Any]:
    return {"hostname": "HOST-REDACTED", "local_ip": LOCAL_IP, "default_gateway": GATEWAY,
            "dns_servers": [SYSTEM_DNS], "active_interfaces": ["Wi-Fi"], "ssid": "SSID-REDACTED",
            "adapters": []}


def wifi_data(signal: int, rssi: int, rate: float) -> dict[str, Any]:
    return {"interface_name": "Wi-Fi", "state": "connected", "connected": True,
            "ssid": "SSID-REDACTED", "bssid_masked": "XX:XX:XX:XX:XX:XX", "band": "5 GHz",
            "channel": 36, "radio_type": "802.11ac", "authentication": "WPA2-Personal",
            "receive_rate_mbps": rate, "transmit_rate_mbps": rate,
            "signal_pct": signal, "rssi_dbm": rssi}


def dns_data(sys_ms: float, sys_ok: bool = True, sys_rcode: str = "NOERROR",
             pub_ms: float = 12.0) -> dict[str, Any]:
    ips = ["216.239.38.120"]
    results = [{"resolver": SYSTEM_DNS, "ok": sys_ok, "rcode": sys_rcode, "time_ms": sys_ms,
                "ips": ips if sys_ok else []},
               {"resolver": "1.1.1.1", "ok": True, "rcode": "NOERROR", "time_ms": pub_ms, "ips": ips}]
    return {"domain": DOMAIN, "results": results, "slowest_ms": max(sys_ms, pub_ms)}


def tcp_data(host: str, port: int, ms: float) -> dict[str, Any]:
    return {"host": host, "port": port,
            "attempts": [{"ip": "216.239.38.120", "outcome": "open", "ms": ms}],
            "ip": "216.239.38.120", "open": True, "reason": None, "connect_ms": ms}


def http_data(dns: float, tcp: float, tls: float, ttfb: float, total: float) -> dict[str, Any]:
    return {"host": DOMAIN, "ip": "216.239.38.120", "status_code": 200, "redirected": False,
            "dns_ms": dns, "tcp_ms": tcp, "tls_ms": tls, "tls_version": "TLSv1.3",
            "ttfb_ms": ttfb, "total_ms": total, "body_bytes": 16852, "ips_tried": 1}


def download_data(mbps: float, transfer_ms: float) -> dict[str, Any]:
    return {"host": "speed.cloudflare.com", "ip": "162.159.140.220", "status_code": 200,
            "bytes_received": 1_007_616, "measured_bytes": 1_007_566, "transfer_ms": transfer_ms,
            "throughput_mbps": mbps, "max_bytes": 1_000_000, "limit_reached": True,
            "truncated": None, "low_confidence": False, "ttfb_ms": 50.0,
            "dns_ms": 10.0, "tcp_ms": 25.0, "tls_ms": 45.0}


def _ok(data: dict[str, Any], ms: int = 10) -> Payload:
    return Payload(ToolStatus.OK, data, None, ms)


GATEWAY_PORT80_FILTERED = Payload(
    ToolStatus.TIMEOUT, None,
    ("timeout", f"connect to port 80 timed out on all tried IPs: {GATEWAY}"), 3000)

# ---------------------------------------------------------------- scenarios

_HEALTHY: dict[str, Payload] = {
    "get_network_info": _ok(network_data()),
    "get_wifi_link_info": _ok(wifi_data(88, -52, 780.0)),
    "ping_host:gateway": _ok(ping_data(GATEWAY, [2.0, 3.0, 3.0, 4.0, 3.0], 5), 4000),
    "ping_host:public": _ok(ping_data(PUBLIC_PING, [19.0, 20.0, 21.0, 20.0, 20.0], 5), 4000),
    "check_dns": _ok(dns_data(10.7, pub_ms=12.0)),
    "check_tcp_port:gateway": GATEWAY_PORT80_FILTERED,
    "check_tcp_port:public": _ok(tcp_data(DOMAIN, 443, 36.1)),
    "http_timing": _ok(http_data(6.0, 38.0, 47.0, 56.0, 170.0), 200),
    "measure_download": _ok(download_data(24.3, 331.5), 400),
}


def _variant(**overrides: Payload) -> dict[str, Payload]:
    out = dict(_HEALTHY)
    for k, v in overrides.items():
        out[k.replace("__", ":")] = v
    return out


SCENARIOS: dict[str, Scenario] = {s.name: s for s in (
    Scenario("healthy", "Semua pengukuran normal.", dict(_HEALTHY)),
    Scenario("weak_wifi", "Sinyal WiFi lemah; latensi gateway tinggi dan ada loss.", _variant(
        get_wifi_link_info=_ok(wifi_data(22, -83, 65.0)),
        ping_host__gateway=_ok(ping_data(GATEWAY, [35.0, 80.0, 42.0, 120.0, 51.0, 38.0, 95.0, 44.0, 60.0],
                                         10), 9000),
        ping_host__public=_ok(ping_data(PUBLIC_PING, [90.0, 140.0, 95.0, 180.0, 110.0, 99.0, 150.0, 105.0],
                                        10), 9000))),
    Scenario("upstream_slow", "Gateway cepat, jalur ke internet lambat.", _variant(
        ping_host__public=_ok(ping_data(PUBLIC_PING, [205.0, 240.0, 190.0, 260.0, 210.0], 5), 4000),
        http_timing=_ok(http_data(12.0, 210.0, 420.0, 1100.0, 1500.0), 1600),
        measure_download=_ok(download_data(1.8, 4400.0), 4500))),
    Scenario("dns_failure", "Resolver sistem gagal atau sangat lambat, resolver publik normal.", _variant(
        check_dns=_ok(dns_data(3000.0, sys_ok=False, sys_rcode="LIFETIMETIMEOUT", pub_ms=12.0), 3100),
        http_timing=_ok(http_data(2900.0, 38.0, 47.0, 56.0, 3100.0), 3200))),
    Scenario("packet_loss", "Packet loss di gateway dan di jalur publik.", _variant(
        ping_host__gateway=_ok(ping_data(GATEWAY, [3.0, 4.0, 3.0, 5.0, 3.0, 4.0, 3.0], 10), 9000),
        ping_host__public=_ok(ping_data(PUBLIC_PING, [22.0, 25.0, 21.0, 30.0, 24.0, 23.0], 10), 9000))),
    Scenario("host_unreachable", "Host publik tidak terjangkau; gateway normal.", _variant(
        ping_host__public=_ok(ping_data(PUBLIC_PING, [], 4, unreachable=4), 4000),
        check_tcp_port__public=Payload(ToolStatus.TIMEOUT, None,
                                       ("timeout", "connect to port 443 timed out on all tried IPs"), 3000),
        http_timing=Payload(ToolStatus.TIMEOUT, None, ("timeout", "http request timed out"), 8000),
        measure_download=Payload(ToolStatus.TIMEOUT, None, ("timeout", "download timed out"), 8000))),
)}

SCENARIO_NAMES = tuple(SCENARIOS)


def get_scenario(name: str) -> Scenario:
    return SCENARIOS[name]