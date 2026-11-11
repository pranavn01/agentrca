"""Scoped LLM judge — the default verifier when a customer has none (§7).

Prompted with one stage's contract, inbound payload, own steps and outbound
payload. Never the full transcript: the decomposition is the thesis.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from rca.core.model import Handoff, Stage, Step, VerifierKind, VerifierSignal
from rca.llm.client import LLMClient

SYSTEM = """\
You are a strict verifier for ONE stage of a multi-stage agent workflow.

You will be given: the stage's contract (what it is supposed to accomplish), the input \
payload it received, the steps it took (numbered), and the output payload it handed to \
the next stage.

Judge ONLY this stage against ONLY its contract. Assume its input is what it had to work \
with; do not speculate about what other stages did. The stage's output is UNACCEPTABLE if \
it is factually wrong, incomplete relative to the contract, fabricated or unsupported by \
the input and steps, contradicts the input, or would foreseeably cause a downstream stage \
to fail. Minor style issues do not make an output unacceptable.

If the output is unacceptable, identify the first step (by its bracketed number) where \
the stage's work went wrong. Keep the reason to at most two sentences."""

# Payload caps keep judge calls affordable; truncation is marked so the judge
# knows content is missing rather than absent.
MAX_PAYLOAD_CHARS = 12_000
MAX_STEP_CHARS = 4_000


class JudgeDecision(BaseModel):
    acceptable: bool
    first_bad_step: int | None = Field(
        default=None,
        description="The bracketed number of the step where the stage's work first went "
        "wrong; null when the output is acceptable.",
    )
    reason: str = Field(description="At most two sentences.")


class ScopedJudge:
    source = "scoped_judge"

    def __init__(self, client: LLMClient):
        self.client = client

    async def judge(
        self,
        *,
        contract: str,
        stage: Stage,
        steps: list[Step],
        inbound: Handoff | None,
        outbound: Handoff | None,
    ) -> VerifierSignal:
        question = f"Does the output of stage '{stage.name}' satisfy its contract?"
        decision = await self.client.structured(
            system=SYSTEM,
            user=self._render(contract, stage, steps, inbound, outbound),
            schema=JudgeDecision,
            max_tokens=2000,
        )
        valid_indices = {s.index for s in steps}
        suspect = (
            decision.first_bad_step
            if not decision.acceptable and decision.first_bad_step in valid_indices
            else None
        )
        return VerifierSignal(
            boundary=stage.id,
            source=self.source,
            kind=VerifierKind.LLM,
            question=question,
            acceptable=decision.acceptable,
            suspect_step=suspect,
            reason=decision.reason,
        )

    def _render(
        self,
        contract: str,
        stage: Stage,
        steps: list[Step],
        inbound: Handoff | None,
        outbound: Handoff | None,
    ) -> str:
        inbound_text = _clip(inbound.payload, MAX_PAYLOAD_CHARS) if inbound else "(workflow start)"
        outbound_text = (
            _clip(outbound.payload, MAX_PAYLOAD_CHARS) if outbound else "(no recorded output)"
        )
        step_lines = (
            "\n".join(
                f"[step {s.index}] ({s.kind.value}) {_clip(s.output or s.input, MAX_STEP_CHARS)}"
                for s in steps
            )
            or "(no recorded steps)"
        )
        return (
            f"## Stage\n{stage.name} (attempt {stage.attempt})\n\n"
            f"## Contract\n{contract}\n\n"
            f"## Input payload\n{inbound_text}\n\n"
            f"## Steps\n{step_lines}\n\n"
            f"## Output payload\n{outbound_text}"
        )


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated, {len(text) - limit} chars omitted]"
