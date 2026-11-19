import dataclasses
import json
from types import SimpleNamespace

from google.genai import types

from app.agent import dispatcher as disp
from app.agent import graph as gr
from app.agent import tool_specs as ts
from app.agent.state import Budget, HypStatus
from app.tools.base import ToolContext, execute_tool

CTX = ToolContext(gateway="10.1.1.254", system_dns=("198.51.100.1",))
GW = "10.1.1.254"


def fake_tools(monkeypatch):
    calls = []

    def fake(host, count=4, ctx=None):
        calls.append(host)
        return execute_tool("ping_host", {"host": host}, lambda: {"host": host, "avg_ms": 3.0})

    spec = dataclasses.replace(ts.get_spec("ping_host"), func=fake)
    monkeypatch.setattr(disp, "get_spec", lambda n: spec if n == "ping_host" else None)
    return calls


def text(t):
    return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(
        role="model", parts=[types.Part(text=t)]))])


def call(host):
    return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name="ping_host", args={"host": host}))]))])


PLAN = text(json.dumps({"hypotheses": [{"statement": "Gateway bermasalah"}, {"statement": "DNS lambat"}]}))


def settle(h_id, status, ref):
    return {"id": h_id, "status": status, "evidence_refs": [ref]}


class Script:
    """Reply by kind of call: plan / act (tools) / evaluate / report. Each kind has a list of
    replies; the last one repeats. Callables get the contents so they can read evidence ids."""
    def __init__(self, plan=None, act=None, evaluate=None, report=None):
        self.q = {"plan": list(plan or []), "act": list(act or []),
                  "evaluate": list(evaluate or []), "report": list(report or [])}
        self.n = 0

    def _kind(self, config):
        if config.tools:
            return "act"
        instr = config.system_instruction or ""
        if instr.startswith("You plan"):
            return "plan"
        if instr.startswith("You update"):
            return "evaluate"
        return "report"

    def __call__(self, contents, config):
        self.n += 1
        q = self.q[self._kind(config)]
        s = q.pop(0) if len(q) > 1 else q[0]
        return s(contents) if callable(s) else s


def last_ref(contents):
    m = __import__("re").findall(r'"tool_call_id": "([0-9a-f]{32})"', contents[0].parts[0].text)
    return m[-1]


REPORT_OK = lambda c: text(json.dumps({  # noqa: E731
    "summary": "Tidak ada gangguan teramati saat ini.",
    "observations": [{"statement": "Ping gateway dijalankan.", "evidence_refs": [
        __import__("re").findall(r'"tool_call_id": "([0-9a-f]{32})"', c[0].parts[0].text)[-1]]}],
    "hypotheses": [], "root_causes": [], "recommended_actions": [], "limitations": [], "simulated": False}))


def test_full_path_confirms_with_evidence_and_ends_in_valid_report(monkeypatch):
    fake_tools(monkeypatch)
    g = Script(plan=[PLAN], act=[call(GW)],
               evaluate=[lambda c: text(json.dumps({"updates": [settle("h1", "rejected", last_ref(c)),
                                                                settle("h2", "rejected", last_ref(c))]}))],
               report=[REPORT_OK])
    state, d = gr.run_investigation("lambat?", g, dispatcher=disp.Dispatcher(ctx=CTX))
    assert [h.status for h in state["hypotheses"]] == [HypStatus.REJECTED] * 2
    assert state["iteration"] == 1 and d.tool_calls_used == 1 and state["report"] is not None
    assert all(h.evidence_refs for h in state["hypotheses"])


def test_no_tool_means_straight_to_report(monkeypatch):
    fake_tools(monkeypatch)
    g = Script(plan=[PLAN], act=[text("tidak ada tool lagi")], report=[text("{}")])
    state, d = gr.run_investigation("x", g, dispatcher=disp.Dispatcher(ctx=CTX))
    assert state["stop_reason"] == "no_more_tools" and d.tool_calls_used == 0
    assert state["report"] is not None


def test_unsupported_confirmation_is_ignored_and_budget_stops_loop(monkeypatch):
    calls = fake_tools(monkeypatch)
    g = Script(plan=[PLAN], act=[call(GW)],
               evaluate=[text(json.dumps({"updates": [{"id": "h1", "status": "confirmed",
                                                       "evidence_refs": []}]}))],
               report=[text("{}")])
    state, d = gr.run_investigation("x", g, Budget(max_iterations=2, max_tool_calls=12),
                                    dispatcher=disp.Dispatcher(ctx=CTX))
    assert all(h.status == HypStatus.OPEN for h in state["hypotheses"])
    assert state["iteration"] == 2
    assert len(calls) == 2


def test_identical_call_refused_after_two(monkeypatch):
    calls = fake_tools(monkeypatch)
    g = Script(plan=[PLAN], act=[call(GW)], evaluate=[text(json.dumps({"updates": []}))],
               report=[text("{}")])
    state, d = gr.run_investigation("x", g, Budget(max_iterations=5, max_tool_calls=12),
                                    dispatcher=disp.Dispatcher(ctx=CTX))
    assert len(calls) == 2 and state["stop_reason"] == "no_new_calls"


def test_tool_budget_stops_investigation(monkeypatch):
    fake_tools(monkeypatch)
    g = Script(plan=[PLAN], act=[call(GW), call("8.8.8.8")],
               evaluate=[text(json.dumps({"updates": []}))], report=[text("{}")])
    state, d = gr.run_investigation("x", g, Budget(max_iterations=6, max_tool_calls=1),
                                    dispatcher=disp.Dispatcher(max_tool_calls=1, ctx=CTX))
    assert d.tool_calls_used <= 1


def test_plan_failure_goes_to_report_without_crash(monkeypatch):
    fake_tools(monkeypatch)
    state, d = gr.run_investigation("x", Script(plan=[text("bukan json")], report=[text("{}")]),
                                    dispatcher=disp.Dispatcher(ctx=CTX))
    assert state["stop_reason"] == "plan_failed" and state["report"] is not None


def test_api_error_in_act_stops_cleanly(monkeypatch):
    fake_tools(monkeypatch)

    class Boom(Script):
        def __call__(self, contents, config):
            if config.tools:
                raise TimeoutError("slow")
            return super().__call__(contents, config)

    state, d = gr.run_investigation("x", Boom(plan=[PLAN], report=[text("{}")]),
                                    dispatcher=disp.Dispatcher(ctx=CTX))
    assert state["stop_reason"].startswith("api_error") and state["report"] is not None