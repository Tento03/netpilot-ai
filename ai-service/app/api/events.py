"""Event envelope for the /investigate stream (Master Prompt section 9).
Event names: node_started, tool_started, tool_finished, hypothesis_updated, report_ready, error."""
from __future__ import annotations

import json
from typing import Any

EVENT_TYPES = ("node_started", "tool_started", "tool_finished",
               "hypothesis_updated", "report_ready", "error")


def make_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    if event not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event}")
    return {"event": event, "data": data}


def to_sse(ev: dict[str, Any]) -> str:
    """Server-Sent Events frame. Data is one JSON line, so newlines in values cannot break framing."""
    return f"event: {ev['event']}\ndata: {json.dumps(ev['data'], ensure_ascii=False, default=str)}\n\n"


def error_event(code: str, message: str = "") -> dict[str, Any]:
    """Never pass LLM text or secrets in `message`; callers use fixed strings."""
    return make_event("error", {"code": code, "message": message[:200]})