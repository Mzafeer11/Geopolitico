"""
Graph node wrapper functions for Geopolitico LangGraph orchestrator.
Each node is a thin wrapper calling underlying tools or pipelines.
"""

from typing import Dict, Any, List
from langchain_core.messages import SystemMessage

from backend.models.schemas import PlanningResult, SequentialScenarioPlan, ScenarioStateResult, PartialRegion, SplitProvince
from backend.agents.prompt_guardrail import refine_user_prompt
from backend.helpers.llm import invoke_structured_with_fallback
from backend.helpers.validation import run_geopolitical_validation, check_geopolitical_anomalies
from backend.helpers.result_builder import build_common_results
from backend.tools.compiler import process_territory_definitions
from backend.tools.gis_tools import find_contested_provinces
from backend.helpers.prompt_loader import _load_prompt_template
from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
from backend.pipelines.conquest import run_conquest_sim
from backend.pipelines.compounding import run_compounding_stage1, run_compounding_stage2
from backend.pipelines.partition import run_partition_sim
from backend.pipelines.demographic import run_demographic_simulation


def guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 1: User prompt verification & refinement guardrail."""
    original_scenario = state.get("scenario") or state.get("raw_scenario", "")
    refined = refine_user_prompt(original_scenario)
    if isinstance(refined, dict):
        refined_str = refined.get("refined_prompt", original_scenario)
    elif isinstance(refined, str):
        if refined.startswith("{") and "refined_prompt" in refined:
            try:
                import json
                d = json.loads(refined)
                refined_str = d.get("refined_prompt", original_scenario)
            except Exception:
                refined_str = refined
        else:
            refined_str = refined
    else:
        refined_str = str(refined)
        
    print(f"[SIMULATOR-GRAPH] Guardrail Refinement: original='{original_scenario}' -> refined='{refined_str}'", flush=True)
    return {"scenario": refined_str, "original_scenario": original_scenario}


def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 2: Scenario classification & structured planning node."""
    scenario = state["scenario"]
    template = _load_prompt_template("planning.txt")
    prompt = template.format(scenario=scenario) if template else f"Classify: {scenario}"
    
    res: PlanningResult = invoke_structured_with_fallback(PlanningResult, [SystemMessage(content=prompt)], temperature=0.3)
    
    return {
        "year": res.year,
        "parties": res.parties,
        "baseline_polities": res.baseline_polities,
        "simulation_mode": res.simulation_mode,
        "target_region": res.target_region,
        "target_countries": res.target_countries,
        "baseline_description": res.baseline_description,
        "planning_result": res.model_dump()
    }


def demographic_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 3: Demographic shift simulation pipeline."""
    return run_demographic_simulation(state)


def compound_splitter_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 4: Sequential compounding scenario plan parser."""
    scenario = state["scenario"]
    template = _load_prompt_template("sequential_compounding_plan.txt")
    prompt = template.format(scenario=scenario) if template else f"Split compounding: {scenario}"
    
    plan: SequentialScenarioPlan = invoke_structured_with_fallback(SequentialScenarioPlan, [SystemMessage(content=prompt)], temperature=0.3)
    
    return {
        "compounding_plan": plan.model_dump(),
        "scenario_1": plan.scenario_1,
        "scenario_2": plan.scenario_2,
        "base_year": plan.base_year,
        "timeline_span": plan.timeline_span,
        "compounding_narrative": plan.compounding_narrative
    }


