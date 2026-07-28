# Geopolitico v2 — Antigravity Execution Playbook

How to use this: paste each prompt into a **new Antigravity task** in the order given.
Don't batch multiple numbered items into one task — the 64k output-token cap and shared
mutable state in `simulation_engine.py` make large single-shot edits risky. One task =
one numbered item. Wait for verification before starting the next item in the same
dependency chain.

Model key: **[GEMINI]** = Gemini 3.1 Pro or 3.5 Flash · **[OPUS]** = Claude Opus 4.6
(agentic, but scoped tightly) · **[OPUS-CHAT]** = Opus used in plain chat, not agentic
mode, for a design decision before any code is touched.

---

## 0. One-time setup prompt

Run this first, in its own task, before anything else. It loads context so you don't
have to re-explain the architecture in every subsequent prompt.

```
[GEMINI]
Read SYSTEM_IMPROVEMENT_PLAN.md and the attached technical report in full before doing
anything else. Do not summarize them back to me — just confirm you've read them and are
ready for scoped tasks referencing their section numbers and line numbers.

For the rest of this project: every task I give you will reference specific line
numbers from these documents. Treat backend/tools/cliopatria_loader.py,
backend/tools/country_polygons.py's OVERSEAS_EXCLUSIONS block, and
_process_territory_definitions's merge/subtract ordering as files/blocks you must never
modify unless a task explicitly names them as the target. If a task doesn't explicitly
say to touch one of those, don't — even if it looks related.
```

---

## PHASE 1 — Harden & de-LLM the factual layer

Items 1, 3, 5, 6 touch non-overlapping code and can run as **parallel Manager View
agents**. Item 2 and item 4 should run alone — item 4 touches shared context state and
needs your review before anything downstream depends on it.

### 1. Fail-closed guardrail
```
[GEMINI]
In backend/agents/prompt_guardrail.py, refine_user_prompt() currently returns
is_valid=True with the raw, unrefined prompt when an exception occurs (around line 82).
Change this so that on any exception, it returns is_valid=False with a clear error
message instead of silently passing the raw prompt through.

Do not change the guardrail's LLM call, its temperature, or its success-path return
shape — only the except block's behavior.

After the edit, show me the diff and confirm: does anything downstream in
simulation_engine.py's simulate_start() branch on is_valid? If so, confirm that branch
still handles is_valid=False correctly (i.e. it doesn't crash on the missing refined
prompt).
```

### 2. Add seed + deterministic ordering (run alone)
```
[GEMINI]
Two changes to backend/simulation_engine.py:

1. In the ChatOpenAI constructor around line 200, add a seed parameter (use a fixed
   integer, e.g. 42, or better — thread a seed value through from the request context
   if one exists). Confirm whether the GitHub Models API backend for the model actually
   in use honors seed — if a model in GITHUB_MODELS doesn't support it, tell me which
   ones don't rather than silently ignoring it.
2. Find every place list(set(...)) is used to merge or order results (I count at least
   two blocks, around lines 1614-1629 and 1744-1793 per the technical report — confirm
   exact locations yourself, don't trust my line numbers blindly). Replace with
   sorted(set(...)) so ordering is stable, using an appropriate sort key for each case
   (explain what key you chose for each).

Do not touch _invoke_structured_with_fallback's model-fallback/blacklisting logic —
only the seed parameter and the set-ordering calls.

Show me every location you changed with before/after snippets.
```

