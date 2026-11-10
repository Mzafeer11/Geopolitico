"""
Eastern Expansion & Painted-Base Patcher
========================================
Loads the user's exported painted map (painted_imperial_level1_map.geojson),
preserving every manual slice / blank / paint, and then applies:

  1. Hungary fix: Komarom-Esztergom lies entirely SOUTH of the Danube
     (the Danube IS its northern border), so both river-split fragments are
     merged back into one colorable Pannonian province.
  2. Consolidated Eastern Frontier (beyond the Syr Darya):
       - Semirechye / Yeti-Su up to Lake Balkhash & the Chu river (KAZ)
       - Fergana & Tian Shan (KGZ)
       - Tarim Basin (Xinjiang) cut along natural lines:
            North : Borohoro range axis (Ili valley) -> Tian Shan main crest
            South : Karakoram -> Kunlun crest -> Altun Shan crest
            Internal divisions along the Yarkand / Tarim / Konqi rivers,
            the Aksu river and the Kuruk Tagh ridge
       - Dunhuang (Shazhou) oasis in Gansu, closed by the Danghe Nanshan
         (western Qilian) to the south and the Beishan/Gobi desert gap east
         of Dunhuang (between Shazhou and Guazhou) to the east.
  3. Historical Arabic / Islamicate province names for the Central Asian
     and eastern frontier units.
"""
import os
import json
from shapely.geometry import shape, mapping, LineString, Point
from shapely.ops import split, unary_union

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
PAINTED_BASE = os.path.join(ROOT_DIR, "painted_imperial_level1_map.geojson")

EXT_COLOR = "#1e293b"

REALM_SEMIRECHYE = "Semirechye & Syr Darya Marches (Isbijab, Taraz & Yeti-Su)"
REALM_FERGHANA = "Fergana Basin & Tien Shan (Farghana & Balasaghun)"
REALM_TARIM = "Tarim Basin & Silk Road Marches (Kashgar)"

COL_SEMIRECHYE = "#0f766e"
COL_FERGHANA = "#155e75"
COL_TARIM = "#b45309"


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------
def _clean(g):
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = g.buffer(0)
    return g


def _round(coords, p=4):
    if isinstance(coords, (list, tuple)):
        if coords and isinstance(coords[0], (int, float)):
            return [round(c, p) for c in coords]
        return [_round(c, p) for c in coords]
    return coords


def _feat(geom, uid, name, country, iso, realm, color, is_cal):
    geom = _clean(geom)
    if geom is None:
        return None
    geom = geom.simplify(0.01, preserve_topology=True)
    m = mapping(geom)
    return {
        "type": "Feature",
        "geometry": {"type": m["type"], "coordinates": _round(m["coordinates"])},
        "properties": {
            "id": uid, "name": name, "country": country, "iso": iso,
            "realm": realm, "initial_color": color, "is_caliphate": is_cal,
            "admin_level": "Level-1 Province", "painted_color": color,
        },
    }


def _side(pt, coords):
    """-1 = left of the directed polyline, +1 = right."""
    best, side = float("inf"), 0
    px, py = pt.x, pt.y
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        if L == 0:
            continue
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
        d = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
        if d < best:
            best = d
            side = -1 if ((px - x1) * dy - (py - y1) * dx) < 0 else 1
    return side


def cut(geom, coords):
    """Split geom by polyline; return (left_geom, right_geom)."""
    geom = _clean(geom)
    line = LineString(coords)
    try:
        res = split(geom, line)
        parts = list(res.geoms)
    except Exception:
        parts = [geom]
    left, right = [], []
    for p in parts:
        (left if _side(p.representative_point(), coords) < 0 else right).append(p)
    return (_clean(unary_union(left)) if left else None,
            _clean(unary_union(right)) if right else None)


def load_river(name):
    d = json.load(open(os.path.join(DATA_DIR, "ne_10m_rivers_lake_centerlines.geojson"), encoding="utf-8"))
    out = []
    for f in d["features"]:
        if f["properties"].get("name") == name and f["properties"].get("featurecla") == "River":
            g = shape(f["geometry"])
            for part in getattr(g, "geoms", [g]):
                out.append(list(part.coords))
    out.sort(key=len, reverse=True)
    return out[0] if out else []


