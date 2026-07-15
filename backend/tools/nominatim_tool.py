import httpx
import time
from typing import Tuple, Optional, Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Simple rate limiter state
_LAST_REQUEST_TIME = 0.0

def _rate_limit():
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < 5.0:
        time.sleep(5.0 - elapsed)
    _LAST_REQUEST_TIME = time.time()

class GeocodeLandmarkInput(BaseModel):
    query: str = Field(..., description="The name of the city, river, or landmark to geocode.")

class GeocodeLandmarkTool(BaseTool):
    name: str = "Geocode Landmark"
    description: str = "Geocode a city, river, or landmark to get its latitude and longitude coordinate."
    args_schema: Type[BaseModel] = GeocodeLandmarkInput

    def _run(self, query: str) -> str:
        global _LAST_REQUEST_TIME
        try:
            _rate_limit()
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": query,
                "format": "json",
                "limit": 1
            }
            headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
            
            response = httpx.get(url, params=params, headers=headers, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                if not data:
                    return f"Could not find coordinates for landmark '{query}'."
                place = data[0]
                lat = place.get("lat")
                lon = place.get("lon")
                display_name = place.get("display_name")
                return f"Landmark: {display_name}\nLatitude: {lat}\nLongitude: {lon}"
            return f"Error geocoding landmark: HTTP {response.status_code}"
        except Exception as e:
            return f"Error querying Nominatim API: {e}"

def geocode_landmark_internal(query: str) -> Optional[Tuple[float, float]]:
    """Internal helper to get coordinates for clipping calculations."""
    global _LAST_REQUEST_TIME
    try:
        _rate_limit()
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
        
        response = httpx.get(url, params=params, headers=headers, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        return None
    except Exception:
        return None

geocode_landmark = GeocodeLandmarkTool()


