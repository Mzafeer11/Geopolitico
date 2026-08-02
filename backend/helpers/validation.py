"""
Geopolitical validation and anomaly checking helpers for Geopolitico simulation engine.
"""

import json
import traceback
from typing import List, Dict, Any, Tuple
from shapely.geometry import shape
from shapely.ops import unary_union
from langchain_core.messages import SystemMessage

from backend.models.schemas import (
    ScenarioStateResult,
    ValidationTerritoriesResult,
    AnomalyCheckResult,
    PartialRegion,
    TerritoryChange,
)
from backend.helpers.llm import invoke_structured_with_fallback
from backend.helpers.postprocess import force_conquest_provinces, resolve_modern_cities_to_historical_units
from backend.tools.cliopatria_loader import cliopatria_db
from backend.helpers.prompt_loader import _load_prompt_template


def run_geopolitical_validation(
    result: ScenarioStateResult, 
    scenario: str, 
    year: int, 
    context: Dict[str, Any],
    stage1_conquests_str: str = ""
) -> ScenarioStateResult:
    """Zero-latency programmatic geopolitical validation (0 LLM calls)."""
    try:
        print("[SIMULATOR] Programmatic Geopolitical & Topological Validation running...", flush=True)
        force_conquest_provinces(result.territories, scenario)
        resolve_modern_cities_to_historical_units(result.territories, year, context)

        for t in result.territories:
            if getattr(t, "historical_provinces", []):
                t.countries_absorbed = []
                t.partial_countries = []

        print("[SIMULATOR] Programmatic Geopolitical Validation completed successfully (0 LLM calls).", flush=True)
        return result
    except Exception as e:
        print(f"[WARN] Programmatic Geopolitical Validation error: {e}.", flush=True)
        return result


