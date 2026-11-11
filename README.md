# Agents RCA

**Given a failed multi-stage agent run, name the stage and step that caused the failure — with evidence.**

In a multi-stage agent workflow (research → plan → code → test → …), the stage where a failure *surfaces* is usually not the stage that *caused* it. Engineers burn 30 minutes to hours per failure reading transcripts. This project automates that attribution. The full product vision — decomposed judging plus counterfactual **replay** of suspect stages — is in [docs/DESIGN.md](docs/DESIGN.md). This repo currently contains milestone 1: the Phase 1 (judge-only) attribution engine, validated on a public benchmark.

Status: research prototype. No SDK, no replay, no delivery layer yet.

## How it works

1. **Normalize** — an adapter translates a trace into the run model: `Run → Stage → Step`, with `Handoff` payloads between stages (`src/rca/core/model.py`). The engine never parses payloads; adapters do.
2. **Judge each boundary in isolation** — a *scoped judge* sees one stage's contract, its input, its steps, and its output. Never the full transcript (`src/rca/verifiers/scoped_judge.py`).
3. **Derive origins** — a stage whose input was judged acceptable but whose output was not is an *origin*; a flagged stage fed by a flagged input is a *victim* (`src/rca/core/phase1.py`).
4. **Adjudicate** — when several boundaries are flagged, one extra scoped call reviews the shortlist (in execution order, with the run's final wrong output) and picks the decisive origin.
5. **Emit a verdict** — origins, propagation path, evidence type, confidence (`src/rca/core/verdict.py`). Never a suggested fix — that's a deliberate scope decision (design doc §1).

Phase 2 (planned) replays suspect stages on their original and known-good inputs to *prove* the origin instead of judging it — see the roadmap below for why the benchmark results motivate exactly this.

## Evaluation

Benchmark: [Who&When](https://huggingface.co/datasets/Kevin355/Who_and_When) (ICML 2025) — 184 failed multi-agent runs, human-labeled with the culprit agent and decisive step. Two populations: **Algorithm-Generated** (90 short runs, ~7 messages, CaptainAgent/AG2) and **Hand-Crafted** (39 long runs, 60–90 messages, Magnetic-One) in our dev split.

Methodology:

- **Frozen 70/30 dev/holdout split** (seed 42, committed in `eval/splits.json`). All prompt iteration happened on dev; the holdout was scored once, after the configuration was frozen. Who&When ships no split of its own — the design doc's guard is "never tune on the test split."
- **Same-model control**: the published baselines (53.5% agent / 14.2% step) were measured with older models, so we also run a whole-trace baseline with our exact judge model (`claude-sonnet-4-6`). Beating only the published number would be a model upgrade, not a method.
- Stage contracts are auto-drafted from dev examples only (`eval/contracts.json`).
- Judge model: `claude-sonnet-4-6`, structured outputs, all responses disk-cached for reproducible, cheap re-runs.

### Dev results (129 runs, iterated on)

| Method | Agent acc | Step acc |
|---|---|---|
| Published best (older models, full dataset) | 53.5% | 14.2% |
| Phase 1, earliest-origin pick | 54.3% | 24.8% |
| **Phase 1 + adjudication** | **59.7%** | **33.3%** |
| Whole-trace, same model (control) | 67.4% | 45.0% |

Split by trace length, the aggregate hides the real story (agent-level accuracy):

| Method | Short runs (n=90) | Long runs (n=39) |
|---|---|---|
| Phase 1 + adjudication | 57.8% | **64.1%** |
| Whole-trace, same model | **74.4%** | 51.3% |

### Holdout results (55 runs, configuration frozen before scoring)

| Method | Agent acc | Step acc |
|---|---|---|
| Phase 1 + adjudication (frozen) | 48.1% | 18.5% |
| Whole-trace, same model (control) | **60.0%** | **36.4%** |

Per-population agent accuracy: short runs 45.7% vs 61.1%; long runs 52.6% vs 57.9% (n=19).

### Findings — reported as measured

1. **Judge-only decomposition does not beat same-model whole-trace on this benchmark.** The control wins the holdout overall and in both populations. Our frozen config beats the published step baseline (18.5% vs 14.2%) but not the published agent baseline (48.1% vs 53.5%) on this holdout; a modern model reading the whole trace beats both published numbers easily.
2. **The dev split told a better story that only partly survived.** On dev, decomposition won long traces by 13 points (64.1% vs 51.3%); on the 19-run holdout the direction reversed within noise. Both methods scored lower on holdout (ours −11.6, control −7.4) — the split is harder and our two adjudicator iterations fit dev somewhat. With n=19, the length hypothesis is *unresolved on this benchmark*, not refuted: Who&When's "long" traces are conversations, not the 9+-stage production pipelines the product targets. Layer-3 validation (OpenHands/SWE-bench, design doc §14) is the real test.
3. **Detection recall stays high; selection and the never-flagged remainder are the gaps.** The scoped judge flags the true culprit in 85% of holdout runs (46/54) — well above what our final answer converts (48%). The misses concentrate exactly where the design doc predicts judge-only verdicts fail (§18, "all verifiers agree and are wrong"), whose designed backstop is Phase 2 **replay**. These results are the empirical motivation for milestone 2, and they corroborate the design's own positioning that Phase 1 alone is a feature, not the product (§2).
4. Cost: ~$0.10 per attributed failure judge-only; whole-trace control ~$0.03.

Caveats: holdout n=55 carries ±13-point 95% intervals at these rates; 3 Hand-Crafted labels point outside their own history and are kept (every method scores them wrong, including published baselines); one holdout trajectory triggered a model refusal and is excluded from our n (54), not the control's (55); Who&When has single injected faults on 2–4-agent systems — a floor-clearing exercise, not production accuracy (design doc §14 guards).

## Repo layout

```
src/rca/
  core/        # stable core: run model, verdict schema, Phase 1 engine — imports no plug-ins (enforced by test)
  verifiers/   # scoped LLM judge
  adapters/    # Who&When ingest
  llm/         # Anthropic client: structured output, disk cache, cost accounting
eval/          # benchmark harness: splits, contract drafting, runner, whole-trace baseline, analysis
tests/         # unit tests + the core-isolation guard (design doc D15)
docs/DESIGN.md # the full product design document
```

## Reproducing the evaluation

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and `ANTHROPIC_API_KEY`. Full reproduction costs ~$20 in API calls (re-runs are ~free: all LLM responses are cached under `.cache/llm/`).

```bash
uv sync
uv run pytest                                              # 19 tests incl. core-isolation guard
uv run python -m eval.splits                               # regenerate frozen dev/holdout split
uv run python -m eval.draft_contracts                      # draft stage contracts from dev data (~$0.50)
uv run python -m eval.run_whoandwhen --split dev --adjudicate
uv run python -m eval.baseline --split dev                 # same-model whole-trace control
uv run python -m eval.analyze results/<phase1_dir> results/<baseline_dir>
```

## Roadmap

- **Milestone 2** — Phase 2 confirmation: single-stage replay on original/golden inputs, the Python `@stage` SDK (ingest + replay provider), and the OpenHands/SWE-bench corpus (design doc §8, §9, §14 layer 3). Directly attacks the measured recall ceiling.
- Calibrated confidence from labeled verdicts (§12), delivery layer (§13), OTel adapter (§5).
