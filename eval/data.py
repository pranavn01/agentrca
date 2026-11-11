"""Who&When dataset loading with stable example ids."""

from __future__ import annotations

from datasets import get_dataset_config_names, load_dataset

DATASET = "Kevin355/Who_and_When"
# Pin after first download for reproducible ids (HF repo revision).
REVISION: str | None = None


def load_examples() -> list[tuple[str, dict]]:
    """Returns (stable_id, example) pairs across every config and split."""
    configs = get_dataset_config_names(DATASET, revision=REVISION)
    out: list[tuple[str, dict]] = []
    for config in configs or [None]:
        dataset_dict = load_dataset(DATASET, config, revision=REVISION)
        for split_name, split in dataset_dict.items():
            out.extend(
                (f"{config or 'default'}/{split_name}/{i}", dict(example))
                for i, example in enumerate(split)
            )
    return sorted(out, key=lambda pair: pair[0])
