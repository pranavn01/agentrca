"""Plug-in interfaces. Core depends on these; implementations live outside core (D15)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rca.core.model import Handoff, Stage, Step, VerifierSignal


@runtime_checkable
class Verifier(Protocol):
    """One opinion-producer for one boundary (§7).

    Implementations may be deterministic checks, human signals, or LLM judges;
    the engine is indifferent. A verifier sees one stage's contract, its inbound
    handoff, its own steps and its outbound handoff — never the full transcript.
    """

    source: str

    async def judge(
        self,
        *,
        contract: str,
        stage: Stage,
        steps: list[Step],
        inbound: Handoff | None,
        outbound: Handoff | None,
    ) -> VerifierSignal: ...
