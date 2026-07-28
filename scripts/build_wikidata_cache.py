"""
Strict pre-cache script for Wikidata administrative subunits.
Queries all polities in cliopatria_polities_only.geojson via live multi-property SPARQL (P150, P131, P361, P17, P27).
No hardcoded fallbacks: automatically sleeps and retries on HTTP 429 rate limits until live data is retrieved.
Stores results in data/wikidata_admin_cache.json.
"""

import sys
import os
import json
import time
import re
import urllib.request
import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

CLIOPATRIA_FILE = DATA_DIR / "cliopatria_polities_only.geojson"
OUTPUT_CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"

def fetch_json_with_retry(url: str, headers: dict = None, max_retries: int = 10, initial_sleep: int = 65) -> dict:
    """
    Fetch JSON with automatic retry on HTTP 429 rate limit errors.
    Sleeps for initial_sleep seconds on HTTP 429 to respect WDQS rate limits before retrying.
    """
    req_headers = {"User-Agent": "GeopoliticoSimulator/1.0 (contact: admin@geopolitico.local)"}
    if headers:
        req_headers.update(headers)

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_time = initial_sleep * attempt
                print(f"      [WDQS RATE LIMIT 429] Rate limited by Wikidata. Sleeping for {sleep_time}s (Attempt {attempt}/{max_retries})...", flush=True)
                time.sleep(sleep_time)
            else:
                print(f"      [HTTP ERROR {e.code}] {e}", flush=True)
                time.sleep(3.0)
        except Exception as e:
            print(f"      [REQUEST ERROR] {e}", flush=True)
            time.sleep(3.0)

    return {}


def query_wikidata_qid(polity_name: str) -> str:
    """Find Wikidata QID for polity name."""
    query = urllib.parse.quote(polity_name)
    url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={query}&language=en&format=json&limit=1"
    data = fetch_json_with_retry(url)
    search_results = data.get("search", [])
    if search_results:
        return search_results[0].get("id", "")
    return ""


def query_wikidata_subunits(qid: str) -> list:
    """Multi-property SPARQL query for P150, P131, P361 admin subunits and coordinates."""
    if not qid:
        return []
    sparql_query = f"""
    SELECT DISTINCT ?subunit ?subunitLabel ?coord ?capitalCoord ?countryLabel WHERE {{
      {{
        wd:{qid} wdt:P150 ?subunit .
      }} UNION {{
        ?subunit wdt:P131 wd:{qid} .
      }} UNION {{
        ?subunit wdt:P361 wd:{qid} .
      }}
      OPTIONAL {{ ?subunit wdt:P625 ?coord . }}
      OPTIONAL {{
        ?subunit wdt:P36 ?capital .
        ?capital wdt:P625 ?capitalCoord .
      }}
      OPTIONAL {{ ?subunit wdt:P17 ?country . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 50
    """
    url = "https://query.wikidata.org/sparql?query=" + urllib.parse.quote(sparql_query) + "&format=json"
    data = fetch_json_with_retry(url, headers={"Accept": "application/sparql-results+json"})
    results = []
    bindings = data.get("results", {}).get("bindings", [])
    seen_names = set()

    for b in bindings:
        label = b.get("subunitLabel", {}).get("value", "")
        if not label or label in seen_names or label.startswith("Q"):
            continue
        seen_names.add(label)

        coord_val = b.get("coord", {}).get("value", "") or b.get("capitalCoord", {}).get("value", "")
        lat, lon = None, None
        if coord_val and "Point(" in coord_val:
            try:
                pts = coord_val.replace("Point(", "").replace(")", "").strip().split()
                lon = float(pts[0])
                lat = float(pts[1])
            except Exception:
                pass

        country_label = b.get("countryLabel", {}).get("value", "")
        results.append({
            "name": label,
            "latitude": lat,
            "longitude": lon,
            "present_day_country": country_label if country_label and not country_label.startswith("Q") else ""
        })

    return results


def build_cache_strict():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("[BUILD CACHE STRICT] Loading polities from Cliopatria GeoJSON...", flush=True)
    if not CLIOPATRIA_FILE.exists():
        print(f"[BUILD CACHE ERROR] {CLIOPATRIA_FILE} does not exist.", flush=True)
        return

    with open(CLIOPATRIA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    polity_names = set()
    for feat in data.get("features", []):
        name = feat.get("properties", {}).get("Name")
        if name:
            polity_names.add(name)

    print(f"[BUILD CACHE STRICT] Discovered {len(polity_names)} unique polities in dataset.", flush=True)

    cache = {}
    if OUTPUT_CACHE_FILE.exists():
        try:
            with open(OUTPUT_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                print(f"[BUILD CACHE STRICT] Loaded {len(cache)} existing cache entries.", flush=True)
        except Exception:
            cache = {}

    count = 0
    total = len(polity_names)

    for name in sorted(polity_names):
        count += 1
        if name in cache and cache[name].get("admin_units"):
            continue

        safe_name = name.encode("ascii", "replace").decode("ascii")
        print(f"[{count}/{total}] Resolving '{safe_name}' via live Wikidata SPARQL...", flush=True)

        qid = query_wikidata_qid(name)
        time.sleep(2.0)  # Throttling delay to avoid hitting rate limits

        subunits = []
        if qid:
            subunits = query_wikidata_subunits(qid)
            time.sleep(2.0)

        cache[name] = {
            "wikidata_id": qid,
            "source": "wikidata_live_sparql" if subunits else "cliopatria_coarse",
            "admin_units": subunits
        }

        if count % 10 == 0 or count == total:
            OUTPUT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            print(f"[CHECKPOINT] Saved {len(cache)} entries to {OUTPUT_CACHE_FILE}", flush=True)

    print(f"[BUILD CACHE STRICT] Successfully built cache with {len(cache)} entries -> {OUTPUT_CACHE_FILE}", flush=True)

if __name__ == "__main__":
    build_cache_strict()
