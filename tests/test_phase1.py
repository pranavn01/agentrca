from rca.core.model import (
    Handoff,
    ManifestLite,
    Run,
    RunOutcome,
    Stage,
    StageContract,
    Step,
    StepKind,
    VerifierKind,
    VerifierSignal,
)
from rca.core.phase1 import localize
from rca.core.verdict import VerdictKind


class ScriptedVerifier:
    """Test double: acceptability per stage id is scripted, not judged."""

    def __init__(self, script: dict[str, tuple[bool, int | None]], source: str = "scripted"):
        self.script = script
        self.source = source

    async def judge(self, *, contract, stage, steps, inbound, outbound):
        acceptable, suspect_step = self.script[stage.id]
        return VerifierSignal(
            boundary=stage.id,
            source=self.source,
            kind=VerifierKind.LLM,
            question="is the output acceptable?",
            acceptable=acceptable,
            suspect_step=suspect_step,
            reason="scripted opinion",
        )


def make_run(n_stages: int = 3) -> Run:
    stages = [Stage(id=f"s{i}", name=f"agent{i}", run_id="r1", index=i) for i in range(n_stages)]
    steps = [
        Step(stage_id=f"s{i}", index=i, kind=StepKind.LLM, output=f"out{i}")
        for i in range(n_stages)
    ]
    handoffs = [Handoff(from_stage=None, to_stage="s0", payload="task")]
    handoffs += [
        Handoff(from_stage=f"s{i}", to_stage=f"s{i + 1}", payload=f"out{i}")
        for i in range(n_stages - 1)
    ]
    handoffs.append(Handoff(from_stage=f"s{n_stages - 1}", to_stage=None, payload="final"))
    return Run(
        id="r1",
        workflow="w",
        outcome=RunOutcome.FAILURE,
        stages=stages,
        steps=steps,
        handoffs=handoffs,
    )


def make_manifest(n_stages: int = 3) -> ManifestLite:
    return ManifestLite(
        workflow="w",
        contracts=[
            StageContract(name=f"agent{i}", contract=f"do thing {i}")
            for i in range(n_stages)
        ],
    )


async def test_single_origin_with_downstream_victim():
    run, manifest = make_run(), make_manifest()
    verifier = ScriptedVerifier({"s0": (True, None), "s1": (False, 1), "s2": (False, 2)})
    result = await localize(run, manifest, [verifier])
    verdict = result.verdict
    assert verdict.verdict_kind == VerdictKind.SINGLE
    assert len(verdict.origins) == 1
    assert verdict.origins[0].stage_id == "s1"
    assert verdict.origins[0].step == 1
    assert verdict.propagation_path == ["s1", "s2"]  # s2 is a victim, not an origin


async def test_multiple_independent_origins():
    run, manifest = make_run(), make_manifest()
    verifier = ScriptedVerifier({"s0": (False, 0), "s1": (True, None), "s2": (False, 2)})
    result = await localize(run, manifest, [verifier])
    verdict = result.verdict
    assert verdict.verdict_kind == VerdictKind.MULTIPLE
    assert [o.stage_id for o in verdict.origins] == ["s0", "s2"]


async def test_nothing_flagged_is_undetermined_with_last_stage_candidate():
    run, manifest = make_run(), make_manifest()
    verifier = ScriptedVerifier({"s0": (True, None), "s1": (True, None), "s2": (True, None)})
    result = await localize(run, manifest, [verifier])
    verdict = result.verdict
    assert verdict.verdict_kind == VerdictKind.UNDETERMINED
    assert verdict.origins[0].stage_id == "s2"
    assert verdict.context is not None


async def test_disagreeing_verifiers_mark_boundary_contested_and_flagged():
    run, manifest = make_run(), make_manifest()
    optimist = ScriptedVerifier(
        {"s0": (True, None), "s1": (True, None), "s2": (True, None)}, source="optimist"
    )
    pessimist = ScriptedVerifier(
        {"s0": (True, None), "s1": (False, 1), "s2": (True, None)}, source="pessimist"
    )
    result = await localize(run, manifest, [optimist, pessimist])
    verdict = result.verdict
    assert [c.boundary for c in verdict.contested_boundaries] == ["s1"]
    assert len(verdict.contested_boundaries[0].verifiers) == 2  # signals kept separate
    assert verdict.origins[0].stage_id == "s1"  # any-flag counts as flagged


async def test_first_stage_input_assumed_acceptable():
    run, manifest = make_run(), make_manifest()
    verifier = ScriptedVerifier({"s0": (False, 0), "s1": (False, 1), "s2": (False, 2)})
    result = await localize(run, manifest, [verifier])
    verdict = result.verdict
    assert verdict.verdict_kind == VerdictKind.SINGLE
    assert verdict.origins[0].stage_id == "s0"
    assert verdict.propagation_path == ["s0", "s1", "s2"]
