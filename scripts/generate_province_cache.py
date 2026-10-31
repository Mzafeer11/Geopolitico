import os
import sys
import json
import time
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Base Directory Setup
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

load_dotenv(WORKSPACE_ROOT / ".env", override=True)

# Imports from backend
from backend.config import DATA_DIR, GROQ_API_KEY
from backend.tools.gis_tools import geocode_landmark_tool

# Input & Output Paths
CLIOPATRIA_PATH = DATA_DIR / "cliopatria_polities.geojson"
OUTPUT_CACHE_PATH = DATA_DIR / "ai_province_cache.json"
LOG_PATH = DATA_DIR / "ai_province_generation_log.json"
PLEIADES_PLACES_PATH = WORKSPACE_ROOT / "pleiades_gis_data" / "data" / "gis" / "places.csv"

# Pydantic schema for structured output
class ProvinceItem(BaseModel):
    name: str = Field(description="Historical name of the province/eyalet/theme/crown land/subnational division")
    capital_historical: str = Field(description="Historical name of the capital city/seat of this province")
    capital_modern: str = Field(description="Modern name of the capital city and country (e.g. 'Edirne, Turkey') for geocoding")
    tier: str = Field(description="Administrative division type/tier (e.g. Eyalet, Theme, Duchy, Crown Land, Satrapy, Province)")

class EmpireProvincesResponse(BaseModel):
    empire_name: str
    peak_period_description: str
    provinces: List[ProvinceItem]