### 3. Fix Stage-1 context gap in validation (run alone, high-risk)
```
[OPUS]
backend/simulation_engine.py's _run_geopolitical_validation() (around line 323) only
formats result.model_dump_json() — the Stage-2 territory list — into the validation
prompt. It never sees the accumulated Stage-1 baseline. This is the root cause of the
Belgium-disappearing / North Macedonia-becoming-Albania bug documented in
simulation.log lines 454-504, where countries_absorbed changed from
["Spain","Belgium"] to ["Spain","France"] between stages.

Fix this by feeding the full accumulated baseline (Stage-1 conquered territories +
historical baseline) into the validation prompt alongside the Stage-2 list, so the
validator can see what's already been established and won't silently drop or
contradict it.

Before writing code: walk me through exactly what "full accumulated baseline" should
consist of at this point in the pipeline — trace where Stage-1's resolved territory
list lives in the context dict by the time this function is called, and confirm it's
actually available (not yet overwritten) at line 323. Show me that trace before editing
anything.

Then: check backend/prompts/validation.txt — does its prompt template have a variable
slot for this new baseline data, or does the template itself need a new {baseline}
placeholder? If the template needs changing, show me both the template diff and the
prompt_vars dict change together, since they must stay in sync per the report's
Phase notes.

After the fix, re-run (or walk through manually) the exact Constantinople+Tours
scenario from simulation.log and confirm Belgium is no longer dropped between stages.
```

### 4. Topological neighbor detection for natural boundaries
```
[GEMINI]
In backend/tools/gis_tools.py, natural_boundary_tool's dynamic expansion logic (around
simulation_engine.py lines 2027-2055 per the report — confirm exact location) uses
line.intersects(country_polygon) to detect which countries border a natural boundary
like a river. This misses border-hugging countries like Belgium, whose polygon runs
along the Rhine's centerline without the line technically intersecting it.

Change this to line.buffer(0.5).intersects(country_polygon) — a 0.5-degree buffer
around the boundary line before the intersection test.

Confirm: does this buffer distance introduce any new false positives (countries that
shouldn't be considered adjacent to the boundary but now are, because 0.5 degrees is
too generous)? Check against a couple of known cases — e.g. does this now incorrectly
flag a country like Luxembourg or the Netherlands as bordering the Danube when it
shouldn't.
```

### 5. Remove dead code
```
[GEMINI]
Remove the following confirmed-dead code from backend/simulation_engine.py:
- _get_active_model() (around line 146) — never called anywhere
- import httpx (line 5) — unused
- the contested_union computation around lines 2394-2412 — computed and printed but
  never used in the actual subtraction logic (which uses conqueror_final_geom /
  other_add instead)

Also check backend/models/schemas.py against the engine's own duplicate schema
definitions at lines 49-146 — list which schemas in schemas.py are genuinely unused
(shadowed by the engine's own copies) before deleting anything there. Don't delete
schemas.py content yet, just report what's safe to remove in a follow-up task.

Confirm nothing else in the file references any of the three items above (grep before
deleting) and show me the grep results.
```

### 6. Verification pass for Phase 1
```
[GEMINI]
Run the existing test suite (tests/test_agentic_gis.py and tests/test_interactive.py)
against the current state of the repo after the Phase 1 changes above. Report pass/fail
for each. If test_agentic_gis.py needs a live token and can't run in this environment,
tell me that explicitly rather than skipping silently.

Then re-run the Constantinople+Tours compounding scenario referenced in simulation.log
(or the closest equivalent you can construct from the test files) twice with the same
input, and diff the two output GeoJSON files. Report whether they're now byte-identical.
If not, tell me exactly where they diverge — this will tell us whether the seed fix
actually achieved determinism or whether the model-fallback path is still introducing
variance.
```

---

## PHASE 2 — Historical-region resolver

WHG is removed from this phase entirely — it's a place-gazetteer/reconciliation index,
not a source of administrative hierarchy, and its reconciliation is exactly why
politically-related entities (e.g. Al-Andalus vs. the base Umayyad Caliphate) show up
decoupled. Cliopatria stays, but only for what it actually is: polity-level baseline
geometry, not sub-national administrative units.

The resolver is a **four-tier fallback chain**, tried in order, each tier cheaper/more
grounded than the next:
1. Real traced/authoritative source (DARMC, France Dataverse) — where it exists.
2. Point-based reconstruction: period-attested settlements (Pleiades/Wikidata) bounded
   by Cliopatria's coarse polygon, matched against modern ADM2 districts.