# -----------------------------------------------------------------------------
# Natural frontier lines (axes derived from Natural Earth range polygons)
# -----------------------------------------------------------------------------
# NORTH: Dzungarian Alatau -> Borohoro axis (closing the Ili valley) -> Tian Shan
#        main crest (Bogda Shan, Karlik Tagh), W -> E
NORTH_LINE = [
    (78.5, 45.6), (80.2, 45.1), (81.0, 44.75), (81.5, 44.5), (82.0, 44.39), (82.5, 44.25),
    (83.0, 44.15), (83.5, 44.07), (84.0, 43.96), (84.5, 43.85), (85.0, 43.74),
    (85.5, 43.59), (86.0, 43.44), (86.5, 43.36), (87.0, 42.93), (87.5, 42.99),
    (88.0, 43.10), (88.5, 43.37), (89.0, 43.40), (89.5, 43.31), (90.0, 43.28),
    (90.5, 43.36), (91.0, 43.58), (91.5, 43.60), (92.0, 43.65), (92.5, 43.64),
    (93.0, 43.58), (93.5, 43.38), (94.0, 43.27), (94.5, 43.26), (95.0, 43.36),
    (96.0, 43.30), (98.0, 43.30),
]
# SOUTH: Karakoram (Khunjerab) -> Kunlun crest -> Altun Shan crest, W -> E
SOUTH_LINE = [
    (73.0, 37.2), (74.5, 37.05), (75.4, 36.85), (77.0, 36.85), (78.0, 36.72),
    (78.5, 36.59), (79.0, 36.53), (79.5, 36.39), (80.0, 36.18), (80.5, 35.95),
    (81.0, 35.82), (81.5, 35.82), (82.0, 35.95), (82.5, 36.04), (83.0, 36.08),
    (83.5, 36.11), (84.0, 36.21), (84.5, 36.30), (85.0, 36.40), (85.5, 36.49),
    (86.0, 36.59), (86.5, 37.30), (87.0, 37.96), (87.5, 38.01), (88.0, 38.10),
    (88.5, 38.20), (89.0, 38.29), (89.5, 38.36), (90.0, 38.42), (90.5, 38.50),
    (91.0, 38.52), (91.5, 39.01), (92.0, 39.05), (92.5, 39.08), (93.0, 39.04),
    (93.5, 38.95), (94.0, 38.95), (94.5, 39.48), (95.0, 39.58), (95.5, 39.70),
    (98.0, 39.70),
]
# Tian Shan main axis inside the zone (separates the Ili valley from Tarim), W -> E
TIANSHAN_AXIS = [
    (78.3, 41.75), (79.0, 41.94), (79.5, 42.04), (80.0, 42.14), (80.5, 42.24),
    (81.0, 42.35), (81.5, 42.45), (82.0, 42.55), (82.5, 42.61), (83.0, 42.66),
    (83.5, 42.72), (84.0, 42.86), (84.5, 42.99), (85.0, 42.97), (85.5, 42.96),
    (86.0, 42.94), (86.5, 42.93), (87.0, 42.93), (87.4, 43.4),
]
# Kuruk Tagh ridge (separates Turfan-Qumul from Qarashahr / Lop), NW -> SE
KURUK_TAGH = [
    (86.9, 43.2), (87.0, 42.93), (87.5, 42.30), (88.0, 41.95), (88.5, 41.65),
    (89.0, 41.45), (89.5, 41.20), (90.0, 40.90), (90.4, 40.55), (90.5, 39.9),
]
# East closure of the Dunhuang oasis: Beishan / Gobi desert gap between
# Shazhou (Dunhuang) and Guazhou, S -> N
DUNHUANG_EAST = [
    (95.10, 39.0), (95.15, 39.60), (95.30, 39.95), (95.22, 40.30), (95.38, 40.75),
    (95.30, 41.30), (95.50, 41.90), (95.40, 42.60), (95.50, 43.5),
]


