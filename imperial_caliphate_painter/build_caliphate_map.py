"""
Imperial Caliphate Regional & Global Province Map Builder (Level 1 Units)
==========================================================================
Compiles the complete global administrative Level-1 map with precise scenario borders:
  - Official CartoDB Dark basemap with project API key: ?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972
  - Complete GMBA Mountain Zones across all of Europe, Africa, Asia, and the Americas
  - Global GMBA Mountain Ridge Lines
  - Global River Networks with Darkened/Highlighted Major Continental Arteries vs Minor Streams
  - Global Deserts & Erg Shields
  - Precise Scenario Geometric Frontier Cutting:
      * Africa: Sahara units (Algeria, Libya, Egypt, Sudan) clipped along Cliopatria historical caliphate line
      * Europe (Danube & Rhine):
          - Germany: Divided along the Rhine (NRW Left Bank) and Danube (Bavaria Raetia/Alpine March)
          - Netherlands: Divided along the Rhine/Waal (Zeeland, Brabant, Limburg, South Gelderland/Zuid-Holland)
          - Austria: Divided along the Danube (Alpine Marches Noricum/Pannonia south vs Waldviertel north)
          - Hungary: Divided along the Danube (Transdanubia / Roman Pannonia west vs Great Alföld plain east)
          - Serbia: Divided along Danube/Sava (Balkan Marches south vs Vojvodina north)
      * Central Asia (Kazakhstan): Southern Syr Darya / Silk Road basin vs northern nomadic Kipchak steppe
      * China (Xinjiang): Western Tarim Basin (Kashgar, Kizilsu, Hotan) Silk Road Marches vs Dzungaria/Taklamakan
      * India: Indus Basin / Thar Desert frontier cutting across Punjab, Rajasthan, Gujarat, and Kashmir
  - Enforced Imperial Painting Rule: ONLY provinces/parts included in the Empire are colorable by click!
  - Color Swatches, Imperial Realm Filters, Global Search, GeoJSON & 2K PNG Export

Usage:
    python build_caliphate_map.py
"""

import os
import glob
import json
import time
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, LineString
from shapely.ops import split, unary_union, linemerge, nearest_points

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, CURRENT_DIR)
PROVINCES_DIR = os.path.join(CURRENT_DIR, "gadm_provinces")
DATA_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "data"))
HTML_OUT = os.path.join(CURRENT_DIR, "caliphate_province_painter.html")
FRONTEND_HTML_OUT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "frontend", "caliphate_province_painter.html"))
GEOJSON_OUT = os.path.join(CURRENT_DIR, "imperial_caliphate_provinces.geojson")
GMBA_GLOBAL_PATH = os.path.join(CURRENT_DIR, "gmba_global_level4.geojson")

CARTO_API_KEY = "cb1_2l84_1_a4a33a1ad51e9fc32f33f972"

REALM_MAP = {
    # Levant & Near East
    "SYR": ("Syria", "Levant & Imperial Seat (Dimashq)", "#0284c7"),
    "LBN": ("Lebanon", "Levant & Imperial Seat (Dimashq)", "#0284c7"),
    "JOR": ("Jordan", "Levant & Imperial Seat (Dimashq)", "#0284c7"),
    "PSE": ("Palestine", "Levant & Imperial Seat (Dimashq)", "#0284c7"),
    "ISR": ("Israel", "Levant & Imperial Seat (Dimashq)", "#0284c7"),
    "IRQ": ("Iraq", "Mesopotamia (al-Iraq: Kufa & Wasit)", "#0369a1"),
    "KWT": ("Kuwait", "Mesopotamia (al-Iraq: Kufa & Wasit)", "#0369a1"),

    # Anatolia & Kostantiniyya
    "TUR": ("Turkey", "Anatolia & al-Qustantiniyya", "#9333ea"),
    "CYP": ("Cyprus", "Anatolia & al-Qustantiniyya", "#a855f7"),

    # Balkans & Danube Marches
    "GRC": ("Greece", "Balkans & Aegean Marches (al-Yunan)", "#6366f1"),
    "BGR": ("Bulgaria", "Danube Marches (Thughur al-Danub)", "#4f46e5"),
    "MKD": ("North Macedonia", "Balkans & Aegean Marches (al-Yunan)", "#6366f1"),
    "ALB": ("Albania", "Illyricum & Adriatic Marches", "#4338ca"),
    "SRB": ("Serbia", "Danube Marches (Thughur al-Danub)", "#4f46e5"),
    "BIH": ("Bosnia and Herzegovina", "Illyricum & Adriatic Marches", "#4338ca"),
    "MNE": ("Montenegro", "Illyricum & Adriatic Marches", "#4338ca"),
    "HRV": ("Croatia", "Illyricum & Adriatic Marches", "#4338ca"),
    "XKO": ("Kosovo", "Illyricum & Adriatic Marches", "#4338ca"),
    "SVN": ("Slovenia", "Illyricum & Adriatic Marches", "#4338ca"),
    "HUN": ("Hungary", "Danube & Pannonian Marches (Thughur al-Danub)", "#4f46e5"),
    "SVK": ("Slovakia", "Danube Frontier Marches", "#4f46e5"),
    "ROU": ("Romania", "Danube Marches & Dobruja (Thughur al-Danub)", "#4f46e5"),

    # Western Europe (al-Andalus, Gaul, Italy)
    "ESP": ("Spain", "al-Andalus (Cordoba, Toledo & Seville)", "#10b981"),
    "PRT": ("Portugal", "al-Andalus (Gharb al-Andalus)", "#059669"),
    "FRA": ("France", "Gaul (Ard Ifranja / Narbonne & Paris)", "#14b8a6"),
    "BEL": ("Belgium", "Rhine Marches (Thughur al-Rin)", "#0d9488"),
    "LUX": ("Luxembourg", "Rhine Marches (Thughur al-Rin)", "#0d9488"),
    "CHE": ("Switzerland", "Alpine Marches (Jibal al-Alp)", "#0f766e"),
    "AUT": ("Austria", "Alpine Marches (Jibal al-Alp)", "#0f766e"),
    "DEU": ("Germany", "Rhine Frontier Marches", "#0f766e"),
    "NLD": ("Netherlands", "Rhine Marches (Thughur al-Rin)", "#0d9488"),
    "ITA": ("Italy", "Italy & Rome (al-Italiyya, Langobardia & Ruma)", "#e11d48"),
    "MLT": ("Malta", "Italy & Rome (al-Italiyya, Langobardia & Ruma)", "#e11d48"),
    "SMR": ("San Marino", "Italy & Rome (al-Italiyya, Langobardia & Ruma)", "#e11d48"),

    # North Africa (al-Maghrib & Misr)
    "EGY": ("Egypt", "Egypt (Misr & al-Iskandariyya)", "#f59e0b"),
    "SDN": ("Sudan", "Upper Nile Marches (Nubian Frontier)", "#d97706"),
    "SOM": ("Somalia", "Horn of Africa & Zeila Ports", "#b45309"),
    "ETH": ("Ethiopia", "Horn of Africa Marches", "#b45309"),
    "LBY": ("Libya", "Barqa & Tripoli Marches", "#d97706"),
    "TUN": ("Tunisia", "Ifriqiya (Qayrawan & Carthage)", "#b45309"),
    "DZA": ("Algeria", "Maghrib al-Awsat (Tahert & Tlemcen)", "#ca8a04"),
    "MAR": ("Morocco", "Maghrib al-Aqsa (Fes & Tangier)", "#eab308"),

    # Arabian Peninsula & Gulf
    "SAU": ("Saudi Arabia", "The Holy Sanctuaries (Hijaz & Najd)", "#16a34a"),
    "YEM": ("Yemen", "Yemen (Sana'a & Aden)", "#15803d"),
    "OMN": ("Oman", "Oman & Indian Ocean Ports", "#166534"),
    "ARE": ("United Arab Emirates", "Gulf Coast Marches", "#166534"),
    "QAT": ("Qatar", "Gulf Coast Marches", "#166534"),
    "BHR": ("Bahrain", "Historical al-Bahrayn", "#166534"),

    # Caucasus Marches
    "AZE": ("Azerbaijan", "Caucasus Marches (al-Qabq & Shirvan)", "#8b5cf6"),
    "ARM": ("Armenia", "Caucasus Marches (al-Qabq & Shirvan)", "#7c3aed"),
    "GEO": ("Georgia", "Caucasus Marches (al-Qabq & Shirvan)", "#6d28d9"),

    # Iranian Plateau & Khurasan
    "IRN": ("Iran", "Persian Plateau (Fars, Rayy & Khurasan)", "#f97316"),
    "AFG": ("Afghanistan", "Eastern Khurasan (Herat, Balkh & Kabul)", "#ea580c"),

    # Central Asia (Transoxiana / Mawara'un-Nahr)
    "TKM": ("Turkmenistan", "Transoxiana (Merv & Karakum)", "#06b6d4"),
    "UZB": ("Uzbekistan", "Transoxiana (Samarkand & Bukhara)", "#0891b2"),
    "TJK": ("Tajikistan", "Sogdia & Pamir Marches", "#0e7490"),
    "KGZ": ("Kyrgyzstan", "Fergana Basin & Tien Shan", "#155e75"),
    "KAZ": ("Kazakhstan", "Syr Darya & Steppe Marches", "#164e63"),

    # South Asia (al-Hind & Indus Basin)
    "PAK": ("Pakistan", "Indus Valley (al-Sind & al-Bunjab: Multan)", "#00f2fe"),
    "IND": ("India", "Northern & Western India (al-Hind Marches)", "#ec4899"),
    "CHN": ("China", "Tarim Basin & Silk Road Marches (Kashgar)", "#fb7185")
}

MAJOR_RIVER_NAMES = {
    "nile", "blue nile", "white nile", "amazon", "danube", "rhine", "indus", "euphrates", "tigris",
    "volga", "po", "rhone", "seine", "loire", "garonne", "elbe", "oder", "vistula", "dnieper", 
    "dnester", "don", "ebro", "tajo", "tagus", "guadalquivir", "guadiana", "douro", "duero",
    "amu darya", "syr darya", "helmand", "tarim", "ganges", "brahmaputra", "yamuna", "indus river",
    "narmada", "godavari", "congo", "niger", "senegal", "zambezi", "yangtze", "yellow river", "huang he",
    "mekong", "irrawaddy", "thames", "severn", "tiber", "adige", "draa", "moulouya", "cheliff", "chélif",
    "scheldt", "meuse", "maritsa", "strymon", "vardar", "morava", "sava", "drina", "ural"
}

def round_coords(geom, precision=4):
    if not geom or "coordinates" not in geom:
        return geom
    def _round(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], precision), round(coords[1], precision)]
        return [_round(c) for c in coords]
    try:
        geom["coordinates"] = _round(geom["coordinates"])
    except Exception:
        pass
    return geom

def safe_geom_to_feature(geom, uid, prov_name, country_name, iso, realm, color, is_caliphate, admin_level):
    if geom.is_empty:
        return None
    if not geom.is_valid:
        geom = geom.buffer(0)
    sim = geom.simplify(0.012, preserve_topology=True)
    m = round_coords(mapping(sim), precision=4)
    return {
        "type": "Feature",
        "geometry": m,
        "properties": {
            "id": uid,
            "name": prov_name,
            "country": country_name,
            "iso": iso,
            "realm": realm,
            "initial_color": color,
            "is_caliphate": is_caliphate,
            "admin_level": admin_level
        }
    }

def split_province_by_river(poly, river_line, keep_side="south", extend_dist=2.0):
    """
    Splits a province polygon cleanly along a river LineString without straight-line cuts.
    keep_side: 'south', 'north', 'west', or 'east'.
    Returns: (imperial_poly, external_poly)
    """
    if not poly.is_valid:
        poly = poly.buffer(0)
    
    coords = list(river_line.coords)
    if len(coords) < 2:
        return None, None
    
    dx0, dy0 = coords[0][0] - coords[1][0], coords[0][1] - coords[1][1]
    l0 = (dx0**2 + dy0**2)**0.5 or 1.0
    ext0 = (coords[0][0] + (dx0/l0)*extend_dist, coords[0][1] + (dy0/l0)*extend_dist)
    
    dx1, dy1 = coords[-1][0] - coords[-2][0], coords[-1][1] - coords[-2][1]
    l1 = (dx1**2 + dy1**2)**0.5 or 1.0
    ext1 = (coords[-1][0] + (dx1/l1)*extend_dist, coords[-1][1] + (dy1/l1)*extend_dist)
    
    cutter = LineString([ext0] + coords + [ext1])
    try:
        res = split(poly, cutter)
    except Exception:
        return None, None
    
    if not hasattr(res, "geoms") or len(res.geoms) <= 1:
        return None, None
    
    side_imperial = []
    side_external = []
    for sub in res.geoms:
        c = sub.centroid
        p1, p2 = nearest_points(c, river_line)
        is_imp = False
        if keep_side == "south":
            is_imp = (c.y <= p2.y)
        elif keep_side == "north":
            is_imp = (c.y > p2.y)
        elif keep_side == "west":
            is_imp = (c.x <= p2.x)
        elif keep_side == "east":
            is_imp = (c.x > p2.x)
        
        if is_imp:
            side_imperial.append(sub)
        else:
            side_external.append(sub)
    
    imp_geom = unary_union(side_imperial) if side_imperial else None
    ext_geom = unary_union(side_external) if side_external else None
    return imp_geom, ext_geom

