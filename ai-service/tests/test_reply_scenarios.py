import json

import pytest

from app.replay import scenarios as sc
from app.tools.models import ToolStatus


@pytest.mark.parametrize("name", sc.SCENARIO_NAMES)
def test_every_scenario_covers_all_keys_and_is_labeled_simulated(name):
    s = sc.get_scenario(name)
    assert set(s.payloads) == set(sc.ALL_KEYS)
    for key, p in s.payloads.items():
        r = sc.make_result(key.split(":")[0], {}, p)   # validates as ToolResult
        assert r.simulated is True
        assert (r.error is None) == (r.status == ToolStatus.OK)


@pytest.mark.parametrize("name", sc.SCENARIO_NAMES)
def test_ping_payloads_are_internally_consistent(name):
    for key in ("ping_host:gateway", "ping_host:public"):
        d = sc.get_scenario(name).payloads[key].data
        assert d["received"] + d["lost"] == d["sent"] and len(d["rtts_ms"]) == d["received"]
        assert d["loss_pct"] == round(d["lost"] / d["sent"] * 100, 1)
        assert d["reachable"] == (d["received"] > 0)
        if d["rtts_ms"]:
            assert d["avg_ms"] == round(sum(d["rtts_ms"]) / d["received"], 1)
            assert d["min_ms"] == min(d["rtts_ms"]) and d["max_ms"] == max(d["rtts_ms"])
        else:
            assert d["avg_ms"] is None and d["jitter_ms"] is None


def test_six_scenarios_all_different():
    assert len(sc.SCENARIO_NAMES) == 6
    sigs = {n: json.dumps({k: [p.status.value, p.data] for k, p in s.payloads.items()}, sort_keys=True)
            for n, s in sc.SCENARIOS.items()}
    assert len(set(sigs.values())) == 6


def test_each_scenario_has_its_defining_signal():
    g = lambda n, k: sc.get_scenario(n).payloads[k].data  # noqa: E731
    assert g("weak_wifi", "get_wifi_link_info")["signal_pct"] < 40
    assert g("upstream_slow", "ping_host:gateway")["avg_ms"] < 10
    assert g("upstream_slow", "ping_host:public")["avg_ms"] > 150
    dns = g("dns_failure", "check_dns")["results"]
    assert dns[0]["ok"] is False and dns[1]["ok"] is True
    assert g("packet_loss", "ping_host:gateway")["loss_pct"] > 0
    assert g("host_unreachable", "ping_host:public")["reachable"] is False
    assert g("host_unreachable", "ping_host:gateway")["reachable"] is True
    assert g("healthy", "ping_host:gateway")["loss_pct"] == 0.0


def test_gateway_port80_is_a_timeout_in_every_scenario():
    for s in sc.SCENARIOS.values():
        assert s.payloads["check_tcp_port:gateway"].status == ToolStatus.TIMEOUT


def test_key_for_splits_gateway_and_public():
    assert sc.key_for("ping_host", {"host": sc.GATEWAY}) == "ping_host:gateway"
    assert sc.key_for("ping_host", {"host": "8.8.8.8"}) == "ping_host:public"
    assert sc.key_for("check_tcp_port", {"host": sc.GATEWAY, "port": 80}) == "check_tcp_port:gateway"
    assert sc.key_for("check_dns", {"domain": "x"}) == "check_dns"