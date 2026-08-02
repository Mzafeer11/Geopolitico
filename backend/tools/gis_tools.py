import os
import json
import httpx
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from shapely.geometry import LineString, MultiLineString
from backend.config import DATA_DIR

# Helper to avoid rate limiting
import time
_LAST_REQUEST_TIME = 0.0

def _rate_limit(seconds=2.0):
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < seconds:
        time.sleep(seconds - elapsed)
    _LAST_REQUEST_TIME = time.time()

# ─── 1. Nominatim Geocoding Tool ──────────────────────────────────────────────

def geocode_landmark_tool(query: str) -> Dict[str, Any]:
    """Geocode a landmark name to coordinates using Nominatim OpenStreetMap API."""
    global _LAST_REQUEST_TIME
    try:
        _rate_limit(3.0)
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
        
        r = httpx.get(url, params=params, headers=headers, timeout=12.0)
        if r.status_code == 200:
            data = r.json()
            if data:
                place = data[0]
                lat = float(place.get("lat"))
                lon = float(place.get("lon"))
                display_name = place.get("display_name")
                return {
                    "status": "success",
                    "display_name": display_name,
                    "latitude": lat,
                    "longitude": lon,
                    "message": f"Resolved landmark '{query}' to coordinate: ({lat}, {lon})"
                }
        return {"status": "error", "message": f"Could not find coordinates for landmark '{query}'."}
    except Exception as e:
        return {"status": "error", "message": f"Nominatim API geocode error: {e}"}

# ─── 2. OpenStreetMap Overpass River/Boundary Tool ────────────────────────────

OFFLINE_BOUNDARIES = {
    "rhone": [
        [[8.43, 46.57], [6.83, 46.43], [6.15, 46.20], [5.81, 46.05], [4.84, 45.76], [4.89, 44.93], [4.80, 43.95], [4.63, 43.68]]
    ],
    "rhône": [
        [[8.43, 46.57], [6.83, 46.43], [6.15, 46.20], [5.81, 46.05], [4.84, 45.76], [4.89, 44.93], [4.80, 43.95], [4.63, 43.68]]
    ]
}


