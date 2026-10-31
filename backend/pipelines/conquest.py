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
from backend.tools.baseline_resolver import get_historical_units
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
        
        prompt_contested = f"Contested territories are located within the conflict zone across: {', '.join(sorted(target_countries) if target_countries else sorted(restricted_countries))}. Since this is an ancient/medieval scenario (< 1800 AD), define your conquests using authentic regional units from `available_historical_units` in `historical_provinces` (set `countries_absorbed`: [] and `partial_countries`: [])."
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
            
    parties_list = context_val.get("parties", []) if context_val else []
    conqueror_polity = parties_list[0] if parties_list else (baseline_polities[0] if baseline_polities else "")
    
    # Identify conqueror's already-owned baseline historical units so we don't offer them as conquests
    conqueror_owned_units = set()
    if conqueror_polity:
        res_conq = get_historical_units(conqueror_polity, year_val, context_val.get("target_region", "") if context_val else "")
        conqueror_owned_units = set(res_conq.get("historical_units_map", {}).keys())

    # Resolve conqueror baseline polygon for frontier adjacency detection
    winner_base_sh = polity_shapes.get(conqueror_polity)
    if winner_base_sh is None and conqueror_polity:
        try:
            sh_w, _, _ = _get_resolved_baseline_geometry(conqueror_polity, year_val, context_val.get("target_region", "") if context_val else "")
            winner_base_sh = sh_w
        except Exception:
            pass

    all_available_units = set()
    unit_geom_map = {}
    unit_polity_map = {}
    active_prompt_pols = list(context_val.get("all_baseline_polities") or context_val.get("parties") or baseline_polities)

    # Filter out polities belonging exclusively to an inactive compounding stage theater
    scen_lower = scenario_val.lower()
    is_byz_stage = any(k in scen_lower for k in ["constantinople", "byzantine", "byzantium", "anatolia", "thrace"]) and not any(k in scen_lower for k in ["tours", "frank", "poitiers", "gaul", "france"])
    is_frank_stage = any(k in scen_lower for k in ["tours", "frank", "poitiers", "gaul", "france", "aquitaine"]) and not any(k in scen_lower for k in ["constantinople", "byzantine", "byzantium", "anatolia"])

    for bp in active_prompt_pols:
        if bp.lower() == conqueror_polity.lower():
            continue
        bp_low = bp.lower()
        if is_byz_stage and ("frank" in bp_low):
            continue
        if is_frank_stage and ("byzant" in bp_low or "eastern roman" in bp_low):
            continue
        res_hist = get_historical_units(bp, year_val, context_val.get("target_region", "") if context_val else "")
        h_map = res_hist.get("historical_units_map", {})
        for u_name, u_geom in h_map.items():
            if u_name not in conqueror_owned_units:
                all_available_units.add(u_name)
                if u_geom and not u_geom.is_empty:
                    unit_geom_map[u_name] = u_geom
                unit_polity_map[u_name] = bp

    # If the theater involves Vienna/Austria/Habsburgs/Hungary in 1529, ensure all Austrian duchies and Hungarian plain units are available
    if any(k in scen_lower or k in (context_val.get("target_region", "") if context_val else "").lower() for k in ["vienna", "austria", "habsburg", "wien", "hungary"]):
        for rel_pol in ["Archduchy of Austria", "Kingdom of Hungary"]:
            res_pol = get_historical_units(rel_pol, year_val, context_val.get("target_region", "") if context_val else "")
            for u_name, u_geom in res_pol.get("historical_units_map", {}).items():
                if u_name not in conqueror_owned_units:
                    all_available_units.add(u_name)
                    if u_geom and not u_geom.is_empty:
                        unit_geom_map[u_name] = u_geom
                    unit_polity_map.setdefault(u_name, rel_pol)

    # Build rich Spatial & Topological Adjacency Briefing for each available historical unit
    unit_meta_lookup = {}
    try:
        from backend.tools.baseline_resolver import _load_wikidata_cache
        w_cache = _load_wikidata_cache()
        for _, p_entry in w_cache.items():
            for adm_u in p_entry.get("admin_units", []):
                adm_name = adm_u.get("name")
                if adm_name and adm_name not in unit_meta_lookup:
                    unit_meta_lookup[adm_name] = adm_u
    except Exception:
        pass

    sorted_avail = sorted(all_available_units)
    if sorted_avail:
        briefing_lines = []
        for u_name in sorted_avail:
            u_pol = unit_polity_map.get(u_name, "Target Polity")
            u_meta = unit_meta_lookup.get(u_name, {})
            u_cap = u_meta.get("capital_modern") or u_meta.get("capital_historical") or ""
            u_tier = u_meta.get("tier") or "Region"
            cap_str = f", Capital: {u_cap}" if u_cap else ""

            neighbors = []
            u_geom = unit_geom_map.get(u_name)
            if u_geom and not u_geom.is_empty:
                if winner_base_sh and not winner_base_sh.is_empty:
                    try:
                        if u_geom.distance(winner_base_sh) <= 0.06:
                            neighbors.append("[CONQUEROR FRONTIER]")
                    except Exception:
                        pass
                for other_u in sorted_avail:
                    if other_u == u_name:
                        continue
                    o_geom = unit_geom_map.get(other_u)
                    if o_geom and not o_geom.is_empty:
                        try:
                            if u_geom.distance(o_geom) <= 0.05:
                                neighbors.append(other_u)
                        except Exception:
                            pass
            adj_str = f" | Borders: {', '.join(neighbors)}" if neighbors else ""
            briefing_lines.append(f"  * \"{u_name}\" ({u_pol} {u_tier}{cap_str}){adj_str}")
        available_units_str = "\n" + "\n".join(briefing_lines)
    else:
        available_units_str = "None"

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
            f"- GEOGRAPHIC CONTIGUITY & CORRIDOR INTEGRITY: All conquests MUST form a single, unbroken block attached directly to the conqueror's baseline borders. Armies advancing to an inland fortress or capital (e.g. Vienna) MUST prioritize securing the lowland river plain corridor connecting their frontier to that objective (e.g. 'Alföld (Great Hungarian Plain)' linking the Balkans directly to 'Lower Austria (Vienna)'). Do NOT bypass the connecting river plain to take rugged peripheral mountain regions.\n"
            f"- Set `countries_absorbed: []` and `partial_countries: []` when specifying `historical_provinces`."
        )
        
    if stage_num == 2 and baselines_override_real:
        stage1_real = context_val.get("stage1_real_conquests_str", "")
        stage1_opt = context_val.get("stage1_opt_conquests_str", "")
        target_instructions += (
            f"\nCRITICAL STAGE 2 MOMENTUM INSTRUCTIONS:\n"
            f"- You achieved major victories in the previous Stage 1 conflict. You start this stage with that expanded territory.\n"
            f"- FOR REALISTIC SCENARIO: Defeated parties lost the realistic Stage 1 conquests:\n{stage1_real}\n"
            f"- FOR OPTIMISTIC SCENARIO: Defeated parties lost the maximum optimistic Stage 1 conquests:\n{stage1_opt}\n"
            f"- Reduce the starting territories of defeated parties accordingly in each respective scenario."
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
            "REALISTIC military simulation: Select the complete, contiguous set of historical administrative units in `historical_provinces` "
            "that the conqueror must annex to connect `[CONQUEROR FRONTIER]` to the scenario's primary focal objective(s), plus the immediate theater of victory. "
            "Use the provided `Borders:` adjacency list to include every intermediate stepping-stone province along the campaign corridor so zero un-annexed holes remain behind the advance. "
            "Stop at the realistic extent of the campaign objective (e.g., for Constantinople 717 AD, annex the Anatolian corridor and Thrace/Constantinople without jumping deep into Balkan Europe or Italy; for Tours 732 AD, annex Septimania and Aquitaine/southern Gaul without annexing distant German duchies like Saxony or Bavaria). "
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
        
    res_real: ScenarioStateResult = invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=real_prompt)], temperature=0.25)
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
                f"REALISTIC STAGE 2 BASELINE (YOU MUST INCLUDE ALL OF THESE AND EXPAND BEYOND THEM BY 1 TO 3 ADJACENT THEATER UNITS):\n{real_conquests_str}"
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
                f"\nREALISTIC CONQUESTS ACHIEVED IN THIS EVENT (YOU MUST INCLUDE ALL OF THESE IN YOUR OPTIMISTIC LIST):\n{real_conquests_str}"
                "\nCRITICAL OPTIMISTIC THEATER EXPANSION REQUIREMENT:\n"
                "- OPTIMISTIC SCENARIO (Maximum Plausible Theater Annexation): Include ALL historical units from the Realistic Conquests above, PLUS 1 to 3 additional contiguous historical units directly bordering the realistic front within the same or immediately adjacent regional theater.\n"
                "- For example: after taking Constantinople & Anatolia in 717 AD, expand into adjacent European/Aegean Byzantine units (`Illyricum`, `Aegean Sea`); after winning at Tours in 732 AD, expand from `Septimania` and `Aquitaine` into the adjacent Gallic heartland (`Neustria`, `Burgundy`) without annexing distant German duchies east of the Rhine (`Saxony`, `Thuringia`, `Bavaria`).\n"
                "- Set `countries_absorbed`: [] and `partial_countries`: [] when `historical_provinces` are specified."
            )
            
        if stage_num == 2:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC compounding simulation: This is a BEST-CASE scenario representing maximum plausible expansion across active campaign fronts. "
                "Include all Realistic `historical_provinces` PLUS 1 to 3 additional contiguous historical units bordering the realistic conquests in the active theater (avoid distant off-theater German/Italian realms unless directly part of the campaign). "
                "Set `countries_absorbed`: [] and `partial_countries`: [] when specifying `historical_provinces`."
            )
        else:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC military simulation: This is a BEST-CASE scenario representing maximum plausible expansion within the active conflict theater. "
                "Include all Realistic `historical_provinces` PLUS 1 to 3 additional contiguous historical units bordering the realistic conquests. "
                "Do NOT jump into distant unrelated foreign realms. Set `countries_absorbed`: [] and `partial_countries`: [] when specifying `historical_provinces`."
            )
            
        prompt_vars["ownership_str"] = ownership_str_opt
        opt_prompt = template_real.format(**prompt_vars)
    else:
        opt_prompt = real_prompt
        
    res_opt: ScenarioStateResult = invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=opt_prompt)], temperature=0.25)
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

    if stage_num == 2 and conqueror_polity:
        sh_base_yr, _, _ = _get_resolved_baseline_geometry(conqueror_polity, year_val, context_val.get("target_region", ""))
        if sh_base_yr is not None and not sh_base_yr.is_empty:
            for ov_dict in [baselines_override_real, baselines_override_opt]:
                if isinstance(ov_dict, dict):
                    matched_k = None
                    for k_ov, v_ov in list(ov_dict.items()):
                        if v_ov is not None and (conqueror_polity.lower() in k_ov.lower() or k_ov.lower() in conqueror_polity.lower() or "umayyad" in k_ov.lower()):
                            matched_k = k_ov
                            ov_dict[k_ov] = sh_base_yr.union(v_ov)
                    if matched_k is None:
                        ov_dict[conqueror_polity] = sh_base_yr
                    else:
                        ov_dict[conqueror_polity] = ov_dict[matched_k]

    enforce_additive_optimistic_expansion(
        res_real=res_real,
        res_opt=res_opt,
        year_val=year_val,
        context_val=context_val,
        scenario_val=scenario_val
    )

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


