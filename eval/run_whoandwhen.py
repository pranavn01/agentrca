"""Validation layer 1: Phase 1 (judge-only) over Who&When, scored against labels.

Usage:
    uv run python -m eval.run_whoandwhen --split dev --limit 5
    uv run python -m eval.run_whoandwhen --split dev --adjudicate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from eval.data import load_examples
from eval.draft_contracts import CONTRACTS_PATH
from eval.metrics import PredictionRecord, summarize
from eval.splits import load_splits
from rca.adapters.whoandwhen import parse_example
from rca.core.model import ManifestLite, Run
from rca.core.phase1 import Phase1Result, localize
from rca.llm.client import DEFAULT_MODEL, LLMClient
from rca.verifiers.scoped_judge import ScopedJudge

ADJUDICATOR_SYSTEM = """\
A multi-stage agent run failed its task. Independent scoped reviews flagged the stages \
below as suspect. Candidates are listed in EXECUTION ORDER, each with the reviewer's \
complaint and an excerpt of that stage's output. The run's final (wrong) result is also \
shown.

Pick the single candidate whose mistake was the decisive ORIGIN of the failure — the \
earliest mistake that corrupted everything after it. Apply these rules:
- A downstream stage that produced bad work from already-corrupted inputs is a victim, \
not the origin. Never pick a stage merely because it sits close to the final failure.
- An upstream complaint about a minor or recoverable imperfection that downstream stages \
in fact recovered from is noise; skip it.
- Decide by counterfactual: pick the candidate whose correction would most plausibly have \
made the run succeed.

