"""
Territory definitions compiler module for Geopolitico simulation engine.
Assembles final GeoJSON polygons from LLM territory definitions,
merging historical baseline shapes and applying additions/subtractions.
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from shapely.geometry import shape, mapping, Polygon, box, LineString, MultiLineString, MultiPolygon
from shapely.ops import unary_union, split, nearest_points

from backend.models.schemas import TerritoryChange, PartialRegion
from backend.tools.country_polygons import get_country_polygon_loader, get_countries_for_natural_boundary
from backend.tools.cliopatria_loader import cliopatria_db
from backend.helpers.llm import invoke_structured_with_fallback
from langchain_core.messages import SystemMessage
from pydantic import BaseModel


def clip_province_geom(prov_geom, boundary_geom, direction, val=None, prov_name=None, territory_desc=None):
    minx, miny, maxx, maxy = prov_geom.bounds
    cx, cy = prov_geom.centroid.x, prov_geom.centroid.y
    
    if direction == "north_of_latitude":
        val = val if val is not None else cy
        split_poly = box(minx, val, maxx, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "south_of_latitude":
        val = val if val is not None else cy
        split_poly = box(minx, miny, maxx, val)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "west_of_longitude":
        val = val if val is not None else cx
        split_poly = box(minx, miny, val, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "east_of_longitude":
        val = val if val is not None else cx
        split_poly = box(val, miny, maxx, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
        
    if boundary_geom:
        is_mentioned = False
        if prov_name and territory_desc:
            p_lower = prov_name.lower()
            desc_lower = territory_desc.lower()
            island_keywords = []
            if "corse" in p_lower or "corsica" in p_lower:
                island_keywords = ["corse", "corsica"]
            elif "baleares" in p_lower or "balearic" in p_lower:
                island_keywords = ["baleares", "balearic", "mallorca", "menorca", "ibiza"]
            elif "sardegna" in p_lower or "sardinia" in p_lower:
                island_keywords = ["sardegna", "sardinia"]
            elif "sicilia" in p_lower or "sicily" in p_lower:
                island_keywords = ["sicilia", "sicily"]
                
            for kw in island_keywords:
                if kw in desc_lower:
                    is_mentioned = True
                    break
                    
        if not is_mentioned:
            try:
                if prov_geom.distance(boundary_geom) > 3.0:
                    return None
            except Exception:
                pass
            
        if boundary_geom.buffer(0.5).intersects(prov_geom):
            try:
                # Extend line endpoints past province bounding box so split() cuts completely across polygon
                ext_b_geom = boundary_geom
                if boundary_geom.geom_type in ["LineString", "MultiLineString"]:
                    diag = ((maxx - minx)**2 + (maxy - miny)**2)**0.5 + 2.0
                    lines_to_ext = [boundary_geom] if boundary_geom.geom_type == "LineString" else list(boundary_geom.geoms)
                    ext_lines = []
                    for ls in lines_to_ext:
                        coords = list(ls.coords)
                        if len(coords) >= 2:
                            dx0, dy0 = coords[0][0] - coords[1][0], coords[0][1] - coords[1][1]
                            len0 = (dx0**2 + dy0**2)**0.5 or 1.0
                            new_start = (coords[0][0] + (dx0/len0)*diag, coords[0][1] + (dy0/len0)*diag)
                            print("I was here")
                            dx1, dy1 = coords[-1][0] - coords[-2][0], coords[-1][1] - coords[-2][1]
                            len1 = (dx1**2 + dy1**2)**0.5 or 1.0
                            new_end = (coords[-1][0] + (dx1/len1)*diag, coords[-1][1] + (dy1/len1)*diag)
                            ext_lines.append(LineString([new_start] + coords + [new_end]))
                    if ext_lines:
                        ext_b_geom = ext_lines[0] if len(ext_lines) == 1 else unary_union(ext_lines)

                split_result = split(prov_geom, ext_b_geom)
                if hasattr(split_result, "geoms") and len(split_result.geoms) > 1:
                    keep_polys = []
                    for sub_poly in split_result.geoms:
                        scy = sub_poly.centroid.y
                        scx = sub_poly.centroid.x
                        p1, p2 = nearest_points(sub_poly.centroid, boundary_geom)
                        local_y = p2.y
                        local_x = p2.x
                        
                        if direction in ["north_of_natural_boundary", "north_of_latitude"] and scy > local_y:
                            keep_polys.append(sub_poly)
                        elif direction in ["south_of_natural_boundary", "south_of_latitude"] and scy < local_y:
                            keep_polys.append(sub_poly)
                        elif direction in ["west_of_natural_boundary", "west_of_longitude"] and scx < local_x:
                            keep_polys.append(sub_poly)
                        elif direction in ["east_of_natural_boundary", "east_of_longitude"] and scx > local_x:
                            keep_polys.append(sub_poly)
                            
                    if keep_polys:
                        res_sh = unary_union(keep_polys)
                        print(f"  [PARTITION-DEBUG] clip_province_geom '{prov_name}': split() succeeded! Kept {len(keep_polys)} sub-polys (dir={direction}, area={res_sh.area:.4f}, bounds={res_sh.bounds})", flush=True)
                        return res_sh
                    else:
                        print(f"  [PARTITION-DEBUG] clip_province_geom '{prov_name}': split() succeeded but zero sub-polys matched direction '{direction}'.", flush=True)
            except Exception as e:
                print(f"  [PARTITION-DEBUG] clip_province_geom '{prov_name}': split() exception: {e}", flush=True)
                
        try:
            p1, p2 = nearest_points(prov_geom.centroid, boundary_geom)
            local_y = p2.y
            local_x = p2.x
            scy = prov_geom.centroid.y
            scx = prov_geom.centroid.x
            
            keep = False
            if direction in ["north_of_natural_boundary", "north_of_latitude"] and scy > local_y:
                keep = True
            elif direction in ["south_of_natural_boundary", "south_of_latitude"] and scy < local_y:
                keep = True
            elif direction in ["west_of_natural_boundary", "west_of_longitude"] and scx < local_x:
                keep = True
            elif direction in ["east_of_natural_boundary", "east_of_longitude"] and scx > local_x:
                keep = True
                
            if keep:
                print(f"  [PARTITION-DEBUG] clip_province_geom '{prov_name}': centroid fallback KEPT whole province (dir={direction}, area={prov_geom.area:.4f})", flush=True)
                return prov_geom
            else:
                print(f"  [PARTITION-DEBUG] clip_province_geom '{prov_name}': centroid fallback DISCARDED province (dir={direction})", flush=True)
        except Exception:
            pass
            
    return None


def _resolve_boundary_geometry(p: Any, context: Optional[Dict[str, Any]], prov_geom: Optional[Any] = None) -> Optional[Any]:
    """
    Robust natural boundary geometry resolver.
    Handles empty clip_description or clip_method="provinces" by checking context['osm_boundaries'] for intersecting rivers/lines.
    """
    b_geom = None
    b_name = getattr(p, "clip_description", "") or ""
    
    if context and "osm_boundaries" in context:
        osm_bounds = context["osm_boundaries"]
        # 1a. Try exact or substring match in osm_boundaries
        if b_name:
            matched_k = next((k for k in osm_bounds if k.lower() in b_name.lower() or b_name.lower() in k.lower()), None)
            if matched_k:
                paths = osm_bounds[matched_k]
                lines = [LineString(pt_list) for pt_list in paths if len(pt_list) >= 2]
                if lines:
                    b_geom = lines[0] if len(lines) == 1 else MultiLineString(lines)
                    
        # 1b. Spatial fallback: if b_name is empty or unmatched, find any loaded boundary intersecting prov_geom
        if not b_geom and prov_geom and not prov_geom.is_empty:
            for k, paths in osm_bounds.items():
                lines = [LineString(pt_list) for pt_list in paths if len(pt_list) >= 2]
                if lines:
                    cand_geom = lines[0] if len(lines) == 1 else MultiLineString(lines)
                    if cand_geom.buffer(0.5).intersects(prov_geom):
                        b_geom = cand_geom
                        break

        # 1c. Direct fallback: if only 1 boundary is pre-loaded in context, use it
        if not b_geom and len(osm_bounds) == 1:
            only_paths = list(osm_bounds.values())[0]
            lines = [LineString(pt_list) for pt_list in only_paths if len(pt_list) >= 2]
            if lines:
                b_geom = lines[0] if len(lines) == 1 else MultiLineString(lines)

    # 2. Fallback to GIS tool lookup with keyword cleaning
    if not b_geom and b_name:
        try:
            from backend.tools.gis_tools import get_natural_boundary_geometry
            clean_b = b_name.split(";")[0].split("-")[0].strip()
            for kw in ["chenab", "loire", "pyrenees", "pyrénées", "rhine", "danube", "bosphorus"]:
                if kw in b_name.lower():
                    clean_b = (kw.capitalize() + " River") if kw in ["chenab", "loire", "rhine", "danube"] else kw.capitalize()
                    break
            b_geom, _ = get_natural_boundary_geometry(clean_b)
        except Exception:
            pass

    return b_geom


def process_territory_definitions(territories: List[TerritoryChange], year: int, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Assemble final GeoJSON polygons from LLM territory definitions,
    merging their historical baseline shapes and applying additions/subtractions.
    """
    if context is not None:
        context["map_markers"] = []
        
    loader = get_country_polygon_loader()
    
    # Step 1: Pre-process shared provinces
    mode = context.get("simulation_mode") if context else "expansion_conquest"
    shared_provinces = {}
    if mode != "expansion_conquest":
        for t in territories:
            for p_raw in (t.partial_countries or []):
                p = PartialRegion(**p_raw) if isinstance(p_raw, dict) else p_raw
                for prov in (p.provinces or []):
                    shared_provinces.setdefault(prov, []).append((t.name, p.country, prov))
                
    split_instructions = {}
    for t in territories:
        for p_raw in (t.partial_countries or []):
            p = PartialRegion(**p_raw) if isinstance(p_raw, dict) else p_raw
            for sp in (p.split_provinces or []):
                sp_name = sp.get("name") if isinstance(sp, dict) else getattr(sp, "name", "")
                if sp_name:
                    split_instructions[(t.name, sp_name)] = sp
                    split_instructions[(t.name, sp_name.lower())] = sp
                    clean_sp = sp_name.split("(")[0].strip()
                    split_instructions[(t.name, clean_sp)] = sp
                    split_instructions[(t.name, clean_sp.lower())] = sp
                
    polity_additions_shapes = {t.name: [] for t in territories}
    
    is_conquest = (mode in ["expansion_conquest", "compounding_conquest"])
    parties_list = context.get("parties", []) if context else []
    baseline_pols = context.get("baseline_polities", []) if context else []
    winner_polity = (context.get("winner_polity") if context else None) or (parties_list[0] if parties_list else (baseline_pols[0] if baseline_pols else None))
    
    for t in territories:
        has_additions = bool(getattr(t, "historical_provinces", []) or getattr(t, "countries_absorbed", []) or getattr(t, "partial_countries", []))
        is_winner = True
        if is_conquest and winner_polity:
            is_winner = (winner_polity.lower() in t.name.lower() or t.name.lower() in winner_polity.lower())
            
        if is_conquest and not is_winner and not has_additions:
            continue
        
        scen_text = (context.get("scenario", "") if context else "").lower()
        from backend.tools.baseline_resolver import get_historical_units
        baseline_pols = context.get("baseline_polities", []) if context else []
        
        if is_conquest:
            for f_feat in loader.provinces_data:
                p_name = (f_feat.get("properties", {}).get("name") or "").lower()
                if p_name and len(p_name) > 3 and re.search(r'\b' + re.escape(p_name) + r'\b', scen_text):
                    for bp in baseline_pols:
                        res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
                        for sub_p in res_hist.get("provinces_core", []) + res_hist.get("provinces_edge", []):
                            if p_name in sub_p.get("name", "").lower():
                                target_u = sub_p.get("assigned_unit")
                                if target_u and target_u not in getattr(t, "historical_provinces", []):
                                    if not hasattr(t, "historical_provinces") or t.historical_provinces is None:
                                        t.historical_provinces = []
                                    t.historical_provinces.append(target_u)

        if getattr(t, "historical_provinces", []):
            winner_base_sh = None
            stage2_baselines = context.get("stage2_baselines") if context else None
            comp_geoms = context.get("compounding_resolved_geoms") if context else None
            
            if stage2_baselines and (t.name in stage2_baselines or winner_polity in stage2_baselines):
                winner_base_sh = stage2_baselines.get(t.name) or stage2_baselines.get(winner_polity)
            elif comp_geoms and (t.name in comp_geoms or winner_polity in comp_geoms):
                winner_base_sh = comp_geoms.get(t.name) or comp_geoms.get(winner_polity)
                
            if not winner_base_sh:
                polity_to_fetch = winner_polity if (winner_polity and is_winner) else t.name
                feat = cliopatria_db.get_polity_geometry(polity_to_fetch, year)
                if not feat or not feat.get("geometry"):
                    for bp in baseline_pols:
                        if bp.lower() in t.name.lower() or t.name.lower() in bp.lower():
                            feat = cliopatria_db.get_polity_geometry(bp, year)
                            break
                if feat and feat.get("geometry"):
                    try:
                        winner_base_sh = shape(feat["geometry"])
                    except Exception:
                        pass

            h_map_all = {}
            for bp in baseline_pols:
                res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
                h_map_all.update(res_hist.get("historical_units_map", {}))

            # Filter out conqueror baseline territories that were already part of the conqueror's baseline empire
            if is_conquest and is_winner and winner_polity:
                base_units_dict = get_historical_units(winner_polity, year)
                winner_owned_units = set(base_units_dict.get("historical_units_map", {}).keys())
                if getattr(t, "historical_provinces", []):
                    t.historical_provinces = [hp for hp in t.historical_provinces if hp not in winner_owned_units and hp.lower() not in ["ifriqiya", "central maghreb"]]

            if is_conquest and winner_base_sh and not winner_base_sh.is_empty:
                target_polities = [bp for bp in baseline_pols if winner_polity and bp.lower() != winner_polity.lower()]
                candidate_units_shapes = {}
                for tp in target_polities:
                    tp_res = get_historical_units(tp, year, context.get("target_region", "") if context else "")
                    for item_f in (tp_res.get("provinces_core", []) + tp_res.get("provinces_edge", [])):
                        u_name = item_f.get("assigned_unit") or item_f.get("province")
                        u_sh = item_f.get("shape")
                        if u_name and u_sh and not u_sh.is_empty:
                            candidate_units_shapes.setdefault(u_name, []).append(u_sh)

                if year >= 1800:
                    winner_baseline_names = set(b.lower() for b in context.get("baseline_polities", [])) if context else set()
                    for feat in loader.provinces_data:
                        props = feat.get("properties", {})
                        admin = props.get("admin") or ""
                        if admin.lower() in winner_baseline_names:
                            continue
                        reg = props.get("region") or props.get("subregion") or props.get("name")
                        g = feat.get("geometry")
                        if reg and g:
                            try:
                                p_sh = shape(g)
                                clean_reg = reg.split("-")[0].split("(")[0].strip()
                                if clean_reg:
                                    candidate_units_shapes.setdefault(clean_reg, []).append(p_sh)
                            except Exception:
                                pass

                candidate_units_map = {uname: unary_union(sl) for uname, sl in candidate_units_shapes.items()}

                def _get_geom_for_hp(name_str):
                    for h_key, geom in h_map_all.items():
                        if name_str.lower() in h_key.lower() or h_key.lower() in name_str.lower():
                            if geom and not geom.is_empty:
                                return geom
                    for h_key, geom in candidate_units_map.items():
                        if name_str.lower() in h_key.lower() or h_key.lower() in name_str.lower():
                            if geom and not geom.is_empty:
                                return geom
                    matched_feats = loader.get_province_features(name_str, "")
                    g_list = [shape(f["geometry"]) for f in matched_feats if f.get("geometry")]
                    return unary_union(g_list) if g_list else None

                for iter_step in range(5):
                    requested_geoms = []
                    for hp_name in list(t.historical_provinces):
                        g_found = _get_geom_for_hp(hp_name)
                        if g_found and not g_found.is_empty:
                            requested_geoms.append(g_found)

                    connected_body = winner_base_sh
                    changed = True
                    unconnected_geoms = list(requested_geoms)

                    while changed:
                        changed = False
                        still_unconnected = []
                        for g in unconnected_geoms:
                            if connected_body.distance(g) <= 0.05:
                                connected_body = unary_union([connected_body, g])
                                changed = True
                            else:
                                still_unconnected.append(g)
                        unconnected_geoms = still_unconnected

                    if unconnected_geoms:
                        target_isolated = unary_union(unconnected_geoms)
                        from shapely.ops import nearest_points
                        p1, p2 = nearest_points(connected_body, target_isolated)
                        corridor = LineString([p1, p2]).buffer(0.5)

                        best_cand_unit = None
                        best_dist = 999.0
                        for cand_u, cand_geom in candidate_units_map.items():
                            if cand_u not in t.historical_provinces and cand_geom and not cand_geom.is_empty:
                                if corridor.intersects(cand_geom):
                                    d = connected_body.distance(cand_geom) + cand_geom.distance(target_isolated)
                                    if d < best_dist:
                                        best_dist = d
                                        best_cand_unit = cand_u

                        if best_cand_unit:
                            print(f"[COMPILER-GAP] Step {iter_step+1}: Detected disconnected target region (gap distance: {connected_body.distance(target_isolated):.3f} deg). Automatically added intermediate bridging unit: '{best_cand_unit}'.", flush=True)
                            t.historical_provinces.append(best_cand_unit)
                        else:
                            print(f"[COMPILER-GAP WARN] Step {iter_step+1}: Found disconnected region (gap distance: {connected_body.distance(target_isolated):.3f} deg), but no intermediate candidate unit intersected the corridor vector.", flush=True)
                            break
                    else:
                        print(f"[COMPILER-GAP] Step {iter_step+1}: All requested historical provinces are 100% contiguous with conqueror's baseline borders.", flush=True)
                        break

        if getattr(t, "historical_provinces", []):
            h_map = {}
            for bp in baseline_pols:
                res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
                h_map.update(res_hist.get("historical_units_map", {}))
            
            for hp_name in t.historical_provinces:
                hp_found = False
                for h_key, geom in h_map.items():
                    if hp_name.lower() in h_key.lower() or h_key.lower() in hp_name.lower():
                        if geom and not geom.is_empty:
                            polity_additions_shapes[t.name].append(geom)
                            hp_found = True
                            break
                if not hp_found:
                    matched_feats = loader.get_province_features(hp_name, "")
                    for feat_data in matched_feats:
                        g = feat_data.get("geometry")
                        if g:
                            try:
                                polity_additions_shapes[t.name].append(shape(g))
                            except Exception:
                                pass

            if is_conquest:
                t.countries_absorbed = []
                t.partial_countries = []

        expanded_partials = []
        for p_raw in (t.partial_countries or []):
            p = PartialRegion(**p_raw) if isinstance(p_raw, dict) else p_raw
            expanded_partials.append(p)
            if mode != "proposal_partition" and p.clip_method == "natural_boundary" and p.clip_description:
                matched_countries = get_countries_for_natural_boundary(p.clip_description, loader)
                
                existing_countries = [
                    (x.country.lower() if hasattr(x, "country") else x.get("country", "").lower())
                    for x in t.partial_countries
                ]
                absorbed_countries = [x.lower() for x in getattr(t, "countries_absorbed", [])]
                
                for c in matched_countries:
                    if c.lower() not in existing_countries and c.lower() not in absorbed_countries:
                        new_p = PartialRegion(
                            country=c,
                            provinces=[],
                            split_provinces=[],
                            clip_method=p.clip_method,
                            clip_value=p.clip_value,
                            clip_description=p.clip_description,
                            clip_direction=p.clip_direction,
                            landmark_city=None,
                            status=p.status
                        )
                        expanded_partials.append(new_p)
        t.partial_countries = expanded_partials
        
        for country_name in getattr(t, "countries_absorbed", []):
            if mode == "proposal_partition" and (country_name.lower() in t.name.lower() or t.name.lower() in country_name.lower()):
                continue
            for feat_data in loader.provinces_data:
                props = feat_data.get("properties", {})
                admin = props.get("admin", "")
                if admin.lower() == country_name.lower():
                    g = feat_data.get("geometry")
                    if g:
                        try:
                            polity_additions_shapes[t.name].append(shape(g))
                        except Exception:
                            pass
                            
        for p_raw in (t.partial_countries or []):
            p = PartialRegion(**p_raw) if isinstance(p_raw, dict) else p_raw
            country_name = p.country
            
            if getattr(p, "historical_provinces", []):
                h_map = {}
                for bp in baseline_pols:
                    res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
                    h_map.update(res_hist.get("historical_units_map", {}))
                
                for hp_name in p.historical_provinces:
                    hp_found = False
                    clean_hp = hp_name.split("(")[0].strip()
                    sp_key = (t.name, hp_name)
                    sp_inst = split_instructions.get(sp_key) or split_instructions.get((t.name, hp_name.lower())) or split_instructions.get((t.name, clean_hp)) or split_instructions.get((t.name, clean_hp.lower()))
                    
                    for h_key, geom in h_map.items():
                        if hp_name.lower() in h_key.lower() or h_key.lower() in hp_name.lower() or clean_hp.lower() in h_key.lower():
                            if geom and not geom.is_empty:
                                if sp_inst and (sp_inst.is_split if hasattr(sp_inst, "is_split") else sp_inst.get("is_split", False)):
                                    sp_dir = sp_inst.split_direction if hasattr(sp_inst, "split_direction") else sp_inst.get("split_direction")
                                    sp_val = sp_inst.split_value if hasattr(sp_inst, "split_value") else sp_inst.get("split_value")
                                    b_geom = _resolve_boundary_geometry(p, context, geom)
                                    clipped = clip_province_geom(geom, b_geom, sp_dir, sp_val, prov_name=hp_name, territory_desc=t.description)
                                    if clipped and not clipped.is_empty:
                                        polity_additions_shapes[t.name].append(clipped)
                                else:
                                    polity_additions_shapes[t.name].append(geom)
                                hp_found = True
                                break
                    if not hp_found:
                        matched_feats = loader.get_province_features(hp_name, country_name) or loader.get_province_features(clean_hp, country_name)
                        for feat_data in matched_feats:
                            g = feat_data.get("geometry")
                            if g:
                                try:
                                    prov_sh = shape(g)
                                    if sp_inst and (sp_inst.is_split if hasattr(sp_inst, "is_split") else sp_inst.get("is_split", False)):
                                        sp_dir = sp_inst.split_direction if hasattr(sp_inst, "split_direction") else sp_inst.get("split_direction")
                                        sp_val = sp_inst.split_value if hasattr(sp_inst, "split_value") else sp_inst.get("split_value")
                                        b_geom = _resolve_boundary_geometry(p, context, prov_sh)
                                        clipped = clip_province_geom(prov_sh, b_geom, sp_dir, sp_val, prov_name=hp_name, territory_desc=t.description)
                                        if clipped and not clipped.is_empty:
                                            polity_additions_shapes[t.name].append(clipped)
                                    else:
                                        polity_additions_shapes[t.name].append(prov_sh)
                                except Exception:
                                    pass
                continue
            
            for prov_name in (p.provinces or []):
                matched_feats = loader.get_province_features(prov_name, country_name)
                for feat_data in matched_feats:
                    g = feat_data.get("geometry")
                    if not g:
                        continue
                    try:
                        prov_sh = shape(g)
                        sp_key = (t.name, prov_name)
                        sp_inst = split_instructions.get(sp_key)
                        
                        if sp_inst:
                            sp_split = sp_inst.is_split if hasattr(sp_inst, "is_split") else sp_inst.get("is_split", False)
                            sp_dir = sp_inst.split_direction if hasattr(sp_inst, "split_direction") else sp_inst.get("split_direction")
                            sp_val = sp_inst.split_value if hasattr(sp_inst, "split_value") else sp_inst.get("split_value")
                        else:
                            sp_split = False
                            sp_dir = None
                            sp_val = None
                            
                        if sp_split:
                            b_geom = _resolve_boundary_geometry(p, context, prov_sh)
                            clipped = clip_province_geom(
                                prov_sh, b_geom, sp_dir, sp_val,
                                prov_name=prov_name, territory_desc=t.description
                            )
                            if clipped and not clipped.is_empty:
                                polity_additions_shapes[t.name].append(clipped)
                        else:
                            polity_additions_shapes[t.name].append(prov_sh)
                    except Exception as e:
                        print(f"[WARN] Error parsing shape for province '{prov_name}': {e}")
                        
            if mode != "proposal_partition" and p.clip_method in ["natural_boundary", "coordinate_latitude", "coordinate_longitude"] and not p.provinces and not getattr(p, "historical_provinces", []):
                country_feat = loader.get_country_feature(country_name)
                if country_feat:
                    c_provinces = [f for f in loader.provinces_data if f.get("properties", {}).get("admin", "").lower() == country_name.lower()]
                    
                    b_geom = _resolve_boundary_geometry(p, context, shape(country_feat["geometry"]) if country_feat.get("geometry") else None)
                                
                    if not c_provinces:
                        try:
                            country_sh = shape(country_feat["geometry"])
                            clipped = clip_province_geom(
                                country_sh, b_geom, p.clip_direction, p.clip_value,
                                prov_name=country_name, territory_desc=t.description
                            )
                            if clipped and not clipped.is_empty:
                                polity_additions_shapes[t.name].append(clipped)
                        except Exception:
                            pass
                    else:
                        added_provinces = []
                        for prov_f in c_provinces:
                            g = prov_f.get("geometry")
                            p_name = prov_f.get("properties", {}).get("name", "")
                            if g:
                                try:
                                    prov_sh = shape(g)
                                    clipped = clip_province_geom(
                                        prov_sh, b_geom, p.clip_direction, p.clip_value,
                                        prov_name=p_name, territory_desc=t.description
                                    )
                                    if clipped and not clipped.is_empty:
                                        polity_additions_shapes[t.name].append(clipped)
                                        if p_name:
                                            added_provinces.append(p_name)
                                except Exception:
                                    pass
                        if added_provinces:
                            print(f"[NATURAL-BOUNDARY] '{p.clip_description}' ({p.clip_direction}) annexed {len(added_provinces)} modern provinces in {country_name}: {', '.join(added_provinces)}", flush=True)

        if getattr(t, "historical_provinces", []):
            h_map = {}
            search_pols = list(set(baseline_pols + (context.get("parties", []) if context else []) + (context.get("all_baseline_polities", []) if context else [])))
            for bp in search_pols:
                res_hist = get_historical_units(bp, year, context.get("target_region", "") if context else "")
                h_map.update(res_hist.get("historical_units_map", {}))
                
            for hp_name in t.historical_provinces:
                for h_key, geom in h_map.items():
                    if hp_name.lower() in h_key.lower() or h_key.lower() in hp_name.lower():
                        if geom and not geom.is_empty:
                            polity_additions_shapes[t.name].append(geom)
                            break

    # Step 2: Merge baseline geometry with additions geometry
    from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
    
    resolved_territories = []
    baseline_polities = context.get("baseline_polities", []) if context else []
    
    for t in territories:
        base_sh = None
        actual_name = t.name
        
        stage2_baselines = context.get("stage2_baselines") if context else None
        comp_geoms = context.get("compounding_resolved_geoms") if context else None
        
        if stage2_baselines:
            for sb_key, sb_geom in stage2_baselines.items():
                if t.name.lower() in sb_key.lower() or sb_key.lower() in t.name.lower():
                    base_sh = sb_geom
                    break
        elif comp_geoms:
            for cg_key, cg_geom in comp_geoms.items():
                if t.name.lower() in cg_key.lower() or cg_key.lower() in t.name.lower():
                    base_sh = cg_geom
                    break
            
        if not base_sh:
            if actual_name not in baseline_polities:
                for bp in baseline_polities:
                    if bp.lower() in t.name.lower() or t.name.lower() in bp.lower():
                        actual_name = bp
                        break
            
            if actual_name in baseline_polities:
                hist_geom, _, tier = _get_resolved_baseline_geometry(actual_name, year, context.get("target_region", "") if context else "")
                base_sh = hist_geom
            else:
                sh_base, _, tier = _get_resolved_baseline_geometry(actual_name, year, context.get("target_region", "") if context else "")
                base_sh = sh_base
            
        additions_shapes = polity_additions_shapes.get(t.name, [])
        additions_union = unary_union(additions_shapes) if additions_shapes else None
        
        resolved_territories.append({
            "definition": t,
            "actual_name": actual_name,
            "base_geom": base_sh,
            "additions_geom": additions_union,
            "final_geom": None
        })

    is_conquest = (mode in ["expansion_conquest", "compounding_conquest"])
    winner_item = None
    if is_conquest and winner_polity:
        for item in resolved_territories:
            if winner_polity.lower() in item["definition"].name.lower() or item["definition"].name.lower() in winner_polity.lower():
                winner_item = item
                break

    for item in resolved_territories:
        t = item["definition"]
        base_sh = item["base_geom"]
        add_sh = item["additions_geom"]
        
        if is_conquest:
            if winner_item and item == winner_item:
                comb_shapes = []
                if base_sh and not base_sh.is_empty:
                    comb_shapes.append(base_sh)
                if add_sh and not add_sh.is_empty:
                    comb_shapes.append(add_sh)
                item["final_geom"] = unary_union(comb_shapes) if comb_shapes else None
            else:
                winner_add = winner_item["additions_geom"] if winner_item else None
                if base_sh and not base_sh.is_empty:
                    if winner_add and not winner_add.is_empty:
                        try:
                            diff_sh = base_sh.difference(winner_add.buffer(0.001))
                            item["final_geom"] = diff_sh if diff_sh and not diff_sh.is_empty else None
                        except Exception:
                            item["final_geom"] = base_sh
                    else:
                        item["final_geom"] = base_sh
                else:
                    item["final_geom"] = None
        else:
            comb_shapes = []
            if base_sh and not base_sh.is_empty:
                comb_shapes.append(base_sh)
            if add_sh and not add_sh.is_empty:
                comb_shapes.append(add_sh)
            item["final_geom"] = unary_union(comb_shapes) if comb_shapes else None

    # Mutual subtraction for partition mode
    if mode == "proposal_partition":
        print(f"[PARTITION-DEBUG] Running mutual subtraction for {len(resolved_territories)} territories...", flush=True)
        for i, item_i in enumerate(resolved_territories):
            t_name = item_i["definition"].name
            base_area = item_i["base_geom"].area if item_i["base_geom"] else 0
            add_area = item_i["additions_geom"].area if item_i["additions_geom"] else 0
            print(f"[PARTITION-DEBUG] Pre-subtraction for '{t_name}': Base Area={base_area:.4f}, Additions Area={add_area:.4f}", flush=True)

            final_sh = item_i["final_geom"]
            if not final_sh or final_sh.is_empty:
                continue
            for j, item_j in enumerate(resolved_territories):
                if i == j:
                    continue
                other_name = item_j["definition"].name
                other_add = item_j["additions_geom"]
                if other_add and not other_add.is_empty:
                    try:
                        final_sh = final_sh.difference(other_add.buffer(0.001))
                        print(f"  [PARTITION-DEBUG] Subtracted '{other_name}' additions (area={other_add.area:.4f}) from '{t_name}' → New Area={final_sh.area:.4f}", flush=True)
                    except Exception as e:
                        print(f"  [PARTITION-DEBUG] Error subtracting '{other_name}' from '{t_name}': {e}", flush=True)
            item_i["final_geom"] = final_sh
            print(f"[PARTITION-DEBUG] Final shape for '{t_name}': Area={final_sh.area:.4f}, Bounds={final_sh.bounds}", flush=True)

    # Filter out tiny disconnected island slivers for conquest mode (disabled in partition mode to preserve split border polygons)
    if mode == "proposal_partition":
        for i, item in enumerate(resolved_territories):
            final_sh = item["final_geom"]
            if final_sh and not final_sh.is_empty:
                if final_sh and getattr(final_sh, 'geom_type', None) == 'MultiPolygon':
                    valid_polys = []
                    for p in final_sh.geoms:
                        if p.area < 0.1:
                            near_other = False
                            for j, other_item in enumerate(resolved_territories):
                                if i == j:
                                    continue
                                other_base = other_item["base_geom"]
                                other_add = other_item["additions_geom"]
                                if other_base and p.distance(other_base) < 0.1:
                                    near_other = True
                                    break
                                if other_add and p.distance(other_add) < 0.1:
                                    near_other = True
                                    break
                            if near_other:
                                continue
                        valid_polys.append(p)
                    final_sh = MultiPolygon(valid_polys) if valid_polys else None
                item["final_geom"] = final_sh
        
    features = []
    for item in resolved_territories:
        t = item["definition"]
        final_sh = item["final_geom"]
        if not final_sh or final_sh.is_empty:
            continue
            
        color = t.color
        if not color:
            name_lower = t.name.lower()
            if "umayyad" in name_lower:
                color = "#10b981"
            elif "frank" in name_lower or "caroling" in name_lower:
                color = "#ef4444"
            elif "byzant" in name_lower:
                color = "#8b5cf6"
            elif "india" in name_lower:
                color = "#fbbf24"
            elif "pakistan" in name_lower:
                color = "#047857"
            else:
                color = "#d4a853"
            
        status_val = "direct_control" if t.status in ["direct_control", "conquered", "vassal"] else t.status
        features.append({
            "type": "Feature",
            "properties": {
                "name": t.name,
                "color": color,
                "fill_color": color,
                "status": status_val,
                "description": t.description,
                "capital": t.capital,
                "population": t.population_estimate
            },
            "geometry": mapping(final_sh)
        })
        
    if context is not None:
        compounding_resolved = context.get("compounding_resolved_geoms")
        if compounding_resolved is not None:
            compounding_resolved.clear()
            baseline_polities = context.get("baseline_polities", [])
            for item in resolved_territories:
                t = item["definition"]
                actual_name = t.name
                if actual_name not in baseline_polities:
                    for bp in baseline_polities:
                        if bp.lower() in t.name.lower() or t.name.lower() in bp.lower():
                            actual_name = bp
                            break
                final_sh = item["final_geom"]
                if final_sh and not final_sh.is_empty:
                    compounding_resolved[t.name] = final_sh
                    compounding_resolved[actual_name] = final_sh
        
    return features


_process_territory_definitions = process_territory_definitions
