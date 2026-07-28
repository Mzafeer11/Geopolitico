import os
import re
import csv
import json
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from pydantic import BaseModel, Field

from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union
import networkx as nx

try:
    from backend.tools.gis_tools import wikipedia_demographics_tool
except ImportError:
    wikipedia_demographics_tool = None

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

PAK_GADM = ROOT_DIR / "gadm41_PAK_2.json"
BGD_GADM = ROOT_DIR / "gadm41_BGD_2.json"
IND_GADM = ROOT_DIR / "gadm41_IND_2.json"

ENRICHED_CENSUS_CSV = ROOT_DIR / "data" / "census_1941_enriched.csv"
COMBINED_CENSUS_CSV = ENRICHED_CENSUS_CSV if ENRICHED_CENSUS_CSV.exists() else (ROOT_DIR / "Census 1941" / "census_1941_combined.csv")
NE_ADMIN1_GEOJSON = ROOT_DIR / "data" / "ne_10m_admin_1_provinces.geojson"
WIKIDATA_ALIASES_CACHE = ROOT_DIR / "data" / "gadm_wikidata_aliases_cache.json"

STATE_ALIASES = {
    "uttarpradesh": "united provinces", "uttar pradesh": "united provinces", "uttarakhand": "united provinces",
    "westbengal": "bengal", "west bengal": "bengal",
    "jammuandkashmir": "kashmir", "jammu and kashmir": "kashmir", "ladakh": "kashmir", "azadkashmir": "kashmir",
    "azad kashmir": "kashmir", "northernareas": "kashmir", "gilgit-baltistan": "kashmir",
    "madhyapradesh": "central provinces", "madhya pradesh": "central provinces", "andhrapradesh": "madras",
    "andhra pradesh": "madras", "telangana": "madras", "tamilnadu": "madras", "tamil nadu": "madras",
    "karnataka": "mysore", "kerala": "travancore", "rajasthan": "rajputana", "gujarat": "bombay",
    "maharashtra": "bombay", "haryana": "punjab", "himachalpradesh": "punjab", "himachal pradesh": "punjab",
    "jharkhand": "bihar", "odisha": "orissa", "orissa": "orissa", "delhi": "delhi", "goa": "bombay",
    "chandigarh": "punjab", "assam": "assam", "meghalaya": "khasi", "nagaland": "naga hills",
    "mizoram": "lushai hills", "manipur": "manipur", "tripura": "tripura", "arunachalpradesh": "nefa frontier",
    "arunachal pradesh": "nefa frontier", "federallyadministeredtribalar": "north-west frontier province",
    "f.a.t.a.": "north-west frontier province", "islamabad": "punjab", "khyberpakhtunkhwa": "north-west frontier province",
    "khyber-pakhtunkhwa": "north-west frontier province", "balochistan": "baluchistan", "sindh": "sind"
}

DISTRICT_ALIASES = {
    "mewat": "gurgaon", "nuh": "gurgaon",
    "faisalabad": "lyallpur", "sahiwal": "montgomery", "pakpattan": "montgomery",
    "attock": "campbellpore", "benazirabad": "nawabshah", "deraghazikhan": "deragazikhan",
    "firozpur": "ferozepur", "jalandhar": "jullundur", "hisar": "hissar",
    "kolkata": "calcutta", "mumbai": "bombay", "chennai": "madras", "bengaluru": "bangalore",
    "prayagraj": "allahabad", "dhaka": "dacca", "barisal": "bakarganj",
    "kozhikode": "calicut", "malappuram": "calicut", "kannur": "calicut", "kasaragod": "calicut"
}

REGIONAL_HISTORICAL_DEFAULTS = {
    "naga hills": 1.0, "lushai hills": 0.8, "manipur state": 7.0, "khasi & jaintia hills": 4.0,
    "nefa frontier": 0.5, "tripura state": 24.1, "united provinces": 15.3, "bihar": 13.0,
    "central provinces & berar": 4.7, "orissa": 1.5, "travancore state": 7.15, "mysore state": 6.62,
    "rajputana states": 9.51, "baroda state": 7.8, "bombay": 9.2
}


