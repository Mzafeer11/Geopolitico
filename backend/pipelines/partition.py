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

    # Partition Guardrails: Clear countries_absorbed / historical_provinces and enforce natural boundary partitioning
    scenario_lower = scenario.lower()
    osm_bounds = state.get("osm_boundaries") or {}
    loaded_b_name = next(iter(osm_bounds.keys()), None) if osm_bounds else None
    loaded_b_geom = None
    corridor_provs_by_country = {}

    assigned_dirs = {}
    is_east_west = True
    if loaded_b_name and not ("chenab" in scenario_lower or "kashmir" in scenario_lower):
        try:
            from shapely.geometry import shape, LineString, MultiLineString
            from backend.tools.country_polygons import get_country_polygon_loader
            paths = osm_bounds[loaded_b_name]
            lines = [LineString(pt_list) for pt_list in paths if len(pt_list) >= 2]
            if lines:
                loaded_b_geom = lines[0] if len(lines) == 1 else MultiLineString(lines)
                loader = get_country_polygon_loader()

                # Pre-calculate assigned directions for general natural boundary partitions to guarantee opposing sides
                OPPOSITE_DIR = {
                    "north_of_natural_boundary": "south_of_natural_boundary",
                    "south_of_natural_boundary": "north_of_natural_boundary",
                    "west_of_natural_boundary": "east_of_natural_boundary",
                    "east_of_natural_boundary": "west_of_natural_boundary"
                }
                b_bounds = loaded_b_geom.bounds
                dx = b_bounds[2] - b_bounds[0]
                dy = b_bounds[3] - b_bounds[1]
                is_east_west = (dx >= dy)

                for t in res.territories:
                    t_desc = (t.description or "").lower()
                    t_name_lower = t.name.lower()
                    chosen_dir = None

                    # 1. Check description and name keywords
                    if is_east_west:
                        if "north" in t_desc and "south" not in t_desc:
                            chosen_dir = "north_of_natural_boundary"
                        elif "south" in t_desc and "north" not in t_desc:
                            chosen_dir = "south_of_natural_boundary"
                        elif "pakistan" in t_name_lower:
                            chosen_dir = "north_of_natural_boundary"
                        elif "india" in t_name_lower:
                            chosen_dir = "south_of_natural_boundary"
                    else:
                        if "west" in t_desc and "east" not in t_desc:
                            chosen_dir = "west_of_natural_boundary"
                        elif "east" in t_desc and "west" not in t_desc:
                            chosen_dir = "east_of_natural_boundary"
                        elif "france" in t_name_lower:
                            chosen_dir = "west_of_natural_boundary"
                        elif "germany" in t_name_lower:
                            chosen_dir = "east_of_natural_boundary"

                    # 2. Check explicit split_provinces / clip_direction from LLM if consistent
                    if not chosen_dir:
                        for p_raw in (t.partial_countries or []):
                            p_obj = PartialRegion(**p_raw) if isinstance(p_raw, dict) else p_raw
                            c_dir = p_obj.clip_direction
                            if c_dir in OPPOSITE_DIR:
                                chosen_dir = c_dir
                                break

                    # 3. Fallback to geometric centroid of territory's baseline
                    if not chosen_dir:
                        try:
                            from backend.tools.baseline_resolver import _get_resolved_baseline_geometry, _calculate_boundary_direction
                            b_sh, _, _ = _get_resolved_baseline_geometry(t.name, year)
                            if b_sh and not b_sh.is_empty:
                                chosen_dir = _calculate_boundary_direction(b_sh, loaded_b_geom)
                        except Exception:
                            pass

                    if chosen_dir:
                        assigned_dirs[t.name] = chosen_dir

                # Ensure opposing sides in a 2-party treaty
                if len(res.territories) == 2:
                    t0, t1 = res.territories[0], res.territories[1]
                    d0 = assigned_dirs.get(t0.name)
                    d1 = assigned_dirs.get(t1.name)
                    if d0 and not d1:
                        assigned_dirs[t1.name] = OPPOSITE_DIR.get(d0, "south_of_natural_boundary")
                    elif d1 and not d0:
                        assigned_dirs[t0.name] = OPPOSITE_DIR.get(d1, "north_of_natural_boundary")
                    elif d0 and d1 and d0 == d1:
                        # Disambiguate conflict using relative baseline centroids
                        try:
                            from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
                            sh0, _, _ = _get_resolved_baseline_geometry(t0.name, year)
                            sh1, _, _ = _get_resolved_baseline_geometry(t1.name, year)
                            if sh0 and sh1:
                                if is_east_west:
                                    if sh0.centroid.y >= sh1.centroid.y:
                                        assigned_dirs[t0.name] = "north_of_natural_boundary"
                                        assigned_dirs[t1.name] = "south_of_natural_boundary"
                                    else:
                                        assigned_dirs[t0.name] = "south_of_natural_boundary"
                                        assigned_dirs[t1.name] = "north_of_natural_boundary"
                                else:
                                    if sh0.centroid.x <= sh1.centroid.x:
                                        assigned_dirs[t0.name] = "west_of_natural_boundary"
                                        assigned_dirs[t1.name] = "east_of_natural_boundary"
                                    else:
                                        assigned_dirs[t0.name] = "east_of_natural_boundary"
                                        assigned_dirs[t1.name] = "west_of_natural_boundary"
                        except Exception:
                            assigned_dirs[t1.name] = OPPOSITE_DIR.get(d0, "south_of_natural_boundary")

                cand_countries = list(dict.fromkeys([
                    (p.get("country", "") if isinstance(p, dict) else getattr(p, "country", ""))
                    for t_item in res.territories
                    for p in (t_item.partial_countries or [])
                    if (p.get("country", "") if isinstance(p, dict) else getattr(p, "country", ""))
                ]))
                if not cand_countries:
                    cand_countries = list(state.get("target_countries") or [])

                # Collect all province names explicitly mentioned by the LLM
                llm_named_provs = {}
                for t_item in res.territories:
                    for p in (t_item.partial_countries or []):
                        c_nm = p.get("country", "") if isinstance(p, dict) else getattr(p, "country", "")
                        p_list = p.get("provinces", []) if isinstance(p, dict) else getattr(p, "provinces", [])
                        sp_list = p.get("split_provinces", []) if isinstance(p, dict) else getattr(p, "split_provinces", [])
                        names = list(p_list) + [
                            sp.get("name") if isinstance(sp, dict) else getattr(sp, "name", "")
                            for sp in sp_list
                        ]
                        if c_nm:
                            llm_named_provs.setdefault(c_nm.lower(), set()).update([
                                n.split("(")[0].strip().lower() for n in names if n
                            ])

                # Discover intersecting corridor provinces and frontier shapes
                intersecting_by_c = {}
                intersecting_shapes = []
                for c_name in cand_countries:
                    for f in loader.provinces_data:
                        props = f.get("properties", {})
                        admin = props.get("admin", "")
                        pname = props.get("name", "")
                        if pname and admin and (c_name.lower() in admin.lower() or admin.lower() in c_name.lower()):
                            g = f.get("geometry")
                            if g:
                                try:
                                    psh = shape(g)
                                    if psh.intersects(loaded_b_geom.buffer(0.05)):
                                        intersecting_by_c.setdefault(c_name, []).append((pname, psh))
                                        intersecting_shapes.append(psh)
                                except Exception:
                                    pass

                for c_name in cand_countries:
                    c_provs = []
                    named_set = llm_named_provs.get(c_name.lower(), set())
                    c_dir = assigned_dirs.get(c_name)

                    # 1. Primary: Provinces directly intersecting the boundary
                    for pname, psh in intersecting_by_c.get(c_name, []):
                        if pname not in c_provs:
                            c_provs.append(pname)

                    # 2. Secondary & Trans-boundary cut-off provinces:
                    # In frontier zone that lie ENTIRELY on opposing side of river
                    # (e.g. Jammu & Kashmir and Ladakh north of Sutlej River when Sutlej is boundary; or Saarland west of Rhine)
                    # OR provinces explicitly requested by LLM near frontier.
                    for f in loader.provinces_data:
                        props = f.get("properties", {})
                        admin = props.get("admin", "")
                        pname = props.get("name", "")
                        if pname and admin and (c_name.lower() in admin.lower() or admin.lower() in c_name.lower()) and pname not in c_provs:
                            g = f.get("geometry")
                            if g:
                                try:
                                    psh = shape(g)
                                    dist_river = psh.distance(loaded_b_geom)
                                    explicitly_named = any(pname.lower() in n or n in pname.lower() for n in named_set)
                                    if explicitly_named and dist_river <= 1.2:
                                        c_provs.append(pname)
                                    elif dist_river <= 3.5 and intersecting_shapes and any(psh.distance(ish) <= 0.8 for ish in intersecting_shapes):
                                        from shapely.ops import nearest_points
                                        p1, p2 = nearest_points(psh.centroid, loaded_b_geom)
                                        is_on_opposing_side = False

                                        # Check baseline centroid of country to ensure province is truly cut off from its own mainland
                                        c_base_geom = None
                                        try:
                                            from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
                                            c_base_geom, _, _ = _get_resolved_baseline_geometry(c_name, year)
                                        except Exception:
                                            pass

                                        if c_base_geom and not c_base_geom.is_empty:
                                            if is_east_west:
                                                c_side = (c_base_geom.centroid.y > loaded_b_geom.centroid.y)
                                                p_side = (psh.centroid.y > p2.y)
                                                if p_side != c_side:
                                                    is_on_opposing_side = True
                                            else:
                                                c_side = (c_base_geom.centroid.x > loaded_b_geom.centroid.x)
                                                p_side = (psh.centroid.x > p2.x)
                                                if p_side != c_side:
                                                    is_on_opposing_side = True
                                        else:
                                            if is_east_west:
                                                if c_dir == "south_of_natural_boundary" and psh.centroid.y > p2.y:
                                                    is_on_opposing_side = True
                                                elif c_dir == "north_of_natural_boundary" and psh.centroid.y < p2.y:
                                                    is_on_opposing_side = True
                                            else:
                                                if c_dir == "east_of_natural_boundary" and psh.centroid.x < p2.x:
                                                    is_on_opposing_side = True
                                                elif c_dir == "west_of_natural_boundary" and psh.centroid.x > p2.x:
                                                    is_on_opposing_side = True

                                        if is_on_opposing_side:
                                            c_provs.append(pname)
                                except Exception:
                                    pass

                    if c_provs:
                        corridor_provs_by_country[c_name] = c_provs
                print(f"[PARTITION-DEBUG] Corridor provinces for '{loaded_b_name}': {corridor_provs_by_country}", flush=True)
        except Exception as e_corr:
            print(f"[WARN] River corridor province discovery error: {e_corr}", flush=True)

    for t in res.territories:
        t.countries_absorbed = []
        t.historical_provinces = []
        
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
        elif loaded_b_name and loaded_b_geom and corridor_provs_by_country:
            # General natural boundary partition guardrail for any river/mountain range (e.g. Sutlej River, Rhine River)
            t_dir = assigned_dirs.get(t.name)
            if t_dir:
                new_partials = []
                for c_name, c_provs in corridor_provs_by_country.items():
                    new_partials.append(
                        PartialRegion(
                            country=c_name,
                            provinces=c_provs,
                            historical_provinces=[],
                            split_provinces=[
                                SplitProvince(name=p_name, is_split=True, split_direction=t_dir) for p_name in c_provs
                            ],
                            clip_method="natural_boundary",
                            clip_description=loaded_b_name,
                            clip_direction=t_dir,
                            status="direct_control"
                        )
                    )
                t.partial_countries = new_partials
                print(f"[PARTITION-DEBUG] General river guardrail applied for '{t.name}': {len(new_partials)} partial region(s) set ({loaded_b_name}, {t_dir}).", flush=True)

    print("[PARTITION-DEBUG] Calling process_territory_definitions...", flush=True)
    realistic_features = process_territory_definitions(res.territories, year, state)
    print(f"[PARTITION-DEBUG] process_territory_definitions returned {len(realistic_features)} GeoJSON features.", flush=True)
    
    results = {
        "title": res.title,
        "scenario_mode": "proposal_partition",
        "mode": "proposal_partition",
        "pipeline": "proposal_partition",
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
