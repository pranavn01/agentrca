from rca.core.model import (
    Handoff,
    ManifestLite,
    Run,
    RunOutcome,
    Stage,
    StageContract,
    Step,
    StepKind,
)
from rca.core.verdict import EvidenceType, Origin, Verdict, VerdictKind


def make_run() -> Run:
    stages = [
        Stage(id="s0", name="alpha", run_id="r1", index=0),
        Stage(id="s1", name="beta", run_id="r1", index=1),
    ]
    steps = [
        Step(stage_id="s0", index=0, kind=StepKind.LLM, output="a"),
        Step(stage_id="s1", index=1, kind=StepKind.LLM, output="b"),
    ]
    handoffs = [
        Handoff(from_stage=None, to_stage="s0", payload="task"),
        Handoff(from_stage="s0", to_stage="s1", payload="a"),
        Handoff(from_stage="s1", to_stage=None, payload="b"),
    ]
    return Run(
        id="r1",
        workflow="w",
        outcome=RunOutcome.FAILURE,
        stages=stages,
        steps=steps,
        handoffs=handoffs,
    )


def test_topology_helpers():
    run = make_run()
    assert [s.id for s in run.ordered_stages()] == ["s0", "s1"]
    assert run.inbound("s1").payload == "a"
    assert run.outbound("s1").to_stage is None
    assert [s.index for s in run.steps_for("s0")] == [0]


def test_run_round_trips_through_json():
    run = make_run()
    assert Run.model_validate_json(run.model_dump_json()) == run


def test_origin_confidence_defaults_uncalibrated():
    verdict = Verdict(
        run_id="r1",
        workflow="w",
        verdict_kind=VerdictKind.SINGLE,
        origins=[
            Origin(
                stage="alpha",
                stage_id="s0",
                step=0,
                cause="bad output",
                evidence_type=EvidenceType.JUDGE_ONLY,
            )
        ],
        propagation_path=["s0", "s1"],
    )
    assert verdict.origins[0].confidence == "uncalibrated"


def test_manifest_lookup():
    manifest = ManifestLite(workflow="w", contracts=[StageContract(name="alpha", contract="do a")])
    assert manifest.contract_for("alpha") == "do a"
    assert manifest.contract_for("missing") is None