def shared_preprocess_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 5: Preprocess baseline geometries and contested provinces."""
    scenario = state["scenario"]
    year = state["year"]
    parties = state.get("parties", [])
    target_region = state.get("target_region", "")
    target_countries = state.get("target_countries", [])
    simulation_mode = state.get("simulation_mode", "expansion_conquest")
    all_baseline_polities = state.get("baseline_polities", parties)
    
    contested = find_contested_provinces(all_baseline_polities, year, target_countries, is_partition=(simulation_mode == "proposal_partition"))
    prompt_contested = ", ".join(contested[:12]) if contested else "regional borders"
    
    features_before_coarse = []
    features_provinces = []
    
    for bp in all_baseline_polities:
        sh, feat_dict, tier = _get_resolved_baseline_geometry(bp, year, target_region)
        if sh is not None and not sh.is_empty:
            if feat_dict:
                coarse_feat = {
                    "type": "Feature",
                    "geometry": feat_dict["geometry"],
                    "properties": {
                        **feat_dict.get("properties", {}),
                        "Name": bp, "name": bp,
                        "FromYear": year, "ToYear": year, "year": year,
                        "tier": tier,
                        "is_outer_border": True,
                        "color": "#4b5563", "fill_color": "#4b5563"
                    }
                }
                features_before_coarse.append(coarse_feat)
                
                sub_feats = feat_dict.get("properties", {}).get("sub_province_features", [])
                if sub_feats:
                    features_provinces.extend(sub_feats)
                else:
                    features_provinces.append(coarse_feat)
            else:
                from shapely.geometry import mapping
                coarse_feat = {
                    "type": "Feature",
                    "geometry": mapping(sh),
                    "properties": {
                        "Name": bp, "name": bp,
                        "FromYear": year, "ToYear": year, "year": year,
                        "color": "#4b5563", "fill": "#4b5563", "fillOpacity": 0.45,
                        "stroke": "#1f2937", "strokeWidth": 1.5,
                        "is_outer_border": True
                    }
                }
                features_before_coarse.append(coarse_feat)
                features_provinces.append(coarse_feat)

    geojson_before = {
        "type": "FeatureCollection",
        "features": features_before_coarse
    }
    
    geojson_provinces = {
        "type": "FeatureCollection",
        "features": features_provinces
    }
    
    gis_context = ""
    osm_boundaries = {}
    
    if simulation_mode == "proposal_partition":
        try:
            from backend.tools.gis_tools import get_natural_boundary_geometry
            river_geom, river_paths = get_natural_boundary_geometry("Chenab River", "Kashmir")
            if river_paths:
                osm_boundaries["Chenab River"] = river_paths
                gis_context = f"\nNATURAL BOUNDARY GEOMETRY LOADED: Chenab River (Kashmir) with {len(river_paths)} vector segments."
        except Exception as e:
            print(f"[WARN] Failed to load GIS boundary geometry: {e}", flush=True)
            
    units_ownership_map = {}
    if year < 1800 and simulation_mode == "expansion_conquest":
        try:
            from backend.tools.baseline_resolver import get_historical_units
            for bp in all_baseline_polities:
                h_res = get_historical_units(bp, year, target_region)
                units_ownership_map[bp] = list(h_res.get("historical_units_map", {}).keys())
        except Exception as e:
            print(f"[WARN] Preprocessing historical units failed: {e}", flush=True)

    return {
        "contested_provinces": contested,
        "prompt_contested": prompt_contested,
        "geojson_before": geojson_before,
        "geojson_provinces": geojson_provinces,
        "gis_context": gis_context,
        "osm_boundaries": osm_boundaries,
        "baseline_units_map": units_ownership_map
    }


def ownership_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 6: Territorial ownership analysis across baseline polities."""
    scenario = state["scenario"]
    year = state["year"]
    parties = state.get("parties", [])
    prompt_contested = state.get("prompt_contested", "")
    
    template = _load_prompt_template("baseline_ownership.txt")
    prompt = template.format(
        scenario=scenario,
        year=year,
        parties=", ".join(parties),
        contested_provinces=prompt_contested
    ) if template else f"Baseline ownership: {scenario}"
    
    class OwnershipResult:
        def __init__(self, summary: str):
            self.summary = summary
            
    try:
        from pydantic import BaseModel
        class OwnershipSchema(BaseModel):
            ownership_summary: str
        res = invoke_structured_with_fallback(OwnershipSchema, [SystemMessage(content=prompt)], temperature=0.3)
        summary = res.ownership_summary
    except Exception:
        summary = f"Baseline territorial configuration for {', '.join(parties)} in {year} AD."
        
    return {"ownership_str": summary}


