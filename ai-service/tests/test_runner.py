import subprocess
import sys

import pytest

from app import runner
from app.runner import (
    CommandOutput, RunnerError, _execute, ping_argv, run_fixed, tracert_argv,
)
from app.tools.validation import ValidationFailure

GATEWAY = "10.17.11.254"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("PING_MAX_COUNT", raising=False)


def test_ping_argv_fixed_template():
    assert ping_argv("8.8.8.8", 3) == ["ping", "-n", "3", "-w", "1000", "8.8.8.8"]


@pytest.mark.parametrize("host", ["-t", "8.8.8.8; calc", "127.0.0.1", "$(id)", "-n 1000 1.1.1.1"])
def test_ping_argv_rejects_bad_host(host):
    with pytest.raises(ValidationFailure):
        ping_argv(host, 3)


@pytest.mark.parametrize("count", [0, 11, 500, "3", True, None])
def test_ping_argv_rejects_bad_count(count):
    with pytest.raises(ValidationFailure) as e:
        ping_argv("8.8.8.8", count)
    assert e.value.code == "invalid_count"


def test_ping_gateway_needs_allowlist_and_nothing_else_leaks():
    assert ping_argv(GATEWAY, 2, allowed_private=[GATEWAY])[-1] == GATEWAY
    with pytest.raises(ValidationFailure):
        ping_argv(GATEWAY, 2)
    with pytest.raises(ValidationFailure):  # double-NAT hop must stay blocked
        ping_argv("192.168.1.1", 2, allowed_private=[GATEWAY])


def test_tracert_argv_template_and_limits():
    assert tracert_argv("8.8.8.8") == ["tracert", "-d", "-h", "15", "-w", "1000", "8.8.8.8"]
    for bad in (0, 21, True, "5", None):
        with pytest.raises(RunnerError) as e:
            tracert_argv("8.8.8.8", max_hops=bad)
        assert e.value.code == "invalid_argument"
    with pytest.raises(ValidationFailure):
        tracert_argv("127.0.0.1")


@pytest.mark.parametrize("argv", [
    ["powershell", "-c", "dir"], ["cmd", "/c", "dir"], [], ["curl", "x"],
    [r"C:\Windows\System32\ping.exe", "8.8.8.8"],
])
def test_run_fixed_blocks_other_executables(argv):
    with pytest.raises(RunnerError) as e:
        run_fixed(argv, 5)
    assert e.value.code == "executable_blocked"


def test_run_fixed_rejects_non_positive_timeout():
    with pytest.raises(RunnerError) as e:
        run_fixed(["ping", "8.8.8.8"], 0)
    assert e.value.code == "invalid_argument"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific path resolution")
def test_run_fixed_uses_full_system32_path(monkeypatch):
    seen = {}

    def fake_execute(argv, timeout_s):
        seen["argv"] = argv
        return CommandOutput("", "", 0, 0.0, False)

    monkeypatch.setattr(runner, "_execute", fake_execute)
    run_fixed(["ping", "8.8.8.8"], 5)
    assert seen["argv"][0].lower().endswith("system32\\ping.exe")
    assert seen["argv"][1:] == ["8.8.8.8"]


def test_execute_captures_output():
    out = _execute([sys.executable, "-c", "print('halo')"], 10)
    assert out.returncode == 0 and "halo" in out.stdout and not out.timed_out


def test_execute_timeout_is_reported_not_raised():
    out = _execute([sys.executable, "-c", "import time; time.sleep(5)"], 0.5)
    assert out.timed_out and out.returncode is None
    assert out.duration_ms < 3000


def test_execute_uses_shell_false(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    _execute(["ping", "x"], 1)
    assert seen["shell"] is False and seen["timeout"] == 1


def test_missing_executable_raises_runner_error():
    with pytest.raises(RunnerError) as e:
        _execute(["netpilot-tidak-ada-xyz"], 2)
    assert e.value.code == "executable_not_found"