import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from backend.tools.nominatim_tool import geocode_landmark_internal
from backend.config import DATA_DIR

GEOJSON_FILE = DATA_DIR / "ne_110m_admin_0_countries.geojson"
PROVINCES_FILE = DATA_DIR / "ne_10m_admin_1_provinces.geojson"

# Overseas departments/territories to exclude from continental polygon selection.
# These are politically part of a European country but located on other continents.
OVERSEAS_EXCLUSIONS = {
    "france": [
        "guyane francaise", "guyane", "french guiana",
        "guadeloupe", "martinique", "mayotte", "la reunion", "reunion",
        "saint pierre and miquelon", "saint barthelemy", "saint martin",
        "wallis and futuna", "new caledonia", "french polynesia",
    ],
    "spain": [
        "canarias", "islas canarias", "canary islands",
        "melilla", "ceuta",
    ],
    "portugal": [
        "azores", "acores", "madeira",
    ],
    "netherlands": [
        "aruba", "curacao", "bonaire", "sint maarten",
        "sint eustatius", "saba",
    ],
    "united kingdom": [
        "bermuda", "cayman islands", "british virgin islands",
        "turks and caicos islands", "montserrat", "anguilla",
        "falkland islands", "gibraltar", "pitcairn islands",
        "saint helena",
    ],
}


