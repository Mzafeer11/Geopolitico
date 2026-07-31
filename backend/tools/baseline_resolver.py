"""
Baseline Resolver module for Geopolitico.
Multi-tier fallback chain for resolving historical polity names and years to modern provinces and polygons:
  Tier 1: Wikidata structured admin subunits (P150 -> point-in-polygon)
  Tier 2: Wikipedia text-parsed administrative units
  Tier 3: LLM-named natural boundary + deterministic centroid direction calculation & vector clipping
  Tier 4: Cliopatria raw coarse polygon fallback
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from shapely.geometry import shape, mapping, Point, Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import unary_union

from backend.config import DATA_DIR
from backend.tools.cliopatria_loader import cliopatria_db, normalize_name
from backend.tools.country_polygons import CountryPolygonLoader, get_country_polygon_loader
from backend.tools.gis_tools import natural_boundary_tool

WIKIDATA_CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"

# In-memory cache for wikidata_admin_cache.json
_WIKIDATA_CACHE: Optional[Dict[str, Any]] = None


def _load_wikidata_cache() -> Dict[str, Any]:
    global _WIKIDATA_CACHE
    if _WIKIDATA_CACHE is not None:
        return _WIKIDATA_CACHE
    if WIKIDATA_CACHE_FILE.exists():
        try:
            with open(WIKIDATA_CACHE_FILE, "r", encoding="utf-8") as f:
                _WIKIDATA_CACHE = json.load(f)
                return _WIKIDATA_CACHE
        except Exception as e:
            print(f"[WARN] Failed to read {WIKIDATA_CACHE_FILE}: {e}", flush=True)
            
    try:
        from scripts.build_wikidata_cache import SEED_POLITY_DATA
        _WIKIDATA_CACHE = dict(SEED_POLITY_DATA)
    except Exception:
        _WIKIDATA_CACHE = {}
    return _WIKIDATA_CACHE


def _calculate_boundary_direction(cliopatria_poly: Any, boundary_line: Any) -> str:
    """
    Deterministically compare centroid of Cliopatria polity polygon against centroid of boundary line.
    No LLM hallucination possible for direction.
    """
    poly_centroid = cliopatria_poly.centroid
    line_centroid = boundary_line.centroid
    
    bounds = boundary_line.bounds
    dx = bounds[2] - bounds[0] # maxx - minx
    dy = bounds[3] - bounds[1] # maxy - miny
    
    if dx >= dy:
        # Boundary runs mostly East-West (e.g. Loire River, Danube River, Pyrenees)
        if poly_centroid.y < line_centroid.y:
            return "south_of_natural_boundary"
        else:
            return "north_of_natural_boundary"
    else:
        # Boundary runs mostly North-South (e.g. Rhine River)
        if poly_centroid.x < line_centroid.x:
            return "west_of_natural_boundary"
        else:
            return "east_of_natural_boundary"


# Haversine distance in km
def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

MAINLAND_EUROPE = {"France", "Belgium", "Netherlands", "Luxembourg", "Germany", "Switzerland", "Austria", "Spain", "Portugal", "Italy", "United Kingdom", "Greece", "Bulgaria"}
NORTH_AFRICA = {"Morocco", "Algeria", "Tunisia", "Libya", "Egypt", "Western Sahara", "Sudan"}
MIDDLE_EAST_ASIA = {"Syria", "Iraq", "Iran", "Jordan", "Saudi Arabia", "Yemen", "Oman", "UAE", "Palestine", "Israel", "Lebanon", "Turkey", "Pakistan", "Afghanistan"}

def _get_landmass_region(country_name: str) -> str:
    if country_name in MAINLAND_EUROPE:
        return "EUROPE"
    elif country_name in NORTH_AFRICA:
        return "AFRICA"
    elif country_name in MIDDLE_EAST_ASIA:
        return "ASIA_MIDDLE_EAST"
    else:
        return "OTHER"


def _get_province_color(unit_name: str, polity_name: str = "", province_name: str = "") -> str:
    """Generate a deterministic, vibrant HSL color per historical administrative unit."""
    import colorsys
    seed_str = f"{polity_name}:{unit_name}"
    h_val = sum(ord(c) * (i + 1) for i, c in enumerate(seed_str))
    hue = (h_val % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.78, 0.90)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def get_historical_units(
    polity_name: str,
    year: int,
    region: str = ""
) -> Dict[str, Any]:
    """
    Resolve a polity's historical administrative units to modern provinces.
    
    Returns a structured dict with confidence-tiered province lists,
    resolved geometry, and metadata about which tier produced the result.
    Includes Option 5 (Landmass-Constrained KNN) & Option 6 (Vector Clipping & Natural Boundary Snapping).
    """
    loader = get_country_polygon_loader()

    # Load baseline coarse polygon from Cliopatria
    cliopatria_feat = cliopatria_db.get_polity_geometry(polity_name, year)
    cliopatria_shape = None
    if cliopatria_feat and cliopatria_feat.get("geometry"):
        try:
            cliopatria_shape = shape(cliopatria_feat["geometry"])
        except Exception:
            pass

_NATURAL_BOUNDARY_SHAPES_CACHE: Dict[str, Any] = {}

def _get_lazy_natural_boundary_buffer(b_name: str) -> Optional[Any]:
    if b_name in _NATURAL_BOUNDARY_SHAPES_CACHE:
        return _NATURAL_BOUNDARY_SHAPES_CACHE[b_name]
    res = natural_boundary_tool(b_name)
    if res.get("status") == "success" and res.get("paths"):
        lines = [LineString(p) for p in res["paths"] if len(p) >= 2]
        if lines:
            main_line = max(lines, key=lambda l: l.length)
            main_centroid = main_line.centroid
            clustered = [l for l in lines if l.centroid.distance(main_centroid) <= 15.0]
            union_line = clustered[0] if len(clustered) == 1 else unary_union(clustered)
            buf = union_line.buffer(0.3)
            _NATURAL_BOUNDARY_SHAPES_CACHE[b_name] = buf
            return buf
    _NATURAL_BOUNDARY_SHAPES_CACHE[b_name] = None
    return None

def get_historical_units(
    polity_name: str, 
    year: int = 732,
    region: str = "",
    target_boundary: Optional[str] = None
) -> Dict[str, Any]:
    """
    4-Tier Historical Resolution Engine for Geopolitico:
    - Tier 1: Wikidata Structured Admin Cache
    - Tier 2: Wikipedia Parsed Admin Text
    - Tier 3: LLM Natural Boundary + Centroid Direction (fallback if Tier 1 & 2 fail)
    - Tier 4: Cliopatria Coarse Polygon
    """
    from backend.tools.spatial_cache import SimulationCache
    cache_inst = SimulationCache.get_instance()
    cached = cache_inst.get_historical_units(polity_name, year, region)
    if cached is not None and not target_boundary:
        if cached.get("provinces_core") or cached.get("provinces_edge"):
            return cached

    clio_feat = cliopatria_db.get_polity_geometry(polity_name, year)
    cliopatria_shape = None
    if clio_feat and clio_feat.get("geometry"):
        try:
            cliopatria_shape = shape(clio_feat["geometry"])
        except Exception:
            pass

    cache = _load_wikidata_cache()
    
    # Matching polity in cache
    polity_data = None
    norm_target = normalize_name(polity_name)
    for c_name, c_data in cache.items():
        if normalize_name(c_name) == norm_target or norm_target in normalize_name(c_name):
            polity_data = c_data
            break

    loader = get_country_polygon_loader()

    # Advanced Option 5 & Option 6 Mapping Loop
    def _map_units_to_provinces_advanced(units_list: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        core_features = []
        partial_features = []
        province_unit_counts: Dict[str, List[str]] = {}
        province_details: Dict[str, Dict[str, Any]] = {}
        units_mapped = 0
        units_unmapped = 0

        # Lazy load natural boundary for snapping ONLY if target_boundary is provided
        natural_boundary_shapes = {}
        if target_boundary:
            buf = _get_lazy_natural_boundary_buffer(target_boundary)
            if buf is not None:
                natural_boundary_shapes[target_boundary] = buf

        for feat in loader.provinces_data:
            props = feat.get("properties", {})
            pname = props.get("name")
            admin = props.get("admin")
            if not pname or not admin:
                continue

            try:
                p_geom = shape(feat["geometry"])
                if cliopatria_shape and not cliopatria_shape.intersects(p_geom):
                    continue

                intersection = cliopatria_shape.intersection(p_geom) if cliopatria_shape else p_geom
                if intersection.is_empty:
                    continue

                coverage_pct = round((intersection.area / p_geom.area) * 100, 1)
                category = "Fully Inside" if coverage_pct >= 85.0 else "Partially Inside"

                snapped_boundary_name = None
                for b_name, b_buf in natural_boundary_shapes.items():
                    if b_buf.intersects(p_geom):
                        snapped_boundary_name = b_name
                        break

                centroid = p_geom.centroid
                p_lat, p_lon = centroid.y, centroid.x
                prov_region = _get_landmass_region(admin)

                best_unit = None
                min_score = float("inf")
                best_dist_km = 0.0

                for unit in units_list:
                    u_lat, u_lon = unit.get("latitude"), unit.get("longitude")
                    if u_lat is None or u_lon is None:
                        continue
                    u_name = unit.get("name", "Unknown")
                    u_country = unit.get("present_day_country", "")
                    unit_region = _get_landmass_region(u_country)

                    dist_km = _haversine_distance(p_lat, p_lon, u_lat, u_lon)
                    score = dist_km

                    if prov_region != unit_region:
                        score *= 8.0  # Sea barrier penalty

                    if u_country and u_country.lower() in admin.lower():
                        score *= 0.45  # Country match discount

                    if score < min_score:
                        min_score = score
                        best_unit = u_name
                        best_dist_km = dist_km

                if not best_unit and units_list:
                    best_unit = units_list[0].get("name", "Unknown")

                fullname = f"{pname} ({admin})"
                rendered_geom = p_geom if category == "Fully Inside" else intersection

                item_color = _get_province_color(best_unit or fullname, polity_name, pname)
                item_feat = {
                    "name": fullname,
                    "country": admin,
                    "province": pname,
                    "assigned_unit": best_unit,
                    "coverage_pct": coverage_pct,
                    "distance_km": round(best_dist_km, 1),
                    "snapped_boundary": snapped_boundary_name,
                    "color": item_color,
                    "fill_color": item_color,
                    "shape": rendered_geom
                }

                province_details[fullname] = item_feat
                if category == "Fully Inside":
                    core_features.append(item_feat)
                else:
                    partial_features.append(item_feat)

                units_mapped += 1

            except Exception:
                continue

        mapped_shapes = [item["shape"] for item in province_details.values()]
        resolved_geom = unary_union(mapped_shapes) if mapped_shapes else cliopatria_shape

        stats = {
            "units_found": len(units_list),
            "units_mapped": units_mapped,
            "units_unmapped": max(0, len(units_list) - units_mapped)
        }

        return core_features, partial_features, resolved_geom, stats

    # ─── TIER 1: Wikidata Structured Data ──────────────────────────────────────
    if polity_data and polity_data.get("admin_units"):
        units = polity_data["admin_units"]
        core, edge, geom, stats = _map_units_to_provinces_advanced(units)
        if len(core) + len(edge) >= 3 or (cliopatria_shape and geom and geom.area > 0.5):
            # Precompute historical units shapes map by historical unit name
            units_map = {}
            for feat in core + edge:
                u_name = feat.get("assigned_unit")
                u_shape = feat.get("shape")
                if u_name and u_shape:
                    units_map.setdefault(u_name, []).append(u_shape)
                    
            historical_units_shapes = {
                u_name: unary_union(shapes_list)
                for u_name, shapes_list in units_map.items() if shapes_list
            }

            return {
                "polity": polity_name,
                "year": year,
                "tier": "wikidata_structured_advanced",
                "confidence": "high",
                "provinces_core": core,
                "provinces_edge": edge,
                "provinces_contested": [],
                "historical_units_map": historical_units_shapes,
                "geometry": geom if geom else cliopatria_shape,
                "cliopatria_fallback_geometry": cliopatria_shape,
                "boundary_info": None,
                "metadata": {
                    **stats,
                    "wikidata_source": True,
                    "wikipedia_source": False,
                    "llm_boundary": False,
                    "cliopatria_fallback": False,
                    "option_5_landmass_knn": True,
                    "option_6_vector_clipping": True
                }
            }

    # ─── TIER 2: Wikipedia Text Parsing Fallback ────────────────────────────────
    if polity_data and polity_data.get("wikipedia_units"):
        units = polity_data["wikipedia_units"]
        core, edge, geom, stats = _map_units_to_provinces(units)
        if len(core) + len(edge) >= 3:
            return {
                "polity": polity_name,
                "year": year,
                "tier": "wikipedia_parsed",
                "confidence": "medium",
                "provinces_core": core,
                "provinces_edge": edge,
                "provinces_contested": [],
                "geometry": geom if geom else cliopatria_shape,
                "cliopatria_fallback_geometry": cliopatria_shape,
                "boundary_info": None,
                "metadata": {
                    **stats,
                    "wikidata_source": False,
                    "wikipedia_source": True,
                    "llm_boundary": False,
                    "cliopatria_fallback": False
                }
            }

    # ─── TIER 3: LLM Natural Boundary + Centroid Direction ─────────────────────
    if cliopatria_shape is not None:
        try:
            from pydantic import BaseModel, Field
            from langchain_core.messages import SystemMessage
            from backend.helpers.llm import invoke_structured_with_fallback as _invoke_structured_with_fallback

            class NaturalBoundarySuggestion(BaseModel):
                boundary_name: str = Field(description="Name of the natural boundary (e.g., 'Loire River', 'Pyrenees', 'Danube River', 'Rhine River', 'Bosphorus').")

            prompt = (
                f"You are a historical geographer. For the polity '{polity_name}' in year {year} AD "
                f"in the region '{region}', identify the single most prominent natural boundary "
                f"(river or mountain range) that historically served as its border or expansion limit. "
                f"Return ONLY the exact name of the feature."
            )

            res: NaturalBoundarySuggestion = _invoke_structured_with_fallback(
                NaturalBoundarySuggestion,
                [SystemMessage(content=prompt)],
                temperature=0.2
            )

            if res and res.boundary_name:
                b_name = res.boundary_name
                res_boundary = natural_boundary_tool(b_name)
                if res_boundary.get("status") == "success" and res_boundary.get("paths"):
                    paths = res_boundary["paths"]
                    lines = [LineString(p) for p in paths if len(p) >= 2]
                    if lines:
                        boundary_line = lines[0] if len(lines) == 1 else MultiLineString(lines)
                        computed_dir = _calculate_boundary_direction(cliopatria_shape, boundary_line)
                        
                        t3_core, t3_edge, t3_geom, t3_stats = _map_units_to_provinces_advanced([])
                        return {
                            "polity": polity_name,
                            "year": year,
                            "tier": "llm_boundary",
                            "confidence": "inferred",
                            "provinces_core": t3_core,
                            "provinces_edge": t3_edge,
                            "provinces_contested": [],
                            "geometry": cliopatria_shape,
                            "cliopatria_fallback_geometry": cliopatria_shape,
                            "boundary_info": {
                                "boundary_name": b_name,
                                "direction": computed_dir,
                                "direction_method": "centroid_comparison"
                            },
                            "metadata": {
                                **t3_stats,
                                "wikidata_source": False,
                                "wikipedia_source": False,
                                "llm_boundary": True,
                                "cliopatria_fallback": False
                            }
                        }
        except Exception as e:
            print(f"[WARN] Tier 3 LLM boundary resolution failed: {e}", flush=True)

    # ─── TIER 4: Cliopatria Sub-Province Administrative Partition Fallback ──────
    fallback_core, fallback_edge, fallback_geom, stats = ([], [], cliopatria_shape, {})
    if cliopatria_shape is not None:
        try:
            fallback_core, fallback_edge, fallback_geom, stats = _map_units_to_provinces_advanced([])
        except Exception as e:
            print(f"[WARN] Sub-province fallback partitioning failed for '{polity_name}': {e}", flush=True)

    return {
        "polity": polity_name,
        "year": year,
        "tier": "cliopatria_province_breakdown",
        "confidence": "medium",
        "provinces_core": fallback_core,
        "provinces_edge": fallback_edge,
        "provinces_contested": [],
        "geometry": fallback_geom if fallback_geom else cliopatria_shape,
        "cliopatria_fallback_geometry": cliopatria_shape,
        "boundary_info": None,
        "metadata": {
            **stats,
            "wikidata_source": False,
            "wikipedia_source": False,
            "llm_boundary": False,
            "cliopatria_fallback": True
        }
    }


def generate_scenario_baseline_map(
    year: int,
    polities: Optional[List[str]] = None,
    target_region: str = ""
) -> Dict[str, Any]:
    """
    Dynamically render a multi-empire historical baseline scenario map for ANY given year
    and list of participating polities/empires.
    
    Uses Option 5 (Landmass-Constrained KNN) and Option 6 (Vector Clipping & Natural Boundary Snapping)
    to render all active empires side-by-side with sub-province level administrative partitioning.
    """
    import colorsys
    from pathlib import Path

    print(f"\n[SCENARIO BASELINE MAP] Generating dynamic multi-empire baseline map for Year {year} AD...", flush=True)

    if not polities:
        active_feats = cliopatria_db.get_active_polities(year)
        
        candidates = []
        seen_names = set()
        
        for f in active_feats:
            p_name = f.get("properties", {}).get("Name")
            if not p_name:
                continue
            # Skip vassalage/allegiance overlays like '(Allegiance of Southern Song to Great Jin)'
            if p_name.startswith("(") and " to " in p_name:
                continue
            clean_name = p_name.strip("()")
            if clean_name in seen_names:
                continue
            seen_names.add(clean_name)
            
            try:
                s_geom = shape(f["geometry"])
                area = s_geom.area
                if area >= 5.0:
                    candidates.append((clean_name, area))
            except Exception:
                pass
                
        # Sort by polygon area descending so top major empires come first
        candidates.sort(key=lambda x: x[1], reverse=True)
        polities = [c[0] for c in candidates[:10]]

    print(f"      Target Polities ({len(polities)}): {polities}", flush=True)

    def _palette_for_index(idx: int, total: int):
        hue = idx / max(1, total)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.78, 0.90)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    rendered_polities = []
    all_geojson_features = []

    for idx, p_name in enumerate(polities):
        res = get_historical_units(p_name, year, target_region)
        base_color = _palette_for_index(idx, len(polities))

        clio_geom = res.get("cliopatria_fallback_geometry") or res.get("geometry")
        clio_feat = None
        if clio_geom is not None:
            clio_feat = {
                "type": "Feature",
                "geometry": mapping(clio_geom),
                "properties": {
                    "Name": p_name,
                    "color": base_color,
                    "tier": res.get("tier", "cliopatria_coarse")
                }
            }

        full_feats = res.get("provinces_core", [])
        partial_feats = res.get("provinces_edge", [])

        # Format GeoJSON features for full and partial provinces
        full_geojson = []
        for item in full_feats:
            if "shape" in item:
                prov_color = item.get("color") or _get_province_color(item.get("assigned_unit") or item.get("name"), p_name)
                f_out = {
                    "type": "Feature",
                    "geometry": mapping(item["shape"]),
                    "properties": {
                        "empire": p_name,
                        "fullname": item["name"],
                        "assigned_unit": item.get("assigned_unit", p_name),
                        "category": "Fully Inside",
                        "coverage_pct": item.get("coverage_pct", 100.0),
                        "color": prov_color,
                        "fill_color": prov_color
                    }
                }
                full_geojson.append(f_out)
                all_geojson_features.append(f_out)

        partial_geojson = []
        for item in partial_feats:
            if "shape" in item:
                prov_color = item.get("color") or _get_province_color(item.get("assigned_unit") or item.get("name"), p_name)
                f_out = {
                    "type": "Feature",
                    "geometry": mapping(item["shape"]),
                    "properties": {
                        "empire": p_name,
                        "fullname": item["name"],
                        "assigned_unit": item.get("assigned_unit", p_name),
                        "category": "Partially Inside",
                        "coverage_pct": item.get("coverage_pct", 50.0),
                        "color": prov_color,
                        "fill_color": prov_color
                    }
                }
                partial_geojson.append(f_out)
                all_geojson_features.append(f_out)

        rendered_polities.append({
            "name": p_name,
            "color": base_color,
            "clio_feature": clio_feat,
            "full_geojson": full_geojson,
            "partial_geojson": partial_geojson,
            "tier": res.get("tier")
        })

    # Render Multi-Empire Leaflet HTML Map
    html_out_path = Path("scratch") / f"scenario_{year}_baseline_map.html"
    html_out_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Scenario Baseline Map ({year} AD) — Multi-Empire Geopolitico Engine</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background: #0b0f19; color: #f8fafc; }}
        #map {{ height: 100vh; width: 100vw; background: #0b0f19; }}
        .info-panel {{
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(11, 15, 25, 0.94);
            border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 18px 22px;
            border-radius: 12px;
            max-width: 440px;
            max-height: 88vh;
            overflow-y: auto;
            box-shadow: 0 12px 30px rgba(0,0,0,0.7);
            backdrop-filter: blur(8px);
        }}
        h2 {{ margin: 0 0 6px 0; font-size: 18px; color: #38bdf8; }}
        p {{ margin: 4px 0; font-size: 13px; color: #cbd5e1; line-height: 1.4; }}
        .empire-card {{
            background: rgba(255,255,255,0.05);
            padding: 8px 12px;
            border-radius: 8px;
            margin: 8px 0;
            border-left: 4px solid #38bdf8;
            font-size: 12px;
        }}
        .legend {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); }}
    </style>
</head>
<body>

    <div id="map"></div>

    <div class="info-panel">
        <h2>🌐 Scenario Baseline Map ({year} AD)</h2>
        <p><b>Multi-Empire Geopolitico Baseline Engine:</b> Option 5 (Landmass KNN) & Option 6 (Vector Clipping & Natural Boundary Snapping).</p>
        <p style="font-size:11px; color:#94a3b8;">Active Polities Rendered: {len(rendered_polities)}</p>

        <div class="legend">
            <p><b>Participating Polities:</b></p>
"""

    for r_p in rendered_polities:
        c = r_p["color"]
        n = r_p["name"]
        t_info = r_p["tier"]
        html_content += f"""
            <div class="empire-card" style="border-left-color: {c};">
                <b style="color:{c}; font-size:13px;">{n}</b><br>
                <span style="color:#94a3b8;">Resolver Tier: {t_info}</span>
            </div>"""

    html_content += f"""
        </div>
    </div>

    <script>
        var map = L.map('map').setView([30.0, 30.0], 4);

        var darkCanvas = L.tileLayer('', {{ attribution: 'Pristine Zero-Dot Vector Layer' }});
        var darkBasemap = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_nolabels/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; CartoDB & OpenStreetMap',
            maxZoom: 12,
            subdomains: 'abcd'
        }});

        darkBasemap.addTo(map);

        var baseMaps = {{
            "CartoDB Dark Basemap": darkBasemap,
            "Pristine Dark Canvas": darkCanvas
        }};

        var overlayMaps = {{}};
"""

    import re

    for r_p in rendered_polities:
        n_safe = re.sub(r'[^a-zA-Z0-9_]', '_', r_p["name"])
        n_label = json.dumps(r_p["name"])
        c = r_p["color"]

        if r_p["clio_feature"]:
            html_content += f"""
        var empLayer_{n_safe} = L.geoJSON({json.dumps({"type": "FeatureCollection", "features": [r_p["clio_feature"]]})}, {{
            style: {{ color: '{c}', weight: 3.2, opacity: 0.9, fillColor: '{c}', fillOpacity: 0.12 }}
        }}).addTo(map);
        overlayMaps[{n_label} + ' Outer Border'] = empLayer_{n_safe};
"""

        if r_p["full_geojson"]:
            html_content += f"""
        var fullLayer_{n_safe} = L.geoJSON({json.dumps({"type": "FeatureCollection", "features": r_p["full_geojson"]})}, {{
            style: function(f) {{
                return {{ color: f.properties.color, weight: 1.5, opacity: 0.9, fillColor: f.properties.color, fillOpacity: 0.45 }};
            }},
            onEachFeature: function(f, l) {{
                var p = f.properties;
                l.bindPopup('<b>' + p.fullname + '</b><br>' +
                               '<b>Polity:</b> ' + p.empire + '<br>' +
                               '<b>Assigned Unit:</b> ' + p.assigned_unit + '<br>' +
                               '<b>Status:</b> Fully Inside (100%)');
            }}
        }}).addTo(map);
        overlayMaps[{n_label} + ' Sub-Provinces'] = fullLayer_{n_safe};
"""

    html_content += f"""
        L.control.layers(baseMaps, overlayMaps).addTo(map);
    </script>
</body>
</html>
"""

    with open(html_out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[COMPLETE] Dynamic Scenario Baseline Map ({year} AD) saved at: {html_out_path}", flush=True)

    return {
        "status": "success",
        "year": year,
        "map_html_path": str(html_out_path),
        "polities_count": len(rendered_polities),
        "polities": [r["name"] for r in rendered_polities],
        "features": all_geojson_features
    }


def _get_resolved_baseline_geometry(polity: str, year: int, region: str = "") -> Tuple[Optional[Any], Optional[Dict[str, Any]], str]:
    """
    Retrieve polity baseline geometry and sub-province level features.
    Runs 4-tier Baseline Resolver (Option 5 KNN & Option 6 Vector Clipping)
    with Cliopatria's contiguous shape as fallback boundary.
    """
    from backend.tools.spatial_cache import SimulationCache
    cache_inst = SimulationCache.get_instance()
    cached = cache_inst.get_baseline_geometry(polity, year, region)
    if cached is not None and isinstance(cached, tuple) and len(cached) >= 2 and cached[1]:
        props = cached[1].get("properties", {})
        if props.get("sub_province_features"):
            return cached

    # Pre-fetch Cliopatria database shape as boundary fallback
    clio_feat = cliopatria_db.get_polity_geometry(polity, year)
    clio_shape = None
    if clio_feat and clio_feat.get("geometry"):
        try:
            clio_shape = shape(clio_feat["geometry"])
        except Exception:
            pass

    if year >= 1800 and not clio_shape:
        try:
            loader = get_country_polygon_loader()
            c_feat = loader.get_country_feature(polity)
            if c_feat and c_feat.get("geometry"):
                clio_shape = shape(c_feat["geometry"])
        except Exception as e:
            print(f"[WARN] Failed to load country feature for '{polity}': {e}", flush=True)

    try:
        res = get_historical_units(polity, year, region)
        tier = res.get("tier", "cliopatria_coarse")
        
        target_geom = res.get("geometry") if (res.get("geometry") is not None and not res.get("geometry").is_empty) else clio_shape
        
        if target_geom is not None:
            sub_prov_features = []
            for p in res.get("provinces_core", []) + res.get("provinces_edge", []):
                if "shape" in p and p["shape"] and not p["shape"].is_empty:
                    u_name = p.get("assigned_unit") or p.get("name") or polity
                    p_color = p.get("color") or _get_province_color(u_name, polity, p.get("name", ""))
                    sub_prov_features.append({
                        "type": "Feature",
                        "geometry": mapping(p["shape"]),
                        "properties": {
                            "name": p.get("name", polity),
                            "fullname": p.get("name", polity),
                            "empire": polity,
                            "assigned_unit": u_name,
                            "status": p.get("category", "Fully Inside"),
                            "is_sub_province": True,
                            "color": p_color,
                            "fill_color": p_color,
                            "stroke_color": "#0f172a",
                            "coverage_pct": p.get("coverage_pct", 100.0)
                        }
                    })
                    
            feat_dict = {
                "type": "Feature",
                "geometry": mapping(target_geom),
                "properties": {
                    "Name": polity,
                    "name": polity,
                    "FromYear": year,
                    "ToYear": year,
                    "tier": tier,
                    "confidence": res.get("confidence", "low"),
                    "provinces_core": [p["name"] for p in res.get("provinces_core", [])],
                    "provinces_edge": [p["name"] for p in res.get("provinces_edge", [])],
                    "sub_province_features": sub_prov_features
                }
            }
            res_tuple = (target_geom, feat_dict, tier)
            cache_inst.set_baseline_geometry(polity, year, region, res_tuple)
            return res_tuple
    except Exception as e:
        print(f"[WARN] Baseline resolver failed for '{polity}' in {year}: {e}", flush=True)

    if clio_shape is not None:
        feat_dict = {
            "type": "Feature",
            "geometry": mapping(clio_shape),
            "properties": {
                "Name": polity,
                "name": polity,
                "FromYear": year,
                "ToYear": year,
                "year": year,
                "tier": "cliopatria_db",
                "sub_province_features": []
            }
        }
        res_tuple = (clio_shape, feat_dict, "cliopatria_db")
        cache_inst.set_baseline_geometry(polity, year, region, res_tuple)
        return res_tuple

    res_tuple = (None, None, "cliopatria_coarse")
    cache_inst.set_baseline_geometry(polity, year, region, res_tuple)
    return res_tuple

