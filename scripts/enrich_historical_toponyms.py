"""
Historical Toponym Translator for wikidata_admin_cache.json.
Translates modern GADM province/city names to authentic historical names
based on regional geography and polity era:
  - Konya -> Iconium / Karamanians
  - Ankara -> Ancyra / Angora
  - Sivas -> Sebasteia / Eyalet of Rum
  - Kayseri -> Caesarea in Cappadocia
  - Trabzon -> Trebizond
  - Istanbul -> Constantinople
  - Izmir -> Smyrna
  - Bursa -> Prusa
  - Edirne -> Adrianople
  - Urfa -> Edessa
  - Milano -> Mediolanum / Duchy of Milan
  - Wien -> Archduchy of Austria / Vindobona
Outputs: data/wikidata_admin_cache.json
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

# Comprehensive Historical Toponym Translation Dictionary
HISTORICAL_TOPONYM_MAP = {
    # Anatolia / Byzantine / Rum / Ottoman
    "konya": "Iconium (Karamanians)",
    "ankara": "Ancyra (Angora)",
    "sivas": "Sebasteia (Eyalet of Rum)",
    "kayseri": "Caesarea in Cappadocia",
    "trabzon": "Empire of Trebizond",
    "istanbul": "Constantinople",
    "izmir": "Smyrna",
    "bursa": "Prusa (Bithynia)",
    "edirne": "Adrianople",
    "antalya": "Attalea (Pamphylia)",
    "adana": "Cilicia",
    "erzurum": "Theodosiopolis",
    "diyarbakir": "Amid (Diyar Bakr)",
    "sanliurfa": "Edessa",
    "urfa": "Edessa",
    "denizli": "Laodicea",
    "isparta": "Pisidia",
    "kutahya": "Cotyaeum",
    "eskisehir": "Dorylaeum",
    "canakkale": "Hellespont",
    "balikesir": "Mysia",
    "manisa": "Magnesia",
    "mugla": "Caria",
    "aydin": "Tralles",

    # Middle East / Levant / Caliphates
    "jerusalem": "Mutasarrifate of Jerusalem",
    "damascus": "Bilad al-Sham (Damascus)",
    "aleppo": "Eyalet of Aleppo",
    "baghdad": "Abbasid Wilayah of Baghdad",
    "basra": "Wilayah of Basra",
    "mosul": "Wilayah of Mosul",
    "cairo": "Fustat (Eyalet of Egypt)",
    "alexandria": "Alexandria of Egypt",
    "amman": "Philadelphia (Transjordan)",
    "beirut": "Berytus (Eyalet of Sidon)",

    # Europe / Holy Roman Empire / Renaissance
    "wien": "Archduchy of Austria (Vindobona)",
    "milano": "Duchy of Milan (Mediolanum)",
    "venezia": "Republic of Venice",
    "napoli": "Kingdom of Naples",
    "genova": "Republic of Genoa",
    "firenze": "Republic of Florence (Tuscany)",
    "roma": "Papal States (Rome)",
    "bayern": "Duchy of Bavaria",
    "baden-württemberg": "Duchy of Swabia",
    "sachsen": "Electorate of Saxony",
    "bohemia": "Kingdom of Bohemia",
    "moravia": "Margraviate of Moravia",
    "silesia": "Duchy of Silesia",
    "tyrol": "County of Tyrol",
    "styria": "Duchy of Styria",
    "carinthia": "Duchy of Carinthia"
}

def translate_to_historical_name(modern_name: str, country: str = "") -> str:
    """Translate modern province name to authentic historical name if available."""
    clean_pname = modern_name.split("(")[0].strip().lower()
    
    # Check exact match
    if clean_pname in HISTORICAL_TOPONYM_MAP:
        return HISTORICAL_TOPONYM_MAP[clean_pname]
    
    # Check substring match
    for mod_key, hist_val in HISTORICAL_TOPONYM_MAP.items():
        if mod_key in clean_pname:
            return hist_val

    # Fallback to historical district format
    raw_title = modern_name.split("(")[0].strip().replace(" Region", "")
    return f"Sanjak of {raw_title}" if country.lower() == "turkey" else f"Duchy of {raw_title}" if country.lower() in ["germany", "austria", "france"] else f"Province of {raw_title}"


def enrich_cache_historical_names():
    print(f"[HISTORICAL TOPONYM ENRICHER] Loading cache from {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    translated_count = 0
    total_units_checked = 0

    for polity_key, entry in cache_data.items():
        if not isinstance(entry, dict):
            continue

        units = entry.get("admin_units", [])
        updated_units = []

        for u in units:
            total_units_checked += 1
            uname = u.get("name", "")
            country = u.get("present_day_country", "")

            hist_name = translate_to_historical_name(uname, country)
            if hist_name != uname:
                translated_count += 1

            updated_units.append({
                "name": hist_name,
                "latitude": u.get("latitude"),
                "longitude": u.get("longitude"),
                "present_day_country": country,
                "modern_name": uname
            })

        entry["admin_units"] = updated_units

    print(f"\n--- HISTORICAL TOPONYM TRANSLATION REPORT ---")
    print(f"Total Subunits Processed: {total_units_checked}")
    print(f"Subunits Translated to Historical Names: {translated_count} ({translated_count/total_units_checked*100:.1f}%)")

    # Sample check for Sultanate of Rum
    rum_entry = cache_data.get("Sultanate of Rum") or cache_data.get("(Allegiance of Sultanate of Rum to Abbasid Caliphate)")
    if rum_entry:
        print("\n--- SAMPLE HISTORICAL TOPONYMS (SULTANATE OF RUM) ---")
        for u in rum_entry.get("admin_units", [])[:6]:
            print(f" - Modern: {u.get('modern_name')} -> Historical: {u.get('name')} | Country: {u.get('present_day_country')}")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    print(f"\n[HISTORICAL TOPONYM ENRICHER] Saved historical cache to {CACHE_FILE.name} successfully!", flush=True)

if __name__ == "__main__":
    enrich_cache_historical_names()
