# Agents RCA — Design

*The working summary. Full specification, rationale, and the complete decision log: [DESIGN-full.md](DESIGN-full.md).*

**One sentence:** given a failed multi-stage agent run, tell the platform team which stage and step caused it — and prove it.

## 1. Scope

**In:** attribution (origin stage, origin step, cause, propagation path) · evidence (stage-scoped verification plus counterfactual replay) · delivery to where engineers work · aggregation into a propagation graph · calibrated confidence.

**Out, decided not deferred:** fixes of any kind (suggestions, remediation hints, PRs, fix validation) · trace viewers, dashboards, cost monitoring · evals, guardrails, prompt optimization · single-agent or chatbot systems. The verdict says *where* and *why*; it stops before *what to do*.

## 2. Problem and positioning

In a multi-stage pipeline, the stage where a failure *surfaces* is usually not the stage that *caused* it — most production agent failures originate upstream of where they're observed. Engineers attribute failures by reading transcripts (30 min–hours each); patching the visible stage leaves the origin in place; teams see failure *rate* but never failure *source*.

| Tier | Question answered | Status |
|---|---|---|
| 1. Observability | What happened? (span trees) | Commoditized — LangSmith, Langfuse, Datadog, etc. |
| 2. Automated analysis | What category is this failure? | Shipping — classifies at the point of *visibility*, markets it as "root cause" |
| 3. Attribution | Which stage *caused* it, and how do you know? | Research only. Nobody sells this. |

Tier 3 is open because every existing method hands an LLM the full transcript — a needle-in-haystack task — and nobody has execution environments to test hypotheses. The defensible claim is **verified attribution**: "we don't guess where it broke, we proved it by replay." Decomposed judging alone is copyable in a quarter; the moat is the replay SDK, the per-stage profiling cache, per-workflow calibration, and the propagation graph, which compound.

**Customer:** platform/AI-infra teams running multi-stage agent workflows in production, where runs are expensive enough to diagnose rather than retry. The primary build pattern we target: one repo, one process, orchestrator calls agents as functions, prompts in `.md` files, state in memory.

## 3. The PMF fence

An idea enters the design only if all four hold:

1. **Requires stages** — if it makes sense for a chatbot, it's out.
2. **Produces or strengthens a verdict** — visibility features are out.
3. **Agnostic at the right layer** — adapters/verifiers/replay providers may be domain-specific; the engine, run model, manifest and verdict schemas may not.
4. **The platform team pays** — value accruing elsewhere is a distraction.

## 4. Normalized run model

Every customer system is translated into one data model; everything downstream reads only it.

```
Run       { id, workflow, outcome, started, ended }
Stage     { name, run_id, index, parent_stage?, attempt, version_hash }
Step      { stage_id, kind: llm | tool | code | human, input, output, status }
Handoff   { from_stage, to_stage, payload, content_type, mechanism }
Verifier  { boundary, source, kind, question, result, coverage_gaps[], measured_accuracy? }
```

Rules: payloads are opaque to the engine (only plug-ins parse them); topology is a DAG derived from index/attempt/handoffs, loops unrolled by `attempt`; an orchestrator-as-LLM is just a stage whose output is a routing decision — blamable like any other.

## 5. Ingest

| Priority | Adapter | Why |
|---|---|---|
| 1 | **Python SDK decorator** | Largest segment (in-process monorepos); boundaries and handoffs *observed*, not inferred; doubles as the replay hook |
| 2 | OpenTelemetry GenAI | Zero-code fallback; handoffs recovered by diffing prompts against prior outputs |
| 3 | LangGraph | Largest framework share; checkpointed state is near-free to map |

The decorator (`@stage("plan", reads=["repo_path"])`) emits stage boundaries on entry/exit, captures arguments/returns as handoffs, wraps LLM/tool clients for `steps[]`, snapshots declared `reads`, and registers the function as its own replay provider. Divergence detection: if replay on the original input produces a different output than recorded, report "stage reads undeclared inputs" instead of a bad verdict.

## 6. Workflow manifest

Onboarding is one declarative YAML — stage inventory, topology, one-sentence contract per stage, `consumes`/`emits`, and the run-level outcome expression — half generated from sample traces, confirmed by the customer, in under an hour. Stage-level verifiers, replay hooks, side-effect tags, and golden fixtures are optional: each one raises evidence quality but none blocks onboarding.

## 7. Verifiers

**Bring your own:** any check at a boundary counts — build status, schema validation, human approvals, the customer's own checker agents, or our LLM judges. Requirements: independent of the stage it judges, positioned at the boundary.

**Default:** the *scoped judge* — prompted with one stage's contract, inbound handoff, and outbound handoff. Never the full transcript; the decomposition is the thesis.