def natural_boundary_tool(name: str) -> Dict[str, Any]:
    """Query local pre-packaged boundaries, local Natural Earth datasets, falling back to OpenStreetMap Overpass API."""
    global _LAST_REQUEST_TIME
    try:
        # Normalize search query (strip common suffixes)
        q = name.lower()
        for suffix in ["river", "lake", "mountains", "mountain", "range", "the"]:
            q = q.replace(suffix, "")
        q = q.strip()
        
        # Spelling variations for natural boundaries
        q_variants = [q]
        if q == "rhine":
            q_variants.extend(["rhein", "rhin"])
        elif q == "danube":
            q_variants.extend(["donau", "dunav", "duna"])
        elif q == "rhone":
            q_variants.extend(["rhône", "roten"])
        
        # Check pre-packaged boundaries first
        if q in OFFLINE_BOUNDARIES:
            print(f"[OFFLINE GIS] Successfully loaded pre-packaged offline coordinates for '{name}'.", flush=True)
            return {
                "status": "success",
                "name": name,
                "paths": OFFLINE_BOUNDARIES[q],
                "message": f"Loaded pre-packaged offline coordinates for boundary '{name}'."
            }
        
        # Special local construction for Bosphorus / Constantinople
        if q in ["bosphorus", "constantinople"]:
            print(f"[OFFLINE GIS] Programmatically constructing centerline for '{name}'...", flush=True)
            from backend.config import DATA_DIR
            import json
            from shapely.geometry import shape, LineString
            regions_path = DATA_DIR / "ne_10m_geography_regions_polys.geojson"
            if regions_path.exists():
                with open(regions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    europe_geom = None
                    asia_geom = None
                    for feat in data.get("features", []):
                        nm = feat.get("properties", {}).get("NAME", "").upper()
                        if nm == "EUROPE":
                            europe_geom = shape(feat["geometry"])
                        elif nm == "ASIA":
                            asia_geom = shape(feat["geometry"])
                    
                    if europe_geom and asia_geom:
                        istanbul_box = shape({"type": "Polygon", "coordinates": [[[28.90, 40.95], [29.20, 40.95], [29.20, 41.25], [28.90, 41.25], [28.90, 40.95]]]})
                        europe_ist = europe_geom.intersection(istanbul_box)
                        asia_ist = asia_geom.intersection(istanbul_box)
                        if not europe_ist.is_empty and not asia_ist.is_empty:
                            eb = europe_ist.boundary
                            ab = asia_ist.boundary
                            strait_pts = []
                            for lat in [41.00, 41.03, 41.06, 41.09, 41.12, 41.15, 41.18, 41.21, 41.24]:
                                slice_line = LineString([(28.8, lat), (29.4, lat)])
                                p_euro = eb.intersection(slice_line)
                                p_asia = ab.intersection(slice_line)
                                if not p_euro.is_empty and not p_asia.is_empty:
                                    strait_pts.append([(p_euro.centroid.x + p_asia.centroid.x) / 2, lat])
                            if len(strait_pts) >= 2:
                                return {
                                    "status": "success",
                                    "name": name,
                                    "paths": [strait_pts],
                                    "message": f"Programmatically constructed centerline for boundary '{name}' from continent outlines."
                                }
        
        from backend.config import DATA_DIR
        import json
        
        files_to_search = []
        for entry in sorted(DATA_DIR.iterdir()):
            if not entry.is_file():
                continue
            filename = entry.name.lower()
            if not filename.endswith(".geojson"):
                continue
            if not any(token in filename for token in ["river", "lake", "geography"]):
                continue

            if "regions" in filename or "marine" in filename:
                name_keys = ["NAME", "NAMEALT", "name", "namealt"]
            else:
                name_keys = ["name", "name_alt", "name_en", "name_de", "name_fr", "name_el", "name_tr"]

            files_to_search.append((entry.name, name_keys))
        
        lines = []
        for filename, name_keys in files_to_search:
            path = DATA_DIR / filename
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        matched = False
                        for key in name_keys:
                            val = props.get(key)
                            if val:
                                val_str = str(val).lower()
                                if any(var in val_str for var in q_variants):
                                    matched = True
                                    break
                        if matched:
                            geom = feat.get("geometry", {})
                            gtype = geom.get("type")
                            coords = geom.get("coordinates", [])
                            if gtype == "LineString":
                                lines.append(coords)
                            elif gtype == "MultiLineString":
                                lines.extend(coords)
                            elif gtype in ["Polygon", "MultiPolygon"]:
                                # Programmatically construct a centerline (spine) through the long direction of the polygon
                                try:
                                    from shapely.geometry import shape, LineString
                                    poly = shape(geom)
                                    if poly.is_valid and not poly.is_empty:
                                        minx, miny, maxx, maxy = poly.bounds
                                        dx = maxx - minx
                                        dy = maxy - miny
                                        slice_points = []
                                        
                                        if dx > dy:
                                            # Slice vertically (east-west range like Pyrenees)
                                            # Use 20 slices to get a smooth line
                                            x_steps = [minx + (i / 20.0) * dx for i in range(1, 20)]
                                            for x in x_steps:
                                                slice_line = LineString([(x, miny - 1.0), (x, maxy + 1.0)])
                                                intersect = poly.intersection(slice_line)
                                                if intersect and not intersect.is_empty:
                                                    slice_points.append([x, intersect.centroid.y])
                                            # Sort west to east
                                            slice_points.sort(key=lambda pt: pt[0])
                                        else:
                                            # Slice horizontally (north-south range)
                                            y_steps = [miny + (i / 20.0) * dy for i in range(1, 20)]
                                            for y in y_steps:
                                                slice_line = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
                                                intersect = poly.intersection(slice_line)
                                                if intersect and not intersect.is_empty:
                                                    slice_points.append([intersect.centroid.x, y])
                                            # Sort south to north
                                            slice_points.sort(key=lambda pt: pt[1])
                                            
                                        if len(slice_points) >= 2:
                                            lines.append(slice_points)
                                            print(f"[OFFLINE GIS] Extracted spine centerline for polygon natural boundary with {len(slice_points)} points.", flush=True)
                                except Exception as e:
                                    print(f"[OFFLINE GIS] Failed to extract spine centerline for polygon: {e}", flush=True)
                                            
        if lines:
            print(f"[OFFLINE GIS] Successfully located natural boundary '{name}' in local datasets. Segments: {len(lines)}", flush=True)
            return {
                "status": "success",
                "name": name,
                "paths": lines,
                "message": f"Retrieved {len(lines)} path segments for boundary '{name}' offline from Natural Earth."
            }
            
    except Exception as e:
        print(f"[OFFLINE GIS] Local query error: {e}. Falling back to live Overpass API...", flush=True)

    # Fallback to online OSM Overpass API
    try:
        _rate_limit(3.0)
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:15];
        (
          relation["name"="{name}"];
          way["name"="{name}"];
          relation["name"="{name} River"];
          way["name"="{name} River"];
          relation["name"="{name} Strait"];
          way["name"="{name} Strait"];
          relation["name"="Bosphorus"];
          way["name"="Bosphorus"];
          relation["name"="Bosporus"];
          way["name"="Bosporus"];
        );
        out geom;
        """
        headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
        r = httpx.post(overpass_url, data={"data": query}, headers=headers, timeout=30.0)
        if r.status_code != 200:
            return {"status": "error", "message": f"OSM Overpass API returned HTTP {r.status_code}"}
            
        data = r.json()
        elements = data.get("elements", [])
        if not elements:
            return {"status": "error", "message": f"No OSM features found matching natural boundary: '{name}'"}
            
        lines = []
        for el in elements:
            if el.get("type") == "way" and el.get("geometry"):
                pts = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
                if len(pts) >= 2:
                    lines.append(pts)
            elif el.get("type") == "relation" and el.get("members"):
                for mem in el["members"]:
                    if mem.get("type") == "way" and mem.get("geometry"):
                        pts = [(pt["lon"], pt["lat"]) for pt in mem["geometry"]]
                        if len(pts) >= 2:
                            lines.append(pts)
                            
        if not lines:
            return {"status": "error", "message": f"OSM returned elements but no valid geometry for: '{name}'"}
            
        return {
            "status": "success",
            "name": name,
            "paths": lines,
            "message": f"Retrieved {len(lines)} path segments for boundary '{name}' from OSM Overpass."
        }
    except Exception as e:
        return {"status": "error", "message": f"OSM Overpass query error: {e}"}

# ─── 3. Wikipedia Demographics Extraction Tool ────────────────────────────────




def find_contested_provinces(polities: List[str], year: int, target_countries: Optional[List[str]] = None, is_partition: bool = False) -> List[str]:
    """
    Find all modern provinces that overlap or border the baseline geometries 
    of the primary conflict polities in the Cliopatria database.
    """
    from backend.tools.spatial_cache import SimulationCache
    from backend.tools.country_polygons import get_country_polygon_loader
    from backend.tools.baseline_resolver import _get_resolved_baseline_geometry
    from shapely.geometry import shape, box
    
    cache_inst = SimulationCache.get_instance()
    tc_list = target_countries or []
    cached = cache_inst.get_contested_provinces(polities, year, tc_list, is_partition)
    if cached is not None:
        return cached

    loader = get_country_polygon_loader()
    contested = set()
    
    disputed_geoms = []
    if is_partition:
        disputed_path = os.path.join(DATA_DIR, "ne_10m_admin_0_disputed_areas.geojson")
        if os.path.exists(disputed_path):
            try:
                with open(disputed_path, "r", encoding="utf-8") as f:
                    d_data = json.load(f)
                    for feat in d_data.get("features", []):
                        g = feat.get("geometry")
                        if g:
                            disputed_geoms.append(shape(g))
            except Exception as e:
                print(f"[SIMULATOR] Error loading disputed areas: {e}")
    
    party_shapes = []
    for polity in polities:
        sh, _, tier = _get_resolved_baseline_geometry(polity, year)
        if sh is not None:
            print(f"[RESOLVER] Baseline shape for '{polity}' ({year} AD) resolved via {tier}. Bounds: {sh.bounds}", flush=True)
            party_shapes.append(sh)
                
    if not party_shapes:
        return []
        
    for f in loader.provinces_data:
        props = f.get("properties", {})
        admin = props.get("admin")
        
        if target_countries and admin:
            matched = False
            for country in target_countries:
                if country.lower() in admin.lower() or admin.lower() in country.lower():
                    matched = True
                    break
            if not matched:
                continue
                
        geom_dict = f.get("geometry")
        if not geom_dict:
            continue
        try:
            prov_shape = shape(geom_dict)
            prov_bounds = prov_shape.bounds
            
            bbox = box(*prov_bounds)
            intersect_count = 0
            is_contested = False
            for p_sh in party_shapes:
                if p_sh.bounds[0]-1.0 <= prov_bounds[2] and prov_bounds[0] <= p_sh.bounds[2]+1.0 and \
                   p_sh.bounds[1]-1.0 <= prov_bounds[3] and prov_bounds[1] <= p_sh.bounds[3]+1.0:
                    
                    try:
                        if prov_shape.intersects(p_sh) or prov_shape.distance(p_sh) < 0.1:
                            intersect_count += 1
                            if not is_partition or len(party_shapes) < 2:
                                is_contested = True
                    except Exception:
                        pass
            
            if is_partition and len(party_shapes) >= 2:
                if intersect_count >= 2:
                    is_contested = True
            
            if is_contested and is_partition and disputed_geoms:
                intersects_disputed = False
                for d_sh in disputed_geoms:
                    try:
                        if prov_shape.intersects(d_sh):
                            intersects_disputed = True
                            break
                    except Exception:
                        pass
                if not intersects_disputed:
                    is_contested = False
                    
            if is_contested:
                pname = props.get("name")
                if pname and admin:
                    contested.add(f"{pname} ({admin})")
        except Exception:
            pass
            
    result_list = sorted(list(contested))
    cache_inst.set_contested_provinces(polities, year, tc_list, is_partition, result_list)
    return result_list


def get_natural_boundary_geometry(name: str, region: str = "") -> Tuple[Optional[Any], Optional[List[Any]]]:
    """
    Get Shapely geometry and coordinate paths for a natural boundary by name.
    """
    res = natural_boundary_tool(name)
    if res.get("status") == "success" and res.get("paths"):
        lines = [LineString(p) for p in res["paths"] if len(p) >= 2]
        if lines:
            geom = lines[0] if len(lines) == 1 else MultiLineString(lines)
            return geom, res["paths"]
    return None, None
