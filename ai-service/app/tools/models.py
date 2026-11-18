"""Single result envelope shared by every diagnostic tool (Master Prompt section 6)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolError(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    duration_ms: int = Field(ge=0)
    status: ToolStatus
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    simulated: bool = False

    @model_validator(mode="after")
    def _status_matches_error(self) -> "ToolResult":
        if self.status == ToolStatus.OK and self.error is not None:
            raise ValueError("status 'ok' must not carry an error")
        if self.status != ToolStatus.OK and self.error is None:
            raise ValueError(f"status '{self.status.value}' requires an error")
        return self


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ok_result(
    tool: str,
    args: dict[str, Any],
    started_at: datetime,
    duration_ms: int,
    data: dict[str, Any],
    simulated: bool = False,
) -> ToolResult:
    return ToolResult(
        tool=tool,
        args=args,
        started_at=started_at,
        duration_ms=duration_ms,
        status=ToolStatus.OK,
        data=data,
        simulated=simulated,
    )


def error_result(
    tool: str,
    args: dict[str, Any],
    started_at: datetime,
    duration_ms: int,
    code: str,
    message: str,
    status: ToolStatus = ToolStatus.ERROR,
    simulated: bool = False,
) -> ToolResult:
    return ToolResult(
        tool=tool,
        args=args,
        started_at=started_at,
        duration_ms=duration_ms,
        status=status,
        error=ToolError(code=code, message=message),
        simulated=simulated,
    )
