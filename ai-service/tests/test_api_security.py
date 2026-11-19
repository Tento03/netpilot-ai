import pytest

from app.api import events as ev
from app.api import security as sec


def test_token_ok_requires_nonempty_match(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "s3cret")
    assert sec.token_ok("s3cret")
    assert not sec.token_ok("wrong") and not sec.token_ok("") and not sec.token_ok(None)


def test_empty_server_token_refuses_everything(monkeypatch):
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    assert not sec.token_ok("anything") and not sec.token_ok("")


def test_explicit_expected_overrides_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "env")
    assert sec.token_ok("x", expected="x") and not sec.token_ok("env", expected="x")


def test_make_event_rejects_unknown_type():
    assert ev.make_event("node_started", {"node": "plan"})["event"] == "node_started"
    with pytest.raises(ValueError):
        ev.make_event("shell_exec", {})


def test_sse_frame_is_single_data_line_even_with_newlines():
    frame = ev.to_sse(ev.make_event("tool_finished", {"note": "a\nb\r\nevent: error"}))
    assert frame.startswith("event: tool_finished\ndata: ") and frame.endswith("\n\n")
    assert frame.count("\ndata: ") == 1 and "\r" not in frame
    assert len(frame.strip().split("\n")) == 2


def test_error_event_truncates_message():
    e = ev.error_event("api_error", "x" * 1000)
    assert len(e["data"]["message"]) == 200 and e["event"] == "error"