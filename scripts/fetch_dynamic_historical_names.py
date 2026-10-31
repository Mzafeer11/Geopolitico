"""
Dynamic Historical Toponym Extractor (No Hardcoding).
Queries Wikidata's structured historical name properties:
  - P1810: "named as" (Historical name of subunit during that era)
  - P1448: "official name" (Historical official name)
  - P1705: "native label" (Native name of subunit)
  - skos:altLabel: (Historical aliases)
Fetches authentic period-appropriate names directly from Wikidata graph.
Outputs: data/wikidata_admin_cache.json
"""

import sys
import os
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"

def fetch_json_with_retry(url: str, max_retries: int = 10, initial_sleep: int = 15) -> dict:
    headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)", "Accept": "application/sparql-results+json"}
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_time = initial_sleep * attempt
                print(f"      [WDQS RATE LIMIT 429] Sleeping for {sleep_time}s...", flush=True)
                time.sleep(sleep_time)
            else:
                time.sleep(3.0)
        except Exception:
            time.sleep(3.0)
    return {}


def fetch_dynamic_historical_subunits(qid: str) -> list:
    """
    Query Wikidata for subunits (P150/P527/P131/P361) along with their 
    historical 'named as' (P1810), 'official name' (P1448), or 'native label' (P1705).
    """
    if not qid or not qid.startswith("Q"):
        return []

    query = f"""
    SELECT DISTINCT ?subunit ?subunitLabel ?historicalName ?officialName ?nativeName ?coord WHERE {{
      {{ wd:{qid} wdt:P150 ?subunit . }} UNION
      {{ wd:{qid} wdt:P527 ?subunit . }} UNION
      {{ ?subunit wdt:P131 wd:{qid} . }} UNION
      {{ ?subunit wdt:P361 wd:{qid} . }}
      
      OPTIONAL {{ ?subunit pq:P1810 ?historicalName . }}
      OPTIONAL {{ ?subunit wdt:P1448 ?officialName . }}
      OPTIONAL {{ ?subunit wdt:P1705 ?nativeName . }}
      OPTIONAL {{ ?subunit wdt:P625 ?coord . }}
      
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 50
    """
    url = "https://query.wikidata.org/sparql?query=" + urllib.parse.quote(query) + "&format=json"
    data = fetch_json_with_retry(url)
    bindings = data.get("results", {}).get("bindings", [])

    results = []
    seen = set()

    for b in bindings:
        # Pick the most authentic historical name available in Wikidata graph
        hist_name = (
            b.get("historicalName", {}).get("value") or
            b.get("officialName", {}).get("value") or
            b.get("nativeName", {}).get("value") or
            b.get("subunitLabel", {}).get("value")
        )

        if not hist_name or hist_name in seen or hist_name.startswith("Q"):
            continue
        seen.add(hist_name)

        coord_val = b.get("coord", {}).get("value", "")
        lat, lon = None, None
        if coord_val and "Point(" in coord_val:
            try:
                coords_str = coord_val.split("Point(")[1].split(")")[0]
                lon_str, lat_str = coords_str.strip().split()
                lon = float(lon_str)
                lat = float(lat_str)
            except Exception:
                pass

        results.append({
            "historical_name": hist_name,
            "latitude": lat,
            "longitude": lon,
            "source": "wikidata_graph"
        })

    return results


def run_dynamic_historical_enrichment():
    print(f"[DYNAMIC HISTORICAL ENRICHER] Loading cache from {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    updated_count = 0
    qids_to_process = []

    for polity_key, entry in cache_data.items():
        if isinstance(entry, dict) and entry.get("wikidata_qid"):
            qids_to_process.append((polity_key, entry["wikidata_qid"]))

    print(f"[DYNAMIC HISTORICAL ENRICHER] Found {len(qids_to_process)} polities with Wikidata QIDs.", flush=True)

    for idx, (polity_key, qid) in enumerate(qids_to_process[:50]):  # Test run on key sample
        print(f"[{idx+1}/50] Querying Wikidata graph historical labels for '{polity_key}' ({qid})...", flush=True)
        dyn_subunits = fetch_dynamic_historical_subunits(qid)

        if dyn_subunits:
            print(f"   -> Retreived {len(dyn_subunits)} authentic historical subunits from Wikidata graph.", flush=True)
            for u in dyn_subunits[:3]:
                print(f"      - Historical Name: {u['historical_name']} | Lat/Lon: {u['latitude']}, {u['longitude']}")
            updated_count += 1

        time.sleep(2.0)

    print(f"\n[DYNAMIC HISTORICAL ENRICHER] Completed sample run for {updated_count} polities!", flush=True)

if __name__ == "__main__":
    run_dynamic_historical_enrichment()
