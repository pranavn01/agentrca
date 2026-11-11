# Agents RCA — Design Document v1

Oct 4, 2026 · @Pranav

## 1. Purpose and scope

The product takes a failed multi-stage agent workflow run and returns a verdict naming the stage and step that caused the failure, with evidence. Nothing else.

**One-sentence definition:** *Given a failed multi-stage agent run, tell the platform team which stage caused it and prove it.*

**In scope**

- Attribution: origin stage, origin step, cause, propagation path
- Evidence: stage-scoped verification plus counterfactual replay
- Delivery of the verdict to where engineers already work
- Aggregation of verdicts over time into a propagation graph
- Calibrated confidence per verdict

**Explicitly out of scope (decided, not deferred)**

- Fixes of any kind: suggested fixes, prompt recommendations, remediation hints, "which prompt to look at", opened PRs, fix validation by replay, regression tests generated from failures
- Trace viewers, dashboards, cost or latency monitoring, generic LLM observability
- Evals, guardrails, prompt optimization, agent-building frameworks
- Single-agent or chatbot systems with no stage structure

The verdict says *where* and *why*. It stops before *what to do*. Any feature that smuggles a fix back in under another name ("recommended action", "remediation hint") is rejected on sight.

## 2. Problem, market, and positioning

No product performs step-level failure attribution with evidence; every tool that says "root cause" is doing classification at the point the failure became visible.

### The problem

In a multi-stage agent workflow, the stage where a failure *surfaces* is usually not the stage that *caused* it. Roughly 60% of production agent failures originate upstream of where they are observed. Consequences:

- **Time.** Attribution for one failed run takes an engineer 30 minutes to several hours. At volume it becomes a full-time role ("the trace reader").
- **Wrong fixes.** Patching the visible stage leaves the origin in place; the same root cause reappears with different symptoms, and downstream prompts accumulate defensive instructions compensating for upstream mistakes.
- **No aggregate signal.** Teams see failure rate, not failure source. They cannot answer "which stage is weakest" or "did last week's change to Plan help or hurt".

### The three tiers of existing tools

| Tier | Question answered | Who | Status |
| --- | --- | --- | --- |
| 1. Observability | What happened? Span tree of every LLM/tool call | LangSmith, Langfuse, Arize Phoenix, Datadog LLM Obs, Braintrust, Laminar, AgentOps, Helicone, MLflow | Commoditized. Not our product. |
| 2. Automated analysis | Which failures are common; what category is this one? | Patronus Percival (20+ failure modes, clustering), Arize AX Signal (scheduled scan, grouped issues, proposed cause), Latitude, Future AGI (diff failed vs successful), Fiddler, Confident AI, Maxim | Shipping. Classifies and clusters at the point of visibility. Markets itself as "root cause". Our direct comparison. |
| 3. Attribution | Which stage, which step, caused it, and how do you know? | Research only: Who&When (ICML 2025), TraceElephant, POIROT, StepFinder, spectrum and causal methods | Best published method: \~53% agent-level, \~14% step-level, on 2–4 agent systems. Nobody sells this. |

### Why Tier 3 is open

Every attribution method, research and commercial, hands an LLM the full multi-agent transcript and asks where it went wrong. That is a needle-in-haystack reasoning task models are bad at. Doing better requires (a) decomposing the judgment to one stage boundary at a time and (b) re-executing stages to test hypotheses, which needs execution environments, not logs. Tier 1 and 2 vendors have neither.

### Who has the problem

**Target:** platform / AI-infra teams at companies running multi-stage agent workflows in production, where a run is expensive enough that failures are worth diagnosing rather than retrying.

- Internal autonomous engineering pipelines (the originating case: Lisa at PANW, research → plan → repro → verify → fix → build → test → verify → document)
- Agentic data / ETL pipelines
- Support resolution and back-office automation (ticket triage, claims, KYC, invoice processing)
- Security operations automation
- Companies selling agent products who debug customer-reported failures

**User:** the engineer who owns the orchestrator and has become the de facto trace reader. **Buyer:** their engineering manager, paying for that engineer's time and for failed runs.

**Not the target:** single-agent chatbots, RAG Q&A, anything where retry is cheap and there is no stage structure.

### How corporate teams build these systems

Adoption data is thin, but the pattern is consistent: LangGraph leads among frameworks (roughly a third of framework citations in production architecture docs at 1,000+ employee companies); Microsoft Agent Framework, Google ADK and Bedrock AgentCore follow by cloud. Custom code with no framework is still the plurality. The Lisa pattern — one repo, one process, orchestrator calls agents as functions, prompts in `.md` files, state in memory — is assumed to be the single most common corporate build and is the primary target.

### Positioning

The defensible claim is **verified attribution**: "we don't guess where it broke, we proved it by replay." It is publicly benchmarkable and nobody else can make it. Phase 1 alone (decomposed judging) is copyable by an incumbent in a quarter; the moat is the replay SDK, the profiling cache, per-workflow calibrated confidence, and the propagation graph built from verified origins, which compound together.

## 3. Design philosophy

Every idea is tested against the fence below before it enters the design; every component follows the standing principles.

### The PMF fence

An idea is in scope only if all four hold:

1. **Requires stages.** If it makes sense for a single agent or a chatbot, it is out. Stage structure is the premise.
2. **Produces or strengthens a verdict.** Anything whose primary output is visibility (dashboards, trace viewers, cost tracking) is out.
3. **Agnostic at the abstraction layer.** Adapters, verifiers and replay providers may be specific to a framework or domain; the engine, run model, manifest schema and verdict schema may not.
4. **The platform team pays.** If value accrues to the app developer, end user or model provider, it is a distraction.

### Standing principles