def check_geopolitical_anomalies(
    result_real: ScenarioStateResult,
    result_opt: ScenarioStateResult,
    realistic_features: List[Dict[str, Any]],
    optimistic_features: List[Dict[str, Any]],
    scenario: str,
    year: int,
    context: Dict[str, Any],
    process_territory_definitions_fn=None
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Run validation LLM to detect major contiguity enclaves, and pre-calculate highlight GeoJSONs."""
    try:
        baseline_pols = context.get("baseline_polities", []) if context else []
        winner_polity = baseline_pols[0] if baseline_pols else "Conqueror"
        
        template = _load_prompt_template("anomaly_checker.txt")
        if not template:
            print("[WARN] Anomaly checker template anomaly_checker.txt not found. Skipping.", flush=True)
            return False, []
            
        input_data = {
            "realistic": [t.model_dump() for t in result_real.territories],
            "optimistic": [t.model_dump() for t in result_opt.territories]
        }
        
        prompt = template.format(
            scenario=scenario,
            year=year,
            winner_polity=winner_polity,
            territories_json=json.dumps(input_data, indent=2)
        )
        
        print("[SIMULATOR] Launching Geopolitical Contiguity and Enclave Inspector...", flush=True)
        try:
            checker_res: AnomalyCheckResult = invoke_structured_with_fallback(
                AnomalyCheckResult,
                [SystemMessage(content=prompt)],
                temperature=0.2
            )
        except Exception as e:
            print(f"[WARN] Geopolitical anomaly inspection skipped due to LLM/network error: {e}", flush=True)
            return False, []
        
        if not checker_res or not checker_res.has_anomalies or not checker_res.questions:
            print("[SIMULATOR] No major contiguity enclaves detected.", flush=True)
            return False, []
            
        filtered_questions = []
        for q in checker_res.questions:
            baseline_geom = None
            if winner_polity:
                stage2_baselines = context.get("compounding_baselines_real" if q.scenario_type == "realistic" else "compounding_baselines_opt")
                if stage2_baselines and winner_polity in stage2_baselines:
                    baseline_geom = stage2_baselines[winner_polity]
                else:
                    hist_feat = cliopatria_db.get_polity_geometry(winner_polity, year)
                    if hist_feat and hist_feat.get("geometry"):
                        try:
                            baseline_geom = shape(hist_feat["geometry"])
                        except Exception:
                            pass
            
            if not baseline_geom:
                filtered_questions.append(q)
                continue
                
            sub_countries = [c.lower() for c in q.option_2.countries_absorbed]
            sub_partials = [p.get("country", "").lower() if isinstance(p, dict) else p.country.lower() for p in q.option_2.partial_countries]
            all_sub_names = set(sub_countries + sub_partials)
            
            if not all_sub_names:
                filtered_questions.append(q)
                continue
                
            target_features = realistic_features if q.scenario_type == "realistic" else optimistic_features
            main_body_shapes = [baseline_geom]
            enclave_shapes = []
            
            for feat in target_features:
                props = feat.get("properties", {})
                c_name = props.get("country", "") or props.get("name", "")
                if c_name:
                    try:
                        feat_shape = shape(feat["geometry"])
                        if c_name.lower() in all_sub_names:
                            enclave_shapes.append(feat_shape)
                        else:
                            main_body_shapes.append(feat_shape)
                    except Exception:
                        pass
                        
            try:
                main_body_union = unary_union(main_body_shapes)
                is_disconnected = False
                for es in enclave_shapes:
                    if es.disjoint(main_body_union.buffer(0.05)):
                        is_disconnected = True
                        break
                if is_disconnected:
                    filtered_questions.append(q)
                    print(f"[SIMULATOR] Geometric Contiguity check CONFIRMED enclave for question '{q.id}'.", flush=True)
                else:
                    print(f"[SIMULATOR] Geometric Contiguity check SUPPRESSED false enclave question '{q.id}' (connected to baseline).", flush=True)
            except Exception as geom_err:
                print(f"[WARN] Geometry contiguity check error for '{q.id}': {geom_err}", flush=True)
                filtered_questions.append(q)
                
        checker_res.questions = filtered_questions
        if not filtered_questions:
            checker_res.has_anomalies = False
            print("[SIMULATOR] All detected enclaves were suppressed programmatically as contiguous.", flush=True)
            return False, []
            
        print(f"[SIMULATOR] Detected {len(checker_res.questions)} major anomalies. Pre-calculating highlight layers...", flush=True)
        questions_with_geojson = []
        for q in checker_res.questions:
            q_dict = q.model_dump()
            
            # Option 1: Addition (Green)
            opt1 = q.option_1
            feat_list_1 = []
            if (opt1.countries_absorbed or opt1.partial_countries) and process_territory_definitions_fn:
                pc_list = []
                for pc in opt1.partial_countries:
                    if isinstance(pc, dict):
                        pc_list.append(PartialRegion(**pc))
                    else:
                        pc_list.append(pc)
                t_mock = TerritoryChange(
                    name="HighlightLayer",
                    type="region",
                    color="#2ecc71",
                    countries_absorbed=opt1.countries_absorbed,
                    partial_countries=pc_list,
                    description=opt1.description
                )
                feats = process_territory_definitions_fn(
                    [t_mock], year,
                    {**context, "simulation_mode": "proposal_partition", "baseline_polities": [], "compounding_resolved_geoms": None}
                )
                for f in feats:
                    f["properties"]["color"] = "#2ecc71"
                    f["properties"]["description"] = f"Proposed Addition: {opt1.description}"
                feat_list_1 = feats
            q_dict["option_1_geojson"] = {"type": "FeatureCollection", "features": feat_list_1}
            
            # Option 2: Subtraction (Red)
            opt2 = q.option_2
            feat_list_2 = []
            target_features = realistic_features if q.scenario_type == "realistic" else optimistic_features
            sub_countries = [c.lower() for c in opt2.countries_absorbed]
            sub_partials = [p.get("country", "").lower() if isinstance(p, dict) else p.country.lower() for p in opt2.partial_countries]
            all_sub_names = set(sub_countries + sub_partials)
            
            if all_sub_names:
                import copy
                for feat in target_features:
                    props = feat.get("properties", {})
                    c_name = props.get("country", "") or props.get("name", "")
                    if c_name and c_name.lower() in all_sub_names:
                        f_copy = copy.deepcopy(feat)
                        f_copy["properties"]["color"] = "#ef4444"
                        f_copy["properties"]["description"] = f"Proposed Subtraction: {opt2.description}"
                        feat_list_2.append(f_copy)
                        
            if not feat_list_2 and (opt2.countries_absorbed or opt2.partial_countries) and process_territory_definitions_fn:
                pc_list = []
                for pc in opt2.partial_countries:
                    if isinstance(pc, dict):
                        pc_list.append(PartialRegion(**pc))
                    else:
                        pc_list.append(pc)
                t_mock = TerritoryChange(
                    name="HighlightLayer",
                    type="region",
                    color="#ef4444",
                    countries_absorbed=opt2.countries_absorbed,
                    partial_countries=pc_list,
                    description=opt2.description
                )
                feats = process_territory_definitions_fn(
                    [t_mock], year,
                    {**context, "simulation_mode": "proposal_partition", "baseline_polities": [], "compounding_resolved_geoms": None}
                )
                for f in feats:
                    f["properties"]["color"] = "#ef4444"
                    f["properties"]["description"] = f"Proposed Subtraction: {opt2.description}"
                feat_list_2 = feats
            q_dict["option_2_geojson"] = {"type": "FeatureCollection", "features": feat_list_2}
            
            questions_with_geojson.append(q_dict)
            
        return True, questions_with_geojson
    except Exception as e:
        print(f"[WARN] Geopolitical Anomaly Inspector failed: {e}", flush=True)
        traceback.print_exc()
        return False, []
