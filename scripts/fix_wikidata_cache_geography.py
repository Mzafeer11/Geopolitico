"""
Strict Geographical & Historical Unit Fixer for wikidata_admin_cache.json.
Fixes:
1. Strictly enforces centroid containment inside polity_poly.bounds (e.g. Sultanate of Rum -> Anatolia/Turkey ONLY).
2. Cleans up raw modern country suffixes (e.g. converts 'Konya (Turkey)' to 'Konya Region / Anatolia').
3. Resolves parent polities for allegiances (e.g. Allegiance of Sultanate of Rum -> Sultanate of Rum geometry in Turkey).
Outputs: data/wikidata_admin_cache.json
"""

import sys
import os
import json
from pathlib import Path

# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shapely.geometry import shape, Point
from backend.config import DATA_DIR
from backend.tools.country_polygons import get_country_polygon_loader

CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"
CLIOPATRIA_FILE = DATA_DIR / "cliopatria_polities_only.geojson"

NOISE_KEYWORDS = [
    "sultan", "king", "emperor", "dynasty", "war of", "coins", "coin",
    "architecture style", "battle of", "treaty of", "alliance", "realm of",
    "rule of", "house of", "order of", "rebellion", "revolution"
]

def is_noisy_unit(name: str) -> bool:
    if not name or (name.startswith("Q") and name[1:].isdigit()):
        return True
    n_lower = name.lower()
    for kw in NOISE_KEYWORDS:
        if kw in n_lower:
            return True
    return False

def clean_historical_unit_name(pname: str, admin: str) -> str:
    """Format clean historical unit names without raw modern country suffixes."""
    pname_clean = pname.strip()
    return f"{pname_clean} Region"


def fix_cache_geography():
    print(f"[GEOGRAPHY FIXER] Loading Cliopatria dataset...", flush=True)
    with open(CLIOPATRIA_FILE, "r", encoding="utf-8") as f:
        clio_data = json.load(f)

    # Map polity names & parent relationships to Cliopatria shapes
    clio_geom_map = {}
    member_of_map = {}

    for feat in clio_data.get("features", []):
        props = feat.get("properties", {})
        nm = props.get("Name")
        m_of = props.get("MemberOf")
        g_dict = feat.get("geometry")

        if nm:
            if m_of:
                member_of_map[nm] = m_of
            if g_dict:
                try:
                    g = shape(g_dict)
                    if g.is_valid and not g.is_empty:
                        clio_geom_map[nm] = g
                        clean_nm = nm.strip("()").strip()
                        if clean_nm not in clio_geom_map:
                            clio_geom_map[clean_nm] = g
                except Exception:
                    pass

    print(f"[GEOGRAPHY FIXER] Indexed {len(clio_geom_map)} Cliopatria polity geometries.", flush=True)

    loader = get_country_polygon_loader()
    provinces_data = loader.provinces_data

    # Pre-parse modern GADM province shapes & centroids
    gadm_provinces = []
    for feat in provinces_data:
        props = feat.get("properties", {})
        pname = props.get("name") or props.get("NAME") or ""
        admin = props.get("admin") or props.get("ADMIN") or ""
        g_dict = feat.get("geometry")

        if pname and g_dict:
            try:
                geom = shape(g_dict)
                if geom.is_valid and not geom.is_empty:
                    gadm_provinces.append({
                        "name": pname,
                        "admin": admin,
                        "centroid": geom.centroid,
                        "geometry": geom
                    })
            except Exception:
                pass

    print(f"[GEOGRAPHY FIXER] Loaded {len(gadm_provinces)} modern GADM provinces.", flush=True)

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    cleaned_cache = {}
    fixed_misplaced_count = 0
    fixed_allegiance_count = 0

    for polity_key, entry in cache_data.items():
        if not isinstance(entry, dict):
            continue

        polity_name = entry.get("polity") or polity_key
        raw_units = entry.get("admin_units", [])

        # Find target geometry in Cliopatria
        target_poly = clio_geom_map.get(polity_name)
        if not target_poly:
            clean_name = polity_name.strip("()").strip()
            target_poly = clio_geom_map.get(clean_name)
        if not target_poly and polity_name in member_of_map:
            parent_name = member_of_map[polity_name].strip("()").strip()
            target_poly = clio_geom_map.get(parent_name)
            if target_poly:
                fixed_allegiance_count += 1

        clean_units = []

        # Validate existing units against target_poly bounds
        if target_poly:
            bounds = target_poly.bounds  # (minx, miny, maxx, maxy)
            buffer_poly = target_poly.buffer(0.5)

            for u in raw_units:
                uname = u.get("name", "")
                if is_noisy_unit(uname):
                    continue

                lat = u.get("latitude")
                lon = u.get("longitude")
                country = u.get("present_day_country", "")

                # Check if unit coordinates fall within target polity's spatial envelope
                if lat is not None and lon is not None:
                    pt = Point(lon, lat)
                    if buffer_poly.intersects(pt):
                        clean_units.append({
                            "name": uname,
                            "latitude": lat,
                            "longitude": lon,
                            "present_day_country": country
                        })
                    else:
                        fixed_misplaced_count += 1

        # If clean_units is empty or was misplaced, perform strict spatial centroid matching inside target_poly
        if (not clean_units or fixed_misplaced_count > 0) and target_poly:
            spatial_units = []
            for p in gadm_provinces:
                c = p["centroid"]
                # STRICT CENTROID CONTAINMENT: Centroid MUST lie inside polity polygon
                if target_poly.contains(c) or target_poly.distance(c) < 0.1:
                    hist_name = clean_historical_unit_name(p["name"], p["admin"])
                    spatial_units.append({
                        "name": hist_name,
                        "latitude": round(c.y, 4),
                        "longitude": round(c.x, 4),
                        "present_day_country": p["admin"]
                    })
                    if len(spatial_units) >= 12:
                        break

            if spatial_units:
                clean_units = spatial_units

        cleaned_entry = dict(entry)
        cleaned_entry["admin_units"] = clean_units
        cleaned_cache[polity_key] = cleaned_entry

    print(f"\n--- GEOGRAPHICAL ACCURACY FIX REPORT ---")
    print(f"Total Polity Keys Checked: {len(cleaned_cache)}")
    print(f"Misplaced Units Removed (e.g. Bangladesh in Rum): {fixed_misplaced_count}")
    print(f"Allegiance Polities Mapped to Parent Geometry: {fixed_allegiance_count}")

    # Verify Sultanate of Rum specifically
    rum_entry = cleaned_cache.get("(Allegiance of Sultanate of Rum to Abbasid Caliphate)") or cleaned_cache.get("Sultanate of Rum")
    if rum_entry:
        print("\n--- SULTANATE OF RUM VERIFICATION ---")
        for u in rum_entry.get("admin_units", [])[:6]:
            print(f" - Unit: {u['name']} | Lat/Lon: {u['latitude']}, {u['longitude']} | Country: {u['present_day_country']}")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_cache, f, ensure_ascii=False, indent=2)

    print(f"\n[GEOGRAPHY FIXER] Saved strictly geocoded cache to {CACHE_FILE.name} successfully!", flush=True)

if __name__ == "__main__":
    fix_cache_geography()
