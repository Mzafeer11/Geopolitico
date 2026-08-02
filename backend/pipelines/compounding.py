"""
Compounding conquest pipeline module for Geopolitico simulation engine.
Executes multi-stage sequential counterfactual conflicts (e.g., Stage 1: Constantinople -> Stage 2: Tours).
"""

from typing import Dict, Any, Optional, Tuple
from backend.pipelines.conquest import run_conquest_sim
from backend.helpers.result_builder import build_conquest_summary_str


def run_compounding_conquest(
    scenario: str,
    year: int,
    context: Dict[str, Any],
    answers: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, Any], Any, Any, Any, Any]:
    """Execute multi-stage compounding conquest simulation across two sequential historical events."""
    plan_dict = context.get("compounding_plan")
    if not plan_dict:
        raise ValueError("Compounding plan is missing from context.")
        
    scenario_1 = plan_dict["scenario_1"]
    year_1 = plan_dict["year_1"]
    scenario_2 = plan_dict["scenario_2"]
    year_2 = plan_dict["year_2"]
    
    parties_list = context.get("parties", [])
    winner_name = parties_list[0] if parties_list else context.get("baseline_polities", ["Umayyad Caliphate"])[0]

    # --- STAGE 1 (First Event) ---
    print(f"[SIMULATOR] --- STAGE 1: Simulating first event '{scenario_1}' at {year_1} ---", flush=True)
    
    context_1 = dict(context)
    context_1["year"] = year_1
    context_1["scenario"] = scenario_1
    context_1["simulation_mode"] = "expansion_conquest"
    
    resolved_real_1 = {}
    resolved_opt_1 = {}
    context_1["compounding_resolved_geoms_real"] = resolved_real_1
    context_1["compounding_resolved_geoms_opt"] = resolved_opt_1
    res_real_1, res_opt_1, realistic_features_1, optimistic_features_1 = run_conquest_sim(
        scenario_1, year_1, context_1, stage_num=1, answers=answers
    )
    
    # Synchronize conqueror territory names to enable continuous geometric union across stages
    for t in res_real_1.territories + res_opt_1.territories:
        if winner_name.lower() in t.name.lower() or "umayyad" in t.name.lower():
            t.name = winner_name

    # Union winner's full 732 AD baseline geometry (Spain + North Africa + Middle East) into Stage 1 resolved shapes
    from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
    winner_sh_732, _, _ = _get_resolved_baseline_geometry(winner_name, year_2, context.get("target_region", ""))
    if winner_sh_732 and not winner_sh_732.is_empty:
        for r_dict in [resolved_real_1, resolved_opt_1]:
            if winner_name in r_dict and r_dict[winner_name] is not None:
                r_dict[winner_name] = winner_sh_732.union(r_dict[winner_name])
            else:
                r_dict[winner_name] = winner_sh_732

    real_conquests_str_1 = build_conquest_summary_str(res_real_1.territories)
    opt_conquests_str_1 = build_conquest_summary_str(res_opt_1.territories)
    
    # --- STAGE 2 (Second Event) ---
    print(f"[SIMULATOR] --- STAGE 2: Simulating second event '{scenario_2}' at {year_2} ---", flush=True)
    
    context_2 = dict(context)
    context_2["year"] = year_2
    context_2["scenario"] = scenario_2
    context_2["simulation_mode"] = "expansion_conquest"
    context_2["stage1_real_conquests_str"] = real_conquests_str_1
    context_2["stage1_opt_conquests_str"] = opt_conquests_str_1
    
    context["compounding_baselines_real"] = resolved_real_1
    context["compounding_baselines_opt"] = resolved_opt_1
    
    res_real_2, res_opt_2, realistic_features_2, optimistic_features_2 = run_conquest_sim(
        scenario_2, year_2, context_2, stage_num=2,
        baselines_override_real=resolved_real_1,
        baselines_override_opt=resolved_opt_1,
        answers=answers
    )
    
    # Synchronize conqueror territory names for Stage 2
    for t in res_real_2.territories + res_opt_2.territories:
        if winner_name.lower() in t.name.lower() or "umayyad" in t.name.lower():
            t.name = winner_name

    compounding_results = {}
    compounding_results["title"] = f"{res_real_1.title} & {res_real_2.title}"
    compounding_results["alternate_outcome"] = (
        f"Stage 1 ({year_1} AD - Realistic): {res_real_1.alternate_outcome}\n"
        f"Stage 2 ({year_2} AD - Realistic): {res_real_2.alternate_outcome}\n\n"
        f"Stage 1 ({year_1} AD - Optimistic): {res_opt_1.alternate_outcome}\n"
        f"Stage 2 ({year_2} AD - Optimistic): {res_opt_2.alternate_outcome}"
    )
    compounding_results["alternate_outcome_realistic"] = (
        f"Stage 1 ({year_1} AD): {res_real_1.alternate_outcome}\n\n"
        f"Stage 2 ({year_2} AD): {res_real_2.alternate_outcome}"
    )
    compounding_results["alternate_outcome_optimistic"] = (
        f"Stage 1 ({year_1} AD): {res_opt_1.alternate_outcome}\n\n"
        f"Stage 2 ({year_2} AD): {res_opt_2.alternate_outcome}"
    )
    compounding_results["key_changes"] = sorted(set(res_real_1.key_changes + res_opt_1.key_changes + res_real_2.key_changes + res_opt_2.key_changes))
    compounding_results["realistic_scenario_summary"] = "Compounded realistic sequential outcomes with moral momentum."
    compounding_results["optimistic_scenario_summary"] = "Maximum compounded territorial expansion across all theatres."
    
    compounding_results["butterfly_effects"] = sorted(set(res_real_1.butterfly_effects + res_opt_1.butterfly_effects + res_real_2.butterfly_effects + res_opt_2.butterfly_effects))
    compounding_results["sources"] = sorted(set(res_real_1.sources + res_opt_1.sources + res_real_2.sources + res_opt_2.sources))
    
    seen_t = set()
    combined_timeline = []
    for t in res_real_1.timeline + res_opt_1.timeline + res_real_2.timeline + res_opt_2.timeline:
        val = f"{t.year}:{t.event}"
        if val not in seen_t:
            seen_t.add(val)
            combined_timeline.append(t.model_dump())
    compounding_results["timeline"] = sorted(combined_timeline, key=lambda x: x["year"])
    
    # Stage 2 features ALREADY contain the single Unified MultiPolygon of Stage 1 + Stage 2 + Baseline!
    compounding_results["geojson_after_realistic"] = {
        "type": "FeatureCollection",
        "features": realistic_features_2
    }
    compounding_results["geojson_after_optimistic"] = {
        "type": "FeatureCollection",
        "features": optimistic_features_2
    }
    compounding_results["territories_after_realistic"] = [t.model_dump() for t in res_real_2.territories]
    compounding_results["territories_after_optimistic"] = [t.model_dump() for t in res_opt_2.territories]

    return compounding_results, res_real_2, res_opt_2, realistic_features_2, optimistic_features_2


def run_compounding_stage1(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute compounding stage 1 and stage 2 pipeline."""
    plan_dict = state.get("compounding_plan") or {}
    year_2 = plan_dict.get("year_2", state.get("year", 732))
    
    comp_results, res_real_2, res_opt_2, realistic_features_2, optimistic_features_2 = run_compounding_conquest(
        state["scenario"], state["year"], state
    )
    return {
        "results": comp_results,
        "res_real": res_real_2.model_dump(),
        "res_opt": res_opt_2.model_dump(),
        "realistic_features": realistic_features_2,
        "optimistic_features": optimistic_features_2,
        "year": year_2
    }


def run_compounding_stage2(state: Dict[str, Any]) -> Dict[str, Any]:
    """Compounding stage 2 pass-through."""
    return {"results": state.get("results", {})}
