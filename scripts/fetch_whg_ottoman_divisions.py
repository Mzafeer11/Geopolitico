import json
import urllib.request
import urllib.parse
from pathlib import Path

DATA_DIR = Path("C:/Users/ADMIN/Desktop/Geopolitico/data")
WHG_CACHE_DIR = DATA_DIR / "whg_cache"
WHG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

OTTOMAN_DIVISIONS = [
    "Eyalet of Rumelia", "Eyalet of Anatolia", "Damascus Eyalet", "Aleppo Eyalet", 
    "Egypt Eyalet", "Eyalet of Buda", "Baghdad Eyalet", "Eyalet of Tripoli", 
    "Eyalet of Tunis", "Eyalet of Algiers", "Eyalet of Morea", "Trebizond Eyalet", 
    "Erzurum Eyalet", "Diyarbekir Eyalet", "Mosul Eyalet", "Sidon Eyalet",
    "Basra Eyalet", "Hejaz Eyalet", "Yemen Eyalet", "Archipelago Eyalet"
]

def query_whg_name(term):
    encoded = urllib.parse.quote(term)
    url = f"https://whgazetteer.org/api/index/?name={encoded}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityWHGFetcher/1.0',
        'Accept': 'application/json'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                raw = response.read().decode('utf-8')
                return json.loads(raw)
    except Exception as e:
        print(f"Error querying WHG for '{term}': {e}")
    return None

def fetch_all_ottoman_whg_divisions():
    print("==================================================")
    print("FETCHING OTTOMAN DIVISIONS VIA WHG API")
    print("==================================================\n")

    features = []

    for div in OTTOMAN_DIVISIONS:
        res = query_whg_name(div)
        if res and "features" in res and res["features"]:
            for f in res["features"]:
                props = f.get("properties", {})
                geom = f.get("geometry")
                title = props.get("title") or div
                features.append({
                    "type": "Feature",
                    "properties": {
                        "name": title,
                        "division_type": "Ottoman Eyalet / Province",
                        "place_id": props.get("place_id"),
                        "dataset": props.get("dataset"),
                        "links": props.get("links"),
                        "timespans": props.get("timespans"),
                        "source": "World Historical Gazetteer (WHG API)"
                    },
                    "geometry": geom
                })
            print(f"  [OK] {div}: Found {len(res['features'])} WHG place records")
        else:
            # Fallback search by key name
            short_name = div.replace("Eyalet of ", "").replace(" Eyalet", "")
            res_short = query_whg_name(short_name)
            if res_short and "features" in res_short and res_short["features"]:
                for f in res_short["features"][:2]:
                    props = f.get("properties", {})
                    geom = f.get("geometry")
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "name": f"{short_name} ({props.get('title', 'Ottoman Province')})",
                            "division_type": "Ottoman Eyalet / Regional Center",
                            "place_id": props.get("place_id"),
                            "dataset": props.get("dataset"),
                            "source": "World Historical Gazetteer (WHG API)"
                        },
                        "geometry": geom
                    })
                print(f"  [OK] {short_name} (fallback): Found {len(res_short['features'])} WHG place records")


    out_file = DATA_DIR / "whg_ottoman_admin_units.geojson"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": [f for f in features if f.get("geometry")]
        }, f, indent=2)

    print(f"\nSaved {len([f for f in features if f.get('geometry')])} valid WHG Ottoman administrative features to {out_file}")

if __name__ == "__main__":
    fetch_all_ottoman_whg_divisions()
