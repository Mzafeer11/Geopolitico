"""
SimulationCache — Centralized spatial caching singleton for Geopolitico backend.

Caches high-cost GeoJSON assets (CountryPolygonLoader), resolved baseline geometries,
contested province spatial analysis results, and historical sub-province maps
across pipeline calls within a simulation run.
"""

from typing import Dict, Any, Optional, List, Tuple
from shapely.geometry import shape

class SimulationCache:
    _instance: Optional["SimulationCache"] = None

    def __new__(cls) -> "SimulationCache":
        if cls._instance is None:
            cls._instance = super(SimulationCache, cls).__new__(cls)
            cls._instance._loader = None
            cls._instance._baseline_geoms = {}      # (polity_name, year, target_region) -> (shape, geojson, tier)
            cls._instance._historical_units = {}     # (polity_name, year, target_region) -> result_dict
            cls._instance._contested_provinces = {}  # (polities_tuple, year, target_countries_tuple, is_partition) -> List[str]
            cls._instance._polity_shapes = {}        # (polity_name, year) -> Shapely shape
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SimulationCache":
        return cls()

    def get_country_polygon_loader(self):
        """Get or initialize the singleton CountryPolygonLoader."""
        if self._loader is None:
            from backend.tools.country_polygons import CountryPolygonLoader
            self._loader = CountryPolygonLoader()
        return self._loader

    def get_baseline_geometry(self, polity: str, year: int, target_region: str = "") -> Optional[Tuple[Any, Any, str]]:
        key = (polity.lower(), year, target_region.lower())
        return self._baseline_geoms.get(key)

    def set_baseline_geometry(self, polity: str, year: int, target_region: str, value: Tuple[Any, Any, str]):
        key = (polity.lower(), year, target_region.lower())
        self._baseline_geoms[key] = value

    def get_historical_units(self, polity: str, year: int, target_region: str = "") -> Optional[Dict[str, Any]]:
        key = (polity.lower(), year, target_region.lower())
        return self._historical_units.get(key)

    def set_historical_units(self, polity: str, year: int, target_region: str, value: Dict[str, Any]):
        key = (polity.lower(), year, target_region.lower())
        self._historical_units[key] = value

    def get_contested_provinces(self, polities: List[str], year: int, target_countries: List[str], is_partition: bool) -> Optional[List[str]]:
        key = (tuple(sorted([p.lower() for p in polities])), year, tuple(sorted([c.lower() for c in target_countries])), is_partition)
        return self._contested_provinces.get(key)

    def set_contested_provinces(self, polities: List[str], year: int, target_countries: List[str], is_partition: bool, value: List[str]):
        key = (tuple(sorted([p.lower() for p in polities])), year, tuple(sorted([c.lower() for c in target_countries])), is_partition)
        self._contested_provinces[key] = value

    def clear(self):
        """Reset cache between runs if necessary."""
        self._baseline_geoms.clear()
        self._historical_units.clear()
        self._contested_provinces.clear()
        self._polity_shapes.clear()
