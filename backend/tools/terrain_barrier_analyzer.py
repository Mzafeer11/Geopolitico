"""
Terrain & Geographic Barrier Analyzer for Geopolitico Simulation Engine.
Scores candidate provinces/historical units using GMBA mountain ranges, ridge lines,
major rivers, and desert polygons, and automatically bisects historical units cut by
major rivers into independently scored near-bank and far-bank sub-provinces.
"""

import os
import json
import math
from typing import Dict, List, Any, Optional, Tuple, Set
from shapely.geometry import shape, LineString, MultiLineString, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, linemerge, split, nearest_points
from shapely.strtree import STRtree

from backend.config import DATA_DIR


# Canonical river aliases so segments with local names merge into a single continuous river
RIVER_ALIASES: Dict[str, str] = {
    "danube": "Danube", "donau": "Danube", "dunav": "Danube", "duna": "Danube", "dunarea": "Danube",
    "rhine": "Rhine", "rhein": "Rhine", "rhin": "Rhine", "waal": "Rhine", "nederrijn": "Rhine",
    "loire": "Loire",
    "rhône": "Rhône", "rhone": "Rhône", "roten": "Rhône",
    "seine": "Seine",
    "garonne": "Garonne",
    "elbe": "Elbe", "labe": "Elbe",
    "oder": "Oder", "odra": "Oder",
    "vistula": "Vistula", "wisła": "Vistula", "wisla": "Vistula",
    "po": "Po",
    "tiber": "Tiber", "tevere": "Tiber",
    "adige": "Adige",
    "ebro": "Ebro",
    "tagus": "Tagus", "tajo": "Tagus", "tejo": "Tagus",
    "douro": "Douro", "duero": "Douro",
    "guadiana": "Guadiana",
    "guadalquivir": "Guadalquivir",
    "sava": "Sava",
    "drava": "Drava", "drau": "Drava",
    "tisza": "Tisza", "tisa": "Tisza",
    "maritsa": "Maritsa", "evros": "Maritsa", "meriç": "Maritsa",
    "vardar": "Vardar", "axios": "Vardar",
    "dnieper": "Dnieper", "dnipro": "Dnieper", "dnepr": "Dnieper",
    "dniester": "Dniester", "dnister": "Dniester",
    "don": "Don",
    "volga": "Volga", "itil": "Volga",
    "ural": "Ural", "yaik": "Ural", "zhayyq": "Ural",
    "irtysh": "Irtysh", "ertis": "Irtysh", "irtish": "Irtysh",
    "tobol": "Tobol", "tubul": "Tobol",
    "ishim": "Ishim", "esil": "Ishim",
    "euphrates": "Euphrates", "furat": "Euphrates", "fırat": "Euphrates",
    "tigris": "Tigris", "dijla": "Tigris", "dicle": "Tigris",
    "nile": "Nile", "blue nile": "Blue Nile", "white nile": "White Nile",
    "amu darya": "Amu Darya", "oxus": "Amu Darya", "jayhun": "Amu Darya", "panj": "Amu Darya",
    "syr darya": "Syr Darya", "jaxartes": "Syr Darya", "sayhun": "Syr Darya", "naryn": "Syr Darya",
    "tarim": "Tarim", "yarkant": "Yarkand", "yarkand": "Yarkand",
    "helmand": "Helmand",
    "indus": "Indus", "sindhu": "Indus",
    "sutlej": "Sutlej", "satluj": "Sutlej",
    "chenab": "Chenab",
    "jhelum": "Jhelum",
    "ravi": "Ravi",
    "beas": "Beas",
    "ganges": "Ganges", "ganga": "Ganges", "padma": "Ganges",
    "yamuna": "Yamuna", "jamuna": "Yamuna",
    "son": "Son",
    "narmada": "Narmada",
    "tapi": "Tapi", "tapti": "Tapi",
    "godavari": "Godavari",
    "brahmaputra": "Brahmaputra",
}

# Major strategic frontier rivers eligible for automatic province bisection
MAJOR_FRONTIER_RIVERS: Set[str] = {
    "Danube", "Rhine", "Loire", "Rhône", "Elbe", "Oder", "Po", "Ebro", "Tagus",
    "Guadalquivir", "Sava", "Drava", "Tisza", "Maritsa", "Dnieper", "Don", "Volga",
    "Ural", "Irtysh", "Tobol", "Euphrates", "Tigris", "Nile", "Amu Darya", "Syr Darya",
    "Tarim", "Indus", "Sutlej", "Chenab", "Narmada", "Tapi", "Ganges", "Yamuna", "Son"
}


