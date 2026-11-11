"""Verdict schema — the product's interface (design doc §11). Carries no fix, ever."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rca.core.model import VerifierSignal


class EvidenceType(StrEnum):
    REPLAY_ORIGINAL_INPUT = "replay_original_input"
    REPLAY_ORACLE_INPUT = "replay_oracle_input"
    REPLAY_PERTURBED_INPUT = "replay_perturbed_input"
    REPLAY_SYNTHESIZED_INPUT = "replay_synthesized_input"
    LLM_CALL_REPLAY = "llm_call_replay"
    JUDGE_ONLY = "judge_only"


class VerdictKind(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    COMPOUND = "compound"
    UNDETERMINED = "undetermined"


class Samples(BaseModel):
    n: int
    original_ok: int | None = None
    golden_ok: int | None = None
    perturbed_ok: int | None = None


class Origin(BaseModel):
    stage: str  # stage name
    stage_id: str
    step: int | None  # global Step.index
    cause: str
    evidence_type: EvidenceType
    confidence: float | Literal["uncalibrated"] = "uncalibrated"
    samples: Samples | None = None


class ContestedBoundary(BaseModel):
    boundary: str
    verifiers: list[VerifierSignal] = Field(default_factory=list)
    resolution: str = ""


class Budget(BaseModel):
    replay_spent: int = 0
    replay_cap: int | None = None


class Verdict(BaseModel):
    run_id: str
    workflow: str
    verdict_kind: VerdictKind
    origins: list[Origin] = Field(default_factory=list)
    propagation_path: list[str] = Field(default_factory=list)  # stage ids, origin -> failure
    contested_boundaries: list[ContestedBoundary] = Field(default_factory=list)
    budget: Budget | None = None
    context: str | None = None
