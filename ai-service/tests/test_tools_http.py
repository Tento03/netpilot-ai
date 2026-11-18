import ssl
import time

import pytest

from app.tools import download as dl
from app.tools import http_timing as ht
from app.tools import https_client as hc
from app.tools.base import ToolFailure
from app.tools.download import measure_download
from app.tools.http_timing import http_timing
from app.tools.https_client import Connection

OKHEAD = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"


class FakeSock:
    def __init__(self, chunks, delay=0.0):
        self.chunks, self.delay = list(chunks), delay
        self.sent, self.closed = b"", False

    def settimeout(self, t): pass
    def sendall(self, b): self.sent += b
    def close(self): self.closed = True

    def recv(self, n):
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        if isinstance(c, Exception):
            raise c
        if self.delay:
            time.sleep(self.delay)
        return c


def make_conn(chunks, delay=0.0):
    return Connection(FakeSock(chunks, delay), "example.com", "93.184.216.34", "/",
                      5.0, 20.0, 40.0, "TLSv1.3", 1)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("ALLOWED_HTTP_HOSTS", "DOWNLOAD_MAX_BYTES"):
        monkeypatch.delenv(k, raising=False)


def patch_conn(monkeypatch, module, conn):
    monkeypatch.setattr(module, "connect", lambda url, ctx: conn)
    return conn


# ---------------- http_timing ----------------

def test_http_timing_ok(monkeypatch):
    conn = patch_conn(monkeypatch, ht, make_conn([OKHEAD + b"hello", b" world", b""]))
    r = http_timing("https://example.com/")
    assert r.status.value == "ok" and r.simulated is False
    d = r.data
    assert d["status_code"] == 200 and d["body_bytes"] == 11 and d["redirected"] is False
    assert (d["dns_ms"], d["tcp_ms"], d["tls_ms"]) == (5.0, 20.0, 40.0)
    assert d["ttfb_ms"] >= 0 and d["total_ms"] >= 65.0
    assert conn.sock.closed is True


def test_http_timing_sends_one_fixed_request(monkeypatch):
    conn = patch_conn(monkeypatch, ht, make_conn([OKHEAD]))
    http_timing("https://example.com/")
    assert conn.sock.sent.startswith(b"GET / HTTP/1.1\r\nHost: example.com\r\n")
    assert conn.sock.sent.count(b"GET ") == 1 and b"Cookie" not in conn.sock.sent


def test_http_timing_redirect_is_reported_not_followed(monkeypatch):
    conn = patch_conn(monkeypatch, ht, make_conn(
        [b"HTTP/1.1 301 Moved\r\nLocation: http://169.254.169.254/\r\n\r\n"]))
    r = http_timing("https://example.com/")
    assert r.data["status_code"] == 301 and r.data["redirected"] is True
    assert "169.254" not in r.model_dump_json()      # Location is untrusted text, never exposed
    assert conn.sock.sent.count(b"GET ") == 1


def test_http_timing_garbage_response(monkeypatch):
    patch_conn(monkeypatch, ht, make_conn([b"NOT HTTP AT ALL\r\n\r\n"]))
    assert http_timing("https://example.com/").error.code == "bad_response"


def test_http_timing_closed_before_headers(monkeypatch):
    patch_conn(monkeypatch, ht, make_conn([]))
    assert http_timing("https://example.com/").error.code == "bad_response"


def test_http_timing_read_timeout(monkeypatch):
    patch_conn(monkeypatch, ht, make_conn([TimeoutError()]))
    assert http_timing("https://example.com/").status.value == "timeout"


@pytest.mark.parametrize("url,code", [
    ("http://example.com/", "url_scheme_not_allowed"),
    ("https://evil.com/", "host_not_allowed"),
    ("https://example.com@evil.com/", "url_credentials_not_allowed"),
    ("https://example.com:8443/", "url_port_not_allowed"),
    ("https://127.0.0.1/", "blocked_loopback"),
    ("https://example.com/caf\u00e9", "invalid_url"),
])
def test_http_timing_rejects_bad_urls_without_network(monkeypatch, url, code):
    monkeypatch.setattr(hc, "resolve_host", lambda h: pytest.fail("no network"))
    r = http_timing(url)
    assert r.status.value == "error" and r.error.code == code


def test_http_timing_internal_resolution_blocked(monkeypatch):
    monkeypatch.setattr(hc, "resolve_host", lambda h: ["127.0.0.1"])
    assert http_timing("https://example.com/").error.code == "blocked_loopback"


def test_http_timing_tcp_timeout_on_all_ips(monkeypatch):
    monkeypatch.setattr(hc, "resolve_host", lambda h: ["93.184.216.34", "93.184.216.35"])

    def slow(addr, timeout):
        raise TimeoutError()

    monkeypatch.setattr(hc.socket, "create_connection", slow)
    assert http_timing("https://example.com/").status.value == "timeout"


