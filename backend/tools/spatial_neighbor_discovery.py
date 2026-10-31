"""
Spatial Neighbor Discovery & Conflict Theater Decomposition Engine for Geopolitico.
Deterministically computes ground-truth bordering polities from Cliopatria GIS data
and isolates theater-specific constituent entities for composite monarchies and personal unions.
"""

from typing import List, Dict, Any, Optional, Tuple
from shapely.geometry import shape, mapping, box, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

from backend.tools.cliopatria_loader import cliopatria_db, normalize_name
from backend.tools.country_polygons import get_country_polygon_loader


def construct_theater_mask(
    target_countries: Optional[List[str]] = None,
    target_anchor_city: Optional[str] = None,
    buffer_deg: float = 1.5
) -> Optional[Any]:
    """
    Constructs a geographic conflict theater mask polygon using target country polygons
    or a radial buffer around a key anchor city.
    """
    loader = get_country_polygon_loader()
    geoms = []

    if target_countries:
        for c_name in target_countries:
            c_feat = loader.get_country_feature(c_name)
            if c_feat and c_feat.get("geometry"):
                try:
                    s = shape(c_feat["geometry"])
                    if s and not s.is_empty:
                        geoms.append(s)
                except Exception:
                    pass

    if target_anchor_city:
        matched_provs = loader.get_province_features(target_anchor_city, "")
        for p in matched_provs:
            if p.get("geometry"):
                try:
                    s = shape(p["geometry"])
                    if s and not s.is_empty:
                        geoms.append(s.centroid.buffer(buffer_deg + 2.0))
                except Exception:
                    pass

    if geoms:
        return unary_union(geoms).buffer(buffer_deg)
    return None


def discover_spatial_neighbors(
    focus_polity: str,
    year: int,
    target_countries: Optional[List[str]] = None,
    target_anchor_city: Optional[str] = None,
    frontier_buffer_deg: float = 0.5,
    min_frontier_area: float = 0.05
) -> Dict[str, Any]:
    """
    Deterministically discovers all physically bordering polities for a focus polity in Cliopatria at year.
    Decomposes composite personal unions and filters candidates against the active conflict theater.
    """
    focus_feat = cliopatria_db.get_polity_geometry(focus_polity, year)
    if not focus_feat or not focus_feat.get("geometry"):
        return {
            "focus_polity": focus_polity,
            "year": year,
            "status": "focus_not_found",
            "frontier_neighbors": [],
            "theater_neighbors": [],
            "decomposed_union_neighbors": []
        }

    try:
        focus_shape = shape(focus_feat["geometry"])
    except Exception:
        return {
            "focus_polity": focus_polity,
            "year": year,
            "status": "invalid_focus_geometry",
            "frontier_neighbors": [],
            "theater_neighbors": [],
            "decomposed_union_neighbors": []
        }

    # Frontier buffer to detect shared borders and immediate maritime straits
    frontier_buffer = focus_shape.buffer(frontier_buffer_deg)
    theater_mask = construct_theater_mask(target_countries, target_anchor_city)

    active_polities = cliopatria_db.get_active_polities(year)
    norm_focus = normalize_name(focus_polity)

    frontier_candidates = []
    seen_names = set()

    for feat in active_polities:
        props = feat.get("properties", {})
        p_name = props.get("Name", "")
        if not p_name:
            continue
        # Skip allegiance meta-labels like '(Allegiance of X to Y)'
        if p_name.startswith("(") and " to " in p_name:
            continue

        clean_name = p_name.strip("()")
        norm_cand = normalize_name(p_name)
        if norm_cand == norm_focus or norm_focus in norm_cand:
            continue

        if p_name in seen_names:
            continue

        g = feat.get("geometry")
        if not g:
            continue

        try:
            cand_shape = shape(g)
            if not cand_shape or cand_shape.is_empty:
                continue

            if frontier_buffer.intersects(cand_shape):
                inter = frontier_buffer.intersection(cand_shape)
                inter_area = inter.area if inter else 0.0

                if inter_area >= min_frontier_area:
                    seen_names.add(p_name)
                    in_theater = False
                    theater_contact_area = 0.0

                    if theater_mask:
                        if cand_shape.intersects(theater_mask):
                            th_inter = cand_shape.intersection(theater_mask)
                            in_theater = bool(th_inter and not th_inter.is_empty)
                            theater_contact_area = th_inter.area if th_inter else 0.0
                    else:
                        in_theater = True
                        theater_contact_area = inter_area

                    frontier_candidates.append({
                        "name": p_name,
                        "clean_name": clean_name,
                        "frontier_contact_area": round(inter_area, 3),
                        "total_area": round(cand_shape.area, 2),
                        "in_theater": in_theater,
                        "theater_contact_area": round(theater_contact_area, 3),
                        "bounds": cand_shape.bounds,
                        "is_composite_union": False
                    })
        except Exception:
            continue

    # Sort frontier candidates by theater relevance first, then total frontier contact
    frontier_candidates.sort(key=lambda x: (1 if x["in_theater"] else 0, x["theater_contact_area"], x["frontier_contact_area"]), reverse=True)

    # Decompose composite unions & personal unions
    decomposed_theater_polities = []
    added_decomposed = set()

    for cand in frontier_candidates:
        c_name = cand["name"]
        rel_info = cliopatria_db.get_overarching_relationship(c_name, year)

        if rel_info.get("has_relation"):
            cand["is_composite_union"] = True
            children = rel_info.get("children", [])
            for child in children:
                ch_feat = cliopatria_db.get_polity_geometry(child, year)
                if ch_feat and ch_feat.get("geometry"):
                    try:
                        ch_sh = shape(ch_feat["geometry"])
                        ch_in_theater = False
                        ch_th_area = 0.0
                        if theater_mask:
                            if ch_sh.intersects(theater_mask):
                                ch_inter = ch_sh.intersection(theater_mask)
                                ch_in_theater = bool(ch_inter and not ch_inter.is_empty)
                                ch_th_area = ch_inter.area if ch_inter else 0.0
                        else:
                            ch_in_theater = True
                            ch_th_area = ch_sh.area

                        # Only include child if it physically intersects the conflict theater
                        if ch_in_theater and child not in added_decomposed:
                            added_decomposed.add(child)
                            decomposed_theater_polities.append({
                                "name": child,
                                "parent_relation": c_name,
                                "theater_contact_area": round(ch_th_area, 3),
                                "total_area": round(ch_sh.area, 2),
                                "bounds": ch_sh.bounds
                            })
                    except Exception:
                        pass
        else:
            if cand["in_theater"] and cand["name"] not in added_decomposed:
                added_decomposed.add(cand["name"])
                decomposed_theater_polities.append({
                    "name": cand["name"],
                    "parent_relation": None,
                    "theater_contact_area": cand["theater_contact_area"],
                    "total_area": cand["total_area"],
                    "bounds": cand["bounds"]
                })

    return {
        "focus_polity": focus_polity,
        "year": year,
        "status": "success",
        "frontier_neighbors": frontier_candidates,
        "theater_neighbors": [c for c in frontier_candidates if c["in_theater"]],
        "decomposed_theater_polities": decomposed_theater_polities
    }
