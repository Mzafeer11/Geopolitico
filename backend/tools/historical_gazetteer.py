"""
Offline Historical Gazetteer Loader for Geopolitico.
Combines Al-Thurayya (master/places.geojson) and Pleiades Ancient World Gazetteer (pleiades_gis_data/data/gis/).
Provides 100% offline resolution of historical administrative sub-units, cities, and regional centers.
"""

import os
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = ROOT_DIR / "master"
PLEIADES_DIR = ROOT_DIR / "pleiades_gis_data" / "data" / "gis"

# Region code mapping from Al-Thurayya (master/regions.json) to polity names
REGION_POLITY_MAP = {
    "Andalus": ["Umayyad Caliphate", "Al-Andalus", "Caliphate of Córdoba", "Emirate of Córdoba", "Taifa Kingdoms"],
    "Sham": ["Umayyad Caliphate", "Abbasid Caliphate", "Rashidun Caliphate", "Fatimid Caliphate", "Ayyubid Sultanate", "Mamluk Sultanate"],
    "Aqur": ["Umayyad Caliphate", "Abbasid Caliphate", "Zengid Dynasty", "Ayyubid Sultanate", "Ottoman Empire"],
    "Iraq": ["Umayyad Caliphate", "Abbasid Caliphate", "Buyid Dynasty", "Seljuk Empire", "Ilkhanate", "Jalayirid Sultanate"],
    "Khurasan": ["Umayyad Caliphate", "Abbasid Caliphate", "Samanid Empire", "Ghaznavid Empire", "Seljuk Empire", "Timurid Empire"],
    "Misr": ["Umayyad Caliphate", "Abbasid Caliphate", "Fatimid Caliphate", "Ayyubid Sultanate", "Mamluk Sultanate", "Ottoman Empire"],
    "Barqa": ["Umayyad Caliphate", "Abbasid Caliphate", "Fatimid Caliphate", "Ottoman Empire"],
    "Ifriqiya": ["Umayyad Caliphate", "Abbasid Caliphate", "Aghlabid Dynasty", "Fatimid Caliphate", "Hafsid Dynasty"],
    "Daylam": ["Umayyad Caliphate", "Abbasid Caliphate", "Buyid Dynasty", "Ziyarid Dynasty"],
    "Fars": ["Umayyad Caliphate", "Abbasid Caliphate", "Buyid Dynasty", "Seljuk Empire", "Muzaffarids"],
    "Rum": ["Byzantine Empire", "Sultanate of Rum", "Ottoman Empire"],
    "Yaman": ["Umayyad Caliphate", "Abbasid Caliphate", "Rassid Imamate", "Rasulid Dynasty"]
}

class HistoricalGazetteer:
    _instance = None

    def __init__(self):
        self.thurayya_places = []
        self.regions_meta = {}
        self.pleiades_places = []
        self._is_loaded = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load_data()
        return cls._instance

    def load_data(self):
        if self._is_loaded:
            return

        print("[GAZETTEER] Loading Al-Thurayya master dataset...", flush=True)

        # 1. Load regions.json
        regions_file = MASTER_DIR / "regions.json"
        if regions_file.exists():
            try:
                with open(regions_file, "r", encoding="utf-8") as f:
                    self.regions_meta = json.load(f)
            except Exception as e:
                print(f"[GAZETTEER WARN] Could not load regions.json: {e}", flush=True)

        # 2. Load places.geojson / places_new_structure.geojson
        places_file = MASTER_DIR / "places_new_structure.geojson"
        if not places_file.exists():
            places_file = MASTER_DIR / "places.geojson"

        if places_file.exists():
            try:
                with open(places_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        cornu = props.get("cornuData", {})
                        geom = feat.get("geometry", {})
                        coords = geom.get("coordinates", [])

                        if coords and len(coords) >= 2:
                            lon, lat = coords[0], coords[1]
                            region_code = cornu.get("region_code", "")
                            toponym = cornu.get("toponym_search") or cornu.get("toponym_translit") or cornu.get("toponym_arabic")
                            top_type = cornu.get("top_type_orig") or cornu.get("top_type_hom")

                            if toponym:
                                self.thurayya_places.append({
                                    "name": toponym,
                                    "latitude": lat,
                                    "longitude": lon,
                                    "region_code": region_code,
                                    "region_spelled": cornu.get("region_spelled", ""),
                                    "top_type": top_type,
                                    "source": "Al-Thurayya"
                                })
                print(f"[GAZETTEER] Indexed {len(self.thurayya_places)} historical places from Al-Thurayya.", flush=True)
            except Exception as e:
                print(f"[GAZETTEER ERROR] Error loading Al-Thurayya places: {e}", flush=True)

        # 3. Load Pleiades places.csv
        pleiades_places_file = PLEIADES_DIR / "places.csv"
        if pleiades_places_file.exists():
            try:
                print("[GAZETTEER] Loading Pleiades Ancient World dataset...", flush=True)
                with open(pleiades_places_file, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        lat_str = row.get("representative_latitude")
                        lon_str = row.get("representative_longitude")
                        title = row.get("title")
                        if title and lat_str and lon_str:
                            try:
                                lat = float(lat_str)
                                lon = float(lon_str)
                                self.pleiades_places.append({
                                    "name": title,
                                    "latitude": lat,
                                    "longitude": lon,
                                    "description": row.get("description", ""),
                                    "source": "Pleiades"
                                })
                            except ValueError:
                                pass
                print(f"[GAZETTEER] Indexed {len(self.pleiades_places)} ancient places from Pleiades.", flush=True)
            except Exception as e:
                print(f"[GAZETTEER ERROR] Error loading Pleiades places: {e}", flush=True)

        self._is_loaded = True

    def get_historical_units(self, polity_name: str, year: Optional[int] = None, region: str = "") -> List[Dict[str, Any]]:
        """
        Query historical places for a given polity and optional year/region 100% offline.
        """
        self.load_data()
        results = []
        seen = set()

        polity_lower = polity_name.lower()

        # 1. Match Al-Thurayya places by region code mapping
        matched_region_codes = set()
        for r_code, polities in REGION_POLITY_MAP.items():
            if any(p.lower() in polity_lower or polity_lower in p.lower() for p in polities):
                matched_region_codes.add(r_code)

        for p in self.thurayya_places:
            if p["region_code"] in matched_region_codes:
                pname = p["name"]
                if pname not in seen:
                    seen.add(pname)
                    results.append({
                        "name": f"{pname} ({p['region_spelled'] or p['region_code']})",
                        "latitude": p["latitude"],
                        "longitude": p["longitude"],
                        "top_type": p["top_type"],
                        "source": "Al-Thurayya"
                    })

        # 2. Match Pleiades places by keyword if results are sparse
        if len(results) < 5:
            for p in self.pleiades_places:
                title_lower = p["name"].lower()
                desc_lower = p.get("description", "").lower()
                if polity_lower in title_lower or polity_lower in desc_lower:
                    if p["name"] not in seen:
                        seen.add(p["name"])
                        results.append({
                            "name": p["name"],
                            "latitude": p["latitude"],
                            "longitude": p["longitude"],
                            "source": "Pleiades"
                        })
                        if len(results) >= 30:
                            break

        return results


gazetteer = HistoricalGazetteer()
