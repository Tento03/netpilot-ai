import pytest
from pydantic import ValidationError

from app.report.models import (Action, Confidence, DiagnosisReport, HypothesisResult,
                               HypothesisStatus, Observation, RootCause)


def test_minimal_report_defaults():
    r = DiagnosisReport(summary="Tidak ada gangguan teramati.")
    assert r.observations == [] and r.root_causes == [] and r.simulated is False


def test_observation_requires_at_least_one_evidence_ref():
    with pytest.raises(ValidationError):
        Observation(statement="Ping gateway 3 ms", evidence_refs=[])
    assert Observation(statement="x", evidence_refs=["abc"]).evidence_refs == ["abc"]


def test_root_cause_requires_evidence_refs():
    with pytest.raises(ValidationError):
        RootCause(statement="DNS lambat", evidence_refs=[])


def test_empty_statements_rejected():
    with pytest.raises(ValidationError):
        Observation(statement="", evidence_refs=["a"])
    with pytest.raises(ValidationError):
        DiagnosisReport(summary="")


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        DiagnosisReport(summary="x", verdict="pasti")
    with pytest.raises(ValidationError):
        Action(action="a", rationale="b", auto_apply=True)


def test_enums_validate_and_hypothesis_defaults_to_low_confidence():
    h = HypothesisResult(statement="WiFi lemah", status="open")
    assert h.status is HypothesisStatus.OPEN and h.confidence is Confidence.LOW
    with pytest.raises(ValidationError):
        HypothesisResult(statement="x", status="maybe")
    with pytest.raises(ValidationError):
        HypothesisResult(statement="x", status="open", confidence="certain")


def test_action_safe_defaults_true_and_roundtrip_json():
    r = DiagnosisReport(
        summary="s",
        observations=[Observation(statement="o", evidence_refs=["a"])],
        recommended_actions=[Action(action="Ulangi pengukuran", rationale="sampel tunggal")],
    )
    assert r.recommended_actions[0].safe is True
    assert DiagnosisReport.model_validate_json(r.model_dump_json()) == r