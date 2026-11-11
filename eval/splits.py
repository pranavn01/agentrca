"""Seeded dev/holdout split. Who&When ships none, and the design doc's guard
(§14: never tune on the test split) requires one: all prompt iteration happens
on dev; the holdout is scored once."""

from __future__ import annotations

import json
import random
from pathlib import Path

SPLITS_PATH = Path(__file__).parent / "splits.json"
SEED = 42
HOLDOUT_FRACTION = 0.3


def generate(ids: list[str]) -> dict[str, list[str]]:
    shuffled = sorted(ids)
    random.Random(SEED).shuffle(shuffled)
    n_holdout = round(len(shuffled) * HOLDOUT_FRACTION)
    return {"holdout": sorted(shuffled[:n_holdout]), "dev": sorted(shuffled[n_holdout:])}


def load_splits() -> dict[str, list[str]]:
    return json.loads(SPLITS_PATH.read_text())


def main() -> None:
    from eval.data import load_examples

    ids = [example_id for example_id, _ in load_examples()]
    splits = generate(ids)
    SPLITS_PATH.write_text(json.dumps(splits, indent=2))
    print(f"wrote {SPLITS_PATH}: dev={len(splits['dev'])} holdout={len(splits['holdout'])}")


if __name__ == "__main__":
    main()