def build_map():
    t0 = time.time()
    print("=" * 80)
    print("  BUILDING GLOBAL LEVEL-1 PROVINCE PAINTER (EXACT SCENARIO FRONTIER CUTTING)")
    print("=" * 80)

    # 1. Load Cliopatria Peak Umayyad Geometry for Sahara Desert Cutting in Africa
    print("[1/5] Loading Cliopatria Peak Umayyad Geometry (Internal Tool for Sahara Cutting)...")
    clio_raw_path = os.path.join(DATA_DIR, "cliopatria_polities_only.geojson")
    with open(clio_raw_path, "r", encoding="utf-8") as f:
        clio_data = json.load(f)
    clio_feat = clio_data['features'][2710]
    clio_peak = shape(clio_feat['geometry'])
    if not clio_peak.is_valid:
        clio_peak = clio_peak.buffer(0)

    # 2. Extract Authentic Meandering River Lines for Europe, India & Central Asia
    print("[2/5] Extracting authentic river geometries (Danube, Rhine/Waal, Sutlej, Indus, Narmada, Syr Darya, Tarim)...")
    with open(os.path.join(DATA_DIR, "ne_10m_rivers_lake_centerlines.geojson"), "r", encoding="utf-8") as f:
        rdata = json.load(f)

    # A. Continuous Danube River (561 points from Germany through Austria, Hungary & Serbia)
    d_lines = []
    r_lines = []
    sutlej_sub = None
    indus_sub = None
    narmada_sub = None
    syr_darya_sub = None
    yarkant_sub = None
    tarim_sub = None

    for feat in rdata['features']:
        props = feat.get('properties', {})
        rname = str(props.get('name') or props.get('name_en') or '').lower()
        g = shape(feat['geometry'])

        if rname in ['danube', 'donau']:
            if g.geom_type == 'LineString': d_lines.append(g)
            elif g.geom_type == 'MultiLineString': d_lines.extend(g.geoms)

        if any(k in rname for k in ['rhine', 'waal']):
            if g.geom_type == 'LineString': r_lines.append(g)
            elif g.geom_type == 'MultiLineString': r_lines.extend(g.geoms)

        if 'sutlej' in rname and g.geom_type == 'MultiLineString':
            for sub in g.geoms:
                if sub.bounds[0] < 72: sutlej_sub = sub

        if rname == 'indus' and g.geom_type == 'MultiLineString':
            for sub in g.geoms:
                if 75 < sub.centroid.x < 80 and 33 < sub.centroid.y < 36:
                    indus_sub = sub

        if rname == 'narmada' and g.bounds[0] < 74:
            narmada_sub = g.geoms[0] if g.geom_type == 'MultiLineString' else g

        if 'syr' in rname and 'darya' in rname and g.geom_type == 'MultiLineString':
            for sub in g.geoms:
                if sub.length > 10.0: syr_darya_sub = sub

        if rname == 'yarkant':
            yarkant_sub = g.geoms[0] if g.geom_type == 'MultiLineString' else g
        if rname == 'tarim':
            tarim_sub = g.geoms[0] if g.geom_type == 'MultiLineString' else g

    # Build continuous Danube
    main_d = [l for l in d_lines if l.length > 1.0 and l.bounds[1] > 40]
    l_de = [l for l in main_d if l.bounds[0] < 9][0]
    l_at = [l for l in main_d if 12.0 < l.bounds[0] < 13][0]
    l_hu = [l for l in main_d if 17.0 < l.bounds[0] < 18][0]
    full_danube = LineString(list(l_de.coords) + list(reversed(list(l_at.coords)))[1:] + list(l_hu.coords)[1:])

    # Build continuous Rhine & Waal
    r6 = [l for l in r_lines if l.length > 5.0][0]
    w0 = [l for l in r_lines if 4.6 < l.bounds[0] < 5.0 and l.bounds[1] > 51.5][0]
    w1 = [l for l in r_lines if 4.0 <= l.bounds[0] < 4.5 and l.bounds[1] > 51.5][0]
    c_rh = list(r6.coords) + list(w0.coords)[1:] + list(w1.coords)
    rhine_waal = LineString([(c_rh[0][0]+1.0, c_rh[0][1])] + c_rh + [(3.0, c_rh[-1][1])])

    # Build Sutlej River for Punjab
    sutlej_river = sutlej_sub

    # Build Indus River for Jammu & Kashmir
    indus_river = indus_sub

    # Build Narmada River for Gujarat (extended west into Gulf of Khambhat / Arabian Sea)
    c_n = list(narmada_sub.coords)
    narmada_river = LineString([(67.0, 21.70), (71.0, 21.75)] + c_n + [(83.0, c_n[-1][1])])

    # Build Luni River for Rajasthan (authentic winding river line from Rann of Kutch up through Pushkar/Ajmer into Aravallis)
    luni_coords = [
        (70.8, 23.8), (71.15, 24.50), (71.30, 24.65), (71.45, 24.80),
        (71.60, 25.00), (71.75, 25.25), (71.90, 25.50), (72.05, 25.75),
        (72.24, 25.83), (72.45, 25.80), (72.70, 25.82), (72.95, 25.85),
        (73.20, 25.90), (73.45, 25.95), (73.70, 26.05), (73.95, 26.15),
        (74.20, 26.25), (74.45, 26.40), (74.64, 26.45), (75.00, 27.00),
        (75.50, 28.00), (76.00, 29.00), (76.50, 30.50)
    ]
    luni_river = LineString(luni_coords)

    # Build Syr Darya River for Kazakhstan
    syr_darya = syr_darya_sub

    # Build Yarkant & Tarim River system for Xinjiang
    c_y = list(yarkant_sub.coords)
    c_t = list(tarim_sub.coords)
    if c_t[0] != c_y[-1]:
        if c_t[-1] == c_y[-1]: c_t = list(reversed(c_t))
        elif c_t[0] == c_y[0]: c_y = list(reversed(c_y))
    silk_road_river = LineString([(74.0, 42.5), (76.0, 41.5)] + c_y + c_t[1:] + [(88.0, 35.0)])

    # 3. Process all Imperial Caliphate GADM Level-1 Provinces with Scenario Cuttings
    prov_files = glob.glob(os.path.join(PROVINCES_DIR, "*.json")) + glob.glob(os.path.join(PROVINCES_DIR, "*.geojson"))
    print(f"[3/5] Processing and cutting {len(prov_files)} administrative datasets...")

    all_provinces = []
    gadm_countries_lower = set()

    SAHARA_CUT_PROVS = {
        "DZA": ["Adrar", "Tamanghasset", "Illizi", "Tindouf", "Bchar", "Béchar"],
        "LBY": ["AlKufrah", "Murzuq", "Ghat"],
        "EGY": ["AlWadialJadid", "AlBahralAhmar", "Aswan", "Matrouh"],
        "SDN": ["Northern", "RiverNile", "RedSea"]
    }

    for fpath in prov_files:
        fname = os.path.basename(fpath)
        iso = None
        for code in REALM_MAP.keys():
            if f"_{code}_" in fname or f"-{code}-" in fname or fname.startswith(f"gadm41_{code}_"):
                iso = code
                break

        if not iso:
            parts = fname.replace(".", "_").replace("-", "_").split("_")
            for p in parts:
                if len(p) == 3 and p.upper() in REALM_MAP:
                    iso = p.upper()
                    break

        if iso in ["SDN", "SOM", "BGD", "NPL", "BTN", "MMR", "SSD"]:
            continue

        country_name, realm_name, default_color = REALM_MAP.get(iso, ("Empire Territory", "Frontier Realm", "#64748b"))

        try:
            with open(fpath, "r", encoding="utf-8") as jf:
                d = json.load(jf)
        except Exception as e:
            print(f"  [WARN] Skipping {fname}: {e}")
            continue

        raw_feats = d.get("features", [])
        if not raw_feats and d.get("type") == "Feature":
            raw_feats = [d]

        for idx, feat in enumerate(raw_feats):
            props = feat.get("properties", {})
            geom_raw = feat.get("geometry")
            if not geom_raw:
                continue

            prov_name = (
                props.get("NAME_1") or
                props.get("shapeName") or
                props.get("ADM1_EN") or
                props.get("admin1Name") or
                props.get("name") or
                props.get("NAME") or
                props.get("VARNAME_1") or
                f"Province {idx+1}"
            )

            c_name = props.get("COUNTRY") or country_name
            gadm_countries_lower.add(c_name.lower())
            gadm_countries_lower.add((iso or "").lower())

            try:
                poly = shape(geom_raw)
                if not poly.is_valid:
                    poly = poly.buffer(0)
            except Exception:
                continue

            # =========================================================================
            # CASE A: SAHARA BORDER PROVINCES CUTTING (Cliopatria Line - Africa Only)
            # =========================================================================
            if iso in SAHARA_CUT_PROVS and any(sp.lower() in prov_name.lower() for sp in SAHARA_CUT_PROVS[iso]):
                try:
                    in_empire = poly.intersection(clio_peak)
                    out_empire = poly.difference(clio_peak)

                    if not in_empire.is_empty and in_empire.area > 0.05:
                        f_in = safe_geom_to_feature(
                            in_empire,
                            f"{iso}_{prov_name.replace(' ', '_')}_Imperial_Oasis_{idx+1}",
                            f"{prov_name} (Northern Oasis March)",
                            c_name, iso or "EMP", realm_name, default_color, True, "Level-1 Province (Imperial Oasis)"
                        )
                        if f_in: all_provinces.append(f_in)

                    if not out_empire.is_empty and out_empire.area > 0.05:
                        f_out = safe_geom_to_feature(
                            out_empire,
                            f"EXT_{iso}_{prov_name.replace(' ', '_')}_Deep_Sahara_{idx+1}",
                            f"{prov_name} (Deep Sahara Desert - Uninhabited Frontier)",
                            c_name, iso or "EXT", "External World (Sahara Desert)", "#0f172a", False, "Level-1 Province (Uninhabited Sahara)"
                        )
                        if f_out: all_provinces.append(f_out)
                    continue
                except Exception:
                    pass

            # =========================================================================
            # CASE B: GERMANY (DEU) RHINE & DANUBE FRONTIER CUTTING (RIVER LINES)
            # =========================================================================
            if iso == "DEU":
                if "Nordrhein-Westfalen" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, rhine_waal, keep_side="west", extend_dist=1.5)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, "DEU_Nordrhein-Westfalen_West_Rhine",
                            "Nordrhein-Westfalen (Left Bank Rhine / Aachen & Köln)",
                            c_name, "DEU", "Rhine Frontier Marches", "#0f766e", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, "EXT_DEU_Nordrhein-Westfalen_East_Saxon",
                            "Nordrhein-Westfalen (Right Bank / Westphalian Frontier)",
                            c_name, "DEU", "External World (Germany)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                elif "Bayern" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, full_danube, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_s = safe_geom_to_feature(
                            f_imp_geom, "DEU_Bayern_South_Danube_Raetia",
                            "Bayern (South Danube / Roman Raetia & Noricum)",
                            c_name, "DEU", "Alpine Marches (Jibal al-Alp / Raetia)", "#0f766e", True, "Level-1 Province"
                        )
                        f_n = safe_geom_to_feature(
                            f_ext_geom, "EXT_DEU_Bayern_North_Danube_Germanic",
                            "Bayern (North Danube / Germanic Franconia)",
                            c_name, "DEU", "External World (Germany)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_s: all_provinces.append(f_s)
                        if f_n: all_provinces.append(f_n)
                        continue
                elif any(kp in prov_name for kp in ["Rheinland-Pfalz", "Saarland", "Baden-W"]):
                    f_de = safe_geom_to_feature(
                        poly, f"DEU_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "DEU", "Rhine Frontier Marches", "#0f766e", True, "Level-1 Province"
                    )
                    if f_de: all_provinces.append(f_de)
                    continue
                else:
                    f_ext = safe_geom_to_feature(
                        poly, f"EXT_DEU_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "DEU", "External World (Germany)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_ext: all_provinces.append(f_ext)
                    continue

            # =========================================================================
            # CASE C: NETHERLANDS (NLD) RHINE / WAAL FRONTIER CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "NLD":
                gid_1 = props.get("GID_1", "")
                if any(kp in prov_name for kp in ["Gelderland", "Utrecht", "Zuid-Holland"]) or gid_1 == "NLD.14_1" or prov_name == "NA":
                    real_name = "Zuid-Holland" if (gid_1 == "NLD.14_1" or prov_name == "NA") else prov_name
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, rhine_waal, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom and f_imp_geom.area > 0.01:
                        f_s = safe_geom_to_feature(
                            f_imp_geom, f"NLD_{real_name.replace(' ', '_')}_South_Rhine",
                            f"{real_name} (South Rhine / Waal March)",
                            c_name, "NLD", "Rhine Marches (Thughur al-Rin)", "#0d9488", True, "Level-1 Province"
                        )
                        f_n = safe_geom_to_feature(
                            f_ext_geom, f"EXT_NLD_{real_name.replace(' ', '_')}_North_Rhine",
                            f"{real_name} (North Rhine / Frisian March)",
                            c_name, "NLD", "External World (Netherlands)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_s: all_provinces.append(f_s)
                        if f_n: all_provinces.append(f_n)
                        continue
                    elif "Utrecht" in real_name:
                        # Utrecht is north of the Waal/Lower Rhine frontier
                        f_nld_out = safe_geom_to_feature(
                            poly, f"EXT_NLD_{real_name.replace(' ', '_')}_{idx+1}",
                            f"{real_name} (North Rhine / Frisian March)",
                            c_name, "NLD", "External World (Netherlands)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_nld_out: all_provinces.append(f_nld_out)
                        continue
                elif any(kp in prov_name for kp in ["Limburg", "Noord-Brabant", "Zeeland"]):
                    f_nld_in = safe_geom_to_feature(
                        poly, f"NLD_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "NLD", "Rhine Marches (Thughur al-Rin)", "#0d9488", True, "Level-1 Province"
                    )
                    if f_nld_in: all_provinces.append(f_nld_in)
                    continue
                else:
                    f_nld_out = safe_geom_to_feature(
                        poly, f"EXT_NLD_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "NLD", "External World (Netherlands)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_nld_out: all_provinces.append(f_nld_out)
                    continue

            # =========================================================================
            # CASE D: AUSTRIA (AUT) DANUBE FRONTIER CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "AUT":
                if any(kp in prov_name for kp in ["Oberösterreich", "Niederösterreich", "Wien", "Obersterreich", "Niedersterreich"]):
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, full_danube, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_s = safe_geom_to_feature(
                            f_imp_geom, f"AUT_{prov_name.replace(' ', '_')}_South_Danube",
                            f"{prov_name} (South Danube / Roman Noricum & Pannonia)",
                            c_name, "AUT", "Alpine Marches (Jibal al-Alp)", "#0f766e", True, "Level-1 Province"
                        )
                        f_n = safe_geom_to_feature(
                            f_ext_geom, f"EXT_AUT_{prov_name.replace(' ', '_')}_North_Danube",
                            f"{prov_name} (North Danube Frontier - Waldviertel/Mühlviertel)",
                            c_name, "AUT", "External World (Austria)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_s: all_provinces.append(f_s)
                        if f_n: all_provinces.append(f_n)
                        continue
                else:
                    f_aut = safe_geom_to_feature(
                        poly, f"AUT_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "AUT", "Alpine Marches (Jibal al-Alp)", "#0f766e", True, "Level-1 Province"
                    )
                    if f_aut: all_provinces.append(f_aut)
                    continue

            # =========================================================================
            # CASE E: HUNGARY (HUN) DANUBE & PANNONIAN CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "HUN":
                TRANSDANUBIA = ["Gyor", "Győr", "Vas", "Zala", "Somogy", "Baranya", "Tolna", "Fejér", "Fejr", "Veszprém", "Veszprm"]
                DANUBE_CUT_HUN = ["Pest", "Budapest", "Bács-Kiskun", "Bcs-Kiskun", "Komárom", "Komm"]

                if any(kp.lower() in prov_name.lower() for kp in DANUBE_CUT_HUN):
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, full_danube, keep_side="west", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, f"HUN_{prov_name.replace(' ', '_')}_West_Danube",
                            f"{prov_name} (West Danube / Roman Pannonia - Buda)",
                            c_name, "HUN", "Danube & Pannonian Marches", "#4f46e5", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, f"EXT_HUN_{prov_name.replace(' ', '_')}_East_Danube",
                            f"{prov_name} (East Danube / Great Alföld Plain - Pest)",
                            c_name, "HUN", "External World (Hungary)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                    elif any(kp.lower() in prov_name.lower() for kp in ["Komárom", "Komm"]):
                        # South of Danube: Roman Pannonia
                        f_hun_in = safe_geom_to_feature(
                            poly, f"HUN_{prov_name.replace(' ', '_')}_{idx+1}",
                            f"{prov_name} (Transdanubia / Pannonia)",
                            c_name, "HUN", "Danube & Pannonian Marches", "#4f46e5", True, "Level-1 Province"
                        )
                        if f_hun_in: all_provinces.append(f_hun_in)
                        continue
                elif any(kp.lower() in prov_name.lower() for kp in TRANSDANUBIA):
                    # West of Danube: Roman Pannonia in Empire
                    f_hun_in = safe_geom_to_feature(
                        poly, f"HUN_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Transdanubia / Pannonia)",
                        c_name, "HUN", "Danube & Pannonian Marches", "#4f46e5", True, "Level-1 Province"
                    )
                    if f_hun_in: all_provinces.append(f_hun_in)
                    continue
                else:
                    # East of Danube (Alföld / Great Hungarian Plain) outside Empire
                    f_hun_out = safe_geom_to_feature(
                        poly, f"EXT_HUN_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Alföld / Great Plain Frontier)",
                        c_name, "HUN", "External World (Hungary)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_hun_out: all_provinces.append(f_hun_out)
                    continue

            # =========================================================================
            # CASE F: SERBIA (SRB) DANUBE / SAVA FRONTIER CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "SRB":
                VOJVODINA = ["Severnobacki", "Zapadnobacki", "Juznobacki", "Severnobanatski", "Srednjobanatski", "Juznobanatski"]
                if "Beograd" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, full_danube, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_s = safe_geom_to_feature(
                            f_imp_geom, "SRB_Beograd_South_Danube",
                            "Beograd (South Danube / Kalemegdan Citadel & Old City)",
                            c_name, "SRB", "Danube Marches (Thughur al-Danub)", "#4f46e5", True, "Level-1 Province"
                        )
                        f_n = safe_geom_to_feature(
                            f_ext_geom, "EXT_SRB_Beograd_North_Danube",
                            "Beograd (North Danube / Banat Frontier)",
                            c_name, "SRB", "External World (Serbia)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_s: all_provinces.append(f_s)
                        if f_n: all_provinces.append(f_n)
                        continue
                elif any(v in prov_name for v in VOJVODINA):
                    f_srb_out = safe_geom_to_feature(
                        poly, f"EXT_SRB_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Vojvodina / North Danube Frontier)",
                        c_name, "SRB", "External World (Serbia)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_srb_out: all_provinces.append(f_srb_out)
                    continue
                else:
                    f_srb_in = safe_geom_to_feature(
                        poly, f"SRB_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "SRB", "Danube Marches (Thughur al-Danub)", "#4f46e5", True, "Level-1 Province"
                    )
                    if f_srb_in: all_provinces.append(f_srb_in)
                    continue

            # =========================================================================
            # CASE G: ROMANIA (ROU) - DANUBE MARCHES & DOBRUJA
            # =========================================================================
            if iso == "ROU":
                DANUBE_ROU = [
                    "Constanta", "Constanța", "Tulcea", "Calarasi", "Călărași",
                    "Giurgiu", "Teleorman", "Olt", "Dolj", "Mehedinti", "Mehedinți",
                    "Caras-Severin", "Caraș-Severin", "Ialomita", "Ialomița", "Braila", "Brăila",
                    "Galati", "Galați", "Bucharest", "București", "Ilfov"
                ]
                if any(kp.lower() in prov_name.lower() for kp in DANUBE_ROU):
                    f_rou = safe_geom_to_feature(
                        poly, f"ROU_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Danube Marches & Dobruja)",
                        c_name, "ROU", "Danube Marches & Dobruja (Thughur al-Danub)", "#4f46e5", True, "Level-1 Province"
                    )
                    if f_rou: all_provinces.append(f_rou)
                    continue
                else:
                    f_rou_ext = safe_geom_to_feature(
                        poly, f"EXT_ROU_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Carpathian & Northern Frontier)",
                        c_name, "ROU", "External World (Romania)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_rou_ext: all_provinces.append(f_rou_ext)
                    continue

            # =========================================================================
            # CASE G: CENTRAL ASIA - KAZAKHSTAN (KAZ) SYR DARYA CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "KAZ":
                if "Qyzylorda" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, syr_darya, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_s = safe_geom_to_feature(
                            f_imp_geom, "KAZ_Qyzylorda_South_Syr_Darya",
                            "Qyzylorda (Syr Darya Oasis Basin / Otrar March)",
                            c_name, "KAZ", "Transoxiana (Merv & Karakum)", "#06b6d4", True, "Level-1 Province"
                        )
                        f_n = safe_geom_to_feature(
                            f_ext_geom, "EXT_KAZ_Qyzylorda_North_Steppe",
                            "Qyzylorda (Kipchak Steppe Frontier)",
                            c_name, "KAZ", "External World (Kazakhstan)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_s: all_provinces.append(f_s)
                        if f_n: all_provinces.append(f_n)
                        continue
                elif any(kp in prov_name for kp in ["SouthKazakhstan", "Zhambyl", "Almaty"]):
                    f_kaz_in = safe_geom_to_feature(
                        poly, f"KAZ_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Syr Darya & Talas Oasis March)",
                        c_name, "KAZ", "Transoxiana (Merv & Karakum)", "#06b6d4", True, "Level-1 Province"
                    )
                    if f_kaz_in: all_provinces.append(f_kaz_in)
                    continue
                else:
                    f_kaz_out = safe_geom_to_feature(
                        poly, f"EXT_KAZ_{prov_name.replace(' ', '_')}_{idx+1}",
                        f"{prov_name} (Nomadic Kipchak Steppe)",
                        c_name, "KAZ", "External World (Kazakhstan)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_kaz_out: all_provinces.append(f_kaz_out)
                    continue

            # =========================================================================
            # CASE H: CHINA (CHN) TARIM BASIN / SILK ROAD CUTTING (RIVER LINE)
            # =========================================================================
            if iso == "CHN":
                if "xinjiang" in prov_name.lower():
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, silk_road_river, keep_side="west", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_tarim = safe_geom_to_feature(
                            f_imp_geom, f"CHN_Xinjiang_Tarim_Kashgar_{idx+1}",
                            "Xinjiang (Western Tarim Silk Road Marches: Kashgar & Hotan)",
                            c_name, "CHN", "Tarim Basin & Silk Road Marches (Kashgar)", "#fb7185", True, "Level-1 Province"
                        )
                        f_dzungaria = safe_geom_to_feature(
                            f_ext_geom, f"EXT_CHN_Xinjiang_Dzungaria_{idx+1}",
                            "Xinjiang (Dzungaria & Taklamakan Desert Frontier)",
                            c_name, "CHN", "External World (China)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_tarim: all_provinces.append(f_tarim)
                        if f_dzungaria: all_provinces.append(f_dzungaria)
                        continue
                else:
                    f_chn = safe_geom_to_feature(
                        poly, f"EXT_CHN_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "CHN", "External World (China)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_chn: all_provinces.append(f_chn)
                    continue

            # =========================================================================
            # CASE I: PAKISTAN (PAK) - AUTHENTIC PROVINCIAL IDENTIFICATION
            # =========================================================================
            if iso == "PAK":
                gid_1 = props.get("GID_1", "")
                c_pt = poly.centroid
                pak_name = prov_name
                if gid_1 == "PAK.1_1":
                    pak_name = "Azad Kashmir (Himalayan Marches)"
                elif gid_1 == "PAK.2_1":
                    pak_name = "Balochistan (Makran & Turan)"
                elif gid_1 == "PAK.3_1":
                    pak_name = "Gilgit-Baltistan (Karakoram Marches)"
                elif gid_1 == "PAK.4_1" or poly.area < 0.2:
                    pak_name = "Islamabad Capital Territory"
                elif gid_1 == "PAK.5_1":
                    pak_name = "Khyber Pakhtunkhwa (Peshawar & Gandhara)"
                elif gid_1 == "PAK.6_1":
                    pak_name = "Punjab (al-Multan & Lahore)"
                elif gid_1 == "PAK.7_1":
                    pak_name = "Sindh (al-Mansurah & Daybul)"
                elif (c_pt.x < 68 and c_pt.y < 30):
                    pak_name = "Balochistan (Makran & Turan)"
                elif (c_pt.y > 35):
                    pak_name = "Gilgit-Baltistan (Karakoram Marches)"
                elif (67 < c_pt.x < 71 and 24 < c_pt.y < 28.5):
                    pak_name = "Sindh (al-Mansurah & Daybul)"
                elif (70 < c_pt.x < 75 and 28 < c_pt.y < 33):
                    pak_name = "Punjab (al-Multan & Lahore)"
                
                clean_pname = pak_name.replace(" ", "_").replace("(", "").replace(")", "").replace("&", "and")
                f_pak = safe_geom_to_feature(
                    poly, f"PAK_{clean_pname}_{idx+1}",
                    pak_name, c_name, "PAK", "Indus Valley & al-Sind (Mansura & Multan)", "#ec4899", True, "Level-1 Province"
                )
                if f_pak: all_provinces.append(f_pak)
                continue

            # =========================================================================
            # CASE J: INDIA (IND) INDUS, SUTLEJ, NARMADA & LUNI RIVER CUTTING
            # =========================================================================
            if iso == "IND":
                if "Punjab" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, sutlej_river, keep_side="north", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, "IND_Punjab_West_Sutlej",
                            "Punjab (West Sutlej Marches: Amritsar & Jalandhar Doab)",
                            c_name, "IND", "Northern & Western India (al-Hind Marches)", "#ec4899", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, "EXT_IND_Punjab_East_Sutlej",
                            "Punjab (East Sutlej Frontier: Ludhiana & Patiala)",
                            c_name, "IND", "External World (India)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                elif "Rajasthan" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, luni_river, keep_side="west", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, "IND_Rajasthan_West_Thar",
                            "Rajasthan (West Thar Desert Marches: Jaisalmer & Barmer)",
                            c_name, "IND", "Northern & Western India (al-Hind Marches)", "#ec4899", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, "EXT_IND_Rajasthan_East_Rajput",
                            "Rajasthan (Eastern Rajputana Heartlands - Mewar & Jaipur)",
                            c_name, "IND", "External World (India)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                elif "Gujarat" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, narmada_river, keep_side="north", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, "IND_Gujarat_Kutch_Saurashtra",
                            "Gujarat (Kutch & Saurashtra Coastal Marches)",
                            c_name, "IND", "Northern & Western India (al-Hind Marches)", "#ec4899", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, "EXT_IND_Gujarat_East_Mainland",
                            "Gujarat (Southern Mainland Gujarat - Surat & Dangs)",
                            c_name, "IND", "External World (India)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                elif "Jammu" in prov_name or "Kashmir" in prov_name:
                    f_imp_geom, f_ext_geom = split_province_by_river(poly, indus_river, keep_side="south", extend_dist=2.0)
                    if f_imp_geom and f_ext_geom:
                        f_w = safe_geom_to_feature(
                            f_imp_geom, "IND_Jammu_Kashmir_Indus",
                            "Jammu and Kashmir (Kashmir Valley & Indus Basin)",
                            c_name, "IND", "Northern & Western India (al-Hind Marches)", "#ec4899", True, "Level-1 Province"
                        )
                        f_e = safe_geom_to_feature(
                            f_ext_geom, "EXT_IND_Ladakh_Himalaya",
                            "Ladakh (High Himalayan & Tibetan Frontier)",
                            c_name, "IND", "External World (India)", "#1e293b", False, "Level-1 Province"
                        )
                        if f_w: all_provinces.append(f_w)
                        if f_e: all_provinces.append(f_e)
                        continue
                else:
                    f_ind = safe_geom_to_feature(
                        poly, f"EXT_IND_{prov_name.replace(' ', '_')}_{idx+1}",
                        prov_name, c_name, "IND", "External World (India)", "#1e293b", False, "Level-1 Province"
                    )
                    if f_ind: all_provinces.append(f_ind)
                    continue

            # =========================================================================
            # STANDARD CALIPHATE LEVEL-1 PROVINCE
            # =========================================================================
            clean_name = prov_name.replace(" ", "_").replace("'", "").replace("/", "_")
            uid = f"{iso or 'EMP'}_{clean_name}_{idx+1}"
            f_std = safe_geom_to_feature(
                poly, uid, prov_name, c_name, iso or "UNK", realm_name, default_color, True, "Level-1 Province"
            )
            if f_std: all_provinces.append(f_std)

    caliphate_units = [f for f in all_provinces if f['properties']['is_caliphate']]
    print(f"  -> Generated {len(caliphate_units)} Imperial Caliphate scenario units (Colorable).")

    # 4. Ingest the REST OF THE WORLD from Natural Earth 10m Admin-1
    ne_admin1_path = os.path.join(DATA_DIR, "ne_10m_admin_1_provinces.geojson")
    external_count = 0
    if os.path.exists(ne_admin1_path):
        print("[4/5] Ingesting rest of the world Level-1 provinces from Natural Earth...")
        with open(ne_admin1_path, "r", encoding="utf-8") as nef:
            ne_data = json.load(nef)

        for idx, feat in enumerate(ne_data.get("features", [])):
            p = feat.get("properties", {})
            admin_country = p.get("admin") or "External Territory"
            admin_country_lower = admin_country.lower()

            if any(gc and (gc in admin_country_lower or admin_country_lower in gc) for gc in gadm_countries_lower):
                continue

            if any(rc in admin_country_lower for rc in ["bangladesh", "sudan", "somali", "nepal", "bhutan", "myanmar", "burma"]):
                continue

            prov_name = p.get("name") or p.get("name_alt") or f"Region {idx+1}"
            iso_a2 = p.get("iso_a2") or "EXT"
            clean_name = prov_name.replace(" ", "_").replace("'", "").replace("/", "_")
            uid = f"EXT_{iso_a2}_{clean_name}_{idx+1}"

            try:
                poly = shape(feat["geometry"])
                if not poly.is_valid:
                    poly = poly.buffer(0)
                f_ext = safe_geom_to_feature(
                    poly, uid, prov_name, admin_country, iso_a2,
                    f"External World ({admin_country})", "#1e293b", False, "Level-1 Province"
                )
                if f_ext:
                    all_provinces.append(f_ext)
                    external_count += 1
            except Exception:
                pass

    print(f"  -> Added {external_count} Level-1 provinces for the rest of the world.")
    print(f"  -> Total Global Units: {len(all_provinces)}.")

    # Apply user's painted base (slices / blanks / paint) + Consolidated Eastern Frontier
    try:
        from eastern_expansion import build_from_painted_base
        all_provinces = build_from_painted_base(all_provinces)
    except Exception as e:
        print(f"  [WARN] Eastern expansion patch failed: {e}")

    # Save compiled GeoJSON
    with open(GEOJSON_OUT, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": all_provinces}, f)

    # 5. Extract GMBA Mountains, Rivers & Deserts
    print("[5/5] Extracting GMBA Mountains, Rivers & Deserts...")
    mtn_zones = []
    if os.path.exists(GMBA_GLOBAL_PATH):
        with open(GMBA_GLOBAL_PATH, "r", encoding="utf-8") as f:
            gmba_global = json.load(f)
            mtn_zones = gmba_global.get("features", [])

    mtn_lines_path = os.path.join(DATA_DIR, "gmba_defense_mountain_lines.geojson")
    mtn_lines = []
    if os.path.exists(mtn_lines_path):
        with open(mtn_lines_path, "r", encoding="utf-8") as f:
            gmba_l_raw = json.load(f)
        for feat in gmba_l_raw.get("features", []):
            try:
                s = shape(feat["geometry"])
                sim = s.simplify(0.015, preserve_topology=True)
                if not sim.is_empty:
                    mtn_lines.append({
                        "type": "Feature",
                        "geometry": round_coords(mapping(sim), 3),
                        "properties": {
                            "name": feat["properties"].get("Name") or feat["properties"].get("MapName") or "Mountain Ridge"
                        }
                    })
            except Exception:
                pass

    # Rivers & Deserts
    river_paths = [
        os.path.join(DATA_DIR, "ne_10m_rivers_lake_centerlines.geojson"),
        os.path.join(DATA_DIR, "ne_10m_rivers_europe.geojson")
    ]
    rivers = []
    seen_rivers = set()
    major_count = 0
    minor_count = 0

    for rp in river_paths:
        if os.path.exists(rp):
            with open(rp, "r", encoding="utf-8") as f:
                rdata = json.load(f)
            for feat in rdata.get("features", []):
                props = feat.get("properties", {})
                rname = props.get("name") or props.get("NAME") or props.get("name_en") or "Waterway"
                srank = props.get("scalerank")

                is_major = False
                try:
                    if srank is not None and float(srank) <= 4.0:
                        is_major = True
                except Exception:
                    pass

                if not is_major:
                    rname_lower = rname.lower()
                    if any(mr in rname_lower for mr in MAJOR_RIVER_NAMES):
                        is_major = True

                geom = feat.get("geometry")
                if not geom:
                    continue

                try:
                    s = shape(geom)
                    bounds = (round(s.bounds[0], 2), round(s.bounds[1], 2), round(s.bounds[2], 2), round(s.bounds[3], 2))
                    key = (rname, bounds)
                    if key in seen_rivers:
                        continue
                    seen_rivers.add(key)
                    sim = s.simplify(0.015, preserve_topology=True)
                    if not sim.is_empty:
                        rivers.append({
                            "type": "Feature",
                            "geometry": round_coords(mapping(sim), 3),
                            "properties": {
                                "name": rname,
                                "is_major": is_major
                            }
                        })
                        if is_major: major_count += 1
                        else: minor_count += 1
                except Exception:
                    pass

    reg_path = os.path.join(DATA_DIR, "ne_10m_geography_regions_polys.geojson")
    deserts = []
    if os.path.exists(reg_path):
        with open(reg_path, "r", encoding="utf-8") as f:
            reg_data = json.load(f)
        for feat in reg_data.get("features", []):
            p = feat.get("properties", {})
            mname = p.get("NAME") or ""
            ftype = p.get("FEATURECLA") or ""
            if ftype == "Desert" or "desert" in mname.lower() or "erg" in mname.lower() or "hamada" in mname.lower():
                try:
                    s = shape(feat["geometry"])
                    sim = s.simplify(0.02, preserve_topology=True)
                    if not sim.is_empty:
                        deserts.append({
                            "type": "Feature",
                            "geometry": round_coords(mapping(sim), 3),
                            "properties": {"name": mname, "type": "Desert"}
                        })
                except Exception:
                    pass

    # Mountain range name labels (one per GMBA range, placed at pole of inaccessibility)
    from shapely.ops import polylabel
    mtn_by_name = {}
    for feat in mtn_zones:
        try:
            p = feat.get("properties", {})
            nm = p.get("name") or p.get("Name") or ""
            try:
                nm = nm.encode("latin-1").decode("utf-8")
            except Exception:
                pass
            if not nm:
                continue
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            rec = mtn_by_name.setdefault(nm, {"area": 0.0, "best": None, "high": p.get("high")})
            rec["area"] += g.area
            for part in getattr(g, "geoms", [g]):
                if rec["best"] is None or part.area > rec["best"].area:
                    rec["best"] = part
            if p.get("high") and (rec["high"] or 0) < p.get("high"):
                rec["high"] = p.get("high")
        except Exception:
            pass
    mtn_labels = []
    for nm, rec in mtn_by_name.items():
        try:
            pt = polylabel(rec["best"], tolerance=0.05)
        except Exception:
            pt = rec["best"].representative_point()
        mtn_labels.append({"n": nm, "lat": round(pt.y, 3), "lng": round(pt.x, 3),
                           "a": round(rec["area"], 2), "h": int(rec["high"] or 0)})
    mtn_labels.sort(key=lambda r: -r["a"])
    print(f"  -> {len(mtn_labels)} mountain range name labels")

    # Compile HTML Application
    print("[5/5] Compiling HTML Painter (Cliopatria UI hidden, only imperial units colorable)...")
    provinces_json_str = json.dumps({"type": "FeatureCollection", "features": all_provinces})
    mtn_zones_str = json.dumps({"type": "FeatureCollection", "features": mtn_zones})
    mtn_lines_str = json.dumps({"type": "FeatureCollection", "features": mtn_lines})
    rivers_str = json.dumps({"type": "FeatureCollection", "features": rivers})
    deserts_str = json.dumps({"type": "FeatureCollection", "features": deserts})
    mtn_labels_str = json.dumps(mtn_labels, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🗺️ Global & Imperial Caliphate Province Painter (Colorable Imperial Units)</title>
    
    <!-- Google Fonts & Leaflet -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/@turf/turf@6/turf.min.js"></script>

    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
        body {{ background-color: #070a13; color: #f8fafc; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

        /* Top Header */
        header {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #334155;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
        }}
        .header-title h1 {{ font-size: 16.5px; font-weight: 700; color: #38bdf8; letter-spacing: -0.01em; }}
        .header-title p {{ font-size: 11px; color: #94a3b8; }}

        /* Layer Toggles */
        .toggle-group {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: rgba(15, 23, 42, 0.85);
            padding: 5px 14px;
            border-radius: 8px;
            border: 1px solid #334155;
        }}
        .toggle-label {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            user-select: none;
        }}

        .legend-pill {{
            font-size: 10.5px;
            padding: 4px 9px;
            background: rgba(2, 132, 199, 0.18);
            border: 1px solid rgba(2, 132, 199, 0.5);
            border-radius: 6px;
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .legend-pill strong {{ color: #ffffff; }}

        #container {{ display: flex; flex: 1; position: relative; }}
        #map {{ width: 100%; height: 100%; background: #070a13; }}

        /* Sidebar Control Panel */
        .controls-panel {{
            position: absolute;
            top: 16px;
            right: 16px;
            width: 380px;
            max-height: calc(100vh - 100px);
            background: rgba(15, 23, 42, 0.95);
            backdrop-filter: blur(14px);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px;
            z-index: 1000;
            box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6);
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow-y: auto;
        }}

        .section-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #94a3b8;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        /* Color Palette Grid */
        .palette-grid {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 6px;
        }}
        .color-swatch {{
            height: 28px;
            border-radius: 5px;
            cursor: pointer;
            border: 2px solid transparent;
            transition: all 0.15s ease;
        }}
        .color-swatch:hover {{ transform: scale(1.1); box-shadow: 0 0 10px rgba(255, 255, 255, 0.4); }}
        .color-swatch.active {{
            border-color: #ffffff;
            box-shadow: 0 0 12px rgba(255, 255, 255, 0.9);
            transform: scale(1.12);
        }}

        /* Search Bar & Filters */
        .search-bar {{
            width: 100%;
            padding: 8px 12px;
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 6px;
            color: #ffffff;
            font-size: 12px;
            outline: none;
            transition: border-color 0.2s;
        }}
        .search-bar:focus {{ border-color: #38bdf8; box-shadow: 0 0 8px rgba(56, 189, 248, 0.25); }}

        .filter-select {{
            width: 100%;
            padding: 8px 10px;
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 6px;
            color: #cbd5e1;
            font-size: 12px;
            outline: none;
            cursor: pointer;
        }}
        .filter-select option {{ background: #0f172a; color: #ffffff; }}

        /* Inspector Card */
        .info-box {{
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .info-title {{ font-size: 13px; font-weight: 700; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 4px; }}
        .info-row {{ display: flex; justify-content: space-between; font-size: 11.5px; }}
        .info-label {{ color: #94a3b8; }}
        .info-val {{ color: #f1f5f9; font-weight: 600; text-align: right; max-width: 220px; }}

        /* Action Buttons */
        .btn-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .btn {{
            padding: 8px 10px;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.2s;
            text-align: center;
        }}
        .btn-primary {{ background: #0284c7; color: #ffffff; }}
        .btn-primary:hover {{ background: #0369a1; }}
        .btn-success {{ background: #10b981; color: #ffffff; }}
        .btn-success:hover {{ background: #059669; }}
        .btn-gold {{ background: #d97706; color: #ffffff; }}
        .btn-gold:hover {{ background: #b45309; }}
        .btn-dark {{ background: #334155; color: #cbd5e1; }}
        .btn-dark:hover {{ background: #475569; }}

        /* Leaflet Panes Z-Index Order */
        .leaflet-pane.leaflet-unitsPane-pane {{ z-index: 350; }}
        .leaflet-pane.leaflet-desertsPane-pane {{ z-index: 410; }}
        .leaflet-pane.leaflet-mountainsPane-pane {{ z-index: 430; }}
        .leaflet-pane.leaflet-mountainLinesPane-pane {{ z-index: 440; }}
        .leaflet-pane.leaflet-riversPane-pane {{ z-index: 450; }}
        .leaflet-pane.leaflet-mtnLabelsPane-pane {{ z-index: 470; pointer-events: none !important; }}
        .leaflet-pane.leaflet-mtnLabelsPane-pane * {{ pointer-events: none !important; }}
        .mtn-label {{ background: transparent; border: none; }}
        .mtn-label-inner {{
            transform: translate(-50%, -50%);
            display: inline-block;
            white-space: nowrap;
            font-family: 'Space Grotesk', 'Inter', sans-serif;
            font-weight: 700;
            font-style: italic;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #fde68a;
            text-shadow: 0 0 3px #000, 0 0 6px #000, 1px 1px 2px #000;
        }}
        .mtn-label-inner .mtn-elev {{
            display: block;
            text-align: center;
            font-size: 0.75em;
            font-style: normal;
            letter-spacing: 0.02em;
            color: #fbbf24;
            opacity: 0.9;
        }}

        /* Terrain overlay panes pointer events */
        .leaflet-pane.leaflet-mountainsPane-pane,
        .leaflet-pane.leaflet-mountainLinesPane-pane,
        .leaflet-pane.leaflet-desertsPane-pane {{
            pointer-events: none !important;
        }}
        .leaflet-pane.leaflet-mountainsPane-pane *,
        .leaflet-pane.leaflet-mountainLinesPane-pane *,
        .leaflet-pane.leaflet-desertsPane-pane * {{
            pointer-events: none !important;
        }}
        /* Rivers layer is interactive for hover inspection & tactics */
        .leaflet-pane.leaflet-riversPane-pane {{
            pointer-events: auto !important;
        }}
        .leaflet-pane.leaflet-riversPane-pane path {{
            pointer-events: auto !important;
            cursor: pointer !important;
        }}

        /* River Custom Tooltip */
        .river-tooltip-custom {{
            background: rgba(15, 23, 42, 0.95) !important;
            border: 1px solid #0284c7 !important;
            border-radius: 6px !important;
            color: #f8fafc !important;
            box-shadow: 0 4px 14px rgba(0,0,0,0.6) !important;
        }}

        /* Frontier Slicer Card & Cut Banner */
        .slicer-card {{
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .badge-idle {{
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            background: #334155;
            color: #94a3b8;
            font-weight: 600;
        }}
        .badge-active {{
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
            border: 1px solid #f59e0b;
            font-weight: 700;
            animation: slicerPulse 1.5s infinite;
        }}
        @keyframes slicerPulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        .btn-warning {{ background: #f59e0b; color: #000000; font-weight: 700; }}
        .btn-warning:hover {{ background: #d97706; color: #ffffff; }}
        .btn-warning.active {{
            background: #ef4444 !important;
            color: #ffffff !important;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.6);
        }}

        .cut-banner {{
            position: absolute;
            top: 16px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1100;
            background: rgba(15, 23, 42, 0.96);
            border: 1px solid #f59e0b;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.75);
            border-radius: 30px;
            padding: 7px 18px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 12px;
            color: #fbbf24;
            backdrop-filter: blur(8px);
        }}

        /* Slice Decision Modal */
        .slice-modal-backdrop {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.78);
            backdrop-filter: blur(6px);
            z-index: 2000;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .slice-modal-card {{
            background: #0f172a;
            border: 1px solid #38bdf8;
            border-radius: 12px;
            max-width: 560px;
            width: 100%;
            padding: 22px;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.85);
            display: flex;
            flex-direction: column;
            gap: 14px;
            animation: modalFadeIn 0.2s ease-out;
        }}
        @keyframes modalFadeIn {{
            from {{ opacity: 0; transform: scale(0.95); }}
            to {{ opacity: 1; transform: scale(1); }}
        }}
        .slice-modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 10px;
        }}
        .slice-modal-header h3 {{
            font-size: 16px;
            font-weight: 700;
            color: #f8fafc;
        }}
        .close-modal-btn {{
            background: transparent;
            border: none;
            color: #94a3b8;
            font-size: 18px;
            cursor: pointer;
            padding: 0 4px;
        }}
        .close-modal-btn:hover {{ color: #ffffff; }}

        .slice-choices-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin: 4px 0;
        }}
        .slice-choice-card {{
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }}
        .portion-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 6px;
        }}
        .portion-details {{
            font-size: 11.5px;
            color: #cbd5e1;
        }}

        .slice-actions-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .slice-action-btn {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            background: rgba(30, 41, 59, 0.9);
            border: 1px solid #475569;
            border-radius: 8px;
            color: #f8fafc;
            text-align: left;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .slice-action-btn:hover {{
            background: #1e293b;
            border-color: #38bdf8;
            transform: translateY(-1px);
        }}
        .slice-action-btn .action-icon {{
            font-size: 20px;
            flex-shrink: 0;
        }}
        .slice-action-btn strong {{
            display: block;
            font-size: 12.5px;
            color: #ffffff;
            margin-bottom: 2px;
        }}
        .slice-action-btn .action-sub {{
            font-size: 10.5px;
            color: #94a3b8;
            line-height: 1.3;
        }}
        .btn-action-a:hover {{ border-color: #0284c7; box-shadow: 0 0 12px rgba(2, 132, 199, 0.3); }}
        .btn-action-b:hover {{ border-color: #e11d48; box-shadow: 0 0 12px rgba(225, 29, 72, 0.3); }}
        .btn-action-both:hover {{ border-color: #10b981; box-shadow: 0 0 12px rgba(16, 185, 129, 0.3); }}
        .btn-action-blank-both:hover {{ border-color: #64748b; }}

        /* Toast notification */
        .toast-notify {{
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.96);
            border: 1px solid #10b981;
            color: #f8fafc;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 12.5px;
            font-weight: 600;
            box-shadow: 0 6px 20px rgba(0,0,0,0.7);
            z-index: 3000;
            display: none;
            animation: toastIn 0.2s ease-out;
        }}
        @keyframes toastIn {{
            from {{ opacity: 0; transform: translate(-50%, 10px); }}
            to {{ opacity: 1; transform: translate(-50%, 0); }}
        }}

        /* Units pane accepts pointer events */
        .leaflet-pane.leaflet-unitsPane-pane {{
            pointer-events: auto !important;
        }}
        
        /* Only Imperial Units have pointer cursor; uncolorable external units have default cursor */
        .leaflet-pane.leaflet-unitsPane-pane path.caliphate-unit {{
            cursor: pointer !important;
        }}
        .leaflet-pane.leaflet-unitsPane-pane path.external-unit {{
            cursor: default !important;
        }}
    </style>
</head>
<body>

<header>
    <div class="header-title">
        <h1>🗺️ Global & Imperial Caliphate Province Painter</h1>
        <p>Scenario Frontier Cutting (Only Imperial Units Colorable) | {len(all_provinces)} Units</p>
    </div>

    <!-- Layer Toggles -->
    <div class="toggle-group">
        <label class="toggle-label" style="color:#38bdf8;" title="Toggle Global Rivers (Darkened Major Continental Arteries + Minor Streams)">
            <input type="checkbox" id="chk-rivers" checked> 🌊 Rivers
        </label>
        <label class="toggle-label" style="color:#f59e0b;" title="Toggle GMBA Mountain Zones (Europe, Africa, Asia, Americas)">
            <input type="checkbox" id="chk-mtn-zones" checked> ⛰️ Mountains
        </label>
        <label class="toggle-label" style="color:#fbbf24;" title="Toggle Mountain Ridge Crest Lines">
            <input type="checkbox" id="chk-mtn-lines" checked> 🏔️ Ridges
        </label>
        <label class="toggle-label" style="color:#fde68a;" title="Show Mountain Range Names">
            <input type="checkbox" id="chk-mtn-names" checked> 🏷️ Range Names
        </label>
        <label class="toggle-label" style="color:#d97706;" title="Toggle Desert Shields & Dunes">
            <input type="checkbox" id="chk-deserts" checked> 🏜️ Deserts
        </label>
    </div>

    <div class="legend-pill">
        <span>🎨 <strong style="color:#10b981;">Colorable:</strong> Imperial Provinces Only</span>
        <span>|</span>
        <span>🌊 <strong>Dark Blue:</strong> Major Rivers</span>
        <span>|</span>
        <span>✂️ <strong>Cut:</strong> Danube, Rhine, Sahara, Silk Road & Indus</span>
    </div>
</header>

<div id="container">
    <div id="map"></div>

    <div id="cut-banner" class="cut-banner" style="display:none;">
        <span>✂️ <strong>Cut Mode Active:</strong> Click on the map across the province to add vertices. Double-click or click "✓ Slice Unit" when done.</span>
        <button class="btn btn-dark" onclick="cancelCutDrawing()" style="padding:2px 10px; font-size:11px;">Cancel</button>
    </div>

    <!-- Floating Interactive Controls -->
    <div class="controls-panel">
        <!-- Palette Header -->
        <div>
            <div class="section-title">
                <span>Color Palette Swatches</span>
                <span style="font-size:10px; color:#38bdf8; text-transform:none;">Click swatch, then click province</span>
            </div>
            <div class="palette-grid" id="palette-container"></div>
            <div style="margin-top:8px; display:flex; align-items:center; justify-content:space-between;">
                <span style="font-size:11px; color:#94a3b8;">Custom Hex Color:</span>
                <input type="color" id="custom-color-picker" value="#f59e0b" style="border:none; width:32px; height:24px; cursor:pointer; background:transparent;">
            </div>
        </div>

        <!-- Search Bar -->
        <div>
            <div class="section-title">Search Any Province or Country</div>
            <input type="text" id="search-input" class="search-bar" placeholder="🔍 Search e.g. Damascus, Cordoba, Buda, Transdanubia, Kashgar...">
        </div>

        <!-- Imperial Realm Filter -->
        <div>
            <div class="section-title">Filter by Realm / Scope</div>
            <select id="realm-filter" class="filter-select" onchange="applyRealmFilter()">
                <option value="ALL">🌍 Entire World (All {len(all_provinces)} Units)</option>
                <option value="CALIPHATE" selected>👑 Imperial Caliphate Core & Frontier Marches (Colorable)</option>
                <option value="Levant & Imperial Seat (Dimashq)">🏛️ Levant & Imperial Seat (Dimashq / Syria, Jordan, Palestine)</option>
                <option value="Mesopotamia (al-Iraq: Kufa & Wasit)">🌾 Mesopotamia (al-Iraq: Kufa & Wasit)</option>
                <option value="Anatolia & al-Qustantiniyya">⚔️ Anatolia & Kostantiniyya (Kostantiniyya, Konya, Taurus)</option>
                <option value="Balkans & Aegean Marches (al-Yunan)">🏛️ Balkans & Aegean Marches (Greece, Macedonia, Albania)</option>
                <option value="Danube & Pannonian Marches">🛡️ Danube & Pannonian Marches (Hungary/Buda, Serbia, Bulgaria)</option>
                <option value="Danube Marches & Dobruja">🛡️ Danube Marches & Dobruja (Romania: Dobruja & Danube Marches)</option>
                <option value="al-Andalus (Cordoba, Toledo & Seville)">🏰 al-Andalus (Cordoba, Toledo, Seville, Granada)</option>
                <option value="Gaul (Ard Ifranja / Narbonne & Paris)">⚜️ Gaul (Ard Ifranja / Narbonne, Aquitaine & Paris)</option>
                <option value="Rhine Marches (Thughur al-Rin)">🌊 Rhine Marches (Belgium, Netherlands South Rhine)</option>
                <option value="Rhine Frontier Marches">🛡️ Rhine Frontier Marches (Rhineland-Palatinate, NRW West Bank)</option>
                <option value="Alpine Marches (Jibal al-Alp">🏔️ Alpine Marches (Switzerland, Austria South Danube, Bavaria Raetia)</option>
                <option value="Italy & Rome (al-Italiyya, Langobardia & Ruma)">🦅 Italy & Rome (al-Italiyya, Langobardia & Ruma)</option>
                <option value="Egypt (Misr & al-Iskandariyya)">⛵ Egypt (Misr & Alexandria)</option>
                <option value="Maghrib">🌅 Maghrib (Morocco, Algeria Oasis, Tunisia, Libya)</option>
                <option value="The Holy Sanctuaries (Hijaz & Najd)">🕋 The Holy Sanctuaries (Hijaz & Yaman)</option>
                <option value="Persian Plateau (Fars, Rayy & Khurasan)">🦁 Persian Plateau & Khurasan</option>
                <option value="Transoxiana">💎 Central Asia / Transoxiana (Samarkand & Syr Darya)</option>
                <option value="Semirechye & Syr Darya Marches">🏞️ Semirechye / Yeti-Su (Isbijab, Taraz, Almaliq to Lake Balkhash)</option>
                <option value="Fergana Basin & Tien Shan">⛰️ Farghana & Balasaghun (Kyrgyz Tian Shan)</option>
                <option value="Tarim Basin & Silk Road Marches (Kashgar)">🐎 Tarim Basin & Silk Road Marches (Kashgar & Hotan)</option>
                <option value="Indus Valley">🌊 Indus Valley & al-Hind (Sindh, Punjab & Thar Marches)</option>
                <option value="Caucasus Marches (al-Qabq & Shirvan)">🏔️ Caucasus Marches (Derbent Gates)</option>
                <option value="Frontier Marches - ">✂️ Customizable Frontiers (India, Kazakhstan, China & Russia - cut with Slicer)</option>
                <option value="Bilad al-Khazar & al-Saqaliba">❄️ Russia & Khazaria (Bilad al-Khazar, Volga/Itil & al-Saqaliba)</option>
                <option value="External World">🌍 External World (Uncolorable Frontiers: Deep Sahara, East Danube, etc.)</option>
                <option value="ALL">🌍 Entire Imperial Caliphate (All {len(all_provinces)} Units)</option>
                <option value="CALIPHATE" selected>👑 Imperial Caliphate Overview (All Ancient Regions)</option>
                <option value="al-Andalus">🏰 al-Andalus (Hispania & Gharb al-Andalus)</option>
                <option value="Gaul & Septimania">⚜️ Gaul & Septimania (Gallia & Ard Ifranja)</option>
                <option value="Raetia & Alpine Marches">🏔️ Raetia & Alpine Marches (Jibal al-Alp & Noricum)</option>
                <option value="Italia & al-Siqilliyya">🦅 Italia & al-Siqilliyya (Italy, Rome & the Islands)</option>
                <option value="Illyricum & Dalmatia">🛡️ Illyricum & Dalmatia (Adriatic Marches)</option>
                <option value="Pannonia & Danube Marches">🌊 Pannonia & Danube Marches (Thughur al-Danub)</option>
                <option value="al-Yunan & Thracia">🏛️ al-Yunan & Thracia (Greece, Macedonia & Aegean)</option>
                <option value="Anatolia & al-Qustantiniyya">⚔️ Anatolia & al-Qustantiniyya (Asia Minor / Bilad al-Rum)</option>
                <option value="al-Qabq & Shirvan">🏔️ al-Qabq & Shirvan (Caucasus Marches / Armenia & Arran)</option>
                <option value="Bilad al-Sham">🏛️ Bilad al-Sham (The Levant / Dimashq, al-Quds & Hims)</option>
                <option value="Mesopotamia">🌾 Mesopotamia (al-Iraq wa al-Jazira / Kufa & Wasit)</option>
                <option value="Misr">⛵ Misr (Egypt, Nile Valley & al-Iskandariyya)</option>
                <option value="Barqa & Tripoli">🌅 Barqa & Tripoli (Cyrenaica & Tripolitania)</option>
                <option value="Ifriqiya">🏺 Ifriqiya (Tunisia, Carthage & Qayrawan)</option>
                <option value="al-Maghrib al-Awsat">🛡️ al-Maghrib al-Awsat (Central Maghreb / Tahert & Tlemcen)</option>
                <option value="al-Maghrib al-Aqsa">🏰 al-Maghrib al-Aqsa (Far Maghreb / Fes & Tangier)</option>
                <option value="al-Habasha">⛵ al-Habasha & the Horn (Horn of Africa Marches)</option>
                <option value="al-Hijaz">🕋 al-Hijaz & Bilad al-Arab (Makkah, Madinah & Najd)</option>
                <option value="al-Yaman">🌴 al-Yaman & Hadhramaut (South Arabia / Sana'a & Aden)</option>
                <option value="Oman & al-Bahrayn">🌊 Oman & al-Bahrayn (Eastern Arabia & Persian Gulf)</option>
                <option value="Bilad Faris">🦁 Bilad Faris & al-Jibal (Persian Plateau / Fars, Rayy & Isfahan)</option>
                <option value="Khurasan al-Kubra">⚔️ Khurasan al-Kubra (Greater Khorasan, Balkh & Kabul)</option>
                <option value="Mawara al-Nahr">💎 Mawara al-Nahr (Transoxiana / Samarqand, Bukhara & Khwarazm)</option>
                <option value="Farghana & Yeti-Su">⛰️ Farghana & Yeti-Su (Fergana Basin & Semirechye)</option>
                <option value="Dasht-i Qipchaq">🐎 Dasht-i Qipchaq & Bilad al-Khazar (Caspian Steppe & Ural Marches)</option>
                <option value="Kashgharia">🐎 Kashgharia & the Tarim Basin (Silk Road Marches)</option>
                <option value="al-Sind & the Indus Valley">🌊 al-Sind & the Indus Valley (Mansura, Daybul & Multan)</option>
                <option value="Northern & Western India">🛡️ Northern & Western India (al-Hind Marches & Gangetic Basin)</option>
            </select>
        </div>

        <!-- Province Inspector -->
        <div>
            <div class="section-title">Province Inspector</div>
            <div class="info-box">
                <div class="info-title" id="insp-name">Click any province on Earth to inspect & paint</div>
                <div class="info-row">
                    <span class="info-label">Country:</span>
                    <span class="info-val" id="insp-country">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Imperial Realm / Region:</span>
                    <span class="info-val" id="insp-realm" style="color:#f59e0b;">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Admin Level:</span>
                    <span class="info-val" id="insp-level">Level-1 Province</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Imperial Status:</span>
                    <span class="info-val" id="insp-status">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Painted Color:</span>
                    <span class="info-val" id="insp-color">-</span>
                </div>
            </div>
            <div id="insp-actions" style="margin-top:8px; display:flex; gap:6px;">
                <button id="btn-blank-current" class="btn" onclick="blankCurrentInspectedFeature()" style="flex:1; background:#dc2626; color:#ffffff; font-weight:700; padding:6px 10px; font-size:11.5px; border:1px solid #ef4444; border-radius:6px; cursor:pointer;" disabled title="Exclude this province from the Empire">
                    🚫 Blank Province
                </button>
                <button id="btn-unblank-current" class="btn" onclick="restoreCurrentInspectedFeature()" style="flex:1; background:#10b981; color:#ffffff; font-weight:700; padding:6px 10px; font-size:11.5px; border:1px solid #34d399; border-radius:6px; cursor:pointer; display:none;" title="Restore this province as colorable imperial territory">
                    ✨ Restore to Empire
                </button>
            </div>
        </div>

        <!-- Frontier Slicer & Province Divider Tool -->
        <div class="slicer-card">
            <div class="section-title">
                <span>✂️ Frontier Slicer & Divider</span>
                <span id="slicer-status-badge" class="badge-idle">Ready</span>
            </div>
            <p style="font-size:11px; color:#94a3b8; line-height:1.4;">
                Draw a cutting line across any administrative unit to divide it into two colorable units, or permanently blank out frontier portions.
            </p>
            <div class="btn-grid" style="grid-template-columns: 1fr 1fr; gap:6px;">
                <button id="btn-start-cut" class="btn btn-warning" onclick="toggleCutDrawing()">✂️ Draw Cut Line</button>
                <button id="btn-river-cut" class="btn btn-info" onclick="toggleRiverCutMode()" style="background:#0284c7; color:#ffffff; font-weight:700;">🌊 Cut Along River</button>
            </div>
            <div class="btn-grid" style="grid-template-columns: 1fr 1fr; gap:6px; margin-top:6px;">
                <button id="btn-exec-cut" class="btn btn-primary" onclick="executeCutLine()" disabled>✓ Slice Unit</button>
                <button id="btn-blank-mode" class="btn" onclick="toggleBlankMode()" style="background:#dc2626; color:#ffffff; font-weight:700; border:1px solid #ef4444;" title="Click any province to blank it out">🚫 Blank Mode</button>
            </div>
            <div class="btn-grid" style="grid-template-columns: 1fr 1fr; gap:6px; margin-top:6px;">
                <button id="btn-clear-cut" class="btn btn-dark" onclick="cancelCutDrawing()">✖ Clear / Cancel</button>
                <button id="btn-undo-cut" class="btn btn-dark" onclick="undoLastCut()" disabled>↺ Undo</button>
            </div>
        </div>

        <!-- Quick Action Buttons -->
        <div class="btn-grid">
            <button class="btn btn-gold" onclick="paintActiveFilteredRealm()">🎨 Paint Realm</button>
            <button class="btn btn-dark" onclick="resetAllPaintedColors()">↺ Reset Paint</button>
        </div>

        <div class="btn-grid">
            <button class="btn btn-primary" onclick="exportPaintedGeoJSON()">💾 Export GeoJSON</button>
            <button class="btn btn-success" id="btn-export-png">🖼️ Export 2K PNG</button>
        </div>
    </div>
</div>

<script>
    // Embedded Global GeoJSON Datasets
    const geojsonData = {provinces_json_str};
    const mountainsData = {mtn_zones_str};
    const mountainLinesData = {mtn_lines_str};
    const riversData = {rivers_str};
    const desertsData = {deserts_str};
    const mtnLabelsData = {mtn_labels_str};

    // Color Palette
    // Color Palette - Ancient Regions of the Caliphate
    const palette = [
        {{ name: "al-Andalus (Emerald)", hex: "#059669" }},
        {{ name: "Gaul & Septimania (Teal)", hex: "#0d9488" }},
        {{ name: "Raetia & Alps (Alpine Sky)", hex: "#0284c7" }},
        {{ name: "Italia & Rome (Imperial Crimson)", hex: "#e11d48" }},
        {{ name: "Illyricum & Dalmatia (Adriatic Indigo)", hex: "#4338ca" }},
        {{ name: "Pannonia & Danube (Danubian Cobalt)", hex: "#4f46e5" }},
        {{ name: "al-Yunan & Thracia (Aegean Violet)", hex: "#6366f1" }},
        {{ name: "Anatolia & Rum (Byzantine Purple)", hex: "#9333ea" }},
        {{ name: "Caucasus & Shirvan (Amethyst)", hex: "#a855f7" }},
        {{ name: "Bilad al-Sham (Levantine Blue)", hex: "#2563eb" }},
        {{ name: "Mesopotamia (Tigris-Euphrates Blue)", hex: "#0369a1" }},
        {{ name: "Misr / Egypt (Golden Amber)", hex: "#f59e0b" }},
        {{ name: "Barqa & Tripoli (Desert Ochre)", hex: "#d97706" }},
        {{ name: "Ifriqiya / Carthage (Bronze)", hex: "#b45309" }},
        {{ name: "Maghrib al-Awsat (Atlas Brass)", hex: "#ca8a04" }},
        {{ name: "Maghrib al-Aqsa (Imperial Gold)", hex: "#eab308" }},
        {{ name: "al-Habasha & Horn (Bronze Earth)", hex: "#854d0e" }},
        {{ name: "al-Hijaz & Arabia (Sacred Green)", hex: "#16a34a" }},
        {{ name: "al-Yaman (Arabian Green)", hex: "#15803d" }},
        {{ name: "Oman & al-Bahrayn (Gulf Green)", hex: "#166534" }},
        {{ name: "Bilad Faris (Persian Saffron)", hex: "#f97316" }},
        {{ name: "Khurasan al-Kubra (Khurasani Burnt Orange)", hex: "#ea580c" }},
        {{ name: "Transoxiana / Mawara al-Nahr (Turquoise)", hex: "#0891b2" }},
        {{ name: "Farghana & Yeti-Su (Jade Teal)", hex: "#0f766e" }},
        {{ name: "Dasht-i Qipchaq & Khazaria (Steppe Olive)", hex: "#3f6212" }},
        {{ name: "Tarim / Kashgharia (Sandstone Gold)", hex: "#a16207" }},
        {{ name: "al-Sind / Indus (Indus Rose Magenta)", hex: "#ec4899" }},
        {{ name: "al-Hind / Aryavarta (Terracotta Crimson)", hex: "#9a3412" }},
        {{ name: "Umayyad Royal White", hex: "#f8fafc" }},
        {{ name: "Cordoba Gold", hex: "#f59e0b" }},
        {{ name: "Andalusian Emerald", hex: "#10b981" }},
        {{ name: "Damascus Royal Azure", hex: "#0284c7" }},
        {{ name: "Byzantine Tyrian Purple", hex: "#7e22ce" }},
        {{ name: "Constantinople Amethyst", hex: "#a855f7" }},
        {{ name: "Gallic Mint", hex: "#14b8a6" }},

        {{ name: "Khurasan Crimson", hex: "#dc2626" }},
        {{ name: "Italian Rose Carmine", hex: "#e11d48" }},
        {{ name: "Persian Saffron", hex: "#f97316" }},
        {{ name: "Maghrib Terracotta", hex: "#ea580c" }},
        {{ name: "Desert Amber", hex: "#d97706" }},
        {{ name: "Hijaz Olive Green", hex: "#15803d" }},
        {{ name: "Balkan Royal Indigo", hex: "#4338ca" }},

        {{ name: "Danube Cobalt", hex: "#2563eb" }},
        {{ name: "Aegean Sky Blue", hex: "#38bdf8" }},
        {{ name: "Transoxiana Turquoise", hex: "#06b6d4" }},
        {{ name: "Samarkand Deep Teal", hex: "#0e7490" }},
        {{ name: "Indus Cyan", hex: "#00f2fe" }},
        {{ name: "Sindh Saffron Rose", hex: "#fb7185" }},
        {{ name: "Hindustan Magenta", hex: "#ec4899" }},

        {{ name: "Pamir Bronze", hex: "#b45309" }},
        {{ name: "Abbasid Obsidian Slate", hex: "#334155" }},
        {{ name: "Imperial Dark Black", hex: "#0f172a" }},
        {{ name: "Lime Citron", hex: "#84cc16" }},
        {{ name: "Gold Yellow", hex: "#eab308" }},
        {{ name: "Dark Carmine", hex: "#991b1b" }},
        {{ name: "Slate Blue", hex: "#64748b" }},
        {{ name: "Frontier Blank (Excluded)", hex: "#1e293b" }}
    ];

    let activeColor = palette[1].hex;
    const divisionColors = {{}};

    // Pre-populate default colors
    geojsonData.features.forEach(f => {{
        if (f.properties.painted_color || f.properties.initial_color) {{
            divisionColors[f.properties.id] = f.properties.is_caliphate
                ? (f.properties.painted_color || f.properties.initial_color)
                : f.properties.initial_color;
        }}
    }});

    // Build Palette Swatches
    const paletteContainer = document.getElementById('palette-container');
    palette.forEach((col, idx) => {{
        const swatch = document.createElement('div');
        swatch.className = 'color-swatch' + (idx === 1 ? ' active' : '');
        swatch.style.backgroundColor = col.hex;
        swatch.title = col.name + ' (' + col.hex + ')';
        swatch.addEventListener('click', () => {{
            document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
            swatch.classList.add('active');
            activeColor = col.hex;
            document.getElementById('custom-color-picker').value = col.hex;
        }});
        paletteContainer.appendChild(swatch);
    }});

    document.getElementById('custom-color-picker').addEventListener('input', (e) => {{
        activeColor = e.target.value;
        document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
    }});

    // Initialize Global Map Centered on World (SVG mode, no preferCanvas to ensure DOM event precision)
    const map = L.map('map', {{
        zoomControl: false,
        preferCanvas: false,
        minZoom: 2,
        worldCopyJump: true
    }}).setView([28.0, 20.0], 3);

    L.control.zoom({{ position: 'bottomleft' }}).addTo(map);

    // Official CartoDB Dark Basemap with User Project API Key
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key={CARTO_API_KEY}', {{
        attribution: '&copy; OpenStreetMap &copy; CARTO | Global Regional Painter',
        maxZoom: 18,
        subdomains: 'abcd'
    }}).addTo(map);

    // Create Dedicated Panes for Z-Index Layering
    map.createPane('unitsPane'); map.getPane('unitsPane').style.zIndex = 350;
    map.createPane('desertsPane'); map.getPane('desertsPane').style.zIndex = 410;
    map.createPane('mountainsPane'); map.getPane('mountainsPane').style.zIndex = 430;
    map.createPane('mountainLinesPane'); map.getPane('mountainLinesPane').style.zIndex = 440;
    map.createPane('riversPane'); map.getPane('riversPane').style.zIndex = 450;
    map.createPane('mtnLabelsPane'); map.getPane('mtnLabelsPane').style.zIndex = 470;

    let unitsLayer, mtnZonesLayer, mtnLinesLayer, riversLayer, desertsLayer;
    let currentlyFilteredFeatures = geojsonData.features;

    // Unit Province Styling
    function getUnitStyle(feature) {{
        const uid = feature.properties.id;
        const color = divisionColors[uid] || feature.properties.initial_color || '#1e293b';
        const isCaliphate = feature.properties.is_caliphate;
        return {{
            pane: 'unitsPane',
            fillColor: color,
            fillOpacity: isCaliphate ? 0.74 : 0.38,
            color: isCaliphate ? 'rgba(255, 255, 255, 0.38)' : 'rgba(255, 255, 255, 0.12)',
            weight: isCaliphate ? 1.0 : 0.5
        }};
    }}

    // Paint Province Action (ONLY Imperial Caliphate units can be painted)
    function paintFeature(feature, layer) {{
        const p = feature.properties;

        // If Blank Mode is active, blank this province immediately!
        if (isBlankModeActive) {{
            blankFeature(feature);
            return;
        }}

        // If user painted with the Frontier Blank swatch (#1e293b), blank it!
        if (activeColor === '#1e293b') {{
            blankFeature(feature);
            return;
        }}
        
        // Strict Rule: ONLY parts included in the Empire are colorable!
        if (!p.is_caliphate) {{
            updateInspector(feature, null);
            return;
        }}

        if (divisionColors[p.id] === activeColor) {{
            // Toggle off to default initial color
            divisionColors[p.id] = p.initial_color;
        }} else {{
            divisionColors[p.id] = activeColor;
        }}
        if (unitsLayer && layer) {{
            unitsLayer.resetStyle(layer);
        }}
        updateInspector(feature, divisionColors[p.id]);
    }}

    // Render Administrative Level 1 Provinces
    function renderUnits(feats) {{
        if (unitsLayer) map.removeLayer(unitsLayer);

        unitsLayer = L.geoJSON({{ type: 'FeatureCollection', features: feats }}, {{
            pane: 'unitsPane',
            style: getUnitStyle,
            onEachFeature: function(feature, layer) {{
                const p = feature.properties;
                const statusBadge = p.is_caliphate
                    ? '<span style="color:#10b981; font-weight:700;">● Colorable Imperial Province</span>'
                    : '<span style="color:#64748b; font-weight:600;">○ External Frontier (Uncolorable)</span>';

                layer.bindTooltip(`<b>${{p.name}}</b><br><span style="color:#38bdf8;">${{p.country}}</span> &bull; <i>${{p.realm}}</i><br>${{statusBadge}}`, {{
                    sticky: true
                }});

                layer.on('click', function(e) {{
                    L.DomEvent.stopPropagation(e);
                    if (isRiverCutModeActive) {{
                        return;
                    }}
                    if (isCutModeActive) {{
                        handleCutMapClick(e);
                        return;
                    }}
                    if (isBlankModeActive) {{
                        blankFeature(feature);
                        return;
                    }}
                    paintFeature(feature, layer);
                }});

                layer.on('mouseover', function() {{
                    if (p.is_caliphate) {{
                        layer.setStyle({{ weight: 2.5, color: '#ffffff', fillOpacity: 0.90 }});
                        layer.bringToFront();
                    }} else {{
                        layer.setStyle({{ weight: 1.2, color: 'rgba(255, 255, 255, 0.4)' }});
                    }}
                }});

                layer.on('mouseout', function() {{
                    if (unitsLayer) unitsLayer.resetStyle(layer);
                }});

                // Add class for cursor pointer on imperial units
                setTimeout(() => {{
                    if (layer._path) {{
                        layer._path.classList.add(p.is_caliphate ? 'caliphate-unit' : 'external-unit');
                    }}
                }}, 0);
            }}
        }}).addTo(map);

        currentlyFilteredFeatures = feats;
    }}

    function updateInspector(feature, color) {{
        currentInspectedFeature = feature;
        const p = feature.properties;
        document.getElementById('insp-name').innerText = p.name;
        document.getElementById('insp-country').innerText = `${{p.country}} (${{p.iso || ''}})`;
        document.getElementById('insp-realm').innerText = p.realm;
        document.getElementById('insp-level').innerText = p.admin_level || 'Level-1 Province';
        
        const statusBox = document.getElementById('insp-status');
        const colorBox = document.getElementById('insp-color');
        const btnBlank = document.getElementById('btn-blank-current');
        const btnUnblank = document.getElementById('btn-unblank-current');

        if (p.is_caliphate) {{
            statusBox.innerHTML = '<span style="color:#10b981; font-weight:700;">● Imperial Province (Colorable)</span>';
            const activeCol = color || divisionColors[p.id] || p.initial_color;
            colorBox.innerHTML = `<span style="display:inline-block; width:12px; height:12px; border-radius:2px; background:${{activeCol}}; margin-right:5px; vertical-align:middle; border:1px solid #ffffff;"></span> ${{activeCol}}`;
            if (btnBlank) {{ btnBlank.style.display = 'block'; btnBlank.disabled = false; }}
            if (btnUnblank) {{ btnUnblank.style.display = 'none'; }}
        }} else {{
            statusBox.innerHTML = '<span style="color:#94a3b8; font-weight:600;">○ External Territory (Uncolorable)</span>';
            colorBox.innerHTML = `<span style="color:#64748b; font-style:italic;">None (Outside Imperial Frontier)</span>`;
            if (btnBlank) {{ btnBlank.style.display = 'none'; }}
            if (btnUnblank) {{ btnUnblank.style.display = 'block'; btnUnblank.disabled = false; }}
        }}
    }}

    // 1. Mountain Zones Layer (GMBA v2.0 Global - Europe, Africa, Asia, Americas)
    mtnZonesLayer = L.geoJSON(mountainsData, {{
        pane: 'mountainsPane',
        interactive: false,
        style: {{
            fillColor: '#f59e0b',
            fillOpacity: 0.28,
            color: '#d97706',
            weight: 0.8
        }}
    }}).addTo(map);

    // 2. Mountain Lines Layer
    mtnLinesLayer = L.geoJSON(mountainLinesData, {{
        pane: 'mountainLinesPane',
        interactive: false,
        style: {{
            color: '#fbbf24',
            weight: 1.5,
            opacity: 0.80,
            dashArray: '3, 4'
        }}
    }}).addTo(map);

    // 3. Rivers Layer (Highlighting & Darkening Major Continental Arteries)
    function getRiverStyle(feature) {{
        const isMajor = feature.properties && feature.properties.is_major;
        if (isMajor) {{
            return {{
                color: '#0284c7', // Darker royal blue
                weight: 2.8,
                opacity: 0.95
            }};
        }} else {{
            return {{
                color: '#38bdf8', // Lighter cyan stream
                weight: 1.0,
                opacity: 0.50,
                dashArray: '2, 3'
            }};
        }}
    }}

    // 3. Rivers Layer (Interactive Centerlines + Tactical Inspection)
    riversLayer = L.geoJSON(riversData, {{
        pane: 'riversPane',
        interactive: true,
        style: getRiverStyle,
        onEachFeature: function(feature, layer) {{
            const props = feature.properties || {{}};
            const rName = props.name || props.name_en || 'Major River / Waterway';
            const rank = props.scalerank != null ? `Scale Rank ${{props.scalerank}}` : 'Navigable River';
            const classification = props.featurecla || 'River Waterway';
            const isMajor = !!props.is_major;

            layer.bindTooltip(`
                <div style="font-family:'Inter',sans-serif; font-size:11px; padding:2px 4px;">
                    <div style="font-weight:700; color:#38bdf8;">🌊 ${{rName}}</div>
                    <div style="font-size:10px; color:#cbd5e1;">${{isMajor ? '⭐ Major Continental Artery' : 'Navigable Stream'}} &bull; ${{rank}}</div>
                </div>
            `, {{ sticky: true, className: 'river-tooltip-custom' }});

            layer.on({{
                mouseover: function(e) {{
                    layer.setStyle({{ color: '#7dd3fc', weight: isMajor ? 5.0 : 3.5, opacity: 1.0 }});
                    document.getElementById('insp-name').textContent = '🌊 ' + rName;
                    document.getElementById('insp-country').innerHTML = '<span style="color:#38bdf8;">Continental Waterway</span>';
                    document.getElementById('insp-realm').innerHTML = isMajor ? '<span style="color:#0284c7; font-weight:700;">Major Continental River Artery</span>' : 'Secondary River / Tributary';
                    document.getElementById('insp-level').textContent = classification + ' (' + rank + ')';
                    document.getElementById('insp-status').innerHTML = '<span style="color:#38bdf8; font-weight:700;">🛡️ Natural River Moat & Strategic Barrier</span>';
                    document.getElementById('insp-color').innerHTML = `<span style="color:#7dd3fc;">Hydrographic Defense Line</span>`;
                }},
                mouseout: function(e) {{
                    riversLayer.resetStyle(layer);
                }},
                click: function(e) {{
                    L.DomEvent.stopPropagation(e);
                    lastClickedRiverFeat = feature;
                    lastClickedRiverLatLng = e.latlng;

                    // If River Slice mode is active, directly execute cut along this river
                    if (isRiverCutModeActive) {{
                        executeRiverSlice(feature, e.latlng);
                        return;
                    }}

                    if (isCutModeActive) {{
                        handleCutMapClick(e);
                        return;
                    }}

                    L.popup()
                        .setLatLng(e.latlng)
                        .setContent(`
                            <div style="font-family:'Inter',sans-serif; min-width:210px;">
                                <div style="font-size:10px; text-transform:uppercase; font-weight:700; color:#38bdf8; letter-spacing:0.5px; margin-bottom:2px;">
                                    ${{isMajor ? '⭐ Major Continental River' : '🌊 River Waterway'}}
                                </div>
                                <div style="font-size:14px; font-weight:700; color:#f8fafc; margin-bottom:6px;">${{rName}}</div>
                                <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                                    <div>📐 <strong>Rank:</strong> ${{rank}}</div>
                                    <div>🌊 <strong>Classification:</strong> ${{classification}}</div>
                                    <div>🛡️ <strong>Strategy:</strong> Natural Frontier Water Trench</div>
                                </div>
                                <button class="btn btn-primary" onclick="executeRiverSliceFromPopup()" style="margin-top:8px; width:100%; font-size:11px; padding:6px 8px; background:#0284c7; color:#ffffff; border:1px solid #38bdf8; border-radius:4px; font-weight:600; cursor:pointer;">
                                    ✂️ Slice Province Along This River
                                </button>
                                <div style="margin-top:5px; font-size:10px; color:#94a3b8; font-style:italic; text-align:center;">
                                    (Or toggle Rivers OFF in header to paint underneath)
                                </div>
                            </div>
                        `)
                        .openOn(map);
                }}
            }});
        }}
    }}).addTo(map);

    // 4. Deserts Layer
    desertsLayer = L.geoJSON(desertsData, {{
        pane: 'desertsPane',
        interactive: false,
        style: {{
            fillColor: '#d97706',
            fillOpacity: 0.18,
            color: '#b45309',
            weight: 0.8,
            dashArray: '4, 4'
        }}
    }}).addTo(map);

    // Map Click Handler (Supports Cut Point Placement & Spatial Fallback)
    map.on('click', function(e) {{
        if (isCutModeActive) {{
            handleCutMapClick(e);
            return;
        }}

        const pt = turf.point([e.latlng.lng, e.latlng.lat]);
        let targetFeature = null;
        let targetLayer = null;

        if (unitsLayer) {{
            unitsLayer.eachLayer(function(l) {{
                if (!targetFeature && l.feature && l.feature.geometry) {{
                    try {{
                        if (turf.booleanPointInPolygon(pt, l.feature)) {{
                            targetFeature = l.feature;
                            targetLayer = l;
                        }}
                    }} catch (err) {{}}
                }}
            }});
        }}

        if (targetFeature && targetLayer) {{
            paintFeature(targetFeature, targetLayer);
        }}
    }});

    // Double-click to execute cut line
    map.on('dblclick', function(e) {{
        if (isCutModeActive) {{
            L.DomEvent.stopPropagation(e);
            executeCutLine();
        }}
    }});

    // Layer Toggle Wiring
    document.getElementById('chk-mtn-zones').addEventListener('change', (e) => {{
        if (e.target.checked) map.addLayer(mtnZonesLayer);
        else map.removeLayer(mtnZonesLayer);
    }});
    // Mountain range name labels (zoom-dependent declutter)
    const mtnNamesLayer = L.layerGroup().addTo(map);
    function labelMinZoom(a) {{
        if (a >= 150) return 2;
        if (a >= 40) return 3;
        if (a >= 12) return 4;
        if (a >= 3) return 5;
        if (a >= 0.8) return 6;
        return 7;
    }}
    function refreshMtnLabels() {{
        mtnNamesLayer.clearLayers();
        if (!document.getElementById('chk-mtn-names').checked) return;
        const z = map.getZoom();
        const b = map.getBounds().pad(0.15);
        const placed = [];
        for (const r of mtnLabelsData) {{
            if (z < labelMinZoom(r.a)) continue;
            const ll = L.latLng(r.lat, r.lng);
            if (!b.contains(ll)) continue;
            const px = map.latLngToContainerPoint(ll);
            const w = r.n.length * (z >= 6 ? 8 : 6.5);
            if (placed.some(q => Math.abs(q.x - px.x) < (q.w + w) / 2 && Math.abs(q.y - px.y) < 18)) continue;
            placed.push({{ x: px.x, y: px.y, w: w }});
            const fs = Math.max(9, Math.min(15, 8 + Math.log2(r.a + 1) * 0.9 + (z - 4) * 0.6));
            const elev = (z >= 5 && r.h) ? `<span class="mtn-elev">▲ ${{r.h.toLocaleString()}} m</span>` : '';
            L.marker(ll, {{
                pane: 'mtnLabelsPane',
                interactive: false,
                keyboard: false,
                icon: L.divIcon({{
                    className: 'mtn-label',
                    html: `<span class="mtn-label-inner" style="font-size:${{fs.toFixed(1)}}px;">⛰ ${{r.n}}${{elev}}</span>`,
                    iconSize: [0, 0]
                }})
            }}).addTo(mtnNamesLayer);
        }}
    }}
    map.on('zoomend moveend', refreshMtnLabels);
    refreshMtnLabels();
    document.getElementById('chk-mtn-names').addEventListener('change', refreshMtnLabels);

    document.getElementById('chk-mtn-lines').addEventListener('change', (e) => {{
        if (e.target.checked) map.addLayer(mtnLinesLayer);
        else map.removeLayer(mtnLinesLayer);
    }});
    document.getElementById('chk-rivers').addEventListener('change', (e) => {{
        if (e.target.checked) map.addLayer(riversLayer);
        else map.removeLayer(riversLayer);
    }});
    document.getElementById('chk-deserts').addEventListener('change', (e) => {{
        if (e.target.checked) map.addLayer(desertsLayer);
        else map.removeLayer(desertsLayer);
    }});

    // Global Search Bar
    document.getElementById('search-input').addEventListener('input', (e) => {{
        const q = e.target.value.toLowerCase().trim();
        if (!q) {{
            renderUnits(geojsonData.features);
            return;
        }}
        const matched = geojsonData.features.filter(f => {{
            const p = f.properties;
            return (p.name || '').toLowerCase().includes(q) || (p.country || '').toLowerCase().includes(q) || (p.realm || '').toLowerCase().includes(q);
        }});
        renderUnits(matched);
        if (matched.length > 0 && unitsLayer) {{
            map.fitBounds(unitsLayer.getBounds(), {{ padding: [50, 50], maxZoom: 8 }});
        }}
    }});

    // Realm / Scope Filter
    function applyRealmFilter() {{
        const sel = document.getElementById('realm-filter').value;
        if (sel === 'ALL') {{
            renderUnits(geojsonData.features);
            map.setView([28.0, 20.0], 3);
        }} else if (sel === 'CALIPHATE') {{
            const filtered = geojsonData.features.filter(f => f.properties.is_caliphate);
            renderUnits(filtered);
            if (filtered.length > 0 && unitsLayer) {{
                map.fitBounds(unitsLayer.getBounds(), {{ padding: [40, 40] }});
            }}
        }} else if (sel === 'External World') {{
            const filtered = geojsonData.features.filter(f => !f.properties.is_caliphate);
            renderUnits(filtered);
        }} else {{
            const filtered = geojsonData.features.filter(f => f.properties.realm.includes(sel));
            renderUnits(filtered);
            if (filtered.length > 0 && unitsLayer) {{
                map.fitBounds(unitsLayer.getBounds(), {{ padding: [50, 50] }});
            }}
        }}
    }}

    // Paint Active Filtered Realm (ONLY paints Caliphate units)
    function paintActiveFilteredRealm() {{
        currentlyFilteredFeatures.forEach(f => {{
            if (f.properties.is_caliphate) {{
                divisionColors[f.properties.id] = activeColor;
            }}
        }});
        renderUnits(currentlyFilteredFeatures);
    }}

    // Reset Painted Colors
    function resetAllPaintedColors() {{
        if (confirm("Reset all painted provinces to default colors?")) {{
            geojsonData.features.forEach(f => {{
                divisionColors[f.properties.id] = f.properties.initial_color;
            }});
            renderUnits(currentlyFilteredFeatures);
        }}
    }}

    // Export GeoJSON
    function exportPaintedGeoJSON() {{
        const exportFc = {{
            type: "FeatureCollection",
            name: "painted_level1_provinces",
            total_provinces: geojsonData.features.length,
            features: geojsonData.features.map(f => ({{
                ...f,
                properties: {{
                    ...f.properties,
                    painted_color: divisionColors[f.properties.id] || f.properties.initial_color
                }}
            }}))
        }};
        const blob = new Blob([JSON.stringify(exportFc, null, 2)], {{ type: "application/json" }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "painted_imperial_level1_map.geojson";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }}

    // High-Resolution 2K PNG Map Export with Legend
    document.getElementById('btn-export-png').addEventListener('click', () => {{
        alert("Rendering high-resolution 2K global map with custom legend. Please wait a moment...");
        
        let minLon = 180, maxLon = -180, minLat = 90, maxLat = -90;
        const paintedFeatures = [];

        geojsonData.features.forEach(feat => {{
            const col = divisionColors[feat.properties.id] || feat.properties.initial_color;
            if (col && feat.properties.is_caliphate) {{
                paintedFeatures.push({{
                    geometry: feat.geometry,
                    color: col,
                    name: feat.properties.name,
                    country: feat.properties.country,
                    realm: feat.properties.realm
                }});
                try {{
                    const b = turf.bbox(feat);
                    if (b[0] < minLon) minLon = b[0];
                    if (b[2] > maxLon) maxLon = b[2];
                    if (b[1] < minLat) minLat = b[1];
                    if (b[3] > maxLat) maxLat = b[3];
                }} catch(e) {{}}
            }}
        }});

        if (paintedFeatures.length === 0) return;

        const mapWidth = 2400;
        const legendWidth = 600;
        const canvasWidth = mapWidth + legendWidth;
        const canvasHeight = 1600;

        const canvas = document.createElement('canvas');
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        const ctx = canvas.getContext('2d');

        // Dark Canvas Background
        ctx.fillStyle = '#070a13';
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);

        function project(lon, lat) {{
            const x = ((lon - minLon) / (maxLon - minLon)) * (mapWidth - 100) + 50;
            const y = canvasHeight - (((lat - minLat) / (maxLat - minLat)) * (canvasHeight - 100) + 50);
            return [x, y];
        }}

        function drawPolygon(rings) {{
            ctx.beginPath();
            rings.forEach(ring => {{
                ring.forEach((pt, i) => {{
                    const [px, py] = project(pt[0], pt[1]);
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }});
            }});
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        }}

        // Draw Deserts
        ctx.fillStyle = 'rgba(217, 119, 6, 0.25)';
        ctx.strokeStyle = '#b45309';
        ctx.lineWidth = 1.0;
        desertsData.features.forEach(feat => {{
            const g = feat.geometry;
            if (g.type === 'Polygon') drawPolygon(g.coordinates);
            else if (g.type === 'MultiPolygon') g.coordinates.forEach(drawPolygon);
        }});

        // Draw Mountain Zones
        ctx.fillStyle = 'rgba(245, 158, 11, 0.35)';
        ctx.strokeStyle = '#d97706';
        ctx.lineWidth = 1.2;
        mountainsData.features.forEach(feat => {{
            const g = feat.geometry;
            if (g.type === 'Polygon') drawPolygon(g.coordinates);
            else if (g.type === 'MultiPolygon') g.coordinates.forEach(drawPolygon);
        }});

        // Draw Level 1 Provinces
        paintedFeatures.forEach(feat => {{
            ctx.fillStyle = feat.color;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
            ctx.lineWidth = 1.2;
            const g = feat.geometry;
            if (g.type === 'Polygon') drawPolygon(g.coordinates);
            else if (g.type === 'MultiPolygon') g.coordinates.forEach(drawPolygon);
        }});

        // Draw Rivers (Major Rivers bold dark azure, minor streams light cyan)
        riversData.features.forEach(feat => {{
            const isMajor = feat.properties && feat.properties.is_major;
            ctx.strokeStyle = isMajor ? '#0284c7' : '#38bdf8';
            ctx.lineWidth = isMajor ? 3.0 : 1.2;
            const g = feat.geometry;
            const lines = g.type === 'LineString' ? [g.coordinates] : (g.type === 'MultiLineString' ? g.coordinates : []);
            lines.forEach(line => {{
                ctx.beginPath();
                line.forEach((pt, i) => {{
                    const [px, py] = project(pt[0], pt[1]);
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }});
                ctx.stroke();
            }});
        }});

        // Draw Legend Panel
        ctx.fillStyle = 'rgba(15, 23, 42, 0.98)';
        ctx.fillRect(mapWidth, 0, legendWidth, canvasHeight);
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(mapWidth, 0); ctx.lineTo(mapWidth, canvasHeight);
        ctx.stroke();

        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 30px Inter, sans-serif';
        ctx.fillText('🗺️ IMPERIAL CALIPHATE', mapWidth + 40, 60);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '16px Inter, sans-serif';
        ctx.fillText('The Pan-Islamic Super-Empire (670–850 CE)', mapWidth + 40, 92);
        ctx.fillText(`All Level-1 Units & Frontier Cuts (${{paintedFeatures.length}} Provinces)`, mapWidth + 40, 118);

        // Group by Realm for Legend
        const realmSummary = {{}};
        paintedFeatures.forEach(f => {{
            if (!realmSummary[f.realm]) {{
                realmSummary[f.realm] = {{ color: f.color, count: 0 }};
            }}
            realmSummary[f.realm].count++;
        }});

        let startY = 170;
        Object.entries(realmSummary).forEach(([rname, rinfo]) => {{
            if (startY > canvasHeight - 40) return;
            ctx.fillStyle = rinfo.color;
            ctx.fillRect(mapWidth + 40, startY - 18, 22, 22);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.2;
            ctx.strokeRect(mapWidth + 40, startY - 18, 22, 22);

            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 16px Inter, sans-serif';
            ctx.fillText(rname.length > 32 ? rname.substring(0, 30) + '..' : rname, mapWidth + 75, startY);

            ctx.fillStyle = '#94a3b8';
            ctx.font = '13px Inter, sans-serif';
            ctx.fillText(`${{rinfo.count}} provinces`, mapWidth + 75, startY + 18);
            startY += 48;
        }});

        // Trigger PNG Download
        const imgURI = canvas.toDataURL('image/png');
        const dl = document.createElement('a');
        dl.setAttribute('href', imgURI);
        dl.setAttribute('download', 'imperial_caliphate_level1_map.png');
        document.body.appendChild(dl);
        dl.click();
        dl.remove();
    }});

    // =========================================================================
    // FRONTIER SLICER & PROVINCE DIVIDER ENGINE
    // =========================================================================
    let isCutModeActive = false;
    let isRiverCutModeActive = false;
    let isBlankModeActive = false;
    let currentInspectedFeature = null;
    let lastClickedRiverFeat = null;
    let lastClickedRiverLatLng = null;
    let cutLineCoords = [];
    let cutLineLayer = null;
    let cutMarkerLayers = [];
    let activeSliceTarget = null;
    let slicePreviewLayers = [];
    let sliceHistory = [];

    function toggleBlankMode() {{
        isBlankModeActive = !isBlankModeActive;
        const btn = document.getElementById('btn-blank-mode');
        const badge = document.getElementById('slicer-status-badge');
        const banner = document.getElementById('cut-banner');

        if (isBlankModeActive) {{
            if (isCutModeActive) toggleCutDrawing();
            if (isRiverCutModeActive) toggleRiverCutMode();
            btn.classList.add('active');
            btn.innerHTML = '🛑 Stop Blank Mode';
            badge.className = 'badge-active';
            badge.textContent = 'Blank Mode Active';
            banner.innerHTML = `<span>🚫 <strong>Blank Mode Active:</strong> Click ANY province on the map to immediately blank it out and exclude it from the Empire!</span>
                <button class="btn btn-dark" onclick="toggleBlankMode()" style="padding:2px 10px; font-size:11px; margin-left:10px;">Done</button>`;
            banner.style.display = 'flex';
            document.getElementById('map').style.cursor = 'crosshair';
        }} else {{
            btn.classList.remove('active');
            btn.innerHTML = '🚫 Blank Mode';
            badge.className = 'badge-idle';
            badge.textContent = 'Ready';
            banner.style.display = 'none';
            document.getElementById('map').style.cursor = '';
        }}
    }}

    function blankFeature(feature) {{
        if (!feature) return;
        const p = feature.properties;
        sliceHistory.push(JSON.stringify(geojsonData));
        document.getElementById('btn-undo-cut').disabled = false;

        p.is_caliphate = false;
        p.realm = 'External World (Blanked Frontier)';
        p.initial_color = '#1e293b';
        p.painted_color = '#1e293b';
        divisionColors[p.id] = '#1e293b';

        renderUnits(geojsonData.features);
        updateInspector(feature, '#1e293b');
        showToast(`🚫 ${{p.name}} blanked out and excluded from the Empire.`);
    }}

    function restoreFeature(feature) {{
        if (!feature) return;
        const p = feature.properties;
        sliceHistory.push(JSON.stringify(geojsonData));
        document.getElementById('btn-undo-cut').disabled = false;

        p.is_caliphate = true;
        if (p.realm.includes('External World')) {{
            p.realm = 'Imperial Frontier (Restored)';
        }}
        const restCol = activeColor && activeColor !== '#1e293b' ? activeColor : '#0284c7';
        p.initial_color = restCol;
        p.painted_color = restCol;
        divisionColors[p.id] = restCol;

        renderUnits(geojsonData.features);
        updateInspector(feature, restCol);
        showToast(`✨ ${{p.name}} restored to Imperial Caliphate (Colorable)!`);
    }}

    function blankCurrentInspectedFeature() {{
        if (currentInspectedFeature) {{
            blankFeature(currentInspectedFeature);
        }}
    }}

    function restoreCurrentInspectedFeature() {{
        if (currentInspectedFeature) {{
            restoreFeature(currentInspectedFeature);
        }}
    }}

    function toggleRiverCutMode() {{
        isRiverCutModeActive = !isRiverCutModeActive;
        const btn = document.getElementById('btn-river-cut');
        const badge = document.getElementById('slicer-status-badge');
        const banner = document.getElementById('cut-banner');

        if (isRiverCutModeActive) {{
            if (isCutModeActive) toggleCutDrawing();
            btn.classList.add('active');
            btn.innerHTML = '🛑 Stop River Cut';
            badge.className = 'badge-active';
            badge.textContent = 'River Select Active';
            banner.innerHTML = `<span>🌊 <strong>River Slice Mode:</strong> Click ANY river on the map to slice the underlying province along that river channel!</span>
                <button class="btn btn-dark" onclick="toggleRiverCutMode()" style="padding:2px 10px; font-size:11px; margin-left:10px;">Cancel</button>`;
            banner.style.display = 'flex';
            document.getElementById('map').style.cursor = 'pointer';
        }} else {{
            btn.classList.remove('active');
            btn.innerHTML = '🌊 Cut Along River';
            badge.className = 'badge-idle';
            badge.textContent = 'Ready';
            banner.style.display = 'none';
            document.getElementById('map').style.cursor = '';
        }}
    }}

    function executeRiverSliceFromPopup() {{
        map.closePopup();
        if (lastClickedRiverFeat && lastClickedRiverLatLng) {{
            executeRiverSlice(lastClickedRiverFeat, lastClickedRiverLatLng);
        }}
    }}

    // Transboundary River Network Stitcher: connects river segments that share aliases
    // or touch at international/regional borders (e.g. Irtysh / Ertis / Ertix, Danube / Donau / Duna, etc.)
    const TRANSBOUNDARY_RIVER_ALIASES = [
        ['irtysh', 'ertis', 'ertix', 'black irtysh', 'kara irtysh'],
        ['danube', 'donau', 'duna', 'dunav', 'dunarea', 'dunărea'],
        ['rhine', 'rhein', 'rijn', 'waal', 'nederrijn', 'oude rijn'],
        ['syr darya', 'sayhun', 'sirdaryo', 'seyhun', 'naryn', 'kara darya'],
        ['amu darya', 'jayhun', 'panj', 'vakhsh', 'piandj'],
        ['indus', 'sindh', 'sindhu', 'mehran', 'panjnad'],
        ['ganges', 'ganga', 'padma', 'hooghly', 'bhagirathi'],
        ['brahmaputra', 'yarlung tsangpo', 'jamuna', 'tsangpo'],
        ['narmada', 'narbada'],
        ['volga', 'itil', 'atil'],
        ['don', 'tanais'],
        ['dnieper', 'dnipro'],
        ['dniester', 'nistru', 'dnister'],
        ['euphrates', 'firat', 'al-furat', 'furat'],
        ['tigris', 'dicle', 'dijla'],
        ['mekong', 'lancang'],
        ['salween', 'nu jiang', 'nu'],
        ['amur', 'heilong'],
        ['yellow river', 'huang he', 'huang'],
        ['yangtze', 'chang jiang', 'chang'],
        ['ob', 'katun', 'biya'],
        ['yenisey', 'yenisei', 'enisey']
    ];

    function getStitchedRiverLine(riverFeat, latlng, targetFeat) {{
        const clickLng = latlng.lng;
        const clickLat = latlng.lat;
        const bbox = turf.bbox(targetFeat);
        const minx = bbox[0] - 0.6;
        const miny = bbox[1] - 0.6;
        const maxx = bbox[2] + 0.6;
        const maxy = bbox[3] + 0.6;

        const clickedName = ((riverFeat.properties && riverFeat.properties.name) || '').toLowerCase().trim();

        // 1. Find alias group for multi-named river systems
        let aliasGroup = null;
        for (const grp of TRANSBOUNDARY_RIVER_ALIASES) {{
            if (grp.some(n => clickedName.includes(n) || n.includes(clickedName))) {{
                aliasGroup = grp;
                break;
            }}
        }}

        // 2. Collect all candidate river segments across riversData
        let candidateParts = [];
        riversData.features.forEach(rf => {{
            if (!rf.geometry) return;
            const rfn = ((rf.properties && rf.properties.name) || '').toLowerCase().trim();
            const isNameMatch = aliasGroup 
                ? aliasGroup.some(n => rfn.includes(n) || n.includes(rfn))
                : (rfn && clickedName && (rfn.includes(clickedName) || clickedName.includes(rfn)));

            let geomParts = [];
            if (rf.geometry.type === 'LineString') {{
                geomParts = [rf.geometry.coordinates];
            }} else if (rf.geometry.type === 'MultiLineString') {{
                geomParts = rf.geometry.coordinates;
            }}

            geomParts.forEach(pts => {{
                if (pts.length < 2) return;
                // Check if segment is in or near targetFeat bbox
                let nearBbox = false;
                const step = Math.max(1, Math.floor(pts.length / 8));
                for (let i = 0; i < pts.length; i += step) {{
                    const x = pts[i][0], y = pts[i][1];
                    if (x >= minx && x <= maxx && y >= miny && y <= maxy) {{
                        nearBbox = true;
                        break;
                    }}
                }}
                if (isNameMatch || nearBbox) {{
                    candidateParts.push(pts);
                }}
            }});
        }});

        if (candidateParts.length === 0) {{
            if (riverFeat.geometry.type === 'LineString') candidateParts = [riverFeat.geometry.coordinates];
            else if (riverFeat.geometry.type === 'MultiLineString') candidateParts = riverFeat.geometry.coordinates;
        }}

        // 3. Find candidate closest to click point
        let bestPart = candidateParts[0];
        let bestDist = Infinity;
        let bestIdx = 0;

        candidateParts.forEach((pts, pIdx) => {{
            for (let i = 0; i < pts.length; i++) {{
                const d = (pts[i][0] - clickLng) ** 2 + (pts[i][1] - clickLat) ** 2;
                if (d < bestDist) {{
                    bestDist = d;
                    bestPart = pts;
                    bestIdx = pIdx;
                }}
            }}
        }});

        // 4. Chain connected segments (snapping tolerance: ~5 km at borders/junctions)
        let chain = [...bestPart];
        let used = new Set([bestIdx]);
        const tolSq = 0.05 ** 2;

        let changed = true;
        let iterations = 0;
        while (changed && iterations < 60) {{
            changed = false;
            iterations++;
            for (let i = 0; i < candidateParts.length; i++) {{
                if (used.has(i)) continue;
                const c = candidateParts[i];
                if (c.length < 2) continue;

                const cStart = c[0];
                const cEnd = c[c.length - 1];
                const chainStart = chain[0];
                const chainEnd = chain[chain.length - 1];

                const d_end_start = (chainEnd[0] - cStart[0]) ** 2 + (chainEnd[1] - cStart[1]) ** 2;
                const d_end_end   = (chainEnd[0] - cEnd[0]) ** 2 + (chainEnd[1] - cEnd[1]) ** 2;
                const d_start_end = (chainStart[0] - cEnd[0]) ** 2 + (chainStart[1] - cEnd[1]) ** 2;
                const d_start_start = (chainStart[0] - cStart[0]) ** 2 + (chainStart[1] - cStart[1]) ** 2;

                if (d_end_start <= tolSq) {{
                    chain = chain.concat(c.slice(1));
                    used.add(i);
                    changed = true;
                    break;
                }} else if (d_end_end <= tolSq) {{
                    chain = chain.concat([...c].reverse().slice(1));
                    used.add(i);
                    changed = true;
                    break;
                }} else if (d_start_end <= tolSq) {{
                    chain = c.slice(0, -1).concat(chain);
                    used.add(i);
                    changed = true;
                    break;
                }} else if (d_start_start <= tolSq) {{
                    chain = [...c].reverse().slice(0, -1).concat(chain);
                    used.add(i);
                    changed = true;
                    break;
                }}
            }}
        }}

        // 5. Trim points that wander too far outside the province to keep the river cutter focused
        let trimMinX = bbox[0] - 1.2, trimMinY = bbox[1] - 1.2;
        let trimMaxX = bbox[2] + 1.2, trimMaxY = bbox[3] + 1.2;

        let inBboxIndices = [];
        for (let i = 0; i < chain.length; i++) {{
            const x = chain[i][0], y = chain[i][1];
            if (x >= bbox[0] - 0.2 && x <= bbox[2] + 0.2 && y >= bbox[1] - 0.2 && y <= bbox[3] + 0.2) {{
                inBboxIndices.push(i);
            }}
        }}

        let startTrim, endTrim;
        if (inBboxIndices.length > 0) {{
            startTrim = Math.max(0, inBboxIndices[0] - 8);
            endTrim = Math.min(chain.length - 1, inBboxIndices[inBboxIndices.length - 1] + 8);
        }} else {{
            // Find index of click point along the chain
            let clickIdx = 0, minClickDist = Infinity;
            for (let i = 0; i < chain.length; i++) {{
                const d = (chain[i][0] - clickLng) ** 2 + (chain[i][1] - clickLat) ** 2;
                if (d < minClickDist) {{
                    minClickDist = d;
                    clickIdx = i;
                }}
            }}
            startTrim = Math.max(0, clickIdx - 20);
            endTrim = Math.min(chain.length - 1, clickIdx + 20);
        }}

        const resultCoords = chain.slice(startTrim, endTrim + 1);
        return resultCoords.length >= 2 ? resultCoords : chain;
    }}

    function executeRiverSlice(riverFeat, latlng) {{
        const clickLng = latlng.lng;
        const clickLat = latlng.lat;
        const clickPt = turf.point([clickLng, clickLat]);

        // 1. Find intersecting / clicked province (prefer currently inspected province if active)
        let targetFeat = null;
        if (currentInspectedFeature && currentInspectedFeature.geometry) {{
            try {{
                if (turf.booleanIntersects(riverFeat, currentInspectedFeature) ||
                    turf.booleanPointInPolygon(clickPt, currentInspectedFeature)) {{
                    targetFeat = currentInspectedFeature;
                }}
            }} catch(e) {{}}
        }}

        if (!targetFeat) {{
            for (const feat of geojsonData.features) {{
                if (!feat.geometry) continue;
                try {{
                    if (turf.booleanPointInPolygon(clickPt, feat)) {{
                        targetFeat = feat;
                        break;
                    }}
                }} catch(e) {{}}
            }}
        }}

        if (!targetFeat) {{
            let bestDist = Infinity;
            for (const feat of geojsonData.features) {{
                if (!feat.geometry) continue;
                try {{
                    if (turf.booleanIntersects(riverFeat, feat)) {{
                        const c = turf.centroid(feat).geometry.coordinates;
                        const d = (c[0] - clickLng) ** 2 + (c[1] - clickLat) ** 2;
                        if (d < bestDist) {{
                            bestDist = d;
                            targetFeat = feat;
                        }}
                    }}
                }} catch(e) {{}}
            }}
        }}

        if (!targetFeat) {{
            showToast('⚠️ No province found under this river position.');
            return;
        }}

        // 2. Extract & Stitch Continuous Transboundary River Network across borders
        const riverCoords = getStitchedRiverLine(riverFeat, latlng, targetFeat);
        if (!riverCoords || riverCoords.length < 2) {{
            showToast('⚠️ Could not extract continuous river line.');
            return;
        }}
        const bbox = turf.bbox(targetFeat);

        // 4. Draw the cut line through the river line on the map
        cutLineCoords = riverCoords;
        if (cutLineLayer) {{
            map.removeLayer(cutLineLayer);
        }}
        cutLineLayer = L.polyline(cutLineCoords.map(c => [c[1], c[0]]), {{
            color: '#0284c7',
            weight: 5,
            opacity: 0.95,
            dashArray: '4, 4'
        }}).addTo(map);

        cutMarkerLayers.forEach(m => map.removeLayer(m));
        cutMarkerLayers = [];
        const m1 = L.circleMarker([cutLineCoords[0][1], cutLineCoords[0][0]], {{
            radius: 5, fillColor: '#38bdf8', fillOpacity: 1, color: '#ffffff', weight: 2
        }}).addTo(map);
        const m2 = L.circleMarker([cutLineCoords[cutLineCoords.length - 1][1], cutLineCoords[cutLineCoords.length - 1][0]], {{
            radius: 5, fillColor: '#38bdf8', fillOpacity: 1, color: '#ffffff', weight: 2
        }}).addTo(map);
        cutMarkerLayers = [m1, m2];

        // 5. Extend line endpoints to guarantee cutting across the province boundary
        const diag = Math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]);
        const extDist = Math.max(diag * 1.5, 2.5);
        const extendedCoords = extendLineCoords(riverCoords, extDist);
        const extendedLine = turf.lineString(extendedCoords);

        // 6. Divide the unit
        const sliceRes = sliceFeatureGeometry(targetFeat, extendedLine);
        if (!sliceRes || sliceRes.sideAPolys.length === 0 || sliceRes.sideBPolys.length === 0) {{
            showToast('⚠️ The river passes along the boundary of this province without bisecting it.');
            return;
        }}

        const geomA = sliceRes.sideAPolys.length === 1 ?
            {{ type: 'Polygon', coordinates: sliceRes.sideAPolys[0] }} :
            {{ type: 'MultiPolygon', coordinates: sliceRes.sideAPolys }};
        const geomB = sliceRes.sideBPolys.length === 1 ?
            {{ type: 'Polygon', coordinates: sliceRes.sideBPolys[0] }} :
            {{ type: 'MultiPolygon', coordinates: sliceRes.sideBPolys }};

        const featA = turf.feature(geomA);
        const featB = turf.feature(geomB);
        const areaA = Math.round(turf.area(featA) / 1000000);
        const areaB = Math.round(turf.area(featB) / 1000000);

        const rName = riverFeat.properties.name || riverFeat.properties.name_en || 'River';

        activeSliceTarget = {{
            origFeature: targetFeat,
            geomA: geomA,
            geomB: geomB,
            areaA: areaA,
            areaB: areaB,
            riverName: rName
        }};

        showSlicePreview(geomA, geomB);

        if (isRiverCutModeActive) {{
            toggleRiverCutMode();
        }}

        openSliceModal(`${{targetFeat.properties.name}} (along 🌊 ${{rName}})`, areaA, areaB);
        showToast(`🌊 River line drawn through ${{rName}}! Select how to partition ${{targetFeat.properties.name}}.`);
    }}

    function toggleCutDrawing() {{
        isCutModeActive = !isCutModeActive;
        const btn = document.getElementById('btn-start-cut');
        const badge = document.getElementById('slicer-status-badge');
        const banner = document.getElementById('cut-banner');
        const execBtn = document.getElementById('btn-exec-cut');

        if (isCutModeActive) {{
            btn.classList.add('active');
            btn.innerHTML = '🛑 Stop Drawing';
            badge.className = 'badge-active';
            badge.textContent = 'Drawing Active';
            banner.style.display = 'flex';
            document.getElementById('map').style.cursor = 'crosshair';
            map.doubleClickZoom.disable();
        }} else {{
            btn.classList.remove('active');
            btn.innerHTML = '✂️ Draw Cut Line';
            badge.className = 'badge-idle';
            badge.textContent = cutLineCoords.length > 0 ? `${{cutLineCoords.length}} pts placed` : 'Ready';
            banner.style.display = 'none';
            document.getElementById('map').style.cursor = '';
            map.doubleClickZoom.enable();
        }}
        execBtn.disabled = cutLineCoords.length < 2;
    }}

    function handleCutMapClick(e) {{
        if (!isCutModeActive) return;
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        cutLineCoords.push([lng, lat]);

        if (!cutLineLayer) {{
            cutLineLayer = L.polyline(cutLineCoords.map(c => [c[1], c[0]]), {{
                color: '#facc15',
                weight: 3.5,
                dashArray: '4, 4'
            }}).addTo(map);
        }} else {{
            cutLineLayer.setLatLngs(cutLineCoords.map(c => [c[1], c[0]]));
        }}

        const marker = L.circleMarker([lat, lng], {{
            radius: 4,
            fillColor: '#facc15',
            fillOpacity: 1,
            color: '#0f172a',
            weight: 1.5
        }}).addTo(map);
        cutMarkerLayers.push(marker);

        const badge = document.getElementById('slicer-status-badge');
        badge.textContent = `${{cutLineCoords.length}} pts placed`;
        document.getElementById('btn-exec-cut').disabled = cutLineCoords.length < 2;
    }}

    function cancelCutDrawing() {{
        isCutModeActive = false;
        if (isRiverCutModeActive) {{
            isRiverCutModeActive = false;
            const btnR = document.getElementById('btn-river-cut');
            if (btnR) {{
                btnR.classList.remove('active');
                btnR.innerHTML = '🌊 Cut Along River';
            }}
        }}
        if (isBlankModeActive) {{
            isBlankModeActive = false;
            const btnB = document.getElementById('btn-blank-mode');
            if (btnB) {{
                btnB.classList.remove('active');
                btnB.innerHTML = '🚫 Blank Mode';
            }}
        }}
        cutLineCoords = [];
        if (cutLineLayer) {{
            map.removeLayer(cutLineLayer);
            cutLineLayer = null;
        }}
        cutMarkerLayers.forEach(m => map.removeLayer(m));
        cutMarkerLayers = [];
        clearSlicePreviews();

        const btn = document.getElementById('btn-start-cut');
        btn.classList.remove('active');
        btn.innerHTML = '✂️ Draw Cut Line';
        const badge = document.getElementById('slicer-status-badge');
        badge.className = 'badge-idle';
        badge.textContent = 'Ready';
        document.getElementById('cut-banner').style.display = 'none';
        document.getElementById('btn-exec-cut').disabled = true;
        document.getElementById('map').style.cursor = '';
        map.doubleClickZoom.enable();
    }}

    function extendLineCoords(coords, dist) {{
        if (coords.length < 2) return coords;
        const n = coords.length;

        // Smooth lookback for start
        const p0 = coords[0];
        let idx0 = 1;
        for (let i = 1; i < n; i++) {{
            const d = Math.hypot(p0[0] - coords[i][0], p0[1] - coords[i][1]);
            if (d >= 0.12 || i === n - 1) {{
                idx0 = i;
                break;
            }}
        }}
        const dx0 = p0[0] - coords[idx0][0];
        const dy0 = p0[1] - coords[idx0][1];
        const len0 = Math.hypot(dx0, dy0);
        const extStart = len0 > 0 ? [p0[0] + (dx0 / len0) * dist, p0[1] + (dy0 / len0) * dist] : p0;

        // Smooth lookback for end
        const p1 = coords[n - 1];
        let idx1 = n - 2;
        for (let i = n - 2; i >= 0; i--) {{
            const d = Math.hypot(p1[0] - coords[i][0], p1[1] - coords[i][1]);
            if (d >= 0.12 || i === 0) {{
                idx1 = i;
                break;
            }}
        }}
        const dx1 = p1[0] - coords[idx1][0];
        const dy1 = p1[1] - coords[idx1][1];
        const len1 = Math.hypot(dx1, dy1);
        const extEnd = len1 > 0 ? [p1[0] + (dx1 / len1) * dist, p1[1] + (dy1 / len1) * dist] : p1;

        return [extStart, ...coords, extEnd];
    }}

    function getPointSideOfLine(px, py, lineCoords) {{
        let bestDist = Infinity;
        let bestSide = 0;
        for (let i = 0; i < lineCoords.length - 1; i++) {{
            const x1 = lineCoords[i][0], y1 = lineCoords[i][1];
            const x2 = lineCoords[i+1][0], y2 = lineCoords[i+1][1];
            const dx = x2 - x1, dy = y2 - y1;
            const segLenSq = dx * dx + dy * dy;
            if (segLenSq === 0) continue;
            const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / segLenSq));
            const projX = x1 + t * dx;
            const projY = y1 + t * dy;
            const distSq = (px - projX) ** 2 + (py - projY) ** 2;
            if (distSq < bestDist) {{
                bestDist = distSq;
                const cross = (px - x1) * dy - (py - y1) * dx;
                bestSide = cross >= 0 ? 1 : -1;
            }}
        }}
        return bestSide;
    }}

    function sliceFeatureGeometry(feature, extendedLine) {{
        let ribbon = null;
        try {{
            ribbon = turf.buffer(extendedLine, 0.00005, {{ units: 'degrees' }});
        }} catch(e) {{
            try {{
                ribbon = turf.buffer(extendedLine, 0.0001, {{ units: 'degrees' }});
            }} catch(e2) {{}}
        }}
        if (!ribbon) return null;

        const lineCoords = extendedLine.geometry.coordinates;

        let inputPolys = [];
        if (feature.geometry.type === 'Polygon') {{
            inputPolys = [feature.geometry.coordinates];
        }} else if (feature.geometry.type === 'MultiPolygon') {{
            inputPolys = feature.geometry.coordinates;
        }}

        let sideAPolys = [];
        let sideBPolys = [];

        for (const polyCoords of inputPolys) {{
            const subPoly = turf.polygon(polyCoords);
            let parts = [];
            let intersects = false;
            try {{
                intersects = turf.booleanIntersects(subPoly, ribbon);
            }} catch(e) {{ intersects = false; }}

            if (intersects) {{
                try {{
                    const diff = turf.difference(subPoly, ribbon);
                    if (diff && diff.geometry) {{
                        if (diff.geometry.type === 'Polygon') {{
                            parts = [diff.geometry.coordinates];
                        }} else if (diff.geometry.type === 'MultiPolygon') {{
                            parts = diff.geometry.coordinates;
                        }}
                    }} else {{
                        parts = [polyCoords];
                    }}
                }} catch(err) {{
                    parts = [polyCoords];
                }}
            }} else {{
                parts = [polyCoords];
            }}

            for (const pCoords of parts) {{
                const pFeat = turf.polygon(pCoords);
                let cent;
                try {{
                    cent = turf.centroid(pFeat).geometry.coordinates;
                }} catch(e) {{
                    cent = pCoords[0][0];
                }}
                const side = getPointSideOfLine(cent[0], cent[1], lineCoords);
                if (side >= 0) {{
                    sideAPolys.push(pCoords);
                }} else {{
                    sideBPolys.push(pCoords);
                }}
            }}
        }}

        // If geometric bisection occurred into 2+ pieces but winding curvature put all centroids on one side:
        if ((sideAPolys.length === 0 || sideBPolys.length === 0) && (sideAPolys.length + sideBPolys.length) >= 2) {{
            const allPolys = [...sideAPolys, ...sideBPolys];
            allPolys.sort((a, b) => turf.area(turf.polygon(b)) - turf.area(turf.polygon(a)));
            sideAPolys = [allPolys[0]];
            sideBPolys = [allPolys[1]];
            for (let i = 2; i < allPolys.length; i++) {{
                const cPoly = allPolys[i];
                try {{
                    const cCent = turf.centroid(turf.polygon(cPoly)).geometry.coordinates;
                    const centA = turf.centroid(turf.polygon(sideAPolys[0])).geometry.coordinates;
                    const centB = turf.centroid(turf.polygon(sideBPolys[0])).geometry.coordinates;
                    const distA = (cCent[0] - centA[0]) ** 2 + (cCent[1] - centA[1]) ** 2;
                    const distB = (cCent[0] - centB[0]) ** 2 + (cCent[1] - centB[1]) ** 2;
                    if (distA <= distB) sideAPolys.push(cPoly);
                    else sideBPolys.push(cPoly);
                }} catch(e) {{
                    sideAPolys.push(cPoly);
                }}
            }}
        }}

        return {{ sideAPolys, sideBPolys }};
    }}

    function showSlicePreview(geomA, geomB) {{
        clearSlicePreviews();
        const layerA = L.geoJSON(geomA, {{
            style: {{
                fillColor: '#0ea5e9',
                fillOpacity: 0.55,
                color: '#38bdf8',
                weight: 2.5
            }}
        }}).addTo(map);

        const layerB = L.geoJSON(geomB, {{
            style: {{
                fillColor: '#f43f5e',
                fillOpacity: 0.55,
                color: '#fb7185',
                weight: 2.5
            }}
        }}).addTo(map);

        slicePreviewLayers = [layerA, layerB];
    }}

    function clearSlicePreviews() {{
        slicePreviewLayers.forEach(l => map.removeLayer(l));
        slicePreviewLayers = [];
    }}

    function openSliceModal(name, areaA, areaB) {{
        document.getElementById('slice-unit-name').textContent = name;
        document.getElementById('portion-a-info').textContent = `Area: ~${{areaA.toLocaleString()}} km²`;
        document.getElementById('portion-b-info').textContent = `Area: ~${{areaB.toLocaleString()}} km²`;
        document.getElementById('slice-modal').style.display = 'flex';
    }}

    function closeSliceModal() {{
        document.getElementById('slice-modal').style.display = 'none';
        clearSlicePreviews();
    }}

    function executeCutLine() {{
        if (cutLineCoords.length < 2) {{
            showToast('⚠️ Please click at least 2 points across a province.');
            return;
        }}

        const cutLine = turf.lineString(cutLineCoords);

        let candidates = [];
        for (const feat of geojsonData.features) {{
            if (!feat.geometry) continue;
            try {{
                if (turf.booleanIntersects(cutLine, feat)) {{
                    candidates.push(feat);
                }}
            }} catch(e) {{}}
        }}

        if (candidates.length === 0) {{
            showToast('⚠️ No province intersects your cut line. Draw across a province.');
            return;
        }}

        candidates.sort((a, b) => {{
            if (a.properties.is_caliphate && !b.properties.is_caliphate) return -1;
            if (!a.properties.is_caliphate && b.properties.is_caliphate) return 1;
            return turf.area(b) - turf.area(a);
        }});
        const targetFeat = candidates[0];

        const bbox = turf.bbox(targetFeat);
        const diag = Math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]);
        const extDist = Math.max(diag * 0.8, 0.5);

        const extendedCoords = extendLineCoords(cutLineCoords, extDist);
        const extendedLine = turf.lineString(extendedCoords);

        const sliceRes = sliceFeatureGeometry(targetFeat, extendedLine);
        if (!sliceRes || sliceRes.sideAPolys.length === 0 || sliceRes.sideBPolys.length === 0) {{
            showToast('⚠️ The cut line did not divide this province into two parts. Please draw across the entire unit.');
            return;
        }}

        const geomA = sliceRes.sideAPolys.length === 1 ?
            {{ type: 'Polygon', coordinates: sliceRes.sideAPolys[0] }} :
            {{ type: 'MultiPolygon', coordinates: sliceRes.sideAPolys }};
        const geomB = sliceRes.sideBPolys.length === 1 ?
            {{ type: 'Polygon', coordinates: sliceRes.sideBPolys[0] }} :
            {{ type: 'MultiPolygon', coordinates: sliceRes.sideBPolys }};

        const featA = turf.feature(geomA);
        const featB = turf.feature(geomB);
        const areaA = Math.round(turf.area(featA) / 1000000);
        const areaB = Math.round(turf.area(featB) / 1000000);

        activeSliceTarget = {{
            origFeature: targetFeat,
            geomA: geomA,
            geomB: geomB,
            areaA: areaA,
            areaB: areaB
        }};

        showSlicePreview(geomA, geomB);
        openSliceModal(targetFeat.properties.name, areaA, areaB);
    }}

    function applySliceDecision(choice) {{
        if (!activeSliceTarget) return;
        const orig = activeSliceTarget.origFeature.properties;
        const geomA = activeSliceTarget.geomA;
        const geomB = activeSliceTarget.geomB;

        let isCaliphateA = true;
        let isCaliphateB = true;
        let realmA = orig.realm;
        let realmB = orig.realm;
        let defaultImpCol = activeColor && activeColor !== '#1e293b' ? activeColor : '#0284c7';
        let colorA = (divisionColors[orig.id] && divisionColors[orig.id] !== '#1e293b') ? divisionColors[orig.id] : defaultImpCol;
        let colorB = (divisionColors[orig.id] && divisionColors[orig.id] !== '#1e293b') ? divisionColors[orig.id] : defaultImpCol;
        let nameA = orig.name + ' (Portion A)';
        let nameB = orig.name + ' (Portion B)';

        const rivTag = activeSliceTarget && activeSliceTarget.riverName ? ' - ' + activeSliceTarget.riverName + ' Bank' : '';
        if (choice === 'keep_a_blank_b') {{
            isCaliphateA = true;
            isCaliphateB = false;
            nameA = orig.name + ' (Imperial Province' + rivTag + ')';
            nameB = orig.name + ' (Blanked Frontier' + rivTag + ')';
            realmA = orig.realm.includes('External') ? 'Imperial Frontier (Claimed)' : orig.realm;
            realmB = 'External World (Blanked Frontier)';
            colorA = colorA !== '#1e293b' ? colorA : '#0284c7';
            colorB = '#1e293b';
        }} else if (choice === 'keep_b_blank_a') {{
            isCaliphateA = false;
            isCaliphateB = true;
            nameA = orig.name + ' (Blanked Frontier' + rivTag + ')';
            nameB = orig.name + ' (Imperial Province' + rivTag + ')';
            realmB = orig.realm.includes('External') ? 'Imperial Frontier (Claimed)' : orig.realm;
            realmA = 'External World (Blanked Frontier)';
            colorA = '#1e293b';
            colorB = colorB !== '#1e293b' ? colorB : '#0284c7';
        }} else if (choice === 'keep_both') {{
            isCaliphateA = true;
            isCaliphateB = true;
            nameA = orig.name + (activeSliceTarget && activeSliceTarget.riverName ? ' (North/West of ' + activeSliceTarget.riverName + ')' : ' (Portion A)');
            nameB = orig.name + (activeSliceTarget && activeSliceTarget.riverName ? ' (South/East of ' + activeSliceTarget.riverName + ')' : ' (Portion B)');
            realmA = orig.realm.includes('External') ? 'Imperial Frontier (Unit A)' : orig.realm;
            realmB = orig.realm.includes('External') ? 'Imperial Frontier (Unit B)' : orig.realm;
            colorA = colorA !== '#1e293b' ? colorA : '#0284c7';
            colorB = '#10b981'; // Emerald green so both portions are immediately distinct on the UI!
        }} else if (choice === 'blank_both') {{
            isCaliphateA = false;
            isCaliphateB = false;
            nameA = orig.name + ' (Blanked Frontier A)';
            nameB = orig.name + ' (Blanked Frontier B)';
            realmA = 'External World (Blanked Frontier)';
            realmB = 'External World (Blanked Frontier)';
            colorA = '#1e293b';
            colorB = '#1e293b';
        }}

        const featA_obj = {{
            type: 'Feature',
            geometry: geomA,
            properties: {{
                id: orig.id + '_ptA_' + Date.now().toString().slice(-4),
                name: nameA,
                country: orig.country,
                country_code: orig.country_code,
                realm: realmA,
                initial_color: colorA,
                painted_color: colorA,
                is_caliphate: isCaliphateA,
                admin_level: orig.admin_level || 'Level-1 Province'
            }}
        }};

        const featB_obj = {{
            type: 'Feature',
            geometry: geomB,
            properties: {{
                id: orig.id + '_ptB_' + Date.now().toString().slice(-4),
                name: nameB,
                country: orig.country,
                country_code: orig.country_code,
                realm: realmB,
                initial_color: colorB,
                painted_color: colorB,
                is_caliphate: isCaliphateB,
                admin_level: orig.admin_level || 'Level-1 Province'
            }}
        }};

        divisionColors[featA_obj.properties.id] = colorA;
        divisionColors[featB_obj.properties.id] = colorB;

        sliceHistory.push(JSON.stringify(geojsonData));
        document.getElementById('btn-undo-cut').disabled = false;

        const idx = geojsonData.features.findIndex(f => f.properties.id === orig.id);
        if (idx !== -1) {{
            geojsonData.features.splice(idx, 1, featA_obj, featB_obj);
        }} else {{
            geojsonData.features.push(featA_obj, featB_obj);
        }}

        closeSliceModal();
        cancelCutDrawing();
        renderUnits(geojsonData.features);

        const choiceText = choice === 'keep_a_blank_b' ? 'Portion A kept in Empire; Portion B blanked out.'
            : choice === 'keep_b_blank_a' ? 'Portion B kept in Empire; Portion A blanked out.'
            : choice === 'keep_both' ? 'Both portions kept colorable.'
            : 'Both portions blanked out.';
        showToast('✂️ Slice applied! ' + choiceText);
    }}

    function undoLastCut() {{
        if (sliceHistory.length === 0) return;
        const prevJSON = sliceHistory.pop();
        const restoredData = JSON.parse(prevJSON);
        geojsonData.features = restoredData.features;
        renderUnits(geojsonData.features);
        document.getElementById('btn-undo-cut').disabled = sliceHistory.length === 0;
        showToast('↺ Last cut undone! Previous province boundary restored.');
    }}

    function showToast(msg) {{
        let t = document.getElementById('toast-notify');
        if (!t) {{
            t = document.createElement('div');
            t.id = 'toast-notify';
            t.className = 'toast-notify';
            document.body.appendChild(t);
        }}
        t.innerHTML = msg;
        t.style.display = 'block';
        setTimeout(() => {{
            t.style.display = 'none';
        }}, 4000);
    }}

    // Initial Render: Caliphate Realm Focus
    renderUnits(geojsonData.features.filter(f => f.properties.is_caliphate));
</script>

<!-- Slice Decision Modal -->
<div id="slice-modal" class="slice-modal-backdrop" style="display:none;">
    <div class="slice-modal-card">
        <div class="slice-modal-header">
            <h3>✂️ Unit Divided: <span id="slice-unit-name" style="color:#38bdf8;">Province</span></h3>
            <button class="close-modal-btn" onclick="closeSliceModal()">✕</button>
        </div>
        <p style="font-size:12px; color:#cbd5e1;">
            The administrative unit has been divided into two separate portions along your cut line. Choose how to assign each portion:
        </p>

        <div class="slice-choices-grid">
            <div class="slice-choice-card" style="border-color:#0284c7;">
                <div class="portion-badge" style="background:#0284c7;">Portion A (Cyan)</div>
                <div class="portion-details" id="portion-a-info">Area: ~... km²</div>
            </div>
            <div class="slice-choice-card" style="border-color:#e11d48;">
                <div class="portion-badge" style="background:#e11d48;">Portion B (Red)</div>
                <div class="portion-details" id="portion-b-info">Area: ~... km²</div>
            </div>
        </div>

        <div class="slice-actions-list">
            <button class="slice-action-btn btn-action-a" onclick="applySliceDecision('keep_a_blank_b')">
                <span class="action-icon">🚫</span>
                <div>
                    <strong>Keep Portion A in Empire & Blank Out Portion B</strong>
                    <div class="action-sub">Portion A stays a colorable imperial province; Portion B becomes uncolorable external frontier (#1e293b).</div>
                </div>
            </button>
            <button class="slice-action-btn btn-action-b" onclick="applySliceDecision('keep_b_blank_a')">
                <span class="action-icon">🚫</span>
                <div>
                    <strong>Keep Portion B in Empire & Blank Out Portion A</strong>
                    <div class="action-sub">Portion B stays a colorable imperial province; Portion A becomes uncolorable external frontier (#1e293b).</div>
                </div>
            </button>
            <button class="slice-action-btn btn-action-both" onclick="applySliceDecision('keep_both')">
                <span class="action-icon">🎨</span>
                <div>
                    <strong>Keep Both Portions as Separate Colorable Units</strong>
                    <div class="action-sub">Divides into two distinct colorable imperial provinces that can each be painted independently.</div>
                </div>
            </button>
            <button class="slice-action-btn btn-action-blank-both" onclick="applySliceDecision('blank_both')">
                <span class="action-icon">⬛</span>
                <div>
                    <strong>Permanently Blank Out Both Portions</strong>
                    <div class="action-sub">Turn both portions into uncolorable external frontier (#1e293b).</div>
                </div>
            </button>
        </div>

        <div style="text-align:right; margin-top:8px;">
            <button class="btn btn-dark" onclick="closeSliceModal()">Cancel Division</button>
        </div>
    </div>
</div>

<div id="toast-notify" class="toast-notify"></div>

</body>
</html>
"""

    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"  -> Generated standalone HTML application: {HTML_OUT}")
    print(f"  -> HTML File Size: {os.path.getsize(HTML_OUT) / (1024 * 1024):.2f} MB")

    # Mirror to frontend
    try:
        with open(FRONTEND_HTML_OUT, "w", encoding="utf-8") as ff:
            ff.write(html_content)
        print(f"  -> Mirrored to frontend: {FRONTEND_HTML_OUT}")
    except Exception as e:
        print(f"  [WARN] Could not mirror to frontend: {e}")

    elapsed = time.time() - t0
    print("=" * 80)
    print(f"  SUCCESSFULLY COMPILED IN {elapsed:.2f}s!")
    print("=" * 80)

if __name__ == "__main__":
    build_map()
