"""Investigation state for the hypothesis-driven agent (Master Prompt section 7).
Pure data and rules, no LLM and no LangGraph here, so it is easy to test.
A hypothesis can only become 'confirmed' or 'rejected' by citing evidence that exists."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from app.report.models import DiagnosisReport
from app.tools.models import ToolResult

DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_TOOL_CALLS = 12
MAX_HYPOTHESES = 6


class HypStatus(str, Enum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class Hypothesis:
    id: str
    statement: str
    status: HypStatus = HypStatus.OPEN
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Budget:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS


class InvestigationState(TypedDict, total=False):
    question: str
    hypotheses: list[Hypothesis]
    evidence: list[ToolResult]
    tool_calls_used: int
    iteration: int
    budget: Budget
    baseline: dict[str, Any] | None
    report: DiagnosisReport | None
    stop_reason: str | None
    call_log: list[tuple[str, str]]   # (tool, canonical args) of executed calls


def new_state(question: str, budget: Budget | None = None,
              baseline: dict[str, Any] | None = None) -> InvestigationState:
    return InvestigationState(
        question=question, hypotheses=[], evidence=[], tool_calls_used=0, iteration=0,
        budget=budget or Budget(), baseline=baseline, report=None, stop_reason=None,
        call_log=[])


def open_hypotheses(state: InvestigationState) -> list[Hypothesis]:
    return [h for h in state.get("hypotheses", []) if h.status == HypStatus.OPEN]


def budget_left(state: InvestigationState) -> bool:
    b = state["budget"]
    return state["iteration"] < b.max_iterations and state["tool_calls_used"] < b.max_tool_calls


def parse_hypotheses(items: Any) -> list[Hypothesis]:
    """Build the initial hypotheses from model output; ignore malformed entries, cap the count."""
    out: list[Hypothesis] = []
    if not isinstance(items, list):
        return out
    for n, it in enumerate(items[:MAX_HYPOTHESES], 1):
        stmt = it.get("statement") if isinstance(it, dict) else (it if isinstance(it, str) else None)
        if isinstance(stmt, str) and stmt.strip():
            out.append(Hypothesis(id=f"h{n}", statement=stmt.strip()[:300]))
    return out


def apply_updates(hypotheses: list[Hypothesis], updates: Any,
                  evidence_ids: set[str]) -> tuple[list[Hypothesis], list[str]]:
    """Apply model-proposed status changes. Returns (new list, rejected-update notes).
    Rules: id must exist; status must be valid; confirmed/rejected needs at least one
    evidence_ref and every ref must exist; an already settled hypothesis is never changed."""
    by_id = {h.id: Hypothesis(h.id, h.statement, h.status, list(h.evidence_refs)) for h in hypotheses}
    notes: list[str] = []
    if not isinstance(updates, list):
        return list(by_id.values()), ["updates bukan list"]
    for u in updates:
        if not isinstance(u, dict) or u.get("id") not in by_id:
            notes.append("update untuk hipotesis tak dikenal")
            continue
        h = by_id[u["id"]]
        try:
            status = HypStatus(u.get("status"))
        except ValueError:
            notes.append(f"{h.id}: status tidak valid")
            continue
        refs = u.get("evidence_refs") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            notes.append(f"{h.id}: evidence_refs tidak valid")
            continue
        if h.status != HypStatus.OPEN:
            notes.append(f"{h.id}: sudah {h.status.value}, tidak diubah")
            continue
        if status != HypStatus.OPEN:
            if not refs:
                notes.append(f"{h.id}: {status.value} tanpa evidence_refs ditolak")
                continue
            if any(r not in evidence_ids for r in refs):
                notes.append(f"{h.id}: evidence_ref tidak ada di investigasi")
                continue
        h.status = status
        h.evidence_refs = list(dict.fromkeys(h.evidence_refs + refs))
    return list(by_id.values()), notes


def canonical_call(tool: str, args: dict[str, Any]) -> tuple[str, str]:
    import json
    return tool, json.dumps(args, sort_keys=True, default=str)