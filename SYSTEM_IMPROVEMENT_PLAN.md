# Geopolitico v2 — Complete System Improvement Plan

**Status:** Design + implementation plan. No code has been changed.
**Scope:** Redesign the decision-making architecture so that territorial outcomes are
geographically and logistically *continuous with the historical baseline*, while
remaining fully permissive about the political *outcome* (it is a what-if simulator).

**Core principle (the pivot):**
> The engine is **deterministic about geography and logistics**, and **fully
> permissive about the political outcome**. The historical dataset is the source of
> truth for *where things are and how hard it is to move*, never for *what should happen*.
>
> "Accuracy" in a what-if engine means **baseline-continuity**, not historical
> correspondence. A what-if can put the Umayyads in Vienna; it cannot put them in
> Vienna with a border that ignores the Alps and the Danube.

---

## 0. Problem Restatement (validated against `simulation.log`)

The current pipeline is **LLM-first with GIS as a post-processor**: the LLM emits a
territory spec (`countries_absorbed`, `partial_countries`), and Shapely only *draws* it.

| Observed symptom | Structural cause |
|---|---|
| Modern Turkey instead of Byzantine Anatolia | LLM picks a 1923 concept; no historical-region resolver |
| Inconsistent natural boundaries | `natural_boundary_tool` is geometric-only; no hydrology model |
| Random neighbor inclusion/exclusion | LLM free to add/absorb any country; no adjacency model |
| Disconnected enclaves | Validation LLM sees only Stage-2 list, no Stage-1 context |
| Optimistic ignores logistics | No logistics/military constraint layer exists |
| Outputs change between runs | No `seed`; `list(set(...))`; model fallback swaps models |

Every symptom is a **continuity failure**, not an accuracy failure. The fix is to
invert the dependency: **the database + rule engine decide what is *possible*; the LLM
only selects among plausible options and writes the story.**

