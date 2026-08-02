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
from backend.tools.baseline_resolver import _get_resolved_baseline_geometry, _get_province_color, get_historical_units
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
    
    parties = list(res.parties) if res.parties else []
    scen_lower = scenario.lower()
    desc_lower = (res.baseline_description or "").lower()
    combined_text = scen_lower + " " + desc_lower

    winner_polity = ""
    for p in parties:
        if len(p) >= 3 and p.lower() in combined_text:
            winner_polity = p
            break

    if winner_polity and parties and parties[0] != winner_polity:
        print(f"[SAFEGUARD-1] Inverted party order detected in AI output. Reordering victor '{winner_polity}' to index 0 of parties.", flush=True)
        parties.remove(winner_polity)
        parties.insert(0, winner_polity)

    if not winner_polity and parties:
        winner_polity = parties[0]

    return {
        "year": res.year,
        "parties": parties,
        "winner_polity": winner_polity,
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
        "year_1": plan.year_1,
        "scenario_2": plan.scenario_2,
        "year_2": plan.year_2,
        "year": plan.year_1
    }


def shared_preprocess_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 5: Preprocess baseline geometries and contested provinces with spatial filtering."""
    scenario = state["scenario"]
    year = state["year"]
    parties = state.get("parties", [])
    target_region = state.get("target_region", "")
    target_countries = state.get("target_countries", [])
    simulation_mode = state.get("simulation_mode", "expansion_conquest")
    raw_baseline_polities = state.get("baseline_polities", parties)
    winner_polity = state.get("winner_polity") or (parties[0] if parties else "")

    # Phase 7: Spatial adjacency filter — drop non-contiguous distant polities (e.g. Poland, Venice)
    from backend.helpers.programmatic_validator import filter_contiguous_baseline_polities
    all_baseline_polities = filter_contiguous_baseline_polities(
        raw_baseline_polities, winner_polity, year, target_countries
    )

    contested = find_contested_provinces(all_baseline_polities, year, target_countries, is_partition=(simulation_mode == "proposal_partition"))
    prompt_contested = ", ".join(contested[:12]) if contested else "regional borders"

    features_before_coarse = []
    features_provinces = []
    units_ownership_map = {}

    for bp in all_baseline_polities:
        sh, feat_dict, tier = _get_resolved_baseline_geometry(bp, year, target_region)
        base_color = _get_province_color(bp, bp)

        if sh is not None and not sh.is_empty:
            from shapely.geometry import mapping
            geom_map = feat_dict["geometry"] if (feat_dict and "geometry" in feat_dict) else mapping(sh)
            coarse_feat = {
                "type": "Feature",
                "geometry": geom_map,
                "properties": {
                    "Name": bp, "name": bp,
                    "FromYear": year, "ToYear": year, "year": year,
                    "tier": tier,
                    "is_outer_border": True,
                    "color": base_color, "fill_color": base_color
                }
            }
            features_before_coarse.append(coarse_feat)

            # Direct sub-province feature resolution (read from SimulationCache or resolve once)
            res = get_historical_units(bp, year, target_region)
            core_provs = res.get("provinces_core", [])
            edge_provs = res.get("provinces_edge", [])
            units_ownership_map[bp] = list(res.get("historical_units_map", {}).keys())

            if not core_provs and not edge_provs:
                from backend.tools.baseline_resolver import _map_units_to_provinces_advanced
                c_core, c_edge, _, _ = _map_units_to_provinces_advanced([])
                core_provs, edge_provs = c_core, c_edge

            bp_sub_features = []
            for item in core_provs + edge_provs:
                    u_name = item.get("assigned_unit") or bp
                    p_name = u_name
                    prov_color = item.get("color") or _get_province_color(u_name, bp)
                    bp_sub_features.append({
                        "type": "Feature",
                        "geometry": mapping(item["shape"]),
                        "properties": {
                            "empire": bp,
                            "name": p_name,
                            "fullname": p_name,
                            "assigned_unit": u_name,
                            "category": item.get("category", "Fully Inside"),
                            "status": item.get("category", "Fully Inside"),
                            "coverage_pct": item.get("coverage_pct", 100.0),
                            "color": prov_color,
                            "fill_color": prov_color,
                            "stroke_color": "rgba(255, 255, 255, 0.45)",
                            "is_sub_province": True
                        }
                    })

            if bp_sub_features:
                features_provinces.extend(bp_sub_features)

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

    return {
        "all_baseline_polities": all_baseline_polities,
        "contested_provinces": contested,
        "prompt_contested": prompt_contested,
        "geojson_before": geojson_before,
        "geojson_provinces": geojson_provinces,
        "gis_context": gis_context,
        "osm_boundaries": osm_boundaries,
        "baseline_units_map": units_ownership_map
    }


def ownership_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 6: Deterministic territorial ownership analysis (0 AI calls)."""
    year = state.get("year", 732)
    parties = state.get("parties", [])
    contested = state.get("contested_provinces", [])
    contested_str = ", ".join(contested[:5]) if contested else "borderlands"
    summary = f"Baseline territorial configuration for {', '.join(parties)} in {year} AD across {contested_str}."
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
    all_baseline_polities = state.get("all_baseline_polities") or state.get("baseline_polities", state.get("parties", []))
    
    if "results" in state and state["results"]:
        results = state["results"]
    else:
        res_real = ScenarioStateResult(**state["res_real"])
        res_opt = ScenarioStateResult(**state["res_opt"])
        
        mode_val = state.get("simulation_mode", "expansion_conquest")
        results = {
            "title": res_real.title,
            "scenario_mode": mode_val,
            "mode": mode_val,
            "pipeline": mode_val,
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
        if "geojson_audit" in state:
            results["geojson_audit"] = state["geojson_audit"]
            
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
