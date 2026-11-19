import json

import pytest

from app.agent.state import Budget, HypStatus
from app.replay import scenarios as sc
from app.replay.engine import ReplayDispatcher, run_scenario
from app.report.validator import validate_report

BUDGET = Budget(max_iterations=8, max_tool_calls=12)


def tools(d):
    return {r.tool for r in d.evidence}


def sig(d):
    return tuple((r.tool, json.dumps(r.args, sort_keys=True)) for r in d.evidence)


def status(state):
    return {h.id: h.status for h in state["hypotheses"]}


@pytest.mark.parametrize("name", sc.SCENARIO_NAMES)
def test_every_scenario_stops_in_budget_with_valid_simulated_report(name):
    state, d, _ = run_scenario(name)
    assert state["iteration"] <= BUDGET.max_iterations and d.tool_calls_used <= BUDGET.max_tool_calls
    assert d.evidence and all(r.simulated for r in d.evidence)
    rep = state["report"]
    assert rep is not None and rep.simulated is True and not rep.summary.startswith("Laporan minimal")
    assert validate_report(rep, d.evidence).ok
    assert rep.root_causes == []


@pytest.mark.parametrize("name", sc.SCENARIO_NAMES)
def test_settled_hypotheses_always_cite_existing_evidence(name):
    state, d, _ = run_scenario(name)
    ids = {r.tool_call_id for r in d.evidence}
    for h in state["hypotheses"]:
        if h.status != HypStatus.OPEN:
            assert h.evidence_refs and set(h.evidence_refs) <= ids


def test_investigation_paths_differ_between_scenarios():
    paths = {n: sig(run_scenario(n)[1]) for n in sc.SCENARIO_NAMES}
    assert len(set(paths.values())) == 6


def test_healthy_skips_heavy_tests_and_rejects_everything():
    state, d, _ = run_scenario("healthy")
    assert tools(d) == {"get_network_info", "get_wifi_link_info", "ping_host", "check_dns"}
    assert set(status(state).values()) == {HypStatus.REJECTED}


def test_weak_wifi_skips_upstream_tests():
    state, d, _ = run_scenario("weak_wifi")
    assert tools(d) == {"get_network_info", "get_wifi_link_info", "ping_host"}
    assert all(r.args["host"] == sc.GATEWAY for r in d.evidence if r.tool == "ping_host")
    assert status(state)["h1"] == HypStatus.CONFIRMED


def test_upstream_slow_measures_path_and_throughput():
    state, d, _ = run_scenario("upstream_slow")
    assert {"http_timing", "measure_download"} <= tools(d) and "check_dns" not in tools(d)
    assert status(state)["h4"] == HypStatus.CONFIRMED and status(state)["h2"] == HypStatus.REJECTED


def test_dns_failure_repeats_the_slow_sample_before_confirming():
    state, d, _ = run_scenario("dns_failure")
    assert sum(r.tool == "check_dns" for r in d.evidence) == 2
    assert status(state)["h3"] == HypStatus.CONFIRMED


def test_packet_loss_repeats_gateway_ping_before_confirming():
    state, d, _ = run_scenario("packet_loss")
    gw = [r for r in d.evidence if r.tool == "ping_host" and r.args["host"] == sc.GATEWAY]
    assert len(gw) == 2 and status(state)["h2"] == HypStatus.CONFIRMED


def test_unreachable_host_uses_tcp_check_and_skips_http_and_download():
    state, d, _ = run_scenario("host_unreachable")
    assert "check_tcp_port" in tools(d) and not tools(d) & {"http_timing", "measure_download"}
    assert status(state)["h4"] == HypStatus.CONFIRMED


def test_failed_tools_are_evidence_not_crashes():
    state, d, _ = run_scenario("host_unreachable")
    assert any(r.status.value == "timeout" for r in d.evidence) and state["report"] is not None


def test_tiny_budget_stops_early_and_still_reports():
    state, d, _ = run_scenario("healthy", Budget(max_iterations=2, max_tool_calls=12))
    assert state["iteration"] == 2 and d.tool_calls_used == 2 and state["report"] is not None


def test_replay_dispatcher_keeps_validation_and_budget():
    rd = ReplayDispatcher(sc.get_scenario("healthy"), max_tool_calls=1)
    assert rd.dispatch("run_shell", {}).error.code == "unknown_tool"
    assert rd.dispatch("ping_host", {"host": "x", "count": 99}).error.code == "invalid_argument"
    ok = rd.dispatch("ping_host", {"host": "8.8.8.8", "count": 3})
    assert ok.simulated and ok.data["host"] == "8.8.8.8"
    assert rd.dispatch("ping_host", {"host": "8.8.8.8"}).error.code == "budget_exceeded"

def test_on_event_streams_ordered_events_and_report_ready():
    seen = []
    state, d, _ = run_scenario("healthy", on_event=lambda e, data: seen.append(e))
    assert seen[0] == "node_started" and seen[-1] == "report_ready"
    assert {"tool_started", "tool_finished", "hypothesis_updated"} <= set(seen)


def test_no_callback_behaves_as_before():
    state, d, _ = run_scenario("healthy")
    assert state["report"] is not None