def partition_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 8: Treaty partition simulation pipeline wrapper."""
    scenario = state["scenario"]
    year = state["year"]
    return run_partition_sim(scenario, year, state)


def conquest_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 7: Military expansion conquest pipeline execution."""
    scenario = state["scenario"]
    year = state["year"]
    answers = state.get("user_selections")
    
    res_real, res_opt, realistic_features, optimistic_features = run_conquest_sim(scenario, year, state, answers=answers)
    
    return {
        "res_real": res_real.model_dump(),
        "res_opt": res_opt.model_dump(),
        "realistic_features": realistic_features,
        "optimistic_features": optimistic_features
    }


def conquest_stage1_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 9: Sequential compounding Stage 1 execution."""
    return run_compounding_stage1(state)


def conquest_stage2_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 10: Sequential compounding Stage 2 execution."""
    return run_compounding_stage2(state)


def conquest_retry_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 11: Optimistic scenario retry loop."""
    retries = state.get("optimistic_retry_count", 0) + 1
    state["optimistic_retry_count"] = retries
    print(f"[SIMULATOR-GRAPH] Triggering optimistic expansion retry attempt {retries}...", flush=True)
    return conquest_node(state)


def result_assembly_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 13: Response payload compiler."""
    if "results" in state and state["results"]:
        return {"results": state["results"]}
        
    res_real = ScenarioStateResult(**state["res_real"])
    res_opt = ScenarioStateResult(**state["res_opt"])
    
    results = {
        "title": res_real.title,
        "alternate_outcome": res_real.alternate_outcome,
        "alternate_outcome_realistic": res_real.alternate_outcome,
        "alternate_outcome_optimistic": res_opt.alternate_outcome,
        "key_changes": list(dict.fromkeys(res_real.key_changes + res_opt.key_changes)),
        "realistic_scenario_summary": res_real.alternate_outcome,
        "optimistic_scenario_summary": res_opt.alternate_outcome,
        "timeline": [t.model_dump() for t in res_real.timeline],
        "butterfly_effects": list(dict.fromkeys(res_real.butterfly_effects + res_opt.butterfly_effects)),
        "sources": list(dict.fromkeys(res_real.sources + res_opt.sources)),
        "geojson_after_realistic": {"type": "FeatureCollection", "features": state.get("realistic_features", [])},
        "geojson_after_optimistic": {"type": "FeatureCollection", "features": state.get("optimistic_features", [])},
        "territories_after_realistic": [t.model_dump() for t in res_real.territories],
        "territories_after_optimistic": [t.model_dump() for t in res_opt.territories]
    }
    
    if "geojson_districts" in state:
        results["geojson_districts"] = state["geojson_districts"]
    
    all_baseline_polities = state.get("baseline_polities", state.get("parties", []))
    build_common_results(results, state["year"], state, all_baseline_polities, state.get("geojson_before", {}))
    
    return {"results": results}


def anomaly_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 14: Geopolitical anomaly & enclave inspector."""
    if state.get("simulation_mode") != "expansion_conquest":
        return {"status": "completed", "anomalies": []}
        
    res_real = ScenarioStateResult(**state["res_real"])
    res_opt = ScenarioStateResult(**state["res_opt"])
    
    has_anomalies, questions_list = check_geopolitical_anomalies(
        res_real, res_opt,
        state.get("realistic_features", []),
        state.get("optimistic_features", []),
        state["scenario"], state["year"], state
    )
    
    if has_anomalies:
        return {
            "status": "awaiting_verification",
            "anomalies": questions_list,
            "questions": questions_list
        }
    else:
        return {
            "status": "completed",
            "anomalies": []
        }


def verification_apply_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 15: User verification choices application node."""
    selections = state.get("user_selections", {})
    context_answers = state.get("clarifying_questions", [])
    
    if not selections and not context_answers:
        return {"status": "completed"}
        
    return run_geopolitical_validation(state)
