"""
Exact Historical Administrative Units Fixer for Byzantine Empire, Kingdom of the Franks, and Major Empires.
Replaces empty entries and false stem duchy noise in data/wikidata_admin_cache.json with
authentic, period-accurate historical Themes, Stem Duchies, Eyalets, Junds, and Subahs.
Outputs: data/wikidata_admin_cache.json
"""

import sys
import os
import json
from pathlib import Path

# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

CACHE_FILE = DATA_DIR / "wikidata_admin_cache.json"

AUTHENTIC_EMPIRE_DIVISIONS = {
    # 1. Byzantine Empire (7th-15th Century Themes & Catepanates)
    "Byzantine Empire": [
        {"name": "Theme of Opsikion (Bithynia)", "latitude": 40.4000, "longitude": 29.8000, "present_day_country": "Turkey"},
        {"name": "Theme of Anatolikon (Amorium / Iconium)", "latitude": 38.3000, "longitude": 32.2000, "present_day_country": "Turkey"},
        {"name": "Theme of Armeniakon (Pontus)", "latitude": 40.6000, "longitude": 35.8000, "present_day_country": "Turkey"},
        {"name": "Theme of Thracesion (Ephesus / Smyrna)", "latitude": 37.9400, "longitude": 27.3600, "present_day_country": "Turkey"},
        {"name": "Theme of Thrace (Constantinople Capital)", "latitude": 41.0082, "longitude": 28.9784, "present_day_country": "Turkey"},
        {"name": "Theme of Macedonia (Adrianople)", "latitude": 41.6700, "longitude": 26.5600, "present_day_country": "Greece"},
        {"name": "Theme of Hellas (Attica / Thebes)", "latitude": 38.3000, "longitude": 23.3000, "present_day_country": "Greece"},
        {"name": "Theme of Peloponnese (Corinth)", "latitude": 37.9300, "longitude": 22.9300, "present_day_country": "Greece"},
        {"name": "Theme of Thessalonica", "latitude": 40.6400, "longitude": 22.9400, "present_day_country": "Greece"},
        {"name": "Theme of Epirus (Arta)", "latitude": 39.1600, "longitude": 20.9800, "present_day_country": "Greece"},
        {"name": "Catapanate of Italy (Bari / Apulia)", "latitude": 41.1200, "longitude": 16.8600, "present_day_country": "Italy"},
        {"name": "Theme of Sicily (Syracuse)", "latitude": 37.0700, "longitude": 15.2800, "present_day_country": "Italy"},
        {"name": "Exarchate of Ravenna", "latitude": 44.4100, "longitude": 12.2000, "present_day_country": "Italy"}
    ],

    # 2. Kingdom of the Franks / Carolingian Empire (Austrasia, Neustria, Burgundy, Aquitaine, Bavaria, Saxony, Swabia)
    "Kingdom of the Franks": [
        {"name": "Austrasia (Metz / Aachen Capital)", "latitude": 49.1100, "longitude": 6.1700, "present_day_country": "France"},
        {"name": "Neustria (Paris / Soissons Capital)", "latitude": 48.8500, "longitude": 2.3500, "present_day_country": "France"},
        {"name": "Kingdom of Burgundy (Orléans / Lyon)", "latitude": 45.7600, "longitude": 4.8300, "present_day_country": "France"},
        {"name": "Duchy of Aquitaine (Bordeaux / Poitiers)", "latitude": 44.8300, "longitude": -0.5700, "present_day_country": "France"},
        {"name": "March of Brittany (Rennes)", "latitude": 48.1100, "longitude": -1.6700, "present_day_country": "France"},
        {"name": "Spanish March (Marca Hispanica - Barcelona)", "latitude": 41.3800, "longitude": 2.1700, "present_day_country": "Spain"},
        {"name": "Duchy of Bavaria (Regensburg)", "latitude": 49.0100, "longitude": 12.1000, "present_day_country": "Germany"},
        {"name": "Duchy of Swabia / Alemannia (Stuttgart)", "latitude": 48.7700, "longitude": 9.1800, "present_day_country": "Germany"},
        {"name": "Duchy of Saxony (Paderborn / Bremen)", "latitude": 51.7100, "longitude": 8.7500, "present_day_country": "Germany"},
        {"name": "Duchy of Thuringia (Erfurt)", "latitude": 50.9700, "longitude": 11.0200, "present_day_country": "Germany"},
        {"name": "Duchy of Frisia (Utrecht / Groningen)", "latitude": 52.0900, "longitude": 5.1200, "present_day_country": "Netherlands"},
        {"name": "Kingdom of Lombardy (Pavia / Milan)", "latitude": 45.1800, "longitude": 9.1500, "present_day_country": "Italy"}
    ],

    # 3. Ottoman Empire
    "Ottoman Empire": [
        {"name": "Eyalet of Rumelia (Sofia / Adrianople)", "latitude": 42.6900, "longitude": 23.3200, "present_day_country": "Bulgaria"},
        {"name": "Eyalet of Anatolia (Kütahya / Bursa)", "latitude": 39.4100, "longitude": 29.9800, "present_day_country": "Turkey"},
        {"name": "Eyalet of Rum (Sivas / Amasya)", "latitude": 39.7400, "longitude": 37.0100, "present_day_country": "Turkey"},
        {"name": "Eyalet of Karaman (Konya)", "latitude": 38.0400, "longitude": 32.6100, "present_day_country": "Turkey"},
        {"name": "Eyalet of Diyarbekir", "latitude": 37.9100, "longitude": 40.2300, "present_day_country": "Turkey"},
        {"name": "Eyalet of Damascus (Syria)", "latitude": 33.5100, "longitude": 36.2700, "present_day_country": "Syria"},
        {"name": "Eyalet of Aleppo", "latitude": 36.2000, "longitude": 37.1300, "present_day_country": "Syria"},
        {"name": "Eyalet of Egypt (Cairo)", "latitude": 30.0000, "longitude": 31.2200, "present_day_country": "Egypt"},
        {"name": "Eyalet of Algiers", "latitude": 36.7500, "longitude": 3.0500, "present_day_country": "Algeria"},
        {"name": "Eyalet of Tripoli", "latitude": 32.8800, "longitude": 13.1900, "present_day_country": "Libya"},
        {"name": "Eyalet of Baghdad", "latitude": 33.3100, "longitude": 44.3600, "present_day_country": "Iraq"},
        {"name": "Eyalet of Buda", "latitude": 47.4900, "longitude": 19.0400, "present_day_country": "Hungary"}
    ],

    # 4. Holy Roman Empire
    "Holy Roman Empire": [
        {"name": "Austrian Circle (Archduchy of Austria)", "latitude": 48.2000, "longitude": 16.3700, "present_day_country": "Austria"},
        {"name": "Bavarian Circle (Duchy of Bavaria)", "latitude": 48.1300, "longitude": 11.5800, "present_day_country": "Germany"},
        {"name": "Swabian Circle (Duchy of Swabia)", "latitude": 48.7700, "longitude": 9.1800, "present_day_country": "Germany"},
        {"name": "Franconian Circle (Nuremberg)", "latitude": 49.4500, "longitude": 11.0700, "present_day_country": "Germany"},
        {"name": "Upper Rhenish Circle (Frankfurt / Mainz)", "latitude": 50.1100, "longitude": 8.6800, "present_day_country": "Germany"},
        {"name": "Lower Rhenish-Westphalian Circle", "latitude": 50.9300, "longitude": 6.9500, "present_day_country": "Germany"},
        {"name": "Electorate of Saxony (Dresden)", "latitude": 51.0500, "longitude": 13.7300, "present_day_country": "Germany"},
        {"name": "Margraviate of Brandenburg (Berlin)", "latitude": 52.5200, "longitude": 13.4000, "present_day_country": "Germany"},
        {"name": "Lands of the Bohemian Crown (Prague)", "latitude": 50.0800, "longitude": 14.4200, "present_day_country": "Czechia"},
        {"name": "Burgundian Circle (Habsburg Netherlands)", "latitude": 50.8500, "longitude": 4.3500, "present_day_country": "Belgium"}
    ]
}