3. LLM-proposed natural boundary: when tier 2 is too sparse to resolve confidently, ask
   the LLM only to *name* a plausible natural frontier (a river, mountain range, desert
   edge) for that historical region — never to draw the border itself — then feed that
   description into the existing natural_boundary_tool for deterministic clipping. This
   mirrors the same "LLM names it, deterministic code executes it" pattern used
   elsewhere in the plan.
4. Explicit "no data available" gap flag → Cliopatria's polity-level geometry, clearly
   labeled coarse.

### 7. Remove WHG integration from the codebase
```
[GEMINI]
Find and remove every reference to the WHG (World Historical Gazetteer) cache in this
codebase — the technical report flags data/whg_cache/*.json and mentions of "promote
whg_cache to a first-class time-indexed geometry source" as the integration points.
Grep for "whg", "WHG", and "whg_cache" across backend/ and show me every hit before
removing anything.

Remove the cache directory reference, any loader/fetch code for it, and any context
dict fields that store WHG results. Do not remove or modify anything related to
Cliopatria (cliopatria_loader.py, cliopatria_polities_only.geojson) — that stays, WHG is
the only thing being removed here.

After removal, confirm nothing downstream still expects a whg field to exist (check for
KeyError risk in any code that reads context.get("whg_...") or similar) and show me
what you found.
```

### 8. Design the four-tier Baseline Resolver (design-first)
```
[OPUS-CHAT]
I want a Baseline Resolver: given a polity name, year, and region, return the set of
historical administrative units (or best available approximation) that polity
controlled — as a four-tier fallback chain, not a single lookup:

Tier 1 — authoritative source: DARMC / Mapping Past Societies (Harvard,
darmc.harvard.edu) for Roman/medieval Europe; French Historical GIS Dataverse
("Department/Region Boundaries in France, c. 1790", DOIs 10.7910/DVN/HJISNR and
10.7910/DVN/BU2SQZ) for French Revolution/Napoleonic scenarios.

Tier 2 — point-based reconstruction: query Pleiades (pleiades.stoa.org, cross-linked to
Wikidata via P1584) for settlements attested in the target polity/period, bounded by
Cliopatria's coarse polygon for that polity/year. Point-in-polygon each settlement
against modern ADM2 (district-level, not province) polygons from geoBoundaries or GADM.
Confidence-tier the hits: >=2 attested settlements in a district = core/confirmed
territory; exactly 1 = weak/edge; 0 but fully enclosed by confirmed neighbors within
the Cliopatria bound = interior fill (don't penalize sparse-but-interior districts,
e.g. desert frontier, the same way as an edge district with zero corroboration);
0 and on/beyond the Cliopatria boundary = excluded. Weight capitals/major cities higher
(Wikidata P1376 "capital of" is a signal). Confirmed/core+interior-fill becomes the
"realistic" geometry; weak/edge becomes "optimistic" — this reuses the pipeline's
existing realistic/optimistic split instead of inventing a new concept.

Tier 3 — LLM-proposed natural boundary (only when tier 2 doesn't resolve confidently,
e.g. too few attested settlements to form a coherent shape): ask the LLM to name a
plausible natural frontier for the region/period (a river, mountain range, or similar
feature) given historical context, then pass that description into the EXISTING
natural_boundary_tool for deterministic clipping. The LLM never proposes coordinates or
draws a shape itself — only names the feature.

Tier 4 — explicit gap: if none of the above resolves, return a clearly-flagged "no
historical unit data available" result, falling back to Cliopatria's raw polity
geometry labeled as coarse.

Propose the exact function signature and return shape for
get_historical_units(polity_name, year, region), including how the tier/confidence
information is surfaced in the return value so downstream code and the frontend can
distinguish "traced," "reconstructed (core)," "reconstructed (edge)," "boundary-inferred,"
and "coarse fallback" from each other. Also tell me how far to build this for the
polities we actually use in test scenarios (Umayyad/Byzantine/Frankish per
simulation.log) versus full coverage, since we don't need every era/region for a
working v1.
```

