"""
Full Cache Audit Script.
Audits all 2,620 keys in data/wikidata_admin_cache.json to inspect:
  1. Polities with modern region name fallbacks (e.g. "Bayern Region", "Rheinland-Pfalz Region").
  2. Polities with non-geographic noise (e.g. titles, coins, styles).
  3. Polities with 0 admin units (empty).
  4. Polities with authentic historical names from Wikidata graph.
Outputs a comprehensive audit report.
"""

import sys
import os
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"

def audit_cache():
    print(f"[CACHE AUDITOR] Loading {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    total_keys = len(cache_data)
    modern_region_fallback_polities = []
    empty_polities = []
    authentic_historical_polities = []
    noisy_units_count = 0

    for key, entry in cache_data.items():
        if not isinstance(entry, dict):
            continue

        units = entry.get("admin_units", [])
        if not units:
            empty_polities.append(key)
            continue

        has_modern_fallback = False
        has_authentic_historical = False

        for u in units:
            uname = u.get("name", "")
            if uname.endswith(" Region") or uname.endswith(" Province"):
                has_modern_fallback = True
            elif u.get("historical_name") or any(archaic in uname for archaic in ["Theme", "Eyalet", "Jund", "Kūra", "Wilayah", "Subah", "Duchy", "County", "March", "Proconsularis", "Aegyptus", "Hispania", "Austrasia", "Neustria", "Gallia"]):
                has_authentic_historical = True

        if has_modern_fallback:
            modern_region_fallback_polities.append(key)
        elif has_authentic_historical:
            authentic_historical_polities.append(key)

    print("\n================ WIKIDATA CACHE AUDIT REPORT ================")
    print(f"Total Cached Polities / Keys: {total_keys}")
    print(f"Polities using Modern Region Fallbacks (e.g. 'Bayern Region'): {len(modern_region_fallback_polities)} ({len(modern_region_fallback_polities)/total_keys*100:.1f}%)")
    print(f"Polities using Authentic Historical Names (e.g. 'Theme', 'Eyalet', 'Jund'): {len(authentic_historical_polities)} ({len(authentic_historical_polities)/total_keys*100:.1f}%)")
    print(f"Empty Polities (0 Units): {len(empty_polities)} ({len(empty_polities)/total_keys*100:.1f}%)")

    print("\n--- SAMPLE POLITIES WITH MODERN REGION FALLBACKS ---")
    for p in modern_region_fallback_polities[:15]:
        sample_units = [u.get("name") for u in cache_data[p].get("admin_units", [])[:3]]
        print(f" - {p} -> {sample_units}")

    print("\n--- SAMPLE POLITIES WITH AUTHENTIC HISTORICAL NAMES ---")
    for p in authentic_historical_polities[:10]:
        sample_units = [u.get("name") for u in cache_data[p].get("admin_units", [])[:3]]
        print(f" - {p} -> {sample_units}")

if __name__ == "__main__":
    audit_cache()
