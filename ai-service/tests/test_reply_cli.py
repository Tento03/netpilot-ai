import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay  # type: ignore # noqa: E402
from app.replay.scenarios import SCENARIO_NAMES  # noqa: E402


def test_usage_on_bad_input():
    assert replay.main([]) == 2
    assert replay.main(["nope"]) == 2


def test_all_scenarios_render_and_are_labeled_simulated(capsys):
    assert replay.main(["all"]) == 0
    out = capsys.readouterr().out
    for n in SCENARIO_NAMES:
        assert f"=== {n} [SIMULATED] ===" in out
    assert "Jalur tool:" in out and "Hipotesis:" in out