def _canonical_river_name(raw_name: str) -> Optional[str]:
    if not raw_name:
        return None
    low = raw_name.lower().strip()
    for suffix in [" river", " río", " rio", " fleuve", " fluss"]:
        if low.endswith(suffix):
            low = low[:-len(suffix)].strip()
    if low in RIVER_ALIASES:
        return RIVER_ALIASES[low]
    for alias, canon in RIVER_ALIASES.items():
        if alias in low.split() or low == alias:
            return canon
    return raw_name.strip()


class TerrainBarrierDB:
    """Singleton spatial database for mountains, mountain ridges, rivers, and deserts."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TerrainBarrierDB, cls).__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self.mountain_polys: List[Any] = []
        self.mountain_meta: List[Dict[str, Any]] = []
        self.ridge_lines: List[Any] = []
        self.ridge_meta: List[Dict[str, Any]] = []
        self.desert_polys: List[Any] = []
        self.desert_meta: List[Dict[str, Any]] = []
        self.rivers_by_name: Dict[str, Any] = {}
        self.river_geoms: List[Any] = []
        self.river_names: List[str] = []

        # 1. Load GMBA Mountain Polygons
        mtn_path = DATA_DIR / "gmba_defense_mountains.geojson"
        global_mtn_path = DATA_DIR.parent / "imperial_caliphate_painter" / "gmba_global_level4.geojson"
        seen_mtn_names = set()

        for p_mtn in [mtn_path, global_mtn_path]:
            if p_mtn.exists():
                try:
                    with open(p_mtn, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        nm = props.get("name") or props.get("gmba_name") or "Mountain Range"
                        if nm in seen_mtn_names and p_mtn == global_mtn_path:
                            continue
                        g_raw = feat.get("geometry")
                        if g_raw:
                            try:
                                g = shape(g_raw)
                                if g and not g.is_empty:
                                    if not g.is_valid:
                                        g = g.buffer(0)
                                    self.mountain_polys.append(g)
                                    self.mountain_meta.append({
                                        "name": nm,
                                        "elev_high": props.get("elev_high") or props.get("high") or 2500
                                    })
                                    seen_mtn_names.add(nm)
                            except Exception:
                                pass
                except Exception:
                    pass

        # 2. Load GMBA Mountain Ridge Centerlines
        ridge_path = DATA_DIR / "gmba_defense_mountain_lines.geojson"
        if ridge_path.exists():
            try:
                with open(ridge_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    nm = props.get("name") or props.get("gmba_name") or "Mountain Ridge"
                    g_raw = feat.get("geometry")
                    if g_raw:
                        try:
                            g = shape(g_raw)
                            if g and not g.is_empty:
                                self.ridge_lines.append(g)
                                self.ridge_meta.append({
                                    "name": nm,
                                    "elev_high": props.get("elev_high") or 2500
                                })
                        except Exception:
                            pass
            except Exception:
                pass

        # 3. Load Rivers & group segments by canonical river name
        river_segments: Dict[str, List[Any]] = {}
        for r_file in ["ne_10m_rivers_lake_centerlines.geojson", "ne_10m_rivers_europe.geojson"]:
            r_path = DATA_DIR / r_file
            if r_path.exists():
                try:
                    with open(r_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for feat in data.get("features", []):
                        props = feat.get("properties", {})
                        fcla = (props.get("featurecla") or "").lower()
                        if "lake" in fcla and "river" not in fcla and "centerline" not in fcla:
                            continue
                        raw_nm = props.get("name") or props.get("name_en") or props.get("name_alt")
                        canon = _canonical_river_name(raw_nm)
                        if not canon:
                            continue
                        srank = props.get("scalerank")
                        try:
                            srank_val = float(srank) if srank is not None else 5.0
                        except Exception:
                            srank_val = 5.0
                        if canon not in MAJOR_FRONTIER_RIVERS and srank_val > 6.0:
                            continue
                        g_raw = feat.get("geometry")
                        if g_raw:
                            try:
                                g = shape(g_raw)
                                if g and not g.is_empty:
                                    existing_segs = river_segments.setdefault(canon, [])
                                    # Avoid duplicate overlapping river centerlines from secondary Euro dataset
                                    if r_file != "ne_10m_rivers_lake_centerlines.geojson" and existing_segs:
                                        if any(g.distance(ex) < 0.03 for ex in existing_segs):
                                            continue
                                    existing_segs.append(g)
                            except Exception:
                                pass
                except Exception:
                    pass

        for r_name, segs in river_segments.items():
            try:
                merged = unary_union(segs)
                if merged.geom_type == "MultiLineString":
                    merged = linemerge(merged)
                self.rivers_by_name[r_name] = merged
                self.river_geoms.append(merged)
                self.river_names.append(r_name)
            except Exception:
                pass

        # 4. Load Deserts
        reg_path = DATA_DIR / "ne_10m_geography_regions_polys.geojson"
        if reg_path.exists():
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    fcla = (props.get("FEATURECLA") or "").lower()
                    if "desert" in fcla:
                        nm = props.get("NAME") or "Desert"
                        g_raw = feat.get("geometry")
                        if g_raw:
                            try:
                                g = shape(g_raw)
                                if g and not g.is_empty:
                                    if not g.is_valid:
                                        g = g.buffer(0)
                                    self.desert_polys.append(g)
                                    self.desert_meta.append({"name": nm})
                            except Exception:
                                pass
            except Exception:
                pass

        self.mtn_tree = STRtree(self.mountain_polys) if self.mountain_polys else None
        self.ridge_tree = STRtree(self.ridge_lines) if self.ridge_lines else None
        self.desert_tree = STRtree(self.desert_polys) if self.desert_polys else None
        self.river_tree = STRtree(self.river_geoms) if self.river_geoms else None
        self._loaded = True


def get_terrain_db() -> TerrainBarrierDB:
    db = TerrainBarrierDB()
    db.ensure_loaded()
    return db


def _extend_river_cutter(river_geom: Any, bounds: Tuple[float, float, float, float], extend_dist: float = 2.0) -> Any:
    """
    Creates an extended cutting geometry from a river LineString or MultiLineString
    so that rivers starting/ending slightly inside a province or split across multiple
    segments still bisect it cleanly.
    """
    minx, miny, maxx, maxy = bounds
    box_poly = Polygon([(minx - 0.5, miny - 0.5), (maxx + 0.5, miny - 0.5), (maxx + 0.5, maxy + 0.5), (minx - 0.5, maxy + 0.5)])
    clipped = river_geom.intersection(box_poly)
    if not clipped or clipped.is_empty:
        return river_geom

    if clipped.geom_type == "MultiLineString":
        clipped = linemerge(clipped)

    lines = [clipped] if clipped.geom_type == "LineString" else [l for l in getattr(clipped, "geoms", []) if l.length >= 0.02]
    if not lines:
        return river_geom

    # Start with the longest river branch inside the bounding box and greedily stitch collinear/adjacent trunk segments
    main_line = max(lines, key=lambda l: l.length)
    coords = list(main_line.coords)
    used_indices = {lines.index(main_line)}

    changed = True
    while changed and len(used_indices) < len(lines):
        changed = False
        best_idx = None
        best_mode = None
        best_dist = 0.65  # max gap to bridge across river segments
        p_start = coords[0]
        p_end = coords[-1]
        span_cur = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])

        for idx, seg in enumerate(lines):
            if idx in used_indices:
                continue
            sc = list(seg.coords)
            if len(sc) < 2:
                continue
            s0, s1 = sc[0], sc[-1]
            # Candidate attachments that increase total end-to-end span (avoids tributary loops)
            candidates = [
                ("append_fwd", math.hypot(p_end[0] - s0[0], p_end[1] - s0[1]), math.hypot(s1[0] - p_start[0], s1[1] - p_start[1])),
                ("append_rev", math.hypot(p_end[0] - s1[0], p_end[1] - s1[1]), math.hypot(s0[0] - p_start[0], s0[1] - p_start[1])),
                ("prepend_fwd", math.hypot(p_start[0] - s1[0], p_start[1] - s1[1]), math.hypot(p_end[0] - s0[0], p_end[1] - s0[1])),
                ("prepend_rev", math.hypot(p_start[0] - s0[0], p_start[1] - s0[1]), math.hypot(p_end[0] - s1[0], p_end[1] - s1[1])),
            ]
            for mode, d_gap, new_span in candidates:
                if d_gap < best_dist and new_span > span_cur + 0.05:
                    best_dist = d_gap
                    best_idx = idx
                    best_mode = mode

        if best_idx is not None:
            used_indices.add(best_idx)
            sc = list(lines[best_idx].coords)
            if best_mode == "append_fwd":
                coords = coords + sc
            elif best_mode == "append_rev":
                coords = coords + list(reversed(sc))
            elif best_mode == "prepend_fwd":
                coords = sc + coords
            elif best_mode == "prepend_rev":
                coords = list(reversed(sc)) + coords
            changed = True

    if len(coords) < 2:
        return main_line

    # Use broader multi-vertex tangent at both ends so local meanders don't shoot sideways
    step0 = min(4, len(coords) - 1)
    dx0, dy0 = coords[0][0] - coords[step0][0], coords[0][1] - coords[step0][1]
    l0 = math.hypot(dx0, dy0) or 1.0
    ext0 = (coords[0][0] + (dx0 / l0) * extend_dist, coords[0][1] + (dy0 / l0) * extend_dist)

    step1 = max(0, len(coords) - 1 - min(4, len(coords) - 1))
    dx1, dy1 = coords[-1][0] - coords[step1][0], coords[-1][1] - coords[step1][1]
    l1 = math.hypot(dx1, dy1) or 1.0
    ext1 = (coords[-1][0] + (dx1 / l1) * extend_dist, coords[-1][1] + (dy1 / l1) * extend_dist)

    cutter = LineString([ext0] + coords + [ext1])
    if not cutter.is_simple:
        cutter = cutter.simplify(0.015)
    return cutter


def bisect_unit_by_river(
    unit_name: str,
    unit_geom: Any,
    river_name: str,
    river_geom: Any,
    conqueror_geom: Optional[Any] = None,
    min_part_ratio: float = 0.12
) -> Optional[Dict[str, Any]]:
    """
    Bisects a historical unit / province polygon along a river geometry.
    Returns dict with near_bank and far_bank sub-units if the river cleanly divides
    the unit into two substantial parts (each >= min_part_ratio of total area).
    """
    if unit_geom is None or unit_geom.is_empty:
        return None
    if not unit_geom.is_valid:
        unit_geom = unit_geom.buffer(0)

    if not river_geom.intersects(unit_geom):
        return None

    try:
        inter_line = river_geom.intersection(unit_geom)
        if not inter_line or inter_line.is_empty:
            return None
        minx, miny, maxx, maxy = unit_geom.bounds
        span = min(maxx - minx, maxy - miny)
        if span <= 0.05 or inter_line.length < 0.28 * span:
            return None

        # Always construct the extended continuous trunk cutter across the unit bounding box
        cutter = _extend_river_cutter(river_geom, unit_geom.bounds, extend_dist=max(1.5, span))

        def _partition_geoms(geoms_list: List[Any], is_ew: bool) -> Tuple[List[Any], List[Any]]:
            ga, gb = [], []
            for sub_p in geoms_list:
                if sub_p is None or sub_p.is_empty:
                    continue
                c = sub_p.centroid
                _, p_riv = nearest_points(c, inter_line)
                if is_ew:
                    if c.y <= p_riv.y:
                        ga.append(sub_p)
                    else:
                        gb.append(sub_p)
                else:
                    if c.x <= p_riv.x:
                        ga.append(sub_p)
                    else:
                        gb.append(sub_p)
            return ga, gb

        ix0, iy0, ix1, iy1 = inter_line.bounds
        is_east_west = (ix1 - ix0) >= (iy1 - iy0)
        total_area = unit_geom.area
        if total_area <= 0:
            return None

        group_a, group_b = [], []
        for candidate_cutter in [cutter, river_geom]:
            try:
                split_res = split(unit_geom, candidate_cutter)
                if split_res and hasattr(split_res, "geoms") and len(split_res.geoms) > 1:
                    ga, gb = _partition_geoms(list(split_res.geoms), is_east_west)
                    if ga and gb:
                        ua, ub = unary_union(ga), unary_union(gb)
                        if (ua.area / total_area) >= min_part_ratio and (ub.area / total_area) >= min_part_ratio:
                            group_a, group_b = ga, gb
                            break
            except Exception:
                pass

        # Fallback: hair-thin topological buffer difference along extended cutter + river intersection
        if not group_a or not group_b:
            try:
                combined_cut = unary_union([cutter, inter_line]).buffer(2e-4)
                diff_geom = unit_geom.difference(combined_cut)
                diff_parts = [diff_geom] if diff_geom.geom_type == "Polygon" else list(getattr(diff_geom, "geoms", []))
                if len(diff_parts) > 1:
                    ga, gb = _partition_geoms(diff_parts, is_east_west)
                    if ga and gb:
                        ua, ub = unary_union(ga), unary_union(gb)
                        if (ua.area / total_area) >= min_part_ratio and (ub.area / total_area) >= min_part_ratio:
                            group_a, group_b = ga, gb
            except Exception:
                pass

        if not group_a or not group_b:
            return None

        geom_a = unary_union(group_a)
        geom_b = unary_union(group_b)

        dir_a = "South" if is_east_west else "West"
        dir_b = "North" if is_east_west else "East"

        # Determine which side is the Near Bank (closer to local conqueror mass) vs Far Bank (across river)
        a_is_near = True
        if conqueror_geom and not conqueror_geom.is_empty:
            local_conq = conqueror_geom.intersection(unit_geom.buffer(5.0))
            if not local_conq or local_conq.is_empty:
                local_conq = conqueror_geom
            ref_pt = local_conq.centroid
            dist_a = geom_a.centroid.distance(ref_pt)
            dist_b = geom_b.centroid.distance(ref_pt)
            a_is_near = (dist_a <= dist_b)

        if a_is_near:
            near_geom, near_dir = geom_a, dir_a
            far_geom, far_dir = geom_b, dir_b
        else:
            near_geom, near_dir = geom_b, dir_b
            far_geom, far_dir = geom_a, dir_a

        near_name = f"{unit_name} ({near_dir} of {river_name})"
        far_name = f"{unit_name} ({far_dir} of {river_name})"

        return {
            "parent_name": unit_name,
            "river_name": river_name,
            "near_name": near_name,
            "near_geom": near_geom,
            "near_dir": near_dir,
            "far_name": far_name,
            "far_geom": far_geom,
            "far_dir": far_dir,
        }
    except Exception:
        return None


def score_province(
    unit_name: str,
    unit_geom: Any,
    front_geom: Optional[Any] = None,
    is_far_bank: bool = False,
    bisecting_river: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes the standalone Province Score (Realistic & Optimistic) and geographic barrier profile
    for a single province or bisected sub-province.
    """
    db = get_terrain_db()
    if unit_geom is None or unit_geom.is_empty:
        return {
            "unit_name": unit_name,
            "score_real": 0.50,
            "score_opt": 0.60,
            "terrain_weight": 0.50,
            "barrier_weight_real": 1.0,
            "barrier_weight_opt": 1.0,
            "mountain_pct": 0.0,
            "mountain_names": [],
            "desert_pct": 0.0,
            "rivers": [],
            "barrier_note": "Open Plain",
            "is_far_bank": is_far_bank,
        }

    if not unit_geom.is_valid:
        unit_geom = unit_geom.buffer(0)
    u_area = max(unit_geom.area, 1e-6)

    # 1. Mountain Coverage & Dominant Mountain Range Names
    mtn_inter_geoms = []
    mtn_names_ranked = []
    if db.mtn_tree is not None:
        cand_idxs = db.mtn_tree.query(unit_geom)
        for idx in cand_idxs:
            m_poly = db.mountain_polys[idx]
            if unit_geom.intersects(m_poly):
                try:
                    inter = unit_geom.intersection(m_poly)
                    if inter and not inter.is_empty:
                        mtn_inter_geoms.append(inter)
                        m_nm = db.mountain_meta[idx]["name"]
                        mtn_names_ranked.append((m_nm, inter.area, db.mountain_meta[idx].get("elev_high", 2500)))
                except Exception:
                    pass

    mtn_union_area = unary_union(mtn_inter_geoms).area if mtn_inter_geoms else 0.0
    mtn_pct = min(1.0, mtn_union_area / u_area)
    mtn_names_ranked.sort(key=lambda x: x[1], reverse=True)
    top_mtns = []
    for nm, ar, _ in mtn_names_ranked:
        if nm not in top_mtns and (ar / u_area) >= 0.05:
            top_mtns.append(nm)
        if len(top_mtns) >= 2:
            break

    # 2. Desert Coverage
    des_inter_geoms = []
    if db.desert_tree is not None:
        cand_idxs = db.desert_tree.query(unit_geom)
        for idx in cand_idxs:
            d_poly = db.desert_polys[idx]
            if unit_geom.intersects(d_poly):
                try:
                    inter = unit_geom.intersection(d_poly)
                    if inter and not inter.is_empty:
                        des_inter_geoms.append(inter)
                except Exception:
                    pass
    des_union_area = unary_union(des_inter_geoms).area if des_inter_geoms else 0.0
    des_pct = min(1.0, des_union_area / u_area)

    # 3. Intersecting Major Rivers
    unit_rivers = []
    if db.river_tree is not None:
        cand_idxs = db.river_tree.query(unit_geom)
        for idx in cand_idxs:
            r_geom = db.river_geoms[idx]
            r_name = db.river_names[idx]
            if r_name in MAJOR_FRONTIER_RIVERS and unit_geom.buffer(0.04).intersects(r_geom):
                if r_name not in unit_rivers:
                    unit_rivers.append(r_name)

    # 4. Terrain Weight W_terrain in [0.18, 1.00]
    w_terrain = max(0.18, 1.0 - (0.68 * mtn_pct) - (0.60 * des_pct))

    # 5. Barrier Weight W_barrier (Realistic vs Optimistic) relative to front_geom
    w_barrier_real = 1.00
    w_barrier_opt = 1.00
    w_reach_real = 1.00
    w_reach_opt = 1.00
    barrier_note = "Open Lowland Corridor"

    if is_far_bank and bisecting_river:
        w_barrier_real = 0.35
        w_barrier_opt = 0.78
        barrier_note = f"Across {bisecting_river} River Barrier"
        if front_geom and not front_geom.is_empty:
            try:
                dist = unit_geom.distance(front_geom)
                if dist > 0.15:
                    w_reach_real = 1.0 / (1.0 + 0.18 * (dist - 0.15))
                    w_reach_opt = 1.0 / (1.0 + 0.08 * (dist - 0.15))
            except Exception:
                pass
    elif front_geom and not front_geom.is_empty:
        try:
            # Check shared border zone (for adjacent provinces) or approach vector (for non-adjacent provinces)
            dist = unit_geom.distance(front_geom)
            if dist <= 0.15:
                shared_zone = unit_geom.boundary.intersection(front_geom.buffer(0.08))
                if shared_zone and not shared_zone.is_empty and shared_zone.length > 0:
                    mtn_border_len = 0.0
                    blocking_mtn_name = None
                    if db.mtn_tree is not None:
                        for idx in db.mtn_tree.query(shared_zone):
                            mp = db.mountain_polys[idx]
                            if shared_zone.intersects(mp):
                                il = shared_zone.intersection(mp).length
                                if il > mtn_border_len:
                                    mtn_border_len = il
                                    blocking_mtn_name = db.mountain_meta[idx]["name"]

                    mtn_border_ratio = min(1.0, mtn_border_len / max(shared_zone.length, 1e-6))

                    riv_border_len = 0.0
                    blocking_riv_name = None
                    corridor_riv_name = None
                    if db.river_tree is not None:
                        for idx in db.river_tree.query(shared_zone.buffer(0.06)):
                            rg = db.river_geoms[idx]
                            rn = db.river_names[idx]
                            if rn not in MAJOR_FRONTIER_RIVERS:
                                continue
                            riv_buf = rg.buffer(0.06)
                            if shared_zone.intersects(riv_buf):
                                rl = shared_zone.intersection(riv_buf).length
                                if rl > riv_border_len:
                                    riv_border_len = rl
                                    blocking_riv_name = rn
                            if front_geom.intersects(rg) and unit_geom.intersects(rg):
                                corridor_riv_name = rn

                    riv_border_ratio = min(1.0, riv_border_len / max(shared_zone.length, 1e-6))

                    if mtn_border_ratio >= 0.45 and mtn_pct >= 0.35:
                        w_barrier_real = 0.22
                        w_barrier_opt = 0.35
                        barrier_note = f"Mountain Barrier ({blocking_mtn_name or (top_mtns[0] if top_mtns else 'High Range')})"
                    elif riv_border_ratio >= 0.35 and blocking_riv_name:
                        w_barrier_real = 0.38
                        w_barrier_opt = 0.78
                        barrier_note = f"River Boundary ({blocking_riv_name} River)"
                    elif corridor_riv_name and mtn_pct < 0.40:
                        w_barrier_real = 1.15
                        w_barrier_opt = 1.15
                        barrier_note = f"River Valley Corridor ({corridor_riv_name})"
            else:
                # Non-adjacent province: apply distance decay & check intervening river/mountain barriers along approach vector
                w_reach_real = 1.0 / (1.0 + 0.18 * (dist - 0.15))
                w_reach_opt = 1.0 / (1.0 + 0.08 * (dist - 0.15))
                p1, p2 = nearest_points(front_geom, unit_geom)
                approach_line = LineString([p1, p2])

                crossed_rivers = []
                corridor_riv_name = None
                if db.river_tree is not None:
                    for idx in db.river_tree.query(approach_line):
                        rg = db.river_geoms[idx]
                        rn = db.river_names[idx]
                        if rn not in MAJOR_FRONTIER_RIVERS:
                            continue
                        if front_geom.intersects(rg) and unit_geom.intersects(rg):
                            corridor_riv_name = rn
                        elif approach_line.intersects(rg) and not front_geom.buffer(0.05).intersects(rg):
                            if rn not in crossed_rivers:
                                crossed_rivers.append(rn)

                crossed_mtns = []
                if db.mtn_tree is not None:
                    for idx in db.mtn_tree.query(approach_line):
                        mp = db.mountain_polys[idx]
                        if approach_line.intersects(mp):
                            ml = approach_line.intersection(mp).length
                            if ml >= 0.45:
                                m_nm = db.mountain_meta[idx]["name"]
                                if m_nm not in crossed_mtns:
                                    crossed_mtns.append(m_nm)

                if crossed_mtns and mtn_pct >= 0.35:
                    w_barrier_real = 0.25
                    w_barrier_opt = 0.40
                    barrier_note = f"Mountain Barrier ({crossed_mtns[0]})"
                elif crossed_rivers:
                    # Each major river crossed between frontier and distant province compounds logistical friction
                    n_riv = len(crossed_rivers)
                    w_barrier_real = 0.42 if n_riv == 1 else 0.28
                    w_barrier_opt = 0.78 if n_riv == 1 else 0.58
                    barrier_note = f"Across {' & '.join(crossed_rivers[:2])} River Barrier"
                elif corridor_riv_name and mtn_pct < 0.40:
                    w_barrier_real = 1.10
                    w_barrier_opt = 1.12
                    barrier_note = f"River Valley Corridor ({corridor_riv_name})"
                elif dist >= 3.0:
                    barrier_note = f"Distant Interior ({dist:.1f}° from Frontier)"
        except Exception:
            pass

    if barrier_note == "Open Lowland Corridor" and mtn_pct >= 0.55:
        w_barrier_real = min(w_barrier_real, 0.35)
        w_barrier_opt = min(w_barrier_opt, 0.50)
        barrier_note = f"Alpine Massif ({top_mtns[0] if top_mtns else 'Mountain Stronghold'})"

    score_real = round(min(1.00, max(0.05, w_terrain * w_barrier_real * w_reach_real)), 2)
    score_opt = round(min(1.00, max(0.05, w_terrain * w_barrier_opt * w_reach_opt)), 2)

    return {
        "unit_name": unit_name,
        "score_real": score_real,
        "score_opt": score_opt,
        "terrain_weight": round(w_terrain, 2),
        "barrier_weight_real": round(w_barrier_real, 2),
        "barrier_weight_opt": round(w_barrier_opt, 2),
        "mountain_pct": round(mtn_pct * 100.0, 1),
        "mountain_names": top_mtns,
        "desert_pct": round(des_pct * 100.0, 1),
        "rivers": unit_rivers[:2],
        "barrier_note": barrier_note,
        "is_far_bank": is_far_bank,
        "bisecting_river": bisecting_river,
    }


