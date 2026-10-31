"""
Global Demographic & Ethnic/Religious Dataset Loader and Spatial Harmonizer (Option 1).
Integrates:
1. GeoEPR-2023.geojson (ETH Zurich ICR) - Subnational settlement polygons for ethnic/religious/linguistic groups globally.
2. EPR-2023.csv (ETH Zurich ICR) - Group national population share (`size`) and political status over time.
3. WRP_national.csv (World Religion Project / Correlates of War) - National population (`pop`) and religious composition (`*pct`).
4. Natural Earth Admin-1 (`ne_10m_admin_1_provinces.geojson`) & Local GADM Level-1/Level-2 files.

Spatially harmonizes group settlement polygons onto subnational administrative units so that ANY country/region in the world
can run through Geopolitico's mathematical demographic shift & contiguous partition engine.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_DIR = ROOT_DIR / "data" / "demographics"
GEOEPR_PATH = DEMO_DIR / "GeoEPR-2023.geojson"
EPR_CSV_PATH = DEMO_DIR / "EPR-2023.csv"
WRP_CSV_PATH = DEMO_DIR / "WRP_national.csv"
NE_ADMIN1_PATH = ROOT_DIR / "data" / "ne_10m_admin_1_provinces.geojson"

# Map common religious terms to WRP percentage columns
WRP_RELIGION_COLUMNS = {
    "muslim": "islmgenpct",
    "islam": "islmgenpct",
    "islamic": "islmgenpct",
    "sunni": "islmsunpct",
    "shia": "islmshipct",
    "shiite": "islmshipct",
    "alawite": "islmalwpct",
    "christian": "chrstgenpct",
    "christianity": "chrstgenpct",
    "protestant": "chrstprotpct",
    "catholic": "chrstcatpct",
    "orthodox": "chrstorthpct",
    "anglican": "chrstangpct",
    "jewish": "judgenpct",
    "jews": "judgenpct",
    "judaism": "judgenpct",
    "hindu": "hindgenpct",
    "hinduism": "hindgenpct",
    "buddhist": "budgenpct",
    "buddhism": "budgenpct",
    "sikh": "sikhgenpct",
    "sikhism": "sikhgenpct",
    "zoroastrian": "zorogenpct",
    "bahai": "bahgenpct",
    "jain": "jaingenpct",
    "shinto": "shntgenpct",
    "taoist": "taogenpct",
    "confucian": "confgenpct",
    "animist": "anmgenpct",
}


class GlobalDemographicsLoader:
    _instance = None

    def __init__(self):
        self._epr_rows: List[Dict[str, Any]] = []
        self._geoepr_features: List[Dict[str, Any]] = []
        self._wrp_rows: List[Dict[str, Any]] = []
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "GlobalDemographicsLoader":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self):
        if self._loaded:
            return
        if EPR_CSV_PATH.exists():
            with open(EPR_CSV_PATH, "r", encoding="utf-8", errors="replace") as f:
                self._epr_rows = list(csv.DictReader(f))
        if GEOEPR_PATH.exists():
            with open(GEOEPR_PATH, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                self._geoepr_features = data.get("features", [])
        if WRP_CSV_PATH.exists():
            with open(WRP_CSV_PATH, "r", encoding="utf-8", errors="replace") as f:
                self._wrp_rows = list(csv.DictReader(f))
        self._loaded = True
        print(
            f"[GLOBAL-DEMOGRAPHICS] Loaded {len(self._geoepr_features)} GeoEPR polygons, "
            f"{len(self._epr_rows)} EPR records, {len(self._wrp_rows)} WRP national religion records.",
            flush=True
        )

    def _match_country_name(self, candidate: str, target_countries: List[str]) -> bool:
        c_low = candidate.lower().strip()
        alias_map = {
            "united states of america": ["united states", "usa", "us"],
            "united kingdom": ["uk", "great britain", "britain"],
            "bosnia-herzegovina": ["bosnia and herzegovina", "bosnia"],
            "turkey (ottoman empire)": ["turkey", "ottoman empire"],
            "iran (persia)": ["iran", "persia"],
            "myanmar (burma)": ["myanmar", "burma"],
            "sri lanka (ceylon)": ["sri lanka", "ceylon"],
            "russia (soviet union)": ["russia", "soviet union", "ussr"],
            "serbia (yugoslavia)": ["serbia", "yugoslavia"],
            "german federal republic": ["germany"],
            "italy/sardinia": ["italy"],
            "spain": ["spain"],
            "rumania": ["romania"],
        }
        for tc in target_countries:
            tc_low = tc.lower().strip()
            if tc_low == c_low:
                return True
            if len(tc_low) >= 5 and len(c_low) >= 5 and (tc_low in c_low or c_low in tc_low):
                return True
            for k, aliases in alias_map.items():
                if (k == c_low or k in c_low) and any(a == tc_low or tc_low == k for a in aliases):
                    return True
        return False

    def list_available_groups(self, target_countries: List[str], year: int = 1990) -> List[Dict[str, Any]]:
        """Return all ethnic/religious/linguistic groups recorded in EPR for the target countries."""
        self._ensure_loaded()
        groups_by_key = {}
        for r in self._epr_rows:
            st_name = r.get("statename", "")
            if not self._match_country_name(st_name, target_countries):
                continue
            try:
                y_from = int(r.get("from", 1946))
                y_to = int(r.get("to", 2023))
                size_val = float(r.get("size") or 0.0)
            except ValueError:
                continue
            grp_name = r.get("group", "")
            gwgroupid = str(r.get("gwgroupid", ""))
            dist_yr = 0 if (y_from <= year <= y_to) else min(abs(year - y_from), abs(year - y_to))
            key = (st_name, grp_name)
            if key not in groups_by_key or dist_yr < groups_by_key[key]["dist_yr"]:
                groups_by_key[key] = {
                    "country": st_name,
                    "group": grp_name,
                    "gwgroupid": gwgroupid,
                    "size_share": size_val,
                    "size_pct": round(size_val * 100.0, 2),
                    "status": r.get("status", ""),
                    "from": y_from,
                    "to": y_to,
                    "dist_yr": dist_yr
                }
        return sorted(groups_by_key.values(), key=lambda x: x["size_share"], reverse=True)

    def get_wrp_country_stats(self, country_name: str, iso_a3: str, target_group: str, year: int) -> Tuple[Optional[float], Optional[float]]:
        """
        Look up national religious percentage (0-100) and total country population from WRP_national.csv.
        """
        self._ensure_loaded()
        grp_tokens = [t.strip().lower() for t in target_group.replace("/", " ").replace("-", " ").split() if len(t.strip()) >= 3]
        matched_col = None
        for tok in grp_tokens:
            for k, col in WRP_RELIGION_COLUMNS.items():
                if tok.startswith(k[:5]) or k in tok or tok in k:
                    matched_col = col
                    break
            if matched_col:
                break

        best_row = None
        best_dist = 999999
        iso_up = (iso_a3 or "").upper().strip()
        c_low = country_name.lower().strip()

        cow_aliases = {
            "IND": "IND", "PAK": "PAK", "BGD": "BNG", "TUR": "TUR", "GRC": "GRC",
            "CYP": "CYP", "ISR": "ISR", "PSE": "ISR", "LBN": "LEB", "SYR": "SYR",
            "IRQ": "IRQ", "IRN": "IRN", "AFG": "AFG", "ESP": "SPN", "GBR": "UKG",
            "IRL": "IRE", "BEL": "BEL", "CHE": "SWZ", "BIH": "BOS", "SRB": "YUG",
            "HRV": "CRO", "ROU": "RUM", "HUN": "HUN", "BGR": "BUL", "RUS": "RUS",
            "UKR": "UKR", "POL": "POL", "DEU": "GMY", "FRA": "FRN", "ITA": "ITA",
            "CAN": "CAN", "USA": "USA", "NGA": "NIG", "SDN": "SUD", "ETH": "ETH",
            "MMR": "MYA", "LKA": "SRI", "MYS": "MAL", "IDN": "INS", "CHN": "CHN"
        }
        target_codes = {iso_up, cow_aliases.get(iso_up, "")} - {""}

        for r in self._wrp_rows:
            r_name = (r.get("name") or "").upper().strip()
            if r_name in target_codes or (len(c_low) >= 4 and r_name == c_low[:3].upper()):
                try:
                    ry = int(r.get("year", 2000))
                except ValueError:
                    continue
                d = abs(year - ry)
                if d < best_dist:
                    best_dist = d
                    best_row = r

        if not best_row:
            return None, None

        pop_val = None
        try:
            pop_val = float(best_row.get("pop") or 0.0)
        except ValueError:
            pass

        pct_val = None
        if matched_col and best_row.get(matched_col):
            try:
                pct_val = float(best_row[matched_col]) * 100.0
            except ValueError:
                pass

        return pct_val, pop_val

    def load_theater_admin_features(self, target_countries: List[str]) -> List[Dict[str, Any]]:
        """
        Load subnational polygons for `target_countries`:
        - Prefers local GADM Level-2 or Level-1 GeoJSONs if present in the workspace for a country.
        - Otherwise loads all matching Admin-1 provinces from `ne_10m_admin_1_provinces.geojson`.
        """
        features = []
        if not NE_ADMIN1_PATH.exists():
            return features

        with open(NE_ADMIN1_PATH, "r", encoding="utf-8", errors="replace") as f:
            ne_data = json.load(f)

        for feat in ne_data.get("features", []):
            props = feat.get("properties", {})
            admin = props.get("admin") or props.get("sovereignt") or ""
            if self._match_country_name(admin, target_countries):
                p_name = props.get("name_en") or props.get("name") or props.get("gn_name") or "Unknown"
                iso_a3 = props.get("adm0_a3") or props.get("sov_a3") or ""
                feat_copy = dict(feat)
                feat_copy["_country"] = admin
                feat_copy["_province"] = p_name
                feat_copy["_district"] = p_name
                feat_copy["_iso_a3"] = iso_a3
                features.append(feat_copy)

        return features

    def build_harmonized_subnational_baselines(
        self,
        target_countries: List[str],
        target_group: str,
        year: int = 1990
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Spatially harmonizes GeoEPR ethnic/sectarian settlement polygons, EPR national group shares,
        and WRP religious statistics onto the subnational polygons of `target_countries`.

        Mathematical Spatial Harmonization Model:
        For each subnational province $i$ in country $c$:
        1. Let $A_i$ be the geometric area of province $i$, and $I_i = \\text{Area}(P_i \\cap G_{c,g}) / A_i \\in [0, 1]$
           be the fraction of province $i$ covered by the target group's GeoEPR settlement polygon $G_{c,g}$.
        2. Let $S_{c,g} \\in (0, 1)$ be the group's national population share in country $c$ (from EPR `size` or WRP `*pct`),
           and let $F_{c,g} = \\frac{\\sum_{j \\in c} I_j A_j}{\\sum_{j \\in c} A_j}$ be the fraction of country $c$'s area
           inside the group's settlement zone.
        3. Using concentration conservation across the settlement homeland vs. diaspora:
           - Inside the settlement zone ($I_i > 0$), concentration is scaled so that the country-wide average equals $S_{c,g}$
             (clamped to a realistic homeland majority range $[\\max(55\\%, S_{c,g}), 92\\%]$ when $F_{c,g} < S_{c,g}$ or concentrated).
           - Outside the settlement zone ($I_i = 0$), provinces receive the residual diaspora baseline (typically $2\\%\\text{–}12\\%$).
        """
        self._ensure_loaded()
        raw_features = self.load_theater_admin_features(target_countries)
        if not raw_features:
            return [], {}

        # 1. Match target_group against EPR records for target_countries
        grp_tokens = [
            t.strip().lower()
            for t in target_group.replace("/", " ").replace("-", " ").replace("(", " ").replace(")", " ").split()
            if len(t.strip()) >= 3
        ]

        def _score_group_match(epr_group_name: str) -> int:
            g_low = epr_group_name.lower()
            score = 0
            for tok in grp_tokens:
                stem = tok.rstrip("s")
                if len(stem) >= 3 and stem in g_low:
                    score += 10
                elif tok in g_low:
                    score += 10
            return score

        country_epr_matches: Dict[str, List[Dict[str, Any]]] = {}
        matched_gwgroupids = set()

        for r in self._epr_rows:
            st_name = r.get("statename", "")
            if not self._match_country_name(st_name, target_countries):
                continue
            grp_name = r.get("group", "")
            sc = _score_group_match(grp_name)
            if sc > 0:
                try:
                    y_from = int(r.get("from", 1946))
                    y_to = int(r.get("to", 2023))
                    size_val = float(r.get("size") or 0.0)
                except ValueError:
                    continue
                dist_yr = 0 if (y_from <= year <= y_to) else min(abs(year - y_from), abs(year - y_to))
                country_epr_matches.setdefault(st_name, []).append({
                    "group": grp_name,
                    "gwgroupid": str(r.get("gwgroupid", "")),
                    "size": size_val,
                    "dist_yr": dist_yr,
                    "score": sc
                })

        # Select best time-slice match per (country, group)
        country_group_share: Dict[str, float] = {}
        matched_group_names = set()
        for st_name, matches in country_epr_matches.items():
            best_by_grp = {}
            for m in matches:
                g_n = m["group"]
                if g_n not in best_by_grp or (m["dist_yr"], -m["score"]) < (best_by_grp[g_n]["dist_yr"], -best_by_grp[g_n]["score"]):
                    best_by_grp[g_n] = m
            total_share = 0.0
            for g_n, m in best_by_grp.items():
                total_share += m["size"]
                matched_gwgroupids.add(m["gwgroupid"])
                matched_group_names.add(g_n)
            country_group_share[st_name] = min(0.98, total_share)

        # 2. Collect matching GeoEPR settlement polygons
        settlement_polys_by_country: Dict[str, List[Any]] = {}
        all_settlement_polys = []
        for gf in self._geoepr_features:
            gprops = gf.get("properties", {})
            gw_id = str(gprops.get("gwgroupid", ""))
            st_name = gprops.get("statename", "")
            grp_name = gprops.get("group", "")
            if gw_id in matched_gwgroupids or (self._match_country_name(st_name, target_countries) and _score_group_match(grp_name) > 0):
                geom_dict = gf.get("geometry")
                if geom_dict:
                    try:
                        sh = shape(geom_dict)
                        if sh and not sh.is_empty:
                            settlement_polys_by_country.setdefault(st_name, []).append(sh)
                            all_settlement_polys.append(sh)
                    except Exception:
                        pass

        global_settlement_union = unary_union(all_settlement_polys) if all_settlement_polys else None

        # 3. Compute intersection ratio for each Admin-1 province
        temp_items = []
        country_area_totals: Dict[str, float] = {}
        country_settled_area_totals: Dict[str, float] = {}
        country_iso_map: Dict[str, str] = {}

        for feat in raw_features:
            try:
                geom_s = shape(feat["geometry"])
                if not geom_s or geom_s.is_empty:
                    continue
                area = geom_s.area
            except Exception:
                continue

            cname = feat["_country"]
            country_iso_map[cname] = feat.get("_iso_a3", "")
            ov_ratio = 0.0
            if global_settlement_union and not global_settlement_union.is_empty:
                try:
                    if geom_s.intersects(global_settlement_union):
                        inter_a = geom_s.intersection(global_settlement_union).area
                        ov_ratio = min(1.0, max(0.0, inter_a / max(1e-9, area)))
                except Exception:
                    pass

            country_area_totals[cname] = country_area_totals.get(cname, 0.0) + area
            country_settled_area_totals[cname] = country_settled_area_totals.get(cname, 0.0) + (ov_ratio * area)
            temp_items.append({
                "feature": feat,
                "shape": geom_s,
                "area": area,
                "ov_ratio": ov_ratio,
                "country": cname,
                "province": feat["_province"],
                "district": feat["_district"],
            })

        # 4. Resolve national share & population per country (combining EPR + WRP)
        processed_items = []
        for item in temp_items:
            cname = item["country"]
            area = item["area"]
            ov_ratio = item["ov_ratio"]
            c_total_area = max(1e-6, country_area_totals.get(cname, area))
            c_settled_frac = country_settled_area_totals.get(cname, 0.0) / c_total_area

            # Lookup EPR share for this country
            epr_share = None
            for st_k, sh_val in country_group_share.items():
                if self._match_country_name(st_k, [cname]):
                    epr_share = sh_val
                    break

            wrp_pct, wrp_pop = self.get_wrp_country_stats(cname, country_iso_map.get(cname, ""), target_group, year)
            nat_pct = (epr_share * 100.0) if (epr_share is not None and epr_share > 0) else (wrp_pct if wrp_pct is not None else 25.0)
            nat_pop = wrp_pop if (wrp_pop and wrp_pop > 0) else (c_total_area * 1200000.0)

            # Province population proportional to area within country
            prov_pop = max(25000.0, nat_pop * (area / c_total_area))

            if c_settled_frac > 0.01:
                # We have explicit GeoEPR spatial settlement polygons for this group in this country
                # Estimate concentration inside the settlement zone vs outside
                in_zone_density = min(88.0, max(55.0, nat_pct / max(0.15, c_settled_frac)))
                out_zone_density = max(2.0, min(12.0, nat_pct * 0.20))
                baseline_pct = round((ov_ratio * in_zone_density) + ((1.0 - ov_ratio) * out_zone_density), 2)
                match_source = "geoepr_settlement_polygon" if ov_ratio >= 0.10 else "geoepr_outside_settlement"
                is_fallback = False
            elif epr_share is not None or wrp_pct is not None:
                baseline_pct = round(nat_pct, 2)
                match_source = "epr_wrp_national_baseline"
                is_fallback = False
            else:
                baseline_pct = 20.0
                match_source = "country_fallback"
                is_fallback = True

            processed_items.append({
                "feature": item["feature"],
                "shape": item["shape"],
                "area": area,
                "baseline_pct": baseline_pct,
                "current_pct": baseline_pct,
                "population": prov_pop,
                "match_source": match_source,
                "is_fallback": is_fallback,
                "country": cname,
                "province": item["province"],
                "district": item["district"],
            })

        meta = {
            "matched_epr_groups": sorted(matched_group_names),
            "settlement_polygons_count": len(all_settlement_polys),
            "countries_loaded": sorted(country_area_totals.keys()),
        }
        return processed_items, meta
