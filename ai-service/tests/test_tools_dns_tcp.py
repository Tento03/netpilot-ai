import socket

import pytest

from app.tools import dns_check as dc
from app.tools import tcp_port as tp
from app.tools.base import ToolContext, ToolFailure
from app.tools.dns_check import check_dns
from app.tools.tcp_port import check_tcp_port

CTX = ToolContext(gateway="10.17.11.254", system_dns=("118.98.115.69",))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("ALLOWED_PORTS", "PUBLIC_RESOLVERS"):
        monkeypatch.delenv(k, raising=False)


def fake_query(table):
    def q(domain, resolver_ip):
        return table[resolver_ip]
    return q


def ok(resolver, ms, ips=("93.184.216.34",)):
    return {"resolver": resolver, "ok": True, "rcode": "NOERROR", "time_ms": ms, "ips": list(ips)}


def test_dns_compares_system_and_public(monkeypatch):
    monkeypatch.setattr(dc, "_query", fake_query({
        "118.98.115.69": ok("118.98.115.69", 250.0),
        "1.1.1.1": ok("1.1.1.1", 20.0)}))
    r = check_dns("example.com", ctx=CTX)
    assert r.status.value == "ok"
    assert [x["resolver"] for x in r.data["results"]] == ["118.98.115.69", "1.1.1.1"]
    assert r.data["slowest_ms"] == 250.0


def test_dns_unlisted_resolver_rejected(monkeypatch):
    monkeypatch.setattr(dc, "_query", lambda *a: pytest.fail("must not query"))
    r = check_dns("example.com", resolver="9.9.9.9", ctx=CTX)
    assert r.error.code == "resolver_not_allowed"


def test_dns_internal_resolver_rejected():
    assert check_dns("example.com", resolver="127.0.0.1", ctx=CTX).error.code == "blocked_loopback"


def test_dns_all_timeout_is_timeout_status(monkeypatch):
    t = {"ok": False, "rcode": "TIMEOUT", "time_ms": 3000.0, "ips": []}
    monkeypatch.setattr(dc, "_query", lambda d, r: {**t, "resolver": r})
    assert check_dns("example.com", ctx=CTX).status.value == "timeout"


def test_dns_nxdomain_is_data_not_error(monkeypatch):
    bad = {"ok": False, "rcode": "NXDOMAIN", "time_ms": 10.0, "ips": []}
    monkeypatch.setattr(dc, "_query", lambda d, r: {**bad, "resolver": r})
    r = check_dns("tidakada.invalid", ctx=CTX)
    assert r.status.value == "ok" and r.data["results"][0]["rcode"] == "NXDOMAIN"


def test_dns_answer_pointing_inside_is_blocked(monkeypatch):
    monkeypatch.setattr(dc, "_query", lambda d, r: ok(r, 5.0, ips=("127.0.0.1",)))
    assert check_dns("evil.example.com", ctx=CTX).error.code == "blocked_loopback"


def test_dns_bad_domain():
    assert check_dns("example.com; calc", ctx=CTX).status.value == "error"


class FakeSock:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_tcp_open(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34"])
    monkeypatch.setattr(tp.socket, "create_connection", lambda addr, timeout: FakeSock())
    r = check_tcp_port("example.com", 443)
    assert r.status.value == "ok" and r.data["open"] is True and r.data["ip"] == "93.184.216.34"


def test_tcp_connects_to_checked_ip_not_name(monkeypatch):
    seen = {}
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34"])
    def conn(addr, timeout):
        seen["addr"] = addr
        return FakeSock()
    monkeypatch.setattr(tp.socket, "create_connection", conn)
    check_tcp_port("example.com", 443)
    assert seen["addr"] == ("93.184.216.34", 443)


def test_tcp_refused_is_data(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34"])
    def refuse(addr, timeout): raise ConnectionRefusedError()
    monkeypatch.setattr(tp.socket, "create_connection", refuse)
    r = check_tcp_port("example.com", 80)
    assert r.status.value == "ok" and r.data["open"] is False and r.data["reason"] == "refused"


def test_tcp_timeout(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34"])
    def slow(addr, timeout): raise socket.timeout()
    monkeypatch.setattr(tp.socket, "create_connection", slow)
    assert check_tcp_port("example.com", 443).status.value == "timeout"


@pytest.mark.parametrize("port", [22, 3389, 0, "443", True])
def test_tcp_port_blocked_before_any_network(monkeypatch, port):
    monkeypatch.setattr(tp, "resolve_host", lambda h: pytest.fail("no network"))
    assert check_tcp_port("example.com", port).status.value == "error"


def test_tcp_internal_resolution_blocked(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["169.254.169.254"])
    assert check_tcp_port("evil.example.com", 443).error.code == "blocked_link_local"


def test_tcp_gateway_needs_context(monkeypatch):
    monkeypatch.setattr(tp.socket, "create_connection", lambda addr, timeout: FakeSock())
    assert check_tcp_port("10.17.11.254", 80).error.code == "blocked_private_range"
    assert check_tcp_port("10.17.11.254", 80, ctx=CTX).status.value == "ok"

def test_tcp_falls_back_to_second_ip(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34", "93.184.216.35"])

    def conn(addr, timeout):
        if addr[0] == "93.184.216.34":
            raise socket.timeout()
        return FakeSock()

    monkeypatch.setattr(tp.socket, "create_connection", conn)
    r = check_tcp_port("example.com", 443)
    assert r.status.value == "ok" and r.data["open"] is True and r.data["ip"] == "93.184.216.35"
    assert [a["outcome"] for a in r.data["attempts"]] == ["timeout", "open"]


def test_tcp_all_ips_timeout(monkeypatch):
    monkeypatch.setattr(tp, "resolve_host", lambda h: ["93.184.216.34", "93.184.216.35"])

    def slow(addr, timeout):
        raise socket.timeout()

    monkeypatch.setattr(tp.socket, "create_connection", slow)
    r = check_tcp_port("example.com", 443)
    assert r.status.value == "timeout" and "93.184.216.35" in r.error.message