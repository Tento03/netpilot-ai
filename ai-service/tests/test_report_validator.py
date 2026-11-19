from datetime import datetime, timezone

from app.report import validator as vd
from app.report.models import (Action, Confidence, DiagnosisReport, HypothesisResult,
                               Observation, RootCause)
from app.tools.models import ToolResult, error_result, ok_result

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
GW = "10.1.1.254"


def mk(tool, data, args=None, simulated=False):
    return ok_result(tool, args or {}, NOW, 5, data, simulated)


def net():
    return mk("get_network_info", {"default_gateway": GW, "dns_servers": ["198.51.100.1"]})


def ping(host, avg=3.0):
    return mk("ping_host", {"host": host, "avg_ms": avg, "loss_pct": 0.0, "rtts_ms": [2.0, avg]},
              {"host": host, "count": 5})


def rep(**kw):
    return DiagnosisReport(summary=kw.pop("summary", "Ringkasan."), **kw)


def test_valid_report_passes():
    n, p = net(), ping(GW, 3.0)
    r = rep(observations=[Observation(statement="Ping ke gateway rata-rata 3 ms.",
                                      evidence_refs=[p.tool_call_id])])
    assert vd.validate_report(r, [n, p]).ok


def test_unknown_evidence_ref_rejected():
    r = rep(observations=[Observation(statement="Gateway OK.", evidence_refs=["nope"])])
    out = vd.validate_report(r, [net()])
    assert not out.ok and "tidak ada" in out.violations[0]


def test_number_not_in_cited_evidence_rejected():
    p = ping(GW, 3.0)
    r = rep(observations=[Observation(statement="Latensi gateway 99 ms.", evidence_refs=[p.tool_call_id])])
    assert not vd.validate_report(r, [net(), p]).ok


def test_number_from_uncited_tool_rejected():
    p1, p2 = ping(GW, 3.0), ping("8.8.8.8", 77.0)
    r = rep(observations=[Observation(statement="Latensi gateway 77 ms.", evidence_refs=[p1.tool_call_id])])
    assert not vd.validate_report(r, [net(), p1, p2]).ok


def test_rounding_tolerance_and_ip_and_list_number_ignored():
    p = ping(GW, 19.64)
    r = rep(observations=[Observation(
        statement="1. Ping ke 10.1.1.254 rata-rata 19.6 ms, sekitar 20 ms, 5 paket, 802.11ac 5 GHz.",
        evidence_refs=[p.tool_call_id])])
    assert vd.validate_report(r, [net(), p]).ok


def test_summary_number_must_exist_somewhere():
    p = ping(GW, 3.0)
    assert vd.validate_report(rep(summary="Rata-rata 3 ms."), [net(), p]).ok
    assert not vd.validate_report(rep(summary="Rata-rata 888 ms."), [net(), p]).ok


def test_confirmed_hypothesis_needs_refs():
    r = rep(hypotheses=[HypothesisResult(statement="DNS lambat", status="confirmed")])
    assert not vd.validate_report(r, [net()]).ok


def test_confidence_capped_low_without_gateway_measurement():
    p = ping("8.8.8.8", 20.0)
    r = rep(hypotheses=[HypothesisResult(statement="Jalur upstream lambat.", status="open",
                                         evidence_refs=[p.tool_call_id], confidence="medium")])
    out = vd.validate_report(r, [net(), p])
    assert not out.ok and "melebihi batas low" in out.violations[0]


def test_single_sample_medium_ok_high_rejected_two_samples_high_ok():
    p1, p2 = ping(GW, 3.0), ping(GW, 4.0)
    ev = [net(), p1, p2]
    mid = rep(hypotheses=[HypothesisResult(statement="Gateway sehat.", status="open",
                                           evidence_refs=[p1.tool_call_id], confidence="medium")])
    high1 = rep(hypotheses=[HypothesisResult(statement="Gateway sehat.", status="open",
                                             evidence_refs=[p1.tool_call_id], confidence="high")])
    high2 = rep(hypotheses=[HypothesisResult(statement="Gateway sehat.", status="open",
                                             evidence_refs=[p1.tool_call_id, p2.tool_call_id],
                                             confidence="high")])
    assert vd.validate_report(mid, ev).ok
    assert not vd.validate_report(high1, ev).ok
    assert vd.validate_report(high2, ev).ok


def test_throughput_only_evidence_capped_low():
    p = ping(GW)
    d = mk("measure_download", {"throughput_mbps": 23.4, "low_confidence": False})
    r = rep(hypotheses=[HypothesisResult(statement="Throughput terbatas.", status="open",
                                         evidence_refs=[d.tool_call_id], confidence="medium")])
    assert not vd.validate_report(r, [net(), p, d]).ok


def test_root_cause_needs_ok_evidence():
    bad = error_result("ping_host", {}, NOW, 5, "timeout", "x")
    r = rep(root_causes=[RootCause(statement="Gateway mati.", evidence_refs=[bad.tool_call_id])])
    assert not vd.validate_report(r, [net(), bad]).ok


def test_forbidden_actions_rejected_and_safe_false_rejected():
    n = net()
    for text in ["Ubah konfigurasi router secara otomatis", "Reset firewall kantor",
                 "Auto-apply perubahan DNS"]:
        r = rep(recommended_actions=[Action(action=text, rationale="r")])
        assert not vd.validate_report(r, [n]).ok, text
    r = rep(recommended_actions=[Action(action="Ulangi pengukuran nanti", rationale="r", safe=False)])
    assert not vd.validate_report(r, [n]).ok
    ok = rep(recommended_actions=[Action(action="Jalankan ulang pemeriksaan saat lambat", rationale="r")])
    assert vd.validate_report(ok, [n]).ok


def test_simulated_flag_must_match_evidence():
    sim = mk("ping_host", {"host": GW, "avg_ms": 3.0}, simulated=True)
    assert not vd.validate_report(rep(simulated=False), [sim]).ok
    assert vd.validate_report(rep(simulated=True), [sim]).ok


def test_minimal_report_is_valid_and_evidence_only():
    bad = error_result("check_dns", {}, NOW, 5, "timeout", "x")
    ev = [net(), ping(GW), bad]
    m = vd.minimal_report(ev)
    assert vd.validate_report(m, ev).ok
    assert m.root_causes == [] and m.hypotheses == [] and len(m.observations) == 3