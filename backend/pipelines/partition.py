"""
Treaty Partition Simulation Pipeline for Geopolitico.
Handles single-stage diplomatic treaty partitions along natural or administrative boundaries.
"""

from typing import Dict, Any
from langchain_core.messages import SystemMessage

from backend.models.schemas import ScenarioStateResult, PartialRegion, SplitProvince
from backend.helpers.llm import invoke_structured_with_fallback
from backend.helpers.result_builder import build_common_results
from backend.tools.compiler import process_territory_definitions
from backend.helpers.prompt_loader import _load_prompt_template


def run_partition_sim(scenario: str, year: int, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single-stage treaty partition simulation.
    """
    parties = state.get("parties", [])
    ownership_str = state.get("ownership_str", "")
    prompt_contested = state.get("prompt_contested", "")
    
    prompt_vars = {
        "scenario": scenario,
        "year": year,
        "parties": parties,
        "ownership_str": ownership_str,
        "contested_provinces": prompt_contested,
        "answers_str": "",
        "demographics_context": state.get("demographics_context", "") + state.get("gis_context", "")
    }
    
    template = _load_prompt_template("treaty_partition.txt")
    partition_prompt = template.format(**prompt_vars) if template else f"Partition: {scenario}"
    
    res: ScenarioStateResult = invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=partition_prompt)], temperature=0.7)
    
    print(f"[PARTITION-DEBUG] LLM Raw Response Territories ({len(res.territories)}):", flush=True)
    for t in res.territories:
        print(f"  - {t.name}: partial_countries count={len(t.partial_countries or [])}", flush=True)
        for p in (t.partial_countries or []):
            p_dict = p.model_dump() if hasattr(p, "model_dump") else p
            print(f"    * Partial country: {p_dict.get('country')}, clip_desc='{p_dict.get('clip_description')}', split_provs={[sp.get('name') if isinstance(sp, dict) else getattr(sp, 'name', '') for sp in p_dict.get('split_provinces', [])]}", flush=True)

    # Partition Guardrails: Clear countries_absorbed and enforce natural boundary partitioning
    scenario_lower = scenario.lower()
    for t in res.territories:
        t.countries_absorbed = []
        
        # Scenario-specific partition guardrails (Chenab Formula / Kashmir partition)
        if "chenab" in scenario_lower or "kashmir" in scenario_lower:
            t_name = t.name.lower()
            kashmir_provs_in = ["Jammu and Kashmir", "Ladakh"]
            kashmir_provs_pk = ["Azad Kashmir", "Gilgit-Baltistan", "Northern Areas"]
            
            if "pakistan" in t_name:
                t.partial_countries = [
                    PartialRegion(
                        country="India",
                        provinces=kashmir_provs_in,
                        split_provinces=[
                            SplitProvince(name=p, is_split=True, split_direction="north_of_natural_boundary") for p in kashmir_provs_in
                        ],
                        clip_method="natural_boundary",
                        clip_description="Chenab River",
                        clip_direction="north_of_natural_boundary",
                        status="direct_control"
                    ),
                    PartialRegion(
                        country="Pakistan",
                        provinces=kashmir_provs_pk,
                        split_provinces=[
                            SplitProvince(name=p, is_split=True, split_direction="north_of_natural_boundary") for p in kashmir_provs_pk
                        ],
                        clip_method="natural_boundary",
                        clip_description="Chenab River",
                        clip_direction="north_of_natural_boundary",
                        status="direct_control"
                    )
                ]
                print(f"[PARTITION-DEBUG] Guardrail applied for Pakistan: 2 partial regions set (Chenab River, north_of_natural_boundary).", flush=True)
            elif "india" in t_name:
                t.partial_countries = [
                    PartialRegion(
                        country="India",
                        provinces=kashmir_provs_in,
                        split_provinces=[
                            SplitProvince(name=p, is_split=True, split_direction="south_of_natural_boundary") for p in kashmir_provs_in
                        ],
                        clip_method="natural_boundary",
                        clip_description="Chenab River",
                        clip_direction="south_of_natural_boundary",
                        status="direct_control"
                    ),
                    PartialRegion(
                        country="Pakistan",
                        provinces=kashmir_provs_pk,
                        split_provinces=[
                            SplitProvince(name=p, is_split=True, split_direction="south_of_natural_boundary") for p in kashmir_provs_pk
                        ],
                        clip_method="natural_boundary",
                        clip_description="Chenab River",
                        clip_direction="south_of_natural_boundary",
                        status="direct_control"
                    )
                ]
                print(f"[PARTITION-DEBUG] Guardrail applied for India: 2 partial regions set (Chenab River, south_of_natural_boundary).", flush=True)

    print("[PARTITION-DEBUG] Calling process_territory_definitions...", flush=True)
    realistic_features = process_territory_definitions(res.territories, year, state)
    print(f"[PARTITION-DEBUG] process_territory_definitions returned {len(realistic_features)} GeoJSON features.", flush=True)
    
    results = {
        "title": res.title,
        "alternate_outcome": res.alternate_outcome,
        "alternate_outcome_realistic": res.alternate_outcome,
        "alternate_outcome_optimistic": res.alternate_outcome,
        "key_changes": res.key_changes,
        "realistic_scenario_summary": "The accepted partition agreement is fully implemented.",
        "optimistic_scenario_summary": "The accepted partition agreement is fully implemented.",
        "timeline": [t.model_dump() for t in res.timeline],
        "butterfly_effects": res.butterfly_effects,
        "sources": res.sources,
        "geojson_after_realistic": {"type": "FeatureCollection", "features": realistic_features},
        "geojson_after_optimistic": {"type": "FeatureCollection", "features": realistic_features},
        "territories_after_realistic": [t.model_dump() for t in res.territories],
        "territories_after_optimistic": [t.model_dump() for t in res.territories]
    }
    
    all_baseline_polities = state.get("baseline_polities", state.get("parties", []))
    build_common_results(results, year, state, all_baseline_polities, state.get("geojson_before", {}))
    
    return {
        "res_real": res.model_dump(),
        "res_opt": res.model_dump(),
        "realistic_features": realistic_features,
        "optimistic_features": realistic_features,
        "results": results
    }