def prepare_scored_and_bisected_units(
    all_available_units: Set[str],
    unit_geom_map: Dict[str, Any],
    unit_polity_map: Dict[str, str],
    unit_meta_lookup: Dict[str, Dict[str, Any]],
    winner_base_sh: Optional[Any],
    scenario_val: str = "",
    context_val: Optional[Dict[str, Any]] = None
) -> str:
    """
    1. Detects if any scenario-named river or major frontier river cuts through candidate
       historical units and bisects them along the river into near-bank and far-bank sub-units.
    2. Scores every candidate province / bisected sub-unit (`score_real`, `score_opt`).
    3. Registers bisected geometries in `context_val['dynamic_bisected_units']` and scores in
       `context_val['province_scores']`.
    4. Returns the formatted string of scored provinces for the AI prompt.
    """
    db = get_terrain_db()
    scen_low = (scenario_val or "").lower()

    # Identify rivers explicitly mentioned in the scenario or answers
    mentioned_rivers: Set[str] = set()
    for alias, canon in RIVER_ALIASES.items():
        if alias in scen_low:
            mentioned_rivers.add(canon)
    if context_val and "clarifying_questions" in context_val:
        for q in context_val.get("clarifying_questions", []):
            q_txt = (q.get("question", "") + " " + " ".join(q.get("options", []))).lower()
            for alias, canon in RIVER_ALIASES.items():
                if alias in q_txt:
                    mentioned_rivers.add(canon)

    dynamic_bisected: Dict[str, Any] = {}
    near_bank_clips: Dict[str, Dict[str, Any]] = {}
    far_bank_meta: Dict[str, Tuple[bool, Optional[str]]] = {}

    # Step 1: Bisect historical units crossed by mentioned rivers or major frontier rivers
    base_unit_names = sorted(list(all_available_units))
    for u_name in base_unit_names:
        u_geom = unit_geom_map.get(u_name)
        if not u_geom or u_geom.is_empty:
            continue

        # Candidate rivers to check for this unit: mentioned rivers first, then major frontier rivers
        candidate_rivers = list(mentioned_rivers) + [
            r for r in ["Danube", "Rhine", "Loire", "Rhône", "Elbe", "Po", "Ebro", "Euphrates", "Amu Darya", "Syr Darya", "Indus", "Sutlej", "Chenab", "Narmada", "Ganges"]
            if r not in mentioned_rivers
        ]

        for r_name in candidate_rivers:
            r_geom = db.rivers_by_name.get(r_name)
            if not r_geom:
                continue
            # Only auto-bisect non-mentioned rivers if the unit is near the frontier or in the active theater
            if r_name not in mentioned_rivers and winner_base_sh and not winner_base_sh.is_empty:
                if u_geom.distance(winner_base_sh) > 3.5:
                    continue

            bisect_info = bisect_unit_by_river(
                unit_name=u_name,
                unit_geom=u_geom,
                river_name=r_name,
                river_geom=r_geom,
                conqueror_geom=winner_base_sh,
                min_part_ratio=0.14
            )
            if bisect_info:
                near_nm = bisect_info["near_name"]
                far_nm = bisect_info["far_name"]
                near_g = bisect_info["near_geom"]
                far_g = bisect_info["far_geom"]

                # Register both bisected partitions as selectable provinces
                all_available_units.add(near_nm)
                all_available_units.add(far_nm)
                unit_geom_map[near_nm] = near_g
                unit_geom_map[far_nm] = far_g
                unit_polity_map[near_nm] = unit_polity_map.get(u_name, "Target Polity")
                unit_polity_map[far_nm] = unit_polity_map.get(u_name, "Target Polity")

                dynamic_bisected[near_nm] = near_g
                dynamic_bisected[far_nm] = far_g
                near_bank_clips[u_name] = bisect_info
                far_bank_meta[near_nm] = (False, r_name)
                far_bank_meta[far_nm] = (True, r_name)
                print(
                    f"[RIVER-BISECT] Bisected historical unit '{u_name}' along {r_name} River -> "
                    f"Near Bank: '{near_nm}' ({near_g.area:.3f} sq deg) | Far Bank: '{far_nm}' ({far_g.area:.3f} sq deg)",
                    flush=True
                )
                break

    # Step 2: Score every province (and bisected sub-province)
    province_scores: Dict[str, Dict[str, Any]] = {}
    sorted_avail = sorted(all_available_units)
    for u_name in sorted_avail:
        u_geom = unit_geom_map.get(u_name)
        is_far, b_riv = far_bank_meta.get(u_name, (False, None))
        sc = score_province(
            unit_name=u_name,
            unit_geom=u_geom,
            front_geom=winner_base_sh,
            is_far_bank=is_far,
            bisecting_river=b_riv
        )
        province_scores[u_name] = sc

    if province_scores:
        top_scored = sorted(province_scores.values(), key=lambda x: x["score_real"], reverse=True)[:8]
        score_summary = ", ".join(f"{x['unit_name']} [Real={x['score_real']:.2f}, Opt={x['score_opt']:.2f}, {x['barrier_note']}]" for x in top_scored)
        print(f"[PROVINCE-SCORER] Scored {len(province_scores)} candidate provinces ({len(dynamic_bisected)} river-bisected partitions). Top Realistic candidates: {score_summary}", flush=True)

    if context_val is not None:
        context_val.setdefault("dynamic_bisected_units", {}).update(dynamic_bisected)
        context_val.setdefault("river_near_bank_clips", {}).update(near_bank_clips)
        context_val["province_scores"] = province_scores

    # Step 3: Format the Scored Province Briefing for the AI prompt
    if not sorted_avail:
        return "None"

    briefing_lines = []
    for u_name in sorted_avail:
        u_pol = unit_polity_map.get(u_name, "Target Polity")
        u_meta = unit_meta_lookup.get(u_name, {})
        u_cap = u_meta.get("capital_modern") or u_meta.get("capital_historical") or ""
        u_tier = u_meta.get("tier") or "Region"
        cap_str = f", Capital: {u_cap}" if u_cap else ""

        sc = province_scores.get(u_name, {})
        s_real = sc.get("score_real", 0.50)
        s_opt = sc.get("score_opt", 0.60)
        mtn_pct = sc.get("mountain_pct", 0.0)
        mtns = sc.get("mountain_names", [])
        rivs = sc.get("rivers", [])
        b_note = sc.get("barrier_note", "Open Corridor")

        terrain_parts = []
        if mtn_pct >= 10.0:
            m_label = f" ({', '.join(mtns)})" if mtns else ""
            terrain_parts.append(f"{mtn_pct:.0f}% Mtn{m_label}")
        else:
            terrain_parts.append("Lowland Plain")
        if rivs:
            terrain_parts.append(f"Rivers: {'/'.join(rivs)}")
        terrain_str = ", ".join(terrain_parts)

        neighbors = []
        u_geom = unit_geom_map.get(u_name)
        if u_geom and not u_geom.is_empty:
            if winner_base_sh and not winner_base_sh.is_empty:
                try:
                    if u_geom.distance(winner_base_sh) <= 0.06:
                        neighbors.append("[CONQUEROR FRONTIER]")
                except Exception:
                    pass
            for other_u in sorted_avail:
                if other_u == u_name:
                    continue
                # Avoid cluttering parent unit's neighbor list with its own split children
                if other_u.startswith(u_name + " (") or u_name.startswith(other_u + " ("):
                    continue
                o_geom = unit_geom_map.get(other_u)
                if o_geom and not o_geom.is_empty:
                    try:
                        if u_geom.distance(o_geom) <= 0.05:
                            neighbors.append(other_u)
                    except Exception:
                        pass
        adj_str = f" | Borders: {', '.join(neighbors)}" if neighbors else ""
        score_tag = f" | ProvinceScore[Real={s_real:.2f}, Opt={s_opt:.2f} | {b_note} | {terrain_str}]"
        briefing_lines.append(f"  * \"{u_name}\" ({u_pol} {u_tier}{cap_str}){score_tag}{adj_str}")

    return "\n" + "\n".join(briefing_lines)