| Principle | Statement | Where it came from |
| --- | --- | --- |
| Scope over determinism | Attribution accuracy comes from judging one stage boundary at a time, not from deterministic verifiers. Whole-trace judging is why published numbers are bad. | Item 1 debate on verification |
| Bring your own verifier | We never require deterministic criteria. Any verifier is accepted if it is independent of the stage it judges and sits at a boundary. | Same |
| Execution arbitrates | Where opinions conflict or evidence is thin, replay on real inputs decides. | Items 1, 4 |
| Never invent inputs for the primary verdict | Replay uses the original input, golden inputs from real successful runs, or sibling inputs. Synthesized inputs are a lower evidence tier, never required. | Item 1 (circularity) |
| Keep opinions separate and typed | Verifier results are never merged into one pass/fail. Each is a typed signal with measured reliability. | Item 4 |
| No LLM grades another on correctness | Accuracy is measured only against outcome-grounded data. One judge may assess another's *coverage* statically, never its correctness. | Item 4 |
| Report every origin the evidence supports | Never force a single answer for schema convenience; name fragility when no single origin exists. | Item 5 |
| Evidence type is the claim; the number is its track record | Confidence is an observed correctness rate for that kind of evidence, or it is absent. Never hand-tuned. | Item 6 |
| Every customer gets a verdict on day one | Judge-only verdicts are available with nothing but traces; every verdict shows how to make the next one stronger. | Item 7 |
| The engine never knows what stages are for | It reasons about stages, handoffs and evidence; domain nouns live in plug-ins. | Item 8 |
| Observe handoffs, do not infer them | Put the recorder where the handoff happens (the SDK decorator) rather than reconstructing from traces. | Item 9 |
| One benchmark per purpose | Credibility, moat and customer validation are three different measurements. | Item 10 |

## 4. Normalized run model

Every customer system is translated into one data model; everything upstream exists to populate it and everything downstream reads only it.

```
Run       { id, workflow, outcome, started, ended }
Stage     { name, run_id, index, parent_stage?, attempt, version_hash }
Step      { stage_id, kind: llm | tool | code | human, input, output, status }
Handoff   { from_stage, to_stage, payload, content_type, mechanism }
Verifier  { boundary, source, kind: deterministic | human | llm,
            question, result, coverage_gaps[], measured_accuracy? }
```

| Entity | Meaning | Notes |
| --- | --- | --- |
| Run | One execution of the workflow on one task | `outcome` is the run-level success signal (mandatory) |
| Stage | One agent's execution within a run | `attempt` distinguishes loop iterations; `parent_stage` captures sub-agent spawning; `version_hash` keys the profiling cache to the stage's prompt/code version |
| Step | One LLM call, tool call, code execution or human action inside a stage | Populates `steps[]` in replay results |
| Handoff | The payload that moved from one stage to the next | `payload` is opaque bytes to the engine; `mechanism` records how it moved (argument, shared state, file, queue) |
| Verifier | One opinion about one boundary | A list per boundary, never merged; see section 7 |

**Rules**

- The engine treats `Handoff.payload` and `Step.input/output` as opaque. Only adapters, verifiers and replay providers parse them.
- Topology is derived from `Stage.index`, `parent_stage`, `attempt` and `Handoff` edges; it is a DAG with loop unrolled by `attempt`.
- An orchestrator-as-LLM (a manager agent that decides routing) is a Stage whose output is the routing decision. It can be blamed like any other stage.
- The model is the product's stable core. Adapters, verifiers and replay providers are plug-ins; the model, manifest schema and verdict schema are not.

## 5. Ingest adapters

The SDK decorator is the primary ingest path because it serves the largest customer segment (in-process monorepos) and produces the best data; OTel is the zero-code fallback.

### Five axes of variation in how teams build agent systems

| Axis | Range | Matters to us? |
| --- | --- | --- |
| A. Agent definition | Prompt files, code classes, framework nodes (LangGraph, CrewAI, AG2, OpenAI Agents SDK, ADK), low-code builders, hosted platforms | Mostly no. Used only to auto-populate stage contracts from prompts. |
| B. Control flow | Hardcoded script, declarative graph, orchestrator-as-LLM, event/queue, workflow engine (Temporal, Prefect, Step Functions), hierarchical sub-agents | Yes: determines topology reconstruction. |
| C. State passing | In-memory objects, shared state object, message transcript, filesystem, external store, typed payloads over queue/API | Yes: determines handoff visibility. The hard case is in-memory. |
| D. Execution | One process, separate services, serverless, containers per task, mixed (LLM in-process, build/test in CI) | Yes: determines replayability. |
| E. Observability | Nothing, custom logs, OTel GenAI, vendor SDK (LangSmith, Langfuse, Braintrust, AgentOps, Datadog), framework-native (LangGraph checkpoints, Temporal history) | Yes: determines ingestibility. |

A and B carry the diversity; C, D and E carry the difficulty. Adapters exist to flatten C, D and E onto the run model.

### Adapter priority (decided)

| Priority | Adapter | Serves | Data quality | Replay | Why this rank |
| --- | --- | --- | --- | --- | --- |
| 1 | SDK decorator (Python) | In-process monorepos (Lisa pattern) | Best: boundaries and handoffs observed directly | Single-stage, same function | Largest segment; one mechanism solves ingest, handoff capture and replay |
| 2 | OpenTelemetry GenAI conventions | Custom code without SDK, Bedrock AgentCore, Datadog/Langfuse exports | Medium: boundaries inferred, handoffs recovered | LLM-call replay only | Widest zero-code coverage |
| 3 | LangGraph | Clean graph-based systems | High: checkpointed state gives handoffs and node boundaries | Single-stage via node invocation | Largest framework share; cheap to build |
| v2 | Temporal | Agents wrapped in durable execution | High: event history is a replayable state log | Full | Replay solved by the engine itself |
| v2 | SDK decorator (TypeScript) | Mastra/TS monorepos | Best | Single-stage | Second language |
| Later | Microsoft Agent Framework, Google ADK | Azure / GCP shops | High | Single-stage | Chosen by first customers' clouds |

### How the SDK decorator works as an adapter

```python
from rca import stage

@stage("plan", reads=["repo_path", "ticket"])
def plan(ctx):
    ...existing code...
```

At runtime the decorator:

1. Emits a Stage on function entry and exit; function arguments become the inbound Handoff payload, the return value the outbound one. Boundaries and handoffs are observed, not inferred.
2. Wraps LLM and tool clients inside the function to capture `steps[]`.
3. Snapshots any declared `reads` (globals, env vars, files) so replay can reconstruct hidden inputs.
4. Registers the function as a replay provider (section 9). The same function, called with a recorded payload, is the replay.

