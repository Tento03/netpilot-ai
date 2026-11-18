import pytest

from app.tools.validation import (
    ValidationFailure,
    check_resolved_ips,
    validate_count,
    validate_host,
    validate_port,
    validate_url,
)

GATEWAY = "10.17.11.254"
PORTS = {53, 80, 443, 587, 993}
HTTP_HOSTS = {"example.com", "speed.cloudflare.com"}


def code_of(fn, *args, **kwargs) -> str:
    with pytest.raises(ValidationFailure) as exc:
        fn(*args, **kwargs)
    return exc.value.code


# ---------- hosts ----------

@pytest.mark.parametrize("host,expected", [
    ("1.1.1.1", "1.1.1.1"),
    ("8.8.8.8", "8.8.8.8"),
    ("118.98.115.69", "118.98.115.69"),
    ("example.com", "example.com"),
    ("EXAMPLE.com", "example.com"),
    ("example.com.", "example.com"),
    ("tidakada.invalid", "tidakada.invalid"),
    ("xn--bcher-kva.example", "xn--bcher-kva.example"),
])
def test_valid_hosts(host, expected):
    assert validate_host(host) == expected


@pytest.mark.parametrize("host,code", [
    ("127.0.0.1", "blocked_loopback"),
    ("::1", "blocked_loopback"),
    ("::ffff:127.0.0.1", "blocked_loopback"),
    ("169.254.169.254", "blocked_link_local"),
    ("fe80::1", "blocked_link_local"),
    ("0.0.0.0", "blocked_special_range"),
    ("224.0.0.1", "blocked_special_range"),
    ("240.0.0.1", "blocked_special_range"),
    ("10.0.0.1", "blocked_private_range"),
    ("192.168.1.1", "blocked_private_range"),
    ("172.16.0.1", "blocked_private_range"),
    ("100.64.0.1", "blocked_private_range"),
    ("203.0.113.1", "blocked_private_range"),
    ("foo.localhost", "blocked_internal_name"),
    ("printer.local", "blocked_internal_name"),
    ("nas.lan", "blocked_internal_name"),
])
def test_blocked_hosts_have_specific_codes(host, code):
    assert code_of(validate_host, host) == code


@pytest.mark.parametrize("host", [
    "-n 1000 1.1.1.1", "-t", "-bad.com",
    "example.com; calc", "example.com && dir", "example.com|whoami",
    "$(whoami).com", "`id`.com", "a b.com", "exa mple.com",
    "example.com\n", "example.com\r\n1.1.1.1", " example.com", "example.com ",
    "http://example.com", "example.com/path", "user@example.com", "example.com:80",
    "", " ", "localhost", "2130706433", "0x7f.0.0.1", "127.1",
    "bad_label.com", "bad-.com", "exämple.com", "a" * 300 + ".com",
    None, 123, ["example.com"],
])
def test_injection_like_and_malformed_hosts_rejected(host):
    with pytest.raises(ValidationFailure):
        validate_host(host)


def test_gateway_is_the_only_private_exception():
    assert validate_host(GATEWAY, allowed_private=[GATEWAY]) == GATEWAY
    assert code_of(validate_host, "10.17.11.253", allowed_private=[GATEWAY]) == "blocked_private_range"
    assert code_of(validate_host, GATEWAY) == "blocked_private_range"


def test_resolved_ips_are_rechecked():
    check_resolved_ips(["1.1.1.1", "8.8.8.8"])
    with pytest.raises(ValidationFailure):
        check_resolved_ips(["1.1.1.1", "127.0.0.1"])
    with pytest.raises(ValidationFailure):
        check_resolved_ips(["192.168.1.1"])
    check_resolved_ips([GATEWAY], allowed_private=[GATEWAY])


# ---------- ports ----------

@pytest.mark.parametrize("port", [53, 80, 443, 587, 993])
def test_allowed_ports(port):
    assert validate_port(port, PORTS) == port


@pytest.mark.parametrize("port", [22, 3389, 0, 65536, -1])
def test_ports_outside_allowlist(port):
    assert code_of(validate_port, port, PORTS) == "port_not_allowed"


@pytest.mark.parametrize("port", ["443", True, 443.0, None])
def test_non_integer_ports(port):
    assert code_of(validate_port, port, PORTS) == "invalid_port"


# ---------- counts ----------

@pytest.mark.parametrize("count", [1, 4, 10])
def test_valid_counts(count):
    assert validate_count(count, 10) == count


@pytest.mark.parametrize("count", [0, 11, -1, 1_000_000, "4", True, 4.0, None])
def test_invalid_counts(count):
    assert code_of(validate_count, count, 10) == "invalid_count"


# ---------- urls ----------

@pytest.mark.parametrize("url", [
    "https://example.com",
    "https://speed.cloudflare.com/__down?bytes=1000",
    "https://example.com:443/",
])
def test_valid_urls(url):
    assert validate_url(url, HTTP_HOSTS) == url


@pytest.mark.parametrize("url,code", [
    ("http://example.com", "url_scheme_not_allowed"),
    ("ftp://example.com", "url_scheme_not_allowed"),
    ("https://user:pass@example.com", "url_credentials_not_allowed"),
    ("https://example.com@evil.com", "url_credentials_not_allowed"),
    ("https://example.com:8443/", "url_port_not_allowed"),
    ("https://evil.com/", "host_not_allowed"),
    ("https://127.0.0.1/", "blocked_loopback"),
    ("https://[::1]/", "blocked_loopback"),
    ("https://169.254.169.254/latest/meta-data", "blocked_link_local"),
    ("https://10.17.11.254/", "blocked_private_range"),
    ("https://example.com/\nHost: evil.com", "invalid_url"),
    ("https:///path", "invalid_url"),
    ("https://example.com:abc/", "invalid_url"),
    ("", "invalid_url"),
    (None, "invalid_url"),
])
def test_rejected_urls(url, code):
    assert code_of(validate_url, url, HTTP_HOSTS) == code
