"""
Expansion conquest simulation pipeline module for Geopolitico simulation engine.
Runs realistic and optimistic conquest simulations and enforces topological expansions.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from shapely.geometry import shape
from shapely.ops import unary_union

from backend.models.schemas import ScenarioStateResult, TerritoryChange
from backend.tools.country_polygons import get_country_polygon_loader
from backend.helpers.llm import invoke_structured_with_fallback
from backend.helpers.postprocess import force_conquest_provinces, resolve_modern_cities_to_historical_units
from backend.helpers.validation import run_geopolitical_validation
from backend.tools.compiler import process_territory_definitions
from backend.helpers.prompt_loader import _load_prompt_template


def _merge_duplicate_territories(territories: List[TerritoryChange]) -> List[TerritoryChange]:
    """Merge duplicate territory objects returned by LLM with identical names."""
    merged = {}
    for t in territories:
        key = t.name.lower()
        if key in merged:
            existing = merged[key]
            for hp in (getattr(t, "historical_provinces", []) or []):
                if hp not in getattr(existing, "historical_provinces", []):
                    existing.historical_provinces.append(hp)
            for ca in (t.countries_absorbed or []):
                if ca not in existing.countries_absorbed:
                    existing.countries_absorbed.append(ca)
            for pc in (t.partial_countries or []):
                existing.partial_countries.append(pc)
        else:
            merged[key] = t
    return list(merged.values())


def run_conquest_sim(
    scenario_val: str,
    year_val: int,
    context_val: dict,
    stage_num: int = 1,
    baselines_override_real: dict = None,
    baselines_override_opt: dict = None,
    answers: Optional[Dict[str, str]] = None
) -> Tuple[ScenarioStateResult, ScenarioStateResult, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run conquest simulation for realistic and optimistic outcomes."""
    from backend.tools.gis_tools import find_contested_provinces
    from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
    from backend.helpers.prompt_loader import _load_prompt_template
    from backend.tools.baseline_resolver import get_historical_units

    baseline_polities = context_val.get("all_baseline_polities") or context_val.get("baseline_polities", [])
    target_countries = context_val.get("target_countries", [])
    
    restricted_countries = target_countries if target_countries else [
        "France", "Spain", "Italy", "Switzerland", "Germany", "Greece", "Bulgaria", "Turkey",
        "Belgium", "Netherlands", "Luxembourg", "Austria", "Andorra", "Portugal", "Morocco",
        "Slovenia", "Poland", "Czechia", "Denmark", "Middle East", "Albania", "North Macedonia",
        "Syria", "Iraq", "Iran", "Armenia", "Georgia", "Azerbaijan"
    ]
    
    loader = get_country_polygon_loader()
    print(f"[SIMULATOR] (Stage {stage_num}) Locating contested provinces for baseline polities {baseline_polities} in {year_val} AD...", flush=True)
    
    contested_provinces = find_contested_provinces(baseline_polities, year_val, target_countries, is_partition=False)
    
    print(f"[SIMULATOR] (Stage {stage_num}) Analyzing baseline territorial ownership...", flush=True)
    baseline_ownership = {polity: [] for polity in baseline_polities}
    baseline_ownership_opt = {polity: [] for polity in baseline_polities}
    polity_shapes = {}
    polity_shapes_opt = {}
    for polity in baseline_polities:
        if stage_num == 2 and baselines_override_real and polity in baselines_override_real:
            polity_shapes[polity] = baselines_override_real[polity]
        else:
            sh, _, tier = _get_resolved_baseline_geometry(polity, year_val, context_val.get("target_region", ""))
            if sh is not None:
                polity_shapes[polity] = sh

        if stage_num == 2 and baselines_override_opt and polity in baselines_override_opt:
            polity_shapes_opt[polity] = baselines_override_opt[polity]
        elif polity in polity_shapes:
            polity_shapes_opt[polity] = polity_shapes[polity]
                    
    for prov_name in contested_provinces:
        for f in loader.provinces_data:
            props = f.get("properties", {})
            pname = props.get("name")
            admin = props.get("admin")
            if f"{pname} ({admin})" == prov_name:
                geom_dict = f.get("geometry")
                if geom_dict:
                    try:
                        prov_sh = shape(geom_dict)
                        for polity, p_geom in polity_shapes.items():
                            is_owner = False
                            try:
                                intersection_area = prov_sh.intersection(p_geom).area
                                if intersection_area > 0.5 * prov_sh.area:
                                    is_owner = True
                            except Exception:
                                if prov_sh.centroid.within(p_geom):
                                    is_owner = True
                            if is_owner:
                                baseline_ownership[polity].append(prov_name)
                        for polity, p_geom in polity_shapes_opt.items():
                            is_owner = False
                            try:
                                intersection_area = prov_sh.intersection(p_geom).area
                                if intersection_area > 0.5 * prov_sh.area:
                                    is_owner = True
                            except Exception:
                                if prov_sh.centroid.within(p_geom):
                                    is_owner = True
                            if is_owner:
                                baseline_ownership_opt[polity].append(prov_name)
                    except Exception:
                        pass
                break
                
    is_ancient_conquest = (year_val < 1800)
    
    if is_ancient_conquest:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            countries_controlled = sorted(list(set(prov.split('(')[-1].replace(')', '').strip() for prov in provs)))
            ownership_str += f"- {polity} currently controls territory within the following modern countries: {', '.join(countries_controlled) if countries_controlled else 'None'}\n"
        
        ownership_str_opt = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership_opt.items():
            countries_controlled = sorted(list(set(prov.split('(')[-1].replace(')', '').strip() for prov in provs)))
            ownership_str_opt += f"- {polity} currently controls territory within the following modern countries: {', '.join(countries_controlled) if countries_controlled else 'None'}\n"
        
        prompt_contested = f"Contested provinces are located within the following modern countries: {', '.join(sorted(target_countries) if target_countries else sorted(restricted_countries))}. Since this is an ancient/medieval scenario (< 1800 AD), do NOT attempt to annex modern administrative provinces individually. Instead, define your conquests using whole countries, or use the natural boundary vector clipping system (e.g. Loire River, Pyrenees, Alps, Rhine River) with empty provinces array '[]' to draw smooth natural borders. The only exception is capturing a famous capital city, in which case you can annex its modern province (e.g. 'Istanbul (Turkey)' for Constantinople)."
    else:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            if len(provs) > 15:
                ownership_str += f"- {polity} currently controls {len(provs)} provinces including: {', '.join(provs[:15])} ... [and {len(provs) - 15} more]\n"
            else:
                ownership_str += f"- {polity} currently controls: {', '.join(provs) if provs else 'None'}\n"
        
        ownership_str_opt = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership_opt.items():
            if len(provs) > 15:
                ownership_str_opt += f"- {polity} currently controls {len(provs)} provinces including: {', '.join(provs[:15])} ... [and {len(provs) - 15} more]\n"
            else:
                ownership_str_opt += f"- {polity} currently controls: {', '.join(provs) if provs else 'None'}\n"
        
        prompt_contested = contested_provinces
        if isinstance(prompt_contested, list) and len(prompt_contested) > 30:
            prompt_contested = prompt_contested[:30] + [f"... [and {len(prompt_contested) - 30} more contested provinces across target countries]"]
            
    all_available_units = set()
    active_prompt_pols = context_val.get("all_baseline_polities") or context_val.get("parties") or baseline_polities
    for bp in active_prompt_pols:
        res_hist = get_historical_units(bp, year_val, context_val.get("target_region", "") if context_val else "")
        h_map = res_hist.get("historical_units_map", {})
        all_available_units.update(h_map.keys())
    available_units_str = ", ".join(sorted(all_available_units)) if all_available_units else "None"

    prompt_vars = {
        "scenario": scenario_val,
        "year": year_val,
        "parties": context_val.get("parties", []),
        "ownership_str": ownership_str,
        "contested_provinces": prompt_contested,
        "available_historical_units": available_units_str,
        "answers_str": "",
        "demographics_context": ""
    }
    
    target_instructions = ""
    if year_val < 1800:
        target_instructions += (
            f"\nCRITICAL ANCIENT/MEDIEVAL GEOGRAPHY RULES (< 1800 AD):\n"
            f"- Since this simulation is in the year {year_val} (ancient/medieval era), select contiguous, historically authentic regional units from `available_historical_units` for `historical_provinces`.\n"
            f"- SCENARIO FOCAL OBJECTIVE MANDATE: Identify any key cities, battlefields, or focal fortresses named or implied in the scenario prompt ({scenario_val}) (e.g. Constantinople, Tours, Vienna, Rome, Jerusalem). You MUST ensure the historical unit or province containing that primary focal objective is included in `historical_provinces`.\n"
            f"- GEOGRAPHIC CONTIGUITY & NO LEAPFROGGING: All conquests MUST form a single, unbroken block attached directly to the conqueror's baseline borders. Avoid isolated enclaves or disconnected territory.\n"
            f"- Set `countries_absorbed: []` and `partial_countries: []` when specifying `historical_provinces`."
        )
        
    if stage_num == 2 and baselines_override_real:
        stage1_real = context_val.get("stage1_real_conquests_str", "")
        target_instructions += (
            f"\nCRITICAL STAGE 2 MOMENTUM INSTRUCTIONS:\n"
            f"- You achieved a major victory in the previous Stage 1 conflict. You start this stage with that expanded territory.\n"
            f"- Defeated parties have LOST these territories:\n{stage1_real}\n"
            f"- Reduce the territories of defeated parties accordingly."
        )
        
    realistic_answers_str = ""
    optimistic_answers_str = ""
    if answers and "clarifying_questions" in context_val:
        questions = context_val["clarifying_questions"]
        real_parts = []
        opt_parts = []
        for q_id, ans in answers.items():
            matching_q = None
            for q in questions:
                if q.get("id") == q_id:
                    matching_q = q
                    break
            if matching_q:
                type_ = matching_q.get("scenario_type")
                question_text = matching_q.get("question")
                if type_ == "realistic":
                    real_parts.append(f"{question_text} Selected Choice: {ans}")
                elif type_ == "optimistic":
                    opt_parts.append(f"{question_text} Selected Choice: {ans}")
        if real_parts:
            realistic_answers_str = "\nCRITICAL USER OUTCOME CHOICES FOR REALISTIC SCENARIO:\n" + "\n".join(f"- {p}" for p in real_parts)
        if opt_parts:
            optimistic_answers_str = "\nCRITICAL USER OUTCOME CHOICES FOR OPTIMISTIC SCENARIO:\n" + "\n".join(f"- {p}" for p in opt_parts)

    template_real = _load_prompt_template("expansion_conquest.txt")
    if template_real:
        target_instr_real = target_instructions.format(year=year_val)
        if realistic_answers_str:
            target_instr_real += f"\n{realistic_answers_str}\nYou MUST simulate the realistic scenario strictly respecting the user choices listed above. If the choice is a specific boundary or none, adjust the territories to match exactly."
        prompt_vars["target_instructions"] = target_instr_real
        prompt_vars["real_conquests_context"] = ""
        prompt_vars["conquest_type"] = (
            "REALISTIC military simulation: Select a plausible, contiguous set of historical administrative units in `historical_provinces` "
            "that the conqueror would realistically annex based on the scenario victories and regional geography. "
            "Select 2 to 4 contiguous historical units covering the immediate conflict front. "
            "Set `countries_absorbed`: [] and `partial_countries`: [] when specifying `historical_provinces`."
        )
        
        if stage_num == 2 and baselines_override_real:
            prompt_vars["real_conquests_context"] = (
                "\nSTAGE 1 REALISTIC VICTORY ACHIEVED AND INCORPORATED:\n"
                "- The Stage 1 conflict was successfully won, expanding your starting territory. "
                "You must build on top of these expanded borders."
            )
            
        real_prompt = template_real.format(**prompt_vars)
    else:
        real_prompt = f"Simulate military conquest: {scenario_val}. contested: {contested_provinces}"
        
    res_real: ScenarioStateResult = invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=real_prompt)], temperature=0.7)
    res_real.territories = _merge_duplicate_territories(res_real.territories)
    force_conquest_provinces(res_real.territories, scenario_val)
    resolve_modern_cities_to_historical_units(res_real.territories, year_val, context_val)
    
    real_conquests_str = ""
    for t in res_real.territories:
        conquest_parts = []
        if getattr(t, "historical_provinces", []):
            conquest_parts.append(f"Historical Provinces Conquered: {', '.join(t.historical_provinces)}")
        for p in t.partial_countries:
            if getattr(p, "historical_provinces", []):
                conquest_parts.append(f"Historical Provinces Conquered in {p.country}: {', '.join(p.historical_provinces)}")
            elif p.clip_method == "natural_boundary" and p.clip_description:
                conquest_parts.append(f"{p.country} ({p.clip_direction} of {p.clip_description})")
            elif p.clip_method in ["coordinate_latitude", "coordinate_longitude"] and p.clip_description:
                conquest_parts.append(f"{p.country} ({p.clip_description})")
            elif p.provinces:
                conquest_parts.append(f"{p.country} (provinces: {', '.join(p.provinces)})")
        if t.countries_absorbed:
            conquest_parts.append(f"Fully absorbed countries: {', '.join(t.countries_absorbed)}")
        if conquest_parts:
            real_conquests_str += f"- {t.name} conquered: " + "; ".join(conquest_parts) + "\n"
            
    if template_real:
        target_instr_opt = target_instructions.format(year=year_val)
        if optimistic_answers_str:
            target_instr_opt += f"\n{optimistic_answers_str}\nYou MUST simulate the optimistic scenario strictly respecting the user choices listed above. If the choice is a specific boundary or region, adjust the territories to match exactly."
        prompt_vars["target_instructions"] = target_instr_opt
        
        if stage_num == 2 and baselines_override_opt:
            stage1_opt = context_val.get("stage1_opt_conquests_str", "")
            prompt_vars["real_conquests_context"] = (
                "\nSTAGE 1 OPTIMISTIC VICTORY ACHIEVED AND INCORPORATED:\n"
                "- The Stage 1 conflict was won under best-case scenarios. You start Stage 2 with these fully expanded borders.\n"
                f"REALISTIC STAGE 2 BASELINE (YOU MUST EXPAND BEYOND THESE IN THIS OPTIMISTIC RUN):\n{real_conquests_str}"
            )
            prompt_vars["target_instructions"] += (
                f"\nCRITICAL COMPLEMENTARY LOSS INSTRUCTIONS FOR DEFEATED PARTIES:\n"
                f"- In Stage 1, the following territories were conquered from their original owners:\n{stage1_opt}"
                f"- Defeated parties (like Byzantine Empire) have LOST these territories. In your JSON response, you MUST "
                f"reduce the territories of these defeated parties accordingly. Do NOT let the Byzantine Empire claim or "
                f"absorb Turkey, Constantinople, or Greece, as those are now owned by the Umayyad Caliphate!"
            )
        else:
            prompt_vars["real_conquests_context"] = (
                f"\nREALISTIC CONQUESTS ACHIEVED IN THIS EVENT:\n{real_conquests_str}"
                "\nCRITICAL OPTIMISTIC THEATER EXPANSION REQUIREMENT:\n"
                "- OPTIMISTIC SCENARIO (Maximum Plausible Theater Annexation): Annex the maximum historically plausible territorial gain within the SAME regional theater of war (e.g., securing the full river basin or complete historical duchy system covering the active conflict front).\n"
                "- CONTIGUITY & THEATER BOUND: Do NOT expand into distant, unrelated foreign realms outside the active campaign theater unless explicitly specified in the scenario prompt.\n"
                "- Select 1 to 3 additional contiguous historical units in `historical_provinces` bordering the realistic conquests to complete the regional theater.\n"
                "- Set `countries_absorbed`: [] and `partial_countries`: [] when `historical_provinces` are specified."
            )
            
        if stage_num == 2:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC compounding simulation: This is a BEST-CASE scenario representing maximum plausible expansion across active campaign fronts. "
                "Select 1 to 3 additional contiguous historical units in `historical_provinces` bordering the realistic conquests. "
                "Set `countries_absorbed`: [] and `partial_countries`: [] when specifying `historical_provinces`."
            )
        else:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC military simulation: This is a BEST-CASE scenario representing maximum plausible expansion within the active conflict theater. "
                "Select 1 to 3 additional contiguous historical units in `historical_provinces` bordering the realistic conquests. "
                "Do NOT jump into distant unrelated foreign realms. Set `countries_absorbed`: [] and `partial_countries`: [] when specifying `historical_provinces`."
            )
            
        prompt_vars["ownership_str"] = ownership_str_opt
        opt_prompt = template_real.format(**prompt_vars)
    else:
        opt_prompt = real_prompt
        
    res_opt: ScenarioStateResult = invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=opt_prompt)], temperature=0.7)
    res_opt.territories = _merge_duplicate_territories(res_opt.territories)
    force_conquest_provinces(res_opt.territories, scenario_val)
    resolve_modern_cities_to_historical_units(res_opt.territories, year_val, context_val)
    
    # Enforce strict guardrail: clear countries_absorbed and partial_countries if historical_provinces are present
    for t_r in res_real.territories:
        if getattr(t_r, "historical_provinces", []):
            t_r.countries_absorbed = []
            t_r.partial_countries = []
    for t_o in res_opt.territories:
        if getattr(t_o, "historical_provinces", []):
            t_o.countries_absorbed = []
            t_o.partial_countries = []
    
    is_compounding = ("compounding_plan" in context_val or "scenario_2" in context_val)
    if not is_compounding or stage_num == 2:
        stage1_real = context_val.get("stage1_real_conquests_str", "") if context_val else ""
        stage1_opt = context_val.get("stage1_opt_conquests_str", "") if context_val else ""
        res_real = run_geopolitical_validation(res_real, scenario_val, year_val, context_val, stage1_conquests_str=stage1_real)
        res_opt = run_geopolitical_validation(res_opt, scenario_val, year_val, context_val, stage1_conquests_str=stage1_opt)
    
    if baselines_override_real:
        context_val["stage2_baselines"] = baselines_override_real
    else:
        context_val.pop("stage2_baselines", None)
    
    if "compounding_resolved_geoms_real" in context_val:
        context_val["compounding_resolved_geoms"] = context_val["compounding_resolved_geoms_real"]
    realistic_features = process_territory_definitions(res_real.territories, year_val, context_val)
    
    if baselines_override_opt:
        context_val["stage2_baselines"] = baselines_override_opt
    else:
        context_val.pop("stage2_baselines", None)
        
    if "compounding_resolved_geoms_opt" in context_val:
        context_val["compounding_resolved_geoms"] = context_val["compounding_resolved_geoms_opt"]
        
    parties_list = context_val.get("parties", []) if context_val else []
    baseline_pols = context_val.get("baseline_polities", []) if context_val else []
    winner_polity = parties_list[0] if parties_list else (baseline_pols[0] if baseline_pols else "")
    for t_opt in res_opt.territories:
        for t_real in res_real.territories:
            if t_opt.name.lower() == t_real.name.lower() or (winner_polity and winner_polity.lower() in t_opt.name.lower()):
                h_opt = set(getattr(t_opt, "historical_provinces", []) or [])
                h_real = set(getattr(t_real, "historical_provinces", []) or [])
                if h_opt and h_opt.issubset(h_real):
                    h_map_all = {}
                    baseline_pols = context_val.get("baseline_polities", []) if context_val else []
                    for bp in baseline_pols:
                        res_hist = get_historical_units(bp, year_val, context_val.get("target_region", "") if context_val else "")
                        h_map_all.update(res_hist.get("historical_units_map", {}))
                        
                    current_geoms = [h_map_all[k] for k in t_opt.historical_provinces if k in h_map_all and h_map_all[k]]
                    candidate_adjacent = []
                    if current_geoms:
                        opt_union = unary_union(current_geoms)
                        buffer_zone = opt_union.buffer(0.1)
                        for cand_key, cand_geom in h_map_all.items():
                            if cand_key not in t_opt.historical_provinces and cand_geom and not cand_geom.is_empty:
                                if cand_geom.intersects(buffer_zone):
                                    candidate_adjacent.append(cand_key)
                                    
                    if candidate_adjacent:
                        print(f"[SIMULATOR] Optimistic map identical to realistic. Programmatically expanding into adjacent topological units: {candidate_adjacent[:3]}.", flush=True)
                        for app_u in candidate_adjacent[:3]:
                            if app_u not in t_opt.historical_provinces and app_u not in h_real:
                                t_opt.historical_provinces.append(app_u)

    optimistic_features = process_territory_definitions(res_opt.territories, year_val, context_val)
    context_val.pop("stage2_baselines", None)
    
    from backend.helpers.result_builder import build_conquest_summary_str
    real_conquests_str = build_conquest_summary_str(res_real.territories)
    opt_conquests_str = build_conquest_summary_str(res_opt.territories)
    
    print("=" * 80, flush=True)
    print(f"[SIMULATOR] FINAL REALISTIC SCENARIO OUTCOME ({scenario_val}, {year_val} AD):", flush=True)
    print(real_conquests_str if real_conquests_str else "  No territories conquered.", flush=True)
    print("-" * 80, flush=True)
    print(f"[SIMULATOR] FINAL OPTIMISTIC SCENARIO OUTCOME ({scenario_val}, {year_val} AD):", flush=True)
    print(opt_conquests_str if opt_conquests_str else "  No territories conquered.", flush=True)
    print("=" * 80, flush=True)
    
    return res_real, res_opt, realistic_features, optimistic_features


_run_conquest_sim = run_conquest_sim
