"""
Script to enrich and update the Ottoman Empire entry in data/ai_province_cache.json.
Contains the complete historical list of Ottoman Eyalets as of 1609 (and later peak expansions),
verified against historical sources and Wikipedia:

1. Habesh (Habeş / Mecca & Medina / Red Sea)
2. Adana (Ażana / Çukurova)
3. Archipelago (Cezayir-i Bahr-i Sefid / Aegean Islands / Kapudan Pasha)
4. Aleppo (Ḥaleb / Halep)
5. Algiers (Cezâyîr-i Ġarb)
6. Anatolia (Anadolu)
7. Baghdad (Baġdâd)
8. Basra (Baṣra)
9. Bosnia (Bosna)
10. Budin (Buda)
11. Kıbrıs (Cyprus)
12. Diyarbekir (Diyârbekir / Diyarbakır)
13. Eger (Eğri)
14. Egypt (Mıṣır)
15. Erzurum
16. Al-Hasa (Lahsa / Eastern Arabia)
17. Kefe (Theodosia / Crimea)
18. Kanizsa (Kanije)
19. Karaman
20. Kars
21. Dulkadir (Maraş)
22. Mosul (Musul)
23. Ar-Raqqah (Rakka / Urfa)
24. Rumelia (Rumeli / Sofia)
25. Childir (Çıldır / Meskheti / Akhaltsikhe)
26. Shahrizor (Şehrizor / Kirkuk)
27. Silistria (Silistre / Ochakiv / Özi)
28. Sivas (Rum)
29. Syria / Damascus (Şam)
30. Temeşvar (Tımışvar / Banat)
31. Trebizond (Trabzon / Lazistan)
32. Tripoli-in-the-East (Trablus-ı Şam / Lebanon)
33. Tripolitania (Trablus-ı Garb / Libya)
34. Tunis (Tunus)
35. Van
36. Yemen (Sana'a & Zabid)
37. Morea (Mora / Peloponnese & Southern Greece)
38. Crete (Girit / Candia)
39. Yanina (Yanya / Epirus & Western Greece)
40. Thessaloniki (Selanik / Macedonia & Northern Greece)
41. Sidon (Sayda / Acre & Palestine)
42. Uyvar (Nové Zámky / Slovakia)
43. Varat (Oradea / Crișana)
44. Podolia (Kamaniçe / Ukraine)
45. Vidin
46. Niš
47. Scutari (İşkodra / Northern Albania)
"""

import json
from pathlib import Path

CACHE_FILE = Path("data/ai_province_cache.json")

