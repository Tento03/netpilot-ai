"""Real test: python scripts/ask.py "Kenapa internet saya lambat?"
Loads .env (small parser, no extra dependency), runs the agent against the real network,
prints the tool trace and the answer, and saves raw output to evidence/_raw/ (git-ignored)."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.dispatcher import Dispatcher  # noqa: E402
from app.agent.gemini_client import make_generate, run_agent  # noqa: E402
from app.report.generator import generate_report  # noqa: E402


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str]) -> int:
    want_report = "--report" in argv
    argv = [a for a in argv if a != "--report"]
    if not argv:
        print('usage: python scripts/ask.py [--report] "<pertanyaan>"')
        return 2
    load_env(ROOT / ".env")
    try:
        generate = make_generate()
    except RuntimeError as e:
        print(e)
        return 2
    dispatcher = Dispatcher()
    run = run_agent(" ".join(argv), dispatcher, generate)
    print("== TRACE ==")
    for t in run.trace:
            print(f"  round {t['round']}: {t['tool']} -> {t['status']} ({t['tool_call_id']})"
              + (f" {t['detail']}" if t.get("detail") else ""))
    print(f"== {run.stopped_reason} | rounds={run.rounds} | tools={dispatcher.tool_calls_used} ==")
    print(run.text)
    raw = ROOT.parent / "evidence" / "_raw"
    raw.mkdir(parents=True, exist_ok=True)
    out = raw / f"ask_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({
        "question": " ".join(argv), "stopped_reason": run.stopped_reason, "answer": run.text,
        "evidence": [r.model_dump(mode="json") for r in dispatcher.evidence],
        "rejections": [r.model_dump(mode="json") for r in dispatcher.rejections],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved:", out)
    if want_report:
        gen = generate_report(" ".join(argv), dispatcher.evidence, generate)
        print(f"== REPORT == {'FALLBACK' if gen.fell_back else 'valid'} | attempts={gen.attempts}")
        print(gen.report.model_dump_json(indent=2))
        for msg in gen.violations:
            print("  violation:", msg)
        out.with_name(out.name.replace("ask_", "report_")).write_text(
            gen.report.model_dump_json(indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))