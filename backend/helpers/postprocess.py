"""
Post-processing guardrails and resolution helpers for Geopolitico simulation engine.
"""

from typing import List, Dict, Any, Optional
from backend.models.schemas import TerritoryChange, PartialRegion
from backend.tools.country_polygons import get_country_polygon_loader


def force_conquest_provinces(territories: List[TerritoryChange], scenario_text: str):
    """Post-processing guardrail to dynamically ensure focal scenario cities are included in the victor's conquests via GIS spatial index (Zero hardcoded dictionaries)."""
    loader = get_country_polygon_loader()
    victor_t = territories[0] if territories else None
    if not victor_t:
        return
        
    if not hasattr(victor_t, "historical_provinces") or victor_t.historical_provinces is None:
        victor_t.historical_provinces = []
        
    scenario_lower = scenario_text.lower()
    
    # Dynamically scan loader.provinces_data for any city or province named in scenario_text
    for feat_data in loader.provinces_data:
        props = feat_data.get("properties", {})
        name = props.get("name", "")
        assigned_unit = props.get("assigned_unit", "")
        
        if not name:
            continue
            
        clean_name = name.split("(")[0].strip()
        if len(clean_name) >= 4 and clean_name.lower() in scenario_lower:
            target_unit = assigned_unit if assigned_unit else clean_name
            if target_unit and target_unit not in victor_t.historical_provinces:
                victor_t.historical_provinces.append(target_unit)


def resolve_modern_cities_to_historical_units(territories: List[TerritoryChange], year: int, context: Optional[Dict[str, Any]] = None):
    """
    4-Step Resolution Chain for LLM output:
    1. Scan items in t.historical_provinces (e.g. 'Istanbul', 'Edirne', 'Bordeaux', 'Septimania').
    2. Check if item is already a canonical historical unit name across all scenario polities.
    3. If NOT a canonical unit name, search loader.provinces_data for matching modern city/province.
    4. Lookup its precomputed historical 'assigned_unit' and replace raw city names with canonical historical unit names.
    """
    from backend.tools.baseline_resolver import get_historical_units
    loader = get_country_polygon_loader()
    
    all_scenario_pols = list(set((context.get("parties", []) if context else []) + (context.get("baseline_polities", []) if context else []) + ["Franks", "Umayyad", "Byzantine", "Ottoman", "Kingdom of the Franks", "Umayyad Caliphate", "Byzantine Empire"]))
    
    canonical_units_map = {}
    city_to_unit_map = {}
    
    for bp in all_scenario_pols:
        res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
        h_map = res_hist.get("historical_units_map", {})
        for k in h_map.keys():
            canonical_units_map[k.lower()] = k
            
        for sub_p in res_hist.get("provinces_core", []) + res_hist.get("provinces_edge", []):
            sp_name = sub_p.get("name", "").lower()
            assigned_u = sub_p.get("assigned_unit")
            if sp_name and assigned_u:
                city_to_unit_map[sp_name] = assigned_u
                if "(" in sp_name:
                    clean_name = sp_name.split("(")[0].strip().lower()
                    city_to_unit_map[clean_name] = assigned_u

    for t in territories:
        raw_list = getattr(t, "historical_provinces", [])
        if not raw_list:
            continue
            
        resolved_units = []
        for item in raw_list:
            item_lower = item.strip().lower()
            
            # 1. Direct match against canonical historical units
            if item_lower in canonical_units_map:
                resolved_units.append(canonical_units_map[item_lower])
                continue
                
            # Partial substring match against canonical historical units
            matched_canonical = None
            for c_lower, orig_c in canonical_units_map.items():
                if item_lower in c_lower or c_lower in item_lower:
                    matched_canonical = orig_c
                    break
            if matched_canonical:
                resolved_units.append(matched_canonical)
                continue
                
            # 2. Check city_to_unit_map (e.g. 'istanbul' -> 'Opsikion Theme')
            if item_lower in city_to_unit_map:
                resolved_units.append(city_to_unit_map[item_lower])
                print(f"[SIMULATOR] Resolved modern city '{item}' -> parent historical unit '{city_to_unit_map[item_lower]}'", flush=True)
                continue
                
            # 3. Check loader.provinces_data for matching province name
            found_unit = None
            for feat in loader.provinces_data:
                props = feat.get("properties", {})
                prov_n = (props.get("name") or "").lower()
                admin_n = (props.get("admin") or "").lower()
                if item_lower == prov_n or item_lower in prov_n or item_lower == f"{prov_n} ({admin_n})":
                    if prov_n in city_to_unit_map:
                        found_unit = city_to_unit_map[prov_n]
                        break
                        
            if found_unit:
                resolved_units.append(found_unit)
                print(f"[SIMULATOR] Resolved modern province '{item}' -> parent historical unit '{found_unit}'", flush=True)
            else:
                resolved_units.append(item)
                
        t.historical_provinces = list(dict.fromkeys(resolved_units))