### 9. Implement Tier 1 — Roman/medieval Europe adapter (DARMC)
```
[GEMINI]
Implement the DARMC-backed branch of get_historical_units() per the design from the
previous task, covering the Roman/medieval Europe era. Download or reference the
relevant DARMC/Mapping Past Societies layer (diocese/archdiocese boundaries or the
closest equivalent to what our test scenarios need — check simulation.log for which
polities/years are actually exercised, starting with the Umayyad Siege of
Constantinople 717 CE scenario) from darmc.harvard.edu, and wire it into
cliopatria_loader.py as a new adapter module, not by modifying CliopatriaDatabase's
existing methods.

Show me a worked example against the Constantinople scenario's year/region and confirm
whether DARMC actually has coverage for it — Byzantine Anatolia specifically may or may
not be in DARMC's Roman/medieval layers, so verify before assuming this closes the
"modern Turkey" bug for that exact scenario.
```

### 10. Implement Tier 1 — French Revolution adapter
```
[GEMINI]
Implement the French Historical GIS Dataverse-backed branch of get_historical_units()
for French Revolution/Napoleonic-era scenarios (1789 onward), using the department/
region boundary datasets named in the design task (task 8). Wire it into the same
adapter pattern as the DARMC branch. Show me a worked example and confirm date-range
handling (this dataset is specifically "c. 1790" — confirm how far forward/backward
from that date it's reasonable to apply it before it becomes wrong).
```

### 11. Implement Tier 2 — point-based reconstruction (Pleiades/Wikidata)
```
[GEMINI]
Implement the point-based reconstruction branch of get_historical_units() per the
design in task 8, using Wikidata's OWN administrative hierarchy instead of an external
ADM2 shapefile join:

1. Query Pleiades for period-attested settlements of the target polity, cross-linking
   to Wikidata via P1584 to get each settlement's Wikidata Q-item.
2. For each Q-item, read P131 ("located in the administrative territorial entity")
   directly off that item. Most archaeological/ancient-site items in Wikidata already
   have this set to their MODERN administrative container (district/province), because
   the physical site sits in a real place today and Wikidata's own community has
   usually already curated that link — this means most sites resolve to a modern
   administrative unit with zero geometry work, just a property read.
   Walk the P131 chain to whatever granularity you need (district vs. province) — note
   P131's inverse is P150 ("contains administrative territorial entity") if you need to
   go the other direction.
3. FALLBACK ONLY: for any settlement whose Wikidata item lacks P131 (this will happen
   for some sites — don't assume 100% coverage), fall back to a point-in-polygon match
   against a modern ADM2 shapefile (geoBoundaries — confirm current download/API access
   before assuming a URL) using the settlement's coordinates (P625 or Pleiades'
   coordinates). Tell me what fraction of settlements in a test query actually need this
   fallback vs. resolve directly via P131 — that tells us whether the shapefile join is
   worth keeping as permanent infrastructure or just an edge-case patch.
4. Bound everything by Cliopatria's coarse polygon for the polity/year, and apply the
   confidence tiering exactly as specified: >=2 settlements resolving to the same modern
   unit = core, 1 = weak/edge, 0-but-enclosed = interior fill, 0-and-on-boundary =
   excluded.

Test this against the Constantinople scenario's Byzantine Anatolia case (especially if
task 9 found DARMC doesn't cover it) and show me the resulting core/edge/interior-fill
breakdown, AND show me how many settlements resolved via P131 directly vs. needed the
shapefile fallback. If the "holes in sparse regions" problem shows up despite the
interior-fill rule, tell me honestly rather than presenting a broken result as working.
```

