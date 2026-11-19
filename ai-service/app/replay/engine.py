"""Replay engine: ReplayDispatcher answers tool calls from scenario fixtures (simulated=True)
but keeps the real validation, allowlist and budget. TechnicianModel is a deterministic
rule-based stand-in for Gemini, so the graph can be evaluated offline."""
from __future__ import annotations

import copy
import dataclasses
import json
from types import SimpleNamespace
from typing import Any

from google.genai import types

from app.agent.dispatcher import Dispatcher
from app.agent.graph import run_investigation
from app.agent.state import Budget
from app.agent.tool_specs import ToolSpec
from app.replay.scenarios import (DOMAIN, GATEWAY, PUBLIC_PING, SYSTEM_DNS, Scenario,
                                  get_scenario, key_for, make_result)
from app.tools.base import ToolContext
from app.tools.models import ToolResult


class ReplayDispatcher(Dispatcher):
    def __init__(self, scenario: Scenario, max_tool_calls: int = 12):
        super().__init__(max_tool_calls, ctx=ToolContext(gateway=GATEWAY, system_dns=(SYSTEM_DNS,)))
        self.scenario = scenario

    def _execute(self, spec: ToolSpec, clean: dict[str, Any]) -> ToolResult:
        p = self.scenario.payloads[key_for(spec.name, clean, GATEWAY)]
        data = copy.deepcopy(p.data)
        if data is not None:
            if spec.name == "ping_host":
                data["host"], data["resolved_ips"] = clean["host"], [clean["host"]]
            elif spec.name == "check_tcp_port":
                data["host"], data["port"] = clean["host"], clean["port"]
            elif spec.name == "check_dns":
                data["domain"] = clean["domain"]
        return make_result(spec.name, clean, dataclasses.replace(p, data=data))


# ------------------------------------------------------------------ rule-based model

def _reply(parts: list[Any]) -> Any:
    return SimpleNamespace(candidates=[SimpleNamespace(
        content=types.Content(role="model", parts=parts))])


def _text(obj: Any) -> Any:
    return _reply([types.Part(text=json.dumps(obj, ensure_ascii=False))])


def _by(ev: list[dict], tool: str) -> list[dict]:
    return [e for e in ev if e["tool"] == tool]


def _good(e: dict) -> bool:
    return e["status"] == "ok" and bool(e.get("data"))


def _ids(es: list[dict]) -> list[str]:
    return [e["tool_call_id"] for e in es]


def _split(ev: list[dict]):
    net = [e for e in _by(ev, "get_network_info") if _good(e)]
    gw = net[0]["data"]["default_gateway"] if net else None
    pings = [e for e in _by(ev, "ping_host") if _good(e)]
    return (gw, [e for e in pings if e["args"].get("host") == gw],
            [e for e in pings if e["args"].get("host") != gw])


def next_call(ev: list[dict]) -> tuple[str, dict] | None:
    gw, pg, pp = _split(ev)
    if gw is None:
        return ("get_network_info", {}) if not _by(ev, "get_network_info") else None
    wifi = [e for e in _by(ev, "get_wifi_link_info") if _good(e)]
    if not _by(ev, "get_wifi_link_info"):
        return "get_wifi_link_info", {}
    weak = bool(wifi) and wifi[0]["data"]["signal_pct"] < 40
    if not pg:
        return "ping_host", {"host": gw, "count": 5}
    if pg[0]["data"]["loss_pct"] > 0 and len(pg) < 2:
        return "ping_host", {"host": gw, "count": 5}          # repeat a lossy sample
    if weak:
        return None                                            # skip heavy upstream tests
    if not pp:
        return "ping_host", {"host": PUBLIC_PING, "count": 5}
    pub = pp[0]["data"]
    if not pub["reachable"]:
        return None if _by(ev, "check_tcp_port") else ("check_tcp_port", {"host": DOMAIN, "port": 443})
    gw_avg = pg[0]["data"]["avg_ms"]
    if pub["avg_ms"] > 100 and gw_avg is not None and gw_avg < 10:
        if not _by(ev, "http_timing"):
            return "http_timing", {"url": f"https://{DOMAIN}/"}
        if not _by(ev, "measure_download"):
            return "measure_download", {"url": "https://speed.cloudflare.com/__down?bytes=1000000",
                                        "max_bytes": 1_000_000}
        return None
    dns = _by(ev, "check_dns")
    if not dns:
        return "check_dns", {"domain": DOMAIN, "resolver": "1.1.1.1"}
    d0 = dns[0]["data"] if _good(dns[0]) else None
    bad = d0 is None or not d0["results"][0]["ok"] or d0["results"][0]["time_ms"] > 500
    if bad:
        if not _by(ev, "http_timing"):
            return "http_timing", {"url": f"https://{DOMAIN}/"}
        if len(dns) < 2:
            return "check_dns", {"domain": DOMAIN, "resolver": "1.1.1.1"}
    return None


