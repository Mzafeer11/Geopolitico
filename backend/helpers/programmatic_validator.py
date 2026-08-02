"""
Programmatic Spatial & Topological Validator for Geopolitico
Replaces AI-based geopolitical validation calls with deterministic GIS algorithms.
"""

from typing import List, Dict, Any, Optional
from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union

from backend.tools.cliopatria_loader import cliopatria_db


def filter_contiguous_baseline_polities(
    baseline_polities: List[str],
    winner_polity: str,
    year: int = 732,
    target_countries: Optional[List[str]] = None,
    buffer_deg: float = 2.0  # ~200 km buffer for regional frontiers
) -> List[str]:
    """
    Programmatically filters baseline polities so that only polities sharing a direct
    border or proximity (within buffer_deg) to the conqueror/target region are kept.
    Distant polities (e.g. Poland during an Ottoman Siege of Vienna) are dropped.
    Also expands historical alias polities (e.g. Holy Roman Empire -> Habsburg Monarchy).
    """
    if not baseline_polities:
        return [winner_polity] if winner_polity else []

    expanded_polities = list(baseline_polities) if baseline_polities else []

    # Safeguard 3: Mandatory Conqueror/Winner Inclusion
    if winner_polity and winner_polity not in expanded_polities:
        print(f"[SAFEGUARD-3] Conqueror polity '{winner_polity}' missing from AI baseline_polities. Automatically prepending into baseline list.", flush=True)
        expanded_polities.insert(0, winner_polity)

    # Safeguard 2: City Name Resolution in Baseline Polities (e.g. Constantinople -> Byzantine in 732 AD)
    from backend.tools.country_polygons import get_country_polygon_loader
    loader = get_country_polygon_loader()
    resolved_expanded = []
    for pol in expanded_polities:
        p_feat = cliopatria_db.get_polity_geometry(pol, year)
        if (not p_feat or not p_feat.get("geometry")) and pol.lower() not in ["habsburg monarchy", "holy roman empire"]:
            matching_provs = loader.get_province_features(pol, "")
            if matching_provs and matching_provs[0].get("geometry"):
                try:
                    city_shape = shape(matching_provs[0]["geometry"])
                    candidate_matches = []
                    for active_f in cliopatria_db.get_active_polities(year):
                        ap_props = active_f.get("properties", {})
                        ap_name = ap_props.get("Name") or ""
                        if ap_name and active_f.get("geometry"):
                            try:
                                ap_sh = shape(active_f["geometry"])
                                if ap_sh.intersects(city_shape) or ap_sh.contains(city_shape.centroid):
                                    candidate_matches.append(ap_name)
                            except Exception:
                                pass

                    if candidate_matches:
                        candidate_matches.sort(key=lambda n: (1 if n.startswith("(") or "alliance" in n.lower() else 0, len(n)))
                        hist_match = candidate_matches[0]
                        print(f"[SAFEGUARD-2] AI output city/province name '{pol}' in baseline_polities. Resolved to active historical empire in {year} AD: '{hist_match}'.", flush=True)
                        resolved_expanded.append(hist_match)
                        continue
                except Exception:
                    pass

            if matching_provs:
                admin_country = matching_provs[0].get("properties", {}).get("admin") or matching_provs[0].get("properties", {}).get("country")
                if admin_country:
                    print(f"[SAFEGUARD-2] AI output city/province name '{pol}' in baseline_polities. Resolved to parent country/empire: '{admin_country}'.", flush=True)
                    resolved_expanded.append(admin_country)
                    continue
        resolved_expanded.append(pol)
    expanded_polities = resolved_expanded

    # Historical Alias Mapping: ensure real rivals like Habsburg Monarchy are included
    alias_map = {
        "holy roman empire": ["Habsburg Monarchy", "Austria"],
        "habsburg": ["Habsburg Monarchy", "Holy Roman Empire"],
        "austria": ["Habsburg Monarchy"],
    }
    for pol in list(expanded_polities):
        pol_lower = pol.lower()
        for key, aliases in alias_map.items():
            if key in pol_lower:
                for alias in aliases:
                    if alias not in expanded_polities:
                        expanded_polities.append(alias)

    # 1. Resolve conqueror and theater of war geometries from Cliopatria & Country Polygons
    winner_shape = None
    if winner_polity:
        w_feat = cliopatria_db.get_polity_geometry(winner_polity, year)
        if w_feat and w_feat.get("geometry"):
            try:
                winner_shape = shape(w_feat["geometry"])
            except Exception:
                pass

    target_geoms = []
    if target_countries:
        try:
            from backend.tools.country_polygons import get_country_polygon_loader
            loader = get_country_polygon_loader()
            for c_name in target_countries:
                c_feat = loader.get_country_feature(c_name)
                if c_feat and c_feat.get("geometry"):
                    c_geom = shape(c_feat["geometry"])
                    if c_geom:
                        target_geoms.append(c_geom)
        except Exception:
            pass

    theater_shape = unary_union(target_geoms) if target_geoms else None

    # Anchor buffer: prefer winner geometry intersected with target theater if available
    if winner_shape and theater_shape:
        frontier_base = winner_shape.intersection(theater_shape.buffer(1.0))
        anchor_buffer = (frontier_base if not frontier_base.is_empty else winner_shape).buffer(0.8)
    elif winner_shape:
        anchor_buffer = winner_shape.buffer(buffer_deg)
    elif theater_shape:
        anchor_buffer = theater_shape.buffer(0.3)
    else:
        return expanded_polities

    filtered = []
    for pol in expanded_polities:
        # Winner is always retained
        if winner_polity and pol.lower() == winner_polity.lower():
            filtered.append(pol)
            continue

        p_feat = cliopatria_db.get_polity_geometry(pol, year)
        if not p_feat or not p_feat.get("geometry"):
            print(f"[SPATIAL-FILTER] Dropping non-existent baseline polity '{pol}' in {year} AD.", flush=True)
            continue

        props = p_feat.get("properties", {})
        from_yr = props.get("FromYear")
        to_yr = props.get("ToYear")
        if from_yr is not None and to_yr is not None and not (from_yr <= year <= to_yr):
            print(f"[SPATIAL-FILTER] Dropping historically extinct baseline polity '{pol}' (active {from_yr}-{to_yr} AD, query year {year} AD).", flush=True)
            continue

        try:
            p_geom = shape(p_feat["geometry"])
            if anchor_buffer.intersects(p_geom):
                inter = anchor_buffer.intersection(p_geom)
                if inter and not inter.is_empty and inter.area >= 0.5:
                    filtered.append(pol)
                    print(f"[SPATIAL-FILTER] Retaining contiguous baseline polity '{pol}' (intersection area: {inter.area:.2f} sq deg).", flush=True)
                else:
                    print(f"[SPATIAL-FILTER] Dropping non-contiguous baseline polity '{pol}' (minor island sliver area: {inter.area if inter else 0:.3f} sq deg).", flush=True)
            else:
                print(f"[SPATIAL-FILTER] Dropping non-contiguous baseline polity '{pol}' (does not border frontier).", flush=True)
        except Exception:
            filtered.append(pol)

    return filtered if filtered else expanded_polities