### 12. Implement Tier 3 — LLM-proposed natural boundary fallback, with direction cross-checked against the baseline
```
[GEMINI]
Implement the tier-3 fallback: when tier 2's point-based reconstruction doesn't resolve
confidently (define "doesn't resolve confidently" concretely — e.g. fewer than N
attested settlements found, or the resulting shape fails a basic coherence check), do
the following instead of a single unchecked LLM call:

1. Call the LLM with ONLY the historical polity/period/region context and ask it to
   propose BOTH a plausible natural frontier feature (river, mountain range, coastline,
   desert edge) AND a direction relative to that feature, using the same enum the
   codebase already has for this (clip_direction: north/south/east/west_of_natural_
   boundary — check force_conquest_provinces and the partial_countries schema for the
   exact existing values, reuse them rather than inventing new ones). Constrain the
   output schema so it can only return a feature name and a direction enum value —
   never coordinates or a boundary shape.

2. Before trusting the LLM's direction: take Cliopatria's own core baseline geometry
   for that polity (the certain heartland portion, not any disputed/extended area) and
   deterministically compute which side of the named feature that core baseline
   actually sits on (e.g. is its centroid/majority area north or south of the named
   river). This is a geometry check, not an LLM call.

3. Compare the two: if the LLM's proposed direction matches the deterministically
   computed direction, proceed — feed the feature + the GEOMETRY-DERIVED direction (not
   necessarily the LLM's, even if they matched) into the existing natural_boundary_tool
   exactly as a normal scenario's river-boundary description would be used. If they
   DISAGREE, log the mismatch clearly (this usually means the LLM proposed a
   geographically wrong frontier) and either retry once with the geometry-derived
   direction stated explicitly, or fall through to tier 4 if natural_boundary_tool still
   can't resolve the named feature at all.

Show me this working end-to-end on a case where tier 2 is expected to be weak (a sparse
frontier region), including at least one deliberately-provoked mismatch case if you can
construct one, to confirm the geometry check actually catches a wrong LLM direction
rather than just rubber-stamping it.
```

### 13. Wire the final tier-4 gap flag
```
[GEMINI]
Implement tier 4: when tiers 1-3 all fail to resolve, return the explicit "no
historical unit data available" result designed in task 8, and wire it into
_process_territory_definitions so the pipeline falls back to Cliopatria's raw polity
geometry with a clearly labeled "coarse baseline" flag — never silently absorbing a
modern country name.

Show me the diff, and confirm: for a test scenario where you can force all three
earlier tiers to fail (or use an Ottoman-era example, which has none of tier 1-2's
sources), does the output now clearly show the coarse-fallback flag instead of silently
producing a modern-country result?
```

---

## PHASE 2.5 — Scenario Type Classifier & Router

This generalizes the demographic/proposal/military-counterfactual pattern into one
routing stage instead of special-casing each scenario. It sits right after the existing
Planner LLM step (`PlanningResult`) and decides which resolver chain a scenario uses,
in priority order: `named_proposal` (cheapest, most grounded — a real document already
specifies terms) → `military_counterfactual` → `demographic_shift` → `generic_conquest`
(current LLM-invention path, now the lowest-priority fallback instead of the default).

### 14. Design and implement the Scenario Classifier
```
[GEMINI]
Add a new classifier step to backend/simulation_engine.py's pipeline, right after the
existing PlanningResult LLM call in simulate_start(). It should be a new schema-checked
LLM call (same pattern as _invoke_structured_with_fallback) using this system prompt —
save it as backend/prompts/scenario_classifier.txt:

---
You are a scenario classifier for an alternate-history simulator. Classify the user's
scenario into exactly one primary type and extract its parameters. Do not invent
geometry or historical facts yourself — only classify and extract.

TYPES (in resolution priority order):

1. named_proposal — references a specific real historical proposal, formula, plan,
   draft treaty, or rejected boundary-commission recommendation.
   Extract: proposal_name, context/conflict, approximate_year.

2. military_counterfactual — proposes a different outcome to a specific historical
   war, battle, or siege.
   Extract: conflict_name, historical_loser_as_winner (or vice versa), year_or_period.

3. demographic_shift — proposes a different population/ethnic/religious composition
   for a region at a point in time, without a war-driven border change.
   Extract: region, year, group, proposed_percentage_or_ratio.

4. generic_conquest — none of the above apply; no documented real-world proposal or
   composition claim exists to ground the scenario.
   Extract whatever entities/regions/years are given.

Output: primary_type, extracted parameters, and a confidence score. If genuinely
ambiguous between two types, name both in priority order.
---

Define a new Pydantic schema (ScenarioClassification) matching this output shape,
following the existing pattern of PlanningResult/SequentialScenarioPlan. Wire the
classification result into the context dict as context["scenario_type"] and
context["scenario_params"]. Do NOT change simulation_mode or the existing
expansion_conquest/compounding_conquest/proposal_partition/demographic_shift mode
branch yet — this task only adds the classification, not the routing. Show me the
schema, the prompt file, and where you inserted the call.
```

