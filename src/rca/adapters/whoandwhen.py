"""Who&When benchmark adapter: failure trajectories -> normalized Run + ground truth.

Mapping decisions (revisit in M1 error analysis):
- Contiguous same-agent messages form one Stage; a reappearing agent gets a new
  Stage instance with attempt incremented (loops unrolled, §4).
- Each history message is one Step whose global index equals its history index,
  so step-level predictions map directly onto the benchmark's mistake_step.
- The inbound Handoff payload is the task plus the previous stage's final
  message — the boundary message, not the whole transcript. Feeding the full
  transcript back in would recreate exactly the whole-trace judging the design
  rejects (§2).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

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
from rca.llm.client import LLMClient

WORKFLOW = "whoandwhen"


class Turn(BaseModel):
    index: int  # original position in `history`; mistake_step is scored against this
    agent: str
    content: str


class GroundTruth(BaseModel):
    mistake_agent: str
    mistake_step: int | None = None
    reason: str = ""


def build_run(run_id: str, task: str, turns: list[Turn]) -> Run:
    stages: list[Stage] = []
    steps: list[Step] = []
    handoffs: list[Handoff] = []
    attempts: dict[str, int] = {}
    previous_stage_id: str | None = None

    i = 0
    stage_index = 0
    while i < len(turns):
        agent = turns[i].agent
        j = i
        while j < len(turns) and turns[j].agent == agent:
            j += 1

        attempts[agent] = attempts.get(agent, 0) + 1
        stage_id = f"{run_id}/{stage_index}"
        stages.append(
            Stage(
                id=stage_id,
                name=agent,
                run_id=run_id,
                index=stage_index,
                attempt=attempts[agent],
            )
        )
        steps.extend(
            Step(
                stage_id=stage_id,
                index=turns[k].index,
                kind=StepKind.LLM,
                output=turns[k].content,
            )
            for k in range(i, j)
        )
        inbound_payload = (
            f"Task: {task}"
            if previous_stage_id is None
            else f"Task: {task}\n\nOutput of previous stage: {turns[i - 1].content}"
        )
        handoffs.append(
            Handoff(from_stage=previous_stage_id, to_stage=stage_id, payload=inbound_payload)
        )
        previous_stage_id = stage_id
        stage_index += 1
        i = j

    handoffs.append(
        Handoff(
            from_stage=previous_stage_id,
            to_stage=None,
            payload=turns[-1].content if turns else "",
        )
    )
    return Run(
        id=run_id,
        workflow=WORKFLOW,
        outcome=RunOutcome.FAILURE,
        stages=stages,
        steps=steps,
        handoffs=handoffs,
    )


# Magnetic-One logs orchestrator sub-activities as "Orchestrator (thought)",
# "Orchestrator (-> WebSurfer)" etc., while labels use the bare agent name.
_PARENTHETICAL = re.compile(r"\s*\(.*\)\s*$")


def normalize_agent(raw: str) -> str:
    return _PARENTHETICAL.sub("", raw).strip()


def extract_turns(example: dict) -> list[Turn]:
    """Agent identity is `name` (Algorithm-Generated) or `role` (Hand-Crafted).
    The initial 'human' message is the task, not an agent: it is filtered out,
    but original history indices are preserved so mistake_step still aligns."""
    turns: list[Turn] = []
    for i, entry in enumerate(example["history"]):
        raw = entry.get("name") or entry.get("role")
        if not raw:
            raise KeyError(f"history entry {i} has no agent field; keys={sorted(entry)}")
        agent = normalize_agent(str(raw))
        if agent.lower() == "human":
            continue
        turns.append(Turn(index=i, agent=agent, content=str(entry.get("content") or "")))
    return turns


def parse_example(example: dict, run_id: str) -> tuple[Run, GroundTruth]:
    run = build_run(run_id=run_id, task=str(example["question"]), turns=extract_turns(example))
    raw_step = example.get("mistake_step")
    truth = GroundTruth(
        mistake_agent=normalize_agent(str(example["mistake_agent"])),
        mistake_step=int(raw_step) if raw_step not in (None, "") else None,
        reason=str(example.get("mistake_reason") or ""),
    )
    return run, truth


DRAFT_SYSTEM = """\
You write stage contracts for agents in a multi-agent workflow. A contract is one \
sentence stating what the agent is responsible for producing, phrased so an independent \
reviewer could check an output against it. Base it only on the agent's name and the \
sample messages provided."""


class ContractDraft(BaseModel):
    contract: str


async def draft_manifest(
    client: LLMClient,
    agent_samples: dict[str, list[str]],
    max_samples: int = 3,
    sample_chars: int = 1_500,
) -> ManifestLite:
    """One cached LLM call per unique agent name (§5 axis A: prompts/roles are
    only used to auto-draft contracts)."""
    contracts: list[StageContract] = []
    for agent, samples in sorted(agent_samples.items()):
        shown = "\n---\n".join(s[:sample_chars] for s in samples[:max_samples])
        draft = await client.structured(
            system=DRAFT_SYSTEM,
            user=f"Agent name: {agent}\n\nSample messages from this agent:\n{shown}",
            schema=ContractDraft,
        )
        contracts.append(StageContract(name=agent, contract=draft.contract))
    return ManifestLite(workflow=WORKFLOW, contracts=contracts)
