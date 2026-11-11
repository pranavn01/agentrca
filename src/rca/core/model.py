"""Normalized run model — the stable core every adapter populates (design doc §4).

The engine treats Handoff.payload and Step.input/output as opaque text. Only
adapters, verifiers and replay providers may parse them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class StepKind(StrEnum):
    LLM = "llm"
    TOOL = "tool"
    CODE = "code"
    HUMAN = "human"


class StepStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class Step(BaseModel):
    stage_id: str
    index: int  # position in the run's global step sequence; adapters must keep it stable
    kind: StepKind
    input: str = ""
    output: str = ""
    status: StepStatus = StepStatus.OK


class Stage(BaseModel):
    id: str
    name: str
    run_id: str
    index: int
    attempt: int = 1
    parent_stage: str | None = None
    version_hash: str | None = None


class Handoff(BaseModel):
    from_stage: str | None  # None = the workflow's initial input
    to_stage: str | None  # None = the workflow's final output
    payload: str  # opaque to the engine
    content_type: str = "text/plain"
    mechanism: str = "message"


class VerifierKind(StrEnum):
    DETERMINISTIC = "deterministic"
    HUMAN = "human"
    LLM = "llm"


class VerifierSignal(BaseModel):
    """One opinion about one boundary. Signals are never merged (§7)."""

    boundary: str  # id of the stage whose outbound handoff is judged
    source: str
    kind: VerifierKind
    question: str
    acceptable: bool | None  # None = verifier could not answer
    suspect_step: int | None = None  # global Step.index of the first bad step, if named
    reason: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    measured_accuracy: float | None = None


class Run(BaseModel):
    id: str
    workflow: str
    outcome: RunOutcome
    started: datetime | None = None
    ended: datetime | None = None
    stages: list[Stage] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    handoffs: list[Handoff] = Field(default_factory=list)

    def ordered_stages(self) -> list[Stage]:
        return sorted(self.stages, key=lambda s: s.index)

    def steps_for(self, stage_id: str) -> list[Step]:
        return [s for s in self.steps if s.stage_id == stage_id]

    def inbound(self, stage_id: str) -> Handoff | None:
        for handoff in self.handoffs:
            if handoff.to_stage == stage_id:
                return handoff
        return None

    def outbound(self, stage_id: str) -> Handoff | None:
        for handoff in self.handoffs:
            if handoff.from_stage == stage_id:
                return handoff
        return None


class StageContract(BaseModel):
    """Manifest-lite: one sentence per stage. Grows into the full manifest schema in M2."""

    name: str
    contract: str


class ManifestLite(BaseModel):
    workflow: str
    contracts: list[StageContract] = Field(default_factory=list)

    def contract_for(self, stage_name: str) -> str | None:
        for entry in self.contracts:
            if entry.name == stage_name:
                return entry.contract
        return None