Divergence detection: if replay on the *original* input at temperature 0 produces a different output than recorded, the decorator reports "stage reads undeclared inputs" instead of producing a bad verdict, and the customer adds the missing `reads`.

Prompt-file agents with no per-agent function: the decorator goes on the generic runner call, stage name derived from the file.

### Topology reconstruction

| Property | Source | Reliability |
| --- | --- | --- |
| Order, parallelism | Timestamps and span parent/child | High when inferred |
| Loops | Repeated stage name in one run | High to detect; reason for looping needs orchestrator logic |
| Conditional branches | Stage present in some runs, absent in others | Pattern detectable; condition not |
| Data flow (consumes/emits) | Handoff edges (SDK) or prompt-content diffing (OTel) | High with SDK; weakest when inferred from traces |

Decision: infer order, loops and parallelism automatically; require the customer to confirm `consumes` / `emits` in a generated draft manifest. For SDK-instrumented customers data flow is observed and confirmation is a formality.

### Handoff recovery without the SDK

For OTel-only customers, the next stage's prompt usually contains the previous stage's output. Recovery = diff prompt text against prior outputs. Known failure modes: orchestrator transforms the payload; handoff is a path or ID not content; several upstream outputs merged into one prompt. Reliability is measured on the test bed (section 14); if the accuracy gap versus true handoffs is large, OTel customers are told handoff logging is required for replay-grade verdicts.

## 6. Workflow manifest

Onboarding is one declarative file, half generated from sample traces and confirmed by the customer, targeting under one hour.

### Required vs optional inputs

| Input | Source | Required | Fallback if absent |
| --- | --- | --- | --- |
| Stage inventory | Declared, or inferred from span/decorator names | Required | — |
| Topology (order, loops, parallelism, branches) | Inferred; customer confirms | Required | — |
| Stage contract (one sentence per stage: what it does, consumes, emits) | Declared; auto-drafted from prompt files or system prompts | Required | — |
| `consumes` / `emits` per stage | Observed (SDK) or inferred (OTel); customer confirms | Required | — |
| Run-level outcome expression | Declared | Required | Without it we cannot know the run failed |
| Handoff payloads | Trace (SDK or recovered) | Required | — |
| Stage verifier | Declared | Optional | Scoped LLM judge built from the contract |
| Replay hook | SDK decorator or explicit provider | Optional | LLM-call replay, then judge-only |
| `side_effects` per stage | Declared | Optional | Stage assumed side-effect-free only if customer says so; untagged tools default to write-blocked in replay |
| Tool read/write tags | Declared | Optional | Untagged = blocked in replay |
| Golden fixtures per stage | Declared | Optional | Golden inputs harvested from successful runs |
| Trace source | Detected | Required | — |

### Shape (SWE example; values are domain-specific, schema is not)

```yaml
workflow: jira-bug-resolver
outcome: tests_pass && pr_opened
trace_source: sdk
stages:
  - name: research
    consumes: [jira_ticket]
    emits: [context_summary]
    contract: "gather ticket details, related code, prior fixes"
    side_effects: []
  - name: plan
    consumes: [context_summary]
    emits: [repro_plan, fix_plan, test_plan]
    contract: "localize bug and define repro/fix/test steps"
  - name: reproduce
    consumes: [repro_plan]
    emits: [repro_result]
    verifier: repro_verification      # customer's own stage
    replay: { provider: sdk }
  - name: fix
    consumes: [fix_plan, repro_result]
    emits: [patch]
  - name: build
    consumes: [patch]
    emits: [build_status]
    verifier: "build_status == success"
    side_effects: [pushes_branch]
  - name: test
    consumes: [test_plan, build_status]
    emits: [test_results]
    verifier: "all_passed"
  - name: document
    consumes: [patch, test_results]
    emits: [pr_description]
    side_effects: [posts_to_jira]
topology: linear, with fix -> build -> test loop (max 3)
```

The same schema holds a claims workflow (`intake -> classify -> validate -> adjudicate -> notify`, outcome `claim_closed && no_reopen_30d`, replay via API dry-run). Only the values change.

### Two meanings of "success criteria"

- **Run-level outcome** (did the Jira bug get resolved): required.
- **Stage-level criteria** (did Repro actually reproduce the bug): optional; most customers have it for some stages and not others. The customer's own Verification agents are stage-level verifiers.

### Manifest drift

Pipelines change weekly. The manifest is keyed to each stage's `version_hash`; a trace whose stage versions do not match triggers regeneration of the draft and invalidates that stage's profiling cache. Full automatic drift handling is a v2 item (section 17).

## 7. Verifiers

Every verifier is a typed signal with measured reliability; none is merged into a single pass/fail, and execution arbitrates when they disagree.

### Bring-your-own-verifier

