import pytest

from app.config import load_settings

KEYS = ("PING_MAX_COUNT", "ALLOWED_PORTS", "ALLOWED_HTTP_HOSTS", "PUBLIC_RESOLVERS", "DOWNLOAD_MAX_BYTES")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_defaults():
    s = load_settings()
    assert s.ping_max_count == 10
    assert 443 in s.allowed_ports and 22 not in s.allowed_ports
    assert "speed.cloudflare.com" in s.allowed_http_hosts
    assert "1.1.1.1" in s.public_resolvers


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALLOWED_PORTS", "443,8443")
    monkeypatch.setenv("PING_MAX_COUNT", "5")
    monkeypatch.setenv("ALLOWED_HTTP_HOSTS", "Example.com")
    s = load_settings()
    assert s.allowed_ports == frozenset({443, 8443})
    assert s.ping_max_count == 5
    assert s.allowed_http_hosts == frozenset({"example.com"})


@pytest.mark.parametrize("name,value", [
    ("PING_MAX_COUNT", "abc"),
    ("PING_MAX_COUNT", "0"),
    ("PING_MAX_COUNT", "1000"),
    ("DOWNLOAD_MAX_BYTES", "999999999"),
])
def test_invalid_numbers_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        load_settings()