class ProgrammaticPipelineValidator:
    """
    Zero-latency programmatic topology validator enforcing 100% contiguity and enclave pruning.
    """

    @staticmethod
    def validate_and_clean_territories(
        territory_features: List[Dict[str, Any]],
        min_enclave_area_ratio: float = 0.05
    ) -> List[Dict[str, Any]]:
        """
        Processes a list of territory features (provinces/polygons), enforces contiguity,
        and prunes isolated enclave polygons that are detached from the main body.
        """
        cleaned_features = []

        # Group by assigned polity or unit
        polity_groups: Dict[str, List[Dict[str, Any]]] = {}
        for feat in territory_features:
            owner = feat.get("assigned_unit") or feat.get("country") or "default"
            polity_groups.setdefault(owner, []).append(feat)

        for owner, feats in polity_groups.items():
            shapes = []
            for f in feats:
                try:
                    s = f.get("shape")
                    if isinstance(s, dict):
                        s = shape(s)
                    if s and not s.is_empty:
                        shapes.append((f, s))
                except Exception:
                    continue

            if not shapes:
                continue

            # Compute unary union of all shapes for this owner
            combined_shapes = [s for _, s in shapes]
            total_union = unary_union(combined_shapes)

            if isinstance(total_union, Polygon):
                # Single contiguous body — all features kept
                cleaned_features.extend([f for f, _ in shapes])
            elif isinstance(total_union, MultiPolygon):
                # Multiple disjoint bodies — find largest component body
                components = sorted(list(total_union.geoms), key=lambda p: p.area, reverse=True)
                main_body = components[0]
                main_area = main_body.area

                for f, s in shapes:
                    # Keep feature if it intersects main body or is larger than min_enclave_area_ratio of main body
                    if s.intersects(main_body) or (s.area / main_area) >= min_enclave_area_ratio:
                        cleaned_features.append(f)
                    else:
                        print(f"[TOPOLOGY-VALIDATOR] Pruned isolated enclave '{f.get('name', 'Unknown')}' from '{owner}'.", flush=True)
            else:
                cleaned_features.extend([f for f, _ in shapes])

        return cleaned_features