class CountryPolygonLoader:
    def __init__(self):
        self.countries_data: Dict[str, Any] = {}   # key -> country feature
        self.provinces_data: List[Dict[str, Any]] = []  # list of province features
        self._province_index: Dict[str, List[Dict[str, Any]]] = {}  # name.lower() -> [features]
        self._load_data()
        self._load_provinces()

    def _load_data(self):
        if not GEOJSON_FILE.exists():
            print(f"[WARN] GeoJSON file not found at {GEOJSON_FILE}. Run download_data.py first.")
            return
        try:
            with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
                geojson = json.load(f)
            for feature in geojson.get("features", []):
                properties = feature.get("properties", {})
                name = (properties.get("name") or "").lower()
                iso_a3 = (properties.get("iso_a3") or "").lower()
                if name:
                    self.countries_data[name] = feature
                if iso_a3:
                    self.countries_data[iso_a3] = feature
        except Exception as e:
            print(f"[ERR] Failed to load countries GeoJSON: {e}")

    def _load_provinces(self):
        if not PROVINCES_FILE.exists():
            print(f"[WARN] Provinces GeoJSON not found at {PROVINCES_FILE}. Run download_data.py first.")
            return
        try:
            with open(PROVINCES_FILE, "r", encoding="utf-8") as f:
                geojson = json.load(f)
            self.provinces_data = geojson.get("features", [])
            # Build index: province name (lower) -> list of features
            for feature in self.provinces_data:
                props = feature.get("properties", {})
                name = (props.get("name") or "").strip().lower()
                name_alt = (props.get("name_alt") or "").strip().lower()
                if name:
                    self._province_index.setdefault(name, []).append(feature)
                if name_alt and name_alt != name:
                    for alt in name_alt.split("|"):
                        alt = alt.strip()
                        if alt:
                            self._province_index.setdefault(alt, []).append(feature)
            print(f"[DATA] Loaded {len(self.provinces_data)} provinces into index.")
        except Exception as e:
            print(f"[ERR] Failed to load provinces GeoJSON: {e}")

    def get_country_feature(self, name_or_code: str) -> Optional[Dict[str, Any]]:
        return self.countries_data.get(name_or_code.strip().lower())

    def _is_overseas_feature(self, feature: Dict[str, Any], country_name: str) -> bool:
        """Check if a province feature is an overseas territory that should be excluded."""
        import unicodedata
        def _norm(s):
            if not s: return ""
            nfkd = unicodedata.normalize('NFKD', s)
            return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().replace("-", " ").replace("_", " ").strip()

        country_key = _norm(country_name)
        exclusions = OVERSEAS_EXCLUSIONS.get(country_key, [])
        if not exclusions:
            return False

        props = feature.get("properties", {})
        fname = _norm(props.get("name", ""))
        fname_alt = _norm(props.get("name_alt", ""))
        fregion = _norm(props.get("region", ""))

        for excl in exclusions:
            if excl in fname or excl in fname_alt or excl in fregion:
                return True
        return False

    def get_province_features(self, province_name: str, country_name: str = None) -> List[Dict[str, Any]]:
        """Look up all province/department features matching a name (direct name, alt name, or region name)."""
        import unicodedata
        
        if "(" in province_name:
            province_name = province_name.split("(")[0].strip()
            
        def normalize_str(s: str) -> str:
            if not s:
                return ""
            nfkd_form = unicodedata.normalize('NFKD', s)
            s_clean = "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()
            s_clean = s_clean.replace("-", " ").replace("_", " ")
            return " ".join(s_clean.split())

        pname_norm = normalize_str(province_name)
        country_norm = normalize_str(country_name) if country_name else None

        matched_features = []

        # 1. First check direct names & alt names in the index
        for name_key, features in self._province_index.items():
            if normalize_str(name_key) == pname_norm:
                matched_features.extend(features)

        # Filter by country if country is specified
        if country_norm:
            filtered = [f for f in matched_features
                                if normalize_str(f.get("properties", {}).get("admin", "")) == country_norm]
            if filtered:
                matched_features = filtered

        # Filter out overseas territories
        if country_name:
            matched_features = [f for f in matched_features if not self._is_overseas_feature(f, country_name)]

        if matched_features:
            return matched_features

        # 2. If no direct match in the department name/alt name, check region field
        region_features = []
        for feature in self.provinces_data:
            props = feature.get("properties", {})
            region = props.get("region") or ""

            if normalize_str(region) == pname_norm:
                region_features.append(feature)

        if country_norm:
            filtered_region = [f for f in region_features
                               if normalize_str(f.get("properties", {}).get("admin", "")) == country_norm]
            if filtered_region:
                region_features = filtered_region

        # Filter out overseas territories from region matches
        if country_name:
            region_features = [f for f in region_features if not self._is_overseas_feature(f, country_name)]

        return region_features

    def get_province_feature(self, province_name: str, country_name: str = None) -> Optional[Dict[str, Any]]:
        """Look up a province by name, optionally filtering by parent country."""
        features = self.get_province_features(province_name, country_name)
        return features[0] if features else None

    def select_provinces(self, country_name: str, province_names: List[str]) -> Optional[Dict[str, Any]]:
        """Select and merge specific provinces within a country into one polygon."""
        shapes = []
        for pname in province_names:
            features = self.get_province_features(pname, country_name)
            if features:
                for feature in features:
                    geom = feature.get("geometry")
                    if geom:
                        try:
                            shapes.append(shape(geom))
                        except Exception as e:
                            print(f"[WARN] Could not parse geometry for feature in '{pname}': {e}")
            else:
                print(f"[WARN] Province '{pname}' not found in '{country_name}' — skipping.")
        if not shapes:
            return None
        merged = unary_union(shapes)
        return {
            "type": "Feature",
            "properties": {"name": f"{country_name} ({', '.join(province_names[:3])}...)"},
            "geometry": mapping(merged)
        }

    def merge_features(self, features: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not features:
            return None
        shapes = []
        for f in features:
            geom = f.get("geometry")
            if geom:
                shapes.append(shape(geom))
        if not shapes:
            return None
        merged_shape = unary_union(shapes)
        return {
            "type": "Feature",
            "properties": {},
            "geometry": mapping(merged_shape)
        }

    def clip_feature_by_latitude(self, feature: Dict[str, Any], latitude: float, keep: str = "south") -> Optional[Dict[str, Any]]:
        """Clip a country/region polygon by a latitude line."""
        try:
            geom = shape(feature["geometry"])
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            if keep == "south":
                clip_box = box(bounds[0] - 1, bounds[1] - 1, bounds[2] + 1, latitude)
            else:  # north
                clip_box = box(bounds[0] - 1, latitude, bounds[2] + 1, bounds[3] + 1)
            clipped_geom = geom.intersection(clip_box)
            if clipped_geom.is_empty:
                return None
            return {
                "type": "Feature",
                "properties": feature.get("properties", {}),
                "geometry": mapping(clipped_geom)
            }
        except Exception as e:
            print(f"[ERR] Latitude clipping failed: {e}")
            return feature

    def clip_feature_by_longitude(self, feature: Dict[str, Any], longitude: float, keep: str = "west") -> Optional[Dict[str, Any]]:
        """Clip a country/region polygon by a longitude line."""
        try:
            geom = shape(feature["geometry"])
            bounds = geom.bounds
            if keep == "west":
                clip_box = box(bounds[0] - 1, bounds[1] - 1, longitude, bounds[3] + 1)
            else:  # east
                clip_box = box(longitude, bounds[1] - 1, bounds[2] + 1, bounds[3] + 1)
            clipped_geom = geom.intersection(clip_box)
            if clipped_geom.is_empty:
                return None
            return {
                "type": "Feature",
                "properties": feature.get("properties", {}),
                "geometry": mapping(clipped_geom)
            }
        except Exception as e:
            print(f"[ERR] Longitude clipping failed: {e}")
            return feature

    def process_territory(self, territory_def: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a territory definition, assembling full countries and partial regions."""
        shapes_to_combine = []

        # Load and add full countries
        for country_name in territory_def.get("countries_absorbed", []):
            feature = self.get_country_feature(country_name)
            if feature:
                try:
                    shapes_to_combine.append(shape(feature["geometry"]))
                except Exception as e:
                    print(f"[WARN] Could not parse geometry for country '{country_name}': {e}")
            else:
                print(f"[WARN] Country '{country_name}' not found in dataset — skipping.")

        # Load, clip, and add partial regions
        for partial in territory_def.get("partial_countries", []):
            country_name = partial.get("country")
            if not country_name:
                continue

            clip_method = partial.get("clip_method", "latitude")
            clip_value = partial.get("clip_value")
            portion = (partial.get("portion") or "").lower()
            landmark_city = partial.get("landmark_city")
            provinces = partial.get("provinces", [])

            # ── Province-based clipping (most precise) ──────────────────────────
            if clip_method == "provinces" and provinces:
                merged_prov = self.select_provinces(country_name, provinces)
                if merged_prov and merged_prov.get("geometry"):
                    try:
                        shapes_to_combine.append(shape(merged_prov["geometry"]))
                    except Exception as e:
                        print(f"[WARN] Province merge geometry error for '{country_name}': {e}")
                continue  # Done for this partial

            # ── Coordinate-based clipping (latitude / longitude) ────────────────
            feature = self.get_country_feature(country_name)
            if not feature:
                print(f"[WARN] Country '{country_name}' not found for partial clip — skipping.")
                continue

            # Resolve landmark to coordinate if needed
            if landmark_city and clip_value is None:
                coords = geocode_landmark_internal(landmark_city)
                if coords:
                    clip_value = coords[0] if clip_method == "latitude" else coords[1]

            # Fallback to midpoint if no coordinate available
            if clip_value is None:
                bounds = shape(feature["geometry"]).bounds
                if portion in ["southern", "south"]:
                    clip_method = "latitude"
                    clip_value = (bounds[1] + bounds[3]) / 2.0
                elif portion in ["northern", "north"]:
                    clip_method = "latitude"
                    clip_value = (bounds[1] + bounds[3]) / 2.0
                elif portion in ["western", "west"]:
                    clip_method = "longitude"
                    clip_value = (bounds[0] + bounds[2]) / 2.0
                elif portion in ["eastern", "east"]:
                    clip_method = "longitude"
                    clip_value = (bounds[0] + bounds[2]) / 2.0

            clipped_feature = feature
            if clip_method == "latitude" and clip_value is not None:
                keep_side = "south" if portion in ["southern", "south"] else "north"
                clipped_feature = self.clip_feature_by_latitude(feature, clip_value, keep_side)
            elif clip_method == "longitude" and clip_value is not None:
                keep_side = "west" if portion in ["western", "west"] else "east"
                clipped_feature = self.clip_feature_by_longitude(feature, clip_value, keep_side)

            if clipped_feature and clipped_feature.get("geometry"):
                try:
                    shapes_to_combine.append(shape(clipped_feature["geometry"]))
                except Exception as e:
                    print(f"[WARN] Clipped geometry error for '{country_name}': {e}")

        if not shapes_to_combine:
            return None

        merged_shape = unary_union(shapes_to_combine)

        return {
            "type": "Feature",
            "properties": {
                "name": territory_def.get("name"),
                "color": territory_def.get("color"),
                "status": territory_def.get("status", "direct_control"),
                "description": territory_def.get("description"),
                "capital": territory_def.get("capital"),
                "population": territory_def.get("population_estimate")
            },
            "geometry": mapping(merged_shape)
        }
