import pytest

from app.tools.parsers import ParserError, mask_mac, parse_ipconfig, parse_netsh_wlan, parse_ping
from tests import samples as S


def test_ping_ok():
    d = parse_ping(S.PING_OK)
    assert (d["sent"], d["received"], d["lost"], d["loss_pct"]) == (3, 3, 0, 0.0)
    assert (d["min_ms"], d["avg_ms"], d["max_ms"]) == (19.0, 20.7, 23.0)
    assert d["jitter_ms"] == 2.0
    assert d["reachable"] is True


def test_ping_jitter_with_variable_latency():
    d = parse_ping(S.PING_VARIABLE)
    assert d["rtts_ms"] == [43.0, 153.0]
    assert d["jitter_ms"] == 110.0 and d["avg_ms"] == 98.0


def test_ping_total_loss_is_a_result_not_an_error():
    d = parse_ping(S.PING_ALL_LOST)
    assert (d["sent"], d["received"], d["lost"], d["loss_pct"]) == (2, 0, 2, 100.0)
    assert d["reachable"] is False
    assert d["min_ms"] is None and d["avg_ms"] is None and d["jitter_ms"] is None


def test_ping_unknown_host_raises_dns_error():
    with pytest.raises(ParserError) as e:
        parse_ping(S.PING_NOHOST)
    assert e.value.code == "dns_resolution_failed"


def test_ping_sub_millisecond():
    d = parse_ping(S.PING_SUB_MS)
    assert d["sub_ms_replies"] == 1 and d["min_ms"] == 0.5 and d["received"] == 2


def test_ping_unreachable_replies_count_as_loss():
    d = parse_ping(S.PING_UNREACHABLE)
    assert d["received"] == 0 and d["lost"] == 2 and d["loss_pct"] == 100.0
    assert d["unreachable_replies"] == 2 and d["reachable"] is False


@pytest.mark.parametrize("text", ["", "garbage\n", "   \n"])
def test_ping_garbage_raises_parse_error(text):
    with pytest.raises(ParserError) as e:
        parse_ping(text)
    assert e.value.code == "parse_error"


def test_netsh_connected():
    d = parse_netsh_wlan(S.NETSH_CONNECTED)
    assert d["connected"] is True and d["ssid"] == "OfficeWiFi"
    assert d["band"] == "5 GHz" and d["channel"] == 36 and d["radio_type"] == "802.11ac"
    assert d["signal_pct"] == 81 and d["rssi_dbm"] == -67
    assert d["receive_rate_mbps"] == 780.0 and d["transmit_rate_mbps"] == 780.0
    assert d["bssid_masked"] == "aa:bb:cc:xx:xx:xx"


def test_netsh_never_leaks_full_mac():
    assert "dd:ee" not in str(parse_netsh_wlan(S.NETSH_CONNECTED))


def test_netsh_disconnected_is_data_not_error():
    d = parse_netsh_wlan(S.NETSH_DISCONNECTED)
    assert d["connected"] is False and d["signal_pct"] is None and d["ssid"] is None


def test_netsh_service_down_raises():
    with pytest.raises(ParserError) as e:
        parse_netsh_wlan(S.NETSH_NO_SERVICE)
    assert e.value.code == "wlan_unavailable"


def test_netsh_only_first_interface_is_used():
    d = parse_netsh_wlan(S.NETSH_CONNECTED + "\n    Name : Wi-Fi 2\n    SSID : Other\n")
    assert d["ssid"] == "OfficeWiFi"


def test_netsh_ssid_control_chars_stripped():
    d = parse_netsh_wlan(S.NETSH_CONNECTED.replace("OfficeWiFi", "Evil\x07\x1bNet", 1))
    assert d["ssid"] == "EvilNet"


def test_ipconfig_active_interface_gateway_and_dns():
    d = parse_ipconfig(S.IPCONFIG)
    assert d["hostname"] == "TESTPC"
    assert d["active_interfaces"] == ["Wi-Fi"]
    assert d["default_gateway"] == "10.17.11.254"
    assert d["local_ip"] == "10.17.11.9"          # "(Preferred)" stripped
    assert d["dns_servers"] == ["118.98.115.69", "118.98.115.78"]  # continuation line


def test_ipconfig_flags_virtual_and_disconnected_adapters():
    by_name = {a["name"]: a for a in parse_ipconfig(S.IPCONFIG)["adapters"]}
    assert by_name["Ethernet 2"]["virtual"] is True
    assert by_name["Ethernet"]["virtual"] is False
    assert by_name["Wi-Fi"]["virtual"] is False
    assert not by_name["Ethernet"]["active"] and not by_name["Ethernet 2"]["media_connected"]


def test_ipconfig_masks_mac():
    d = parse_ipconfig(S.IPCONFIG)
    assert {a["mac_masked"] for a in d["adapters"]} == {
        "00:11:22:xx:xx:xx", "aa:bb:cc:xx:xx:xx"}


def test_ipconfig_without_adapters_raises():
    with pytest.raises(ParserError):
        parse_ipconfig("Windows IP Configuration\n")


@pytest.mark.parametrize("raw,expected", [
    ("94:bb:43:c9:02:59", "94:bb:43:xx:xx:xx"),
    ("94-BB-43-C9-02-59", "94:bb:43:xx:xx:xx"),
    ("garbage", "xx:xx:xx:xx:xx:xx"),
])
def test_mask_mac(raw, expected):
    assert mask_mac(raw) == expected