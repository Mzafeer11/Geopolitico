"""
Authentic Historical Administrative Subunits Fixer for Umayyad Caliphate.
Replaces Wikidata noise (German village vandalism) with authentic 7th-8th century
Junds, Kūras, and Wilayahs across Al-Andalus, North Africa, Levant, Iraq, Persia, and Sindh.
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

UMAYYAD_AUTHENTIC_UNITS = [
    # Al-Andalus (Iberia)
    {"name": "Kūra of Qurtuba (Córdoba)", "latitude": 37.8882, "longitude": -4.7794, "present_day_country": "Spain"},
    {"name": "Thaghri al-A'la (Upper March - Zaragoza)", "latitude": 41.6488, "longitude": -0.8896, "present_day_country": "Spain"},
    {"name": "Thaghri al-Awsat (Middle March - Toledo)", "latitude": 39.8628, "longitude": -4.0273, "present_day_country": "Spain"},
    {"name": "Thaghri al-Adna (Lower March - Mérida)", "latitude": 38.9161, "longitude": -6.3437, "present_day_country": "Spain"},
    {"name": "Kūra of Ishbīliya (Seville)", "latitude": 37.3891, "longitude": -5.9845, "present_day_country": "Spain"},
    {"name": "Kūra of Elvira (Granada)", "latitude": 37.1773, "longitude": -3.5986, "present_day_country": "Spain"},
    {"name": "Kūra of Jayyān (Jaén)", "latitude": 37.7796, "longitude": -3.7849, "present_day_country": "Spain"},
    {"name": "Kūra of Tudmīr (Murcia)", "latitude": 37.9922, "longitude": -1.1307, "present_day_country": "Spain"},
    {"name": "Kūra of Rayya (Málaga)", "latitude": 36.7213, "longitude": -4.4214, "present_day_country": "Spain"},
    {"name": "Kūra of Bāja (Beja)", "latitude": 38.0151, "longitude": -7.8632, "present_day_country": "Portugal"},
    {"name": "Kūra of al-Gharb (Algarve)", "latitude": 37.0194, "longitude": -7.9304, "present_day_country": "Portugal"},

    # North Africa (Ifriqiya & Maghreb)
    {"name": "Wilayah of Ifriqiya (Kairouan)", "latitude": 35.6781, "longitude": 10.0963, "present_day_country": "Tunisia"},
    {"name": "Wilayah of Misr (Fustat / Cairo)", "latitude": 30.0055, "longitude": 31.2294, "present_day_country": "Egypt"},
    {"name": "Wilayah of Tripoli (Tripolitania)", "latitude": 32.8872, "longitude": 13.1913, "present_day_country": "Libya"},
    {"name": "Wilayah of Tangier (Sus al-Aqsa)", "latitude": 35.7595, "longitude": -5.8340, "present_day_country": "Morocco"},

    # Levant (Bilad al-Sham)
    {"name": "Jund Dimashq (Damascus Capital)", "latitude": 33.5138, "longitude": 36.2765, "present_day_country": "Syria"},
    {"name": "Jund Filastin (Ramla / Jerusalem)", "latitude": 31.9292, "longitude": 34.8656, "present_day_country": "Israel"},
    {"name": "Jund al-Urdunn (Tiberias)", "latitude": 32.7940, "longitude": 35.5317, "present_day_country": "Israel"},
    {"name": "Jund Hims (Homs)", "latitude": 34.7324, "longitude": 36.7137, "present_day_country": "Syria"},
    {"name": "Jund Qinnasrin (Aleppo)", "latitude": 36.2021, "longitude": 37.1343, "present_day_country": "Syria"},

    # Iraq & Persia & Central Asia & Sindh
    {"name": "Wilayah of Kufa (Iraq)", "latitude": 32.0298, "longitude": 44.4009, "present_day_country": "Iraq"},
    {"name": "Wilayah of Basra", "latitude": 30.5081, "longitude": 47.7835, "present_day_country": "Iraq"},
    {"name": "Wilayah of Jibal (Isfahan / Rayy)", "latitude": 32.6546, "longitude": 51.6680, "present_day_country": "Iran"},
    {"name": "Wilayah of Fars (Shiraz)", "latitude": 29.5918, "longitude": 52.5837, "present_day_country": "Iran"},
    {"name": "Wilayah of Khurasan (Merv)", "latitude": 37.6626, "longitude": 62.1814, "present_day_country": "Turkmenistan"},
    {"name": "Wilayah of Sindh (Mansura)", "latitude": 25.8821, "longitude": 68.6472, "present_day_country": "Pakistan"},
    {"name": "Wilayah of Hijaz (Mecca & Medina)", "latitude": 21.4225, "longitude": 39.8262, "present_day_country": "Saudi Arabia"}
]

def fix_umayyad_entry():
    print(f"[UMAYYAD FIXER] Loading cache from {CACHE_FILE.name}...", flush=True)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    umayyad_keys = [
        "Umayyad Caliphate",
        "Q8575",
        "(Umayyad Caliphate)",
        "Caliphate of Córdoba",
        "Q171526",
        "Al-Andalus"
    ]

    for key in umayyad_keys:
        if key in cache_data or key in ["Umayyad Caliphate", "Q8575", "Al-Andalus"]:
            cache_data[key] = {
                "polity": key,
                "wikidata_qid": "Q8575",
                "admin_units": UMAYYAD_AUTHENTIC_UNITS,
                "timestamp": 1785845865.0
            }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    print(f"[UMAYYAD FIXER] Successfully updated Umayyad Caliphate entries in {CACHE_FILE.name} with {len(UMAYYAD_AUTHENTIC_UNITS)} authentic historical units!", flush=True)

if __name__ == "__main__":
    fix_umayyad_entry()