**Reliability has two dimensions, measured differently:** *accuracy* (how often it's right on the question it asks — measured only against outcome-grounded data, never by another LLM) and *coverage* (is it asking the right question relative to the contract — assessable statically). Signals are typed and never merged into one pass/fail; where verifiers disagree, the boundary is marked contested and replay arbitrates. If every verifier agrees and all are wrong, nothing in Phase 1 catches it — replay on the original input is the only backstop.

## 8. Attribution engine

**Phase 1 — localization.** Walk the stage DAG backward from the observed failure; apply every verifier at each boundary; output ranked suspects. Boundaries with confident "acceptable" results from calibrated verifiers are pruned from Phase 2.

**Phase 2 — confirmation by stage profiling.** Never synthesize a "corrected" input (that's the attribution question itself, circular). Instead, replay suspects on inputs with known expectations:

| Input class | Source | Tells us |
|---|---|---|
| Original | the failed run | does the stage fail *systematically* on this input? |
| Golden | harvested from successful runs / fixtures | broken in general, or only here? (cached per stage version) |
| Sibling | other attempts in the same run | consistent behavior on similar inputs? |
| Perturbed | one minimal edit targeting the verifier's complaint | was the verifier's diagnosis right? |

**Verdict matrix (original × golden):** fails/fails → origin, high confidence. fails/passes → ambiguous: run one perturbed replay (passes → origin is upstream, verifier missed it; fails → stage blind spot, this is the origin). passes/passes → fluke; low confidence, flagged nondeterministic. passes/fails → stale golden; re-profile.

**Origin rule:** input acceptable + output fails systematically on replay. Every stage on the path meeting the rule is an origin — "first" is not special.

**Replay ladder** (evidence degrades gracefully): single-stage replay via SDK → LLM-call replay (re-issue recorded prompts, tool responses mocked from the trace) → judge-only. Full-workflow replay is never needed: the scope is localization, not fix validation.

## 9. Verdict

```
Verdict { run_id, workflow, verdict_kind, origins[], propagation_path,
          contested_boundaries[], budget, context }
Origin  { stage, step, cause, evidence_type, confidence, samples }
```

| Kind | Meaning |
|---|---|
| `single` | one origin — the common case |
| `multiple` | independent origins; fixing one won't make the run pass |
| `compound` | no stage fails alone; the marginal boundaries are named |
| `undetermined` | budget exhausted or no replay possible; best candidates listed |

Evidence types, strongest first: `replay_original_input` > `replay_oracle_input` > `replay_perturbed_input` > `replay_synthesized_input` > `llm_call_replay` > `judge_only`. The evidence type is always shown beside the origin; the number is secondary.

## 10. Confidence

Confidence is the **observed correctness rate** of the verdict's evidence bucket `(evidence_type, sample-stat band, contested?)` for this workflow — or `uncalibrated` when fewer than 20 labels exist. Never hand-tuned: the same evidence type can be 95% reliable on one pipeline and 70% on another, and only empirical per-workflow calibration can express that. Labels come from benchmarks, golden-profile consistency, and one-click verdict feedback (its optimism bias is noted and mitigated, not solved).

## 11. Replay safety

Replay never executes a real write. In order: (1) don't replay declared side-effecting stages; (2) record/replay tool responses from the original run (VCR pattern); (3) read-allow/write-block by manifest tags, untagged tools blocked; (4) customer sandbox. Production writes are refused unless explicitly overridden — no configuration silently allows them. Because the product is RCA-only, single-stage replay with recorded tools answers "did this stage decide correctly," which is all the verdict needs.

## 12. Delivery and aggregation

Verdicts go to one channel at launch (Slack or GitHub issue), rendered origin-and-evidence-first, with one-click right/wrong/unsure feedback (required: it feeds calibration). The only "suggestion" the product ever makes is which stage to instrument next for stronger evidence. Over time, verified origins and propagation paths aggregate into a **propagation graph** — which stages cause failures, which inherit them, which silently propagate bad data. The verdict is acquisition; the graph is retention.

## 13. Validation

One benchmark per purpose, results treated as floors to clear, never targets to tune on:

| Layer | Corpus | Purpose |
|---|---|---|
| 1 | Who&When (public, labeled culprits) | external credibility; isolates the decomposition thesis |
| 2 | TraceElephant (re-executable traces) | measures what replay adds over judging — the moat claim |
| 3 | Own corpus: OpenHands on SWE-bench Verified | long pipelines, real handoffs, containerized replay — the customer-shaped case |

## 14. v1 scope

**Ships:** run model + manifest schema · Phase 1 and Phase 2 engines · Python `@stage` SDK (ingest + replay, divergence detection, write blocking) · LLM-call replay · OTel adapter · verdict with evidence types and multi-origin · bucketed calibration · one delivery channel with feedback · propagation-graph data collection (no UI) · validation layers 1–3.

**Deferred with triggers:** Temporal/TypeScript/cloud-specific adapters (first such customer) · graph UI (after three customers) · degraded-input profiling (with the graph) · learned calibrator (~1,000 labels) · automatic manifest drift handling (second customer).

## 15. Top risks

- **Incumbents copy Phase 1** — ship Phase 2 at launch; the moat compounds only if customers climb the replay ladder.
- **LLM-call replay proves unreliable** — then day-one verdicts are judge-only; measured first on the test bed.
- **Hidden inputs in in-process systems** — `reads` declarations + divergence detection; the customer must find every hidden read.
- **Nondeterminism floor** — some stages are coin flips; expressed honestly through confidence, cannot be engineered away.
- **Agnostic-core erosion** — every shipping shortcut pressures coding logic into the engine; enforced structurally in CI, not by discipline alone.
