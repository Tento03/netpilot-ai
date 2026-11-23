"""Python AI service (Master Prompt section 9). Bind to 127.0.0.1 only:
    uvicorn app.api.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import queue
import threading
from typing import Iterator, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.events import error_event, make_event, to_sse
from app.api.security import MAX_QUESTION_LEN, token_ok
from app.replay.engine import run_scenario
from app.replay.scenarios import SCENARIO_NAMES

app = FastAPI(title="NetPilot AI service")
_DONE = object()


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LEN)
    mode: Literal["live", "replay"] = "live"
    scenario: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _run(req: InvestigateRequest, q: "queue.Queue") -> None:
    def emit(event: str, data: dict) -> None:
        q.put(make_event(event, data))

    try:
        if req.mode == "replay":
            run_scenario(req.scenario, on_event=emit)
        else:
            from app.agent.graph import run_investigation
            from app.agent.gemini_client import make_generate
            state, _ = run_investigation(req.question, make_generate(), on_event=emit)
            if state.get("stop_reason", "") and str(state["stop_reason"]).startswith("api_error"):
                q.put(error_event("api_error", "model API unavailable"))
    except Exception as e:  # never leak details; fixed message only
        q.put(error_event("internal_error", type(e).__name__))
    finally:
        q.put(_DONE)


def _stream(req: InvestigateRequest) -> Iterator[str]:
    q: "queue.Queue" = queue.Queue()
    threading.Thread(target=_run, args=(req, q), daemon=True).start()
    while True:
        item = q.get()
        if item is _DONE:
            return
        yield to_sse(item)


@app.post("/investigate")
def investigate(req: InvestigateRequest, x_internal_token: str | None = Header(default=None)):
    if not token_ok(x_internal_token):
        raise HTTPException(status_code=401, detail="unauthorized")
    if req.mode == "replay" and req.scenario not in SCENARIO_NAMES:
        raise HTTPException(status_code=422, detail="unknown scenario")
    return StreamingResponse(_stream(req), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})