def _frontier_zone(xmin=60.0, xmax=100.0):
    """Polygon between NORTH_LINE and SOUTH_LINE."""
    from shapely.geometry import Polygon
    ring = [(xmin, NORTH_LINE[0][1])] + NORTH_LINE + [(xmax, NORTH_LINE[-1][1]),
            (xmax, SOUTH_LINE[-1][1])] + SOUTH_LINE[::-1] + [(xmin, SOUTH_LINE[0][1])]
    return Polygon(ring).buffer(0)


# -----------------------------------------------------------------------------
# Historical Arabic / Islamicate names (Istakhri, Ibn Hawqal, Muqaddasi,
# Hudud al-Alam, Mahmud al-Kashghari)
# -----------------------------------------------------------------------------
HIST_NAMES = {
    # Kazakhstan
    "KAZ_Almaty_1": "Yeti-Su / Bilad al-Anhar al-Sab'a (Talkhiz, Qayaliq & the Ili) - to Lake Balkhash",
    "KAZ_Zhambyl_14": "Tiraz (Taraz) & Wadi Talas - Chu River March",
    "KAZ_SouthKazakhstan_12": "Isbijab (Ispijab / Sayram) & Shawghar",
    "KAZ_Qyzylorda_South_Syr_Darya": "Farab (Utrar) & Jand - Lower Sayhun",
    # Kyrgyzstan
    "KGZ_Chüy_3": "Balasaghun & Suyab (Wadi Chu)",
    "KGZ_Biškek_2": "Jul / Navekat (Bishkek Garrison)",
    "KGZ_Talas_8": "Atlakh (Upper Talas)",
    "KGZ_Ysyk-Köl_9": "Barskhan & Buhayrat Issigh-Kul",
    "KGZ_Naryn_5": "Arghu & At-Bashi (Tash-Rabat Passes)",
    "KGZ_Osh_6": "Ush (Osh) - Upper Farghana",
    "KGZ_Osh(city)_7": "Madinat Ush",
    "KGZ_Jalal-Abad_4": "Uzkand & Kasan - Eastern Farghana",
    "KGZ_Batken_1": "Asbara (Isfara) & Kand-i Badam Marches",
    # Uzbekistan
    "UZB_Samarqand_9": "Samarqand (Sughd)",
    "UZB_Buxoro_2": "Bukhara (Numijkath)",
    "UZB_Toshkent_12": "al-Shash (Binkath)",
    "UZB_ToshkentShahri_13": "Madinat al-Shash (Binkath)",
    "UZB_Xorazm_14": "Khwarazm (Kath & Gurganj)",
    "UZB_Qaraqalpaqstan_7": "Khwarazm al-Shimali & Buhayrat Khwarazm (Aral)",
    "UZB_Qashqadaryo_8": "Kash (Kish) & Nasaf",
    "UZB_Surxondaryo_11": "al-Saghaniyan & Tirmidh",
    "UZB_Jizzax_4": "Usrushana al-Gharbiyya (Dizak)",
    "UZB_Sirdaryo_10": "Ilaq & Banakath (Sayhun Crossing)",
    "UZB_Navoiy_6": "Karmina & Dabusiyya",
    "UZB_Andijon_1": "Andukan - Central Farghana",
    "UZB_Fargona_3": "Farghana (Marghinan & Quba)",
    "UZB_Namangan_5": "Akhsikath - Farghana Capital",
    # Tajikistan
    "TJK_Sughd_5": "Usrushana & Khujanda",
    "TJK_Dushanbe_2": "Khuttal al-Shimali (Dushanbe)",
    "TJK_Khatlon_4": "al-Khuttal (Hulbuk & Munk)",
    "TJK_DistrictsofRepublicanSubordin_1": "Rasht & Wakhsh (Upper Khuttal)",
    "TJK_Gorno-Badakhshan_3": "Badakhshan al-'Ulya & Wakhan (Pamir Marches)",
    # Turkmenistan
    "TKM_Mary_6": "Marw al-Shahijan (Merv)",
    "TKM_Ahal_1": "Nasa & Abiward",
    "TKM_Aşgabat_2": "Nasa (Ashgabat)",
    "TKM_Balkan_3": "Dihistan & Balkhan",
    "TKM_Daşoguz_4": "Khwarazm al-Janubi (Gurganj Marches)",
    "TKM_Lebap_5": "Amul al-Shatt (Amul & Zamm)",
}


