"""Offline demo: python scripts/replay.py <scenario|all>
Runs the hypothesis-driven graph against synthetic fixtures (simulated=True). No network, no API key."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.replay.engine import run_scenario  # noqa: E402
from app.replay.scenarios import SCENARIO_NAMES, get_scenario  # noqa: E402


def render(name: str) -> str:
    state, d, _ = run_scenario(name)
    out = [f"=== {name} [SIMULATED] ===", get_scenario(name).description, "", "Jalur tool:"]
    for i, r in enumerate(d.evidence, 1):
        out.append(f"  {i}. {r.tool} {r.args} -> {r.status.value}")
    out.append("")
    out.append("Hipotesis:")
    for h in state["hypotheses"]:
        out.append(f"  {h.id} [{h.status.value}] {h.statement} (bukti: {len(h.evidence_refs)})")
    out.append("")
    out.append(f"Iterasi: {state['iteration']} | tool: {d.tool_calls_used} | stop: {state.get('stop_reason')}")
    rep = state["report"]
    if rep:
        out += ["", f"Ringkasan: {rep.summary}", "Batasan: " + "; ".join(rep.limitations)]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    names = list(SCENARIO_NAMES) if argv == ["all"] else argv
    if not names or any(n not in SCENARIO_NAMES for n in names):
        print("usage: python scripts/replay.py <all|" + "|".join(SCENARIO_NAMES) + ">")
        return 2
    for n in names:
        print(render(n))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))