def load_pleiades_gazetteer() -> Dict[str, Dict[str, float]]:
    """Loads Pleiades places.csv into a name-to-coordinate lookup map for ancient fallback."""
    lookup = {}
    if not PLEIADES_PLACES_PATH.exists():
        return lookup
    try:
        import csv
        with open(PLEIADES_PLACES_PATH, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = (row.get('title') or '').strip().lower()
                repr_lat = row.get('representative_latitude')
                repr_lon = row.get('representative_longitude')
                if title and repr_lat and repr_lon:
                    try:
                        lookup[title] = {
                            "lat": float(repr_lat),
                            "lon": float(repr_lon)
                        }
                    except ValueError:
                        continue
    except Exception as e:
        print(f"[WARN] Could not load Pleiades gazetteer: {e}", flush=True)
    return lookup


def compute_bbox(geometry: Dict[str, Any]) -> List[float]:
    """Computes bounding box [min_lon, min_lat, max_lon, max_lat] for GeoJSON geometry."""
    coords = geometry.get("coordinates", [])
    
    lons, lats = [], []
    def extract_pts(pts):
        if not pts:
            return
        if isinstance(pts[0], (int, float)):
            lons.append(pts[0])
            lats.append(pts[1])
        else:
            for p in pts:
                extract_pts(p)
                
    extract_pts(coords)
    if not lons or not lats:
        return [-180.0, -90.0, 180.0, 90.0]
    return [min(lons), min(lats), max(lons), max(lats)]


MIN_EMPIRE_AREA_KM2 = 5000.0  # Polities under 5,000 km² do not have subnational provinces

MICROSTATE_KEYWORDS = [
    "free city", "free imperial city", "city-state", "city state", 
    "san marino", "monaco", "liechtenstein", "andorra", "vatican",
    "singapore", "republic of ragusa", "lordship of", "barony of", "abbey of"
]

def is_microstate(name: str, area: float) -> bool:
    name_lower = name.lower()
    if area < MIN_EMPIRE_AREA_KM2:
        return True
    if any(kw in name_lower for kw in MICROSTATE_KEYWORDS):
        return True
    return False


def extract_cliopatria_polity_peaks(target_names: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Extracts non-relation, non-parenthesized polities and determines their peak area & bbox."""
    print("[INFO] Loading Cliopatria features...", flush=True)
    with open(CLIOPATRIA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    polity_peaks: Dict[str, Dict[str, Any]] = {}
    target_names_lower = [t.lower() for t in target_names] if target_names else None

    for ft in data.get("features", []):
        props = ft.get("properties", {})
        name = props.get("Name", "").strip()
        ftype = props.get("Type", "")

        # Filtering Rules
        if not name:
            continue
        if ftype == "RELATION":
            continue
        if name.startswith("(") and name.endswith(")"):
            continue
            
        if target_names_lower:
            if not any(t in name.lower() for t in target_names_lower):
                continue

        area = props.get("Area", 0.0)
        from_year = props.get("FromYear")
        to_year = props.get("ToYear")
        geom = ft.get("geometry")

        if name not in polity_peaks or area > polity_peaks[name]["peak_area"]:
            bbox = compute_bbox(geom) if geom else [-180.0, -90.0, 180.0, 90.0]
            polity_peaks[name] = {
                "name": name,
                "peak_area": area,
                "peak_from_year": from_year,
                "peak_to_year": to_year,
                "bbox": bbox,
                "wikipedia": props.get("Wikipedia", ""),
                "wikidata": props.get("Wikidata", "")
            }

    # Filter out microstates and small states (< 5,000 km²)
    filtered_peaks = {}
    for name, info in polity_peaks.items():
        if is_microstate(name, info["peak_area"]):
            continue
        filtered_peaks[name] = info

    print(f"[INFO] Found {len(filtered_peaks)} candidate polities (excluding microstates < 5,000 km²).", flush=True)
    return filtered_peaks



def call_llm_for_provinces(empire_info: Dict[str, Any]) -> Tuple[Optional[EmpireProvincesResponse], bool]:
    """Queries LLM strictly using Groq models first, then OpenRouter candidates second.
    Azure OpenAI is completely excluded.
    Returns (response, rate_limit_encountered_flag)
    """
    name = empire_info["name"]
    from_yr = empire_info["peak_from_year"]
    to_yr = empire_info["peak_to_year"]
    bbox = empire_info["bbox"]

    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are an expert historical cartographer and historian specializing in administrative geography. "
                "Provide accurate historical subnational administrative divisions/provinces for empires at their territorial peak. "
                "Do NOT invent fictional provinces. Every province must correspond to a real historical division and city."
            )
        },
        {
            "role": "user",
            "content": (
                f"List the major administrative provinces/divisions of the '{name}' at its peak territorial extent "
                f"(approx. {from_yr} CE to {to_yr} CE). Include provinces of vassal states or crown lands directly "
                f"administered or subordinate to the empire at this peak.\n\n"
                f"Approximate Spatial Bounding Box [min_lon, min_lat, max_lon, max_lat]: {bbox}\n\n"
                f"For EACH province, provide:\n"
                f"1. Historical province name\n"
                f"2. Historical capital/seat city name\n"
                f"3. Modern name of that capital city and country (e.g., 'Edirne, Turkey' or 'Aachen, Germany') for geocoding\n"
                f"4. The administrative tier (e.g., Eyalet, Theme, Duchy, Crown Land, Satrapy, Province)\n"
            )
        }
    ]

    rate_limit_flag = False

    # 1. Groq Models (llama-3.3-70b-versatile, gpt-oss-120b, gpt-oss-20b)
    groq_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if groq_key:
        groq_models = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for g_model in groq_models:
            print(f"[LLM] Attempting Groq model '{g_model}' for '{name}'...", flush=True)
            try:
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    model=g_model,
                    groq_api_key=groq_key,
                    temperature=0.1,
                    timeout=30.0,
                    max_retries=1
                )
                structured_llm = llm.with_structured_output(EmpireProvincesResponse)
                res = structured_llm.invoke(prompt_messages)
                if res and hasattr(res, "provinces") and res.provinces:
                    print(f"[LLM SUCCESS] Groq '{g_model}' returned {len(res.provinces)} provinces for '{name}'.", flush=True)
                    return res, False
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str or "quota" in err_str or "too many requests" in err_str:
                    print(f"[RATE LIMIT DETECTED] Groq model '{g_model}' rate limit hit for '{name}': {e}", flush=True)
                    rate_limit_flag = True
                else:
                    print(f"[WARN] Groq model '{g_model}' failed for '{name}': {e}", flush=True)

    # 2. OpenRouter Models (Free Candidates)
    openrouter_key = (os.getenv("OPEN_ROUTER_API") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        openrouter_models = [
            "google/gemma-4-26b-a4b-it:free",
            "openai/gpt-oss-20b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-nano-12b-v2:free"
        ]
        from langchain_openai import ChatOpenAI
        for or_model in openrouter_models:
            print(f"[LLM] Attempting OpenRouter model '{or_model}' for '{name}'...", flush=True)
            try:
                llm = ChatOpenAI(
                    model=or_model,
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=0.1,
                    timeout=30.0,
                    max_retries=1
                )
                structured_llm = llm.with_structured_output(EmpireProvincesResponse)
                res = structured_llm.invoke(prompt_messages)
                if res and hasattr(res, "provinces") and res.provinces:
                    print(f"[LLM SUCCESS] OpenRouter '{or_model}' returned {len(res.provinces)} provinces for '{name}'.", flush=True)
                    return res, False
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str or "quota" in err_str or "too many requests" in err_str:
                    print(f"[RATE LIMIT DETECTED] OpenRouter model '{or_model}' rate limit hit for '{name}': {e}", flush=True)
                    rate_limit_flag = True
                else:
                    print(f"[WARN] OpenRouter model '{or_model}' failed for '{name}': {e}", flush=True)

    print(f"[ERROR] All Groq & OpenRouter models failed for '{name}'. (Rate Limit Hit: {rate_limit_flag})", flush=True)
    return None, rate_limit_flag


def safe_geocode(query: str) -> Dict[str, Any]:
    """Safe wrapper around geocode_landmark_tool to catch network/SSL exceptions."""
    try:
        return geocode_landmark_tool(query)
    except Exception as e:
        return {"status": "error", "message": str(e)}


def geocode_and_validate_provinces(
    provinces: List[ProvinceItem],
    bbox: List[float],
    pleiades_lookup: Dict[str, Dict[str, float]]
) -> List[Dict[str, Any]]:
    """Geocodes province capitals using Nominatim + Pleiades and validates spatial bounds."""
    min_lon, min_lat, max_lon, max_lat = bbox
    # Buffer bbox by 2.0 degrees (~200km) to account for capital seats near boundaries
    b_min_lon, b_min_lat = min_lon - 2.0, min_lat - 2.0
    b_max_lon, b_max_lat = max_lon + 2.0, max_lat + 2.0

    processed_units = []

    for p in provinces:
        lat, lon = None, None
        source = "unknown"
        confidence = "low"

        modern_query = p.capital_modern.strip()
        hist_query = p.capital_historical.strip()

        # 1. Primary: Nominatim with modern city name
        geo_res = safe_geocode(modern_query)
        if geo_res.get("status") == "success":
            lat = geo_res.get("latitude")
            lon = geo_res.get("longitude")
            source = "nominatim_modern"
        else:
            # Try historical name with Nominatim
            geo_res_hist = safe_geocode(hist_query)
            if geo_res_hist.get("status") == "success":
                lat = geo_res_hist.get("latitude")
                lon = geo_res_hist.get("longitude")
                source = "nominatim_historical"

        # 2. Fallback: Pleiades Gazetteer
        if lat is None or lon is None:
            plei_match = pleiades_lookup.get(hist_query.lower()) or pleiades_lookup.get(modern_query.lower())
            if plei_match:
                lat = plei_match["lat"]
                lon = plei_match["lon"]
                source = "pleiades_gazetteer"

        # 3. Spatial Validation
        if lat is not None and lon is not None:
            if b_min_lon <= lon <= b_max_lon and b_min_lat <= lat <= b_max_lat:
                confidence = "high" if "nominatim" in source else "medium"
            else:
                confidence = "low"
                print(f"[BOUNDS WARN] Capital '{modern_query}' ({lat}, {lon}) outside empire bbox {bbox}.", flush=True)

        processed_units.append({
            "name": p.name,
            "capital_historical": p.capital_historical,
            "capital_modern": p.capital_modern,
            "tier": p.tier,
            "latitude": lat,
            "longitude": lon,
            "geocode_source": source,
            "confidence": confidence
        })

    return processed_units


def run_pipeline(target_polities: Optional[List[str]] = None):
    """Main execution workflow with checkpointing, resume support, and strict rate-limit stopping."""
    pleiades_lookup = load_pleiades_gazetteer()
    polity_peaks = extract_cliopatria_polity_peaks(target_polities)

    # Load existing cache if present to preserve/append and resume
    existing_cache = {}
    if OUTPUT_CACHE_PATH.exists():
        try:
            with open(OUTPUT_CACHE_PATH, 'r', encoding='utf-8') as f:
                existing_cache = json.load(f)
            print(f"[RESUME] Loaded {len(existing_cache)} existing entries from cache.", flush=True)
        except Exception as e:
            print(f"[WARN] Could not load existing cache: {e}", flush=True)

    generation_logs = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                generation_logs = json.load(f)
        except Exception:
            pass

    processed_count = 0
    consecutive_failures = 0

    for idx, (name, info) in enumerate(polity_peaks.items(), start=1):
        # SKIP if already present in cache with valid admin_units
        if name in existing_cache and existing_cache[name].get("admin_units"):
            print(f"[{idx}/{len(polity_peaks)}] Skipping '{name}' (Already in cache with {len(existing_cache[name]['admin_units'])} units).", flush=True)
            continue

        print(f"\n==========================================")
        print(f"[{idx}/{len(polity_peaks)}] Processing Polity: '{name}' (Peak: {info['peak_from_year']} - {info['peak_to_year']} CE, Area: {info['peak_area']:.1f} km²)")
        print(f"==========================================")

        llm_response, rate_limit_hit = call_llm_for_provinces(info)

        if not llm_response or not llm_response.provinces:
            consecutive_failures += 1
            print(f"[FAIL] No provinces returned for '{name}'. Consecutive failures: {consecutive_failures}/2", flush=True)
            generation_logs.append({"polity": name, "status": "failed", "error": "No LLM response / Rate limit"})
            
            with open(LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(generation_logs, f, indent=2, ensure_ascii=False)

            # AUTOMATIC STOP: If 2 consecutive polities fail due to rate limit or quota exhaustion, STOP IMMEDIATELY!
            if consecutive_failures >= 2:
                print(f"\n=====================================================", flush=True)
                print(f"[RATE LIMIT / QUOTA EXHAUSTED - AUTOMATIC STOP]", flush=True)
                print(f"All available Groq and OpenRouter models are rate-limited or quota-exhausted.", flush=True)
                print(f"Stopping pipeline cleanly to prevent useless looping.", flush=True)
                print(f"Total polities currently saved in cache: {len(existing_cache)}", flush=True)
                print(f"You can re-run 'python scripts/generate_province_cache.py --all' whenever limits reset.", flush=True)
                print(f"=====================================================\n", flush=True)
                sys.exit(0)
            continue

        # Reset consecutive failures counter on success
        consecutive_failures = 0

        print(f"[INFO] Geocoding {len(llm_response.provinces)} province capitals for '{name}'...", flush=True)
        admin_units = geocode_and_validate_provinces(llm_response.provinces, info["bbox"], pleiades_lookup)

        geocoded_count = sum(1 for u in admin_units if u["latitude"] is not None)
        high_conf_count = sum(1 for u in admin_units if u["confidence"] == "high")
        print(f"[RESULT] '{name}': {len(admin_units)} units generated, {geocoded_count} geocoded ({high_conf_count} high-confidence).", flush=True)

        existing_cache[name] = {
            "polity": name,
            "peak_year_from": info["peak_from_year"],
            "peak_year_to": info["peak_to_year"],
            "peak_area_km2": info["peak_area"],
            "bbox": info["bbox"],
            "source": "ai_generated_peak",
            "admin_units": admin_units
        }

        generation_logs.append({
            "polity": name,
            "status": "success",
            "total_units": len(admin_units),
            "geocoded_units": geocoded_count,
            "high_confidence_units": high_conf_count
        })

        processed_count += 1

        # Incremental Save Checkpoint after EVERY single polity
        with open(OUTPUT_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_cache, f, indent=2, ensure_ascii=False)

        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(generation_logs, f, indent=2, ensure_ascii=False)

    print(f"\n[FINISHED_STEP] Total polities currently stored in cache: {len(existing_cache)}")


if __name__ == "__main__":
    targets = ["Ottoman Empire", "Kingdom of the Franks", "Byzantine Empire", "Habsburg Monarchy", "Austrian Empire"]
    
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        targets = None # Run for all polities

    run_pipeline(targets)