# Key Variations Map for exact key matching
KEY_VARIATIONS = {
    "Byzantine Empire": [
        "Byzantine Empire", "(Byzantine Empire)", "Q12544", "Eastern Roman Empire", "(Eastern Roman Empire)", "Byzantine",
        "(Allegiance of Papal States to Byzantine Empire)", "(Allegiance of Sasanian Empire to Byzantine Empire)"
    ],
    "Kingdom of the Franks": [
        "Kingdom of the Franks", "(Kingdom of the Franks)", "Q71925", "Q146246", "Frankish Empire", "(Frankish Empire)",
        "Carolingian Empire", "(Carolingian Empire)", "(Allegiance of East Franks to Carolingian Empire)"
    ],
    "Ottoman Empire": [
        "Ottoman Empire", "(Ottoman Empire)", "Q12560", "Sublime Porte"
    ],
    "Holy Roman Empire": [
        "Holy Roman Empire", "(Holy Roman Empire)", "Q12548", "(Allegiance of Swiss Confederation to Holy Roman Empire)"
    ]
}

def fix_exact_empires():
    print(f"[EXACT FIXER] Loading cache from {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    updated_count = 0

    for master_name, units in AUTHENTIC_EMPIRE_DIVISIONS.items():
        keys_to_update = KEY_VARIATIONS.get(master_name, [master_name])
        for k in keys_to_update:
            print(f"[EXACT FIXER] Updating '{k}' with {len(units)} authentic historical divisions...", flush=True)
            cache_data[k] = {
                "polity": k,
                "wikidata_qid": cache_data.get(k, {}).get("wikidata_qid", ""),
                "admin_units": units,
                "timestamp": 1785845865.0
            }
            updated_count += 1

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    print(f"\n[EXACT FIXER] Successfully updated {updated_count} cache keys!", flush=True)

if __name__ == "__main__":
    fix_exact_empires()
