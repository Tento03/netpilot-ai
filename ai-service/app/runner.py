"""Single gateway for subprocess execution.

Fixed command templates, validated arguments, shell=False, mandatory timeout.
Only parsers and tools may call this module; nothing else spawns processes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass

from app.config import load_settings
from app.tools.validation import validate_count, validate_host

ALLOWED_EXECUTABLES = frozenset({"ping", "netsh", "ipconfig", "tracert"})
PING_REPLY_TIMEOUT_MS = 1000
TRACERT_MAX_HOPS_CAP = 20


class RunnerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CommandOutput:
    stdout: str
    stderr: str
    returncode: int | None
    duration_ms: float
    timed_out: bool


def _decode(data: bytes | str | None) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        return data
    # Windows console tools print in the OEM codepage, not the ANSI one.
    encoding = "oem" if sys.platform == "win32" else "utf-8"
    return data.decode(encoding, errors="replace")


def _resolve_executable(name: str) -> str:
    """Full path so the current working directory is never searched."""
    if sys.platform == "win32":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        path = os.path.join(root, "System32", f"{name}.exe")
        if os.path.isfile(path):
            return path
        raise RunnerError("executable_not_found", f"{name} not found in System32")
    found = shutil.which(name)
    if found is None:
        raise RunnerError("executable_not_found", f"{name} not found")
    return found


def _execute(argv: list[str], timeout_s: float) -> CommandOutput:
    """Low level. Only run_fixed and tests should call this."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout_s,
            shell=False, check=False, creationflags=flags,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandOutput(
            _decode(exc.stdout), _decode(exc.stderr), None,
            (time.perf_counter() - start) * 1000, True,
        )
    except FileNotFoundError:
        raise RunnerError("executable_not_found", f"{argv[0]} not found") from None
    return CommandOutput(
        _decode(proc.stdout), _decode(proc.stderr), proc.returncode,
        (time.perf_counter() - start) * 1000, False,
    )


def run_fixed(argv: list[str], timeout_s: float) -> CommandOutput:
    if not argv or argv[0] not in ALLOWED_EXECUTABLES:
        raise RunnerError("executable_blocked", f"executable {argv[:1]} is not allowlisted")
    if timeout_s <= 0:
        raise RunnerError("invalid_argument", "timeout must be positive")
    return _execute([_resolve_executable(argv[0]), *argv[1:]], timeout_s)


# ---- Command templates (arguments validated before they are placed) ----

def ping_argv(host: str, count: int, allowed_private: Iterable[str] = ()) -> list[str]:
    host = validate_host(host, allowed_private)
    count = validate_count(count, load_settings().ping_max_count)
    return ["ping", "-n", str(count), "-w", str(PING_REPLY_TIMEOUT_MS), host]


def run_ping(host: str, count: int, allowed_private: Iterable[str] = ()) -> CommandOutput:
    argv = ping_argv(host, count, allowed_private)
    timeout = int(argv[2]) * (PING_REPLY_TIMEOUT_MS / 1000 + 1) + 5
    return run_fixed(argv, timeout)


def run_netsh_wlan() -> CommandOutput:
    return run_fixed(["netsh", "wlan", "show", "interfaces"], 10)


def run_ipconfig() -> CommandOutput:
    return run_fixed(["ipconfig", "/all"], 10)


def tracert_argv(host: str, allowed_private: Iterable[str] = (), max_hops: int = 15) -> list[str]:
    host = validate_host(host, allowed_private)
    if isinstance(max_hops, bool) or not isinstance(max_hops, int) \
            or not 1 <= max_hops <= TRACERT_MAX_HOPS_CAP:
        raise RunnerError("invalid_argument", f"max_hops must be 1..{TRACERT_MAX_HOPS_CAP}")
    return ["tracert", "-d", "-h", str(max_hops), "-w", "1000", host]


def run_tracert(host: str, allowed_private: Iterable[str] = (), max_hops: int = 15) -> CommandOutput:
    argv = tracert_argv(host, allowed_private, max_hops)
    return run_fixed(argv, int(argv[3]) * 3 + 15)