def test_http_timing_certificate_failure(monkeypatch):
    monkeypatch.setattr(hc, "resolve_host", lambda h: ["93.184.216.34"])
    raw = FakeSock([])
    monkeypatch.setattr(hc.socket, "create_connection", lambda addr, timeout: raw)

    class Ctx:
        def wrap_socket(self, s, server_hostname):
            raise ssl.SSLCertVerificationError("bad cert")

    monkeypatch.setattr(hc, "_make_context", lambda: Ctx())
    r = http_timing("https://example.com/")
    assert r.error.code == "tls_verification_failed" and raw.closed is True


# ---------------- measure_download ----------------

def test_download_ok_with_throughput(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn(
        [OKHEAD + b"x" * 1000, b"y" * 50_000, b"z" * 50_000], delay=0.01))
    r = measure_download("https://example.com/f", 1_000_000)
    d = r.data
    assert r.status.value == "ok"
    assert d["bytes_received"] == 101_000 and d["measured_bytes"] == 100_000
    assert d["throughput_mbps"] and d["throughput_mbps"] > 0
    assert d["limit_reached"] is False and d["truncated"] is None
    assert d["low_confidence"] is False


def test_download_stops_at_byte_limit_and_closes(monkeypatch):
    conn = patch_conn(monkeypatch, dl, make_conn([OKHEAD + b"x" * 5000, b"y" * 5000]))
    d = measure_download("https://example.com/f", 1000).data
    assert d["limit_reached"] is True
    assert conn.sock.chunks == [b"y" * 5000]          # nothing more was read
    assert conn.sock.closed is True


def test_download_small_sample_is_low_confidence(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn([OKHEAD + b"x" * 100, b"y" * 200], delay=0.005))
    assert measure_download("https://example.com/f", 10_000).data["low_confidence"] is True


def test_download_non_200_is_error(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn([b"HTTP/1.1 503 Unavailable\r\n\r\n"]))
    r = measure_download("https://example.com/f", 1000)
    assert r.status.value == "error" and r.error.code == "http_status"


@pytest.mark.parametrize("bad", [0, -1, 10**9, "5", True, None, 1.5])
def test_download_rejects_bad_max_bytes_before_connecting(monkeypatch, bad):
    monkeypatch.setattr(dl, "connect", lambda *a: pytest.fail("must not connect"))
    r = measure_download("https://example.com/f", bad)
    assert r.error.code == "invalid_max_bytes"


def test_download_deadline_returns_partial(monkeypatch):
    monkeypatch.setattr(dl, "DOWNLOAD_DEADLINE_S", 0.05)
    patch_conn(monkeypatch, dl, make_conn([OKHEAD + b"x" * 500, b"y" * 500, b"z" * 500], delay=0.06))
    d = measure_download("https://example.com/f", 1_000_000).data
    assert d["truncated"] == "deadline" and d["low_confidence"] is True


def test_download_mid_stream_timeout_returns_partial(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn([OKHEAD + b"x" * 500, TimeoutError()]))
    r = measure_download("https://example.com/f", 1_000_000)
    assert r.status.value == "ok" and r.data["truncated"] == "read_timeout"


def test_download_url_must_be_allowlisted(monkeypatch):
    monkeypatch.setattr(hc, "resolve_host", lambda h: pytest.fail("no network"))
    assert measure_download("https://evil.com/big", 1000).error.code == "host_not_allowed"

def test_download_reports_connection_phase_timings(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn(
        [OKHEAD + b"x" * 1000, b"y" * 50_000], delay=0.01))
    d = measure_download("https://example.com/f", 1_000_000).data
    assert d["dns_ms"] == 5.0
    assert d["tcp_ms"] == 20.0
    assert d["tls_ms"] == 40.0


def test_http_timing_host_is_plain_hostname(monkeypatch):
    # guard: "host" is evidence in reports, must never contain markdown or URL syntax
    patch_conn(monkeypatch, ht, make_conn([OKHEAD + b"hello", b""]))
    host = http_timing("https://example.com/").data["host"]
    assert host == "example.com"
    assert not any(c in host for c in "[]()/:")


def test_download_reports_connection_phase_timings(monkeypatch):
    patch_conn(monkeypatch, dl, make_conn(
        [OKHEAD + b"x" * 1000, b"y" * 50_000], delay=0.01))
    d = measure_download("https://example.com/f", 1_000_000).data
    assert d["dns_ms"] == 5.0
    assert d["tcp_ms"] == 20.0
    assert d["tls_ms"] == 40.0


def test_http_timing_host_is_plain_hostname(monkeypatch):
    # guard: "host" is evidence in reports, must never contain markdown or URL syntax
    patch_conn(monkeypatch, ht, make_conn([OKHEAD + b"hello", b""]))
    host = http_timing("https://example.com/").data["host"]
    assert host == "example.com"
    assert not any(c in host for c in "[]()/:")
