import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)
H = {"X-Internal-Token": "tok"}


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "tok")


def parse(text):
    out = []
    for frame in text.strip().split("\n\n"):
        lines = frame.split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


def test_health_needs_no_token():
    assert client.get("/health").json() == {"status": "ok"}


def test_investigate_rejects_missing_or_wrong_token():
    body = {"question": "x", "mode": "replay", "scenario": "healthy"}
    assert client.post("/investigate", json=body).status_code == 401
    assert client.post("/investigate", json=body, headers={"X-Internal-Token": "no"}).status_code == 401


def test_empty_server_token_refuses_all(monkeypatch):
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    body = {"question": "x", "mode": "replay", "scenario": "healthy"}
    assert client.post("/investigate", json=body, headers=H).status_code == 401


def test_unknown_scenario_and_bad_body_rejected():
    assert client.post("/investigate", headers=H,
                       json={"question": "x", "mode": "replay", "scenario": "nope"}).status_code == 422
    assert client.post("/investigate", headers=H,
                       json={"question": "x", "mode": "replay"}).status_code == 422
    assert client.post("/investigate", headers=H, json={"question": ""}).status_code == 422
    assert client.post("/investigate", headers=H,
                       json={"question": "a" * 501, "mode": "replay", "scenario": "healthy"}).status_code == 422
    assert client.post("/investigate", headers=H,
                       json={"question": "x", "mode": "shell"}).status_code == 422


def test_replay_streams_ordered_events_ending_in_simulated_report():
    r = client.post("/investigate", headers=H,
                    json={"question": "lambat?", "mode": "replay", "scenario": "weak_wifi"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = parse(r.text)
    names = [e for e, _ in ev]
    assert names[0] == "node_started" and names[-1] == "report_ready"
    assert {"tool_started", "tool_finished", "hypothesis_updated"} <= set(names)
    assert ev[-1][1]["report"]["simulated"] is True


def test_live_mode_without_env_yields_error_event_not_crash(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    r = client.post("/investigate", headers=H, json={"question": "x", "mode": "live"})
    ev = parse(r.text)
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "internal_error"
    assert "GEMINI" not in json.dumps(ev)