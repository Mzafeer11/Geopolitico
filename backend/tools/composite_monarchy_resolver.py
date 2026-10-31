"""
Composite Monarchy & Theater-Bounded Resolver for Geopolitico.

Handles:
1. Auto-computation of conflict theater bounding boxes based on participating polities.
2. Decomposition of multi-continental / composite monarchy geometries (e.g., Kingdom of Spain holding Austria + Iberia + Americas)
   into theater-relevant contiguous landmass components.
3. Component selection prioritized by border-sharing with the opposing/winner polity and distance to the conflict anchor.
4. Polity merging for personal unions (e.g., Habsburg Monarchy + Austrian Spain -> "Habsburg Lands (1529)").
"""

from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import shape, mapping, Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union

from backend.tools.cliopatria_loader import cliopatria_db, normalize_name


def auto_compute_theater_radius(
    polity_geoms: List[Any],
    min_radius: float = 8.0,
    max_radius: float = 40.0
) -> float:
    """
    Auto-compute the theater bounding box radius based on the combined spatial extent
    of participating conflict polities.
    """
    valid_geoms = [g for g in polity_geoms if g is not None and not g.is_empty]
    if not valid_geoms:
        return 15.0

    try:
        combined = unary_union(valid_geoms)
        minx, miny, maxx, maxy = combined.bounds
        dx = maxx - minx
        dy = maxy - miny
        diag = (dx**2 + dy**2)**0.5
        radius = diag * 0.45
        return max(min_radius, min(max_radius, radius))
    except Exception:
        return 15.0


def extract_theater_box(
    anchor_lat: float,
    anchor_lon: float,
    radius_deg: float = 15.0
) -> Polygon:
    """
    Create a bounding box polygon centered at (anchor_lat, anchor_lon) with a given radius in degrees.
    """
    min_lon = max(-180.0, anchor_lon - radius_deg)
    max_lon = min(180.0, anchor_lon + radius_deg)
    min_lat = max(-90.0, anchor_lat - radius_deg)
    max_lat = min(90.0, anchor_lat + radius_deg)
    return box(min_lon, min_lat, max_lon, max_lat)


def detect_composite_polity(geom: Any, dispersion_threshold_km: float = 600.0) -> bool:
    """
    Detect if a geometry is a composite / multi-continental polygon with disconnected parts
    widely separated geographically.
    """
    if geom is None or geom.is_empty:
        return False

    if geom.geom_type != "MultiPolygon":
        return False

    geoms = list(geom.geoms)
    if len(geoms) <= 1:
        return False

    # Check pairwise centroid distances
    centroids = [g.centroid for g in geoms if g.area > 0.05]
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            # Rough distance in degrees to km approx
            dx = (centroids[i].x - centroids[j].x) * 85.0
            dy = (centroids[i].y - centroids[j].y) * 111.0
            dist_km = (dx**2 + dy**2)**0.5
            if dist_km >= dispersion_threshold_km:
                return True

    return False


