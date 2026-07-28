"""
Post-processing guardrails and resolution helpers for Geopolitico simulation engine.
"""

from typing import List, Dict, Any, Optional
from backend.models.schemas import TerritoryChange, PartialRegion
from backend.tools.country_polygons import get_country_polygon_loader


def force_conquest_provinces(territories: List[TerritoryChange], scenario_text: str):
    """Post-processing guardrail to ensure critical scenario cities are added to territories."""
    scenario_lower = scenario_text.lower()
    umayyad_t = None
    for t in territories:
        if "umayyad" in t.name.lower():
            umayyad_t = t
            break
            
    if umayyad_t:
        if "constantinople" in scenario_lower:
            if not hasattr(umayyad_t, "historical_provinces") or umayyad_t.historical_provinces is None:
                umayyad_t.historical_provinces = []
            for h_unit in ["Istanbul", "Opsikion Theme", "Thrace Theme"]:
                if h_unit not in umayyad_t.historical_provinces:
                    umayyad_t.historical_provinces.append(h_unit)
                    
            turkey_p = None
            for p in umayyad_t.partial_countries:
                if p.country.lower() == "turkey":
                    turkey_p = p
                    break
            else:
                turkey_p = PartialRegion(country="Turkey", provinces=[], split_provinces=[], clip_method="provinces", clip_description="Conquered Byzantine Capital")
                umayyad_t.partial_countries.append(turkey_p)
            if "Istanbul (Turkey)" not in turkey_p.provinces:
                turkey_p.provinces.append("Istanbul (Turkey)")
        if "tours" in scenario_lower or "poitiers" in scenario_lower:
            france_p = None
            for p in umayyad_t.partial_countries:
                if p.country.lower() == "france":
                    france_p = p
                    break
            else:
                france_p = PartialRegion(country="France", provinces=[], split_provinces=[], clip_method="provinces", clip_description="Conquered Tours region")
                umayyad_t.partial_countries.append(france_p)
            for f_prov in ["Vienne (France)", "Indre (France)", "Indre-et-Loire (France)", "Haute-Vienne (France)", "Deux-Sèvres (France)"]:
                if f_prov not in france_p.provinces:
                    france_p.provinces.append(f_prov)
                    
    # General post-processing to fully absorb countries on the conquered side of natural boundaries
    NATURAL_BOUNDARY_CONQUEST_ABSORB = {
        "rhine": {
            "west_of_natural_boundary": ["France", "Belgium", "Luxembourg"],
            "east_of_natural_boundary": ["Germany", "Switzerland", "Austria", "Netherlands"]
        },
        "danube": {
            "south_of_natural_boundary": ["Bulgaria", "Greece", "Turkey", "North Macedonia", "Albania", "Kosovo", "Montenegro", "Bosnia and Herzegovina"],
            "north_of_natural_boundary": ["Romania", "Moldova", "Ukraine", "Slovakia", "Hungary", "Austria"]
        },
        "loire": {
            "south_of_natural_boundary": ["Spain", "Portugal"]
        },
        "pyrenees": {
            "south_of_natural_boundary": ["Spain", "Portugal"]
        }
    }
    
    for t in territories:
        countries_to_absorb = set()
        for p in t.partial_countries:
            if p.clip_method == "natural_boundary" and p.clip_description:
                desc_lower = p.clip_description.lower()
                matched_boundary = None
                for b_name in NATURAL_BOUNDARY_CONQUEST_ABSORB:
                    if b_name in desc_lower:
                        matched_boundary = b_name
                        break
                if matched_boundary:
                    direction = p.clip_direction
                    absorb_list = NATURAL_BOUNDARY_CONQUEST_ABSORB[matched_boundary].get(direction, [])
                    for country_name in absorb_list:
                        countries_to_absorb.add(country_name)
                        
        if countries_to_absorb:
            for c in countries_to_absorb:
                is_in_partials = any(p.country.lower() == c.lower() for p in t.partial_countries)
                if is_in_partials:
                    if c not in t.countries_absorbed:
                        t.countries_absorbed.append(c)
            t.partial_countries = [p for p in t.partial_countries if p.country.lower() not in [x.lower() for x in countries_to_absorb]]


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
