# Geopolitico Pipeline Improvement Plan

This document reviews the current architecture of Geopolitico and proposes practical improvements for each pipeline stage, with a focus on hallucination control, validation, and whether LangGraph is a good fit without breaking the current functionality.

## What the project is doing now

The system is already a multi-stage simulation pipeline:

1. The frontend collects a counterfactual scenario and sends it to the backend.
2. The backend starts a background simulation job and polls status through an in-memory job store.
3. The simulation engine refines the user prompt, plans the scenario, generates territory outcomes, runs validation, and may ask the user to resolve anomalies.
4. The user can then submit verification selections or a follow-up refinement message, which triggers another backend run.

The relevant entry points are [backend/main.py](backend/main.py), [backend/simulation_engine.py](backend/simulation_engine.py), [backend/agents/prompt_guardrail.py](backend/agents/prompt_guardrail.py), and [frontend/js/app.js](frontend/js/app.js).

## Current strengths

The project already has several good foundations:

1. It uses structured outputs, which is much better than freeform text-only generation.
2. It separates simulation, verification, and refinement into different paths.
3. It already has some anomaly detection and user-in-the-loop validation.
4. It uses geography-aware tools and polygon operations instead of relying only on text generation.
5. It has a fallback system for model failures, which improves availability.

Those are the right ingredients. The main issue is that many of the guardrails are still soft, and some of the fallback behavior currently prefers continuity over correctness.

## Main risks

### 1. Hallucinations can still pass through as valid

The prompt guardrail falls back to the original prompt when structured validation fails. That keeps the app running, but it also means a malformed, inconsistent, or unsafe input may still move forward as if it were acceptable.

### 2. Validation is mostly LLM-driven

The system asks the model to validate itself in multiple places. That is useful, but it is not enough as a final truth source. The strongest checks should be deterministic whenever possible.

### 3. The refinement loop can amplify drift

The interactive refinement step appends user instructions directly into the scenario flow. That is flexible, but repeated refinements can gradually move the simulation away from the original historical constraints unless the system re-anchors every time.

### 4. Job state is ephemeral

The backend stores job status in memory. That is fine for a prototype, but it will not survive restarts and it will not scale cleanly to multiple workers.

### 5. Client-side trust is too high

Verification selections come from the browser and are applied directly. That is acceptable for a demo, but a stronger backend validation boundary would reduce accidental or malformed state changes.

## Pipeline-by-pipeline improvements

### 1. Input and prompt cleaning pipeline

Goal: convert a user prompt into a historically coherent, bounded, testable scenario.

Recommended changes:

1. Keep the prompt-refinement step, but make it stricter. If the prompt is nonsensical, contradictory, or impossible in a way that breaks the simulation, return a validation failure instead of silently accepting it.
2. Split prompt refinement into two outputs: a cleaned prompt and a validation decision. That makes it easier to reject bad input without rewriting the user’s intent.
3. Add a deterministic schema check before any model call. For example, detect empty prompts, missing time period, impossible geography, or unsupported scenario types.
4. Log the original prompt, refined prompt, and validation reason separately so you can audit how often the guardrail changes user intent.

What this improves:

1. Less prompt drift.
2. Clearer failure modes.
3. Better auditability.

### 2. Planning pipeline

Goal: turn the refined prompt into a stable simulation plan with explicit constraints.

Recommended changes:

1. Force the planner to produce a compact machine-readable plan that includes year, parties, baseline polity names, target region, and simulation mode.
2. Require the planner to cite which parts of the scenario are directly grounded in history and which parts are speculative.
3. Add a confidence or risk field, but do not treat it as truth. Use it only to decide whether to trigger extra validation.
4. Prefer a small number of supported simulation modes over broad freeform logic. Narrow mode selection reduces hallucinated behavior.

What this improves:

1. Better consistency between prompt and downstream map generation.
2. Easier debugging.
3. Easier testing.

### 3. Geographic grounding pipeline

Goal: convert the plan into coordinates, polygons, and territory boundaries using deterministic logic as much as possible.

Recommended changes:

1. Treat geocoding and polygon clipping as authoritative geometry steps, not suggestions.
2. Keep all coordinate math outside the LLM whenever possible.
3. Validate every boundary operation against known geography rules, such as country containment, split direction, and coordinate ranges.
4. Cache geocoding and boundary results so the same scenario produces the same geometry across runs.
5. Add a fallback policy for missing geocodes that asks the user for clarification instead of guessing.

What this improves:

1. Less geographic hallucination.
2. Better reproducibility.
3. More reliable before/after maps.

### 4. Simulation and narrative pipeline

Goal: generate a plausible alternate history result without overclaiming certainty.

Recommended changes:

1. Separate factual baseline from speculative outcome in the output schema.
2. Require the model to list assumptions explicitly.
3. Add a post-generation fact check that verifies names, dates, places, and geopolitical claims against the plan.
4. Add a rule that speculative narrative cannot contradict the validated geometry or selected anomalies.
5. If the model invents unsupported claims, strip or downgrade them instead of passing them through.

What this improves:

1. Better narrative discipline.
2. Less confident falsehood.
3. Cleaner user trust.

### 5. Validation and anomaly pipeline

Goal: detect map problems before the user sees the final output.

Recommended changes:

