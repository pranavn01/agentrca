# Agents RCA

**Given a failed multi-stage agent run, name the stage and step that caused the failure — with evidence.**

In a multi-stage agent workflow (research → plan → code → test → …), the stage where a failure *surfaces* is usually not the stage that *caused* it. Engineers burn 30 minutes to hours per failure reading transcripts. This project automates that attribution. The design — decomposed boundary judging plus counterfactual **replay** of suspect stages — is in [docs/DESIGN.md](docs/DESIGN.md) (digest) and [docs/DESIGN-full.md](docs/DESIGN-full.md) (full specification and decision log).

Status: research prototype. This repo contains the Phase 1 (judge-only) attribution engine and its benchmark harness. The SDK, replay engine (Phase 2), and delivery layer are the next milestone.

## How it works

1. **Normalize** — an adapter translates a trace into the run model: `Run → Stage → Step`, with `Handoff` payloads between stages (`src/rca/core/model.py`). The engine never parses payloads; adapters do.
2. **Judge each boundary in isolation** — a *scoped judge* sees one stage's contract, its input, its steps, and its output. Never the full transcript (`src/rca/verifiers/scoped_judge.py`).
3. **Derive origins** — a stage whose input was judged acceptable but whose output was not is an *origin*; a flagged stage fed by a flagged input is a *victim* (`src/rca/core/phase1.py`).
4. **Adjudicate** — when several boundaries are flagged, one extra scoped call reviews the shortlist (in execution order, with the run's final wrong output) and picks the decisive origin.
5. **Emit a verdict** — origins, propagation path, evidence type, confidence (`src/rca/core/verdict.py`). Never a suggested fix — that's a deliberate scope decision.

Phase 2 (planned) replays suspect stages on their original and known-good inputs to *prove* the origin instead of judging it.

## Validation

The engine is evaluated on [Who&When](https://huggingface.co/datasets/Kevin355/Who_and_When) (ICML 2025): 184 failed multi-agent runs, human-labeled with the culprit agent and decisive step. The harness in `eval/` is built for honest measurement:

- a **frozen 70/30 dev/holdout split** (seed 42, committed in `eval/splits.json`) — all iteration happens on dev; the holdout is scored once per frozen configuration;
- a **same-model whole-trace control** (`eval/baseline.py`), so any difference is attributable to the method rather than the model;
- stage contracts auto-drafted from dev examples only (`eval/contracts.json`);
- every LLM response disk-cached, so experiments are reproducible and re-runs are free.

Results are iterating alongside the engine and aren't published here yet; the harness below reproduces them end to end. Treat any Who&When number as a floor-clearing exercise on 2–4-agent systems with injected faults, not production accuracy.

## Repo layout

```
src/rca/
  core/        # stable core: run model, verdict schema, Phase 1 engine — imports no plug-ins (enforced by test)
  verifiers/   # scoped LLM judge
  adapters/    # Who&When ingest
  llm/         # Anthropic client: structured output, disk cache, cost accounting
eval/          # benchmark harness: splits, contract drafting, runner, whole-trace control, analysis
tests/         # unit tests + the core-isolation guard
docs/          # design digest + full specification
```

## Running the benchmark harness

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and `ANTHROPIC_API_KEY`. A full evaluation costs roughly $20 in API calls (re-runs are ~free: responses are cached under `.cache/llm/`).

```bash
uv sync
uv run pytest                                              # unit tests incl. core-isolation guard
uv run python -m eval.splits                               # regenerate frozen dev/holdout split
uv run python -m eval.draft_contracts                      # draft stage contracts from dev data
uv run python -m eval.run_whoandwhen --split dev --adjudicate
uv run python -m eval.baseline --split dev                 # same-model whole-trace control
uv run python -m eval.analyze results/<phase1_dir> results/<baseline_dir>
```

## Roadmap

- **Milestone 2** — Phase 2 confirmation: single-stage replay on original/golden inputs, the Python `@stage` SDK (ingest + replay provider), and a long-pipeline corpus built from OpenHands on SWE-bench Verified.
- Calibrated confidence from labeled verdicts, delivery layer (Slack/GitHub with verdict feedback), OTel ingest adapter.