# -----------------------------------------------------------------------------
# Full-country mode: every Level-1 province of these countries is restored to
# its complete (uncut) shape and made colorable, so the user can decide the
# frontier with the in-browser Slicer tool (cut -> keep / blank).
# -----------------------------------------------------------------------------
import re

FULL_COUNTRIES = {
    "IND": ("India", "Frontier Marches - al-Hind (Customizable)", "#9a3412"),
    "KAZ": ("Kazakhstan", "Frontier Marches - Dasht-i Qipchaq (Customizable)", "#3f6212"),
    "CHN": ("China", "Frontier Marches - al-Sin (Customizable)", "#854d0e"),
    "RU": ("Russia", "Frontier Marches - Bilad al-Khazar & al-Saqaliba (Customizable)", "#312e81"),
    "RUS": ("Russia", "Frontier Marches - Bilad al-Khazar & al-Saqaliba (Customizable)", "#312e81"),
}

ALLOWED_IND_PATTERNS = [
    r"punjab", r"haryana", r"himachal", r"uttarakhand", r"uttaranchal",
    r"rajasthan", r"gujarat", r"uttar\s*pradesh", r"bihar", r"madhya\s*pradesh",
    r"delhi", r"chandigarh", r"jammu", r"kashmir", r"ladakh"
]

ALLOWED_RU_KZ_BORDER = [
    "astrakhan", "volgograd", "saratov", "samara", "orenburg",
    "chelyabinsk", "kurgan", "tyumen", "omsk", "novosibirsk",
    "altay", "gorno-altay", "altai"
]

REMOVED_COUNTRIES = {
    "nepal", "bhutan", "myanmar", "burma",
    "bangladesh", "sudan", "south sudan", "somalia", "somali", "somaliland",
    "czech republic", "czechia", "czech"
}
REMOVED_ISOS = {
    "NPL", "BTN", "MMR", "NP", "BT", "MM",
    "BGD", "BD", "SDN", "SSD", "SD", "SOM", "SO",
    "CZE", "CZ"
}

