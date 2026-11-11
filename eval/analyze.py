"""Dev-set error analysis: per-config breakdown and over-flagging diagnostics.

Usage:
    uv run python -m eval.analyze results/<phase1_dir> results/<baseline_dir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def config_of(run_id: str) -> str:
    return run_id.split("/")[0]


def breakdown(records: list[dict]) -> dict[str, tuple[int, float, float]]:
    by_config: dict[str, list[dict]] = {}
    for record in records:
        by_config.setdefault(config_of(record["run_id"]), []).append(record)
    out = {}
    for config, recs in sorted(by_config.items()):
        n = len(recs)
        agent = sum(r["predicted_agent"] == r["true_agent"] for r in recs) / n
        with_step = [r for r in recs if r["true_step"] is not None]
        step = (
            sum(r["predicted_step"] == r["true_step"] for r in with_step) / len(with_step)
            if with_step
            else 0.0
        )
        out[config] = (n, agent, step)
    return out


def main() -> None:
    phase1_dir, baseline_dir = Path(sys.argv[1]), Path(sys.argv[2])
    phase1 = json.loads((phase1_dir / "records.json").read_text())
    baseline = json.loads((baseline_dir / "records.json").read_text())

    print("per-config accuracy:")
    for name, records in [("phase1", phase1), ("baseline", baseline)]:
        for config, (n, agent, step) in breakdown(records).items():
            print(f"  {name:8s} {config:22s} n={n:3d} agent={agent:6.1%} step={step:6.1%}")

    verdicts = json.loads((phase1_dir / "verdicts.json").read_text())
    truth_by_id = {r["run_id"]: r for r in phase1}
    stages_per_run: list[int] = []
    flagged_per_run: list[int] = []
    true_flagged = 0
    true_in_origins = 0
    rank_of_true: Counter[int] = Counter()
    by_config_diag: dict[str, Counter] = {}

    for entry in verdicts:
        record = truth_by_id.get(entry["id"])
        if record is None:
            continue
        config = config_of(entry["id"])
        diag = by_config_diag.setdefault(config, Counter(n=0, true_flagged=0, true_origin=0))
        diag["n"] += 1
        assessments = entry["assessments"]
        stages_per_run.append(len(assessments))
        flagged = [
            a
            for a in assessments
            if any(s["acceptable"] is False for s in a["signals"])
        ]
        flagged_per_run.append(len(flagged))
        true_agent = record["true_agent"]
        if any(a["stage_name"] == true_agent for a in flagged):
            true_flagged += 1
            diag["true_flagged"] += 1
        origin_names = [o["stage"] for o in entry["verdict"]["origins"]]
        if true_agent in origin_names:
            true_in_origins += 1
            diag["true_origin"] += 1
            rank_of_true[origin_names.index(true_agent)] += 1

    n = len(stages_per_run)
    print(
        f"\nstages/run avg={sum(stages_per_run) / n:.1f}  "
        f"flagged/run avg={sum(flagged_per_run) / n:.1f}"
    )
    print(f"true agent flagged somewhere: {true_flagged}/{n}")
    print(f"true agent among origins:     {true_in_origins}/{n}")
    print(f"rank of true agent in origins: {dict(sorted(rank_of_true.items()))}")
    print("\nper-config diagnostics (n / true flagged / true among origins):")
    for config, diag in sorted(by_config_diag.items()):
        print(
            f"  {config:22s} {diag['n']:3d} / {diag['true_flagged']:3d} / {diag['true_origin']:3d}"
        )


if __name__ == "__main__":
    main()
