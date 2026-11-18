"""Shared plumbing: ToolContext, error types, execute_tool wrapper, safe DNS resolve."""
from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from app.runner import CommandOutput, RunnerError
from app.tools.models import ToolResult, ToolStatus, error_result, ok_result, utcnow
from app.tools.parsers import ParserError
from app.tools.validation import ValidationFailure


class ToolTimeout(Exception):
    pass


class ToolFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolContext:
    """System-supplied facts. The LLM can never set these."""
    gateway: str | None = None
    system_dns: tuple[str, ...] = ()

    @property
    def allowed_private(self) -> tuple[str, ...]:
        return (self.gateway,) if self.gateway else ()


def require_stdout(out: CommandOutput) -> str:
    if out.timed_out:
        raise ToolTimeout("command timed out")
    return out.stdout


def resolve_host(host: str, timeout_s: float = 5.0) -> list[str]:
    """Resolve to IPv4 addresses with a hard timeout. IP literals pass through."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        infos = pool.submit(socket.getaddrinfo, host, None, socket.AF_INET).result(timeout=timeout_s)
    except FutureTimeout:
        raise ToolTimeout("dns resolution timed out") from None
    except socket.gaierror:
        raise ToolFailure("dns_resolution_failed", f"could not resolve {host}") from None
    finally:
        pool.shutdown(wait=False)
    ips = list(dict.fromkeys(i[4][0] for i in infos))
    if not ips:
        raise ToolFailure("dns_resolution_failed", f"no addresses for {host}")
    return ips


def execute_tool(tool: str, args: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> ToolResult:
    started = utcnow()
    t0 = time.perf_counter()

    def ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    try:
        data = fn()
    except ValidationFailure as e:
        return error_result(tool, args, started, ms(), e.code, e.message)
    except (ParserError, ToolFailure, RunnerError) as e:
        return error_result(tool, args, started, ms(), e.code, e.message)
    except ToolTimeout as e:
        return error_result(tool, args, started, ms(), "timeout", str(e), status=ToolStatus.TIMEOUT)
    except Exception as e:  # a tool must never crash the agent
        return error_result(tool, args, started, ms(), "internal_error", type(e).__name__)
    return ok_result(tool, args, started, ms(), data)