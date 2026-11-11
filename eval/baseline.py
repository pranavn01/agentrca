"""Whole-trace baseline with the SAME model as Phase 1.

This is the control that isolates the decomposition thesis: if scoped
per-boundary judging only wins because of model quality, it will not beat
this baseline. Mirrors Who&When's "all_at_once" setting.

Usage:
    uv run python -m eval.baseline --split dev --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from pydantic import BaseModel

from eval.data import load_examples
from eval.metrics import PredictionRecord, summarize
from eval.splits import load_splits
from rca.adapters.whoandwhen import parse_example
from rca.llm.client import DEFAULT_MODEL, LLMClient

SYSTEM = """\
You are given the full transcript of a failed multi-agent run. Identify the agent whose \
mistake caused the failure and the step number where the decisive mistake happened. Keep \
the reason to at most two sentences."""

MAX_STEP_CHARS = 4_000


class BaselineAnswer(BaseModel):
    mistake_agent: str
    mistake_step: int
    reason: str


async def evaluate_one(example_id, example, client):
    run, truth = parse_example(example, run_id=example_id)
    agent_names = sorted({s.name for s in run.stages})
    task = run.inbound(run.ordered_stages()[0].id).payload if run.stages else ""
    lines = []
    for step in sorted(run.steps, key=lambda s: s.index):
        stage = next(s for s in run.stages if s.id == step.stage_id)
        content = step.output[:MAX_STEP_CHARS]
        lines.append(f"[step {step.index}] {stage.name}: {content}")
    answer = await client.structured(
        system=SYSTEM,
        user=(
            f"{task}\n\nAgents: {', '.join(agent_names)}\n\nTranscript:\n" + "\n".join(lines)
        ),
        schema=BaselineAnswer,
        max_tokens=1024,
    )
    return PredictionRecord(
        run_id=example_id,
        predicted_agent=answer.mistake_agent,
        predicted_step=answer.mistake_step,
        true_agent=truth.mistake_agent,
        true_step=truth.mistake_step,
        verdict_kind="baseline",
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    split_ids = set(load_splits()[args.split])
    selected = [(i, e) for i, e in load_examples() if i in split_ids]
    if args.limit:
        selected = selected[: args.limit]

    client = LLMClient(model=args.model, max_concurrency=args.concurrency)
    records: list[PredictionRecord] = []
    errors: list[dict] = []

    async def guarded(example_id, example):
        try:
            records.append(await evaluate_one(example_id, example, client))
        except Exception as exc:
            errors.append({"id": example_id, "error": f"{type(exc).__name__}: {exc}"})

    await asyncio.gather(*(guarded(i, e) for i, e in selected))

    summary = summarize(records)
    out_dir = Path("results") / f"{time.strftime('%Y%m%d-%H%M%S')}_baseline_{args.split}"
    out_dir.mkdir(parents=True)
    (out_dir / "summary.json").write_text(summary.model_dump_json(indent=2))
    (out_dir / "records.json").write_text(json.dumps([r.model_dump() for r in records], indent=2))
    (out_dir / "errors.json").write_text(json.dumps(errors, indent=2))

    print(f"n={summary.n} errors={len(errors)}")
    print(f"agent accuracy: {summary.agent_accuracy:.1%}")
    print(f"step accuracy:  {summary.step_accuracy:.1%} on {summary.step_n}")
    cost = client.usage.cost_usd(client.model)
    print(f"cost: ${cost:.2f}" if cost is not None else "cost: unknown model pricing")
    print(f"results in {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
