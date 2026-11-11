"""Async Anthropic client: structured output, disk cache, prompt caching, cost accounting.

Built against anthropic SDK 1.x: sampling parameters (temperature et al.) no
longer exist, and structured output is first-class via output_config.format.
The disk cache makes eval re-runs free: identical requests return the recorded
output without an API call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "claude-sonnet-4-6"

# USD per million tokens, for reporting only.
PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5-20251001": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
}

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class Usage(BaseModel):
    calls: int = 0
    disk_cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost_usd(self, model: str) -> float | None:
        prices = PRICES.get(model)
        if prices is None:
            return None
        return (
            self.input_tokens * prices["input"]
            + self.output_tokens * prices["output"]
            + self.cache_read_tokens * prices["cache_read"]
            + self.cache_write_tokens * prices["cache_write"]
        ) / 1_000_000


class StructuredOutputError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        cache_dir: str | Path = ".cache/llm",
        max_concurrency: int = 8,
    ):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.usage = Usage()
        self._client = anthropic.AsyncAnthropic(max_retries=5)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[SchemaT],
        max_tokens: int = 1024,
    ) -> SchemaT:
        """One structured-output call: the response is constrained to JSON
        matching the pydantic model's schema (output_config.format)."""
        json_schema = schema.model_json_schema()
        json_schema.setdefault("additionalProperties", False)
        cache_key = _digest(
            {
                "model": self.model,
                "system": system,
                "user": user,
                "schema": json_schema,
                "max_tokens": max_tokens,
            }
        )
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            self.usage.disk_cache_hits += 1
            return schema.model_validate_json(json.loads(cache_path.read_text())["text"])

        last_error: Exception | None = None
        for attempt_max_tokens in (max_tokens, max_tokens * 2):
            async with self._semaphore:
                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=attempt_max_tokens,
                    output_config={"format": {"type": "json_schema", "schema": json_schema}},
                    # cache_control here caches the system prefix across the
                    # thousands of judge calls that share it (5-minute TTL).
                    system=[
                        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                    ],
                    messages=[{"role": "user", "content": user}],
                )

            self.usage.calls += 1
            self.usage.input_tokens += response.usage.input_tokens
            self.usage.output_tokens += response.usage.output_tokens
            self.usage.cache_read_tokens += response.usage.cache_read_input_tokens or 0
            self.usage.cache_write_tokens += response.usage.cache_creation_input_tokens or 0

            text = "".join(block.text for block in response.content if block.type == "text")
            try:
                if not text:
                    raise StructuredOutputError(
                        f"no text content in response (stop_reason={response.stop_reason})"
                    )
                result = schema.model_validate_json(text)
                break
            except (StructuredOutputError, ValidationError) as exc:
                # An output truncated at max_tokens parses as invalid JSON;
                # one retry with a doubled cap recovers it.
                last_error = exc
        else:
            raise StructuredOutputError(f"structured output failed twice: {last_error}")

        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"text": text}))
        os.replace(tmp, cache_path)
        return result


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