### 15. Named-proposal resolver (reuses existing natural_boundary_tool)
```
[GEMINI]
When context["scenario_type"] == "named_proposal", add a resolver step before
_run_final_simulation's normal GIS enrichment: given proposal_name and context/conflict
from the classifier, search (web search or a provided document) for a textual
description of the proposal's boundary — most historical partition/boundary proposals
describe their line in terms of rivers or named regions (e.g. "along the Chenab river").

Extract that description and feed it into the EXISTING natural_boundary_tool the same
way a normal river-boundary scenario would use it — do not build new boundary-clipping
logic, reuse what's there. If no textual boundary description can be found for the
named proposal, fall through to generic_conquest and log that the fallback occurred —
don't silently invent a boundary.

Show me this working against "Chenab Formula, Punjab, 1947" as a test case: what
description did you find, and what did natural_boundary_tool produce from it?
```

### 16. Demographic-shift resolver with real-data interpolation
```
[GEMINI]
When context["scenario_type"] == "demographic_shift" and the region/year matches
British India / Partition-era Punjab or Bengal, implement this pipeline (not a single
LLM guess):

1. get_census_composition(region, year, group): look up real district-level religious
   composition from the 1941 Census of India (the Bharadwaj/Khwaja/Mian Partition-
   economics replication dataset is the citable public source — find and confirm the
   current download location before wiring it in, don't assume a URL). Return a
   per-district table of real historical percentages. If no data exists for the
   region/year, return the same explicit gap-flag pattern used elsewhere — never fall
   back to an LLM guess without flagging it as such.

2. Given the user's target aggregate percentage (e.g. "60% Muslim" for the whole
   region) and the real per-district table, run a DETERMINISTIC search (greedy or
   simple combinatorial) over subsets of real districts to find the 2-3 combinations
   whose combined population comes closest to the target percentage. Do not let the LLM
   invent numbers here — the district-level percentages are real, only the *selection*
   of which districts compose the hypothetical region is being chosen.

3. Pass those 2-3 candidate district-combinations to the LLM ONLY to pick between them
   and narrate a plausible historical mechanism (e.g. migration pattern, a different
   boundary-commission decision) — a constrained selector over real deterministic
   options, same pattern as the rest of the plan. The LLM should prefer geographically
   contiguous combinations when candidates are close in numeric fit, and should say so
   in its narration.

Show me this working against "what if Muslims were 60% of Punjab's population at
Partition": what real per-district numbers did you find, what candidate combinations
did the deterministic search produce, and what did the LLM select?
```

---

## PHASE 3 (scoped) — Feasibility check for military counterfactuals only

This replaces the original Phase 3 (terrain cost-surface + route graph + HydroSHEDS/
ORBIS spanning 500 BCE-2025 CE) with something much smaller, because the classifier
above already routes `named_proposal` and `demographic_shift` scenarios away from
needing any feasibility modeling at all. What's left only needs grounding, not a
logistics simulator: real documented war aims as the target, real pre-war boundaries as
the floor, and a plausibility check reusing code you already have.

