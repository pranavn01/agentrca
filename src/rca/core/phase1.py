"""Phase 1 — localization (design doc §8).

Judge every stage boundary in isolation, then derive origins with the origin
rule: a stage is an origin when its input was judged acceptable and its output
was judged unacceptable. Verifier signals are never merged in the verdict; the
walking consensus below exists only to traverse the DAG.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from pydantic import BaseModel, Field

from rca.core.interfaces import Verifier
from rca.core.model import ManifestLite, Run, VerifierSignal
from rca.core.verdict import ContestedBoundary, EvidenceType, Origin, Verdict, VerdictKind


class BoundaryAssessment(BaseModel):
    stage_id: str
    stage_name: str
    signals: list[VerifierSignal] = Field(default_factory=list)

    @property
    def flagged(self) -> bool:
        """Any verifier judged the stage's output unacceptable."""
        return any(s.acceptable is False for s in self.signals)

    @property
    def contested(self) -> bool:
        votes = {s.acceptable for s in self.signals if s.acceptable is not None}
        return len(votes) > 1

    def first_flagging_signal(self) -> VerifierSignal | None:
        for signal in self.signals:
            if signal.acceptable is False:
                return signal
        return None


class Phase1Result(BaseModel):
    verdict: Verdict
    assessments: list[BoundaryAssessment] = Field(default_factory=list)


async def localize(
    run: Run,
    manifest: ManifestLite,
    verifiers: Sequence[Verifier],
) -> Phase1Result:
    stages = run.ordered_stages()
    if not stages:
        raise ValueError(f"run {run.id} has no stages")

    async def assess(stage_id: str) -> BoundaryAssessment:
        stage = next(s for s in stages if s.id == stage_id)
        contract = manifest.contract_for(stage.name) or f"Perform the role of '{stage.name}'."
        steps = run.steps_for(stage.id)
        signals = await asyncio.gather(
            *(
                v.judge(
                    contract=contract,
                    stage=stage,
                    steps=steps,
                    inbound=run.inbound(stage.id),
                    outbound=run.outbound(stage.id),
                )
                for v in verifiers
            )
        )
        return BoundaryAssessment(stage_id=stage.id, stage_name=stage.name, signals=list(signals))

    # No calibrated verifiers exist yet, so the §8 pruning rule cannot apply:
    # every boundary is judged. Order of judging does not affect derivation.
    assessments = list(await asyncio.gather(*(assess(s.id) for s in stages)))
    by_stage = {a.stage_id: a for a in assessments}

    origins: list[Origin] = []
    contested: list[ContestedBoundary] = []
    for i, stage in enumerate(stages):
        assessment = by_stage[stage.id]
        if assessment.contested:
            contested.append(
                ContestedBoundary(
                    boundary=stage.id,
                    verifiers=assessment.signals,
                    resolution="unresolved: no calibration data yet (§7 rule 4)",
                )
            )
        if not assessment.flagged:
            continue
        # The workflow's initial input is assumed acceptable; otherwise the
        # stage's input is its predecessor's output.
        input_flagged = i > 0 and by_stage[stages[i - 1].id].flagged
        if input_flagged:
            continue  # victim, not origin
        signal = assessment.first_flagging_signal()
        origins.append(
            Origin(
                stage=stage.name,
                stage_id=stage.id,
                step=signal.suspect_step if signal else None,
                cause=signal.reason if signal and signal.reason else "output judged unacceptable",
                evidence_type=EvidenceType.JUDGE_ONLY,
            )
        )

    if origins:
        kind = VerdictKind.SINGLE if len(origins) == 1 else VerdictKind.MULTIPLE
        first_origin_index = next(
            i for i, s in enumerate(stages) if s.id == origins[0].stage_id
        )
        path = [s.id for s in stages[first_origin_index:]]
        context = None
    else:
        # Nothing flagged but the run failed: report the stage where the
        # failure surfaced as the best (weak) candidate (§11, undetermined).
        kind = VerdictKind.UNDETERMINED
        last = stages[-1]
        last_steps = run.steps_for(last.id)
        origins = [
            Origin(
                stage=last.name,
                stage_id=last.id,
                step=last_steps[-1].index if last_steps else None,
                cause="no boundary was judged unacceptable; the failure surfaced here",
                evidence_type=EvidenceType.JUDGE_ONLY,
            )
        ]
        path = [last.id]
        context = "all boundaries judged acceptable despite run-level failure"

    verdict = Verdict(
        run_id=run.id,
        workflow=run.workflow,
        verdict_kind=kind,
        origins=origins,
        propagation_path=path,
        contested_boundaries=contested,
        context=context,
    )
    return Phase1Result(verdict=verdict, assessments=assessments)
