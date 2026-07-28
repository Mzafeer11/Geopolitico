"""
Result Builder helper module for Geopolitico simulation engine.
Encapsulates conquest summary formatting and common response payload construction.
"""

from typing import Dict, Any, List, Optional

def build_conquest_summary_str(territories: List[Any], baseline_units_map: Optional[Dict[str, List[str]]] = None) -> str:
    """Build a human-readable summary string of conquests from a list of territory change objects."""
    summary_str = ""
    baseline_units_map = baseline_units_map or {}
    for t in territories:
        conquest_parts = []
        pre_owned = set(baseline_units_map.get(t.name, []))
        
        hist_provs = getattr(t, "historical_provinces", []) or []
        new_hist_provs = [hp for hp in hist_provs if hp not in pre_owned]
        if new_hist_provs:
            conquest_parts.append(f"Historical Provinces Conquered: {', '.join(new_hist_provs)}")
        elif hist_provs and not pre_owned:
            conquest_parts.append(f"Historical Provinces Conquered: {', '.join(hist_provs)}")
            
        for p in getattr(t, "partial_countries", []):
            if getattr(p, "historical_provinces", []):
                p_new = [hp for hp in p.historical_provinces if hp not in pre_owned]
                if p_new:
                    conquest_parts.append(f"Historical Provinces Conquered in {p.country}: {', '.join(p_new)}")
            elif getattr(p, "clip_method", None) == "natural_boundary" and getattr(p, "clip_description", None):
                conquest_parts.append(f"{p.country} ({p.clip_direction} of {p.clip_description})")
            elif getattr(p, "clip_method", None) in ["coordinate_latitude", "coordinate_longitude"] and getattr(p, "clip_description", None):
                conquest_parts.append(f"{p.country} ({p.clip_description})")
            elif getattr(p, "provinces", []):
                conquest_parts.append(f"{p.country} (provinces: {', '.join(p.provinces)})")
        if getattr(t, "countries_absorbed", []):
            conquest_parts.append(f"Fully absorbed countries: {', '.join(t.countries_absorbed)}")
        if conquest_parts:
            summary_str += f"- {t.name} conquered: " + "; ".join(conquest_parts) + "\n"
    return summary_str


def build_common_results(
    results: Dict[str, Any],
    year: int,
    context: Dict[str, Any],
    all_baseline_polities: List[str],
    geojson_before: Dict[str, Any]
) -> Dict[str, Any]:
    """Assemble common fields in the final results dictionary."""
    results["base_year"] = year
    results["historical_context"] = context.get("baseline_description", "")
    results["what_actually_happened"] = "Real timeline outcome."
    results["geojson_before"] = geojson_before
    results["geojson_provinces"] = context.get("geojson_provinces", geojson_before)
    results["territories_before"] = [
        {"name": p, "status": "baseline", "color": "#4b5563", "description": f"Baseline polity: {p}"}
        for p in all_baseline_polities
    ]
    results["confidence_score"] = 0.85
    
    all_boundary_paths = []
    boundary_names = []
    if "osm_boundaries" in context:
        for name, paths in context["osm_boundaries"].items():
            if paths:
                all_boundary_paths.extend(paths)
                boundary_names.append(name)
                
    results["osm_boundary_geometry"] = all_boundary_paths
    results["osm_boundary_name"] = ", ".join(boundary_names) if boundary_names else "Natural Borders"
    results["map_markers"] = context.get("map_markers", [])
    return results
