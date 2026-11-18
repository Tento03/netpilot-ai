import pytest
from pydantic import ValidationError

from app.tools.models import ToolResult, ToolStatus, error_result, ok_result, utcnow

CONTRACT_FIELDS = {
    "tool_call_id", "tool", "args", "started_at", "duration_ms",
    "status", "data", "error", "simulated",
}


def test_ok_result_has_all_contract_fields():
    r = ok_result("ping_host", {"host": "1.1.1.1"}, utcnow(), 12, {"avg_ms": 19})
    dumped = r.model_dump(mode="json")
    assert set(dumped) == CONTRACT_FIELDS
    assert dumped["status"] == "ok"
    assert dumped["simulated"] is False
    assert dumped["error"] is None


def test_tool_call_ids_are_unique():
    a = ok_result("t", {}, utcnow(), 1, {})
    b = ok_result("t", {}, utcnow(), 1, {})
    assert a.tool_call_id != b.tool_call_id


def test_error_result_carries_error():
    r = error_result("ping_host", {}, utcnow(), 5, "dns_resolution_failed", "no such host")
    assert r.status == ToolStatus.ERROR
    assert r.error.code == "dns_resolution_failed"
    assert r.data is None


def test_timeout_result():
    r = error_result("ping_host", {}, utcnow(), 5000, "timeout", "too slow", status=ToolStatus.TIMEOUT)
    assert r.model_dump(mode="json")["status"] == "timeout"


def test_simulated_flag_is_preserved():
    r = ok_result("ping_host", {}, utcnow(), 1, {}, simulated=True)
    assert r.simulated is True


def test_error_status_without_error_is_rejected():
    with pytest.raises(ValidationError):
        ToolResult(tool="x", started_at=utcnow(), duration_ms=1, status=ToolStatus.ERROR)


def test_ok_status_with_error_is_rejected():
    with pytest.raises(ValidationError):
        ToolResult(
            tool="x", started_at=utcnow(), duration_ms=1, status=ToolStatus.OK,
            error={"code": "c", "message": "m"},
        )


def test_negative_duration_is_rejected():
    with pytest.raises(ValidationError):
        ok_result("x", {}, utcnow(), -1, {})
