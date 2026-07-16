import os
import httpx
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from shapely.geometry import LineString, MultiLineString
from backend.config import GITHUB_TOKEN, GITHUB_API_URL, GITHUB_MODELS, EXHAUSTED_MODELS

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
        
        files_to_search = [
            ("ne_50m_rivers_lake_centerlines.geojson", ["name", "name_alt", "name_en"]),
            ("ne_10m_rivers_lake_centerlines.geojson", ["name", "name_alt", "name_en"]),
            ("ne_50m_lakes.geojson", ["name", "name_alt", "name_en"]),
            ("ne_50m_geography_regions_polys.geojson", ["NAME", "NAMEALT"]),
            ("ne_10m_geography_regions_polys.geojson", ["NAME", "NAMEALT"]),
            ("ne_50m_geography_marine_polys.geojson", ["name", "namealt"]),
            ("ne_10m_geography_marine_polys.geojson", ["name", "namealt"])
        ]
        
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

class DemographicFact(BaseModel):
    province: str = Field(description="Name of the province/region (e.g. Punjab, Bengal, Kashmir).")
    demographic_group: str = Field(description="The group name (e.g. Muslim, Hindu, Sikh, Non-Muslim).")
    percentage: float = Field(description="Percentage value (0-100).")

class ExtractedDemographics(BaseModel):
    is_relevant: bool = Field(description="True if the text contains authentic, historical demographic percentages matching the target region.")
    facts: List[DemographicFact] = Field(default=[], description="List of verified demographic facts found in the text.")
    summary: str = Field(description="A brief summary explaining the demographic distribution in the text.")

def _fetch_wikipedia_raw_extract(query: str) -> str:
    """Fetch raw extract text from Wikipedia search."""
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "utf8": 1
        }
        headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
        
        r = httpx.get(search_url, params=search_params, headers=headers, timeout=12.0)
        if r.status_code != 200:
            return ""
        data = r.json()
        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return ""
            
        articles = []
        for res in search_results[:2]:
            title = res["title"]
            extract_params = {
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "titles": title,
                "format": "json",
                "redirects": 1
            }
            r2 = httpx.get(search_url, params=extract_params, headers=headers, timeout=12.0)
            if r2.status_code == 200:
                data2 = r2.json()
                pages = data2.get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    extract = page_info.get("extract", "")
                    if extract:
                        articles.append(f"Wikipedia Article: {title}\n{extract}")
        return "\n\n".join(articles)
    except Exception:
        return ""

def wikipedia_demographics_tool(scenario: str, target_region: str, target_countries: List[str]) -> Dict[str, Any]:
    """Query Wikipedia for demographics, verify content relevance, and extract structured facts."""
    search_term = f"Demographics of {target_region}" if target_region else f"{scenario} demographics"
    if target_countries:
        search_term += f" {' '.join(target_countries)}"
        
    print(f"[DEMOGRAPHICS TOOL] Searching Wikipedia for: '{search_term}'...", flush=True)
    raw_text = _fetch_wikipedia_raw_extract(search_term)
    if not raw_text:
        # Fallback search query
        fallback_term = f"1941 Census of India demographics" if any(c.lower() in ["india", "pakistan"] for c in target_countries) else f"{scenario} demographics"
        print(f"[DEMOGRAPHICS TOOL] First query returned no results. Trying fallback: '{fallback_term}'...", flush=True)
        raw_text = _fetch_wikipedia_raw_extract(fallback_term)
        
    if not raw_text:
        return {"status": "error", "message": "No relevant Wikipedia articles found."}
        
    # Run structured LLM call to verify and parse facts
    available_models = [m for m in GITHUB_MODELS if m not in EXHAUSTED_MODELS]
    if not available_models:
        available_models = GITHUB_MODELS.copy()
        
    model_to_use = None
    for m in available_models:
        if "gpt-4o" in m.lower():
            model_to_use = m
            break
    if not model_to_use:
        model_to_use = available_models[0]
        
    clean_model = model_to_use.replace("openai/", "", 1) if model_to_use.startswith("openai/") else model_to_use
    token = os.environ.get("GITHUB_TOKEN", GITHUB_TOKEN)
    
    print(f"[DEMOGRAPHICS TOOL] Invoking extraction model '{clean_model}'...", flush=True)
    try:
        llm = ChatOpenAI(
            model=clean_model,
            api_key=token,
            base_url=GITHUB_API_URL,
            temperature=0.0,
            max_tokens=2048,
            timeout=50.0
        )
        if "gpt-4o" not in clean_model.lower():
            try:
                llm.supports_function_calling = lambda: False
            except Exception:
                pass
        structured_llm = llm.with_structured_output(ExtractedDemographics)
        
        system_prompt = f"""You are a demographic data validation and verification system.
Verify if the raw text contains historical, authentic demographic figures for the target scenario: "{scenario}".
If relevant figures are found, extract the exact percentages for each province and list them. Discard irrelevant or modern noise.
Return a verified structured output."""
        
        messages = [
            SystemMessage(content=system_prompt),
            SystemMessage(content=f"Raw Wikipedia Text:\n{raw_text}")
        ]
        res: ExtractedDemographics = structured_llm.invoke(messages)
        
        if not res.is_relevant or not res.facts:
            return {
                "status": "error",
                "message": "Wikipedia articles found but contained no relevant historical demographics for the scenario."
            }
            
        facts_list = [{"province": f.province, "group": f.demographic_group, "percentage": f.percentage} for f in res.facts]
        return {
            "status": "success",
            "facts": facts_list,
            "summary": res.summary,
            "message": f"Successfully validated and extracted {len(facts_list)} demographic facts from Wikipedia."
        }
    except Exception as e:
        return {"status": "error", "message": f"Demographics validation LLM invocation failed: {e}"}