def enforce_additive_optimistic_expansion(
    res_real: ScenarioStateResult,
    res_opt: ScenarioStateResult,
    year_val: int,
    context_val: Dict[str, Any],
    scenario_val: str
) -> None:
    """
    Enforces that:
    1. Realistic and Optimistic conquests are evaluated independently for corridor/enclave holes
       without cross-contaminating each other or causing outward snowball expansion.
    2. Optimistic conquests are strictly additive over Realistic conquests (and expand into 1-2
       adjacent theater units if identical to Realistic).
    """
    parties_list = context_val.get("parties", []) if context_val else []
    baseline_pols = context_val.get("baseline_polities", []) if context_val else []
    winner_polity = parties_list[0] if parties_list else (baseline_pols[0] if baseline_pols else "")

    scen_lower = scenario_val.lower()
    is_byz_stage = any(k in scen_lower for k in ["constantinople", "byzantine", "byzantium", "anatolia", "thrace"]) and not any(k in scen_lower for k in ["tours", "frank", "poitiers", "gaul", "france"])
    is_frank_stage = any(k in scen_lower for k in ["tours", "frank", "poitiers", "gaul", "france", "aquitaine"]) and not any(k in scen_lower for k in ["constantinople", "byzantine", "byzantium", "anatolia"])

    # Identify conqueror's already-owned baseline units so we never assimilate them as enemy conquests
    conqueror_owned_units = set()
    if winner_polity:
        try:
            res_conq = get_historical_units(winner_polity, year_val, context_val.get("target_region", "") if context_val else "")
            conqueror_owned_units = set(res_conq.get("historical_units_map", {}).keys())
        except Exception:
            pass

    # Step 1: Collect candidate historical units from active target polities in the current stage's theater
    h_map_all = {}
    active_search_pols = set(
        (context_val.get("all_baseline_polities", []) if context_val else []) + 
        baseline_pols + 
        (context_val.get("parties", []) if context_val else [])
    )
    if context_val and "geojson_before" in context_val and isinstance(context_val["geojson_before"], dict):
        for feat in context_val["geojson_before"].get("features", []):
            f_props = feat.get("properties", {})
            for k in ["canonical_name", "name", "original_polity"]:
                v = f_props.get(k)
                if v and isinstance(v, str):
                    clean_v = v.split("(")[0].strip()
                    active_search_pols.add(v)
                    if clean_v:
                        active_search_pols.add(clean_v)

    if any(k in scen_lower or k in (context_val.get("target_region", "") if context_val else "").lower() for k in ["vienna", "austria", "habsburg", "wien", "hungary"]):
        active_search_pols.update(["Archduchy of Austria", "Kingdom of Hungary"])

    for bp in active_search_pols:
        bp_low = bp.lower()
        if bp_low == winner_polity.lower() or (winner_polity and winner_polity.lower() in bp_low):
            continue
        if is_byz_stage and "frank" in bp_low:
            continue
        if is_frank_stage and ("byzant" in bp_low or "eastern roman" in bp_low):
            continue
        try:
            res_hist = get_historical_units(bp, year_val, context_val.get("target_region", "") if context_val else "")
            for u_k, u_v in res_hist.get("historical_units_map", {}).items():
                if u_k not in conqueror_owned_units and u_v and not u_v.is_empty:
                    h_map_all[u_k] = u_v
        except Exception:
            pass

    # Resolve winner's baseline geometry for frontier contact measurement (including Stage 1 + 732 AD union if in Stage 2)
    winner_base_sh = None
    if context_val:
        for ov_key in ["stage2_baselines", "compounding_baselines_real", "compounding_resolved_geoms_real", "compounding_resolved_geoms"]:
            ov_dict = context_val.get(ov_key)
            if isinstance(ov_dict, dict):
                for k_ov, v_ov in ov_dict.items():
                    if v_ov is not None and (winner_polity.lower() in k_ov.lower() or k_ov.lower() in winner_polity.lower()):
                        winner_base_sh = v_ov
                        break
            if winner_base_sh is not None:
                break
    if winner_base_sh is None and winner_polity:
        try:
            from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
            w_sh, _, _ = _get_resolved_baseline_geometry(winner_polity, year_val, context_val.get("target_region", "") if context_val else "")
            if w_sh is not None and not w_sh.is_empty:
                winner_base_sh = w_sh
        except Exception:
            pass
    if winner_base_sh is None and winner_polity:
        try:
            from backend.tools.baseline_resolver import cliopatria_db
            w_feat = cliopatria_db.get_polity_geometry(winner_polity, year_val)
            if w_feat and w_feat.get("geometry"):
                winner_base_sh = shape(w_feat["geometry"])
        except Exception:
            pass

    def _lookup_unit_geom(u_name: str):
        if u_name in h_map_all:
            return h_map_all[u_name]
        for hk, hgeom in h_map_all.items():
            if u_name.lower() in hk.lower() or hk.lower() in u_name.lower():
                return hgeom
        return None

    def _seal_corridor_and_enclave_gaps(target_t: TerritoryChange, label: str) -> None:
        """
        Independently seals genuine corridor gaps and surrounded enclaves for a single scenario (`realistic` or `optimistic`):
        - Pass 1 (Corridor & Pocket Assimilation): Assimilates a candidate unit if:
            (a) >= 65% of its boundary is surrounded by the active front (baseline + current target_t units), OR
            (b) >= 42% of its boundary touches the active front AND it touches BOTH the conqueror baseline AND at least one conquered unit (direct stepping-stone bridge), OR
            (c) >= 48% of its boundary touches the active front AND its centroid lies strictly inside the bounding box of the conquered units (or between the frontier and the conquered units), preventing outward peripheral expansion.
        - Pass 2 (Strict Interior Hole Seal Only): Assimilates any remaining multi-unit pocket hole (e.g. Croatia after Slavonia & Bosnia are added) only if >= 62% of its perimeter is surrounded by the active front.
        """
        if not getattr(target_t, "historical_provinces", None) or not h_map_all:
            return

        for gap_pass in range(2):
            current_units = list(target_t.historical_provinces)
            current_clean = {u.strip().replace("_", " ") for u in current_units}
            conquered_geoms = [g for g in (_lookup_unit_geom(u) for u in current_units) if g and not g.is_empty]
            if not conquered_geoms:
                break

            conquered_union = unary_union(conquered_geoms)
            active_geoms = ([winner_base_sh] if (winner_base_sh and not winner_base_sh.is_empty) else []) + conquered_geoms
            active_front = unary_union(active_geoms)
            front_buf = active_front.buffer(0.02)

            # Compute corridor envelope between baseline frontier near conquered units and the conquered units
            corridor_env = conquered_union.envelope.buffer(0.5)
            if winner_base_sh and not winner_base_sh.is_empty:
                try:
                    near_frontier = winner_base_sh.intersection(conquered_union.buffer(4.5))
                    if near_frontier and not near_frontier.is_empty:
                        corridor_env = unary_union([conquered_union, near_frontier]).envelope.buffer(0.25)
                except Exception:
                    pass

            candidates_to_add = []
            for cand_name, cand_sh in h_map_all.items():
                clean_cand = cand_name.strip().replace("_", " ")
                if clean_cand in current_clean or not cand_sh or cand_sh.is_empty:
                    continue
                # Never auto-assimilate distant peripheral Bohemian/Silesian crown lands or trans-Rhine German duchies as gaps
                cand_low = clean_cand.lower()
                if any(ex in cand_low for ex in ["bohemia", "silesia", "saxony", "thuringia", "bavaria", "swabia"]):
                    continue
                try:
                    bnd = cand_sh.boundary
                    if not bnd or bnd.is_empty or bnd.length <= 0:
                        continue
                    shared = bnd.intersection(front_buf)
                    shared_len = shared.length if shared else 0.0
                    ratio = shared_len / bnd.length

                    if gap_pass == 0:
                        touches_base = bool(winner_base_sh and not winner_base_sh.is_empty and cand_sh.distance(winner_base_sh) <= 0.05)
                        touches_conq = bool(cand_sh.distance(conquered_union) <= 0.05)
                        in_corridor = bool(corridor_env.contains(cand_sh.centroid))

                        if ratio >= 0.65 or (ratio >= 0.42 and touches_base and touches_conq and in_corridor) or (ratio >= 0.58 and touches_conq and in_corridor):
                            candidates_to_add.append((cand_name, ratio))
                    else:
                        # Pass 2: Strict interior pocket/hole seal only (e.g. Croatia surrounded by Bosnia, Slavonia, Inner Austria)
                        touches_conq = bool(cand_sh.distance(conquered_union) <= 0.05)
                        if ratio >= 0.60 and touches_conq:
                            candidates_to_add.append((cand_name, ratio))
                except Exception:
                    pass

            if not candidates_to_add:
                break

            candidates_to_add.sort(key=lambda x: x[1], reverse=True)
            for gap_u, r_val in candidates_to_add:
                if gap_u not in target_t.historical_provinces:
                    print(f"[SIMULATOR-ALGO] Assimilating corridor/enclave unit '{gap_u}' (surrounded ratio: {r_val*100:.1f}%, pass {gap_pass+1}) into {label} conquest.", flush=True)
                    target_t.historical_provinces.append(gap_u)

    for t_opt in res_opt.territories:
        for t_real in res_real.territories:
            if t_opt.name.lower() == t_real.name.lower() or (winner_polity and winner_polity.lower() in t_opt.name.lower()):
                # 1. Seal corridor/enclave gaps in Realistic independently first
                _seal_corridor_and_enclave_gaps(t_real, "realistic")

                # 2. Ensure Optimistic includes all Realistic units (additive invariant) before sealing Optimistic gaps
                for r_u in (getattr(t_real, "historical_provinces", []) or []):
                    if r_u not in t_opt.historical_provinces:
                        t_opt.historical_provinces.append(r_u)

                # 3. Seal corridor/enclave gaps in Optimistic independently
                _seal_corridor_and_enclave_gaps(t_opt, "optimistic")

                h_opt_clean = {p.strip().replace("_", " ") for p in (getattr(t_opt, "historical_provinces", []) or [])}
                h_real_clean = {p.strip().replace("_", " ") for p in (getattr(t_real, "historical_provinces", []) or [])}

                # Check if Constantinople/Thrace was conquered in 717 AD without any European/Aegean expansion in Optimistic
                needs_euro_bridgehead = (
                    is_byz_stage
                    and any("constantinople" in u.lower() or "thrace" in u.lower() for u in h_opt_clean)
                    and not any(eu in u.lower() for u in h_opt_clean for eu in ["illyricum", "aegean", "macedonia", "hellas", "dalmatia"])
                )

                # 4. Topological Adjacency Expansion Fallback if Optimistic is still identical to Realistic (or lacks European bridgehead after Constantinople)
                if h_opt_clean.issubset(h_real_clean) or len(h_opt_clean) <= len(h_real_clean) or needs_euro_bridgehead:
                    real_geoms = [g for g in (_lookup_unit_geom(k) for k in t_opt.historical_provinces) if g and not g.is_empty]
                    if not real_geoms:
                        real_geoms = [g for g in (_lookup_unit_geom(k) for k in t_real.historical_provinces) if g and not g.is_empty]
                    if not real_geoms and winner_base_sh and not winner_base_sh.is_empty:
                        real_geoms.append(winner_base_sh)

                    candidate_adjacent = []
                    if real_geoms:
                        real_union = unary_union(real_geoms)
                        real_buf = real_union.buffer(0.05)
                        ranked_neighbors = []
                        for cand_key, cand_geom in h_map_all.items():
                            clean_cand = cand_key.strip().replace("_", " ")
                            cand_low = clean_cand.lower()
                            if any(ex in cand_low for ex in ["bohemia", "silesia", "saxony", "thuringia", "bavaria", "swabia", "sicily", "italy"]):
                                continue
                            if clean_cand not in h_opt_clean and clean_cand not in h_real_clean and cand_geom and not cand_geom.is_empty:
                                try:
                                    bnd = cand_geom.boundary
                                    if bnd and not bnd.is_empty:
                                        shared = bnd.intersection(real_buf)
                                        shared_len = shared.length if shared else 0.0
                                        if shared_len > 0:
                                            ranked_neighbors.append((cand_key, shared_len))
                                except Exception:
                                    pass
                        ranked_neighbors.sort(key=lambda x: x[1], reverse=True)
                        candidate_adjacent = [k for k, _ in ranked_neighbors[:2]]

                    if not candidate_adjacent:
                        ref_geom = unary_union(real_geoms) if real_geoms else winner_base_sh
                        if ref_geom and not ref_geom.is_empty:
                            dist_neighbors = []
                            for cand_key, cand_geom in h_map_all.items():
                                clean_cand = cand_key.strip().replace("_", " ")
                                cand_low = clean_cand.lower()
                                if any(ex in cand_low for ex in ["bohemia", "silesia", "saxony", "thuringia", "bavaria", "swabia"]):
                                    continue
                                if clean_cand not in h_opt_clean and clean_cand not in h_real_clean and cand_geom and not cand_geom.is_empty:
                                    dist_neighbors.append((cand_key, cand_geom.distance(ref_geom)))
                            dist_neighbors.sort(key=lambda x: x[1])
                            candidate_adjacent = [k for k, _ in dist_neighbors[:2]]

                    if candidate_adjacent:
                        print(f"[SIMULATOR-ALGO] Programmatically expanding optimistic conquest into top topological neighbors: {candidate_adjacent}.", flush=True)
                        for app_u in candidate_adjacent:
                            if app_u not in t_opt.historical_provinces:
                                t_opt.historical_provinces.append(app_u)
                        if not res_opt.alternate_outcome.endswith("(Deep Expansion)"):
                            res_opt.alternate_outcome += f" In this optimistic best-case expansion, campaigns also secured {', '.join(candidate_adjacent)}."


_run_conquest_sim = run_conquest_sim

