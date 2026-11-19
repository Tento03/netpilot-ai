"""Deterministic report validator (no LLM). Checks: evidence refs exist, every number in a
statement appears in a referenced tool result, confidence caps, safe recommendations.
On failure the caller retries with the violations, then falls back to minimal_report()."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.report.models import (Action, Confidence, DiagnosisReport, Observation)
from app.tools.models import ToolResult, ToolStatus

ABS_TOL_DECIMAL = 0.05
ABS_TOL_INT = 0.5
_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PROTO = re.compile(r"802\.11\w*|\b[25](?:\.4)?\s*GHz\b|\bTLSv?\s?1\.[0-3]\b|\bIPv[46]\b|\bHTTP/\d(?:\.\d)?\b",
                    re.IGNORECASE)
_LIST_NO = re.compile(r"(?m)^\s*\d+[.)]\s")
_PORT = re.compile(r"\b(?:port|Port|PORT)\s+\d+\b")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_FORBIDDEN_ACTION = re.compile(
    r"(otomatis|automatic|auto[- ]?(?:apply|change|configure))|"
    r"((ubah|ganti|ubahlah|reset|nonaktifkan|matikan|disable|change|modify|reconfigure|flush)\b.{0,40}"
    r"\b(router|firewall|gateway|access point|\bAP\b))", re.IGNORECASE)


@dataclass
class ValidationReport:
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _collect_numbers(o: Any, out: list[float]) -> None:
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        out.append(float(o))
    elif isinstance(o, dict):
        for v in o.values():
            _collect_numbers(v, out)
    elif isinstance(o, (list, tuple)):
        for v in o:
            _collect_numbers(v, out)


def evidence_numbers(results: list[ToolResult]) -> list[float]:
    nums: list[float] = []
    for r in results:
        _collect_numbers(r.data, nums)
        _collect_numbers(r.args, nums)
        nums.append(float(r.duration_ms))
    return nums


def claim_numbers(text: str) -> list[float]:
    t = _LIST_NO.sub(" ", text)
    for pat in (_IP, _PROTO, _PORT):
        t = pat.sub(" ", t)
    return [float(x) for x in _NUM.findall(t)]


def _decimals(text_num: str) -> int:
    return len(text_num.split(".")[1]) if "." in text_num else 0


def _supported(value: float, text: str, pool: list[float]) -> bool:
    # tolerance depends on how the number was written in the claim
    for raw in _NUM.findall(text):
        if float(raw) != value:
            continue
        tol = ABS_TOL_DECIMAL if _decimals(raw) >= 1 else ABS_TOL_INT
        return any(abs(value - p) <= tol for p in pool)
    return False


def check_numbers(text: str, pool: list[float]) -> list[float]:
    """Numbers in `text` with no match in `pool` (within rounding tolerance)."""
    bad = []
    t = _LIST_NO.sub(" ", text)
    for pat in (_IP, _PROTO, _PORT):
        t = pat.sub(" ", t)
    for raw in _NUM.findall(t):
        v = float(raw)
        tol = ABS_TOL_DECIMAL if _decimals(raw) >= 1 else ABS_TOL_INT
        if not any(abs(v - p) <= tol for p in pool):
            bad.append(v)
    return bad


def gateway_of(results: list[ToolResult]) -> str | None:
    for r in results:
        if r.tool == "get_network_info" and r.status == ToolStatus.OK and r.data:
            return r.data.get("default_gateway")
    return None


def confidence_cap(refs: list[str], by_id: dict[str, ToolResult], all_results: list[ToolResult]) -> Confidence:
    refd = [by_id[i] for i in refs if i in by_id]
    ok = [r for r in refd if r.status == ToolStatus.OK]
    if not ok:
        return Confidence.LOW
    gw = gateway_of(all_results)
    has_gateway = gw is not None and any(
        r.tool == "ping_host" and (r.data or {}).get("host") == gw for r in ok)
    if not has_gateway:
        return Confidence.LOW
    if all(r.tool == "measure_download" for r in ok):
        return Confidence.LOW
    per_tool: dict[str, int] = {}
    for r in ok:
        per_tool[r.tool] = per_tool.get(r.tool, 0) + 1
    if max(per_tool.values()) < 2:
        return Confidence.MEDIUM
    return Confidence.HIGH


def _check_refs(label: str, refs: list[str], by_id: dict, v: list[str]) -> list[ToolResult]:
    found = []
    for i in refs:
        if i in by_id:
            found.append(by_id[i])
        else:
            v.append(f"{label}: evidence_ref tidak ada di investigasi")
    return found


def validate_report(report: DiagnosisReport, evidence: list[ToolResult]) -> ValidationReport:
    v: list[str] = []
    by_id = {r.tool_call_id: r for r in evidence}
    all_pool = evidence_numbers(evidence)

    if report.simulated != any(r.simulated for r in evidence):
        v.append("simulated tidak sesuai dengan bukti")

    bad = check_numbers(report.summary, all_pool)
    if bad:
        v.append(f"summary: angka tanpa sumber di bukti: {bad}")

    for n, o in enumerate(report.observations, 1):
        found = _check_refs(f"observation {n}", o.evidence_refs, by_id, v)
        bad = check_numbers(o.statement, evidence_numbers(found))
        if bad:
            v.append(f"observation {n}: angka tanpa sumber di bukti yang dirujuk: {bad}")

    for n, h in enumerate(report.hypotheses, 1):
        found = _check_refs(f"hypothesis {n}", h.evidence_refs, by_id, v)
        if h.status.value == "confirmed" and not h.evidence_refs:
            v.append(f"hypothesis {n}: status confirmed tanpa evidence_refs")
        bad = check_numbers(h.statement, evidence_numbers(found))
        if bad:
            v.append(f"hypothesis {n}: angka tanpa sumber di bukti yang dirujuk: {bad}")
        cap = confidence_cap(h.evidence_refs, by_id, evidence)
        if _RANK[h.confidence] > _RANK[cap]:
            v.append(f"hypothesis {n}: confidence {h.confidence.value} melebihi batas {cap.value}")

    for n, c in enumerate(report.root_causes, 1):
        found = _check_refs(f"root_cause {n}", c.evidence_refs, by_id, v)
        if found and not any(r.status == ToolStatus.OK for r in found):
            v.append(f"root_cause {n}: tidak ada bukti berstatus ok")
        bad = check_numbers(c.statement, evidence_numbers(found))
        if bad:
            v.append(f"root_cause {n}: angka tanpa sumber di bukti yang dirujuk: {bad}")
        cap = confidence_cap(c.evidence_refs, by_id, evidence)
        if _RANK[c.confidence] > _RANK[cap]:
            v.append(f"root_cause {n}: confidence {c.confidence.value} melebihi batas {cap.value}")

    for n, a in enumerate(report.recommended_actions, 1):
        if not a.safe:
            v.append(f"action {n}: safe harus true")
        if _FORBIDDEN_ACTION.search(a.action):
            v.append(f"action {n}: perubahan otomatis atau perubahan router/firewall dilarang")

    return ValidationReport(v)


def minimal_report(evidence: list[ToolResult]) -> DiagnosisReport:
    """Evidence-only fallback: measured facts per tool call, no conclusions."""
    obs = []
    for r in evidence:
        if r.status == ToolStatus.OK:
            stmt = f"Tool {r.tool} berhasil dijalankan."
        else:
            stmt = f"Tool {r.tool} gagal ({r.error.code if r.error else r.status.value})."
        obs.append(Observation(statement=stmt, evidence_refs=[r.tool_call_id]))
    return DiagnosisReport(
        summary="Laporan minimal: hanya fakta terukur, tanpa kesimpulan.",
        observations=obs,
        limitations=["Tidak ada bukti terukur (investigasi tidak berjalan, mis. API tidak tersedia)."
                     if not evidence else
                     "Laporan lengkap gagal validasi; tidak ada kesimpulan yang diambil."],
        simulated=any(r.simulated for r in evidence),
    )