### 17. Grounded targets for military_counterfactual
```
[GEMINI]
When context["scenario_type"] == "military_counterfactual", resolve two real anchors
instead of letting the LLM invent territory:
1. "Realistic" floor = the actual historical pre-war boundary of the counterfactual
   winner, for the stated year — pull this from Cliopatria/Natural Earth exactly as the
   pipeline already does for normal scenarios, no new code needed here.
2. "Optimistic" target = the counterfactual winner's actual documented war aims or
   maximalist territorial claims for that conflict (search Wikipedia's
   "aftermath"/"territorial claims" sections or the relevant treaty text on Wikisource —
   e.g. for the Balkan Wars, the Treaty of London 1913 and Treaty of Bucharest 1913 both
   have real, findable boundary descriptions).

Feed both into the existing _run_conquest_sim flow as pre-resolved geometry rather than
letting the realistic/optimistic LLM calls invent borders for this scenario type. Show
me this working against a Balkan Wars test case: what pre-war boundary and what
documented claim did you find, and do they produce sane, non-overlapping geometry
through the existing Shapely assembly?
```

### 18. Lightweight plausibility check (not a cost-surface engine)
```
[GEMINI]
Add one plausibility check for military_counterfactual scenarios, reusing code that
already exists rather than building new infrastructure:
1. Contiguity: reuse the enclave-detection Shapely logic from
   _check_geopolitical_anomalies to confirm the documented war-aims target territory
   (from the previous task) is actually adjacent to the winner's real pre-war holdings.
   Flag, don't block, if it isn't — some real historical claims genuinely included
   non-contiguous territory.
2. Duration/scale sanity flag: look up the conflict's actual historical duration (a
   simple manual lookup or a small hardcoded table for the conflicts we actually test
   against, not a new dataset integration) and flag if the claimed territorial change is
   large relative to how short the conflict was — advisory only, never a hard block on
   the output.

This is explicitly NOT the terrain/route/cost-surface engine from the original plan —
do not add HydroSHEDS, ORBIS, or any new geographic dataset for this. Show me the diff
and confirm both checks are advisory flags on the output, not gates that can silently
drop or block a result.
```

---

## PHASE 5 (scoped) — LangGraph orchestration

The classifier's four-way branch is the actual trigger for wrapping this in LangGraph
now — a plain if/elif chain across four resolver paths plus the existing mode branches
gets unwieldy fast, and LangGraph's conditional edges are a genuine fit for exactly this
shape. Per the original plan's own principle: LangGraph is the orchestrator only, every
node just calls a plain Python/LLM function you already built in Phases 1-3 — no new
decision logic lives inside the graph itself.

### 19. Design the LangGraph state schema and graph structure (design-first)
```
[OPUS-CHAT]
I want to wrap the existing pipeline in LangGraph as a pure orchestrator, replacing the
imperative call chain in simulate_start()/simulate_verify()/simulate_step() without
changing any of the underlying logic built in Phases 1-3.

Propose a LangGraph StateGraph design:
- A TypedDict state schema carrying everything currently in the `context` dict (session
  id, scenario, year, parties, baseline_polities, scenario_type, scenario_params,
  resolved territories, results, anomalies, etc.) — don't lose any existing field.
- Nodes: guardrail -> planner -> scenario_classifier -> [conditional branch] ->
  {named_proposal_resolver, military_counterfactual_resolver, demographic_resolver,
  generic_conquest (existing LLM path)} -> merge -> geometry_assembler -> validator ->
  anomaly_checker -> end. Each node should be a thin wrapper calling an existing
  function (refine_user_prompt, the PlanningResult call, the classifier from task 14,
  each resolver from tasks 15/16/17-18, _process_territory_definitions,
  _run_geopolitical_validation, _check_geopolitical_anomalies) — no logic duplicated
  inside the node itself.
- The conditional edge after scenario_classifier should route on context["scenario_type"]
  exactly as designed in task 14.
- Tell me how simulate_verify()'s human-in-the-loop anomaly resolution step and
  simulate_step()'s refinement loop fit into this graph — as a resumable checkpoint, or
  as a separate re-invocation of the graph from a given node? I want a decision on this
  before implementation, since it affects whether _sessions needs to become
  LangGraph's own checkpointing mechanism or stay as-is for now.

Do not include session/job persistence (Redis, on-disk) in this design — that's a
separate concern from orchestration and stays deferred. This task is scoped to the
graph structure only.
```