class DemographicShiftPlan(BaseModel):
    prompt_explanation: str = Field(description="Detailed explanation of the demographic shift, base year, target percentages, and spatial distribution logic.")
    target_percentage: float = Field(default=60.0, description="Overall target percentage across the region.")
    spatial_alpha: float = Field(default=0.70, description="Spatial weight for local vs neighbor blend.")
    extracted_year: Optional[int] = Field(default=None, description="The base year extracted from the user's prompt (e.g. 1947, 1946, 1941).")


def split_pascal(text: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", text)


def clean_norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8').lower()
    text = re.sub(r'\b(district|division|city|rural|state|province)\b', '', text)
    clean = re.sub(r'[^a-z0-9]', '', text)
    clean = clean.replace("ghazi", "gazi").replace("pore", "pur").replace("poor", "pur")
    return clean


def load_bangladesh_features() -> List[Dict[str, Any]]:
    bgd_features = []
    if NE_ADMIN1_GEOJSON.exists():
        with open(NE_ADMIN1_GEOJSON, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                if props.get("admin") == "Bangladesh" or props.get("iso_a2") == "BD" or props.get("adm0_a3") == "BGD":
                    p_name = props.get("name_en") or props.get("name") or "Bangladesh"
                    if "properties" not in feat:
                        feat["properties"] = {}
                    feat["properties"]["NAME_1"] = "Bengal"
                    feat["properties"]["NAME_2"] = p_name
                    bgd_features.append(feat)
    if not bgd_features:
        bgd_features = load_gadm_geojson(BGD_GADM)
    return bgd_features


def load_gadm_geojson(path_obj: Path) -> List[Dict[str, Any]]:
    file_target = path_obj / path_obj.name if path_obj.is_dir() else path_obj
    if not file_target.exists():
        return []
    with open(file_target, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
        return data.get("features", [])


def load_census_lookups() -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    unit_lookup = {}
    prov_lookup = {}
    pop_lookup = {}

    if COMBINED_CENSUS_CSV.exists():
        with open(COMBINED_CENSUS_CSV, "r", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                entity = row.get("District or State", "").strip().lower()
                alt_names = row.get("Alternate_Names", "")
                m_pct_str = row.get("Muslim Percentage")
                pop_str = row.get("Population")
                if entity and m_pct_str and m_pct_str != "":
                    try:
                        val = float(m_pct_str)
                        pop_val = float(pop_str) if pop_str and pop_str != "" else None
                        unit = row.get("Administrative Unit", "").strip().lower()
                        clean_key = entity.replace(" (including feudatories)", "").replace(" and berar", "").strip()
                        
                        unit_lookup[entity] = val
                        unit_lookup[clean_key] = val
                        unit_lookup[clean_norm(entity)] = val
                        unit_lookup[clean_norm(clean_key)] = val

                        if pop_val is not None:
                            pop_lookup[entity] = pop_val
                            pop_lookup[clean_key] = pop_val
                            pop_lookup[clean_norm(entity)] = pop_val
                            pop_lookup[clean_norm(clean_key)] = pop_val

                        if alt_names:
                            for alt in alt_names.split(","):
                                alt_clean = alt.strip().lower()
                                alt_norm = clean_norm(alt_clean)
                                if alt_clean:
                                    unit_lookup[alt_clean] = val
                                    if pop_val is not None: pop_lookup[alt_clean] = pop_val
                                if alt_norm:
                                    unit_lookup[alt_norm] = val
                                    if pop_val is not None: pop_lookup[alt_norm] = pop_val
                        
                        if unit in ["province", "state"] or "kashmir" in entity:
                            prov_lookup[entity] = val
                            prov_lookup[clean_key] = val
                            prov_lookup[clean_norm(entity)] = val
                            if "kashmir" in entity:
                                prov_lookup["kashmir"] = val
                                unit_lookup["kashmir"] = val
                                if pop_val is not None:
                                    pop_lookup["kashmir"] = pop_val
                    except ValueError:
                        pass

    if WIKIDATA_ALIASES_CACHE.exists():
        try:
            with open(WIKIDATA_ALIASES_CACHE, "r", encoding="utf-8") as f:
                wiki_cache = json.load(f)
                matched_count = 0
                for gadm_d, aliases in wiki_cache.items():
                    clean_gadm = clean_norm(gadm_d)
                    for alt in aliases:
                        clean_alt = clean_norm(alt)
                        if clean_alt in unit_lookup:
                            val = unit_lookup[clean_alt]
                            pop_val = pop_lookup.get(clean_alt)
                            unit_lookup[gadm_d.lower()] = val
                            unit_lookup[clean_gadm] = val
                            if pop_val is not None:
                                pop_lookup[gadm_d.lower()] = pop_val
                                pop_lookup[clean_gadm] = pop_val
                            matched_count += 1
                if matched_count > 0:
                    print(f"[DEMOGRAPHIC] Successfully resolved {matched_count} GADM districts via Wikidata historical alias lookup.", flush=True)
        except Exception as e:
            print(f"[DEMOGRAPHIC] Error loading Wikidata alias cache: {e}", flush=True)

    return unit_lookup, prov_lookup, pop_lookup


def run_demographic_simulation(context: Dict[str, Any]) -> Dict[str, Any]:
    scenario = context.get("scenario", "")
    ctx_year = context.get("year")

    parsed_year = None
    if ctx_year is not None:
        try:
            parsed_year = int(ctx_year)
        except ValueError:
            pass

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", scenario)
    if parsed_year is None and year_match:
        parsed_year = int(year_match.group(1))

    if parsed_year is not None and parsed_year < 1900:
        print(f"[DEMOGRAPHIC ENGINE WARN] Year {parsed_year} AD < 1900 AD. Falling back to default 1941 Census baseline.", flush=True)
        base_year = 1941
    else:
        base_year = parsed_year if parsed_year is not None else 1941

    print(f"[DEMOGRAPHIC ENGINE] Initializing demographic shift pipeline for scenario base year: {base_year} AD...", flush=True)

    from langchain_core.messages import SystemMessage
    from backend.helpers.llm import invoke_structured_with_fallback
    def invoke_structured_output(schema, msgs, temperature=0.2):
        return invoke_structured_with_fallback(schema, msgs, temperature=temperature)

    prompt_path = ROOT_DIR / "backend" / "prompts" / "demographic_formula.txt"
    system_prompt = ""
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

    full_system_message = f"{system_prompt}\n\nUser Scenario Prompt: {scenario}"
    
    plan: DemographicShiftPlan = invoke_structured_output(
        DemographicShiftPlan,
        [SystemMessage(content=full_system_message)],
        temperature=0.2
    )

    print(f"[DEMOGRAPHIC ENGINE] Formula Extracted: Target={plan.target_percentage}%, Alpha={plan.spatial_alpha}. Rationale: {plan.prompt_explanation}", flush=True)

    target_pct = plan.target_percentage
    alpha = plan.spatial_alpha

    pak_features = load_gadm_geojson(PAK_GADM)
    bgd_features = load_bangladesh_features()
    ind_features = load_gadm_geojson(IND_GADM)

    unit_lookup, prov_lookup, pop_lookup = load_census_lookups()

    all_raw_features = []
    for f in pak_features:
        f["_country"] = "Pakistan"
        all_raw_features.append(f)
    for f in bgd_features:
        f["_country"] = "Bangladesh"
        all_raw_features.append(f)
    for f in ind_features:
        f["_country"] = "India"
        all_raw_features.append(f)

    processed_items = []
    total_area = 0.0
    weighted_baseline_sum = 0.0

    for feat in all_raw_features:
        props = feat.get("properties", {})
        cname = feat["_country"]
        raw_p = props.get("NAME_1", "Unknown").strip()
        raw_d = props.get("NAME_2", props.get("NAME_1", "Unknown")).strip()

        norm_p = split_pascal(raw_p).lower()
        norm_d = split_pascal(raw_d).lower()

        alias_p = STATE_ALIASES.get(raw_p.lower(), STATE_ALIASES.get(norm_p, norm_p))
        alias_d = DISTRICT_ALIASES.get(raw_d.lower(), DISTRICT_ALIASES.get(norm_d, norm_d))

        clean_d = clean_norm(norm_d)
        clean_alias_d = clean_norm(alias_d)
        clean_p = clean_norm(norm_p)
        clean_alias_p = clean_norm(alias_p)

        try:
            geom_shape = shape(feat["geometry"])
            area = geom_shape.area
        except Exception:
            continue

        matched_pct = None
        match_source = "country_fallback"
        is_fallback = False

        if norm_d in unit_lookup:
            matched_pct = unit_lookup[norm_d]
            match_source = "exact_district_csv"
        elif clean_d in unit_lookup:
            matched_pct = unit_lookup[clean_d]
            match_source = "exact_district_csv"
        elif clean_alias_d in unit_lookup:
            matched_pct = unit_lookup[clean_alias_d]
            match_source = "exact_district_csv"
        elif alias_d in unit_lookup:
            matched_pct = unit_lookup[alias_d]
            match_source = "exact_district_csv"
        else:
            for u_k, u_v in unit_lookup.items():
                if len(u_k) > 3 and (u_k in clean_alias_d or clean_alias_d in u_k or u_k in clean_d or clean_d in u_k):
                    matched_pct = u_v
                    match_source = "substring_district_csv"
                    break

        if matched_pct is None:
            if clean_alias_p in prov_lookup:
                matched_pct = prov_lookup[clean_alias_p]
                match_source = "province_csv"
            elif clean_p in prov_lookup:
                matched_pct = prov_lookup[clean_p]
                match_source = "province_csv"
            elif alias_p in prov_lookup:
                matched_pct = prov_lookup[alias_p]
                match_source = "province_csv"
            elif norm_p in prov_lookup:
                matched_pct = prov_lookup[norm_p]
                match_source = "province_csv"
            elif "kashmir" in alias_p and "kashmir" in prov_lookup:
                matched_pct = prov_lookup["kashmir"]
                match_source = "province_csv"
            elif alias_p in REGIONAL_HISTORICAL_DEFAULTS:
                matched_pct = REGIONAL_HISTORICAL_DEFAULTS[alias_p]
                match_source = "regional_default"
            elif norm_p in REGIONAL_HISTORICAL_DEFAULTS:
                matched_pct = REGIONAL_HISTORICAL_DEFAULTS[norm_p]
                match_source = "regional_default"
            else:
                is_fallback = True
                match_source = "country_fallback"
                matched_pct = 78.5 if cname == "Pakistan" else (70.3 if cname == "Bangladesh" else 15.0)

        pop_est = pop_lookup.get(alias_d, pop_lookup.get(norm_d, pop_lookup.get(alias_p, pop_lookup.get(norm_p, None))))
        if pop_est is None or pop_est <= 0:
            pop_est = max(50000.0, area * 50000.0)

        total_area += area
        weighted_baseline_sum += (matched_pct * area)

        processed_items.append({
            "feature": feat,
            "shape": geom_shape,
            "area": area,
            "baseline_pct": matched_pct,
            "current_pct": matched_pct,
            "population": pop_est,
            "match_source": match_source,
            "is_fallback": is_fallback,
            "country": cname,
            "province": raw_p,
            "district": raw_d
        })

    subcontinent_baseline_avg = weighted_baseline_sum / total_area if total_area > 0 else 24.0
    scale_factor = target_pct / max(0.1, subcontinent_baseline_avg)

    for item in processed_items:
        scaled_val = min(99.5, item["baseline_pct"] * scale_factor)
        item["current_pct"] = scaled_val

    num_items = len(processed_items)
    adj_matrix = [[] for _ in range(num_items)]

    for i in range(num_items):
        s_i = processed_items[i]["shape"]
        for j in range(i + 1, num_items):
            s_j = processed_items[j]["shape"]
            if s_i.touches(s_j) or s_i.intersects(s_j):
                adj_matrix[i].append(j)
                adj_matrix[j].append(i)

    iterations = 15
    for _ in range(iterations):
        next_pcts = []
        for i in range(num_items):
            local_val = processed_items[i]["current_pct"]
            neighbors = adj_matrix[i]
            if neighbors:
                neigh_avg = sum(processed_items[n]["current_pct"] for n in neighbors) / len(neighbors)
                blended = alpha * local_val + (1.0 - alpha) * neigh_avg
            else:
                blended = local_val
            next_pcts.append(blended)
        for i in range(num_items):
            processed_items[i]["current_pct"] = next_pcts[i]

    district_spectrum_features = []
    audit_features = []
    pakistan_shapes_realistic = []
    india_shapes_realistic = []

    subcontinent_shapes = []

    for item in processed_items:
        c_pct = item["current_pct"]
        orig_feat = item["feature"]
        geom_s = item["shape"]

        subcontinent_shapes.append(geom_s)

        if c_pct >= 60.0:
            fill_color = "#10b981"
        elif c_pct >= 50.0:
            fill_color = "#059669"
        elif c_pct >= 35.0:
            fill_color = "#f97316"
        else:
            fill_color = "#ef4444"

        dist_feat = {
            "type": "Feature",
            "geometry": orig_feat["geometry"],
            "properties": {
                "name": item["district"],
                "province": item["province"],
                "country": item["country"],
                "muslim_pct": round(c_pct, 2),
                "baseline_pct": round(item["baseline_pct"], 2),
                "population": int(item["population"]),
                "fill": fill_color,
                "fillOpacity": 0.65,
                "stroke": "#000000",
                "strokeWidth": 0.5
            }
        }
        district_spectrum_features.append(dist_feat)

        ms = item["match_source"]
        if ms in ["exact_district_csv", "substring_district_csv"]:
            audit_color = "#3b82f6"
            audit_label = "Exact/Substring District CSV"
        elif ms == "province_csv":
            audit_color = "#8b5cf6"
            audit_label = "1941 Parent Province CSV"
        elif ms == "regional_default":
            audit_color = "#eab308"
            audit_label = "Regional Default"
        else:
            audit_color = "#ef4444"
            audit_label = "Country Baseline Fallback"

        aud_feat = {
            "type": "Feature",
            "geometry": orig_feat["geometry"],
            "properties": {
                "name": item["district"],
                "province": item["province"],
                "country": item["country"],
                "match_tier": audit_label,
                "fill": audit_color,
                "fillOpacity": 0.70,
                "stroke": "#000000",
                "strokeWidth": 0.5
            }
        }
        audit_features.append(aud_feat)

        # FIXED THRESHOLD AT 50% FOR REALISTIC & OPTIMISTIC MAP PARTITION
        if c_pct >= 50.0:
            pakistan_shapes_realistic.append(geom_s)
        else:
            india_shapes_realistic.append(geom_s)

    subcontinent_union = unary_union(subcontinent_shapes)
    baseline_features = [{
        "type": "Feature",
        "geometry": mapping(subcontinent_union),
        "properties": {
            "name": "British India Baseline Territory",
            "color": "#d97706",
            "fill": "#d97706",
            "fillOpacity": 0.45,
            "stroke": "#b45309",
            "strokeWidth": 2.0
        }
    }]

    pak_union_real = unary_union(pakistan_shapes_realistic) if pakistan_shapes_realistic else None
    ind_union_real = unary_union(india_shapes_realistic) if india_shapes_realistic else None

    realistic_features = []
    if pak_union_real and not pak_union_real.is_empty:
        realistic_features.append({
            "type": "Feature",
            "geometry": mapping(pak_union_real),
            "properties": {
                "name": "New Pakistan (Realistic Majority Partition)",
                "color": "#10b981",
                "fill": "#10b981",
                "fillOpacity": 0.55,
                "stroke": "#047857",
                "strokeWidth": 1.5
            }
        })
    if ind_union_real and not ind_union_real.is_empty:
        realistic_features.append({
            "type": "Feature",
            "geometry": mapping(ind_union_real),
            "properties": {
                "name": "New India (Realistic Majority Partition)",
                "color": "#f97316",
                "fill": "#f97316",
                "fillOpacity": 0.55,
                "stroke": "#c2410c",
                "strokeWidth": 1.5
            }
        })

    # OPTIMISTIC CONTIGUOUS STATE PARTITION VIA HIGH-MINORITY NORTHERN CORRIDOR GRAPH
    G = nx.Graph()
    for i in range(num_items):
        G.add_node(i, pct=processed_items[i]["current_pct"], is_pak=(processed_items[i]["current_pct"] >= 50.0))

    for i in range(num_items):
        for j in adj_matrix[i]:
            if j > i:
                G.add_edge(i, j)

    pak_nodes = [n for n, d in G.nodes(data=True) if d["is_pak"]]
    subG_pak = G.subgraph(pak_nodes)
    components = list(nx.connected_components(subG_pak))

    main_comp = max(components, key=len) if components else set()

    corridor_nodes = set(main_comp)
    for comp in components:
        if comp == main_comp:
            continue
        shortest_path = None
        min_len = 999999
        for n_comp in comp:
            for n_main in main_comp:
                try:
                    p = nx.shortest_path(G, source=n_comp, target=n_main)
                    if len(p) < min_len:
                        min_len = len(p)
                        shortest_path = p
                except nx.NetworkXNoPath:
                    pass
        if shortest_path:
            for node in shortest_path:
                corridor_nodes.add(node)

    pakistan_shapes_optimistic = [processed_items[i]["shape"] for i in corridor_nodes]
    india_shapes_optimistic = [processed_items[i]["shape"] for i in range(num_items) if i not in corridor_nodes]

    pak_union_opt = unary_union(pakistan_shapes_optimistic) if pakistan_shapes_optimistic else None
    ind_union_opt = unary_union(india_shapes_optimistic) if india_shapes_optimistic else None

    optimistic_features = []
    if pak_union_opt and not pak_union_opt.is_empty:
        optimistic_features.append({
            "type": "Feature",
            "geometry": mapping(pak_union_opt),
            "properties": {
                "name": "New Pakistan (100% Contiguous State Landmass)",
                "color": "#059669",
                "fill": "#059669",
                "fillOpacity": 0.60,
                "stroke": "#065f46",
                "strokeWidth": 2.0
            }
        })
    if ind_union_opt and not ind_union_opt.is_empty:
        optimistic_features.append({
            "type": "Feature",
            "geometry": mapping(ind_union_opt),
            "properties": {
                "name": "New India (100% Contiguous State Landmass)",
                "color": "#ea580c",
                "fill": "#ea580c",
                "fillOpacity": 0.60,
                "stroke": "#9a3412",
                "strokeWidth": 2.0
            }
        })

    final_results = {
        "title": f"Demographic Shift & State Partition ({base_year} AD Baseline)",
        "alternate_outcome": plan.prompt_explanation,
        "key_changes": [
            f"Base Year Census Baseline: {base_year} AD",
            f"Target Demographic Concentration: {target_pct}%",
            f"Spatial Scaling & Neighbor Blend (Alpha): {alpha}",
            f"Realistic Partition Threshold: 50% majority cut",
            f"Optimistic Partition Model: High-Minority Northern Land Corridor (100% Contiguous State)"
        ],
        "butterfly_effects": [
            "Demographic shifts alter regional electoral and economic centers.",
            "District-level spectrum reveals high-concentration minority corridors.",
            "Contiguous landmass partition prevents isolated enclaves."
        ],
        "geojson_before": {
            "type": "FeatureCollection",
            "features": baseline_features
        },
        "geojson_districts": {
            "type": "FeatureCollection",
            "features": district_spectrum_features
        },
        "geojson_audit": {
            "type": "FeatureCollection",
            "features": audit_features
        },
        "geojson_after_realistic": {
            "type": "FeatureCollection",
            "features": realistic_features
        },
        "geojson_after_optimistic": {
            "type": "FeatureCollection",
            "features": optimistic_features
        },
        "territories_before": [
            {"name": "British India", "status": "baseline", "color": "#d97706", "description": "1941 Census Undivided British India Territory"}
        ],
        "territories_after_realistic": [
            {"name": "New Pakistan", "status": "direct_control", "color": "#10b981", "description": "Realistic 50%+ Majority Partition Boundary"},
            {"name": "New India", "status": "direct_control", "color": "#f97316", "description": "Realistic Non-Muslim Majority Partition Boundary"}
        ],
        "territories_after_optimistic": [
            {"name": "New Pakistan", "status": "direct_control", "color": "#059669", "description": "Optimistic 100% Contiguous State Corridor"},
            {"name": "New India", "status": "direct_control", "color": "#ea580c", "description": "Optimistic 100% Contiguous State Corridor"}
        ],
        "historical_context": f"Demographic shift simulation based on {base_year} Census of India records.",
        "what_actually_happened": "Historical 1947 Partition of British India.",
        "base_year": base_year,
        "confidence_score": 0.92
    }

    return {
        "status": "completed",
        "results": final_results,
        "geojson_before": final_results["geojson_before"],
        "geojson_districts": final_results["geojson_districts"],
        "realistic_features": realistic_features,
        "optimistic_features": optimistic_features
    }