Keep the reason to at most two sentences."""


class Adjudication(BaseModel):
    candidate: int = Field(description="The number of the decisive candidate.")
    step: int | None = Field(
        default=None,
        description="The bracketed step number of the decisive mistake, if identifiable.",
    )
    reason: str = Field(description="At most two sentences.")


def build_candidates(run: Run, result: Phase1Result) -> list[dict]:
    """All flagged boundaries in stage order, with propagation context. Victims
    (flagged stages whose input was also flagged) are included but labeled, so
    the adjudicator can still land on them when the upstream flag was noise."""
    by_stage = {a.stage_id: a for a in result.assessments}
    stages = run.ordered_stages()
    candidates = []
    for i, stage in enumerate(stages):
        assessment = by_stage[stage.id]
        if not assessment.flagged:
            continue
        signal = assessment.first_flagging_signal()
        input_flagged = i > 0 and by_stage[stages[i - 1].id].flagged
        candidates.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "suspect_step": signal.suspect_step if signal else None,
                "reason": signal.reason if signal else "",
                "victim": input_flagged,
            }
        )
    return candidates


async def adjudicate(
    client: LLMClient, run: Run, candidates: list[dict]
) -> tuple[str, int | None]:
    stages = run.ordered_stages()
    task = (run.inbound(stages[0].id) or run.handoffs[0]).payload[:2_000]
    final = run.outbound(stages[-1].id)
    final_text = final.payload[:1_000] if final else "(no recorded final output)"
    lines = []
    for i, candidate in enumerate(candidates):
        steps = run.steps_for(candidate["stage_id"])
        suspect = candidate["suspect_step"]
        excerpt_step = next((s for s in steps if s.index == suspect), steps[-1] if steps else None)
        excerpt = excerpt_step.output[:600] if excerpt_step else ""
        step_span = f"steps {steps[0].index}-{steps[-1].index}" if steps else "no steps"
        victim_note = " (input was itself flagged upstream)" if candidate["victim"] else ""
        lines.append(
            f"[candidate {i}] stage '{candidate['stage_name']}' ({step_span})"
            f"{victim_note}\n  complaint: {candidate['reason']}\n  output excerpt: {excerpt}"
        )
    decision = await client.structured(
        system=ADJUDICATOR_SYSTEM,
        user=(
            f"{task}\n\nFinal (wrong) result of the run:\n{final_text}\n\n"
            "Flagged candidates in execution order:\n" + "\n".join(lines)
        ),
        schema=Adjudication,
        max_tokens=2000,
    )
    if not 0 <= decision.candidate < len(candidates):
        chosen = candidates[0]
    else:
        chosen = candidates[decision.candidate]
    steps = run.steps_for(chosen["stage_id"])
    valid = {s.index for s in steps}
    step = (
        decision.step
        if decision.step in valid
        else (chosen["suspect_step"] if chosen["suspect_step"] in valid else None)
    )
    if step is None and steps:
        step = steps[0].index
    return chosen["stage_name"], step


async def evaluate_one(example_id, example, manifest, judge, client, use_adjudicator):
    run, truth = parse_example(example, run_id=example_id)
    result = await localize(run, manifest, [judge])
    verdict = result.verdict
    origin = verdict.origins[0]  # earliest origin, or the undetermined candidate
    predicted_agent = origin.stage
    predicted_step = origin.step
    if use_adjudicator:
        candidates = build_candidates(run, result)
        if len(candidates) > 1:
            predicted_agent, predicted_step = await adjudicate(client, run, candidates)
    if predicted_step is None:
        stage_steps = run.steps_for(origin.stage_id)
        predicted_step = stage_steps[0].index if stage_steps else None
    record = PredictionRecord(
        run_id=example_id,
        predicted_agent=predicted_agent,
        predicted_step=predicted_step,
        true_agent=truth.mistake_agent,
        true_step=truth.mistake_step,
        verdict_kind=verdict.verdict_kind.value,
    )
    return record, result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--adjudicate", action="store_true")
    args = parser.parse_args()

    split_ids = set(load_splits()[args.split])
    selected = [(i, e) for i, e in load_examples() if i in split_ids]
    if args.limit:
        selected = selected[: args.limit]

    manifest = ManifestLite.model_validate_json(CONTRACTS_PATH.read_text())
    client = LLMClient(model=args.model, max_concurrency=args.concurrency)
    judge = ScopedJudge(client)

    records: list[PredictionRecord] = []
    verdicts: list[dict] = []
    errors: list[dict] = []

    async def guarded(example_id, example):
        try:
            record, result = await evaluate_one(
                example_id, example, manifest, judge, client, args.adjudicate
            )
            records.append(record)
            verdicts.append(
                {
                    "id": example_id,
                    "verdict": result.verdict.model_dump(),
                    "assessments": [a.model_dump() for a in result.assessments],
                }
            )
        except Exception as exc:  # keep the sweep alive; failures are reported
            errors.append({"id": example_id, "error": f"{type(exc).__name__}: {exc}"})

    await asyncio.gather(*(guarded(i, e) for i, e in selected))

    summary = summarize(records)
    mode = "phase1adj" if args.adjudicate else "phase1"
    out_dir = Path("results") / f"{time.strftime('%Y%m%d-%H%M%S')}_{mode}_{args.split}"
    out_dir.mkdir(parents=True)
    (out_dir / "summary.json").write_text(summary.model_dump_json(indent=2))
    (out_dir / "records.json").write_text(
        json.dumps([r.model_dump() for r in records], indent=2)
    )
    (out_dir / "verdicts.json").write_text(json.dumps(verdicts, indent=2))
    (out_dir / "errors.json").write_text(json.dumps(errors, indent=2))
    (out_dir / "usage.json").write_text(
        json.dumps(
            {
                "model": client.model,
                **client.usage.model_dump(),
                "cost_usd": client.usage.cost_usd(client.model),
            },
            indent=2,
        )
    )

    print(f"n={summary.n} errors={len(errors)}")
    print(f"agent accuracy: {summary.agent_accuracy:.1%} (baseline to beat: 53.5%)")
    print(f"step accuracy:  {summary.step_accuracy:.1%} on {summary.step_n} (baseline: 14.2%)")
    print(f"verdict kinds:  {summary.kind_counts}")
    cost = client.usage.cost_usd(client.model)
    print(f"API calls: {client.usage.calls} (disk cache hits: {client.usage.disk_cache_hits})")
    print(f"cost: ${cost:.2f}" if cost is not None else "cost: unknown model pricing")
    print(f"results in {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
