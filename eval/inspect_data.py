"""One-off: inspect Who&When naming conventions to finalize the adapter mapping."""

import collections

from datasets import load_dataset

DATASET = "Kevin355/Who_and_When"


def main() -> None:
    hc = load_dataset(DATASET, "Hand-Crafted")["train"]
    for i in [0, 1, 2]:
        ex = hc[i]
        pairs = collections.Counter((e.get("role"), e.get("name")) for e in ex["history"])
        print(f"ex{i}: mistake_agent={ex['mistake_agent']!r} step={ex['mistake_step']} "
              f"entries={len(ex['history'])}")
        for pair, count in pairs.most_common():
            print("   (role, name) =", pair, "x", count)

    mismatches = []
    for i, ex in enumerate(hc):
        names = {e.get("name") or e.get("role") for e in ex["history"]}
        if ex["mistake_agent"] not in names:
            mismatches.append((i, ex["mistake_agent"], sorted(str(n) for n in names)[:8]))
    print("\nhand-crafted mismatches:", len(mismatches))
    for m in mismatches[:6]:
        print("  ", m)

    out_of_range = [
        (i, int(ex["mistake_step"]), len(ex["history"]))
        for i, ex in enumerate(hc)
        if not (0 <= int(ex["mistake_step"]) < len(ex["history"]))
    ]
    print("hand-crafted out-of-range steps:", out_of_range)

    ag = load_dataset(DATASET, "Algorithm-Generated")["train"]
    roles = collections.Counter()
    missing_name = 0
    for ex in ag:
        for e in ex["history"]:
            roles[e.get("role")] += 1
            if not e.get("name"):
                missing_name += 1
    print("\nalgorithm-generated: role distribution", dict(roles),
          "entries missing name:", missing_name)


if __name__ == "__main__":
    main()
