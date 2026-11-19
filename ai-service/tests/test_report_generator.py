import json
from datetime import datetime, timezone
from types import SimpleNamespace

from google.genai import types

from app.report import generator as gen
from app.tools.models import ok_result

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
GW = "10.1.1.254"


def evidence():
    net = ok_result("get_network_info", {}, NOW, 5, {"default_gateway": GW})
    ping = ok_result("ping_host", {"host": GW, "count": 5}, NOW, 5,
                     {"host": GW, "avg_ms": 3.0, "loss_pct": 0.0})
    return [net, ping], ping.tool_call_id


def reply(text):
    return SimpleNamespace(candidates=[SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(text=text)]))])


def good(ref, avg="3", simulated=False):
    return json.dumps({
        "summary": "Tidak ada gangguan teramati saat ini.",
        "observations": [{"statement": f"Ping ke gateway rata-rata {avg} ms.", "evidence_refs": [ref]}],
        "hypotheses": [], "root_causes": [],
        "recommended_actions": [{"action": "Jalankan ulang pemeriksaan saat lambat",
                                 "rationale": "sampel tunggal", "safe": True}],
        "limitations": ["Hanya satu sampel."], "simulated": simulated})


class Fake:
    def __init__(self, *texts):
        self.texts, self.calls = list(texts), []

    def __call__(self, contents, config):
        self.calls.append(list(contents))
        t = self.texts.pop(0)
        if isinstance(t, Exception):
            raise t
        return reply(t)


def test_config_has_json_output_and_no_tools():
    cfg = gen.build_config()
    assert cfg.response_mime_type == "application/json" and not cfg.tools


def test_valid_report_first_try_and_simulated_taken_from_evidence():
    ev, ref = evidence()
    f = Fake(good(ref, simulated=True))
    out = gen.generate_report("lambat?", ev, f)
    assert out.attempts == 1 and not out.fell_back
    assert out.report.simulated is False


def test_invented_number_triggers_retry_with_violations():
    ev, ref = evidence()
    f = Fake(good(ref, avg="99"), good(ref))
    out = gen.generate_report("x", ev, f)
    assert out.attempts == 2 and not out.fell_back
    assert "angka tanpa sumber" in f.calls[1][-1].parts[0].text


def test_always_invalid_falls_back_to_minimal_report():
    ev, ref = evidence()
    f = Fake(*[good(ref, avg="99")] * 3)
    out = gen.generate_report("x", ev, f)
    assert out.fell_back and out.attempts == 3 and out.violations
    assert out.report.root_causes == [] and len(out.report.observations) == 2


def test_broken_json_and_api_error_do_not_crash():
    ev, ref = evidence()
    out = gen.generate_report("x", ev, Fake("bukan json", RuntimeError("boom"), good(ref)))
    assert out.attempts == 3 and not out.fell_back


def test_code_fenced_json_is_accepted():
    ev, ref = evidence()
    out = gen.generate_report("x", ev, Fake("```json\n" + good(ref) + "\n```"))
    assert not out.fell_back


def test_no_evidence_means_minimal_report_without_calling_model():
    f = Fake()
    out = gen.generate_report("x", [], f)
    assert out.fell_back and out.attempts == 0 and f.calls == []