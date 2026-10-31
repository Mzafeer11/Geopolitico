"""
Comprehensive correction script for vulnerable / distorted historical empires in data/ai_province_cache.json.

Fixes:
1. European Colonial Empires: Adds complete core homeland divisions with geocoded capitals (Castile, Aragon, Andalusia, Minho, Alentejo, Holland, Zeeland, etc.) so they are never left with only overseas islands.
2. Missing Foundational Empires: Adds Archduchy of Austria, Caliphate of Cordoba, Emirate of Cordoba, Kingdom of Ireland.
3. Spatially Displaced Empires: Corrects Great Yuan, Lydia, Goths, Burgundians, 17th Dynasty of Egypt with accurate historical administrative seats within their historical footprint.
"""

import json
from pathlib import Path

CACHE_FILE = Path("data/ai_province_cache.json")

CORRECTIONS = {
    "Kingdom of Spain": {
        "polity": "Kingdom of Spain",
        "peak_year_from": 1516,
        "peak_year_to": 1700,
        "peak_area_km2": 3150000.0,
        "bbox": [-9.30, 35.77, 19.24, 52.32],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Crown of Castile", "capital_historical": "Valladolid", "capital_modern": "Valladolid, Spain", "tier": "Kingdom", "latitude": 41.6523, "longitude": -4.7245, "confidence": "high"},
            {"name": "Crown of Aragon", "capital_historical": "Zaragoza", "capital_modern": "Zaragoza, Spain", "tier": "Kingdom", "latitude": 41.6488, "longitude": -0.8891, "confidence": "high"},
            {"name": "Principality of Catalonia", "capital_historical": "Barcelona", "capital_modern": "Barcelona, Spain", "tier": "Principality", "latitude": 41.3879, "longitude": 2.1699, "confidence": "high"},
            {"name": "Kingdom of Valencia", "capital_historical": "Valencia", "capital_modern": "Valencia, Spain", "tier": "Kingdom", "latitude": 39.4699, "longitude": -0.3763, "confidence": "high"},
            {"name": "Kingdom of Seville (Andalusia)", "capital_historical": "Seville", "capital_modern": "Seville, Spain", "tier": "Kingdom", "latitude": 37.3891, "longitude": -5.9845, "confidence": "high"},
            {"name": "Kingdom of Granada", "capital_historical": "Granada", "capital_modern": "Granada, Spain", "tier": "Kingdom", "latitude": 37.1773, "longitude": -3.5986, "confidence": "high"},
            {"name": "Kingdom of Galicia", "capital_historical": "Santiago de Compostela", "capital_modern": "Santiago de Compostela, Spain", "tier": "Kingdom", "latitude": 42.8782, "longitude": -8.5448, "confidence": "high"},
            {"name": "Kingdom of Navarre", "capital_historical": "Pamplona", "capital_modern": "Pamplona, Spain", "tier": "Kingdom", "latitude": 42.8125, "longitude": -1.6458, "confidence": "high"},
            {"name": "Archduchy of Austria (Habsburg Crown Lands)", "capital_historical": "Vienna", "capital_modern": "Vienna, Austria", "tier": "Archduchy", "latitude": 48.2082, "longitude": 16.3738, "confidence": "high"},
            {"name": "County of Tyrol", "capital_historical": "Innsbruck", "capital_modern": "Innsbruck, Austria", "tier": "County", "latitude": 47.2692, "longitude": 11.4041, "confidence": "high"},
            {"name": "Duchy of Styria", "capital_historical": "Graz", "capital_modern": "Graz, Austria", "tier": "Duchy", "latitude": 47.0707, "longitude": 15.4395, "confidence": "high"},
            {"name": "Duchy of Carinthia", "capital_historical": "Klagenfurt", "capital_modern": "Klagenfurt, Austria", "tier": "Duchy", "latitude": 46.6247, "longitude": 14.3053, "confidence": "high"},
            {"name": "Duchy of Milan", "capital_historical": "Milan", "capital_modern": "Milan, Italy", "tier": "Duchy", "latitude": 45.4642, "longitude": 9.1900, "confidence": "high"},
            {"name": "Kingdom of Naples", "capital_historical": "Naples", "capital_modern": "Naples, Italy", "tier": "Kingdom", "latitude": 40.8518, "longitude": 14.2681, "confidence": "high"},
            {"name": "Kingdom of Sicily", "capital_historical": "Palermo", "capital_modern": "Palermo, Italy", "tier": "Kingdom", "latitude": 38.1157, "longitude": 13.3615, "confidence": "high"},
            {"name": "Kingdom of Sardinia", "capital_historical": "Cagliari", "capital_modern": "Cagliari, Italy", "tier": "Kingdom", "latitude": 39.2238, "longitude": 9.1217, "confidence": "high"},
            {"name": "Spanish Netherlands (Flanders/Brabant)", "capital_historical": "Brussels", "capital_modern": "Brussels, Belgium", "tier": "Lordship", "latitude": 50.8503, "longitude": 4.3517, "confidence": "high"},
            {"name": "Canary Islands", "capital_historical": "Las Palmas", "capital_modern": "Las Palmas, Spain", "tier": "Captaincy General", "latitude": 28.1248, "longitude": -15.4300, "confidence": "high"}
        ]
    },
    "Spanish Empire": {
        "polity": "Spanish Empire",
        "peak_year_from": 1580,
        "peak_year_to": 1790,
        "peak_area_km2": 13700000.0,
        "bbox": [-118.0, -55.0, 125.0, 52.0],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Crown of Castile", "capital_historical": "Madrid", "capital_modern": "Madrid, Spain", "tier": "Kingdom", "latitude": 40.4168, "longitude": -3.7038, "confidence": "high"},
            {"name": "Crown of Aragon", "capital_historical": "Zaragoza", "capital_modern": "Zaragoza, Spain", "tier": "Kingdom", "latitude": 41.6488, "longitude": -0.8891, "confidence": "high"},
            {"name": "Kingdom of Navarre", "capital_historical": "Pamplona", "capital_modern": "Pamplona, Spain", "tier": "Kingdom", "latitude": 42.8125, "longitude": -1.6458, "confidence": "high"},
            {"name": "Kingdom of Naples", "capital_historical": "Naples", "capital_modern": "Naples, Italy", "tier": "Kingdom", "latitude": 40.8518, "longitude": 14.2681, "confidence": "high"},
            {"name": "Kingdom of Sicily", "capital_historical": "Palermo", "capital_modern": "Palermo, Italy", "tier": "Kingdom", "latitude": 38.1157, "longitude": 13.3615, "confidence": "high"},
            {"name": "Duchy of Milan", "capital_historical": "Milan", "capital_modern": "Milan, Italy", "tier": "Duchy", "latitude": 45.4642, "longitude": 9.1900, "confidence": "high"},
            {"name": "Spanish Netherlands", "capital_historical": "Brussels", "capital_modern": "Brussels, Belgium", "tier": "Lordship", "latitude": 50.8503, "longitude": 4.3517, "confidence": "high"},
            {"name": "Viceroyalty of New Spain", "capital_historical": "Mexico City", "capital_modern": "Mexico City, Mexico", "tier": "Viceroyalty", "latitude": 19.4326, "longitude": -99.1332, "confidence": "high"},
            {"name": "Viceroyalty of Peru", "capital_historical": "Lima", "capital_modern": "Lima, Peru", "tier": "Viceroyalty", "latitude": -12.0464, "longitude": -77.0428, "confidence": "high"},
            {"name": "Viceroyalty of New Granada", "capital_historical": "Bogotá", "capital_modern": "Bogota, Colombia", "tier": "Viceroyalty", "latitude": 4.7110, "longitude": -74.0721, "confidence": "high"},
            {"name": "Viceroyalty of the Río de la Plata", "capital_historical": "Buenos Aires", "capital_modern": "Buenos Aires, Argentina", "tier": "Viceroyalty", "latitude": -34.6037, "longitude": -58.3816, "confidence": "high"},
            {"name": "Captaincy General of Cuba", "capital_historical": "Havana", "capital_modern": "Havana, Cuba", "tier": "Captaincy General", "latitude": 23.1136, "longitude": -82.3666, "confidence": "high"},
            {"name": "Captaincy General of the Philippines", "capital_historical": "Manila", "capital_modern": "Manila, Philippines", "tier": "Captaincy General", "latitude": 14.5995, "longitude": 120.9842, "confidence": "high"}
        ]
    },
    "Kingdom of Portugal": {
        "polity": "Kingdom of Portugal",
        "peak_year_from": 1415,
        "peak_year_to": 1822,
        "peak_area_km2": 92000.0,
        "bbox": [-9.53, 36.96, -6.19, 42.15],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Entre-Douro-e-Minho", "capital_historical": "Braga", "capital_modern": "Braga, Portugal", "tier": "Province", "latitude": 41.5454, "longitude": -8.4265, "confidence": "high"},
            {"name": "Trás-os-Montes", "capital_historical": "Bragança", "capital_modern": "Braganca, Portugal", "tier": "Province", "latitude": 41.8061, "longitude": -6.7567, "confidence": "high"},
            {"name": "Beira", "capital_historical": "Coimbra", "capital_modern": "Coimbra, Portugal", "tier": "Province", "latitude": 40.2033, "longitude": -8.4103, "confidence": "high"},
            {"name": "Estremadura", "capital_historical": "Lisbon", "capital_modern": "Lisbon, Portugal", "tier": "Province", "latitude": 38.7223, "longitude": -9.1393, "confidence": "high"},
            {"name": "Alentejo", "capital_historical": "Évora", "capital_modern": "Evora, Portugal", "tier": "Province", "latitude": 38.5714, "longitude": -7.9070, "confidence": "high"},
            {"name": "Kingdom of the Algarve", "capital_historical": "Silves", "capital_modern": "Silves, Portugal", "tier": "Kingdom", "latitude": 37.1887, "longitude": -8.4385, "confidence": "high"},
            {"name": "Azores", "capital_historical": "Angra do Heroísmo", "capital_modern": "Angra do Heroismo, Portugal", "tier": "Captaincy", "latitude": 38.6558, "longitude": -27.2206, "confidence": "high"},
            {"name": "Madeira", "capital_historical": "Funchal", "capital_modern": "Funchal, Portugal", "tier": "Captaincy", "latitude": 32.6669, "longitude": -16.9241, "confidence": "high"}
        ]
    },
    "Portuguese Empire": {
        "polity": "Portuguese Empire",
        "peak_year_from": 1500,
        "peak_year_to": 1822,
        "peak_area_km2": 5500000.0,
        "bbox": [-60.0, -30.0, 125.0, 42.15],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Metropolitan Portugal (Kingdom of Portugal)", "capital_historical": "Lisbon", "capital_modern": "Lisbon, Portugal", "tier": "Kingdom", "latitude": 38.7223, "longitude": -9.1393, "confidence": "high"},
            {"name": "State of Brazil", "capital_historical": "Salvador da Bahia", "capital_modern": "Salvador, Brazil", "tier": "State", "latitude": -12.9777, "longitude": -38.5016, "confidence": "high"},
            {"name": "State of Maranhão and Grão-Pará", "capital_historical": "São Luís", "capital_modern": "Sao Luis, Brazil", "tier": "State", "latitude": -2.5307, "longitude": -44.3068, "confidence": "high"},
            {"name": "State of India (Estado da Índia)", "capital_historical": "Velha Goa", "capital_modern": "Goa, India", "tier": "State", "latitude": 15.5009, "longitude": 73.9116, "confidence": "high"},
            {"name": "Kingdom of Angola", "capital_historical": "Luanda", "capital_modern": "Luanda, Angola", "tier": "Captaincy General", "latitude": -8.8390, "longitude": 13.2894, "confidence": "high"},
            {"name": "Captaincy-General of Mozambique", "capital_historical": "Mozambique Island", "capital_modern": "Mozambique, Mozambique", "tier": "Captaincy General", "latitude": -15.0342, "longitude": 40.7306, "confidence": "high"},
            {"name": "Cape Verde and Guinea", "capital_historical": "Ribeira Grande", "capital_modern": "Cidade Velha, Cape Verde", "tier": "Captaincy", "latitude": 14.9149, "longitude": -23.6053, "confidence": "high"},
            {"name": "Macau", "capital_historical": "Macau", "capital_modern": "Macau, China", "tier": "Capitaincy", "latitude": 22.1987, "longitude": 113.5439, "confidence": "high"}
        ]
    },
    "Dutch Republic": {
        "polity": "Dutch Republic",
        "peak_year_from": 1581,
        "peak_year_to": 1795,
        "peak_area_km2": 34000.0,
        "bbox": [3.35, 51.30, 7.22, 53.55],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "County of Holland", "capital_historical": "The Hague", "capital_modern": "The Hague, Netherlands", "tier": "Province", "latitude": 52.0705, "longitude": 4.3007, "confidence": "high"},
            {"name": "Lordship of Zeeland", "capital_historical": "Middelburg", "capital_modern": "Middelburg, Netherlands", "tier": "Province", "latitude": 51.4988, "longitude": 3.6109, "confidence": "high"},
            {"name": "Lordship of Utrecht", "capital_historical": "Utrecht", "capital_modern": "Utrecht, Netherlands", "tier": "Province", "latitude": 52.0907, "longitude": 5.1214, "confidence": "high"},
            {"name": "Duchy of Guelders", "capital_historical": "Arnhem", "capital_modern": "Arnhem, Netherlands", "tier": "Province", "latitude": 51.9851, "longitude": 5.8987, "confidence": "high"},
            {"name": "Lordship of Overijssel", "capital_historical": "Zwolle", "capital_modern": "Zwolle, Netherlands", "tier": "Province", "latitude": 52.5168, "longitude": 6.0830, "confidence": "high"},
            {"name": "Lordship of Friesland", "capital_historical": "Leeuwarden", "capital_modern": "Leeuwarden, Netherlands", "tier": "Province", "latitude": 53.2012, "longitude": 5.7999, "confidence": "high"},
            {"name": "Lordship of Groningen", "capital_historical": "Groningen", "capital_modern": "Groningen, Netherlands", "tier": "Province", "latitude": 53.2194, "longitude": 6.5665, "confidence": "high"},
            {"name": "Generality Lands (States Brabant)", "capital_historical": "'s-Hertogenbosch", "capital_modern": "s-Hertogenbosch, Netherlands", "tier": "Territory", "latitude": 51.6978, "longitude": 5.3037, "confidence": "high"}
        ]
    },
    "Archduchy of Austria": {
        "polity": "Archduchy of Austria",
        "peak_year_from": 1453,
        "peak_year_to": 1804,
        "peak_area_km2": 85000.0,
        "bbox": [9.53, 46.37, 17.16, 49.02],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Lower Austria (Archduchy below the Enns)", "capital_historical": "Vienna", "capital_modern": "Vienna, Austria", "tier": "Archduchy", "latitude": 48.2082, "longitude": 16.3738, "confidence": "high"},
            {"name": "Upper Austria (Archduchy above the Enns)", "capital_historical": "Linz", "capital_modern": "Linz, Austria", "tier": "Archduchy", "latitude": 48.3069, "longitude": 14.2858, "confidence": "high"},
            {"name": "Duchy of Styria (Inner Austria)", "capital_historical": "Graz", "capital_modern": "Graz, Austria", "tier": "Duchy", "latitude": 47.0707, "longitude": 15.4395, "confidence": "high"},
            {"name": "Duchy of Carinthia", "capital_historical": "Klagenfurt", "capital_modern": "Klagenfurt, Austria", "tier": "Duchy", "latitude": 46.6247, "longitude": 14.3053, "confidence": "high"},
            {"name": "Duchy of Carniola", "capital_historical": "Laibach (Ljubljana)", "capital_modern": "Ljubljana, Slovenia", "tier": "Duchy", "latitude": 46.0569, "longitude": 14.5058, "confidence": "high"},
            {"name": "Princely County of Tyrol", "capital_historical": "Innsbruck", "capital_modern": "Innsbruck, Austria", "tier": "County", "latitude": 47.2692, "longitude": 11.4041, "confidence": "high"},
            {"name": "Vorarlberg", "capital_historical": "Bregenz", "capital_modern": "Bregenz, Austria", "tier": "Lordship", "latitude": 47.5031, "longitude": 9.7471, "confidence": "high"},
            {"name": "Prince-Archbishopric of Salzburg", "capital_historical": "Salzburg", "capital_modern": "Salzburg, Austria", "tier": "Archbishopric", "latitude": 47.8095, "longitude": 13.0550, "confidence": "high"}
        ]
    },
    "Caliphate of Cordoba": {
        "polity": "Caliphate of Cordoba",
        "peak_year_from": 929,
        "peak_year_to": 1031,
        "peak_area_km2": 600000.0,
        "bbox": [-9.50, 35.80, 3.30, 42.50],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Kura of Qurtubah (Cordoba)", "capital_historical": "Qurtubah", "capital_modern": "Cordoba, Spain", "tier": "Province", "latitude": 37.8882, "longitude": -4.7794, "confidence": "high"},
            {"name": "Kura of Ishbiliyah (Seville)", "capital_historical": "Ishbiliyah", "capital_modern": "Seville, Spain", "tier": "Province", "latitude": 37.3891, "longitude": -5.9845, "confidence": "high"},
            {"name": "Lower March (Al-Tagr al-Adna / Merida)", "capital_historical": "Marida", "capital_modern": "Merida, Spain", "tier": "Military March", "latitude": 38.9161, "longitude": -6.3437, "confidence": "high"},
            {"name": "Middle March (Al-Tagr al-Awsat / Toledo)", "capital_historical": "Tulaytulah", "capital_modern": "Toledo, Spain", "tier": "Military March", "latitude": 39.8628, "longitude": -4.0273, "confidence": "high"},
            {"name": "Upper March (Al-Tagr al-A'la / Zaragoza)", "capital_historical": "Saraqustah", "capital_modern": "Zaragoza, Spain", "tier": "Military March", "latitude": 41.6488, "longitude": -0.8891, "confidence": "high"},
            {"name": "Kura of Balansiyyah (Valencia)", "capital_historical": "Balansiyyah", "capital_modern": "Valencia, Spain", "tier": "Province", "latitude": 39.4699, "longitude": -0.3763, "confidence": "high"},
            {"name": "Kura of Gharnatah / Elvira", "capital_historical": "Ilbira / Gharnatah", "capital_modern": "Granada, Spain", "tier": "Province", "latitude": 37.1773, "longitude": -3.5986, "confidence": "high"},
            {"name": "Kura of Rayya (Malaga)", "capital_historical": "Malaqah", "capital_modern": "Malaga, Spain", "tier": "Province", "latitude": 36.7213, "longitude": -4.4214, "confidence": "high"},
            {"name": "Gharb al-Andalus (Algarve / Lisbon)", "capital_historical": "Shilb (Silves) / Ushbuna", "capital_modern": "Silves, Portugal", "tier": "Province", "latitude": 37.1887, "longitude": -8.4385, "confidence": "high"},
            {"name": "Kura of Jayyan (Jaen)", "capital_historical": "Jayyan", "capital_modern": "Jaen, Spain", "tier": "Province", "latitude": 37.7796, "longitude": -3.7849, "confidence": "high"}
        ]
    },
    "Kingdom of Ireland": {
        "polity": "Kingdom of Ireland",
        "peak_year_from": 1542,
        "peak_year_to": 1800,
        "peak_area_km2": 84421.0,
        "bbox": [-10.50, 51.40, -5.40, 55.40],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Province of Leinster", "capital_historical": "Dublin", "capital_modern": "Dublin, Ireland", "tier": "Province", "latitude": 53.3498, "longitude": -6.2603, "confidence": "high"},
            {"name": "Province of Munster", "capital_historical": "Cork / Cashel", "capital_modern": "Cork, Ireland", "tier": "Province", "latitude": 51.8985, "longitude": -8.4756, "confidence": "high"},
            {"name": "Province of Connacht", "capital_historical": "Galway / Athlone", "capital_modern": "Galway, Ireland", "tier": "Province", "latitude": 53.2707, "longitude": -9.0568, "confidence": "high"},
            {"name": "Province of Ulster", "capital_historical": "Armagh / Carrickfergus", "capital_modern": "Belfast, United Kingdom", "tier": "Province", "latitude": 54.5973, "longitude": -5.9301, "confidence": "high"},
            {"name": "The Pale (Dublin & Meath)", "capital_historical": "Dublin", "capital_modern": "Dublin, Ireland", "tier": "Crown Territory", "latitude": 53.3498, "longitude": -6.2603, "confidence": "high"}
        ]
    },
    "Great Yuan": {
        "polity": "Great Yuan",
        "peak_year_from": 1271,
        "peak_year_to": 1368,
        "peak_area_km2": 11000000.0,
        "bbox": [73.0, 18.0, 135.0, 55.0],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Central Region (Zhongshu Sheng / Dadu)", "capital_historical": "Khanbaliq (Dadu)", "capital_modern": "Beijing, China", "tier": "Metropolitan Secretariat", "latitude": 39.9042, "longitude": 116.4074, "confidence": "high"},
            {"name": "Jiangzhe Branch Secretariat", "capital_historical": "Hangzhou", "capital_modern": "Hangzhou, China", "tier": "Branch Secretariat", "latitude": 30.2741, "longitude": 120.1551, "confidence": "high"},
            {"name": "Jiangxi Branch Secretariat", "capital_historical": "Nanchang", "capital_modern": "Nanchang, China", "tier": "Branch Secretariat", "latitude": 28.6829, "longitude": 115.8582, "confidence": "high"},
            {"name": "Huguang Branch Secretariat", "capital_historical": "Wuchang (Wuhan)", "capital_modern": "Wuhan, China", "tier": "Branch Secretariat", "latitude": 30.5928, "longitude": 114.3055, "confidence": "high"},
            {"name": "Henan Jiangbei Branch Secretariat", "capital_historical": "Kaifeng", "capital_modern": "Kaifeng, China", "tier": "Branch Secretariat", "latitude": 34.7972, "longitude": 114.3076, "confidence": "high"},
            {"name": "Shaanxi Branch Secretariat", "capital_historical": "Xi'an", "capital_modern": "Xi'an, China", "tier": "Branch Secretariat", "latitude": 34.3416, "longitude": 108.9398, "confidence": "high"},
            {"name": "Sichuan Branch Secretariat", "capital_historical": "Chengdu", "capital_modern": "Chengdu, China", "tier": "Branch Secretariat", "latitude": 30.5728, "longitude": 104.0668, "confidence": "high"},
            {"name": "Yunnan Branch Secretariat", "capital_historical": "Kunming", "capital_modern": "Kunming, China", "tier": "Branch Secretariat", "latitude": 24.8801, "longitude": 102.8329, "confidence": "high"},
            {"name": "Liaoyang Branch Secretariat", "capital_historical": "Liaoyang", "capital_modern": "Liaoyang, China", "tier": "Branch Secretariat", "latitude": 41.2694, "longitude": 123.1733, "confidence": "high"},
            {"name": "Gansu Branch Secretariat", "capital_historical": "Zhangye", "capital_modern": "Zhangye, China", "tier": "Branch Secretariat", "latitude": 38.9259, "longitude": 100.4498, "confidence": "high"},
            {"name": "Lingbei Branch Secretariat (Mongolia)", "capital_historical": "Karakorum", "capital_modern": "Kharkhorin, Mongolia", "tier": "Branch Secretariat", "latitude": 47.1978, "longitude": 102.8428, "confidence": "high"}
        ]
    },
    "Lydia": {
        "polity": "Lydia",
        "peak_year_from": -680,
        "peak_year_to": -546,
        "peak_area_km2": 250000.0,
        "bbox": [26.0, 36.5, 34.0, 42.0],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Lydia Proper (Hermus Valley)", "capital_historical": "Sardis", "capital_modern": "Sart, Turkey", "tier": "Core Kingdom", "latitude": 38.4883, "longitude": 28.0403, "confidence": "high"},
            {"name": "Mysia", "capital_historical": "Pergamon", "capital_modern": "Bergama, Turkey", "tier": "Region", "latitude": 39.1298, "longitude": 27.1812, "confidence": "high"},
            {"name": "Troad (Troas)", "capital_historical": "Ilion (Troy)", "capital_modern": "Canakkale, Turkey", "tier": "Region", "latitude": 39.9574, "longitude": 26.2389, "confidence": "high"},
            {"name": "Ionia (Subjugated Greek Poleis)", "capital_historical": "Ephesus", "capital_modern": "Selcuk, Turkey", "tier": "Vassal Region", "latitude": 37.9497, "longitude": 27.3639, "confidence": "high"},
            {"name": "Phrygia Epictetus", "capital_historical": "Dorylaeum", "capital_modern": "Eskisehir, Turkey", "tier": "Region", "latitude": 39.7767, "longitude": 30.5206, "confidence": "high"},
            {"name": "Bithynia (Western)", "capital_historical": "Nicomedia", "capital_modern": "Izmit, Turkey", "tier": "Tributary Region", "latitude": 40.7654, "longitude": 29.9406, "confidence": "high"},
            {"name": "Caria (Northern)", "capital_historical": "Miletus", "capital_modern": "Didim, Turkey", "tier": "Tributary Region", "latitude": 37.5306, "longitude": 27.2783, "confidence": "high"}
        ]
    },
    "Goths": {
        "polity": "Goths",
        "peak_year_from": 300,
        "peak_year_to": 550,
        "peak_area_km2": 800000.0,
        "bbox": [-9.0, 36.0, 20.0, 48.0],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Visigothic Kingdom (Toledo Core)", "capital_historical": "Toledo", "capital_modern": "Toledo, Spain", "tier": "Kingdom", "latitude": 39.8628, "longitude": -4.0273, "confidence": "high"},
            {"name": "Gallaecia & Asturia", "capital_historical": "Braga", "capital_modern": "Braga, Portugal", "tier": "Duchy", "latitude": 41.5454, "longitude": -8.4265, "confidence": "high"},
            {"name": "Septimania (Gallia Narbonensis)", "capital_historical": "Narbonne", "capital_modern": "Narbonne, France", "tier": "Duchy", "latitude": 43.1843, "longitude": 3.0031, "confidence": "high"},
            {"name": "Baetica", "capital_historical": "Seville", "capital_modern": "Seville, Spain", "tier": "Duchy", "latitude": 37.3891, "longitude": -5.9845, "confidence": "high"},
            {"name": "Ostrogothic Italy (Ravenna)", "capital_historical": "Ravenna", "capital_modern": "Ravenna, Italy", "tier": "Kingdom", "latitude": 44.4184, "longitude": 12.2035, "confidence": "high"},
            {"name": "Ostrogothic Dalmatia", "capital_historical": "Salona (Split)", "capital_modern": "Split, Croatia", "tier": "Province", "latitude": 43.5081, "longitude": 16.4402, "confidence": "high"}
        ]
    },
    "Burgundians": {
        "polity": "Burgundians",
        "peak_year_from": 411,
        "peak_year_to": 534,
        "peak_area_km2": 220000.0,
        "bbox": [4.5, 44.0, 8.5, 48.5],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Kingdom of the Burgundians (Lyon Core)", "capital_historical": "Lugdunum (Lyon)", "capital_modern": "Lyon, France", "tier": "Kingdom", "latitude": 45.7640, "longitude": 4.8357, "confidence": "high"},
            {"name": "Burgundian Sapaudia (Geneva)", "capital_historical": "Geneva", "capital_modern": "Geneva, Switzerland", "tier": "Region", "latitude": 46.2044, "longitude": 6.1432, "confidence": "high"},
            {"name": "Viennensis (Vienne)", "capital_historical": "Vienna (Vienne)", "capital_modern": "Vienne, France", "tier": "County", "latitude": 45.5253, "longitude": 4.8772, "confidence": "high"},
            {"name": "Augustodunensis (Autun)", "capital_historical": "Augustodunum (Autun)", "capital_modern": "Autun, France", "tier": "Civitas", "latitude": 46.9510, "longitude": 4.2989, "confidence": "high"},
            {"name": "Besançon (Sequani)", "capital_historical": "Vesontio (Besançon)", "capital_modern": "Besancon, France", "tier": "Civitas", "latitude": 47.2378, "longitude": 6.0241, "confidence": "high"}
        ]
    },
    "Seventeenth Dynasty of Egypt": {
        "polity": "Seventeenth Dynasty of Egypt",
        "peak_year_from": -1580,
        "peak_year_to": -1550,
        "peak_area_km2": 150000.0,
        "bbox": [30.5, 23.5, 34.0, 27.5],
        "source": "curated_historical_correction",
        "admin_units": [
            {"name": "Theban Nome (Waset Core)", "capital_historical": "Thebes (Waset)", "capital_modern": "Luxor, Egypt", "tier": "Nome", "latitude": 25.6872, "longitude": 32.6396, "confidence": "high"},
            {"name": "Coptite Nome (Gebtu)", "capital_historical": "Coptos", "capital_modern": "Qift, Egypt", "tier": "Nome", "latitude": 25.9984, "longitude": 32.8174, "confidence": "high"},
            {"name": "Thinite Nome (Abydos)", "capital_historical": "This / Abydos", "capital_modern": "Al-Balyana, Egypt", "tier": "Nome", "latitude": 26.1844, "longitude": 31.9189, "confidence": "high"},
            {"name": "Edfu Nome (Behdet)", "capital_historical": "Apollinopolis Magna (Edfu)", "capital_modern": "Edfu, Egypt", "tier": "Nome", "latitude": 24.9786, "longitude": 32.8752, "confidence": "high"},
            {"name": "First Nome (Elephantine / Aswan)", "capital_historical": "Abu (Elephantine)", "capital_modern": "Aswan, Egypt", "tier": "Nome", "latitude": 24.0889, "longitude": 32.8998, "confidence": "high"}
        ]
    }
}

# Duplicate aliases for Cordoba
CORRECTIONS["Emirate of Cordoba"] = CORRECTIONS["Caliphate of Cordoba"]
CORRECTIONS["Umayyad Emirate of Cordoba"] = CORRECTIONS["Caliphate of Cordoba"]

def apply_corrections():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    updated_count = 0
    added_count = 0

    for polity_name, polity_data in CORRECTIONS.items():
        if polity_name in cache:
            cache[polity_name] = polity_data
            updated_count += 1
        else:
            cache[polity_name] = polity_data
            added_count += 1

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"Successfully applied corrections to {CACHE_FILE.name}:")
    print(f"  • Updated existing entries: {updated_count}")
    print(f"  • Added new missing entries: {added_count}")
    print(f"  • Total polities in cache: {len(cache)}")

if __name__ == "__main__":
    apply_corrections()