1. Keep the anomaly detection step, but make the backend authoritative for whether an anomaly exists.
2. Add deterministic geometry validation for disconnected enclaves, self-intersections, invalid polygons, and impossible splits.
3. Create validation thresholds. For example, if geometry coverage or contiguity drops below a limit, force user review.
4. Keep the anomaly questions, but generate them only after deterministic checks have run.
5. Make the validation result a gate, not a cosmetic suggestion.

What this improves:

1. Fewer broken maps.
2. Better user decision quality.
3. More trustworthy final results.

### 6. Interactive refinement pipeline

Goal: let the user refine the simulation without losing the original historical anchor.

Recommended changes:

1. Do not append refinement instructions directly into the scenario as the only state. Store them as a separate refinement trace.
2. Re-run the full plan-and-validate loop after refinement instead of only patching the last result.
3. Keep a version history of scenario states so users can compare revisions.
4. Add a “refinement budget” or warning when the user has changed the scenario too far from the original prompt.

What this improves:

1. Reduces compounding hallucination.
2. Makes the refinement process explainable.
3. Preserves the original functionality while improving control.

## How to deal with AI hallucination

The best approach is not one single guardrail. It is a stack of guardrails.

### Use a layered strategy

1. Input validation: reject empty, contradictory, or unsupported scenarios early.
2. Structured output: force the model into a schema instead of freeform prose.
3. Grounding: use geography tools, source lookups, and known dataset boundaries for anything spatial or historical.
4. Deterministic checks: verify coordinates, polygon validity, country containment, and split directions in code.
5. Output review: run a final validator that compares the result against the plan and flags unsupported claims.
6. Human-in-the-loop: keep user review for uncertain or ambiguous territories.

### Practical anti-hallucination rules

1. Never let the model invent coordinates if a geocoder or boundary dataset can supply them.
2. Never let the model decide whether a polygon is valid without a geometry check.
3. Never let a fallback path silently mark invalid input as valid.
4. Never merge user refinement text directly into the core scenario without preserving history.
5. Never present speculative claims as historical fact.

### Add confidence, but use it carefully

Confidence scoring is useful only if it changes behavior. Good uses:

1. Trigger extra validation when confidence is low.
2. Ask the user for clarification when geography is ambiguous.
3. Label narrative sections as speculative when evidence is weak.

Bad use:

1. Showing a confidence score as if it were objective truth.

## Is LangGraph a good idea here?

Yes, it is accurate and doable, but only if you use it for orchestration rather than as a replacement for deterministic validation.

### Where LangGraph fits well

LangGraph is a good fit for:

1. Explicit step-by-step control over the workflow.
2. Conditional branching when validation fails.
3. Retry and fallback loops for model calls.
4. Human approval nodes for anomaly resolution.
5. Stateful refinement cycles with version tracking.

### Where LangGraph should not be used as a substitute

LangGraph should not replace:

1. Geometry validation.
2. Schema validation.
3. Data consistency checks.
4. Geocoding and polygon clipping logic.

Those should remain normal Python code or service logic.

### Recommended LangGraph shape

A good graph for this project would look like:

1. Input guardrail node.
2. Scenario planner node.
3. Geographic grounding node.
4. Simulation generation node.
5. Deterministic validation node.
6. Anomaly review node.
7. User refinement node.
8. Final rendering node.

Conditional edges should send the flow back to planning or validation when the output fails checks.

### Why this is better than the current style

The current pipeline already behaves like a graph, but the control flow is spread across modules and callbacks. LangGraph would make the state transitions explicit and easier to reason about. That usually improves maintainability, observability, and retry behavior.

## Is it accurate and doable while keeping the current functionality?

Yes, it is doable, and it can preserve the existing functionality if implemented carefully.

What makes it feasible:

1. The project already uses structured outputs.
2. The current system already has phases that map well to graph nodes.
3. The backend already separates simulation start, verify, and refinement paths.
4. The map rendering can stay as-is if the result schema stays stable.

What would need to stay stable:

1. The response schema used by the frontend.
2. The job status polling API.
3. The validation question shape.
4. The territory and geojson output format.

If those contracts stay stable, LangGraph can improve internal orchestration without forcing a frontend rewrite.

## What I would change first

If you want the highest return with the least disruption, do this in order:

1. Make the guardrail fail closed instead of falling back to valid by default.
2. Add deterministic geometry validation before any final result is shown.
3. Keep refinement history separate from the base scenario.
4. Add one final post-generation checker for unsupported narrative claims.
5. Introduce LangGraph only after the current contracts are stable.

## Suggested implementation path

Phase 1: harden the existing pipeline.

1. Tighten prompt validation.
2. Add more deterministic checks.
3. Record refinement history.
4. Improve logging and error reporting.

Phase 2: introduce orchestration structure.

1. Wrap the existing steps in a LangGraph flow.
2. Keep the same output schema.
3. Use graph edges for retries, fallback, and human review.

Phase 3: add deeper quality controls.

1. Add source-backed claim verification.
2. Add stronger geographic consistency checks.
3. Add regression tests for known scenarios.

## Bottom line

The project is already on the right track. The biggest improvement is not adding more LLM reasoning. It is making the system more deterministic at the places where correctness matters most.

LangGraph is a good and realistic addition for refinement and orchestration, but only if it is used to make the workflow explicit. The actual hallucination control should come from structured outputs, deterministic geometry checks, stricter validation gates, and preserving scenario history.

If you keep the current frontend/backend contract stable, you can improve reliability a lot without losing the current functionality.
