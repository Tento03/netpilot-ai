import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import redact_evidence as rd  # noqa: E402

NET = {"data": {"hostname": "ACME-LAPTOP-7", "ssid": "ACME-Staff", "local_ip": "10.99.1.37",
                "default_gateway": "10.99.1.254", "dns_servers": ["198.18.0.1", "198.18.0.2"]}}
WIFI = {"data": {"ssid": "ACME-Staff", "bssid_masked": "aa:bb:cc:xx:xx:xx"}}


def setup():
    return rd.collect_secrets(NET, WIFI)


def test_hostname_and_ssid_replaced_everywhere():
    names, ips, _ = setup()
    out = rd.redact({"a": "host acme-laptop-7 on ACME-Staff", "b": ["x ACME-STAFF"]}, names, ips)
    text = str(out)
    assert "ACME" not in text.upper() or "REDACTED" in text
    assert "acme-laptop-7" not in text.lower() and "acme-staff" not in text.lower()


def test_local_and_dns_masked_gateway_kept():
    names, ips, gw = setup()
    out = str(rd.redact({"ip": "10.99.1.37", "dns": ["198.18.0.1"], "gw": "10.99.1.254",
                         "txt": "from 10.99.1.37 to 10.99.1.254"}, names, ips))
    assert "10.99.1.37" not in out and "198.18.0.1" not in out
    assert "10.99.1.254" in out and gw == "10.99.1.254"


def test_mac_and_bssid_replaced():
    names, ips, _ = setup()
    out = rd.redact({"bssid_masked": "aa:bb:cc:xx:xx:xx", "m": "mac 00-1A-2B-3C-4D-5E"}, names, ips)
    assert out["bssid_masked"] == rd.MAC_PLACEHOLDER
    assert "00-1A" not in out["m"] and rd.MAC_PLACEHOLDER in out["m"]


def test_find_leaks_flags_unexpected_private_ip_and_passes_clean():
    names, ips, gw = setup()
    assert rd.find_leaks("gw 10.99.1.254 local 192.0.2.10", names, ips, gw) == []
    assert rd.find_leaks("router 192.168.1.1", names, ips, gw) == ["unexpected private IP present"]
