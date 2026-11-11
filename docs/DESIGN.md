# Agents RCA — Design Digest

*The short version. Full specification, rationale, and decision log: [DESIGN-full.md](DESIGN-full.md).*

**One sentence:** given a failed multi-stage agent run, tell the platform team which stage and step caused it — and prove it.

## The problem

In a multi-stage agent pipeline (research → plan → code → test → …), the stage where a failure *surfaces* is usually not the stage that *caused* it. An engineer attributes each failure by reading transcripts: 30 minutes to hours per run. Existing tools either show you everything (observability) or classify the failure where it became visible (so-called "root cause" analysis). Nobody sells attribution back to the true origin, with evidence.

## What the product does — and refuses to do

**Output:** a verdict — origin stage and step, cause, propagation path, evidence type, calibrated confidence.

**Never:** suggested fixes, prompt recommendations, dashboards, trace viewers, chatbot support. The verdict says *where* and *why*, and stops before *what to do*. Any feature that smuggles a fix back in is rejected.

**Customer:** platform teams running multi-stage agent workflows in production, where runs are expensive enough to diagnose rather than retry. Not chatbots, not RAG Q&A.

## Core vocabulary

| Term | Meaning |
|---|---|
| Stage | One agent's execution within a run; the unit of attribution |
| Handoff | The payload that moved between stages |
| Boundary | The point between stages where verifiers sit |
| Verifier | Any independent check at a boundary: deterministic, human, or LLM judge |
| Origin | Stage whose input was acceptable but whose output fails |
| Victim | Stage that received bad input from an upstream origin |
| Verdict | The product's output; carries evidence, never a fix |

## How it works

1. **Ingest.** Adapters translate customer traces into one normalized run model (Run → Stage → Step, plus Handoffs). Primary path: a Python `@stage` decorator that observes boundaries and handoffs directly and doubles as the replay hook. Zero-code fallback: OpenTelemetry traces. The engine never parses payloads and never learns domain concepts — adapters, verifiers, and replay providers are plug-ins; the core is agnostic (enforced structurally, in CI).

2. **Manifest.** One declarative YAML per workflow: stages, topology, one-sentence contracts, run-level outcome. Half auto-generated from traces, confirmed by the customer. Target: onboarded in under an hour.

3. **Phase 1 — localization.** Judge each boundary *in isolation*: a scoped judge sees one stage's contract, input, and output — never the full transcript. Customer-supplied verifiers (build status, test results, their own checker agents) participate as typed signals that are never merged. Output: ranked suspect boundaries.

4. **Phase 2 — confirmation by replay.** Re-execute suspect stages on inputs with known expectations: the original input (does it fail systematically?), golden inputs harvested from successful runs (is the stage broken in general?), and minimally perturbed inputs (was the verifier's complaint right?). Replay converts an opinion into evidence. Golden profiles are cached per stage version, so per-failure cost stays near two stage executions.

5. **Verdict.** Kinds: `single`, `multiple` (independent origins), `compound` (fragility, no single culprit), `undetermined`. Evidence types are an explicit ladder — replay on original input is the strongest, judge-only the weakest — and the evidence type is always shown. Confidence is the *observed correctness rate* of that evidence bucket for that workflow, or `uncalibrated`. Never a hand-tuned score.

6. **Delivery and aggregation.** Verdicts go to Slack/GitHub/Jira with one-click right/wrong feedback (which feeds calibration). Over time, verified origins build a propagation graph per workflow: which stages cause failures, which inherit them, which silently pass bad data along.

## Safety rule for replay

Replay never executes a real write. In order: skip side-effecting stages, replay recorded tool responses (VCR pattern), block write-tagged tools, or use the customer's own sandbox. Production writes are refused unless explicitly overridden — there is no silent-allow configuration.

## Standing principles

- Accuracy comes from **scope** (one boundary at a time), supported by **execution** (replay arbitrates when opinions conflict).
- Never invent inputs for the primary verdict — original, golden, or sibling inputs only.
- No LLM grades another LLM's correctness; accuracy is measured only against outcomes.
- Report every origin the evidence supports; never force a single answer for schema convenience.
- Every customer gets a verdict on day one (judge-only works with traces alone); every verdict shows how to make the next one stronger (add a replay hook).

## Validation plan

Three benchmarks, one per purpose: **Who&When** (public, labeled culprits — external credibility for Phase 1), **TraceElephant** (re-executable traces — measures what replay adds over judging), and an **own corpus** of failed OpenHands runs on SWE-bench Verified (long pipelines, containerized replay — the customer-shaped case). Benchmark results are treated as floors to clear, never targets to tune on.

## v1 scope

Run model and manifest schema; Phase 1 and Phase 2 engines; Python SDK (`@stage` decorator as ingest + replay provider); LLM-call replay and OTel ingest as fallbacks; verdict with evidence types and uncalibrated-first confidence; one delivery channel with feedback; propagation-graph data collection (UI later). Deferred: Temporal/TS/cloud-specific adapters, graph UI, learned calibration, automatic manifest drift handling.