A verifier is any check at a stage boundary that is (a) independent of the stage it judges and (b) positioned at the boundary. Accepted implementations: deterministic checks (build status, schema validation, test pass), downstream outcome signals, human approvals, LLM judges (the customer's or ours). The engine is indifferent to implementation.

**Default when no customer verifier exists:** our scoped judge, prompted only with the stage contract, the inbound handoff and the outbound handoff: "stage X is supposed to do \[contract\]; given input I and output O, is O acceptable?" Never the full transcript.

### Two dimensions of reliability

| Dimension | Question | Measured how | Who may judge it |
| --- | --- | --- | --- |
| Accuracy | On the question it asks, how often is it right? | Against outcome-grounded data: golden handoffs from runs that succeeded, known-bad handoffs from attributed failures | Only outcomes. Never another LLM. |
| Coverage | Is it asking the right question relative to the contract? | Static comparison of the verifier's prompt or code against the manifest contract; reports contract requirements it does not check | Our judge may do this (scope comparison, not a correctness call) |

Example: a Repro Verification agent that checks "did the script run without error" while the contract says "did it reproduce the reported bug" has a coverage gap, independent of its accuracy. Human approvals have unknown coverage (nothing to read). Our scoped judge is calibrated identically; it has no special status.

### Precedence at a contested boundary

1. Deterministic and human verifiers are ground truth **for the question they ask and nothing more.** A passing build says the code compiled, not that the patch is correct; it does not override an LLM judge on a different question. Both are recorded as separate signals.
2. Between LLM verifiers: a disagreement inside a known coverage gap goes to the verifier that covers it.
3. Otherwise measured accuracy on that stage's golden set decides; the margin sets confidence.
4. No calibration yet (new stage, no successful runs): boundary is flagged *unanchored*, agreement rate between verifiers is reported as a weak proxy, and replay budget goes there first.
5. Disagreement itself is a signal. Contested boundaries are prioritized for replay and listed in the verdict's `contested_boundaries`.

### What this does not catch

If every verifier at a boundary agrees and all are wrong, nothing here detects it. Replay on the original input is the only backstop, which is why Phase 2 runs wherever a hook exists rather than being optional.

### Known caveat

The contract and the verifier are often written by the same person. If they misunderstand their own stage, both are wrong together and coverage analysis sees nothing. Outcome-grounded accuracy stays primary for that reason.

## 8. Attribution engine

The engine localizes suspects by judging each boundary in isolation, then confirms origins by replaying suspect stages on their real inputs and reading the verdict off a cached per-stage profile.

### Phase 1 — Localization

Walk the stage DAG along the propagation path from the observed failure backward. At each boundary apply every verifier (section 7) and produce a per-stage suspicion score. Output: an ordered list of candidate stages. This is the decomposition that distinguishes us from whole-trace judging.

Pruning rule: a stage whose boundary has a confident "output acceptable" result from calibrated verifiers is not replayed. Only flagged or contested boundaries proceed to Phase 2.

### Phase 2 — Confirmation by stage profiling

The original design (correct the upstream, replay the downstream) was rejected because it requires synthesizing a corrected input, which is nearly the attribution question itself (circularity). The adopted design replays suspects on inputs we have expectations about and reads the verdict off the resulting profile.

**Input classes**

| Class | Source | Expectation | Tells us | Run when |
| --- | --- | --- | --- | --- |
| Original | The failed run | Unknown | Does the stage fail systematically on this input? | Per failure, n samples |
| Golden | Customer fixtures, or handoffs harvested from past successful runs | Known-good output | Is the stage broken in general or only on this input? | Once per stage version; cached |
| Sibling | Other attempts/branches in the same run, or near-duplicate tasks | Known from that run's outcome | Does the stage behave consistently on similar inputs? | When available |
| Perturbed | Original with one minimal edit targeting the verifier's stated complaint | Should improve if the complaint was right | Validates the verifier's diagnosis without full synthesis | Only in the ambiguous row below; once |
| Degraded | Original or golden with a deliberate defect injected by a customer plug-in | Stage should detect or fail loudly | Does the stage propagate bad input silently? Feeds the propagation graph, not the per-failure verdict | Once per stage version; cached |

**Verdict matrix (original × golden)**

| Original input | Golden input | Reading | Action |
| --- | --- | --- | --- |
| fails | fails | Stage broken in general (prompt regression, model change, tool broken) | Origin, high confidence |
| fails | passes | Works on good input, fails on this one: either input was worse than the verifier thought, or the stage has a blind spot | Run one perturbed replay. Passes → origin is upstream, verifier missed it. Still fails → stage blind spot, this stage is origin |
| passes | passes | Original run was a fluke at this stage | Origin with low confidence, flagged nondeterministic |
| passes | fails | Golden fixture stale or stage changed | Flag the fixture; rerun profiling |

The second row is the ambiguity option C alone could not resolve; golden plus perturbed resolves it.

**Origin rule:** a stage is an origin when its input is judged acceptable and its output fails on replay systematically. Every stage on the propagation path meeting this rule is an origin (section 11, multi-origin). "First" is not special.

**Statistical reading:** each replay runs n samples. We compare `P(stage ok | input)` across input classes. 5/5 failures on original and 5/5 passes on golden is strong; 3/5 versus 4/5 is weak and the confidence bucket (section 12) reflects it.

### Cost structure

Golden and degraded profiling are properties of the stage, not the failure. Run once at onboarding, re-run when `version_hash` changes, cached. Per-failure cost is original-input replay on Phase-1 survivors (typically 1–2 stages × n samples) plus at most one perturbed replay. Approximately 2 × 5 stage executions per verdict, not 9 × 5. Levers if cost is still high: temperature-0 replay where the customer allows, binary search along the propagation path, a per-verdict budget cap with confidence reported as a function of budget spent.

### Dependent inputs

Replay on original, golden and sibling inputs uses real payloads, so dependents are whatever they were. Perturbed replay changes one field; rule: hold all other inputs fixed and accept the noise. Evidence type for perturbed replay ranks accordingly.

### Loops and orchestrators

Loop iterations are separate stage instances by `attempt`; blame lands on the attempt where the trajectory diverged. An orchestrator-as-LLM is a stage whose output is a routing decision; wrong delegation is attributable to it.

### Replay ladder (what runs when no hook exists)

1. Single-stage replay via SDK or declared provider: full evidence
2. LLM-call replay: re-issue the stage's recorded prompts with tool responses mocked from the trace; needs only full prompts in traces. Works for stages that are LLM-plus-tools; not for stages that execute code or hit live systems
3. Judge-only: Phase 1 result reported as-is, `evidence_type: judge_only`

Full-workflow replay is never needed because the scope is localization, not fix validation.

## 9. Replay interface and SDK

The replay interface is the most important API in the product; it is a language-neutral spec, implemented by SDKs so the customer writes one function body per stage and nothing else.

### Spec

```
replay(stage: str, payload: Handoff, options: ReplayOptions) -> ReplayResult

ReplayOptions {
  samples: int                  # n replays
  temperature: float?           # override; None = customer default
  model: str?                   # pin
  dry_run: bool = true          # side-effect handling, section 10
  environment: str?             # customer sandbox selector
  timeout_s: int
}

ReplayResult {
  output: Handoff
  steps: Step[]                 # every LLM/tool call inside the stage
  status: ok | error | blocked_side_effect | undeclared_input
}
```

Anyone can implement the spec raw over HTTP. The SDK exists so they do not have to.

### What the SDK does that the customer does not write

| Responsibility | Detail |
| --- | --- |
| Registration | Advertises which stages are replayable to the engine |
| Serialization | Normalized payload in, customer return value out |
| Instrumentation | Wraps OpenAI / Anthropic / LiteLLM clients and tool functions to populate `steps[]` |
| Options | Applies temperature, model pin, dry-run, timeout, environment |
| Transport | Local HTTP server, outbound worker that pulls jobs, or in-process (inside the customer's CI) |
| Safety | Refuses production writes unless an explicit override is passed (section 10) |
| Divergence check | Replays original input at temperature 0 and compares to recorded output; mismatch → `undeclared_input` |

### Customer's side

```python
from rca import stage, serve

@stage("plan", reads=["repo_path", "ticket"])
def plan(ctx):
    return run_plan_agent(ctx)     # existing code

serve()
```

For SDK-instrumented stages the decorator is simultaneously the ingest adapter and the replay provider; the recorded arguments are the replay payload, so input mapping is solved by observation.

### Input mapping (the bulk of integration work for non-SDK providers)

A stage's real input is almost never just the handoff. Lisa's Fix stage also reads the repo checkout at a commit, the repro result, the Jira ticket, environment config, and possibly orchestrator memory. A replay provider must reconstruct all of it. In in-process systems these reads are implicit and discovered by calling the stage in isolation and watching it fail. The `reads=[...]` declaration plus divergence detection is how the SDK surfaces them. For clean systems (LangGraph typed state, Temporal activities, containerized stages) the mapping is near-identity.

### Replay ladder by customer situation

| Customer has | Replay level | Evidence type |
| --- | --- | --- |
| SDK decorators on stages | Single-stage replay | `replay_original_input` and profile tiers |
| LangGraph / Temporal | Single-stage via framework | Same |
| Full prompts in traces, no hook | LLM-call replay with recorded tool responses | `llm_call_replay` |
| Traces without full prompts | None | `judge_only` |

The product shows each customer which stages are stuck at `judge_only` most often and names them as the first to decorate. Climbing the ladder is expected to happen over weeks, not at onboarding.

### Deferred

Transport default (worker vs local server vs in-process) is decided after the first SDK build; the outbound worker is the likely default for corporate networks (no inbound ports).

## 10. Isolation and side effects

Replay never executes a real write; stages with live effects are skipped, recorded, blocked or sandboxed, in that order.

| Order | Mechanism | How | When it applies | Limit |
| --- | --- | --- | --- | --- |
| 1 | Do not replay | Stages with declared `side_effects` are judged from the trace only | Default for Document, Notify, Deploy-style stages | Origins cluster in early read-mostly stages (Research, Plan), so coverage loss is small; but an origin that *is* side-effecting falls to judge-only exactly where it matters |
| 2 | Record/replay at the tool boundary | The SDK intercepts write tools in replay mode and returns the recorded response from the original run (VCR pattern); nothing is written | Replayed stage makes the same calls as the original | A novel call (different record id because the input changed) has no recording; it returns a synthetic success and the step is flagged unverified. Usually fine for RCA because the stage's decision is visible before the write |
| 3 | Read-allow, write-block | Tools tagged `read` in the manifest execute; tools tagged `write` or untagged short-circuit with a stub | Third-party services we cannot mock | Default-blocked untagged tools may break replay of a stage until tagged |
| 4 | Customer sandbox | `options.environment` points the provider at staging | Customers who already have one | We do not build sandboxes |

**Hard rule:** the SDK refuses production writes in replay unless an explicit, logged override is passed. There is no configuration that silently allows them.

**Scope consequence:** because the product is RCA only, replay never needs to run a pipeline to completion. Single-stage replay with recorded tool responses answers "did this stage decide correctly", which is all the verdict requires.

**Reserved for later (backlog):** full tool mocking beyond record/replay. Schema fields `side_effects` and `options.dry_run` exist now so the upgrade is additive.

## 11. Verdict schema

The verdict is the product's interface: it names every origin the evidence supports, states how each was established, and carries no fix.

```
Verdict {
  run_id, workflow
  verdict_kind:  single | multiple | compound | undetermined
  origins: [ {
      stage, step
      cause            # natural language, grounded in that step's input/output
      evidence_type
      confidence       # bucket rate or "uncalibrated"; see section 12
      samples          # { n, original_ok, golden_ok, perturbed_ok? }
  } ]
  propagation_path   # DAG fragment from each origin to the observed failure
  contested_boundaries: [ { boundary, verifiers[], resolution } ]
  budget             # replay spent vs cap
  context            # aggregate annotations, e.g. "stage C has 30% origin rate on this workflow; not exercised here"
}
```

### Evidence types, strongest first

| Evidence type | Meaning |
| --- | --- |
| `replay_original_input` | Stage replayed n times on its real input; failure is systematic |
| `replay_oracle_input` | Replayed on a golden handoff from a successful run (oracle) |
| `replay_perturbed_input` | Replayed with one verifier-directed minimal edit |
| `replay_synthesized_input` | Replayed with an LLM-generated corrected input; lowest replay tier, never required |
| `llm_call_replay` | Recorded prompts re-issued with tool responses mocked from the trace |
| `judge_only` | Phase 1 scoped judging only; no execution |

Evidence type is always shown beside the origin. The number is secondary.

### Verdict kinds

| Kind | Definition | What the engineer gets |
| --- | --- | --- |
| `single` | One origin | The common case |
| `multiple` | Two or more independent origins, each failing on an acceptable input | Each with its own evidence; fixing one will not make the run pass |
| `compound` | No stage fails alone; two or more boundaries are marginal (low verifier confidence, individual replays pass) | The marginal boundaries named; this is still RCA, it locates fragility |
| `undetermined` | Budget exhausted or no replay possible | Best candidates listed with judge-only evidence |

### Multi-origin rules

- Every stage on the propagation path meeting the origin rule is reported. "First" is not privileged.
- Phase 1 pruning still applies: only flagged or contested boundaries are replayed, so multi-origin detection costs extra only when Phase 1 already flagged multiple boundaries.
- Masked origins (a stage that would have failed but never ran on good input) are invisible in this run. The `context` field may carry that stage's aggregate origin rate from other runs, labeled as aggregate context, never as a claim about this run.

### What is not in the verdict

`fix_target`, recommended actions, prompt suggestions, remediation hints. Removed deliberately (section 1).

## 12. Confidence calibration

Confidence is the observed correctness rate of the verdict's evidence bucket for this workflow, or it is absent; it is never a hand-tuned score.

### Why not hand-tuned

Different customers' pipelines make different evidence types mean different things: replay-on-original may be 95% reliable on one workflow and 70% on another. A fixed weighting cannot express that. Empirical per-workflow calibration can.

### Mechanism (decided: option B)

1. Bucket every verdict by `(evidence_type, sample-stat band, contested?)`.
2. Measure correctness rate per bucket from labeled verdicts.
3. Report the bucket's observed rate as `confidence`.
4. Buckets are per workflow once data exists; global per-evidence-type buckets are the fallback before that.
5. A bucket below the minimum label count (initial value: 20) reports `confidence: uncalibrated` plus raw sample stats. No number is fabricated from priors.
6. `compound` and `undetermined` verdicts carry per-candidate confidence, not a single number.

### Label sources, in order of trust

| Source | What it provides | Availability | Bias |
| --- | --- | --- | --- |
| Benchmark ground truth (Who&When, TraceElephant) | Human-labeled origins | Before any customer exists | Benchmark systems are smaller than real pipelines |
| Golden-profile consistency | If stage S is named origin and S's golden profile shows it failing on known-good inputs, the label is corroborated | Continuous, free | Weak signal |
| Customer verdict feedback | One-click right / wrong / unsure on each delivered verdict | Primary once live | Engineers confirm verdicts matching intuition and skip the rest; overstates accuracy |

Verdict feedback is a required delivery-layer feature (section 13). The feedback bias is mitigated by weighting benchmark and golden-profile labels alongside it and by sampling a fraction of verdicts for mandatory review during onboarding. Not solved; noted.

### Rules

- Confidence is never shown without its evidence type.
- The evidence type is the claim; the number is that kind of claim's track record.
- A learned calibrator (logistic or isotonic over evidence features) is a later upgrade once labels are plentiful, not a launch requirement.

## 13. Delivery and aggregation

Verdicts go where engineers already look; over time they aggregate into a propagation graph showing which stages cause failures and which inherit them.

### Per-verdict delivery

- Channels: Slack, GitHub issue, Jira. One at launch.
- Content: the verdict (section 11) rendered with origin, evidence type and confidence first.
- **Verdict feedback:** right / wrong / unsure, one click, on every delivered verdict. Required for calibration (section 12) and for the known-bad handoff set that verifier accuracy measurement needs (section 7).
- Ladder prompt: when a verdict is `judge_only` or `llm_call_replay`, the delivery names the stage that most often lacks a replay hook on this workflow. This is the only "suggestion" the product makes, and it is about instrumentation, not the customer's agents.

### Aggregation (data collected at launch; UI is v2)

**Propagation graph** per workflow: nodes are stages; edge weight is how often failures propagate along that edge; node coloring is origin rate versus victim rate; time-sliced so a change to a stage shows as a shift.

Inputs to the graph:

- Verified origins from verdicts
- Propagation paths from verdicts
- Degraded-input profiling results (section 8): a stage that passes bad input through silently is a *propagator*, which explains why failures travel across several stages unnoticed
- Per-stage aggregate origin rate, used as `context` on individual verdicts for masked origins

The graph is the retention mechanism; the verdict is acquisition.

## 14. Validation

Three benchmarks, one per purpose: Who&When for a comparable headline number, TraceElephant for proving replay adds accuracy, and an OpenHands/SWE-bench corpus for the customer-shaped case.

| Layer | Benchmark | What runs | Purpose | Baseline to beat |
| --- | --- | --- | --- | --- |
| 1 | Who&When (ICML 2025; 2–4 agent systems, injected single faults, logs only) | Phase 1 only, no replay | External credibility; isolates the decomposition thesis. If Phase 1 cannot beat the baseline, the thesis is wrong | 53.5% agent-level, 14.2% step-level |
| 2 | TraceElephant (April 2026; multi-system traces with reproducible execution environments, labeled origins) | Full engine, evidence-type breakdown | Measures what replay adds over judge-only on the same traces; justifies the moat. Verify environments are public first; if not, publish our own from layer 3 | Same metrics, judge-only versus replay |
| 3 | Own corpus: OpenHands on SWE-bench Verified (hundreds of organically failed trajectories, \~9-stage pipeline, per-task Docker containers, test suite as outcome) | Full engine via the SDK integration path | Internal validation on long pipelines, multi-origin, real handoffs, monorepo integration (exercises exactly what a Lisa-style customer would do) | None; this is our number |

### Metrics on every layer

- Agent-level and step-level accuracy
- Accuracy by evidence type (feeds calibration, section 12)
- Verdict kind distribution (`single` / `multiple` / `compound` / `undetermined`)
- Replay cost per verdict (feeds budget rules, section 8)
- For layer 3 and OTel customers: attribution accuracy with recovered handoffs versus true handoffs (decides whether handoff logging is required for OTel-only customers)
- LLM-call replay fidelity: how often recorded tool responses match what re-issued calls request (decides whether the ladder's first rung exists in practice)

### Labeling layer 3

Manual at first (reading traces, which is also how the engine's failure modes are learned), then bootstrapped with golden-profile consistency.

### Guards

- Who&When's injected faults are single and often obvious. It is a floor to clear, not a target to optimize. Never tune on its test split.
- SWE-bench is still coding. First non-coding validation happens with the first non-coding customer on their traces; no synthetic non-coding benchmark is built.

## 15. Launch scope

v1 ships both phases with the SDK as the primary integration, so day-one verdicts exist for any customer with traces and every verdict shows how to make the next one stronger.

### Ships in v1

- [ ] Normalized run model and manifest schema
- [ ] Phase 1 engine (scoped judging, per-boundary verifier signals, pruning)
- [ ] Phase 2 engine (original-input replay, golden profiling from harvested successful runs, perturbed replay in the ambiguous row, verdict matrix)
- [ ] Python SDK: `@stage` decorator as ingest adapter and replay provider, `reads` declarations, divergence detection, record/replay of write tools, read/write blocking, production-write refusal
- [ ] LLM-call replay (trace-driven re-execution with recorded tool responses)
- [ ] OTel GenAI ingest adapter (zero-code fallback) with prompt-diff handoff recovery
- [ ] LangGraph adapter if time allows
- [ ] Verdict with evidence types, verdict kinds, multi-origin, contested boundaries, uncalibrated confidence
- [ ] Bucketed calibration from benchmark labels and verdict feedback
- [ ] Delivery to one channel (Slack or GitHub issue) with verdict feedback buttons and the ladder prompt
- [ ] Aggregate data collection for the propagation graph (no UI)
- [ ] Launch plug-in set: SWE-bench ingest, test-suite outcome verifier, container replay provider
- [ ] Validation layers 1–3 (section 14)

### Explicitly deferred

| Item | Reason | Trigger to revisit |
| --- | --- | --- |
| Temporal adapter | Clean-system minority | First customer on Temporal |
| TypeScript SDK | Second language | First TS/Mastra customer |
| Microsoft Agent Framework, Google ADK adapters | Cloud-specific | First customer on that cloud |
| Propagation graph UI | Data is collected; graph is retention, not acquisition | After first three customers |
| Degraded-input profiling | Feeds the graph, not the per-failure verdict | With the graph UI |
| Customer-supplied golden fixtures | Harvested goldens suffice initially | When a stage has never succeeded in any run |
| Full tool mocking | Record/replay covers the common case | When a side-effecting origin stage is hit in practice |
| Learned confidence calibrator | Buckets suffice until labels are plentiful | \~1,000 labeled verdicts |
| Automatic manifest drift handling | Version-hash invalidation covers v1 | Second customer |

### Honest risk to the ladder

If LLM-call replay proves unreliable (recorded tool responses rarely match what re-issued calls request), day-one verdicts are judge-only in practice and the ladder's first rung is missing. This is measured first on the test bed (section 14).

## 16. Decision log

Every design decision to date, with its rationale and the alternatives rejected.

| # | Decision | Rationale | Rejected alternatives |
| --- | --- | --- | --- |
| D1 | Build Tier 3 (attribution), not Tier 1 or 2 | Tiers 1 and 2 exist; nobody sells verified step-level attribution; research baseline is 14% step-level | Trace viewer; better Tier-2 classifier |
| D2 | Domain-agnostic product; coding pipelines as beachhead only | Technique (DAG attribution, replay, structural input classes) is domain-free; coding is where replay is cheapest to prove | Coding-only product (too narrow); generic launch with no beachhead |
| D3 | RCA only; no fixes of any kind | Narrower, cleaner claim; removes full-pipeline replay, fix validation and regression tests | Verdict with `fix_target`; PR-opening; prompt suggestions |
| D4 | Accuracy from scope (stage-scoped judging), not determinism | Whole-trace judging is why published numbers are bad; universal deterministic verifiers are impossible | Require deterministic criteria; whole-trace LLM analysis |
| D5 | Bring-your-own-verifier; scoped LLM judge as fallback | Customers already have partial verifiers; the engine is indifferent to implementation | Mandatory per-stage criteria |
| D6 | Minimum requirement: final outcome signal plus stage boundaries | Everything else is optional and raises confidence | Mandatory replay hook at onboarding |
| D7 | Normalized run model is the stable core; everything else is a plug-in | Keeps the engine agnostic; adapters absorb the five axes of variation | Per-framework engines |
| D8 | Replay on original input as primary Phase 2 mechanism (option C) | Removes circularity of synthesizing corrected inputs; no invented inputs in the primary verdict | Verifier-generated corrections (circular); oracle-only (rarely available) |
| D9 | Stage profiling with golden, sibling, perturbed and degraded input classes | Resolves the ambiguity option C leaves (fails-on-original, passes-on-golden); golden/degraded profiles are per-stage and cached, so per-failure cost stays low | Single replay per suspect |
| D10 | Dependent inputs held fixed in perturbed replay | Only perturbation changes an input; accept the noise, rank evidence accordingly | Re-derive dependents (requires more synthesis) |
| D11 | Verifiers are typed signals, never merged; accuracy measured only against outcomes; coverage assessed statically; replay arbitrates | Avoids one LLM grading another on correctness; keeps customer verifiers useful while knowing where they fall short | Customer always wins; our judge always wins; our judge grades theirs |
| D12 | Report all origins; verdict kinds `single` / `multiple` / `compound` / `undetermined` | Real runs have independent and compound faults; forcing one answer produces wrong verdicts | Single origin, earliest wins; Shapley-weighted contributions |
| D13 | Confidence = empirical bucket rate per workflow, else `uncalibrated` (option B) | Different customers' evidence types mean different things; hand-tuning cannot express that; numbers must be honest | Hand-tuned score; learned calibrator at launch |
| D14 | Launch both phases with the replay ladder (option C) | Day-one verdicts with traces only; LLM-call replay as the bridge; moat compounds as customers climb | Phase 1 only (feature, not product); require hook to onboard (no adoption) |
| D15 | Agnostic-core rules enforced structurally (no plug-in imports in core; domain-noun check on every core PR) | Pressure to leak coding logic into the engine will be constant | Doc-only guidance |
| D16 | SDK decorator is the primary ingest adapter and replay provider; in-process monorepos are the primary target | Largest customer segment and the best data; one mechanism solves boundaries, handoffs and replay | Framework-native adapters first (serves the minority) |
| D17 | Three-layer validation: Who&When (Phase 1), TraceElephant (full engine), OpenHands/SWE-bench (customer-shaped) | One benchmark cannot serve credibility, moat and customer validation at once | Single benchmark |
| D18 | Test bed is OpenHands on SWE-bench Verified | Open source, containerized per task, large failed-trajectory corpus, test suite as outcome, monorepo integration path | SWE-agent (lighter alternative); MetaGPT |
| D19 | Side-effecting stages: skip, record/replay, read-allow/write-block, sandbox, in that order; production writes refused by default | RCA-only scope means single-stage replay with recorded tools answers the question | Full tool mocking at launch |

## 17. Open questions and deferred items

Everything below is either empirical (answered by the test bed) or implementation-level (answered after the first build); none blocks starting.

| Item | Status | How it gets resolved | Trigger |
| --- | --- | --- | --- |
| Replay transport default (outbound worker vs local HTTP vs in-process) | Deferred | Decide after first SDK build; worker likely for corporate networks | SDK v0.1 |
| Handoff recovery reliability for OTel-only customers | Empirical | Measure attribution accuracy with recovered vs true handoffs on layer 3 | Layer 3 results |
| Topology inference threshold (when to require declared `consumes` / `emits`) | Empirical | Measure inference accuracy on layer 3; mostly moot for SDK customers | Layer 3 results |
| LLM-call replay fidelity | Empirical | Measure how often recorded tool responses satisfy re-issued calls | First test-bed run; decides whether the ladder's first rung exists |
| Sample count n per replay and per-verdict budget cap | Empirical | Measure cost and confidence curves on layer 3; initial n = 5 | Layer 3 results |
| Minimum label count per calibration bucket | Set at 20 | Revisit once feedback volume is known | \~100 delivered verdicts |
| Nondeterminism floor | Accepted | Expressed through confidence; some stages are coin flips at the customer's temperature | None |
| Side-effecting origin stages | Backlog | Falls to judge-only where it matters most; full tool mocking is the fix | First time it happens in practice |
| Manifest drift | v2 | Version-hash invalidation in v1; automatic draft regeneration later | Second customer |
| Golden inputs for never-succeeded stages | Deferred | Customer-supplied fixtures | When encountered |
| Verdict feedback bias | Noted, not solved | Weight benchmark and golden-profile labels; sample mandatory reviews during onboarding | Ongoing |
| Second-domain plug-in set | Deferred | Written for the first non-coding customer on their traces | First non-coding customer |

## 18. Known risks and limitations

The design holds under its assumptions; these are the places it can break.

| Risk | Why it matters | Mitigation in the design | Residual |
| --- | --- | --- | --- |
| Incumbents copy Phase 1 | Arize, LangSmith or Braintrust could ship decomposed judging in a quarter | Ship Phase 2 at launch; moat is the SDK, profiling cache, calibration and propagation graph, which compound | If customers never climb past judge-only, we are a feature |
| LLM-call replay unreliable | Day-one experience collapses to judge-only | Measured first on the test bed | Ladder's first rung may not exist for some workflows |
| Replay cost exceeds run cost | Product becomes unaffordable | Profiling cached per stage version; Phase 1 pruning; budget cap; temperature-0 where allowed | Long-context stages (Fix at 200K tokens) remain expensive to replay |
| In-process systems have hidden inputs | Replay diverges or fails | `reads` declarations plus divergence detection | Customer must find and declare every hidden read |
| Side-effecting origin stage | Cannot replay exactly where it matters | Record/replay at tool boundary | Novel writes get synthetic success and are flagged unverified |
| Verifier and contract wrong together | Coverage analysis sees nothing | Outcome-grounded accuracy stays primary | Undetectable until outcomes accumulate |
| All verifiers agree and are wrong | Phase 1 misses the boundary entirely | Replay on original input wherever a hook exists | Judge-only customers have no backstop |
| Benchmark does not transfer | Who&When is 2–4 agents with single injected faults; real pipelines are longer with organic multi-faults | Three-layer validation; Who&When treated as a floor | Published number may overstate real-world accuracy |
| Feedback-label bias | Calibration overstates accuracy | Mixed label sources; mandatory review sampling during onboarding | Partial |
| Onboarding requires a code change | Decorators need a PR into the customer's repo and a redeploy | OTel fallback for traces-only start | First conversation may end at "not this sprint" |
| Nondeterminism ceiling | Some stages are coin flips; attribution confidence has a floor we do not control | Reported as `nondeterministic` flag with low confidence | Cannot be engineered away |
| Agnostic-core erosion | Every shortcut toward shipping adds coding logic to the engine | Structural CI guard and PR domain-noun check | Requires discipline from day one |

## 19. Glossary

| Term | Meaning |
| --- | --- |
| Stage | One agent's execution within a run; the unit of attribution |
| Handoff | The payload that moved from one stage to the next; what propagation is traced through |
| Boundary | The point between two stages where a verifier sits |
| Verifier | Any independent check at a boundary: deterministic, human, downstream signal, or LLM judge |
| Scoped judge | Our default LLM verifier, prompted with only one stage's contract, input and output |
| Origin | A stage whose input is acceptable and whose output fails systematically on replay |
| Victim | A stage that received a bad input; downstream of an origin |
| Propagator | A stage that passes bad input through silently; measured by degraded-input profiling |
| Propagation path | The DAG fragment from each origin to the observed failure |
| Phase 1 | Localization: judge every boundary in isolation, rank suspects |
| Phase 2 | Confirmation: replay suspects on inputs with known expectations, read the profile |
| Stage profiling | Replaying a stage on original, golden, sibling, perturbed and degraded inputs to characterize it |
| Golden input | A handoff from a run that succeeded, or a customer fixture; known-good |
| Replay | Re-executing one stage with a chosen input, never the whole pipeline |
| Replay ladder | Single-stage replay > LLM-call replay > judge-only; what a customer gets by instrumentation level |
| LLM-call replay | Re-issuing a stage's recorded prompts with tool responses mocked from the trace |
| Evidence type | The kind of proof behind an origin claim; always shown beside confidence |
| Contested boundary | A boundary where verifiers disagreed; prioritized for replay |
| Verdict | The product's output: origins, propagation path, evidence, confidence; no fix |
| Manifest | The declarative description of a customer's workflow used for onboarding |
| `version_hash` | Identifier of a stage's prompt/code version; keys the profiling cache |
| Lisa | The originating system: an autonomous multi-agent SWE at PANW that resolves Jira bugs (research → plan → repro → verify → fix → build → test → verify → document); one repo, one process, prompts in `.md` files |
| Tier 1 / 2 / 3 | Observability / automated analysis / attribution (section 2) |
| PMF fence | The four tests every idea must pass (section 3) |
