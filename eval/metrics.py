"""Scoring for Who&When: agent-level and step-level accuracy (§14 metrics)."""

from __future__ import annotations

from pydantic import BaseModel


class PredictionRecord(BaseModel):
    run_id: str
    predicted_agent: str
    predicted_step: int | None
    true_agent: str
    true_step: int | None
    verdict_kind: str


class Summary(BaseModel):
    n: int
    agent_accuracy: float
    step_n: int  # records with a labeled mistake_step
    step_accuracy: float
    kind_counts: dict[str, int]


def summarize(records: list[PredictionRecord]) -> Summary:
    if not records:
        raise ValueError("no records to summarize")
    agent_hits = sum(r.predicted_agent == r.true_agent for r in records)
    step_records = [r for r in records if r.true_step is not None]
    step_hits = sum(r.predicted_step == r.true_step for r in step_records)
    kind_counts: dict[str, int] = {}
    for r in records:
        kind_counts[r.verdict_kind] = kind_counts.get(r.verdict_kind, 0) + 1
    return Summary(
        n=len(records),
        agent_accuracy=agent_hits / len(records),
        step_n=len(step_records),
        step_accuracy=step_hits / len(step_records) if step_records else 0.0,
        kind_counts=kind_counts,
    )
