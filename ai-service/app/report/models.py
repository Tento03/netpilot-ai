"""DiagnosisReport schema (Master Prompt section 8). Structure only; the rules that make
a report trustworthy (evidence refs exist, numbers come from tool results, confidence
caps) live in app/report/validator.py."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HypothesisStatus(str, Enum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Observation(_Strict):
    """A measured fact. Must point to the tool calls that measured it."""
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


class HypothesisResult(_Strict):
    """An interpretation, never a verdict."""
    statement: str = Field(min_length=1)
    status: HypothesisStatus
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW


class RootCause(_Strict):
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    confidence: Confidence = Confidence.LOW


class Action(_Strict):
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    safe: bool = True


class DiagnosisReport(_Strict):
    summary: str = Field(min_length=1)
    observations: list[Observation] = Field(default_factory=list)
    hypotheses: list[HypothesisResult] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(default_factory=list)
    recommended_actions: list[Action] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    simulated: bool = False