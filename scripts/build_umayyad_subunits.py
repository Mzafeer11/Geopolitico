import json
import os
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
ADMIN1_PATH = DATA_DIR / "ne_10m_admin_1_provinces.geojson"
ADMIN0_PATH = DATA_DIR / "ne_110m_admin_0_countries.geojson"

UMAYYAD_PROVINCES = [
    {
        "id": "jund_dimashq",
        "name": "Jund Dimashq (Damascus)",
        "capital": "Damascus",
        "type": "Metropolitan Military District (Ajnād)",
        "countries": ["SYR", "LBN"],
        "color": "#10b981",
        "desc": "The central imperial district of the Umayyad Caliphate and home to the Caliph's court at Damascus."
    },
    {
        "id": "jund_filastin",
        "name": "Jund Filastin (Palestine)",
        "capital": "Ludd / Al-Ramla",
        "type": "Military District (Ajnād)",
        "countries": ["ISR", "PSE"],
        "color": "#34d399",
        "desc": "Southern Syrian military district encompassing Jerusalem, Gaza, and the naval port of Acre."
    },
    {
        "id": "jund_urdunn",
        "name": "Jund al-Urdunn (Jordan)",
        "capital": "Tabariyya (Tiberias)",
        "type": "Military District (Ajnād)",
        "countries": ["JOR"],
        "color": "#059669",
        "desc": "District around the Sea of Galilee and the Jordan River Valley."
    },
    {
        "id": "jund_hims",
        "name": "Jund Hims (Homs)",
        "capital": "Hims (Emesa)",
        "type": "Military District (Ajnād)",
        "countries": ["SYR"],
        "color": "#047857",
        "desc": "Central Syrian district extending towards Palmyra and the Desert Palaces."
    },
    {
        "id": "jund_qinnasrin",
        "name": "Jund Qinnasrin (Northern Syria)",
        "capital": "Qinnasrin / Halab (Aleppo)",
        "type": "Frontier Military District (Ajnād)",
        "countries": ["SYR", "TUR"],
        "color": "#065f46",
        "desc": "Northern frontier province guarding against Byzantine border raids (Al-'Awasim)."
    },
    {
        "id": "wilayat_iraq",
        "name": "Wilayat Iraq (Lower Mesopotamia)",
        "capital": "Al-Kufa & Al-Basra",
        "type": "Viceroyalty (Wilāyah)",
        "countries": ["IRQ", "KWT"],
        "color": "#f59e0b",
        "desc": "The wealthy agricultural and garrison center of Kufa and Basra."
    },
    {
        "id": "wilayat_khurasan",
        "name": "Wilayat Khurasan & Transoxiana",
        "capital": "Merv & Samarqand",
        "type": "Eastern Frontier Province",
        "countries": ["IRN", "TKM", "UZB", "AFG", "TJK"],
        "color": "#d97706",
        "desc": "Vast eastern province managing Silk Road trade and expansion into Central Asia."
    },
    {
        "id": "wilayat_egypt",
        "name": "Wilayat Misr (Egypt)",
        "capital": "Al-Fustat (Old Cairo)",
        "type": "Viceroyalty (Wilāyah)",
        "countries": ["EGY"],
        "color": "#ec4899",
        "desc": "The grain basket of the Mediterranean, governed from Al-Fustat."
    },
    {
        "id": "wilayat_ifriqiya",
        "name": "Wilayat Ifriqiya & Maghreb",
        "capital": "Al-Qayrawan (Kairouan)",
        "type": "Western Province (Wilāyah)",
        "countries": ["TUN", "LBY", "DZA", "MAR"],
        "color": "#8b5cf6",
        "desc": "North African administrative division extending from Tripolitania to Tangier."
    },
    {
        "id": "wilayat_andalus",
        "name": "Wilayat Al-Andalus (Iberia)",
        "capital": "Qurtuba (Cordoba)",
        "type": "Dependent Emirate / Province",
        "countries": ["ESP", "PRT"],
        "color": "#6366f1",
        "desc": "Iberian province conquered under Tariq ibn Ziyad and Musa ibn Nusayr (711 CE)."
    },
    {
        "id": "wilayat_jazira",
        "name": "Wilayat Al-Jazira & Arminiya",
        "capital": "Al-Mawsil (Mosul) & Dvin",
        "type": "Northern Mountain Province",
        "countries": ["ARM", "GEO", "AZE"],
        "color": "#14b8a6",
        "desc": "Upper Mesopotamian and Caucasian frontier buffer zone."
    },
    {
        "id": "wilayat_hijaz",
        "name": "Wilayat Al-Hijaz & Al-Yaman",
        "capital": "Makkah & Al-Madinah",
        "type": "Holy Lands Province",
        "countries": ["SAU", "YEM", "OMN"],
        "color": "#84cc16",
        "desc": "The Islamic holy cities of Mecca and Medina and Southern Arabia."
    }
]

def build_umayyad_detailed_geojson():
    print("Building Umayyad Administrative Units GeoJSON...")
    with open(ADMIN0_PATH, "r", encoding="utf-8") as f:
        admin0 = json.load(f)

    # Map features by country ISO_A3
    country_geoms = {}
    for feat in admin0.get("features", []):
        iso = feat.get("properties", {}).get("ADM0_A3") or feat.get("properties", {}).get("ISO_A3")
        if iso:
            country_geoms[iso] = feat.get("geometry")

    out_features = []
    for prov in UMAYYAD_PROVINCES:
        # Combine geometries of matching countries
        geoms = [country_geoms[code] for code in prov["countries"] if code in country_geoms]
        if geoms:
            out_features.append({
                "type": "Feature",
                "properties": {
                    "id": prov["id"],
                    "name": prov["name"],
                    "capital": prov["capital"],
                    "type": prov["type"],
                    "color": prov["color"],
                    "description": prov["desc"],
                    "group": "Umayyad Admin Units"
                },
                "geometry": geoms[0]  # Representative spatial geometry
            })

    output_path = DATA_DIR / "umayyad_detailed_admin_units.geojson"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": out_features
        }, f, indent=2)

    print(f"Saved {len(out_features)} Umayyad administrative unit polygons to {output_path}")

if __name__ == "__main__":
    build_umayyad_detailed_geojson()
