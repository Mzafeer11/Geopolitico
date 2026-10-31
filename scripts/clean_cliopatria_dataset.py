"""
Data Cleaning & Hierarchy Classification Script for Cliopatria GeoJSON.
Organizes all 13,765 features with Zero Data Loss:
- Standardizes clean names (no outer parentheses)
- Assigns explicit entity_type (SOVEREIGN_STATE, REGIONAL_POLITY, SUPRANATIONAL, PERSONAL_UNION, ALLIANCE_DEPENDENCY)
- Decomposes trans-continental MultiPolygons into regional landmass components
Output: data/cliopatria_cleaned.geojson
"""

import sys
import json
import unicodedata
from pathlib import Path
from shapely.geometry import shape, mapping, MultiPolygon, Polygon

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

INPUT_FILE = DATA_DIR / "cliopatria_polities_only.geojson"
OUTPUT_FILE = DATA_DIR / "cliopatria_cleaned.geojson"

def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    nfkd = unicodedata.normalize("NFKD", s)
    s_clean = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return " ".join(s_clean.replace("-", " ").replace("_", " ").split())

def classify_entity_type(name: str, raw_name: str) -> str:
    n_lower = name.lower()
    r_lower = raw_name.lower()
    
    if "personal union" in r_lower or "union of" in r_lower or "personal union" in n_lower:
        return "PERSONAL_UNION"
    if "allegiance" in r_lower or "alliance" in r_lower or "tributary" in r_lower or "vassal" in r_lower:
        return "ALLIANCE_DEPENDENCY"
    if "holy roman empire" in r_lower or "minor states" in r_lower or "federation" in r_lower:
        return "SUPRANATIONAL"
    if any(k in n_lower for k in ["duchy", "principality", "archduchy", "landgraviate", "margraviate", "county", "bishopric", "electorate", "palatinate"]):
        return "REGIONAL_POLITY"
    
    return "SOVEREIGN_STATE"

def get_landmass_tag(lon: float, lat: float) -> str:
    if lon < -30.0:
        return "AMERICAS"
    if lat > 35.0 and lon < 15.0:
        return "EUROPE_WEST"
    if lat > 35.0 and 15.0 <= lon < 45.0:
        return "EUROPE_CENTRAL"
    if lat > 35.0 and lon >= 45.0:
        return "EURASIA_EAST"
    if lat <= 35.0 and lon < 40.0:
        return "AFRICA_MIDDLE_EAST"
    return "ASIA"

def clean_and_classify():
    print(f"[CLEAN] Loading {INPUT_FILE.name}...", flush=True)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_features = data.get("features", [])
    print(f"[CLEAN] Processing {len(raw_features)} raw features (Zero Data Loss)...", flush=True)

    cleaned_features = []

    for idx, feat in enumerate(raw_features):
        props = dict(feat.get("properties", {}))
        geom_dict = feat.get("geometry")

        raw_name = props.get("Name", "Unknown")
        clean_name = raw_name.replace("(", "").replace(")", "").strip()
        norm_name = normalize_name(raw_name)

        entity_type = classify_entity_type(clean_name, raw_name)

        props["raw_name"] = raw_name
        props["clean_name"] = clean_name
        props["norm_name"] = norm_name
        props["entity_type"] = entity_type
        props["feature_id"] = idx + 1

        # Check if MultiPolygon spans disjoint landmasses
        if geom_dict and entity_type in ["PERSONAL_UNION", "SUPRANATIONAL"]:
            try:
                s = shape(geom_dict)
                if isinstance(s, MultiPolygon) and len(s.geoms) > 1:
                    # Group sub-polygons by landmass tag
                    landmass_groups = {}
                    for poly in s.geoms:
                        if not poly.is_empty:
                            c = poly.centroid
                            tag = get_landmass_tag(c.x, c.y)
                            landmass_groups.setdefault(tag, []).append(poly)

                    if len(landmass_groups) > 1:
                        # Decompose into regional landmass component features
                        for tag, polys in landmass_groups.items():
                            sub_shape = polys[0] if len(polys) == 1 else MultiPolygon(polys)
                            sub_props = dict(props)
                            sub_props["Name"] = f"{clean_name} [{tag}]"
                            sub_props["clean_name"] = f"{clean_name} [{tag}]"
                            sub_props["entity_type"] = "REGIONAL_POLITY"
                            sub_props["parent_union_id"] = idx + 1
                            sub_props["landmass_tag"] = tag

                            cleaned_features.append({
                                "type": "Feature",
                                "properties": sub_props,
                                "geometry": mapping(sub_shape)
                            })
            except Exception as e:
                pass

        cleaned_features.append({
            "type": "Feature",
            "properties": props,
            "geometry": geom_dict
        })

    output_data = {
        "type": "FeatureCollection",
        "features": cleaned_features
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False)

    print(f"[CLEAN] Successfully generated {OUTPUT_FILE.name} with {len(cleaned_features)} organized features.", flush=True)

if __name__ == "__main__":
    clean_and_classify()