def decompose_composite_polygon(
    polity_geom: Any,
    anchor_point: Optional[Point] = None,
    theater_box: Optional[Polygon] = None,
    winner_geom: Optional[Any] = None,
    max_ratio: float = 2.5
) -> Any:
    """
    Given a composite polity polygon (e.g. Kingdom of Spain covering Iberia + Austria + Americas),
    extract and return only the geographic component(s) relevant to the scenario theater.
    
    Priority Rules:
    1. Clip components to theater_box if provided.
    2. Prioritize components that share a border or intersect with the winner / opposing polity (Rule Q3).
    3. Secondarily rank by distance to the anchor point (e.g. Vienna).
    4. Discard distant peripheral/overseas components outside the conflict theater.
    """
    if polity_geom is None or polity_geom.is_empty:
        return polity_geom

    # Collect individual polygon pieces
    if polity_geom.geom_type == "Polygon":
        components = [polity_geom]
    elif polity_geom.geom_type == "MultiPolygon":
        components = list(polity_geom.geoms)
    elif polity_geom.geom_type == "GeometryCollection":
        components = [g for g in polity_geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        # Flatten MultiPolygons
        flat = []
        for g in components:
            if g.geom_type == "MultiPolygon":
                flat.extend(list(g.geoms))
            else:
                flat.append(g)
        components = flat
    else:
        return polity_geom

    if not components:
        return polity_geom

    # If single component and no theater box, return as is
    if len(components) == 1 and theater_box is None:
        return components[0]

    # Step 1: Clip each component to the theater box (if provided)
    theater_components = []
    for comp in components:
        if comp.is_empty or comp.area < 0.001:
            continue

        if theater_box is not None:
            clipped = comp.intersection(theater_box)
            if not clipped.is_empty and clipped.area > 0.005:
                theater_components.append((comp, clipped))
        else:
            theater_components.append((comp, comp))

    if not theater_components:
        # If none intersect the theater box, find the component closest to anchor
        if anchor_point is not None:
            sorted_by_anchor = sorted(components, key=lambda c: c.centroid.distance(anchor_point))
            return sorted_by_anchor[0]
        return components[0]

    # Step 2: Evaluate components based on border-sharing with winner_geom and distance to anchor
    scored_components = []
    for raw_comp, clipped_comp in theater_components:
        border_sharing_score = 0.0
        dist_to_winner = 999.0

        if winner_geom is not None and not winner_geom.is_empty:
            try:
                if raw_comp.intersects(winner_geom):
                    inter = raw_comp.intersection(winner_geom)
                    border_length = inter.length if hasattr(inter, 'length') else 0.0
                    border_sharing_score = 1000.0 + border_length * 100.0
                    dist_to_winner = 0.0
                else:
                    dist_to_winner = raw_comp.distance(winner_geom)
                    border_sharing_score = max(0.0, 500.0 - dist_to_winner * 20.0)
            except Exception:
                pass

        dist_to_anchor = 999.0
        if anchor_point is not None:
            dist_to_anchor = raw_comp.centroid.distance(anchor_point)

        # Composite score: higher border-sharing and closer to anchor wins
        total_score = border_sharing_score - (dist_to_anchor * 10.0)
        scored_components.append({
            "raw": raw_comp,
            "clipped": clipped_comp,
            "border_score": border_sharing_score,
            "dist_anchor": dist_to_anchor,
            "dist_winner": dist_to_winner,
            "score": total_score
        })

    # Sort descending by score
    scored_components.sort(key=lambda x: x["score"], reverse=True)

    # Step 3: Keep the best component and any adjacent/connected components in the theater
    best = scored_components[0]
    kept_geoms = [best["clipped"]]

    # Keep other theater components if they are within max_ratio distance from anchor or share border with winner
    for item in scored_components[1:]:
        is_adjacent_or_border = (item["border_score"] > 500.0) or (anchor_point and item["dist_anchor"] <= best["dist_anchor"] * max_ratio)
        if is_adjacent_or_border and item["clipped"].area > 0.02:
            kept_geoms.append(item["clipped"])

    if len(kept_geoms) == 1:
        return kept_geoms[0]
    else:
        return unary_union(kept_geoms)


def merge_theater_polities(
    polities_dict: Dict[str, Any],
    anchor_point: Optional[Point] = None,
    theater_box: Optional[Polygon] = None,
    year: int = 1529
) -> Dict[str, Any]:
    """
    Merge personal union / dynastic components in the theater into unified historical entities.
    E.g. In 1529:
      "Habsburg Monarchy" (Vienna) + "Kingdom of Spain" (Austrian Alpine lands)
      -> Merged into "Habsburg Lands (1529)" for the theater.
    """
    # Check for known personal union relations around 1529
    merged_results = {}
    consumed_keys = set()

    # Specific historical handler for Habsburg / Spanish union in Central Europe
    is_habsburg_austria_scenario = False
    habsburg_shape = None
    spain_shape = None

    for name, p_info in polities_dict.items():
        norm = normalize_name(name)
        if "habsburg" in norm:
            habsburg_shape = p_info.get("geometry")
        elif "spain" in norm:
            spain_shape = p_info.get("geometry")

    # General algorithmic check: if both polities have active components in this theater that touch or overlap
    if habsburg_shape is not None and spain_shape is not None:
        dec_sp = decompose_composite_polygon(spain_shape, anchor_point=anchor_point, theater_box=theater_box)
        dec_hab = decompose_composite_polygon(habsburg_shape, anchor_point=anchor_point, theater_box=theater_box)
        if dec_sp is not None and dec_hab is not None and (dec_sp.intersects(dec_hab) or dec_sp.distance(dec_hab) < 0.5):
            is_habsburg_austria_scenario = True

    if is_habsburg_austria_scenario:
        # Decompose both shapes to the Austrian theater component before unioning
        decomposed_spain = decompose_composite_polygon(
            spain_shape,
            anchor_point=anchor_point,
            theater_box=theater_box,
            winner_geom=None
        )
        decomposed_habsburg = decompose_composite_polygon(
            habsburg_shape,
            anchor_point=anchor_point,
            theater_box=theater_box,
            winner_geom=None
        )
        combined_austrian_lands = unary_union([decomposed_habsburg, decomposed_spain])
        synthetic_name = f"Habsburg Lands ({year})"
        
        merged_results[synthetic_name] = {
            "name": synthetic_name,
            "canonical_name": "Archduchy of Austria",
            "geometry": combined_austrian_lands,
            "merged_from": ["Habsburg Monarchy", "Kingdom of Spain"],
            "is_synthetic": True
        }
        for name in list(polities_dict.keys()):
            norm = normalize_name(name)
            if "habsburg" in norm or "spain" in norm:
                consumed_keys.add(name)

    # Pass through remaining polities unchanged
    for name, p_info in polities_dict.items():
        if name not in consumed_keys:
            merged_results[name] = p_info

    return merged_results


def filter_theater_subpolygons(
    geom: Any,
    frontier_buffer: Optional[Any] = None,
    theater_bounds: Optional[Any] = None,
    parent_name: str = ""
) -> Tuple[Optional[Any], str]:
    """
    Given a geometry (potentially a composite/disconnected MultiPolygon like 1529 Spain),
    filter out sub-polygons that do not intersect the conflict frontier or theater.
    
    Returns:
        (filtered_geometry, canonical_label)
    """
    if geom is None or geom.is_empty:
        return None, parent_name

    theater_poly = None
    if theater_bounds is not None:
        if isinstance(theater_bounds, (tuple, list)) and len(theater_bounds) == 4:
            theater_poly = box(*theater_bounds)
        elif hasattr(theater_bounds, "intersects"):
            theater_poly = theater_bounds

    if geom.geom_type == "Polygon":
        is_valid = True
        if frontier_buffer is not None or theater_poly is not None:
            touches_frontier = frontier_buffer is not None and geom.intersects(frontier_buffer)
            in_theater = theater_poly is not None and geom.intersects(theater_poly)
            is_valid = touches_frontier or in_theater
        if not is_valid:
            return None, parent_name
        res_geom = geom
    elif geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        geoms = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        valid_parts = []
        for p in geoms:
            if p.is_empty or p.area < 0.005:
                continue
            touches_frontier = frontier_buffer is not None and p.intersects(frontier_buffer)
            in_theater = theater_poly is not None and p.intersects(theater_poly)
            if touches_frontier or in_theater:
                valid_parts.append(p)
        
        if not valid_parts:
            # Fallback: if none matched both, check frontier alone or theater alone
            if frontier_buffer is not None:
                valid_parts = [p for p in geoms if p.intersects(frontier_buffer)]
            if not valid_parts and theater_poly is not None:
                valid_parts = [p for p in geoms if p.intersects(theater_poly)]
                
        if not valid_parts:
            return None, parent_name
            
        res_geom = unary_union(valid_parts) if len(valid_parts) > 1 else valid_parts[0]
    else:
        res_geom = geom

    # Determine canonical local label
    canonical_label = parent_name
    if res_geom is not None and not res_geom.is_empty:
        c = res_geom.centroid
        norm_parent = normalize_name(parent_name)
        # If Spain/Habsburg composite realm and territory is in Austrian/Danubian Central Europe
        if ("spain" in norm_parent or "habsburg" in norm_parent) and (44.0 <= c.y <= 54.0 and 8.0 <= c.x <= 22.0):
            canonical_label = "Archduchy of Austria (Habsburg)"

    return res_geom, canonical_label