This plan extends `PIPELINE_IMPROVEMENT_PLAN.md` (which already concluded: "The biggest
improvement is making the system more deterministic where correctness matters most").

---

## 1. Target Architecture (replaces LLM-first)

```
User Prompt
   ↓
[1] Guardrail (fail-closed) ..................... LLM, schema-checked
   ↓
[2] Planner .................................... LLM → machine plan (year, parties, pivot event)
   ↓
[3] Baseline Resolver (DB) .................... Cliopatria + WHG + Wikidata
       → polity@year → historical admin units + control raster
   ↓
[4] Feasibility / Cost-Surface Engine .......... DETERMINISTIC (terrain + routes + pop)
       → movement-cost raster around each core
   ↓
[5] Option Space Generator ..................... DETERMINISTIC
       → enumerates plausible territorial moves (adjacent units only)
   ↓
[6] Scorer (Realistic vs Optimistic) ........... DETERMINISTIC weighting
       → ranks options by logistic/political feasibility
   ↓
[7] LLM Selector ............................... LLM picks index from ranked set
       → realistic = low momentum; optimistic = high momentum
   ↓
[8] LLM Narrative Generator ................... LLM writes story for chosen geometry
   ↓
[9] Geometry Assembler (Shapely) .............. DETERMINISTIC, fed validated units
   ↓
[10] Continuity Validator + HAS score ......... DETERMINISTIC gate (label, not block)
   ↓
Map Render
```

**Key inversion:** The LLM never *invents* a border. It *selects* from a
deterministic option space and *narrates* the choice. Realistic vs optimistic is a
**parameter of the scorer** (momentum weight), not a different LLM persona.

---

## 2. Datasets — Source of Truth

### Authoritative at runtime (keep / strengthen)
| Dataset | Role in v2 |
|---|---|
| **Cliopatria** (`cliopatria_polities_only.geojson`, 158 MB) | Baseline polity geometry, `FromYear`/`ToYear` |
| **WHG cache** (`data/whg_cache/*.json`, time-varying `geoms` + `timespans`) | Time-indexed place geometry (already cached — promote to first-class) |
| **Natural Earth** (countries/provinces/rivers/lakes) | Modern reference + physical geography |
| **OSM** (rivers, defiles, roads) | Authoritative physical features for hydrology/route graph |
| **Wikidata** (via queries) | Polity metadata: capital, predecessor, dissolution, alliances |
| **HydroSHEDS / GTOPO30** (add) | Elevation → terrain cost model |
| **Campaign/conflict datasets** (add) | Feasibility of "did X reach Y" |

### Supplemental (calibration only)
GeoBoundaries, OpenHistoricalMap, Pleiades, historical atlases.

### Recommended new datasets (highest impact)
1. **Era-specific administrative units** (Roman provinces, Ottoman vilayets, French
   départements 1789) — kills the "modern Turkey" error by reasoning in historical units.
2. **Route network graph** (ORBIS for Rome, OSM roads for modern, caravan paths) —
   backbone of the logistics constraint.
3. **Historical population grid** (HYDE / GPW-historical) — demographic + supply constraint.
4. **Treaty/border corpus** (for partition mode) — structured from Wikisource.

---

## 3. Knowledge Representation

**Layered hybrid (not a single representation):**

- **Polygon (space-time)** = rendered leaf. From Cliopatria/WHG.
- **Historical admin-unit graph** = reasoning substrate. Resolves "Anatolia not Turkey".
- **Relational graph** (Wikidata + ORBIS) = constraints: adjacent / at_war / allied /
  controls / supplies.
- **Control-probability raster** = only for the optimistic frontier (soft control).
- **Time-indexed polity graph:** `Polity(year) —[adjacent]→ Polity(year)`,
  `Polity —[controls]→ AdminUnit(year)`.

This directly fixes "modern borders instead of historical regions": the generator
chooses among *historical admin units* from the graph, never modern countries.

---

## 4. Historical Constraints (deterministic, never LLM)

**Hard (code-enforced):**
- Adjacency/contiguity: conquest extends from an owned unit (no leapfrog).
- River crossing requires ford/bridge/port in route graph OR naval capability.
- Mountain passage costs N× movement; below threshold → blocked.
- Supply-line limit = f(route-network density, naval reach) from cost surface.
- Naval superiority gates overseas/island conquest.
- Capital capture = discrete event with defined consequences (from campaign data).
- Admin-unit integrity: never return a modern country when a historical unit exists.

**Soft (weighted in scorer, not blocked):**
- Religion/ethnic match → assimilation probability (deterministic lookup).
- Population density → stable-control probability.
- Alliance/succession rules from Wikidata.

**LLM-only:** narrative, tone, timeline storytelling, source synthesis, butterfly effects
(clearly labeled speculative).

---

## 5. AI Usage — Hybrid Division

**Use LLM for:**
- Refining ambiguous prompts (fail-closed guardrail).
- Selecting among pre-computed plausible options (realistic vs optimistic).
- Generating narrative, timeline, butterfly effects.
- Summarizing sources.

**Never use LLM for:**
- Choosing which polygon/province is conquered.
- Deciding border geometry or clip direction.
- Determining contiguity or enclave status.
- Historical fact claims (names, dates, capitals) → from DB.
- Validating its own output.

**Hybrid pattern:** *DB → option space → LLM picks index → geometry assembler executes
index → scorer labels.* The LLM is a **constrained selector + narrator**, not an author
of fact.

---

## 6. Geographic Reasoning — Border Generation

| Method | Verdict |
|---|---|
| Cost-surface contour (terrain + routes + supply) ∩ historical units | **Primary** — border = contour of movement-cost from core |
| Rivers / mountains | Inputs *to* the cost surface, not hardcoded clip instructions |
| Historical frontier (from DB) | Used when available for the pivot year |
| Voronoi / influence zones | Optimistic soft-control rendering only |
| Modern admin boundaries | Reference only; never the output unit pre-1800 |

This eliminates "inconsistent natural boundary interpretation": the boundary *emerges*
from geography, not from an LLM keyword.

---

## 7. Historical Accuracy Score (HAS) — Label, Not Block

A weighted composite, computed **deterministically**, used to **rank and label**, never
to reject a what-if:

```
HAS = w1·BaselineContinuity        (does it extend continuously from polity@year?)
    + w2·LogisticsFeasibility      (claimed extent vs cost-surface reach)
    + w3·MilitaryFeasibility       (force-ratio + terrain vs defended border)
    + w4·PoliticalFeasibility      (alliance/succession consistency)
    + w5·GeographicValidity        (polygon valid, contiguous, no enclaves)
    + w6·EconomicViability         (captured value vs maintenance cost)
    + w7·DemographicStability      (conquered_pop / controller_pop)
```

- **Realistic mode:** higher weight on w2/w3/w5 (frontier stops where cost surface
  steepens).
- **Optimistic mode:** higher weight on pivot-event momentum (frontier rides the
  momentum); same physical model, different parameterization.
- Score is **diagnostic** — shown as "plausibility spread", never as objective truth.
- Gate behavior: only **force human review** if `GeographicValidity < hard_min`
  (invalid polygon / enclave / discontinuity). Political implausibility is allowed.

---

## 8. Phased Implementation Plan

### Phase 1 — Harden & de-LLM the factual layer (highest return, lowest risk)
1. **Fail-closed guardrail** (`prompt_guardrail.py:82`): return `is_valid=False` on
   exception instead of passing the raw prompt. *(Matches PIPELINE_IMPROVEMENT_PLAN §1.)*
2. **Deterministic geometry validation** before any final result: polygon validity,
   contiguity (`unary_union`/`buffer`), enclave detection — replace the LLM anomaly
   checker's authority with Shapely (keep LLM only for *suggesting* fix options).
3. **Add `seed` to `ChatOpenAI`** (`simulation_engine.py:200`) and use
   `sorted(set(...))` in all result-merging blocks → reproducible runs.
4. **Fix the Stage-1-context gap in validation** (`_run_geopolitical_validation`,
   `simulation_engine.py:323`): feed the full accumulated baseline (Stage-1 + historical)
   into the validation prompt, not just the Stage-2 territory list. This fixes the
   Belgium / North Macedonia class of bugs observed in `simulation.log`.
5. **Topological neighbor detection** for natural boundaries: replace
   `line.intersects(country)` with `line.buffer(0.5).intersects(country)` in
   `_process_territory_definitions` (~`simulation_engine.py:2027`) so border-hugging
   countries (Belgium) are included.
6. **Remove dead code:** `_get_active_model` (`sim:146`), `import httpx` (`sim:5`),
   `contested_union` dead computation (`sim:2394`), duplicate schemas in
   `models/schemas.py`.

### Phase 2 — Historical-region resolver (kills "modern Turkey" error)
7. Build a **Baseline Resolver** that, given `polity@year`, returns the set of
   *historical admin units* controlled (from Cliopatria/WHG), not modern countries.
8. Map modern `countries_absorbed` requests to the nearest historical unit for that
   year; reject anachronistic modern-country output pre-1800.
9. Promote `whg_cache/*.json` to a first-class time-indexed geometry source and lazily
   build an in-memory `polity@year → units` index (mirrors `CliopatriaDatabase`).

### Phase 3 — Feasibility / Cost-Surface Engine (kills "ignores logistics")
10. Add a **terrain cost raster** from HydroSHEDS/GTOPO30 (walkable vs mountain).
11. Build a **route/network graph** (OSM roads + ORBIS for antiquity) for supply lines.
12. Implement `compute_reach(core_units, momentum)` → a cost-surface frontier polygon.
    Realistic = low momentum; optimistic = high momentum (same surface).
13. Wire the cost-surface frontier into `_process_territory_definitions` so borders
    follow the surface, not LLM keywords.

### Phase 4 — Option Space Generator + Scorer
14. Enumerate plausible moves as *adjacent historical units* within the cost-surface
    reach (deterministic). Output a ranked list.
15. Implement the HAS scorer (§7). Realistic/optimistic = scorer parameterization.
16. Refactor `_run_conquest_sim` so the LLM receives the ranked option list and returns
    an *index*, not a freeform territory spec.

### Phase 5 — Orchestration & state
17. Wrap the pipeline in **LangGraph** *only as orchestrator* (guardrail → planner →
    baseline → feasibility → options → selector → narrative → assemble → validate).
    Keep all geometry/constraint logic as plain Python nodes (per PIPELINE_IMPROVEMENT_PLAN
    §"Where LangGraph should not be used").
18. Persist sessions/jobs (Redis or on-disk) instead of in-memory `_sessions` /
    `jobs_store`.
19. Store refinement as a separate `refinement_trace` and re-run the full plan-and-
    validate loop after refinement (PIPELINE_IMPROVEMENT_PLAN §6).

### Phase 6 — Long-term modularity (500 BCE → 2025 CE)
20. Introduce **Era Adapters** (Classical/Medieval/Early-Modern/Industrial/Modern),
    each supplying dataset bindings, route graph, and constraint weights. Core engine
    stays era-agnostic.
21. Add regression tests for known scenarios (e.g. Constantinople+Tours from
    `simulation.log`) to lock behavior.

---

## 9. What Stays Stable (contract preservation)

Per `PIPELINE_IMPROVEMENT_PLAN.md`, the following must not break:
- Frontend response schema (`geojson_before/after_realistic/after_optimistic`).
- Job-status polling API (`/api/status/{job_id}`).
- Validation question shape (`ValidationAnomalyQuestion`).
- Territory / GeoJSON output format.
- Leaflet rendering (if result schema stays stable).

---

## 10. Success Criteria

- [ ] Same scenario + same seed → byte-stable geometry across runs.
- [ ] Pre-1800 output never contains a modern country name as a conquered unit.
- [ ] No enclave/disconnected polygon reaches the user without explicit review.
- [ ] Optimistic and realistic share the same baseline and cost surface.
- [ ] Natural-boundary neighbors (e.g. Belgium on the Rhine) are included consistently.
- [ ] Guardrail failure never silently marks invalid input as valid.
- [ ] Every generated territory is traceable to a DB source or a labeled speculation.

---

*This plan preserves the existing frontend/backend contract, extends (not replaces)
`PIPELINE_IMPROVEMENT_PLAN.md`, and shifts the system from "LLM draws maps" to
"DB defines what is possible, LLM selects and narrates what-if outcomes."*