HISTORICAL_RENAMES = {
    # India (al-Hind Marches)
    'FULL_IND_Punjab': ('al-Bunjab al-Sharqi & Jalandhar Doab (Amritsar, Lahore & Sirhind) [Punjab]', 'Indus Valley & al-Sind (Mansura & Multan)'),
    'EXT_IND_Haryana_13': ('Thanesar & Karnal (Kurukshetra Plains & Panipat Gateway) [Haryana]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_NCTofDelhi_28': ('Madinat Dihli (Indraprastha Citadel & Yamuna Gateway) [Delhi]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_Chandigarh_7': ('Chandigarh Marches (Siwalik Foothills Gate) [Chandigarh]', 'Northern & Western India (al-Hind Marches)'),
    'FULL_IND_HimachalPradesh': ('Jibal Trigarta & Nagarkot (Kangra Valley & Kulu Marches) [Himachal Pradesh]', 'Northern & Western India (al-Hind Marches)'),
    'FULL_IND_Uttarakhand_ptA_3015': ('Jibal Himavant & Kedarkhand (Upper Ganges / Garhwal & Kumaon) [Uttarakhand]', 'Northern & Western India (al-Hind Marches)'),
    'FULL_IND_Rajasthan': ('Bilad al-Raja & Marwar (Jaisalmer, Ajmer & Bikaner) [Rajasthan]', 'Northern & Western India (al-Hind Marches)'),
    'FULL_IND_Gujarat_ptA_8485': ('al-Jurz & Saurashtra (Kambaya, Valabhi & Somnath - North of Tapi) [North Gujarat]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_MadhyaPradesh_22_ptA_4403_ptA_4530': ('Malwa & Bilad Ujjayn (Mandu, Dhar & Gwalior - North Narmada Basin) [Madhya Pradesh]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_UttarPradesh_37_ptA_2360_ptB_1054': ('al-Hind al-Wusta & Awadh (Qannawj, Varanasi & Lucknow - North Ganges) [Uttar Pradesh]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_Bihar_6_ptA_0387_ptA_5616': ('Tirhut & Mithila (Vaishali & Champaran - North of Ganges & Son) [North Bihar]', 'Northern & Western India (al-Hind Marches)'),
    'EXT_IND_Bihar_6_ptA_0387_ptB_5616': ('Magadha & Pataliputra (Azimabad, Nalanda & Gaya - South of Son) [South Bihar]', 'Northern & Western India (al-Hind Marches)'),
    'FULL_IND_Jammu_and_Kashmir_and_Ladakh': ('Kashmir & Bolor (Wadi Kashmir, Srinagar, Zanskar & Ladakh)', 'Northern & Western India (al-Hind Marches)'),

    # China (Xinjiang / Tarim & Silk Road)
    'FULL_CHN_Xinjiang': ('Kashgharia & Bilad al-Sin al-Gharbiyya (Tarim Basin, Kashgar, Khotan & Almaliq) [Xinjiang]', 'Tarim Basin & Silk Road Marches (Kashgar)'),

    # Kazakhstan (Dasht-i Qipchaq & Semirechye)
    'FULL_KAZ_Qyzylorda': ('Farab (Utrar), Jand & Yangikent (Lower Sayhun Basin) [Qyzylorda]', 'Transoxiana (Merv & Karakum)'),
    'EXT_KAZ_Atyrau_4_ptB_6121': ('Saray-Juk & al-Yaik al-Sharqi (Lower Ural Delta & Caspian Steppe) [East Atyrau]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_WestKazakhstan_13_ptB_6946': ('Oral & Wadi al-Yaik al-Janubi (South Ural Basin Steppe) [East West-Kazakhstan]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Pavlodar_8_ptB_5952': ('Bilad al-Kimak & Irtish al-Janubi (South Irtysh Steppe) [East Pavlodar]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Qostanay_10_ptA_0075': ('Torgay & Tubul al-Sharqi (East Tobol Steppe Basin) [East Qostanay]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Qostanay_10_ptB_0075_ptA_2786': ('Bilad al-Tubul & Kipchak Gateway (Tobol River Bank) [Qostanay Tobol]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Mangghystau_6': ('Siyah-Kuh & Jazirat Mankishlak (Caspian Peninsula) [Mangghystau]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Aqtöbe_3': ('Jabal Mugodzhar & Dasht-i Qipchaq al-Gharbi (Aqtöbe Steppe) [Aqtöbe]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Aqmola_2': ('Wadi al-Isil al-Awsat & Dasht-i Qipchaq (Ishim River Steppe) [Aqmola]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_Qaraghandy_9': ('Saryarka & Betpak-Dala (Central Steppe Plateau) [Qaraghandy]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_NorthKazakhstan_7': ('Wadi al-Isil al-A\'la & Qyzyljar (Upper Ishim Steppe) [North Kazakhstan]', 'Frontier Marches - Dasht-i Qipchaq'),
    'EXT_KAZ_EastKazakhstan_5': ('Jibal al-Altai al-Gharbi & Buhayrat Zaysan (Upper Irtysh Basin) [East Kazakhstan]', 'Frontier Marches - Dasht-i Qipchaq'),

    # Russia (Borderland Marches)
    'EXT_RU_Kurgan_1383_ptA_5423': ('Thaghr al-Tubul al-Gharbi (West Tobol Forest-Steppe March) [West Kurgan]', 'Frontier Marches - Bilad al-Khazar & al-Saqaliba'),
    'EXT_RU_Omsk_1384_ptA_9984': ('Thaghr al-Irtish al-Gharbi (West Irtysh Forest-Steppe March) [West Omsk]', 'Frontier Marches - Bilad al-Khazar & al-Saqaliba'),
    'EXT_RU_Orenburg_1390_ptA_2889_ptB_0637': ('Thaghr al-Yaik & Sakmara (Orenburg Ural Gate March) [Orenburg Gate]', 'Frontier Marches - Bilad al-Khazar & al-Saqaliba'),
    'EXT_RU_Orenburg_1390_ptB_2889_ptA_2734': ('Dasht al-Yaik al-Shimali (Southern Ural Foothills March) [Orenburg Foothills]', 'Frontier Marches - Bilad al-Khazar & al-Saqaliba'),
    'EXT_RU_Tyumen_1382_ptA_3265_ptB_1661': ('Majma\' al-Nahrayn: al-Tubul wa al-Irtish (Tyumen-Tobolsk Confluence March) [Tyumen]', 'Frontier Marches - Bilad al-Khazar & al-Saqaliba')
}


def is_ru_border(name):
    clean = name.lower()
    if "tomsk" in clean and "omsk" not in clean.replace("tomsk", ""):
        return False
    for r in ALLOWED_RU_KZ_BORDER:
        if r == "omsk":
            if re.search(r"\bomsk\b", clean) or clean.startswith("omsk"):
                return True
        elif r in clean:
            return True
    return False


def is_ind_allowed(name):
    clean = name.lower()
    return any(re.search(pat, clean) for pat in ALLOWED_IND_PATTERNS)


def _group_key(p):
    iso, uid, name = p.get("iso"), p["id"], p["name"]
    if iso == "CHN" and ("XJ_" in uid or "Xinjiang" in uid):
        return "Xinjiang"
    if iso == "CHN" and ("Gansu" in uid or "GS_" in uid):
        return "Gansu"
    if iso == "IND" and ("Jammu" in uid or "Ladakh" in uid):
        return "Jammu & Kashmir and Ladakh"
    if "[" in name and name.endswith("]"):
        return name[name.rfind("[") + 1:-1]
    return name.split(" (")[0].strip()


def restore_full_countries(feats):
    groups, keep = {}, []
    for f in feats:
        p = f["properties"]
        iso = (p.get("iso") or "").upper()
        country = (p.get("country") or "").lower()

        # Remove Nepal, Bhutan, Myanmar, Bangladesh, Sudan, Somalia
        if any(rc in country for rc in REMOVED_COUNTRIES) or iso in REMOVED_ISOS:
            continue

        if iso in FULL_COUNTRIES:
            groups.setdefault((iso, _group_key(p)), []).append(f)
        else:
            keep.append(f)

    for (iso, key), members in sorted(groups.items()):
        # Filter China: ONLY Xinjiang
        if iso == "CHN":
            if "xinjiang" not in key.lower() and not any("xinjiang" in m["properties"]["name"].lower() for m in members):
                continue

        # Filter India: ONLY Punjab, Haryana, Himachal, Uttarakhand, Rajasthan, Gujarat, UP, Bihar, MP (+ Delhi, Chandigarh, J&K)
        if iso == "IND":
            if not is_ind_allowed(key) and not any(is_ind_allowed(m["properties"]["name"]) for m in members):
                continue

        # Filter Russia: ONLY provinces bordering Kazakhstan
        if iso in ("RU", "RUS"):
            if not is_ru_border(key) and not any(is_ru_border(m["properties"]["name"]) for m in members):
                continue

        country, frontier_realm, frontier_col = FULL_COUNTRIES[iso]
        imperial = [m for m in members if m["properties"].get("is_caliphate")]
        if len(members) == 1:
            p = members[0]["properties"]
            if not p.get("is_caliphate"):
                p["is_caliphate"] = True
                p["realm"] = frontier_realm
                p["initial_color"] = frontier_col
                p["painted_color"] = frontier_col
                p["name"] = f"{key} (Frontier - draw your own line)"
            keep.append(members[0])
            continue
        geom = unary_union([_clean(shape(m["geometry"])) for m in members])
        if imperial:
            ip = imperial[0]["properties"]
            realm, col = ip["realm"], ip.get("painted_color") or ip["initial_color"]
        else:
            realm, col = frontier_realm, frontier_col
        uid = f"FULL_{iso}_{key.replace(' ', '_').replace('&', 'and')}"
        f = _feat(geom, uid, f"{key} (Full Province - draw your own line)", country, iso, realm, col, True)
        if f:
            keep.append(f)

    n = sum(1 for f in keep if f["properties"].get("iso") in FULL_COUNTRIES)
    print(f"  [eastern] Filtered Full India / Kazakhstan / China / Russia: {n} custom border provinces retained")
    return keep


def get_ancient_region(p):
    c = p.get("country")
    iso = (p.get("iso") or "").upper()
    pid = p.get("id", "")

    if c in ("Spain", "Portugal") or iso in ("ESP", "PRT"):
        return ("al-Andalus (Hispania & Gharb al-Andalus)", "#059669")
    if c in ("France", "Belgium", "Luxembourg", "Netherlands") or iso in ("FRA", "BEL", "LUX", "NLD"):
        return ("Gaul & Septimania (Gallia & Ard Ifranja)", "#0d9488")
    if c in ("Switzerland", "Austria", "Germany", "Liechtenstein") or iso in ("CHE", "AUT", "DEU", "LIE"):
        return ("Raetia & Alpine Marches (Jibal al-Alp & Noricum)", "#0284c7")
    if c in ("Italy", "Malta", "SanMarino") or iso in ("ITA", "MLT", "SMR"):
        return ("Italia & al-Siqilliyya (Italy, Rome & the Islands)", "#e11d48")
    if c in ("Slovenia", "Croatia", "BosniaandHerzegovina", "Montenegro", "Albania", "Kosovo") or iso in ("SVN", "HRV", "BIH", "MNE", "ALB", "XKO"):
        return ("Illyricum & Dalmatia (Adriatic Marches)", "#4338ca")
    if c in ("Hungary", "Slovakia", "Republic of Serbia", "Romania") or iso in ("HUN", "SVK", "SRB", "ROU"):
        return ("Pannonia & Danube Marches (Thughur al-Danub)", "#4f46e5")
    if c in ("Greece", "NorthMacedonia", "Bulgaria") or iso in ("GRC", "MKD", "BGR"):
        return ("al-Yunan & Thracia (Greece, Macedonia & Aegean)", "#6366f1")
    if c in ("Turkey", "Cyprus") or iso in ("TUR", "CYP"):
        return ("Anatolia & al-Qustantiniyya (Asia Minor / Bilad al-Rum)", "#9333ea")
    if c in ("Armenia", "Azerbaijan", "Georgia") or iso in ("ARM", "AZE", "GEO"):
        return ("al-Qabq & Shirvan (Caucasus Marches / Armenia & Arran)", "#a855f7")
    if c in ("Syria", "Lebanon", "Jordan", "Palestine", "Israel") or iso in ("SYR", "LBN", "JOR", "PSE", "ISR"):
        return ("Bilad al-Sham (The Levant / Dimashq, al-Quds & Hims)", "#2563eb")
    if c in ("Iraq", "Kuwait") or iso in ("IRQ", "KWT"):
        return ("Mesopotamia (al-Iraq wa al-Jazira / Kufa & Wasit)", "#0369a1")
    if c == "Egypt" or iso == "EGY":
        return ("Misr (Egypt, Nile Valley & al-Iskandariyya)", "#f59e0b")
    if c == "Libya" or iso == "LBY":
        return ("Barqa & Tripoli (Cyrenaica & Tripolitania)", "#d97706")
    if c == "Tunisia" or iso == "TUN":
        return ("Ifriqiya (Tunisia, Carthage & Qayrawan)", "#b45309")
    if c == "Algeria" or iso == "DZA":
        return ("al-Maghrib al-Awsat (Central Maghreb / Tahert & Tlemcen)", "#ca8a04")
    if c == "Morocco" or iso == "MAR":
        return ("al-Maghrib al-Aqsa (Far Maghreb / Fes & Tangier)", "#eab308")
    if c == "Ethiopia" or iso == "ETH":
        return ("al-Habasha & the Horn (Horn of Africa Marches)", "#854d0e")
    if c == "SaudiArabia" or iso == "SAU":
        return ("al-Hijaz & Bilad al-Arab (Makkah, Madinah & Najd)", "#16a34a")
    if c == "Yemen" or iso == "YEM":
        return ("al-Yaman & Hadhramaut (South Arabia / Sana'a & Aden)", "#15803d")
    if c in ("Oman", "UnitedArabEmirates", "Qatar", "Bahrain") or iso in ("OMN", "ARE", "QAT", "BHR"):
        return ("Oman & al-Bahrayn (Eastern Arabia & Persian Gulf)", "#166534")
    if c == "Iran" or iso == "IRN":
        return ("Bilad Faris & al-Jibal (Persian Plateau / Fars, Rayy & Isfahan)", "#f97316")
    if c == "Afghanistan" or iso == "AFG":
        return ("Khurasan al-Kubra (Greater Khorasan, Balkh & Kabul)", "#ea580c")
    if c in ("Uzbekistan", "Tajikistan", "Turkmenistan") or iso in ("UZB", "TJK", "TKM") or pid == "FULL_KAZ_Qyzylorda":
        return ("Mawara al-Nahr (Transoxiana / Samarqand, Bukhara & Khwarazm)", "#0891b2")
    if c == "Kyrgyzstan" or iso == "KGZ" or pid in ("KAZ_Almaty_1", "KAZ_SouthKazakhstan_12", "KAZ_Zhambyl_14"):
        return ("Farghana & Yeti-Su (Fergana Basin & Semirechye)", "#0f766e")
    if c == "Russia" or iso in ("RUS", "RU") or c == "Kazakhstan" or iso == "KAZ":
        return ("Dasht-i Qipchaq & Bilad al-Khazar (Caspian Steppe & Ural Marches)", "#3f6212")
    if c == "China" or iso == "CHN":
        return ("Kashgharia & the Tarim Basin (Silk Road Marches)", "#a16207")
    if c == "Pakistan" or iso == "PAK":
        return ("al-Sind & the Indus Valley (Mansura, Daybul & Multan)", "#ec4899")
    if c == "India" or iso == "IND":
        return ("Northern & Western India (al-Hind Marches & Gangetic Basin)", "#9a3412")

    return ("Imperial Caliphate March", "#64748b")


def build_from_painted_base(fallback_features):
    if not os.path.exists(PAINTED_BASE):
        print("  [eastern] painted base not found, keeping freshly built provinces")
        return fallback_features

    print(f"  [eastern] Loading painted base: {PAINTED_BASE}")
    base = json.load(open(PAINTED_BASE, encoding="utf-8"))["features"]
    final_imperial = []
    for f in base:
        p = f["properties"]
        is_cal = p.get("is_caliphate", False)
        col = p.get("painted_color") or p.get("initial_color")
        iso = (p.get("iso") or "").upper()
        country = (p.get("country") or "").lower()

        # Discard unpainted/blanked portions and external world
        if not is_cal or col == EXT_COLOR:
            continue
        # Discard removed countries (Czechia, Bangladesh, Sudan, Somalia, Myanmar, Nepal, Bhutan)
        if any(rc in country for rc in REMOVED_COUNTRIES) or iso in REMOVED_ISOS:
            continue

        pid = p.get("id")
        if pid in HISTORICAL_RENAMES:
            p["name"], _ = HISTORICAL_RENAMES[pid]
        elif pid in HIST_NAMES:
            modern = p["name"].split(" (")[0]
            p["name"] = f"{HIST_NAMES[pid]} [{modern}]"

        if " - draw your own line" in p["name"]:
            p["name"] = p["name"].replace(" (Frontier - draw your own line)", "").replace(" (Full Province - draw your own line)", "")

        # Color the regions as ancient regions (cohesive historical geography)
        reg_name, reg_color = get_ancient_region(p)
        p["realm"] = reg_name
        p["initial_color"] = reg_color
        p["painted_color"] = reg_color

        final_imperial.append(f)

    # Overwrite PAINTED_BASE with the pure imperial collection
    with open(PAINTED_BASE, "w", encoding="utf-8") as f_pb:
        json.dump({"type": "FeatureCollection", "total_provinces": len(final_imperial), "features": final_imperial}, f_pb)
    print(f"  [eastern] Kept {len(final_imperial)} pure Imperial Caliphate provinces colored as ancient regions")
    return final_imperial


if __name__ == "__main__":
    feats = build_from_painted_base([])
    print(f"Total pure imperial units: {len(feats)}")