### 20. Implement the LangGraph wrapper
```
[GEMINI]
Implement the LangGraph StateGraph per the design from the previous task. Wire each
node to call the existing function it wraps — do not reimplement any logic from
Phases 1-3 inside a node. Preserve the existing API contract exactly: main.py's
/api/simulate, /api/simulate/verify, /api/status/{job_id} endpoints and their request/
response shapes must not change (per SYSTEM_IMPROVEMENT_PLAN.md section 9, "What Stays
Stable").

Show me the graph definition, confirm every existing field from the old context dict
is present in the new state schema, and re-run the Constantinople+Tours scenario from
simulation.log through the new graph-based flow — confirm it produces the same output
as the pre-LangGraph pipeline (modulo the Phase 2/2.5/3 improvements already made on
top of it).
```

---

## STOP HERE — everything past this remains deferred

The original Phase 3's full terrain-cost-surface/route-graph engine, the HAS scorer,
and 500 BCE-2025 CE era adapters beyond what's built in Phase 2 are still not
scheduled. Session/job persistence (Redis or on-disk) is also still deferred — it's a
separate concern from orchestration. If a future scenario type genuinely needs full
logistics modeling (a generic_conquest case where no documented anchor of any kind
exists), treat that as a one-off [OPUS-CHAT] scoping conversation when it actually
comes up, not upfront infrastructure.

---

## Execution order summary

| Order | Item | Model | Can parallelize with |
|---|---|---|---|
| 0 | Setup | Gemini | — |
| 1 | Fail-closed guardrail | Gemini | 3, 5 |
| 2 | Seed + sorted(set()) | Gemini | alone |
| 3 | Stage-1 validation context | Opus | 1, 5 |
| 4 | Topological buffer fix | Gemini | 1, 3 |
| 5 | Dead code removal | Gemini | 1, 3, 4 |
| 6 | Phase 1 verification | Gemini | after 1-5 complete |
| 7 | Remove WHG from codebase | Gemini | after Phase 1 |
| 8 | Baseline Resolver design (4-tier chain) | Opus-chat | after 7 |
| 9 | Tier 1 — DARMC adapter | Gemini | after 8 |
| 10 | Tier 1 — French Revolution adapter | Gemini | after 8, parallel with 9 |
| 11 | Tier 2 — point-based reconstruction (Pleiades/Wikidata) | Gemini | after 9, 10 |
| 12 | Tier 3 — LLM natural-boundary fallback | Gemini | after 11 |
| 13 | Tier 4 — gap flag wiring | Gemini | after 12 |
| 14 | Scenario classifier | Gemini | after Phase 2 complete |
| 15 | Named-proposal resolver | Gemini | after 14 |
| 16 | Demographic-shift resolver + interpolation | Gemini | after 14, parallel with 15 |
| 17 | Grounded targets for military_counterfactual | Gemini | after 14 |
| 18 | Lightweight plausibility check | Gemini | after 17 |
| 19 | LangGraph design | Opus-chat | after 13, 16, 18 all verified |
| 20 | LangGraph implementation | Gemini | after 19 |

**Stop and reassess after item 20.** Confirm the classifier routes your test scenarios
correctly (Chenab Formula -> named_proposal, Balkan Wars -> military_counterfactual,
Partition composition -> demographic_shift), confirm the graph-based flow reproduces
the pre-LangGraph output on the Constantinople+Tours test case, and only then consider
anything beyond this scope — full logistics modeling, session persistence, or broader
era coverage.

Rough credit discipline: everything in Phase 1, 2, 2.5, and scoped Phase 3/5's
implementation steps should stay on Gemini. Reserve Opus specifically for item 3
(shared-state bug, highest risk) and items 8 and 19 (design conversations) — those
remain the places a wrong answer costs you the most rework.
