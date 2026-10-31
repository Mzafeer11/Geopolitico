"""
Wikidata Admin Cache Cleaning, Geocoding, and Subunit Enrichment Script.
1. Filters out non-geographic noise (titles, dynasties, coins, styles).
2. Geocodes missing (lat, lon) coordinates using GADM province centroids.
3. Fills empty allegiance/ancient polities via MemberOf/Components inheritance and GADM spatial clustering.
Outputs: data/wikidata_admin_cache.json
"""

import sys
import os
import json
import re
from pathlib import Path

# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shapely.geometry import shape
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
    if not name or name.startswith("Q") and name[1:].isdigit():
        return True
    n_lower = name.lower()
    for kw in NOISE_KEYWORDS:
        if kw in n_lower:
            return True
    return False


def build_gadm_spatial_index(loader):
    """Index modern GADM provinces by lowercased name and country for fast geocoding."""
    spatial_index = {}
    for feat in loader.provinces_data:
        props = feat.get("properties", {})
        pname = props.get("name") or props.get("NAME") or ""
        admin = props.get("admin") or props.get("ADMIN") or ""
        g_dict = feat.get("geometry")

        if not pname or not g_dict:
            continue

        try:
            geom = shape(g_dict)
            if geom.is_valid and not geom.is_empty:
                c = geom.centroid
                entry = {
                    "name": pname,
                    "admin": admin,
                    "latitude": round(c.y, 4),
                    "longitude": round(c.x, 4),
                    "geometry": geom
                }
                spatial_index[pname.lower()] = entry
                spatial_index[f"{pname.lower()} ({admin.lower()})"] = entry
        except Exception:
            pass

    return spatial_index


def clean_and_enrich_cache():
    print(f"[CACHE CLEANER] Loading cache from {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    print(f"[CACHE CLEANER] Loading Cliopatria dataset...", flush=True)
    with open(CLIOPATRIA_FILE, "r", encoding="utf-8") as f:
        clio_data = json.load(f)

    # Build MemberOf and Components mapping for polity inheritance
    member_of_map = {}
    components_map = {}
    clio_geom_map = {}

    for feat in clio_data.get("features", []):
        props = feat.get("properties", {})
        nm = props.get("Name")
        m_of = props.get("MemberOf")
        comps = props.get("Components")
        g_dict = feat.get("geometry")

        if nm:
            if m_of:
                member_of_map[nm] = m_of
            if comps:
                components_map[nm] = comps
            if g_dict:
                try:
                    g = shape(g_dict)
                    if g.is_valid and not g.is_empty:
                        clio_geom_map[nm] = g
                except Exception:
                    pass

    loader = get_country_polygon_loader()
    gadm_index = build_gadm_spatial_index(loader)
    print(f"[CACHE CLEANER] Built GADM index with {len(gadm_index)} modern province centroids.", flush=True)

    cleaned_cache = {}
    noise_removed = 0
    geocoded_count = 0
    inherited_count = 0
    clustered_count = 0

    for polity_key, entry in cache_data.items():
        if not isinstance(entry, dict):
            continue

        raw_units = entry.get("admin_units", [])
        clean_units = []

        # 1. Noise Removal & Geocoding
        for u in raw_units:
            uname = u.get("name", "")
            if is_noisy_unit(uname):
                noise_removed += 1
                continue

            lat = u.get("latitude")
            lon = u.get("longitude")
            country = u.get("present_day_country", "")

            # Geocode missing coordinates using GADM index
            if lat is None or lon is None:
                g_entry = gadm_index.get(uname.lower())
                if not g_entry and country:
                    g_entry = gadm_index.get(f"{uname.lower()} ({country.lower()})")

                if g_entry:
                    lat = g_entry["latitude"]
                    lon = g_entry["longitude"]
                    geocoded_count += 1

            clean_units.append({
                "name": uname,
                "latitude": lat,
                "longitude": lon,
                "present_day_country": country
            })

        # 2. MemberOf / Parent-Relation Inheritance if 0 units
        polity_name = entry.get("polity") or polity_key
        if not clean_units and polity_name in member_of_map:
            parent_name = member_of_map[polity_name]
            clean_parent = parent_name.strip("()").strip()
            if clean_parent in cache_data and cache_data[clean_parent].get("admin_units"):
                parent_units = cache_data[clean_parent]["admin_units"]
                clean_units = [dict(pu) for pu in parent_units if not is_noisy_unit(pu.get("name", ""))]
                if clean_units:
                    inherited_count += 1

        # 3. GADM Spatial Clustering Fallback if still 0 units
        if not clean_units and polity_name in clio_geom_map:
            polity_poly = clio_geom_map[polity_name]
            clustered_units = []

            for feat in loader.provinces_data:
                props = feat.get("properties", {})
                pname = props.get("name") or props.get("NAME") or ""
                admin = props.get("admin") or props.get("ADMIN") or ""
                g_dict = feat.get("geometry")

                if not pname or not g_dict:
                    continue

                try:
                    p_geom = shape(g_dict)
                    if p_geom.is_valid and p_geom.intersects(polity_poly):
                        inter_area = p_geom.intersection(polity_poly).area
                        if inter_area / p_geom.area >= 0.4:
                            c = p_geom.centroid
                            clustered_units.append({
                                "name": f"{pname} ({admin})",
                                "latitude": round(c.y, 4),
                                "longitude": round(c.x, 4),
                                "present_day_country": admin
                            })
                            if len(clustered_units) >= 15:
                                break
                except Exception:
                    pass

            if clustered_units:
                clean_units = clustered_units
                clustered_count += 1

        cleaned_entry = dict(entry)
        cleaned_entry["admin_units"] = clean_units
        cleaned_cache[polity_key] = cleaned_entry

    print(f"\n--- WIKIDATA CACHE CLEANING & ENRICHMENT REPORT ---")
    print(f"Total Keys Processed: {len(cleaned_cache)}")
    print(f"Non-Geographic Noise Items Removed: {noise_removed}")
    print(f"Missing Coordinates Geocoded: {geocoded_count}")
    print(f"Empty Polities Inherited via Parent MemberOf: {inherited_count}")
    print(f"Empty Ancient Polities Enriched via GADM Spatial Clustering: {clustered_count}")

    # Calculate final populated count
    final_populated = sum(1 for k, v in cleaned_cache.items() if len(v.get("admin_units", [])) > 0)
    print(f"Final Populated Polities in Cache: {final_populated} / {len(cleaned_cache)} ({final_populated/len(cleaned_cache)*100:.1f}%)")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_cache, f, ensure_ascii=False, indent=2)

    print(f"[CACHE CLEANER] Saved clean cache to {CACHE_FILE.name} successfully!", flush=True)

if __name__ == "__main__":
    clean_and_enrich_cache()