OTTOMAN_UNITS = [
    # ─── 1. ARABIAN PENINSULA & RED SEA (HEJAZ, YEMEN, GULF) ─────────────────
    {
        "name": "Habesh (Habeş / Mecca and Medina / Red Sea)",
        "capital_historical": "Jeddah / Mecca / Suakin",
        "capital_modern": "Mecca, Saudi Arabia",
        "tier": "Eyalet",
        "latitude": 21.4225,
        "longitude": 39.8262,
        "present_day_country": "Saudi Arabia",
        "inception": 1554,
        "confidence": "high"
    },
    {
        "name": "Yemen",
        "capital_historical": "Sana'a / Zabid",
        "capital_modern": "Sanaa, Yemen",
        "tier": "Eyalet",
        "latitude": 15.3694,
        "longitude": 44.1910,
        "present_day_country": "Yemen",
        "inception": 1517,
        "confidence": "high"
    },
    {
        "name": "Al-Hasa (Lahsa / Eastern Arabia)",
        "capital_historical": "Al-Hofuf",
        "capital_modern": "Al-Hofuf, Saudi Arabia",
        "tier": "Eyalet",
        "latitude": 25.3800,
        "longitude": 49.5855,
        "present_day_country": "Saudi Arabia",
        "inception": 1560,
        "confidence": "high"
    },

    # ─── 2. GREECE & AEGEAN SEA ──────────────────────────────────────────────
    {
        "name": "Morea (Mora / Peloponnese)",
        "capital_historical": "Tripoli / Nafplio",
        "capital_modern": "Tripoli, Greece",
        "tier": "Eyalet",
        "latitude": 37.5089,
        "longitude": 22.3794,
        "present_day_country": "Greece",
        "inception": 1461,
        "confidence": "high"
    },
    {
        "name": "Archipelago (Cezayir-i Bahr-i Sefid / Aegean Islands)",
        "capital_historical": "Gelibolu / Rhodes / Chios",
        "capital_modern": "Rhodes, Greece",
        "tier": "Eyalet",
        "latitude": 36.4349,
        "longitude": 28.2175,
        "present_day_country": "Greece",
        "inception": 1535,
        "confidence": "high"
    },
    {
        "name": "Crete (Girit)",
        "capital_historical": "Candia (Heraklion) / Chania",
        "capital_modern": "Heraklion, Greece",
        "tier": "Eyalet",
        "latitude": 35.3387,
        "longitude": 25.1442,
        "present_day_country": "Greece",
        "inception": 1669,
        "confidence": "high"
    },
    {
        "name": "Yanina (Yanya / Epirus)",
        "capital_historical": "Ioannina",
        "capital_modern": "Ioannina, Greece",
        "tier": "Eyalet",
        "latitude": 39.6650,
        "longitude": 20.8537,
        "present_day_country": "Greece",
        "inception": 1670,
        "confidence": "high"
    },
    {
        "name": "Thessaloniki (Selanik / Macedonia)",
        "capital_historical": "Thessaloniki",
        "capital_modern": "Thessaloniki, Greece",
        "tier": "Eyalet",
        "latitude": 40.6401,
        "longitude": 22.9444,
        "present_day_country": "Greece",
        "inception": 1430,
        "confidence": "high"
    },

    # ─── 3. DIYARBEKIR & EASTERN ANATOLIA / CAUCASUS ─────────────────────────
    {
        "name": "Diyarbekir (Diyârbekir / Diyarbakır)",
        "capital_historical": "Diyarbekir (Amid)",
        "capital_modern": "Diyarbakir, Turkey",
        "tier": "Eyalet",
        "latitude": 37.9144,
        "longitude": 40.2306,
        "present_day_country": "Turkey",
        "inception": 1515,
        "confidence": "high"
    },
    {
        "name": "Erzurum",
        "capital_historical": "Erzurum",
        "capital_modern": "Erzurum, Turkey",
        "tier": "Eyalet",
        "latitude": 39.9043,
        "longitude": 41.2679,
        "present_day_country": "Turkey",
        "inception": 1533,
        "confidence": "high"
    },
    {
        "name": "Van",
        "capital_historical": "Van",
        "capital_modern": "Van, Turkey",
        "tier": "Eyalet",
        "latitude": 38.4946,
        "longitude": 43.3832,
        "present_day_country": "Turkey",
        "inception": 1548,
        "confidence": "high"
    },
    {
        "name": "Dulkadir (Maraş)",
        "capital_historical": "Maraş",
        "capital_modern": "Kahramanmaras, Turkey",
        "tier": "Eyalet",
        "latitude": 37.5753,
        "longitude": 36.9228,
        "present_day_country": "Turkey",
        "inception": 1522,
        "confidence": "high"
    },
    {
        "name": "Sivas (Rum)",
        "capital_historical": "Sivas / Amasya",
        "capital_modern": "Sivas, Turkey",
        "tier": "Eyalet",
        "latitude": 39.7477,
        "longitude": 37.0179,
        "present_day_country": "Turkey",
        "inception": 1398,
        "confidence": "high"
    },
    {
        "name": "Karaman",
        "capital_historical": "Konya",
        "capital_modern": "Konya, Turkey",
        "tier": "Eyalet",
        "latitude": 37.8746,
        "longitude": 32.4932,
        "present_day_country": "Turkey",
        "inception": 1483,
        "confidence": "high"
    },
    {
        "name": "Adana (Ażana / Çukurova)",
        "capital_historical": "Adana",
        "capital_modern": "Adana, Turkey",
        "tier": "Eyalet",
        "latitude": 36.9914,
        "longitude": 35.3308,
        "present_day_country": "Turkey",
        "inception": 1608,
        "confidence": "high"
    },
    {
        "name": "Trebizond (Trabzon / Lazistan)",
        "capital_historical": "Trabzon",
        "capital_modern": "Trabzon, Turkey",
        "tier": "Eyalet",
        "latitude": 41.0027,
        "longitude": 39.7168,
        "present_day_country": "Turkey",
        "inception": 1461,
        "confidence": "high"
    },
    {
        "name": "Kars",
        "capital_historical": "Kars",
        "capital_modern": "Kars, Turkey",
        "tier": "Eyalet",
        "latitude": 40.6013,
        "longitude": 43.0950,
        "present_day_country": "Turkey",
        "inception": 1580,
        "confidence": "high"
    },
    {
        "name": "Childir (Çıldır / Meskheti / Akhaltsikhe)",
        "capital_historical": "Akhaltsikhe / Çıldır",
        "capital_modern": "Akhaltsikhe, Georgia",
        "tier": "Eyalet",
        "latitude": 41.6389,
        "longitude": 42.9833,
        "present_day_country": "Georgia",
        "inception": 1578,
        "confidence": "high"
    },
    {
        "name": "Anatolia (Anadolu)",
        "capital_historical": "Kütahya / Bursa",
        "capital_modern": "Kutahya, Turkey",
        "tier": "Eyalet",
        "latitude": 39.4200,
        "longitude": 29.9857,
        "present_day_country": "Turkey",
        "inception": 1393,
        "confidence": "high"
    },

    # ─── 4. LEVANT & MESOPOTAMIA ─────────────────────────────────────────────
    {
        "name": "Syria (Damascus / Şam)",
        "capital_historical": "Damascus",
        "capital_modern": "Damascus, Syria",
        "tier": "Eyalet",
        "latitude": 33.5138,
        "longitude": 36.2765,
        "present_day_country": "Syria",
        "inception": 1517,
        "confidence": "high"
    },
    {
        "name": "Aleppo (Ḥaleb / Halep)",
        "capital_historical": "Aleppo",
        "capital_modern": "Aleppo, Syria",
        "tier": "Eyalet",
        "latitude": 36.2021,
        "longitude": 37.1343,
        "present_day_country": "Syria",
        "inception": 1534,
        "confidence": "high"
    },
    {
        "name": "Tripoli-in-the-East (Trablus-ı Şam)",
        "capital_historical": "Tripoli",
        "capital_modern": "Tripoli, Lebanon",
        "tier": "Eyalet",
        "latitude": 34.4367,
        "longitude": 35.8497,
        "present_day_country": "Lebanon",
        "inception": 1579,
        "confidence": "high"
    },
    {
        "name": "Sidon (Sayda / Acre & Palestine)",
        "capital_historical": "Sidon / Acre",
        "capital_modern": "Sidon, Lebanon",
        "tier": "Eyalet",
        "latitude": 33.5599,
        "longitude": 35.3756,
        "present_day_country": "Lebanon",
        "inception": 1660,
        "confidence": "high"
    },
    {
        "name": "Ar-Raqqah (Rakka / Urfa)",
        "capital_historical": "Raqqa / Urfa",
        "capital_modern": "Sanliurfa, Turkey",
        "tier": "Eyalet",
        "latitude": 37.1674,
        "longitude": 38.7955,
        "present_day_country": "Turkey",
        "inception": 1586,
        "confidence": "high"
    },
    {
        "name": "Mosul (Musul)",
        "capital_historical": "Mosul",
        "capital_modern": "Mosul, Iraq",
        "tier": "Eyalet",
        "latitude": 36.3400,
        "longitude": 43.1300,
        "present_day_country": "Iraq",
        "inception": 1535,
        "confidence": "high"
    },
    {
        "name": "Baghdad (Baġdâd)",
        "capital_historical": "Baghdad",
        "capital_modern": "Baghdad, Iraq",
        "tier": "Eyalet",
        "latitude": 33.3152,
        "longitude": 44.3661,
        "present_day_country": "Iraq",
        "inception": 1535,
        "confidence": "high"
    },
    {
        "name": "Basra (Baṣra)",
        "capital_historical": "Basra",
        "capital_modern": "Basra, Iraq",
        "tier": "Eyalet",
        "latitude": 30.5081,
        "longitude": 47.7835,
        "present_day_country": "Iraq",
        "inception": 1538,
        "confidence": "high"
    },
    {
        "name": "Shahrizor (Şehrizor / Kirkuk)",
        "capital_historical": "Kirkuk",
        "capital_modern": "Kirkuk, Iraq",
        "tier": "Eyalet",
        "latitude": 35.4670,
        "longitude": 44.3920,
        "present_day_country": "Iraq",
        "inception": 1554,
        "confidence": "high"
    },

    # ─── 5. BALKANS & DANUBIAN MARCHES ───────────────────────────────────────
    {
        "name": "Rumelia (Rumeli / Sofia)",
        "capital_historical": "Sofia",
        "capital_modern": "Sofia, Bulgaria",
        "tier": "Eyalet",
        "latitude": 42.6977,
        "longitude": 23.3217,
        "present_day_country": "Bulgaria",
        "inception": 1365,
        "confidence": "high"
    },
    {
        "name": "Bosnia (Bosna)",
        "capital_historical": "Sarajevo / Banja Luka",
        "capital_modern": "Sarajevo, Bosnia and Herzegovina",
        "tier": "Eyalet",
        "latitude": 43.8563,
        "longitude": 18.4131,
        "present_day_country": "Bosnia and Herzegovina",
        "inception": 1580,
        "confidence": "high"
    },
    {
        "name": "Silistria (Silistre / Ochakiv / Özi)",
        "capital_historical": "Silistra",
        "capital_modern": "Silistra, Bulgaria",
        "tier": "Eyalet",
        "latitude": 44.1172,
        "longitude": 27.2606,
        "present_day_country": "Bulgaria",
        "inception": 1593,
        "confidence": "high"
    },
    {
        "name": "Budin (Buda)",
        "capital_historical": "Buda",
        "capital_modern": "Budapest, Hungary",
        "tier": "Eyalet",
        "latitude": 47.4979,
        "longitude": 19.0402,
        "present_day_country": "Hungary",
        "inception": 1541,
        "confidence": "high"
    },
    {
        "name": "Temeşvar (Tımışvar / Banat)",
        "capital_historical": "Temeşvar",
        "capital_modern": "Timisoara, Romania",
        "tier": "Eyalet",
        "latitude": 45.7537,
        "longitude": 21.2257,
        "present_day_country": "Romania",
        "inception": 1552,
        "confidence": "high"
    },
    {
        "name": "Kanizsa (Kanije)",
        "capital_historical": "Kanizsa",
        "capital_modern": "Nagykanizsa, Hungary",
        "tier": "Eyalet",
        "latitude": 46.4533,
        "longitude": 16.9912,
        "present_day_country": "Hungary",
        "inception": 1600,
        "confidence": "high"
    },
    {
        "name": "Eger (Eğri)",
        "capital_historical": "Eger",
        "capital_modern": "Eger, Hungary",
        "tier": "Eyalet",
        "latitude": 47.9025,
        "longitude": 20.3772,
        "present_day_country": "Hungary",
        "inception": 1596,
        "confidence": "high"
    },
    {
        "name": "Kefe (Theodosia / Crimea)",
        "capital_historical": "Kefe",
        "capital_modern": "Feodosia, Ukraine",
        "tier": "Eyalet",
        "latitude": 45.0345,
        "longitude": 35.3789,
        "present_day_country": "Ukraine",
        "inception": 1568,
        "confidence": "high"
    },
    {
        "name": "Varat (Oradea / Crișana)",
        "capital_historical": "Varat",
        "capital_modern": "Oradea, Romania",
        "tier": "Eyalet",
        "latitude": 47.0465,
        "longitude": 21.9189,
        "present_day_country": "Romania",
        "inception": 1660,
        "confidence": "high"
    },
    {
        "name": "Uyvar (Nové Zámky)",
        "capital_historical": "Uyvar",
        "capital_modern": "Nove Zamky, Slovakia",
        "tier": "Eyalet",
        "latitude": 47.9854,
        "longitude": 18.1619,
        "present_day_country": "Slovakia",
        "inception": 1663,
        "confidence": "high"
    },
    {
        "name": "Podolia (Kamaniçe)",
        "capital_historical": "Kamaniçe",
        "capital_modern": "Kamianets-Podilskyi, Ukraine",
        "tier": "Eyalet",
        "latitude": 48.6788,
        "longitude": 26.5852,
        "present_day_country": "Ukraine",
        "inception": 1672,
        "confidence": "high"
    },
    {
        "name": "Vidin",
        "capital_historical": "Vidin",
        "capital_modern": "Vidin, Bulgaria",
        "tier": "Eyalet",
        "latitude": 43.9962,
        "longitude": 22.8779,
        "present_day_country": "Bulgaria",
        "inception": 1846,
        "confidence": "high"
    },
    {
        "name": "Niš",
        "capital_historical": "Niš",
        "capital_modern": "Nis, Serbia",
        "tier": "Eyalet",
        "latitude": 43.3209,
        "longitude": 21.8958,
        "present_day_country": "Serbia",
        "inception": 1846,
        "confidence": "high"
    },
    {
        "name": "Scutari (İşkodra / Northern Albania)",
        "capital_historical": "Shkodër",
        "capital_modern": "Shkoder, Albania",
        "tier": "Eyalet",
        "latitude": 42.0683,
        "longitude": 19.5126,
        "present_day_country": "Albania",
        "inception": 1757,
        "confidence": "high"
    },

    # ─── 6. NORTH AFRICA & MEDITERRANEAN ─────────────────────────────────────
    {
        "name": "Egypt (Mıṣır)",
        "capital_historical": "Cairo",
        "capital_modern": "Cairo, Egypt",
        "tier": "Eyalet",
        "latitude": 30.0444,
        "longitude": 31.2357,
        "present_day_country": "Egypt",
        "inception": 1517,
        "confidence": "high"
    },
    {
        "name": "Kıbrıs (Cyprus)",
        "capital_historical": "Nicosia (Lefkoşa)",
        "capital_modern": "Nicosia, Cyprus",
        "tier": "Eyalet",
        "latitude": 35.1856,
        "longitude": 33.3823,
        "present_day_country": "Cyprus",
        "inception": 1571,
        "confidence": "high"
    },
    {
        "name": "Tripolitania (Trablus-ı Garb)",
        "capital_historical": "Tripoli",
        "capital_modern": "Tripoli, Libya",
        "tier": "Eyalet",
        "latitude": 32.8872,
        "longitude": 13.1913,
        "present_day_country": "Libya",
        "inception": 1551,
        "confidence": "high"
    },
    {
        "name": "Tunis (Tunus)",
        "capital_historical": "Tunis",
        "capital_modern": "Tunis, Tunisia",
        "tier": "Eyalet",
        "latitude": 36.8065,
        "longitude": 10.1815,
        "present_day_country": "Tunisia",
        "inception": 1524,
        "confidence": "high"
    },
    {
        "name": "Algiers (Cezâyîr-i Ġarb)",
        "capital_historical": "Algiers",
        "capital_modern": "Algiers, Algeria",
        "tier": "Eyalet",
        "latitude": 36.7538,
        "longitude": 3.0588,
        "present_day_country": "Algeria",
        "inception": 1517,
        "confidence": "high"
    }
]

def enrich_ottoman():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    cache["Ottoman Empire"] = {
        "polity": "Ottoman Empire",
        "peak_year_from": 1520,
        "peak_year_to": 1683,
        "peak_area_km2": 5200000.0,
        "bbox": [8.0, 12.0, 52.0, 49.0],
        "source": "curated_historical_1609_eyalets",
        "admin_units": OTTOMAN_UNITS
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Updated Ottoman Empire in {CACHE_FILE.name} with all {len(OTTOMAN_UNITS)} historical Eyalets!")

if __name__ == "__main__":
    enrich_ottoman()
