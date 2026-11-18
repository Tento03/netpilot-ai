import pytest

from app.runner import CommandOutput
from app.tools import network_info as ni
from app.tools import ping as pg
from app.tools import wifi_link as wl
from app.tools.base import ToolContext, ToolFailure
from app.tools.network_info import get_network_info
from app.tools.ping import ping_host
from app.tools.wifi_link import get_wifi_link_info
from tests import samples as S

GATEWAY = "10.17.11.254"


def out(text, timed_out=False):
    return CommandOutput(text, "", None if timed_out else 0, 5.0, timed_out)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("PING_MAX_COUNT", raising=False)


def test_network_info_ok(monkeypatch):
    monkeypatch.setattr(ni, "run_ipconfig", lambda: out(S.IPCONFIG))
    monkeypatch.setattr(ni, "run_netsh_wlan", lambda: out(S.NETSH_CONNECTED))
    r = get_network_info()
    assert r.status.value == "ok" and r.simulated is False
    assert r.data["default_gateway"] == GATEWAY and r.data["ssid"] == "OfficeWiFi"
    assert r.data["active_interfaces"] == ["Wi-Fi"]


def test_network_info_survives_wlan_failure(monkeypatch):
    monkeypatch.setattr(ni, "run_ipconfig", lambda: out(S.IPCONFIG))
    monkeypatch.setattr(ni, "run_netsh_wlan", lambda: out(S.NETSH_NO_SERVICE))
    r = get_network_info()
    assert r.status.value == "ok" and r.data["ssid"] is None


def test_network_info_timeout(monkeypatch):
    monkeypatch.setattr(ni, "run_ipconfig", lambda: out("", timed_out=True))
    r = get_network_info()
    assert r.status.value == "timeout" and r.error.code == "timeout"


def test_wifi_ok(monkeypatch):
    monkeypatch.setattr(wl, "run_netsh_wlan", lambda: out(S.NETSH_CONNECTED))
    r = get_wifi_link_info()
    assert r.status.value == "ok" and r.data["signal_pct"] == 81 and r.data["rssi_dbm"] == -67


def test_wifi_service_down(monkeypatch):
    monkeypatch.setattr(wl, "run_netsh_wlan", lambda: out(S.NETSH_NO_SERVICE))
    r = get_wifi_link_info()
    assert r.status.value == "error" and r.error.code == "wlan_unavailable"


def test_ping_ok(monkeypatch):
    monkeypatch.setattr(pg, "run_ping", lambda h, n, a=(): out(S.PING_OK))
    r = ping_host("8.8.8.8", 3)
    assert r.status.value == "ok" and r.data["avg_ms"] == 20.7
    assert r.data["host"] == "8.8.8.8" and r.args == {"host": "8.8.8.8", "count": 3}


def test_ping_blocked_loopback_never_runs(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("subprocess must not run")
    monkeypatch.setattr(pg, "run_ping", boom)
    r = ping_host("127.0.0.1", 2)
    assert r.status.value == "error" and r.error.code == "blocked_loopback"


def test_ping_bad_count():
    r = ping_host("8.8.8.8", 500)
    assert r.status.value == "error" and r.error.code == "invalid_count"


def test_ping_gateway_needs_context(monkeypatch):
    monkeypatch.setattr(pg, "run_ping", lambda h, n, a=(): out(S.PING_SUB_MS))
    assert ping_host(GATEWAY, 2).error.code == "blocked_private_range"
    assert ping_host(GATEWAY, 2, ctx=ToolContext(gateway=GATEWAY)).status.value == "ok"
    # double-NAT router stays blocked even with a gateway context
    assert ping_host("192.168.1.1", 2, ctx=ToolContext(gateway=GATEWAY)).status.value == "error"


def test_ping_hostname_resolving_to_internal_is_blocked(monkeypatch):
    monkeypatch.setattr(pg, "resolve_host", lambda h: ["127.0.0.1"])
    r = ping_host("evil.example.com", 2)
    assert r.status.value == "error" and r.error.code == "blocked_loopback"


def test_ping_unresolvable_host(monkeypatch):
    def fail(h):
        raise ToolFailure("dns_resolution_failed", "could not resolve")
    monkeypatch.setattr(pg, "resolve_host", fail)
    r = ping_host("tidakada.invalid", 2)
    assert r.status.value == "error" and r.error.code == "dns_resolution_failed"


def test_ping_timeout(monkeypatch):
    monkeypatch.setattr(pg, "run_ping", lambda h, n, a=(): out("", timed_out=True))
    assert ping_host("8.8.8.8", 2).status.value == "timeout"


def test_results_are_json_serialisable(monkeypatch):
    monkeypatch.setattr(pg, "run_ping", lambda h, n, a=(): out(S.PING_OK))
    assert '"tool":"ping_host"' in ping_host("8.8.8.8", 3).model_dump_json()