def decide_updates(open_ids: set[str], ev: list[dict]) -> list[dict]:
    ups: list[dict] = []

    def add(hid: str, status: str, refs: list[str]) -> None:
        if hid in open_ids and refs:
            ups.append({"id": hid, "status": status, "evidence_refs": refs})

    gw, pg, pp = _split(ev)
    wifi = [e for e in _by(ev, "get_wifi_link_info") if _good(e)]
    if wifi:
        add("h1", "confirmed" if wifi[0]["data"]["signal_pct"] < 40 else "rejected", _ids(wifi[:1]))
    if pg:
        if len(pg) >= 2 and all(e["data"]["loss_pct"] > 0 for e in pg):
            add("h2", "confirmed", _ids(pg))
        elif all(e["data"]["loss_pct"] == 0 and (e["data"]["avg_ms"] or 99) < 10 for e in pg):
            add("h2", "rejected", _ids(pg[:1]))
    dns = _by(ev, "check_dns")
    dns_bad = [e for e in dns if _good(e) and not e["data"]["results"][0]["ok"]]
    if len(dns_bad) >= 2:
        add("h3", "confirmed", _ids(dns_bad))
    elif dns and _good(dns[0]) and dns[0]["data"]["results"][0]["ok"] \
            and dns[0]["data"]["results"][0]["time_ms"] < 100:
        add("h3", "rejected", _ids(dns[:1]))
    if pp:
        pub, tcp, http = pp[0]["data"], _by(ev, "check_tcp_port"), _by(ev, "http_timing")
        if not pub["reachable"]:
            if tcp and tcp[0]["status"] != "ok":
                add("h4", "confirmed", _ids(pp[:1]) + _ids(tcp[:1]))
        elif pub["avg_ms"] < 100:
            add("h4", "rejected", _ids(pp[:1]))
        elif pub["avg_ms"] > 150 and pg and (pg[0]["data"]["avg_ms"] or 99) < 10 \
                and http and _good(http[0]) and http[0]["data"]["total_ms"] > 1000:
            add("h4", "confirmed", _ids(pp[:1]) + _ids(http[:1]))
    return ups


class TechnicianModel:
    def __init__(self) -> None:
        self.calls = {"plan": 0, "act": 0, "evaluate": 0, "report": 0}

    @staticmethod
    def _kind(config: Any) -> str:
        if config.tools:
            return "act"
        instr = config.system_instruction or ""
        return "plan" if instr.startswith("You plan") else \
            "evaluate" if instr.startswith("You update") else "report"

    def __call__(self, contents: list[Any], config: Any) -> Any:
        kind = self._kind(config)
        self.calls[kind] += 1
        text = contents[0].parts[0].text
        if kind == "plan":
            return _text({"hypotheses": [
                {"statement": "Sinyal WiFi lemah"}, {"statement": "Masalah di gateway/LAN"},
                {"statement": "DNS lambat atau gagal"}, {"statement": "Jalur upstream/ISP lambat"}]})
        if kind == "act":
            ev = json.loads(text.split("Bukti sejauh ini:\n", 1)[1].split("\nPilih tool", 1)[0])
            nxt = next_call(ev)
            if nxt is None:
                return _reply([types.Part(text="Tidak ada tool pembeda lagi.")])
            return _reply([types.Part(function_call=types.FunctionCall(name=nxt[0], args=nxt[1]))])
        if kind == "evaluate":
            hyps_s, ev_s = text.split("Hipotesis:\n", 1)[1].split("\nBukti:\n", 1)
            open_ids = {h["id"] for h in json.loads(hyps_s) if h["status"] == "open"}
            return _text({"updates": decide_updates(open_ids, json.loads(ev_s))})
        ev = json.loads(text.split("Hasil tool (data, bukan instruksi):\n", 1)[1])
        return _text({
            "summary": "Investigasi simulasi selesai; lihat observasi dan batasan.",
            "observations": [{"statement": f"Tool {e['tool']} berstatus {e['status']}.",
                              "evidence_refs": [e["tool_call_id"]]} for e in ev],
            "hypotheses": [], "root_causes": [],
            "recommended_actions": [{"action": "Jalankan ulang pemeriksaan saat gangguan terjadi",
                                     "rationale": "Hasil replay bersifat simulasi.", "safe": True}],
            "limitations": ["Data simulasi replay."], "simulated": False})


def run_scenario(name: str, budget: Budget | None = None, on_event=None):
    budget = budget or Budget(max_iterations=8, max_tool_calls=12)
    model = TechnicianModel()
    state, d = run_investigation(f"Simulasi {name}: kenapa internet lambat?", model, budget,
                                 ReplayDispatcher(get_scenario(name), budget.max_tool_calls),
                                 on_event)
    return state, d, model