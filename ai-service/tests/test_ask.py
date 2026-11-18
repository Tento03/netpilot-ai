import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ask  # pyright: ignore[reportMissingImports] # noqa: E402


def test_load_env_parses_and_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# c\nA_KEY=one\nB_KEY="two"\n\nbad line\nC_KEY=three\n', encoding="utf-8")
    monkeypatch.delenv("A_KEY", raising=False)
    monkeypatch.delenv("B_KEY", raising=False)
    monkeypatch.setenv("C_KEY", "already")
    ask.load_env(f)
    import os
    assert os.environ["A_KEY"] == "one" and os.environ["B_KEY"] == "two"
    assert os.environ["C_KEY"] == "already"
    monkeypatch.delenv("A_KEY")
    monkeypatch.delenv("B_KEY")


def test_load_env_missing_file_is_fine(tmp_path):
    ask.load_env(tmp_path / "nope.env")


def test_main_without_question_prints_usage():
    assert ask.main([]) == 2