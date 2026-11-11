"""Draft one contract per unique agent name from DEV examples only, and freeze
the result to eval/contracts.json. Holdout messages never inform contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

from eval.data import load_examples
from eval.splits import load_splits
from rca.adapters.whoandwhen import draft_manifest, extract_turns
from rca.llm.client import LLMClient

CONTRACTS_PATH = Path(__file__).parent / "contracts.json"
SAMPLES_PER_AGENT = 3


async def main() -> None:
    dev_ids = set(load_splits()["dev"])
    agent_samples: dict[str, list[str]] = {}
    for example_id, example in load_examples():
        if example_id not in dev_ids:
            continue
        for turn in extract_turns(example):
            if not turn.content:
                continue
            samples = agent_samples.setdefault(turn.agent, [])
            if len(samples) < SAMPLES_PER_AGENT:
                samples.append(turn.content)

    client = LLMClient()
    manifest = await draft_manifest(client, agent_samples)
    CONTRACTS_PATH.write_text(manifest.model_dump_json(indent=2))
    print(f"wrote {CONTRACTS_PATH}: {len(manifest.contracts)} contracts")
    print(f"usage: {client.usage.model_dump()} cost=${client.usage.cost_usd(client.model):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
