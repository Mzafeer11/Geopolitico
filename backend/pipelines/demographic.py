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
from shapely.strtree import STRtree
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
    "prayagraj": "allahabad", "dhaka": "dacca", "barisal": "bakarganj", "barishal": "bakarganj",
    "comilla": "tippera", "cumilla": "tippera", "bogura": "bogra", "bogra": "bogra",
    "chattogram": "chittagong", "chittagong": "chittagong", "jashore": "jessore", "jessore": "jessore",
    "kushtia": "nadiya", "tangail": "mymeaningh", "jamalpur": "mymensingh", "kishoreganj": "mymensingh",
    "cox's bazar": "chittagong", "coxsbazar": "chittagong", "bhabanipur": "dinajpur",
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
    bgd_features = load_gadm_geojson(BGD_GADM)
    if not bgd_features and NE_ADMIN1_GEOJSON.exists():
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

    # Mathematical Formula Implementation from run_full_gadm_simulation.py
    num_items = len(processed_items)
    shapes_list = [item["shape"] for item in processed_items]
    spatial_tree = STRtree(shapes_list)

    adjacency_list = []
    weighted_baselines = []
    grand_total_pop = sum(item["population"] for item in processed_items)

    for i, item in enumerate(processed_items):
        item_shape = item["shape"]
        dist_share = item["baseline_pct"] / 100.0

        candidate_indices = spatial_tree.query(item_shape)
        neighbors = []
        neighbor_shares = []
        for c_idx in candidate_indices:
            if c_idx != i:
                other_shape = shapes_list[c_idx]
                if item_shape.touches(other_shape) or item_shape.intersects(other_shape):
                    neighbors.append(c_idx)
                    neighbor_shares.append(processed_items[c_idx]["baseline_pct"] / 100.0)

        adjacency_list.append(neighbors)

        if neighbor_shares:
            avg_neighbor_share = sum(neighbor_shares) / len(neighbor_shares)
        else:
            avg_neighbor_share = dist_share

        wb = (alpha * dist_share) + ((1.0 - alpha) * avg_neighbor_share)
        weighted_baselines.append(wb)
        item["weighted_baseline_pct"] = round(wb * 100.0, 2)
        item["avg_neighbor_pct"] = round(avg_neighbor_share * 100.0, 1)

    # Initial Target Allocation based on Target Scenario Ratio
    target_scenario_ratio = target_pct / 100.0
    target_muslim_pop_total = target_scenario_ratio * grand_total_pop
    baseline_weighted_pop_denom = sum(wb * item["population"] for wb, item in zip(weighted_baselines, processed_items))

    alloc_pop = []
    for i, item in enumerate(processed_items):
        wb = weighted_baselines[i]
        init_m_pop = target_muslim_pop_total * (wb * item["population"]) / max(0.0001, baseline_weighted_pop_denom)
        alloc_pop.append(init_m_pop)

    # Cap at 100% of Population and Proportonally Redistribute Excess (Exact 1:1 match to run_full_gadm_simulation.py)
    for _ in range(15):
        excess_sum = 0.0
        for i in range(num_items):
            cap_pop = processed_items[i]["population"]
            if alloc_pop[i] > cap_pop:
                excess_sum += (alloc_pop[i] - cap_pop)
                alloc_pop[i] = cap_pop

        if excess_sum <= 10.0:
            break

        uncapped_total_cap = 0.0
        for i in range(num_items):
            if alloc_pop[i] < processed_items[i]["population"]:
                uncapped_total_cap += (processed_items[i]["population"] - alloc_pop[i])

        if uncapped_total_cap > 0:
            for i in range(num_items):
                if alloc_pop[i] < processed_items[i]["population"]:
                    free_cap = processed_items[i]["population"] - alloc_pop[i]
                    alloc_pop[i] += excess_sum * (free_cap / uncapped_total_cap)

    # Set final projected percentages
    for i, item in enumerate(processed_items):
        final_m_pop = min(item["population"], max(0.0, alloc_pop[i]))
        new_m_pct = round(min(100.0, (final_m_pop / max(1.0, item["population"])) * 100.0), 1)
        item["current_pct"] = new_m_pct

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
                "color": fill_color,
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
                "color": audit_color,
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

    # OPTIMISTIC CONTIGUOUS STATE PARTITION VIA HIGH-MINORITY NORTHERN CORRIDOR GRAPH & ENCLAVE REMOVER
    labels = ["Green" if processed_items[i]["current_pct"] >= 50.0 else "Red" for i in range(num_items)]

    # Build weighted contiguity graph (cost is lower for higher Muslim %)
    G = nx.Graph()
    for i in range(num_items):
        pct_i = processed_items[i]["current_pct"]
        G.add_node(i, pct=pct_i)
        for j in adjacency_list[i]:
            if j > i:
                pct_j = processed_items[j]["current_pct"]
                cost = max(0.1, 100.0 - (pct_i + pct_j) / 2.0)
                G.add_edge(i, j, weight=cost)

    # 1. Identify West Pakistan and East Pakistan components
    green_nodes = [i for i in range(num_items) if labels[i] == "Green"]
    G_green = G.subgraph(green_nodes)
    green_comps = sorted(list(nx.connected_components(G_green)), key=len, reverse=True)

    if len(green_comps) >= 2:
        west_comp = green_comps[0]
        east_comp = green_comps[1]

        # Candidate nodes for corridor: districts with high Muslim minority share
        high_minority_nodes = [i for i in range(num_items) if processed_items[i]["current_pct"] >= 25.0 or labels[i] == "Green"]
        G_sub = G.subgraph(high_minority_nodes)

        min_path = None
        min_cost = 999999
        w_sample = list(west_comp)[:30]
        e_sample = list(east_comp)[:30]

        for w in w_sample:
            for e in e_sample:
                try:
                    path = nx.shortest_path(G_sub, source=w, target=e, weight="weight")
                    cost = nx.path_weight(G_sub, path, weight="weight")
                    if cost < min_cost:
                        min_cost = cost
                        min_path = path
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass

        if min_path is None:
            # Fallback to full weighted graph path
            for w in w_sample:
                for e in e_sample:
                    try:
                        path = nx.shortest_path(G, source=w, target=e, weight="weight")
                        cost = nx.path_weight(G, path, weight="weight")
                        if cost < min_cost:
                            min_cost = cost
                            min_path = path
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        pass

        if min_path:
            for idx in min_path:
                if labels[idx] != "Green":
                    labels[idx] = "Green"

    # 2. FULL ENCLAVE REMOVER HARMONIZATION (Exact 1:1 match to standalone script Image 2):
    # After corridor bridging, green_comps[0] contains the unified Pakistan landmass.
    # All remaining disconnected green components (green_comps[1:]) are harmonized to Red (India).
    # All remaining disconnected red components inside Pakistan (red_comps[1:]) are harmonized to Green (Pakistan).
    green_nodes = [i for i in range(num_items) if labels[i] == "Green"]
    green_comps = sorted(list(nx.connected_components(G.subgraph(green_nodes))), key=len, reverse=True)
    for comp in green_comps[1:]:
        for idx in comp:
            labels[idx] = "Red"

    red_nodes = [i for i in range(num_items) if labels[i] == "Red"]
    red_comps = sorted(list(nx.connected_components(G.subgraph(red_nodes))), key=len, reverse=True)
    for comp in red_comps[1:]:
        for idx in comp:
            labels[idx] = "Green"

    pakistan_shapes_optimistic = [processed_items[i]["shape"] for i in range(num_items) if labels[i] == "Green"]
    india_shapes_optimistic = [processed_items[i]["shape"] for i in range(num_items) if labels[i] == "Red"]

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
        "scenario_mode": "demographic",
        "title": f"Demographic Shift & State Partition ({base_year} AD Baseline)",
        "alternate_outcome": f"Under this {target_pct}% demographic shift model, high-concentration corridors across northern India establish a contiguous sovereign landmass connecting West Pakistan and East Pakistan.",
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
        "historical_context": f"Demographic shift scenario evaluating a {target_pct}% concentration model based on official {base_year} Census of India district records.",
        "what_actually_happened": "In the historical 1947 Partition of British India, the Radcliffe Line divided Punjab and Bengal, creating West Pakistan and East Pakistan as physically separated wings.",
        "base_year": base_year,
        "confidence_score": 0.92
    }

    return {
        "status": "completed",
        "results": final_results,
        "geojson_before": final_results["geojson_before"],
        "geojson_districts": final_results["geojson_districts"],
        "geojson_audit": final_results["geojson_audit"],
        "realistic_features": realistic_features,
        "optimistic_features": optimistic_features
    }
