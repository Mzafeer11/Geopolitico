import os
import json
import uuid
import traceback
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from shapely.geometry import shape, box
from backend.config import GITHUB_TOKEN, GITHUB_API_URL, GITHUB_MODELS, EXHAUSTED_MODELS, DATA_DIR
from backend.tools.cliopatria_loader import cliopatria_db
from backend.tools.country_polygons import CountryPolygonLoader
from backend.agents.prompt_guardrail import refine_user_prompt
from backend.tools.gis_tools import geocode_landmark_tool, natural_boundary_tool, wikipedia_demographics_tool

# ─── Session Store ───────────────────────────────────────────────────────────
_sessions: Dict[str, Dict[str, Any]] = {}

# Load persistently blacklisted models from JSON cache
_BLACKLIST_FILE = Path(DATA_DIR) / "blacklisted_models.json"
_BLACKLISTED_MODELS = set()
if _BLACKLIST_FILE.exists():
    try:
        with open(_BLACKLIST_FILE, "r") as _f:
            _BLACKLISTED_MODELS = set(json.load(_f))
    except Exception:
        pass

# ─── Natural Boundaries mapping ──────────────────────────────────────────────
BOUNDARY_COUNTRIES_MAP = {
    "loire": ["France"],
    "pyrenees": ["France", "Spain", "Andorra"],
    "pyrénées": ["France", "Spain", "Andorra"],
    "alps": ["France", "Italy", "Switzerland", "Germany", "Austria", "Slovenia", "Liechtenstein"],
    "rhine": ["Germany", "France", "Switzerland", "Netherlands", "Austria", "Liechtenstein"],
    "danube": ["Germany", "Austria", "Slovakia", "Hungary", "Croatia", "Serbia", "Romania", "Bulgaria", "Moldova", "Ukraine"],
    "bosphorus": ["Turkey"],
    "chenab": ["India", "Pakistan"],
    "rhone": ["France", "Switzerland"],
    "rhône": ["France", "Switzerland"]
}


# ─── Pydantic Output Schemas ──────────────────────────────────────────────────


class PlanningResult(BaseModel):
    year: int = Field(description="The target base year of the simulation context.")
    parties: List[str] = Field(description="The primary historical/modern states/parties involved in the scenario (e.g. ['Umayyad Caliphate', 'Kingdom of the Franks']).")
    baseline_polities: List[str] = Field(description="The exact polity names in the Cliopatria dataset representing the starting baseline geography (e.g. ['British India'] or ['Umayyad Caliphate', 'Kingdom of the Franks']).")
    simulation_mode: Literal["expansion_conquest", "proposal_partition", "demographic_shift", "compounding_conquest"] = Field(
        description="Mode of simulation: 'proposal_partition' for treaties/formulas, 'demographic_shift' for population changes, 'expansion_conquest' for military events, 'compounding_conquest' for sequential compounding conflicts."
    )
    target_region: str = Field(description="The primary geographic region where the event takes place (e.g. 'Southern France', 'Kashmir').")
    target_countries: List[str] = Field(default=[], description="List of modern sovereign countries containing the conflict zone (e.g. ['France', 'Spain'] or ['India', 'Pakistan']).")
    baseline_description: str = Field(description="Brief explanation of the real-world historical context of the base year.")


class SequentialScenarioPlan(BaseModel):
    scenario_1: str = Field(description="Counterfactual prompt for the first chronological event (e.g. Constantinople in 717 AD)")
    year_1: int = Field(description="The year of the first event")
    scenario_2: str = Field(description="Counterfactual prompt for the second chronological event (e.g. Tours in 732 AD)")
    year_2: int = Field(description="The year of the second event")


class SplitProvince(BaseModel):
    name: str = Field(description="The modern province name to split (must match a name in provinces).")
    is_split: bool = Field(default=False, description="True if this province is split/shared between polities.")
    split_direction: str = Field(default="center", description="Where this polity's territory lies in the split: 'north_of_natural_boundary', 'south_of_natural_boundary', 'north_of_latitude', 'south_of_latitude', 'west_of_longitude', 'east_of_longitude', 'north_west_diagonal', 'south_east_diagonal', 'center' (if not split).")
    split_value: Optional[float] = Field(default=None, description="Optional custom coordinate value (latitude or longitude) to split at. If null, splits 50/50 through centroid or uses the natural boundary geometry if detected.")


class PartialRegion(BaseModel):
    country: str = Field(description="Modern country name.")
    provinces: List[str] = Field(description="List of modern province names within the country.")
    split_provinces: List[SplitProvince] = Field(default=[], description="List of custom geometric splitting configurations for shared/partitioned provinces.")
    clip_method: Literal["provinces", "natural_boundary", "coordinate_latitude", "coordinate_longitude"] = Field(
        default="provinces",
        description="Method to clip/select geometry: 'provinces' (use provinces list), 'natural_boundary' (clip country by river/mountains), 'coordinate_latitude', 'coordinate_longitude'."
    )
    clip_value: Optional[float] = Field(None, description="Coordinate value for clipping (latitude or longitude).")
    clip_description: str = Field(default="", description="Name of the natural boundary (e.g. 'Loire River', 'Pyrenees') if clip_method is 'natural_boundary'.")
    clip_direction: Optional[str] = Field(
        None,
        description="Direction to keep: 'north_of_natural_boundary', 'south_of_natural_boundary', 'west_of_longitude', 'east_of_longitude', 'north_of_latitude', 'south_of_latitude'."
    )
    landmark_city: Optional[str] = Field(None, description="Reference landmark city.")
    status: Literal["direct_control", "vassal", "tributary"] = Field(
        default="direct_control",
        description="Status: 'direct_control', 'vassal', or 'tributary'."
    )


class EnclaveResolutionOption(BaseModel):
    action: Literal["addition", "subtraction"] = Field(description="Whether this option adds connecting land bridge (addition) or pulls back/removes enclave (subtraction).")
    description: str = Field(description="Explanation of the choice for the user (e.g. 'Annex European Turkey to create land bridge' or 'Withdraw from Greece').")
    countries_absorbed: List[str] = Field(default=[], description="List of modern country names to add/remove.")
    partial_countries: List[PartialRegion] = Field(default=[], description="List of PartialRegion definitions to add/remove.")
    
class ValidationAnomalyQuestion(BaseModel):
    id: str = Field(description="Unique ID for this anomaly (e.g., 'greece_enclave').")
    issue_description: str = Field(description="Description of the enclave/gap detected.")
    scenario_type: Literal["realistic", "optimistic"] = Field(description="Whether this anomaly is in the realistic or optimistic result.")
    option_1: EnclaveResolutionOption = Field(description="Option 1: Add connecting land bridge.")
    option_2: EnclaveResolutionOption = Field(description="Option 2: Pull back and remove enclave.")

class AnomalyCheckResult(BaseModel):
    has_anomalies: bool = Field(description="True if major disconnected enclaves/gaps are found.")
    questions: List[ValidationAnomalyQuestion] = Field(default=[], description="List of questions to resolve the detected enclaves.")

class TerritoryChange(BaseModel):
    name: str = Field(description="Name of the alternate history territory or empire.")
    type: str = Field(description="Type: empire, kingdom, republic, or region.")
    color: str = Field(description="Hex color representing the territory.")
    status: Literal["direct_control", "vassal", "tributary"] = Field(
        default="direct_control",
        description="Status: 'direct_control', 'vassal', or 'tributary'."
    )
    countries_absorbed: List[str] = Field(description="Modern countries fully controlled.")
    partial_countries: List[PartialRegion] = Field(default=[], description="Sub-provinces controlled.")
    description: str = Field(description="Explanation of the territory's geopolitical significance.")
    population_estimate: Optional[str] = Field(None, description="Population estimate.")
    capital: Optional[str] = Field(None, description="Proposed/historical capital.")

class ValidationTerritoriesResult(BaseModel):
    territories: List[TerritoryChange] = Field(description="The audited and corrected list of all territories.")


class TimelineEvent(BaseModel):
    year: int = Field(description="The year of the speculative event.")
    event: str = Field(description="Description of the event that occurs in the alternate timeline.")


class ScenarioStateResult(BaseModel):
    title: str = Field(description="Descriptive title of the state outcome.")
    alternate_outcome: str = Field(description="Detailed narrative of this alternate state scenario.")
    key_changes: List[str] = Field(description="Bullet points of major shifts (at least 3 items).")
    butterfly_effects: List[str] = Field(description="Speculative butterfly effects/ripples (at least 3 items).")
    timeline: List[TimelineEvent] = Field(description="Speculative timeline events following the base year (at least 3 events).")
    sources: List[str] = Field(description="A list of 2-3 source links (e.g. Wikipedia search or article links) relating to the historical people, treaties, or places involved.")
    territories: List[TerritoryChange] = Field(description="COMPLETE list of all territories in the empire/states after changes.")


def _get_active_model() -> str:
    """Get the first non-exhausted model, prioritizing GPT-4o models for stable schema generation."""
    available = [m for m in GITHUB_MODELS if m not in EXHAUSTED_MODELS and m not in _BLACKLISTED_MODELS]
    # Filter out nano models
    available = [m for m in available if "nano" not in m.lower()]
    
    if not available:
        EXHAUSTED_MODELS.clear()
        available = [m for m in GITHUB_MODELS if m not in _BLACKLISTED_MODELS]
        available = [m for m in available if "nano" not in m.lower()]
    
    # Prioritize GPT-4o models
    for m in available:
        if "gpt-4o" in m.lower():
            return m
    return available[0] if available else GITHUB_MODELS[0]


def _invoke_structured_with_fallback(schema, messages, temperature=0.5):
    """Tries to invoke structured output, falling back to other models on RateLimitError."""
    available_models = [m for m in GITHUB_MODELS if m not in EXHAUSTED_MODELS and m not in _BLACKLISTED_MODELS]
    # Filter out nano models from structured outputs
    available_models = [m for m in available_models if "nano" not in m.lower()]
    
    if not available_models:
        EXHAUSTED_MODELS.clear()
        _BLACKLISTED_MODELS.clear()
        try:
            if _BLACKLIST_FILE.exists():
                _BLACKLIST_FILE.unlink()
        except Exception:
            pass
        available_models = [m for m in GITHUB_MODELS if "nano" not in m.lower()]
        
    # Prioritize GPT-5 models first, then GPT-4o/4.1 models
    attempt_list = []
    for m in available_models:
        if "gpt-5" in m.lower():
            attempt_list.append(m)
    for m in available_models:
        if ("gpt-4o" in m.lower() or "gpt-4.1" in m.lower()) and m not in attempt_list:
            attempt_list.append(m)
    for m in available_models:
        if m not in attempt_list:
            attempt_list.append(m)
            
    last_error = None
    for model in attempt_list:
        clean_model = model.replace("openai/", "", 1) if model.startswith("openai/") else model
        token = os.environ.get("GITHUB_TOKEN", GITHUB_TOKEN)
        print(f"[SIMULATOR] Invoking model '{clean_model}' for structured output...")
        # Set higher token limit for GPT-5 models to accommodate large reasoning token usages
        model_max_tokens = 16384 if "gpt-5" in clean_model.lower() else 4096
        try:
            llm = ChatOpenAI(
                model=clean_model,
                api_key=token,
                base_url=GITHUB_API_URL,
                temperature=temperature,
                max_tokens=model_max_tokens,
                timeout=120.0
            )
            # Disable native function calling for non-OpenAI models to avoid API errors
            if "gpt-4o" not in clean_model.lower():
                try:
                    llm.supports_function_calling = lambda: False
                except Exception:
                    pass
            structured_llm = llm.with_structured_output(schema)
            res = structured_llm.invoke(messages)
            if res:
                try:
                    if hasattr(res, "model_dump_json"):
                        print(f"[DEBUG] Model '{clean_model}' returned structured result:\n{res.model_dump_json(indent=2)}", flush=True)
                    else:
                        print(f"[DEBUG] Model '{clean_model}' returned result: {res}", flush=True)
                except Exception as print_err:
                    print(f"[DEBUG] Error printing model result: {print_err}", flush=True)
            return res
        except Exception as e:
            print(f"[WARN] Model '{clean_model}' failed structured invoke: {e}")
            last_error = e
            # Add to exhausted list if rate limit or auth limits hit
            err_msg = str(e).lower()
            if "rate limit" in err_msg or "429" in err_msg or "quota" in err_msg or "not found" in err_msg or "too many requests" in err_msg:
                EXHAUSTED_MODELS.add(model)
                _BLACKLISTED_MODELS.add(model)
                try:
                    with open(_BLACKLIST_FILE, "w") as _f:
                        json.dump(list(_BLACKLISTED_MODELS), _f)
                except Exception:
                    pass
                print(f"[SIMULATOR] Permanently blacklisting model '{clean_model}' from further attempts.", flush=True)
                
    raise last_error or RuntimeError("All models failed to complete structured schema generation.")


def force_conquest_provinces(territories: List[TerritoryChange], scenario_text: str):
    """Post-processing guardrail to ensure critical scenario cities are added to territories."""
    scenario_lower = scenario_text.lower()
    umayyad_t = None
    for t in territories:
        if "umayyad" in t.name.lower():
            umayyad_t = t
            break
            
    if umayyad_t:
        if "constantinople" in scenario_lower:
            turkey_p = None
            for p in umayyad_t.partial_countries:
                if p.country.lower() == "turkey":
                    turkey_p = p
                    break
            else:
                turkey_p = PartialRegion(country="Turkey", provinces=[], split_provinces=[], clip_method="provinces", clip_description="Conquered Byzantine Capital")
                umayyad_t.partial_countries.append(turkey_p)
            if "Istanbul (Turkey)" not in turkey_p.provinces:
                turkey_p.provinces.append("Istanbul (Turkey)")
        if "tours" in scenario_lower or "poitiers" in scenario_lower:
            france_p = None
            for p in umayyad_t.partial_countries:
                if p.country.lower() == "france":
                    france_p = p
                    break
            else:
                france_p = PartialRegion(country="France", provinces=[], split_provinces=[], clip_method="provinces", clip_description="Conquered Tours region")
                umayyad_t.partial_countries.append(france_p)
            for f_prov in ["Vienne (France)", "Indre (France)", "Indre-et-Loire (France)", "Haute-Vienne (France)", "Deux-Sèvres (France)"]:
                if f_prov not in france_p.provinces:
                    france_p.provinces.append(f_prov)
                    
    # General post-processing to fully absorb countries on the conquered side of natural boundaries
    NATURAL_BOUNDARY_CONQUEST_ABSORB = {
        "rhine": {
            "west_of_natural_boundary": ["France", "Belgium", "Luxembourg"],
            "east_of_natural_boundary": ["Germany", "Switzerland", "Austria", "Netherlands"]
        },
        "danube": {
            "south_of_natural_boundary": ["Bulgaria", "Greece", "Turkey", "North Macedonia", "Albania", "Kosovo", "Montenegro", "Bosnia and Herzegovina"],
            "north_of_natural_boundary": ["Romania", "Moldova", "Ukraine", "Slovakia", "Hungary", "Austria"]
        },
        "loire": {
            "south_of_natural_boundary": ["Spain", "Portugal"]
        },
        "pyrenees": {
            "south_of_natural_boundary": ["Spain", "Portugal"]
        }
    }
    
    for t in territories:
        countries_to_absorb = set()
        for p in t.partial_countries:
            if p.clip_method == "natural_boundary" and p.clip_description:
                desc_lower = p.clip_description.lower()
                matched_boundary = None
                for b_name in NATURAL_BOUNDARY_CONQUEST_ABSORB:
                    if b_name in desc_lower:
                        matched_boundary = b_name
                        break
                if matched_boundary:
                    direction = p.clip_direction
                    absorb_list = NATURAL_BOUNDARY_CONQUEST_ABSORB[matched_boundary].get(direction, [])
                    for country_name in absorb_list:
                        countries_to_absorb.add(country_name)
                        
        if countries_to_absorb:
            for c in countries_to_absorb:
                # Only absorb if it was listed in partials (meaning it was included in the LLM's boundary expansion)
                # or if it is already in countries_absorbed.
                is_in_partials = any(p.country.lower() == c.lower() for p in t.partial_countries)
                if is_in_partials:
                    if c not in t.countries_absorbed:
                        t.countries_absorbed.append(c)
            # Filter out the absorbed countries from partial_countries, keeping other bisected/split countries
            t.partial_countries = [p for p in t.partial_countries if p.country.lower() not in [x.lower() for x in countries_to_absorb]]


def _run_geopolitical_validation(
    result: ScenarioStateResult, 
    scenario: str, 
    year: int, 
    context: Dict[str, Any]
) -> ScenarioStateResult:
    """Invoke the secondary validation LLM node to audit contiguity, remove enclaves, and enforce exclusivity."""
    try:
        baseline_pols = context.get("baseline_polities", []) if context else []
        winner_polity = baseline_pols[0] if baseline_pols else "Conqueror"
        
        template = _load_prompt_template("validation.txt")
        if not template:
            print("[WARN] Validation template validation.txt not found. Skipping validation node.", flush=True)
            return result
            
        current_result_json = result.model_dump_json(indent=2)
        prompt = template.format(
            scenario=scenario,
            year=year,
            winner_polity=winner_polity,
            current_result_json=current_result_json
        )
        
        print(f"[SIMULATOR] Launching Geopolitical Validation Node for '{winner_polity}'...", flush=True)
        validated_data: ValidationTerritoriesResult = _invoke_structured_with_fallback(
            ValidationTerritoriesResult, 
            [SystemMessage(content=prompt)], 
            temperature=0.2
        )
        
        # Apply force_conquest_provinces on the validated output as a post-processing guardrail
        force_conquest_provinces(validated_data.territories, scenario)
        
        # Inject the corrected territories back into the original result, keeping all narratives intact
        result.territories = validated_data.territories
        
        print("[SIMULATOR] Geopolitical Validation completed successfully.", flush=True)
        return result
    except Exception as e:
        print(f"[WARN] Geopolitical Validation failed: {e}. Falling back to original result.", flush=True)
        traceback.print_exc()
        return result


def _check_geopolitical_anomalies(
    result_real: ScenarioStateResult,
    result_opt: ScenarioStateResult,
    realistic_features: List[Dict[str, Any]],
    optimistic_features: List[Dict[str, Any]],
    scenario: str,
    year: int,
    context: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Run validation LLM to detect major contiguity enclaves, and pre-calculate highlight GeoJSONs."""
    try:
        baseline_pols = context.get("baseline_polities", []) if context else []
        winner_polity = baseline_pols[0] if baseline_pols else "Conqueror"
        
        template = _load_prompt_template("anomaly_checker.txt")
        if not template:
            print("[WARN] Anomaly checker template anomaly_checker.txt not found. Skipping.", flush=True)
            return AnomalyCheckResult(has_anomalies=False, questions=[])
            
        # Combine realistic and optimistic territories for the inspector
        input_data = {
            "realistic": [t.model_dump() for t in result_real.territories],
            "optimistic": [t.model_dump() for t in result_opt.territories]
        }
        
        prompt = template.format(
            scenario=scenario,
            year=year,
            winner_polity=winner_polity,
            territories_json=json.dumps(input_data, indent=2)
        )
        
        print("[SIMULATOR] Launching Geopolitical Contiguity and Enclave Inspector...", flush=True)
        checker_res: AnomalyCheckResult = _invoke_structured_with_fallback(
            AnomalyCheckResult,
            [SystemMessage(content=prompt)],
            temperature=0.2
        )
        
        if not checker_res.has_anomalies or not checker_res.questions:
            print("[SIMULATOR] No major contiguity enclaves detected.", flush=True)
            return False, []
            
        # Pre-calculate highlight GeoJSON features for each option
        print(f"[SIMULATOR] Detected {len(checker_res.questions)} major anomalies. Pre-calculating highlight layers...", flush=True)
        questions_with_geojson = []
        for q in checker_res.questions:
            q_dict = q.model_dump()
            
            # Option 1: Addition (Green)
            opt1 = q.option_1
            feat_list_1 = []
            if opt1.countries_absorbed or opt1.partial_countries:
                pc_list = []
                for pc in opt1.partial_countries:
                    if isinstance(pc, dict):
                        pc_list.append(PartialRegion(**pc))
                    else:
                        pc_list.append(pc)
                # Create a temporary territory to compile
                t_mock = TerritoryChange(
                    name="HighlightLayer",
                    type="region",
                    color="#2ecc71",
                    countries_absorbed=opt1.countries_absorbed,
                    partial_countries=pc_list,
                    description=opt1.description
                )
                feats = _process_territory_definitions(
                    [t_mock], year,
                    {**context, "simulation_mode": "proposal_partition", "baseline_polities": [], "compounding_resolved_geoms": None}
                )
                for f in feats:
                    f["properties"]["color"] = "#2ecc71"
                    f["properties"]["description"] = f"Proposed Addition: {opt1.description}"
                feat_list_1 = feats
            q_dict["option_1_geojson"] = {"type": "FeatureCollection", "features": feat_list_1}
            
            # Option 2: Subtraction (Red)
            opt2 = q.option_2
            feat_list_2 = []
            
            # Directly extract matching features from the already compiled target scenario map layers
            target_features = realistic_features if q.scenario_type == "realistic" else optimistic_features
            sub_countries = [c.lower() for c in opt2.countries_absorbed]
            sub_partials = [p.get("country", "").lower() if isinstance(p, dict) else p.country.lower() for p in opt2.partial_countries]
            all_sub_names = set(sub_countries + sub_partials)
            
            if all_sub_names:
                import copy
                for feat in target_features:
                    props = feat.get("properties", {})
                    c_name = props.get("country", "")
                    if not c_name:
                        c_name = props.get("name", "")
                    if c_name and c_name.lower() in all_sub_names:
                        f_copy = copy.deepcopy(feat)
                        f_copy["properties"]["color"] = "#ef4444"
                        f_copy["properties"]["description"] = f"Proposed Subtraction: {opt2.description}"
                        feat_list_2.append(f_copy)
                        
            # Fallback: if no features matched, compile via _process_territory_definitions
            if not feat_list_2 and (opt2.countries_absorbed or opt2.partial_countries):
                pc_list = []
                for pc in opt2.partial_countries:
                    if isinstance(pc, dict):
                        pc_list.append(PartialRegion(**pc))
                    else:
                        pc_list.append(pc)
                t_mock = TerritoryChange(
                    name="HighlightLayer",
                    type="region",
                    color="#ef4444",
                    countries_absorbed=opt2.countries_absorbed,
                    partial_countries=pc_list,
                    description=opt2.description
                )
                feats = _process_territory_definitions(
                    [t_mock], year,
                    {**context, "simulation_mode": "proposal_partition", "baseline_polities": [], "compounding_resolved_geoms": None}
                )
                for f in feats:
                    f["properties"]["color"] = "#ef4444"
                    f["properties"]["description"] = f"Proposed Subtraction: {opt2.description}"
                feat_list_2 = feats
            q_dict["option_2_geojson"] = {"type": "FeatureCollection", "features": feat_list_2}
            
            questions_with_geojson.append(q_dict)
            
        return True, questions_with_geojson
    except Exception as e:
        print(f"[WARN] Geopolitical Anomaly Inspector failed: {e}", flush=True)
        traceback.print_exc()
        return False, []


# ─── Spatial Contest Finder ──────────────────────────────────────────────────

def find_contested_provinces(polities: List[str], year: int, target_countries: Optional[List[str]] = None, is_partition: bool = False) -> List[str]:
    """
    Find all modern provinces that overlap or border the baseline geometries 
    of the primary conflict polities in the Cliopatria database.
    """
    loader = CountryPolygonLoader()
    contested = set()
    
    # Load disputed areas geometries if in partition mode
    disputed_geoms = []
    if is_partition:
        disputed_path = os.path.join(DATA_DIR, "ne_10m_admin_0_disputed_areas.geojson")
        if os.path.exists(disputed_path):
            try:
                with open(disputed_path, "r", encoding="utf-8") as f:
                    d_data = json.load(f)
                    for feat in d_data.get("features", []):
                        g = feat.get("geometry")
                        if g:
                            disputed_geoms.append(shape(g))
            except Exception as e:
                print(f"[SIMULATOR] Error loading disputed areas: {e}")
    
    party_shapes = []
    for polity in polities:
        feat = cliopatria_db.get_polity_geometry(polity, year)
        if feat and feat.get("geometry"):
            try:
                sh = shape(feat["geometry"])
                party_shapes.append(sh)
            except Exception as e:
                print(f"[CLIOPATRIA] Shape conversion error for '{polity}': {e}")
                
    if not party_shapes:
        return []
        
    # Intersect/proximity search over modern provinces dataset
    for f in loader.provinces_data:
        props = f.get("properties", {})
        admin = props.get("admin")
        
        # Restrict to target countries to keep prompt size small and prevent body size errors
        if target_countries and admin:
            matched = False
            for country in target_countries:
                if country.lower() in admin.lower() or admin.lower() in country.lower():
                    matched = True
                    break
            if not matched:
                continue
                
        geom_dict = f.get("geometry")
        if not geom_dict:
            continue
        try:
            prov_shape = shape(geom_dict)
            prov_bounds = prov_shape.bounds
            
            # Simple bounding box filter first to speed up check
            bbox = box(*prov_bounds)
            intersect_count = 0
            is_contested = False
            for p_sh in party_shapes:
                if p_sh.bounds[0]-1.0 <= prov_bounds[2] and prov_bounds[0] <= p_sh.bounds[2]+1.0 and \
                   p_sh.bounds[1]-1.0 <= prov_bounds[3] and prov_bounds[1] <= p_sh.bounds[3]+1.0:
                    
                    try:
                        # Check if intersects or is extremely close to the border (distance < 0.1 deg)
                        if prov_shape.intersects(p_sh) or prov_shape.distance(p_sh) < 0.1:
                            intersect_count += 1
                            # For non-partition or single polity, one intersection is enough
                            if not is_partition or len(party_shapes) < 2:
                                is_contested = True
                    except Exception:
                        pass
            
            # In partition mode with multiple baseline polities, it must touch at least 2 polities to be contested
            if is_partition and len(party_shapes) >= 2:
                if intersect_count >= 2:
                    is_contested = True
            
            # Further restrict by disputed areas dataset in partition mode
            if is_contested and is_partition and disputed_geoms:
                intersects_disputed = False
                for d_sh in disputed_geoms:
                    try:
                        if prov_shape.intersects(d_sh):
                            intersects_disputed = True
                            break
                    except Exception:
                        pass
                if not intersects_disputed:
                    is_contested = False
                    
            if is_contested:
                pname = props.get("name")
                if pname and admin:
                    contested.add(f"{pname} ({admin})")
        except Exception:
            pass
            
    return sorted(list(contested))


def _load_prompt_template(filename: str) -> str:
    """Load a prompt template from the backend/prompts folder."""
    try:
        path = os.path.join(os.path.dirname(__file__), "prompts", filename)
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[WARN] Failed to load prompt template '{filename}': {e}. Using hardcoded fallback.", flush=True)
        return ""


# ─── Pipeline Implementations ────────────────────────────────────────────────

def simulate_start(scenario: str) -> Dict[str, Any]:
    """Start the simulation pipeline. Extracts context and executes directly."""
    print(f"[SIMULATOR] Starting scenario: {scenario}")
    
    # 1. Run Guardrail and Refinement
    guardrail = refine_user_prompt(scenario)
    refined_scenario = guardrail.get("refined_prompt", scenario)
    print(f"[SIMULATOR] Guardrail Refinement: original='{scenario}' -> refined='{refined_scenario}'", flush=True)
    if guardrail.get("corrections_made") and guardrail.get("corrections_made") != "None":
        print(f"[SIMULATOR] Corrections made by guardrail: {guardrail.get('corrections_made')}", flush=True)
        
    # 2. Run Geopolitical Planner using decoupled planning.txt template
    template = _load_prompt_template("planning.txt")
    if template:
        prompt = template.format(scenario=refined_scenario)
    else:
        prompt = f"""You are a geopolitical alternate history planner. 
Extract planning parameters from this simulation prompt:
"{refined_scenario}"

Choose the simulation_mode based on keywords:
- If it has treaty, formula, partition, agreement, division, accord, compromise -> 'proposal_partition'
- If it has population, percentage, demographic, majority, minority -> 'demographic_shift'
- Default to 'expansion_conquest'"""
    
    messages = [SystemMessage(content=prompt)]
    plan: PlanningResult = _invoke_structured_with_fallback(PlanningResult, messages, temperature=0.2)
    
    # Programmatic override of simulation mode based on strict keyword matching
    scenario_lower = refined_scenario.lower()
    has_partition = any(kw in scenario_lower for kw in ["treaty", "formula", "partition", "agreement", "division", "accord", "compromise"])
    has_demo = any(kw in scenario_lower for kw in ["population", "percentage", "demographic", "majority", "minority"])
    
    # Check for compounding conquest (multiple years or multiple target conflicts in ancient contexts)
    import re
    years = [int(y) for y in re.findall(r'\b\d{3,4}\b', refined_scenario)]
    plausible_years = [y for y in years if 500 <= y <= 2000]
    has_multiple_dates = len(set(plausible_years)) >= 2
    has_multiple_events = "constantinople" in scenario_lower and ("tours" in scenario_lower or "poitiers" in scenario_lower)
    
    is_compounding = (has_multiple_dates or has_multiple_events) and not has_partition and not has_demo
    
    if is_compounding:
        plan.simulation_mode = "compounding_conquest"
    elif not has_partition and not has_demo:
        plan.simulation_mode = "expansion_conquest"
    elif has_demo and not has_partition:
        plan.simulation_mode = "demographic_shift"
        
    session_id = str(uuid.uuid4())
    context = {
        "session_id": session_id,
        "scenario": refined_scenario,
        "year": plan.year,
        "parties": plan.parties,
        "baseline_polities": plan.baseline_polities,
        "simulation_mode": plan.simulation_mode,
        "target_region": plan.target_region,
        "target_countries": plan.target_countries,
        "baseline_description": plan.baseline_description
    }
    
    if plan.simulation_mode == "compounding_conquest":
        # Call LLM to split the scenario into two sequential steps
        split_prompt = f"""You are a chronological timeline planner.
The user wants to simulate a compound counterfactual scenario involving multiple sequential events:
"{refined_scenario}"

Please split this scenario into two distinct chronological steps:
1. scenario_1: A counterfactual prompt focusing solely on the first historical conflict/event (e.g. Siege of Constantinople in 717-718 AD).
2. year_1: The year of this first conflict.
3. scenario_2: A counterfactual prompt focusing solely on the second historical conflict/event (e.g. Battle of Tours in 732 AD).
4. year_2: The year of this second conflict.

Ensure both years are realistic and match the historical conflicts."""
        
        split_plan: SequentialScenarioPlan = _invoke_structured_with_fallback(
            SequentialScenarioPlan,
            [SystemMessage(content=split_prompt)],
            temperature=0.2
        )
        print(f"[SIMULATOR] Compounding scenario plan generated: Stage 1 = '{split_plan.scenario_1}' in {split_plan.year_1}, Stage 2 = '{split_plan.scenario_2}' in {split_plan.year_2}", flush=True)
        context["compounding_plan"] = split_plan.model_dump()
        # Override the base context year to year_1 initially
        context["year"] = split_plan.year_1
        
    _sessions[session_id] = context
        
    # Proceed directly to final simulation if no questions
    res = _run_final_simulation(context, answers=None)
    res["session_id"] = session_id
    # Append the guardrail logs to the results so the frontend can display them to the user
    res["guardrail_logs"] = {
        "original_prompt": scenario,
        "refined_prompt": refined_scenario,
        "corrections_made": guardrail.get("corrections_made", "None")
    }
    return res


def simulate_verify(session_id: str, selections: Dict[str, str]) -> Dict[str, Any]:
    """Apply the user's validation selections (Option 1: additions or Option 2: subtractions) to territories and finalize."""
    context = _sessions.get(session_id)
    if not context:
        raise ValueError("Invalid or expired session ID.")
        
    pending_real = context.get("pending_real_result")
    pending_opt = context.get("pending_opt_result")
    anomalies = context.get("anomalies", [])
    
    if not pending_real or not pending_opt:
        raise ValueError("No pending validation states found for this session.")
        
    # Reconstruct ScenarioStateResult objects from dicts
    res_real = ScenarioStateResult(**pending_real)
    res_opt = ScenarioStateResult(**pending_opt)
    
    baseline_pols = context.get("baseline_polities", [])
    winner_polity_name = baseline_pols[0] if baseline_pols else "Conqueror"
    
    # Process each user selection
    for anomaly in anomalies:
        anomaly_id = anomaly.get("id")
        choice = selections.get(anomaly_id) # 'option_1' or 'option_2'
        if not choice:
            continue
            
        opt_data = anomaly.get(choice)
        if not opt_data:
            continue
            
        action = opt_data.get("action") # 'addition' or 'subtraction'
        countries_abs = opt_data.get("countries_absorbed", [])
        partial_countries_list = opt_data.get("partial_countries", [])
        scenario_type = anomaly.get("scenario_type") # 'realistic' or 'optimistic'
        
        # Determine target state
        target_res = res_real if scenario_type == "realistic" else res_opt
        
        # Find conqueror's territory change
        winner_t = None
        for t in target_res.territories:
            if winner_polity_name.lower() in t.name.lower() or t.name.lower() in winner_polity_name.lower():
                winner_t = t
                break
        else:
            if target_res.territories:
                winner_t = target_res.territories[0]
                
        if not winner_t:
            continue
            
        if action == "addition":
            for country in countries_abs:
                if country not in winner_t.countries_absorbed:
                    winner_t.countries_absorbed.append(country)
                # Remove from partials if present to maintain mutual exclusivity
                winner_t.partial_countries = [p for p in winner_t.partial_countries if p.country.lower() != country.lower()]
            for part in partial_countries_list:
                part_reg = PartialRegion(**part) if isinstance(part, dict) else part
                # Check if country already exists in winner's partial list
                existing = None
                for p in winner_t.partial_countries:
                    if p.country == part_reg.country:
                        existing = p
                        break
                if existing:
                    for prov in part_reg.provinces:
                        if prov not in existing.provinces:
                            existing.provinces.append(prov)
                else:
                    winner_t.partial_countries.append(part_reg)
                    
        elif action == "subtraction":
            for country in countries_abs:
                if country in winner_t.countries_absorbed:
                    winner_t.countries_absorbed.remove(country)
            for part in partial_countries_list:
                part_reg = PartialRegion(**part) if isinstance(part, dict) else part
                # Find matching country in winner's list
                existing = None
                for p in winner_t.partial_countries:
                    if p.country == part_reg.country:
                        existing = p
                        break
                if existing:
                    if not part_reg.provinces:
                        # Remove entire country entry if no specific provinces list is provided
                        winner_t.partial_countries.remove(existing)
                    else:
                        for prov in part_reg.provinces:
                            if prov in existing.provinces:
                                existing.provinces.remove(prov)
                        if not existing.provinces:
                            winner_t.partial_countries.remove(existing)
                            
    # Finalize the subtractive borders and compile the GeoJSON geometries
    print("[SIMULATOR] Finalizing validation borders after user selections...", flush=True)
    year = context["year"]
    if "compounding_plan" in context:
        year = context["compounding_plan"].get("year_2", year)
    
    # Apply realistic compounded baseline from Stage 1
    if "compounding_baselines_real" in context:
        context["stage2_baselines"] = context["compounding_baselines_real"]
    realistic_features = _process_territory_definitions(res_real.territories, year, context)
    
    # Apply optimistic compounded baseline from Stage 1
    if "compounding_baselines_opt" in context:
        context["stage2_baselines"] = context["compounding_baselines_opt"]
    optimistic_features = _process_territory_definitions(res_opt.territories, year, context)
    
    # Clear baseline override to keep session context clean
    context.pop("stage2_baselines", None)
    
    # Retrieve the pre-compiled results from when the simulation paused for validation
    results = context.get("results")
    if not results:
        # Fallback to fresh dictionary if not found
        results = {}
        
    results["geojson_after_realistic"] = {
        "type": "FeatureCollection",
        "features": realistic_features
    }
    results["geojson_after_optimistic"] = {
        "type": "FeatureCollection",
        "features": optimistic_features
    }
    
    return {
        "status": "completed",
        "session_id": session_id,
        "result": results
    }


def simulate_step(session_id: str, message: str) -> Dict[str, Any]:
    """Apply post-simulation refinement instruction and re-run the simulation."""
    context = _sessions.get(session_id)
    if not context:
        raise ValueError("Invalid or expired session ID.")
        
    # Append the refinement feedback guidance directly to the scenario
    context["scenario"] = f"{context['scenario']} (Instruction: {message})"
    
    # Re-run simulation with updated instruction
    res = _run_final_simulation(context, answers=None)
    res["session_id"] = session_id
    
    # Save updated context back
    _sessions[session_id] = context
    return res


def _run_conquest_sim(
    scenario_val: str,
    year_val: int,
    context_val: dict,
    stage_num: int = 1,
    baselines_override_real: dict = None,
    baselines_override_opt: dict = None,
    answers: Optional[Dict[str, str]] = None
):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    
    baseline_polities = context_val.get("baseline_polities", [])
    target_countries = context_val.get("target_countries", [])
    
    restricted_countries = target_countries if target_countries else [
        "France", "Spain", "Italy", "Switzerland", "Germany", "Greece", "Bulgaria", "Turkey",
        "Belgium", "Netherlands", "Luxembourg", "Austria", "Andorra", "Portugal", "Morocco",
        "Slovenia", "Poland", "Czechia", "Denmark", "Middle East", "Albania", "North Macedonia",
        "Syria", "Iraq", "Iran", "Armenia", "Georgia", "Azerbaijan"
    ]
    
    loader = CountryPolygonLoader()
    print(f"[SIMULATOR] (Stage {stage_num}) Locating contested provinces for baseline polities {baseline_polities} in {year_val} AD...", flush=True)
    
    contested_provinces = find_contested_provinces(baseline_polities, year_val, target_countries, is_partition=False)
    
    # Calculate baseline province ownership
    print(f"[SIMULATOR] (Stage {stage_num}) Analyzing baseline territorial ownership...", flush=True)
    baseline_ownership = {polity: [] for polity in baseline_polities}
    polity_shapes = {}
    for polity in baseline_polities:
        if stage_num == 2 and baselines_override_real and polity in baselines_override_real:
            polity_shapes[polity] = baselines_override_real[polity]
        else:
            feat = cliopatria_db.get_polity_geometry(polity, year_val)
            if feat and feat.get("geometry"):
                try:
                    polity_shapes[polity] = shape(feat["geometry"])
                except Exception:
                    pass
                    
    for prov_name in contested_provinces:
        for f in loader.provinces_data:
            props = f.get("properties", {})
            pname = props.get("name")
            admin = props.get("admin")
            if f"{pname} ({admin})" == prov_name:
                geom_dict = f.get("geometry")
                if geom_dict:
                    try:
                        prov_sh = shape(geom_dict)
                        for polity, p_geom in polity_shapes.items():
                            is_owner = False
                            try:
                                intersection_area = prov_sh.intersection(p_geom).area
                                if intersection_area > 0.5 * prov_sh.area:
                                    is_owner = True
                            except Exception:
                                if prov_sh.centroid.within(p_geom):
                                    is_owner = True
                            if is_owner:
                                baseline_ownership[polity].append(prov_name)
                    except Exception:
                        pass
                break
                
    is_ancient_conquest = (year_val < 1800)
    
    if is_ancient_conquest:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            countries_controlled = sorted(list(set(prov.split('(')[-1].replace(')', '').strip() for prov in provs)))
            ownership_str += f"- {polity} currently controls territory within the following modern countries: {', '.join(countries_controlled) if countries_controlled else 'None'}\n"
        
        prompt_contested = f"Contested provinces are located within the following modern countries: {', '.join(sorted(target_countries) if target_countries else sorted(restricted_countries))}. Since this is an ancient/medieval scenario (< 1800 AD), do NOT attempt to annex modern administrative provinces individually. Instead, define your conquests using whole countries, or use the natural boundary vector clipping system (e.g. Loire River, Pyrenees, Alps, Rhine River) with empty provinces array '[]' to draw smooth natural borders. The only exception is capturing a famous capital city, in which case you can annex its modern province (e.g. 'Istanbul (Turkey)' for Constantinople)."
    else:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            if len(provs) > 15:
                ownership_str += f"- {polity} currently controls {len(provs)} provinces including: {', '.join(provs[:15])} ... [and {len(provs) - 15} more]\n"
            else:
                ownership_str += f"- {polity} currently controls: {', '.join(provs) if provs else 'None'}\n"
        prompt_contested = contested_provinces
        if isinstance(prompt_contested, list) and len(prompt_contested) > 30:
            prompt_contested = prompt_contested[:30] + [f"... [and {len(prompt_contested) - 30} more contested provinces across target countries]"]
            
    prompt_vars = {
        "scenario": scenario_val,
        "year": year_val,
        "parties": context_val.get("parties", []),
        "ownership_str": ownership_str,
        "contested_provinces": prompt_contested,
        "answers_str": "",
        "demographics_context": ""
    }
    
    scenario_lower = scenario_val.lower()
    targets = []
    if "constantinople" in scenario_lower:
        targets.append("- The siege of Constantinople was won. Therefore, you MUST annex 'Istanbul (Turkey)' to the Umayyad Caliphate. For the OPTIMISTIC scenario, you MUST fully annex Turkey by adding 'Turkey' to 'countries_absorbed'. For the REALISTIC scenario, only annex the European Turkey / Marmara provinces (such as 'Istanbul', 'Edirne', 'Kırklareli', 'Tekirdağ', 'Çanakkale', 'Kocaeli', 'Bursa') and do NOT add Turkey to 'partial_countries' with Bosphorus clipping.")
    if "tours" in scenario_lower or "poitiers" in scenario_lower:
        targets.append("- The Battle of Tours was won. Therefore, you MUST annex key French provinces (such as 'Vienne (France)', 'Indre (France)', 'Indre-et-Loire (France)', 'Haute-Vienne (France)', 'Deux-Sèvres (France)') to the Umayyad Caliphate. You MUST also annex all of Southern France up to the Loire: add a partial_country for France, setting 'clip_method: natural_boundary', 'clip_description: Loire River', and 'clip_direction: south_of_natural_boundary'.")
        
    target_instructions = ""
    if targets:
        target_instructions = "\nCRITICAL TARGET INSTRUCTIONS (REQUIRED CONQUESTS):\n" + "\n".join(targets)
        
    if year_val < 1800:
        target_instructions += (
            "\nCRITICAL ANCIENT CIVILIZATION GEOGRAPHY RULES (< 1800 AD):\n"
            "- Since this simulation is in the year {year} (ancient/medieval era), modern sub-national province boundaries (like 'Vienne' or 'Aude') are historically irrelevant. "
            "Do NOT list modern administrative province names in the 'provinces' field for PartialRegion.\n"
            "- Instead, use 'clip_method: natural_boundary' and define the natural boundary in 'clip_description' "
            "(e.g., 'Loire River', 'Pyrenees', 'Alps', 'Rhine River', 'Bosphorus') to partition the country cleanly. "
            "Leave the 'provinces' array empty '[]' when using natural boundaries. The engine will automatically "
            "clip the entire country along the river/mountain range in that direction.\n"
            "- GEOGRAPHIC CONTIGUITY & NO LEAPFROGGING: All conquests MUST form a single, contiguous block extending directly from the baseline empire's borders. "
            "Do NOT leapfrog over unconquered land (for example, do NOT annex Bulgaria or Romania unless you also annex Greece, Thrace, and Constantinople, "
            "as they lie in between). Avoid isolated enclaves or disconnected territory.\n"
            "- If a specific key city was captured (like Constantinople or Tours), you may list its containing modern "
            "province (e.g., 'Istanbul (Turkey)' for Constantinople) in the 'provinces' list to represent that city."
        )
        
    if stage_num == 2 and baselines_override_real:
        stage1_real = context_val.get("stage1_real_conquests_str", "")
        target_instructions += (
            f"\nCRITICAL STAGE 2 MOMENTUM INSTRUCTIONS:\n"
            f"- You achieved a major victory in the previous Stage 1 conflict (Constantinople). You start this stage with that expanded territory. "
            f"Your military morale, resources, and power are extremely high. "
            f"Your conquests in this stage MUST reflect this increased power and momentum. Be ambitious and push borders significantly!\n"
            f"CRITICAL COMPLEMENTARY LOSS INSTRUCTIONS FOR DEFEATED PARTIES:\n"
            f"- In Stage 1, the following territories were conquered from their original owners:\n{stage1_real}"
            f"- Defeated parties (like Byzantine Empire) have LOST these territories. In your JSON response, you MUST "
            f"reduce the territories of these defeated parties accordingly. Do NOT let the Byzantine Empire claim or "
            f"absorb Turkey, Constantinople, or Greece, as those are now owned by the Umayyad Caliphate!"
        )
        
    realistic_answers_str = ""
    optimistic_answers_str = ""
    if answers and "clarifying_questions" in context_val:
        questions = context_val["clarifying_questions"]
        real_parts = []
        opt_parts = []
        for q_id, ans in answers.items():
            matching_q = None
            for q in questions:
                if q.get("id") == q_id:
                    matching_q = q
                    break
            if matching_q:
                type_ = matching_q.get("scenario_type")
                question_text = matching_q.get("question")
                if type_ == "realistic":
                    real_parts.append(f"{question_text} Selected Choice: {ans}")
                elif type_ == "optimistic":
                    opt_parts.append(f"{question_text} Selected Choice: {ans}")
        if real_parts:
            realistic_answers_str = "\nCRITICAL USER OUTCOME CHOICES FOR REALISTIC SCENARIO:\n" + "\n".join(f"- {p}" for p in real_parts)
        if opt_parts:
            optimistic_answers_str = "\nCRITICAL USER OUTCOME CHOICES FOR OPTIMISTIC SCENARIO:\n" + "\n".join(f"- {p}" for p in opt_parts)

    template_real = _load_prompt_template("expansion_conquest.txt")
    if template_real:
        target_instr_real = target_instructions.format(year=year_val)
        if realistic_answers_str:
            target_instr_real += f"\n{realistic_answers_str}\nYou MUST simulate the realistic scenario strictly respecting the user choices listed above. If the choice is a specific boundary or none, adjust the territories to match exactly."
        prompt_vars["target_instructions"] = target_instr_real
        prompt_vars["real_conquests_context"] = ""
        prompt_vars["conquest_type"] = "REALISTIC military simulation: Annex only logically contiguous, nearby border provinces that are physically close to the baseline territory and easily defensible. Do NOT let the empire expand excessively."
        
        if stage_num == 2 and baselines_override_real:
            prompt_vars["real_conquests_context"] = (
                "\nSTAGE 1 REALISTIC VICTORY ACHIEVED AND INCORPORATED:\n"
                "- The Stage 1 conflict was successfully won, expanding your starting territory. "
                "You must build on top of these expanded borders."
            )
            
        real_prompt = template_real.format(**prompt_vars)
    else:
        real_prompt = f"Simulate military conquest: {scenario_val}. contested: {contested_provinces}"
        
    res_real: ScenarioStateResult = _invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=real_prompt)], temperature=0.7)
    force_conquest_provinces(res_real.territories, scenario_val)
    
    real_conquests_str = ""
    for t in res_real.territories:
        conquest_parts = []
        for p in t.partial_countries:
            if p.clip_method == "natural_boundary" and p.clip_description:
                conquest_parts.append(f"{p.country} ({p.clip_direction} of {p.clip_description})")
            elif p.clip_method in ["coordinate_latitude", "coordinate_longitude"] and p.clip_description:
                conquest_parts.append(f"{p.country} ({p.clip_description})")
            elif p.provinces:
                conquest_parts.append(f"{p.country} (provinces: {', '.join(p.provinces)})")
        if t.countries_absorbed:
            conquest_parts.append(f"Fully absorbed countries: {', '.join(t.countries_absorbed)}")
        if conquest_parts:
            real_conquests_str += f"- {t.name} conquered: " + "; ".join(conquest_parts) + "\n"
            
    if template_real:
        target_instr_opt = target_instructions.format(year=year_val)
        if optimistic_answers_str:
            target_instr_opt += f"\n{optimistic_answers_str}\nYou MUST simulate the optimistic scenario strictly respecting the user choices listed above. If the choice is a specific boundary or region, adjust the territories to match exactly."
        prompt_vars["target_instructions"] = target_instr_opt
        
        if stage_num == 2 and baselines_override_opt:
            stage1_opt = context_val.get("stage1_opt_conquests_str", "")
            prompt_vars["real_conquests_context"] = (
                "\nSTAGE 1 OPTIMISTIC VICTORY ACHIEVED AND INCORPORATED:\n"
                "- The Stage 1 conflict was won under best-case scenarios. You start Stage 2 with these fully expanded borders.\n"
                f"REALISTIC STAGE 2 BASELINE (YOU MUST EXPAND BEYOND THESE IN THIS OPTIMISTIC RUN):\n{real_conquests_str}"
            )
            # Add loss instructions to target_instructions for Stage 2 Optimistic
            prompt_vars["target_instructions"] += (
                f"\nCRITICAL COMPLEMENTARY LOSS INSTRUCTIONS FOR DEFEATED PARTIES:\n"
                f"- In Stage 1, the following territories were conquered from their original owners:\n{stage1_opt}"
                f"- Defeated parties (like Byzantine Empire) have LOST these territories. In your JSON response, you MUST "
                f"reduce the territories of these defeated parties accordingly. Do NOT let the Byzantine Empire claim or "
                f"absorb Turkey, Constantinople, or Greece, as those are now owned by the Umayyad Caliphate!"
            )
        else:
            prompt_vars["real_conquests_context"] = (
                f"\nREALISTIC CONQUESTS ACHIEVED IN THIS EVENT:\n{real_conquests_str}"
                "\nCRITICAL OPTIMISTIC EXPANSION REQUIREMENT:\n"
                "- You MUST NOT return the same boundaries as the realistic scenario. "
                "Replace realistic boundaries with wider/larger boundaries (e.g. if the realistic boundary was the Loire River, "
                "replace it with the Rhine River using 'clip_description: Rhine River', 'clip_direction: west_of_natural_boundary')."
            )
            
        if stage_num == 2:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC compounding simulation: This is a BEST-CASE scenario with maximum compounding power and moral from winning both wars. "
                "You MUST expand significantly beyond the realistic conquests. Since they won Tours with Constantinople already secured, "
                "they should conquer most of Western Europe up to the Rhine River. Because the Rhine River runs through multiple countries, "
                "you MUST add partial_country definitions for France, Germany, Netherlands, and Switzerland (all setting 'clip_method: natural_boundary', "
                "'clip_description: Rhine River', 'clip_direction: west_of_natural_boundary') and fully absorb Belgium by adding 'Belgium' to 'countries_absorbed'. "
                "You must also expand deeply into the Balkans (fully annexing Greece and Bulgaria, or setting 'clip_description: Danube River' for Bulgaria)."
            )
        else:
            prompt_vars["conquest_type"] = (
                "OPTIMISTIC military simulation: This is a BEST-CASE scenario representing maximum plausible expansion. "
                "You MUST expand significantly beyond the realistic conquests. Be highly ambitious, think beyond the baseline, "
                "do NOT return the same boundaries, and replace realistic boundaries with wider ones."
            )
            
        opt_prompt = template_real.format(**prompt_vars)
    else:
        opt_prompt = real_prompt
        
    res_opt: ScenarioStateResult = _invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=opt_prompt)], temperature=0.7)
    force_conquest_provinces(res_opt.territories, scenario_val)
    
    # Run the Geopolitical Validation AI Node to enforce contiguity and exclusivity
    # Skip running validation during Stage 1 of compounding conquest (run it only at Stage 2 for final outcomes)
    is_compounding = ("compounding_plan" in context_val or "scenario_2" in context_val)
    if not is_compounding or stage_num == 2:
        res_real = _run_geopolitical_validation(res_real, scenario_val, year_val, context_val)
        res_opt = _run_geopolitical_validation(res_opt, scenario_val, year_val, context_val)
    
    if baselines_override_real:
        context_val["stage2_baselines"] = baselines_override_real
    else:
        context_val.pop("stage2_baselines", None)
    
    if "compounding_resolved_geoms_real" in context_val:
        context_val["compounding_resolved_geoms"] = context_val["compounding_resolved_geoms_real"]
    realistic_features = _process_territory_definitions(res_real.territories, year_val, context_val)
    
    if baselines_override_opt:
        context_val["stage2_baselines"] = baselines_override_opt
    else:
        context_val.pop("stage2_baselines", None)
        
    if "compounding_resolved_geoms_opt" in context_val:
        context_val["compounding_resolved_geoms"] = context_val["compounding_resolved_geoms_opt"]
    optimistic_features = _process_territory_definitions(res_opt.territories, year_val, context_val)
    
    context_val.pop("stage2_baselines", None)
    
    return res_real, res_opt, realistic_features, optimistic_features


def _run_final_simulation(context: Dict[str, Any], answers: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Execute loader, spatial processor, specialized simulation nodes, and compiler."""
    year = context["year"]
    parties = context["parties"]
    mode = context["simulation_mode"]
    scenario = context["scenario"]
    
    # Expand target countries list automatically if natural boundaries are detected in scenario text
    scenario_lower = scenario.lower()
    expanded_countries = list(context.get("target_countries", []))
    for kw, b_countries in BOUNDARY_COUNTRIES_MAP.items():
        if kw in scenario_lower:
            for c in b_countries:
                if c not in expanded_countries:
                    expanded_countries.append(c)
                    
    # For ancient timelines (year < 1800), automatically expand target countries regionally
    # to allow the LLM to expand into adjacent countries and use natural boundaries.
    if year < 1800:
        regional_expansions = {
            "france": ["Germany", "Italy", "Switzerland", "Belgium", "Netherlands", "Luxembourg", "Austria", "Andorra", "Spain"],
            "spain": ["France", "Portugal", "Andorra", "Morocco"],
            "germany": ["France", "Poland", "Czechia", "Austria", "Switzerland", "Denmark", "Netherlands", "Belgium", "Middle East"],
            "turkey": ["Greece", "Bulgaria", "Syria", "Iraq", "Iran", "Armenia", "Georgia", "Azerbaijan"],
            "greece": ["Turkey", "Bulgaria", "Albania", "North Macedonia"],
            "italy": ["France", "Switzerland", "Austria", "Slovenia"],
            "india": ["Pakistan", "Bangladesh", "Nepal", "Bhutan", "Myanmar", "China"],
            "pakistan": ["India", "Afghanistan", "Iran", "China"]
        }
        for country in list(expanded_countries):
            country_lower = country.lower()
            if country_lower in regional_expansions:
                for adj in regional_expansions[country_lower]:
                    if adj not in expanded_countries:
                        expanded_countries.append(adj)
                        
    context["target_countries"] = expanded_countries
    
    # 1. Run dynamic GIS and demographic tools based on scenario
    demographics_context = ""
    gis_context = ""
    boundary_geom_data = None
    
    region = context.get("target_region", "")
    countries = context.get("target_countries", [])
    
    # Demographic tool lookup
    if mode == "demographic_shift" or any(k in scenario.lower() for k in ["demographic", "population", "muslim", "percent", "60%"]):
        print(f"[SIMULATOR] Launching agentic Wikipedia demographics lookup...", flush=True)
        res_dem = wikipedia_demographics_tool(scenario, region, countries)
        if res_dem.get("status") == "success":
            facts_text = "\n".join(f"- {f['province']}: {f['group']} {f['percentage']}%" for f in res_dem["facts"])
            demographics_context = f"\n--- VERIFIED HISTORICAL DEMOGRAPHICS (WIKIPEDIA) ---\n{facts_text}\nSummary: {res_dem['summary']}\n"
            print(f"[SIMULATOR] Successfully verified & extracted demographics from Wikipedia.", flush=True)
        else:
            print(f"[SIMULATOR] Demographics lookup status: {res_dem.get('message')}", flush=True)
            
    # Determine all relevant natural boundaries based on countries and scenario text
    detected_boundaries = []
    countries_lower = [c.lower() for c in countries]
    
    if "france" in countries_lower:
        detected_boundaries.extend(["Loire River", "Pyrenees"])
    if "spain" in countries_lower:
        detected_boundaries.append("Pyrenees")
    if "turkey" in countries_lower:
        detected_boundaries.append("Bosphorus")
    if "india" in countries_lower or "pakistan" in countries_lower:
        detected_boundaries.append("Chenab River")
        
    for kw in ["chenab", "loire", "pyrenees", "pyrénées", "rhone", "rhône", "rhine", "danube", "alps"]:
        if kw in scenario.lower():
            if kw == "chenab" and "Chenab River" not in detected_boundaries:
                detected_boundaries.append("Chenab River")
            elif (kw == "rhone" or kw == "rhône") and "Rhone River" not in detected_boundaries:
                detected_boundaries.append("Rhone River")
            elif kw == "loire" and "Loire River" not in detected_boundaries:
                detected_boundaries.append("Loire River")
            elif (kw == "pyrenees" or kw == "pyrénées") and "Pyrenees" not in detected_boundaries:
                detected_boundaries.append("Pyrenees")
            elif kw == "rhine" and "Rhine River" not in detected_boundaries:
                detected_boundaries.append("Rhine River")
            elif kw == "danube" and "Danube River" not in detected_boundaries:
                detected_boundaries.append("Danube River")
            elif kw == "alps" and "Alps" not in detected_boundaries:
                detected_boundaries.append("Alps")

    context["osm_boundaries"] = {}
    for boundary_name in list(set(detected_boundaries)):
        print(f"[SIMULATOR] Retrieving OSM geometry for natural boundary: '{boundary_name}'...", flush=True)
        res_osm = natural_boundary_tool(boundary_name)
        if res_osm.get("status") == "success":
            context["osm_boundaries"][boundary_name] = res_osm["paths"]
            context["osm_boundary_geometry"] = res_osm["paths"]
            context["osm_boundary_name"] = boundary_name
            gis_context += f"\n- Natural boundary '{boundary_name}' found. The compiler can split shared provinces along this boundary.\n"
            print(f"[SIMULATOR] Successfully loaded OSM boundary path for '{boundary_name}'.", flush=True)
        else:
            print(f"[SIMULATOR] OSM boundary retrieval failed for '{boundary_name}': {res_osm.get('message')}", flush=True)
            
    # Landmark geocoding lookup (e.g. "Louvre")
    landmark_keywords = ["louvre", "khyber", "capital", "city"]
    detected_landmark_name = None
    for kw in landmark_keywords:
        if kw in scenario.lower():
            if "louvre" in scenario.lower():
                detected_landmark_name = "Louvre"
            elif "khyber" in scenario.lower():
                detected_landmark_name = "Khyber Pass"
            break
            
    if detected_landmark_name:
        print(f"[SIMULATOR] Geopolitical context references landmark: '{detected_landmark_name}'. Geocoding coordinates...", flush=True)
        res_geo = geocode_landmark_tool(detected_landmark_name)
        if res_geo.get("status") == "success":
            lat = res_geo["latitude"]
            lon = res_geo["longitude"]
            gis_context += f"\n- Resolved landmark '{detected_landmark_name}' to coordinates: Latitude {lat}, Longitude {lon}. The compiler will split shared provinces relative to this landmark.\n"
            print(f"[SIMULATOR] Geocoded landmark '{detected_landmark_name}' successfully to ({lat}, {lon}).", flush=True)
            context["geocoded_landmark_name"] = detected_landmark_name
            context["geocoded_landmark_coords"] = (lat, lon)
        else:
            print(f"[SIMULATOR] Landmark geocoding failed: {res_geo.get('message')}", flush=True)
                
    # 2. Load Baseline historical map from Cliopatria
    baseline_polities = context.get("baseline_polities", parties)
    
    # In expansion_conquest mode, focus ONLY on the primary expanding polity (e.g. Umayyad Caliphate)
    is_conquest = (mode == "expansion_conquest")
    filtered_baseline = baseline_polities[:1] if (is_conquest and baseline_polities) else baseline_polities
    
    print(f"[SIMULATOR] Compiling baseline map for polities {filtered_baseline} in {year} AD...")
    
    before_features = []
    for polity in filtered_baseline:
        f = cliopatria_db.get_polity_geometry(polity, year)
        if f:
            props = f.get("properties", {})
            clean_geom = {k: v for k, v in f.get("geometry", {}).items() if k not in ("when", "approximation")}
            
            # Determine color coding
            name_lower = polity.lower()
            color = "#4b5563" # default gray
            if "umayyad" in name_lower:
                color = "#10b981" # green
            elif "frank" in name_lower or "caroling" in name_lower:
                color = "#ef4444" # red
            elif "byzant" in name_lower:
                color = "#8b5cf6" # purple
            elif "india" in name_lower:
                color = "#fbbf24" # saffron/yellow
            elif "pakistan" in name_lower:
                color = "#047857" # emerald green
            elif "ottoman" in name_lower:
                color = "#b91c1c" # crimson red
                
            before_features.append({
                "type": "Feature",
                "properties": {
                    "name": props.get("Name") or polity,
                    "from_year": props.get("FromYear"),
                    "to_year": props.get("ToYear"),
                    "color": color,
                    "description": f"Historical baseline territory of {props.get('Name') or polity} around year {year}.",
                    "capital": "Historical Capital",
                    "population": "Historical Estimate"
                },
                "geometry": clean_geom
            })
        
    geojson_before = {
        "type": "FeatureCollection",
        "features": before_features
    }
    
    # 3. Get contested modern provinces using Shapely, filtered to target countries
    baseline_polities = context.get("baseline_polities", parties)
    target_countries = context.get("target_countries", [])
    print(f"[SIMULATOR] Locating contested provinces for baseline polities {baseline_polities} (restricted to {target_countries}) in {year} AD...")
    contested_provinces = find_contested_provinces(baseline_polities, year, target_countries, is_partition=(mode == "proposal_partition"))
    context["contested_provinces"] = contested_provinces
    print(f"[SIMULATOR] Contested provinces count: {len(contested_provinces)}")
    
    # Calculate baseline province ownership for each conflict polity to guide model reasoning
    print("[SIMULATOR] Analyzing baseline territorial ownership of contested provinces...")
    baseline_ownership = {polity: [] for polity in baseline_polities}
    polity_shapes = {}
    for polity in baseline_polities:
        feat = cliopatria_db.get_polity_geometry(polity, year)
        if feat and feat.get("geometry"):
            try:
                polity_shapes[polity] = shape(feat["geometry"])
            except Exception:
                pass
                
    loader = CountryPolygonLoader()
    for prov_name in contested_provinces:
        for f in loader.provinces_data:
            props = f.get("properties", {})
            pname = props.get("name")
            admin = props.get("admin")
            if f"{pname} ({admin})" == prov_name:
                geom_dict = f.get("geometry")
                if geom_dict:
                    try:
                        prov_sh = shape(geom_dict)
                        for polity, p_geom in polity_shapes.items():
                            is_owner = False
                            try:
                                intersection_area = prov_sh.intersection(p_geom).area
                                if intersection_area > 0.5 * prov_sh.area:
                                    is_owner = True
                            except Exception:
                                if prov_sh.centroid.within(p_geom):
                                    is_owner = True
                                    
                            if is_owner:
                                baseline_ownership[polity].append(prov_name)
                    except Exception:
                        pass
                break
                
    is_ancient_conquest = (year < 1800 and mode == "expansion_conquest")
    
    if is_ancient_conquest:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            countries_controlled = sorted(list(set(prov.split('(')[-1].replace(')', '').strip() for prov in provs)))
            ownership_str += f"- {polity} currently controls territory within the following modern countries: {', '.join(countries_controlled) if countries_controlled else 'None'}\n"
        
        prompt_contested = f"Contested provinces are located within the following modern countries: {', '.join(sorted(context.get('target_countries', target_countries)) if context else sorted(target_countries))}. Since this is an ancient/medieval scenario (< 1800 AD), do NOT attempt to annex modern administrative provinces individually. Instead, define your conquests using whole countries, or use the natural boundary vector clipping system (e.g. Loire River, Pyrenees, Alps, Rhine River) with empty provinces array '[]' to draw smooth natural borders. The only exception is capturing a famous capital city, in which case you can annex its modern province (e.g. 'Istanbul (Turkey)' for Constantinople)."
    else:
        ownership_str = "Baseline Territorial Control at the start of the simulation:\n"
        for polity, provs in baseline_ownership.items():
            if len(provs) > 15:
                ownership_str += f"- {polity} currently controls {len(provs)} provinces including: {', '.join(provs[:15])} ... [and {len(provs) - 15} more]\n"
            else:
                ownership_str += f"- {polity} currently controls: {', '.join(provs) if provs else 'None'}\n"
                
        # Truncate contested provinces list in prompt if too long to prevent token limit errors
        prompt_contested = contested_provinces
        if isinstance(prompt_contested, list) and len(prompt_contested) > 30:
            prompt_contested = prompt_contested[:30] + [f"... [and {len(prompt_contested) - 30} more contested provinces across target countries]"]
            
    try:
        print(f"[SIMULATOR] Ownership summary compiled:\n{ownership_str}")
    except UnicodeEncodeError:
        import sys
        enc = sys.stdout.encoding or 'utf-8'
        print(f"[SIMULATOR] Ownership summary compiled:\n{ownership_str}".encode(enc, errors='replace').decode(enc))
 
    # Assemble answers string if present
    answers_str = ""
    if answers:
        answers_str = "\nUser preferences for this scenario:\n" + "\n".join(f"- {q}: {a}" for q, a in answers.items())
        
    results = {}
    
    # Load dynamic prompts template variables
    prompt_vars = {
        "scenario": scenario,
        "year": year,
        "parties": parties,
        "ownership_str": ownership_str,
        "contested_provinces": prompt_contested,
        "answers_str": answers_str,
        "demographics_context": demographics_context + gis_context
    }
    
    if mode == "proposal_partition":
        # Run Treaty Partition Node -> single outcome
        print("[SIMULATOR] Executing Treaty Partition Node...")
        template = _load_prompt_template("treaty_partition.txt")
        if template:
            partition_prompt = template.format(**prompt_vars)
        else:
            # Fallback
            partition_prompt = f"Partition contested provinces: {scenario}. contested list: {contested_provinces}"
            
        messages = [SystemMessage(content=partition_prompt)]
        res: ScenarioStateResult = _invoke_structured_with_fallback(ScenarioStateResult, messages, temperature=0.7)
        
        results["title"] = res.title
        results["alternate_outcome"] = res.alternate_outcome
        results["key_changes"] = res.key_changes
        results["realistic_scenario_summary"] = "The accepted partition agreement is fully implemented."
        results["optimistic_scenario_summary"] = "Unified alternate state."
        
        # Save dynamic narrative structures
        results["timeline"] = [t.model_dump() for t in res.timeline]
        results["butterfly_effects"] = res.butterfly_effects
        results["sources"] = res.sources
        
        # Compile realistic map from partition results
        realistic_features = _process_territory_definitions(res.territories, year, context)
        
        # Apply filter if conquest
        if is_conquest and baseline_polities:
            primary_polity = baseline_polities[0].lower()
            realistic_features = [feat for feat in realistic_features if primary_polity in feat["properties"]["name"].lower()]
            
        results["geojson_after_realistic"] = {
            "type": "FeatureCollection",
            "features": realistic_features
        }
        results["geojson_after_optimistic"] = {
            "type": "FeatureCollection",
            "features": realistic_features
        }
        
    elif mode == "demographic_shift":
        # Run Demographic Nodes -> realistic and optimistic
        print("[SIMULATOR] Executing Demographic Nodes...")
        
        template_real = _load_prompt_template("demographic_shift.txt")
        if template_real:
            real_prompt = template_real.format(**prompt_vars)
            opt_prompt = template_real.format(**prompt_vars)
        else:
            # Fallback
            real_prompt = f"Simulate demographic shift: {scenario}. contested: {contested_provinces}"
            opt_prompt = real_prompt
            
        res_real: ScenarioStateResult = _invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=real_prompt)], temperature=0.7)
        res_opt: ScenarioStateResult = _invoke_structured_with_fallback(ScenarioStateResult, [SystemMessage(content=opt_prompt)], temperature=0.7)
        
        results["title"] = res_real.title
        results["alternate_outcome"] = f"Realistic: {res_real.alternate_outcome}\n\nOptimistic: {res_opt.alternate_outcome}"
        results["key_changes"] = list(set(res_real.key_changes + res_opt.key_changes))
        results["realistic_scenario_summary"] = "Realistic partition based on majorities and logistics."
        results["optimistic_scenario_summary"] = "Optimistic/maximum union or state expansion."
        
        # Combine timeline, butterfly effects, and sources
        results["butterfly_effects"] = list(set(res_real.butterfly_effects + res_opt.butterfly_effects))
        results["sources"] = list(set(res_real.sources + res_opt.sources))
        
        seen_t = set()
        combined_timeline = []
        for t in res_real.timeline + res_opt.timeline:
            val = f"{t.year}:{t.event}"
            if val not in seen_t:
                seen_t.add(val)
                combined_timeline.append(t.model_dump())
        results["timeline"] = sorted(combined_timeline, key=lambda x: x["year"])
        
        realistic_features = _process_territory_definitions(res_real.territories, year, context)
        optimistic_features = _process_territory_definitions(res_opt.territories, year, context)
        
        # Apply filter if conquest (removed to allow rendering of all updated polities side-by-side)
        pass
            
        results["geojson_after_realistic"] = {
            "type": "FeatureCollection",
            "features": realistic_features
        }
        results["geojson_after_optimistic"] = {
            "type": "FeatureCollection",
            "features": optimistic_features
        }
        
    elif mode == "compounding_conquest":
        # Run Multi-stage Compounding simulation
        print("[SIMULATOR] Executing Compounding Conquest Sequential Nodes...")
        plan_dict = context.get("compounding_plan")
        if not plan_dict:
            raise ValueError("Compounding plan is missing from context.")
            
        scenario_1 = plan_dict["scenario_1"]
        year_1 = plan_dict["year_1"]
        scenario_2 = plan_dict["scenario_2"]
        year_2 = plan_dict["year_2"]
        
        # --- STAGE 1 (First Event) ---
        print(f"[SIMULATOR] --- STAGE 1: Simulating first event '{scenario_1}' at {year_1} ---", flush=True)
        
        context_1 = dict(context)
        context_1["year"] = year_1
        context_1["scenario"] = scenario_1
        context_1["simulation_mode"] = "expansion_conquest"
        
        # Set collectors to extract Stage 1 geometries
        resolved_real_1 = {}
        resolved_opt_1 = {}
        context_1["compounding_resolved_geoms_real"] = resolved_real_1
        context_1["compounding_resolved_geoms_opt"] = resolved_opt_1
        res_real_1, res_opt_1, realistic_features_1, optimistic_features_1 = _run_conquest_sim(
            scenario_1, year_1, context_1, stage_num=1, answers=answers
        )
        
        # Build Stage 1 conquests summaries to pass to Stage 2
        real_conquests_str_1 = ""
        for t in res_real_1.territories:
            conquest_parts = []
            for p in t.partial_countries:
                if p.clip_method == "natural_boundary" and p.clip_description:
                    conquest_parts.append(f"{p.country} ({p.clip_direction} of {p.clip_description})")
                elif p.clip_method in ["coordinate_latitude", "coordinate_longitude"] and p.clip_description:
                    conquest_parts.append(f"{p.country} ({p.clip_description})")
                elif p.provinces:
                    conquest_parts.append(f"{p.country} (provinces: {', '.join(p.provinces)})")
            if t.countries_absorbed:
                conquest_parts.append(f"Fully absorbed countries: {', '.join(t.countries_absorbed)}")
            if conquest_parts:
                real_conquests_str_1 += f"- {t.name} conquered: " + "; ".join(conquest_parts) + "\n"
                
        opt_conquests_str_1 = ""
        for t in res_opt_1.territories:
            conquest_parts = []
            for p in t.partial_countries:
                if p.clip_method == "natural_boundary" and p.clip_description:
                    conquest_parts.append(f"{p.country} ({p.clip_direction} of {p.clip_description})")
                elif p.clip_method in ["coordinate_latitude", "coordinate_longitude"] and p.clip_description:
                    conquest_parts.append(f"{p.country} ({p.clip_description})")
                elif p.provinces:
                    conquest_parts.append(f"{p.country} (provinces: {', '.join(p.provinces)})")
            if t.countries_absorbed:
                conquest_parts.append(f"Fully absorbed countries: {', '.join(t.countries_absorbed)}")
            if conquest_parts:
                opt_conquests_str_1 += f"- {t.name} conquered: " + "; ".join(conquest_parts) + "\n"
        
        # --- STAGE 2 (Second Event) ---
        print(f"[SIMULATOR] --- STAGE 2: Simulating second event '{scenario_2}' at {year_2} ---", flush=True)
        
        context_2 = dict(context)
        context_2["year"] = year_2
        context_2["scenario"] = scenario_2
        context_2["simulation_mode"] = "expansion_conquest"
        context_2["stage1_real_conquests_str"] = real_conquests_str_1
        context_2["stage1_opt_conquests_str"] = opt_conquests_str_1
        
        # Save baselines overrides in main context for simulate_verify finalization
        context["compounding_baselines_real"] = resolved_real_1
        context["compounding_baselines_opt"] = resolved_opt_1
        
        # Execute Stage 2 with baselines overrides from Stage 1
        res_real_2, res_opt_2, realistic_features_2, optimistic_features_2 = _run_conquest_sim(
            scenario_2, year_2, context_2, stage_num=2,
            baselines_override_real=resolved_real_1,
            baselines_override_opt=resolved_opt_1,
            answers=answers
        )
        
        # Combine narratives and timelines from both stages chronologically
        results["title"] = f"{res_real_1.title} & {res_real_2.title}"
        results["alternate_outcome"] = (
            f"Stage 1 (Constantinople - Realistic): {res_real_1.alternate_outcome}\n"
            f"Stage 2 (Tours - Realistic): {res_real_2.alternate_outcome}\n\n"
            f"Stage 1 (Constantinople - Optimistic): {res_opt_1.alternate_outcome}\n"
            f"Stage 2 (Tours - Optimistic): {res_opt_2.alternate_outcome}"
        )
        results["alternate_outcome_realistic"] = (
            f"Stage 1 (Constantinople): {res_real_1.alternate_outcome}\n\n"
            f"Stage 2 (Tours): {res_real_2.alternate_outcome}"
        )
        results["alternate_outcome_optimistic"] = (
            f"Stage 1 (Constantinople): {res_opt_1.alternate_outcome}\n\n"
            f"Stage 2 (Tours): {res_opt_2.alternate_outcome}"
        )
        results["key_changes"] = list(set(res_real_1.key_changes + res_opt_1.key_changes + res_real_2.key_changes + res_opt_2.key_changes))
        results["realistic_scenario_summary"] = "Compounded realistic sequential outcomes with moral momentum."
        results["optimistic_scenario_summary"] = "Maximum compounded territorial expansion across all theatres."
        
        results["butterfly_effects"] = list(set(res_real_1.butterfly_effects + res_opt_1.butterfly_effects + res_real_2.butterfly_effects + res_opt_2.butterfly_effects))
        results["sources"] = list(set(res_real_1.sources + res_opt_1.sources + res_real_2.sources + res_opt_2.sources))
        
        seen_t = set()
        combined_timeline = []
        for t in res_real_1.timeline + res_opt_1.timeline + res_real_2.timeline + res_opt_2.timeline:
            val = f"{t.year}:{t.event}"
            if val not in seen_t:
                seen_t.add(val)
                combined_timeline.append(t.model_dump())
        results["timeline"] = sorted(combined_timeline, key=lambda x: x["year"])
        
        results["geojson_after_realistic"] = {
            "type": "FeatureCollection",
            "features": realistic_features_2
        }
        results["geojson_after_optimistic"] = {
            "type": "FeatureCollection",
            "features": optimistic_features_2
        }
        
    else:  # expansion_conquest
        print("[SIMULATOR] Executing standard expansion conquest simulation...")
        res_real, res_opt, realistic_features, optimistic_features = _run_conquest_sim(
            scenario, year, context, stage_num=1, answers=answers
        )
        
        results["title"] = res_real.title
        results["alternate_outcome"] = f"Realistic: {res_real.alternate_outcome}\n\nOptimistic: {res_opt.alternate_outcome}"
        results["alternate_outcome_realistic"] = res_real.alternate_outcome
        results["alternate_outcome_optimistic"] = res_opt.alternate_outcome
        results["key_changes"] = list(set(res_real.key_changes + res_opt.key_changes))
        results["realistic_scenario_summary"] = "Plausible conquest limits and client states."
        results["optimistic_scenario_summary"] = "Maximum territorial annexations and tributary states."
        
        results["butterfly_effects"] = list(set(res_real.butterfly_effects + res_opt.butterfly_effects))
        results["sources"] = list(set(res_real.sources + res_opt.sources))
        
        seen_t = set()
        combined_timeline = []
        for t in res_real.timeline + res_opt.timeline:
            val = f"{t.year}:{t.event}"
            if val not in seen_t:
                seen_t.add(val)
                combined_timeline.append(t.model_dump())
        results["timeline"] = sorted(combined_timeline, key=lambda x: x["year"])
        
        results["geojson_after_realistic"] = {
            "type": "FeatureCollection",
            "features": realistic_features
        }
        results["geojson_after_optimistic"] = {
            "type": "FeatureCollection",
            "features": optimistic_features
        }
        
    # Common fields
    results["base_year"] = year
    results["historical_context"] = context["baseline_description"]
    results["what_actually_happened"] = "Real timeline outcome."
    results["geojson_before"] = geojson_before
    results["confidence_score"] = 0.85
    # Merge all loaded natural boundary paths so the Natural Borders view overlays all of them simultaneously
    all_boundary_paths = []
    boundary_names = []
    if "osm_boundaries" in context:
        for name, paths in context["osm_boundaries"].items():
            if paths:
                all_boundary_paths.extend(paths)
                boundary_names.append(name)
                
    results["osm_boundary_geometry"] = all_boundary_paths
    results["osm_boundary_name"] = ", ".join(boundary_names) if boundary_names else "Natural Borders"
    results["map_markers"] = context.get("map_markers", [])
    
    # 4. Check for major geopolitical anomalies (disconnected enclaves/gaps)
    pending_real = None
    pending_opt = None
    if mode == "compounding_conquest":
        if 'res_real_2' in locals() and 'res_opt_2' in locals():
            pending_real = locals()['res_real_2']
            pending_opt = locals()['res_opt_2']
    elif mode in ["expansion_conquest", "demographic_shift"]:
        if 'res_real' in locals() and 'res_opt' in locals():
            pending_real = locals()['res_real']
            pending_opt = locals()['res_opt']
            
    if pending_real and pending_opt:
        has_anomalies, questions_list = _check_geopolitical_anomalies(pending_real, pending_opt, realistic_features, optimistic_features, scenario, year, context)
        if has_anomalies and questions_list:
            # Save state in context for simulate_verify
            context["pending_real_result"] = pending_real.model_dump()
            context["pending_opt_result"] = pending_opt.model_dump()
            context["anomalies"] = questions_list
            context["results"] = results
            _sessions[context["session_id"]] = context
            
            print(f"[SIMULATOR] Pausing simulation for user validation choice on {len(questions_list)} anomalies...", flush=True)
            return {
                "status": "awaiting_verification",
                "session_id": context["session_id"],
                "questions": context["anomalies"],
                "result": results
            }
            
    return {
        "status": "completed",
        "result": results
    }


def clip_province_geom(prov_geom, boundary_geom, direction, val=None, prov_name=None, territory_desc=None):
    from shapely.ops import split, nearest_points
    from shapely.geometry import box
    from shapely.ops import unary_union
    
    minx, miny, maxx, maxy = prov_geom.bounds
    cx, cy = prov_geom.centroid.x, prov_geom.centroid.y
    
    if direction == "north_of_latitude":
        val = val if val is not None else cy
        split_poly = box(minx, val, maxx, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "south_of_latitude":
        val = val if val is not None else cy
        split_poly = box(minx, miny, maxx, val)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "west_of_longitude":
        val = val if val is not None else cx
        split_poly = box(minx, miny, val, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
    elif direction == "east_of_longitude":
        val = val if val is not None else cx
        split_poly = box(val, miny, maxx, maxy)
        res = prov_geom.intersection(split_poly)
        return res if res and not res.is_empty else None
        
    if boundary_geom:
        # Exclude far-away disconnected regions/islands (like Corsica) from mainland boundaries
        # UNLESS they are explicitly mentioned by the LLM in the description
        is_mentioned = False
        if prov_name and territory_desc:
            p_lower = prov_name.lower()
            desc_lower = territory_desc.lower()
            island_keywords = []
            if "corse" in p_lower or "corsica" in p_lower:
                island_keywords = ["corse", "corsica"]
            elif "baleares" in p_lower or "balearic" in p_lower:
                island_keywords = ["baleares", "balearic", "mallorca", "menorca", "ibiza"]
            elif "sardegna" in p_lower or "sardinia" in p_lower:
                island_keywords = ["sardegna", "sardinia"]
            elif "sicilia" in p_lower or "sicily" in p_lower:
                island_keywords = ["sicilia", "sicily"]
                
            for kw in island_keywords:
                if kw in desc_lower:
                    is_mentioned = True
                    break
                    
        if not is_mentioned:
            try:
                if prov_geom.distance(boundary_geom) > 3.0:
                    return None
            except Exception:
                pass
            
        # Check if boundary intersects the province
        if boundary_geom.intersects(prov_geom):
            try:
                split_result = split(prov_geom, boundary_geom)
                if hasattr(split_result, "geoms") and len(split_result.geoms) > 1:
                    keep_polys = []
                    for sub_poly in split_result.geoms:
                        scy = sub_poly.centroid.y
                        scx = sub_poly.centroid.x
                        p1, p2 = nearest_points(sub_poly.centroid, boundary_geom)
                        local_y = p2.y
                        local_x = p2.x
                        
                        if direction in ["north_of_natural_boundary", "north_of_latitude"] and scy > local_y:
                            keep_polys.append(sub_poly)
                        elif direction in ["south_of_natural_boundary", "south_of_latitude"] and scy < local_y:
                            keep_polys.append(sub_poly)
                        elif direction in ["west_of_natural_boundary", "west_of_longitude"] and scx < local_x:
                            keep_polys.append(sub_poly)
                        elif direction in ["east_of_natural_boundary", "east_of_longitude"] and scx > local_x:
                            keep_polys.append(sub_poly)
                            
                    if keep_polys:
                        return unary_union(keep_polys)
            except Exception:
                pass
                
        # If it doesn't intersect or split failed, check if the entire province centroid lies on correct side
        try:
            p1, p2 = nearest_points(prov_geom.centroid, boundary_geom)
            local_y = p2.y
            local_x = p2.x
            scy = prov_geom.centroid.y
            scx = prov_geom.centroid.x
            
            keep = False
            if direction in ["north_of_natural_boundary", "north_of_latitude"] and scy > local_y:
                keep = True
            elif direction in ["south_of_natural_boundary", "south_of_latitude"] and scy < local_y:
                keep = True
            elif direction in ["west_of_natural_boundary", "west_of_longitude"] and scx < local_x:
                keep = True
            elif direction in ["east_of_natural_boundary", "east_of_longitude"] and scx > local_x:
                keep = True
                
            if keep:
                return prov_geom
        except Exception:
            pass
            
    return None


def _process_territory_definitions(territories: List[TerritoryChange], year: int, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Assemble final GeoJSON polygons from LLM territory definitions,
    merging their historical baseline shapes and applying additions/subtractions.
    """
    from shapely.ops import unary_union
    from shapely.geometry import shape, mapping, Polygon, box, LineString, MultiLineString
    
    if context is not None:
        context["map_markers"] = []
        
    loader = CountryPolygonLoader()
    
    # Step 1: Pre-process shared provinces to split their geometries (using exact province name)
    print("[DEBUG] Step 1: Pre-processing shared/partitioned provinces...", flush=True)
    # Only detect shared provinces if we are NOT in expansion_conquest mode!
    mode = context.get("simulation_mode") if context else "expansion_conquest"
    shared_provinces = {}
    if mode != "expansion_conquest":
        for t in territories:
            for p in t.partial_countries:
                for prov in p.provinces:
                    shared_provinces.setdefault(prov, []).append((t.name, p.country, prov))
                
    # Index all split province instructions from the LLM output (using exact province name)
    split_instructions = {}
    for t in territories:
        for p in t.partial_countries:
            for sp in p.split_provinces:
                split_instructions[(t.name, sp.name)] = sp
                
    polity_additions_shapes = {t.name: [] for t in territories}
    assigned_parts = {}
    
    # Identify conqueror / winner in conquest modes
    is_conquest = (mode in ["expansion_conquest", "compounding_conquest"])
    baseline_pols = context.get("baseline_polities", []) if context else []
    winner_polity = baseline_pols[0] if baseline_pols else None
    
    for t in territories:
        print(f"[DEBUG] Processing territory definitions for '{t.name}'...", flush=True)
        
        is_winner = True
        if is_conquest and winner_polity:
            is_winner = (winner_polity.lower() in t.name.lower() or t.name.lower() in winner_polity.lower())
            
        if is_conquest and not is_winner:
            print(f"[DEBUG]   Opponent '{t.name}' detected in conquest mode. Skipping additions and keeping baseline.", flush=True)
            continue
        
        # Dynamically expand partial_countries if a natural boundary crosses multiple countries
        expanded_partials = []
        for p in t.partial_countries:
            expanded_partials.append(p)
            if p.clip_method == "natural_boundary" and p.clip_description:
                b_name_lower = p.clip_description.lower()
                matched_countries = []
                for kw, b_countries in BOUNDARY_COUNTRIES_MAP.items():
                    if kw in b_name_lower:
                        matched_countries = b_countries
                        break
                
                for c in matched_countries:
                    # Exclude if country is already defined in partials or absorbed
                    if c.lower() not in [x.country.lower() for x in t.partial_countries] and c.lower() not in [x.lower() for x in getattr(t, "countries_absorbed", [])]:
                        new_p = PartialRegion(
                            country=c,
                            provinces=[],
                            split_provinces=[],
                            clip_method=p.clip_method,
                            clip_value=p.clip_value,
                            clip_description=p.clip_description,
                            clip_direction=p.clip_direction,
                            landmark_city=None,
                            status=p.status
                        )
                        expanded_partials.append(new_p)
                        print(f"[DEBUG]   Dynamically expanded natural boundary '{p.clip_description}' to include country: '{c}'", flush=True)
        t.partial_countries = expanded_partials
        
        # Load all provinces of fully absorbed countries as additions
        for country_name in getattr(t, "countries_absorbed", []):
            print(f"[DEBUG]   Loading fully absorbed country: '{country_name}'...", flush=True)
            for feat_data in loader.provinces_data:
                props = feat_data.get("properties", {})
                admin_name = props.get("admin", "")
                if admin_name.lower() == country_name.lower():
                    pname = props.get("name")
                    fullname = f"{pname} ({admin_name})"
                    feats = loader.get_province_features(fullname, admin_name)
                    if feats:
                        prov_geom = shape(feats[0]["geometry"])
                        polity_additions_shapes[t.name].append(prov_geom)
                        
        # Prioritize absorbed countries: ignore partial definition if country is fully absorbed
        absorbed_set = {c.lower() for c in getattr(t, "countries_absorbed", [])}
        filtered_partials = [p for p in t.partial_countries if p.country.lower() not in absorbed_set]
        for p in filtered_partials:
            print(f"[DEBUG]   Loading sub-provinces for country: '{p.country}'...", flush=True)
            
            # Check if this region uses natural boundary or coordinate clipping instead of lists
            if p.clip_method in ["natural_boundary", "coordinate_latitude", "coordinate_longitude"] and mode != "proposal_partition":
                print(f"[DEBUG]     Using vector clipping method: {p.clip_method} along {p.clip_description} (direction: {p.clip_direction})", flush=True)
                
                # Fetch all modern provinces for this country
                country_provs = []
                contested_list = context.get("contested_provinces", []) if context else []
                for feat_data in loader.provinces_data:
                    props = feat_data.get("properties", {})
                    admin_name = props.get("admin", "")
                    if admin_name.lower() == p.country.lower():
                        pname = props.get("name")
                        fullname = f"{pname} ({admin_name})"
                        if mode == "proposal_partition" and contested_list:
                            # Only include if this province is part of the contested provinces list
                            if not any(fullname.lower() in cp.lower() or cp.lower() in fullname.lower() for cp in contested_list):
                                continue
                        country_provs.append(fullname)
                        
                # Load boundary geometry if natural_boundary
                boundary_geom = None
                if p.clip_method == "natural_boundary" and context:
                    boundary_name = p.clip_description
                    if "osm_boundaries" not in context:
                        context["osm_boundaries"] = {}
                    if boundary_name not in context["osm_boundaries"]:
                        print(f"[SIMULATOR] Dynamically loading OSM geometry for LLM-suggested natural boundary: '{boundary_name}'...", flush=True)
                        res_osm = natural_boundary_tool(boundary_name)
                        if res_osm.get("status") == "success":
                            context["osm_boundaries"][boundary_name] = res_osm["paths"]
                            print(f"[SIMULATOR] Dynamically loaded paths for boundary '{boundary_name}'.", flush=True)
                        else:
                            print(f"[SIMULATOR] Dynamic OSM boundary retrieval failed: {res_osm.get('message')}", flush=True)
                    osm_geom_data = context["osm_boundaries"].get(boundary_name)
                    if osm_geom_data:
                        try:
                            osm_lines = []
                            for path in osm_geom_data:
                                if len(path) >= 2:
                                    osm_lines.append(LineString(path))
                            boundary_geom = osm_lines[0] if len(osm_lines) == 1 else MultiLineString(osm_lines)
                        except Exception as e:
                            print(f"[DEBUG]       Failed to compile boundary geometry for {boundary_name}: {e}", flush=True)
                
                # Also load any explicitly listed provinces whole (without clipping)
                # to support target forcing (like Istanbul) or specific exceptions
                for prov in p.provinces:
                    if any(sp.name == prov and sp.is_split for sp in p.split_provinces):
                        continue
                    feats = loader.get_province_features(prov, p.country)
                    if feats:
                        prov_geom = shape(feats[0]["geometry"])
                        polity_additions_shapes[t.name].append(prov_geom)
                        assigned_parts.setdefault(prov, []).append(prov_geom)
                
                # Clip each province of this country
                for prov in country_provs:
                    # Skip if we already added it whole (it is in p.provinces and not split)
                    if prov in p.provinces and not any(sp.name == prov and sp.is_split for sp in p.split_provinces):
                        continue
                    feats = loader.get_province_features(prov, p.country)
                    if not feats:
                        continue
                    prov_geom = shape(feats[0]["geometry"])
                    
                    try:
                        clipped_geom = clip_province_geom(prov_geom, boundary_geom, p.clip_direction, p.clip_value, prov_name=prov, territory_desc=t.description)
                        if clipped_geom and not clipped_geom.is_empty:
                            polity_additions_shapes[t.name].append(clipped_geom)
                            assigned_parts.setdefault(prov, []).append(clipped_geom)
                    except Exception as e:
                        print(f"[DEBUG]       Error clipping {prov}: {e}", flush=True)
                continue
                
            all_provs = list(set(p.provinces + [sp.name for sp in p.split_provinces]))
            for prov in all_provs:
                shares = shared_provinces.get(prov, [])
                
                print(f"[DEBUG]     Resolving features for province: '{prov}'...", flush=True)
                feats = loader.get_province_features(prov, p.country)
                if not feats:
                    print(f"[DEBUG]     Province '{prov}' not found in loader index.", flush=True)
                    continue
                prov_geom = shape(feats[0]["geometry"])
                print(f"[DEBUG]     Province '{prov}' successfully loaded. Area: {prov_geom.area:.4f}, Bounds: {prov_geom.bounds}", flush=True)
                
                # Check for explicit split instruction
                inst = split_instructions.get((t.name, prov))
                if inst and inst.is_split:
                    print(f"[DEBUG]     Dynamic split instruction detected for polity '{t.name}', province '{prov}': {inst.split_direction} (value: {inst.split_value})", flush=True)
                    minx, miny, maxx, maxy = prov_geom.bounds
                    cx, cy = prov_geom.centroid.x, prov_geom.centroid.y
                    
                    split_poly = None
                    val = inst.split_value
                    
                    # 1. Try OSM Natural Boundary Split if geometry is present in context
                    osm_geom_data = None
                    boundary_name = None
                    if context and "osm_boundaries" in context:
                        country_lower = p.country.lower()
                        if country_lower == "france":
                            if "pyrenees" in prov.lower() or "pyrénées" in prov.lower():
                                boundary_name = "Pyrenees"
                            else:
                                boundary_name = "Loire River"
                        elif country_lower in ["india", "pakistan"]:
                            boundary_name = "Chenab River"
                        elif country_lower == "turkey":
                            boundary_name = "Bosphorus"
                        
                        if boundary_name:
                            osm_geom_data = context["osm_boundaries"].get(boundary_name)
                            
                    split_done = False
                    if osm_geom_data:
                        try:
                            # Compile LineString/MultiLineString from OSM path list lists
                            osm_lines = []
                            for path in osm_geom_data:
                                if len(path) >= 2:
                                    osm_lines.append(LineString(path))
                            boundary_geom = osm_lines[0] if len(osm_lines) == 1 else MultiLineString(osm_lines)
                            
                            # Perform split
                            from shapely.ops import split, nearest_points
                            split_result = split(prov_geom, boundary_geom)
                            
                            # If successfully split into multiple parts
                            if hasattr(split_result, "geoms") and len(split_result.geoms) > 1:
                                keep_polys = []
                                b_centroid = boundary_geom.centroid
                                for sub_poly in split_result.geoms:
                                    scx, scy = sub_poly.centroid.x, sub_poly.centroid.y
                                    
                                    # Use nearest point on boundary to determine local relative direction
                                    p1, p2 = nearest_points(sub_poly.centroid, boundary_geom)
                                    local_boundary_y = p2.y
                                    local_boundary_x = p2.x
                                    
                                    if inst.split_direction in ["north_of_latitude", "north_of_natural_boundary"] and scy > local_boundary_y:
                                        keep_polys.append(sub_poly)
                                    elif inst.split_direction in ["south_of_latitude", "south_of_natural_boundary"] and scy < local_boundary_y:
                                        keep_polys.append(sub_poly)
                                    elif inst.split_direction == "west_of_longitude" and scx < local_boundary_x:
                                        keep_polys.append(sub_poly)
                                    elif inst.split_direction == "east_of_longitude" and scx > local_boundary_x:
                                        keep_polys.append(sub_poly)
                                    # Fallback
                                    elif inst.split_direction in ["center", "north_west_diagonal", "south_east_diagonal"]:
                                        keep_polys.append(sub_poly)
                                        
                                if keep_polys:
                                    split_geom = unary_union(keep_polys)
                                    polity_additions_shapes[t.name].append(split_geom)
                                    assigned_parts.setdefault(prov, []).append(split_geom)
                                    print(f"[DEBUG]       OSM Natural Boundary split completed successfully. Sub-polygon area: {split_geom.area:.4f}", flush=True)
                                    if context is not None and "map_markers" in context:
                                        centroid = split_geom.centroid
                                        direction_desc = inst.split_direction.replace('_', ' ').title()
                                        context["map_markers"].append({
                                            "lat": centroid.y,
                                            "lon": centroid.x,
                                            "label": f"📍 {prov} ({direction_desc}) — Assigned to {t.name}"
                                        })
                                    split_done = True
                                else:
                                    debug_vals = [(sp.centroid.y, nearest_points(sp.centroid, boundary_geom)[1].y) for sp in split_result.geoms]
                                    raise Exception(f"No polygons kept after split. dir={inst.split_direction}, vals={debug_vals}")
                                    
                            elif hasattr(split_result, "geoms") and len(split_result.geoms) == 1:
                                # Boundary doesn't intersect. Determine if the entire province is on the correct side
                                scx, scy = prov_geom.centroid.x, prov_geom.centroid.y
                                p1, p2 = nearest_points(prov_geom.centroid, boundary_geom)
                                local_boundary_y = p2.y
                                local_boundary_x = p2.x
                                
                                keep = False
                                if inst.split_direction in ["north_of_latitude", "north_of_natural_boundary"] and scy > local_boundary_y:
                                    keep = True
                                elif inst.split_direction in ["south_of_latitude", "south_of_natural_boundary"] and scy < local_boundary_y:
                                    keep = True
                                elif inst.split_direction == "west_of_longitude" and scx < local_boundary_x:
                                    keep = True
                                elif inst.split_direction == "east_of_longitude" and scx > local_boundary_x:
                                    keep = True
                                    
                                if keep:
                                    polity_additions_shapes[t.name].append(prov_geom)
                                    assigned_parts.setdefault(prov, []).append(prov_geom)
                                    print(f"[DEBUG]       OSM Natural Boundary does not intersect, but province '{prov}' is entirely on correct side. Keeping full area: {prov_geom.area:.4f}", flush=True)
                                    split_done = True
                                else:
                                    print(f"[DEBUG]       OSM Natural Boundary does not intersect, and province '{prov}' is on the WRONG side. Discarding.", flush=True)
                                    split_done = True
                        except Exception as e:
                            print(f"[DEBUG]       OSM split failed, falling back: {e}", flush=True)
                            
                    if not split_done:
                        # 2. Try Landmark Geocoding Split if geocoded coordinates are present
                        geo_coords = context.get("geocoded_landmark_coords") if context else None
                        if geo_coords and val is None:
                            if inst.split_direction in ["north_of_latitude", "south_of_latitude"]:
                                val = geo_coords[0]
                            elif inst.split_direction in ["west_of_longitude", "east_of_longitude"]:
                                val = geo_coords[1]
                                
                        d = max(maxx - minx, maxy - miny) * 5
                        if inst.split_direction == "north_of_latitude":
                            val = val if val is not None else cy
                            split_poly = box(minx, val, maxx, maxy)
                        elif inst.split_direction == "south_of_latitude":
                            val = val if val is not None else cy
                            split_poly = box(minx, miny, maxx, val)
                        elif inst.split_direction == "west_of_longitude":
                            val = val if val is not None else cx
                            split_poly = box(minx, miny, val, maxy)
                        elif inst.split_direction == "east_of_longitude":
                            val = val if val is not None else cx
                            split_poly = box(val, miny, maxx, maxy)
                        elif inst.split_direction == "north_west_diagonal":
                            split_poly = Polygon([(cx - d, cy - d), (cx - d, cy + d), (cx + d, cy + d)])
                        elif inst.split_direction == "south_east_diagonal":
                            split_poly = Polygon([(cx - d, cy - d), (cx + d, cy - d), (cx + d, cy + d)])
                            
                        if split_poly is not None:
                            try:
                                split_geom = prov_geom.intersection(split_poly)
                                polity_additions_shapes[t.name].append(split_geom)
                                print(f"[DEBUG]       Coordinate split completed. Sub-polygon area: {split_geom.area:.4f}", flush=True)
                            except Exception as e:
                                print(f"[DEBUG]       Error executing coordinate split: {e}", flush=True)
                                polity_additions_shapes[t.name].append(prov_geom)
                        else:
                            polity_additions_shapes[t.name].append(prov_geom)
                else:
                    # Fallback to implicit shared province splitting
                    unique_claims = list(set(s[0] for s in shares))
                    if len(unique_claims) > 1:
                        print(f"[DEBUG]     Shared province detected: '{prov}' claimed by {unique_claims}. Fallback alphabetical split.", flush=True)
                        shares_sorted = sorted(unique_claims)
                        idx = shares_sorted.index(t.name)
                        k = len(shares_sorted)
                        
                        minx, miny, maxx, maxy = prov_geom.bounds
                        cx = prov_geom.centroid.x
                        
                        # Divide vertically into equal strips
                        w = (maxx - minx) / k
                        split_poly = box(minx + idx * w, miny, minx + (idx + 1) * w, maxy)
                        
                        try:
                            split_geom = prov_geom.intersection(split_poly)
                            polity_additions_shapes[t.name].append(split_geom)
                            assigned_parts.setdefault(prov, []).append(split_geom)
                        except Exception as e:
                            polity_additions_shapes[t.name].append(prov_geom)
                    else:
                        polity_additions_shapes[t.name].append(prov_geom)

    # Assign remainder of split provinces to their original owner if they were not fully assigned
    unique_split_provinces = set(prov_name for (polity, prov_name), inst in split_instructions.items() if inst.is_split)
    for prov in unique_split_provinces:
        assigned = assigned_parts.get(prov, [])
        try:
            feats = loader.get_province_features(prov)
            if feats:
                prov_geom = shape(feats[0]["geometry"])
                if assigned:
                    assigned_union = unary_union(assigned)
                    remainder_geom = prov_geom.difference(assigned_union)
                else:
                    remainder_geom = prov_geom
                    
                if remainder_geom and not remainder_geom.is_empty:
                    target_polity = None
                    
                    # Heuristic to fix LLM omissions in 2-party treaties:
                    # If province is split but only assigned to 1 polity, remainder goes to the other polity.
                    assigned_polities = [polity for (polity, p_name) in split_instructions.keys() if p_name == prov]
                    if len(territories) == 2 and len(assigned_polities) == 1:
                        other_polity = [t.name for t in territories if t.name != assigned_polities[0]]
                        if other_polity:
                            target_polity = other_polity[0]
                            
                    if not target_polity:
                        original_owner = feats[0]["properties"].get("admin")
                        if original_owner:
                            for t in territories:
                                if original_owner.lower() in t.name.lower() or t.name.lower() in original_owner.lower():
                                    target_polity = t.name
                                    break
                                    
                    if target_polity:
                        polity_additions_shapes[target_polity].append(remainder_geom)
                        print(f"[DEBUG] Auto-assigned remainder of split province '{prov}' to original owner polity '{target_polity}'. Area: {remainder_geom.area:.4f}", flush=True)
                        if context is not None and "map_markers" in context:
                            centroid = remainder_geom.centroid
                            context["map_markers"].append({
                                "lat": centroid.y,
                                "lon": centroid.x,
                                "label": f"📍 {prov} (Remainder) — Assigned to {target_polity}"
                            })
        except Exception as e:
            print(f"[DEBUG] Error auto-assigning remainder for split province {prov}: {e}", flush=True)

    # Build a union of all province shapes mentioned in additions to subtract from baselines (making holes)
    mentioned_provinces = set()
    for t in territories:
        for p in t.partial_countries:
            for prov in p.provinces:
                mentioned_provinces.add((prov, p.country))
                
    contested_shapes = []
    for prov_name, country in mentioned_provinces:
        feats = loader.get_province_features(prov_name, country)
        if feats:
            try:
                contested_shapes.append(shape(feats[0]["geometry"]))
            except Exception:
                pass
                
    contested_union = unary_union(contested_shapes) if contested_shapes else None
    if contested_union:
        print(f"[DEBUG] Created contested provinces union for baseline subtraction. Area: {contested_union.area:.4f}", flush=True)

    resolved_territories = []
    print("[DEBUG] Step 2: Merging baseline and additions shapes for each territory...", flush=True)
    for t in territories:
        actual_name = t.name
        baseline_polities = context.get("baseline_polities", [])
        if actual_name not in baseline_polities:
            for p in t.partial_countries:
                if p.country in baseline_polities:
                    actual_name = p.country
                    break
            else:
                for bp in baseline_polities:
                    if bp.lower() in t.name.lower() or t.name.lower() in bp.lower():
                        actual_name = bp
                        break
                        
        stage2_baselines = context.get("stage2_baselines") if context else None
        base_geom = None
        if stage2_baselines and actual_name in stage2_baselines:
            base_geom = stage2_baselines[actual_name]
            print(f"[DEBUG]     Retrieved COMPOUNDED Stage 1 final geometry for '{actual_name}'. Area: {base_geom.area:.4f}", flush=True)
            print(f"[DEBUG]     Merging with actual historical baseline at year {year}...", flush=True)
            hist_feat = cliopatria_db.get_polity_geometry(actual_name, year)
            if hist_feat and hist_feat.get("geometry"):
                try:
                    hist_geom = shape(hist_feat["geometry"])
                    base_geom = base_geom.union(hist_geom)
                    print(f"[DEBUG]     Merged baseline successfully. Final base area: {base_geom.area:.4f}", flush=True)
                except Exception as e:
                    print(f"[DEBUG]     Error merging historical baseline for {actual_name} at year {year}: {e}", flush=True)
        else:
            print(f"[DEBUG]   Loading baseline geometry for polity: '{actual_name}' at year {year}...", flush=True)
            base_feat = cliopatria_db.get_polity_geometry(actual_name, year)
            if base_feat and base_feat.get("geometry"):
                try:
                    base_geom = shape(base_feat["geometry"])
                    print(f"[DEBUG]     Baseline successfully loaded. Area: {base_geom.area:.4f}, Bounds: {base_geom.bounds}", flush=True)
                except Exception as e:
                    print(f"[DEBUG]     Error parsing base shape for {t.name}: {e}", flush=True)
                
        additions_geom = None
        add_shapes = polity_additions_shapes.get(t.name, [])
        if add_shapes:
            try:
                additions_geom = unary_union(add_shapes)
                print(f"[DEBUG]     Merged {len(add_shapes)} additions shapes. Total additions area: {additions_geom.area:.4f}", flush=True)
            except Exception as e:
                print(f"[DEBUG]     Error merging additions shapes for {t.name}: {e}", flush=True)
                
        resolved_territories.append({
            "definition": t,
            "base_geom": base_geom,
            "additions_geom": additions_geom,
            "final_geom": None
        })
        
    # Step 2: Combine base shape and additions for each party,
    # and subtract those additions from all OTHER parties (losers) to prevent overlapping.
    # In conquest mode, we subtract the conqueror's entire final shape from all opponents.
    conqueror_final_geom = None
    if is_conquest and winner_polity:
        for item in resolved_territories:
            t_def = item["definition"]
            is_winner = (winner_polity.lower() in t_def.name.lower() or t_def.name.lower() in winner_polity.lower())
            if is_winner:
                base_sh = item["base_geom"]
                add_sh = item["additions_geom"]
                if base_sh and add_sh:
                    conqueror_final_geom = base_sh.union(add_sh)
                elif add_sh:
                    conqueror_final_geom = add_sh
                else:
                    conqueror_final_geom = base_sh
                break
                
    for i, item in enumerate(resolved_territories):
        t_def = item["definition"]
        base_sh = item["base_geom"]
        add_sh = item["additions_geom"]
        
        is_winner = True
        if is_conquest and winner_polity:
            is_winner = (winner_polity.lower() in t_def.name.lower() or t_def.name.lower() in winner_polity.lower())
            
        if is_conquest and not is_winner:
            # Opponent: final geometry is baseline shape minus the conqueror's final geometry
            final_sh = base_sh
            if final_sh and conqueror_final_geom:
                try:
                    final_sh = final_sh.difference(conqueror_final_geom)
                    if getattr(final_sh, 'geom_type', None) == 'MultiPolygon':
                        from shapely.geometry import MultiPolygon
                        valid_polys = []
                        for p in final_sh.geoms:
                            # Sliver filter
                            if p.area < 0.1 and conqueror_final_geom and p.distance(conqueror_final_geom) < 0.1:
                                continue
                            valid_polys.append(p)
                        final_sh = MultiPolygon(valid_polys) if valid_polys else None
                except Exception as e:
                    print(f"[SIMULATOR] Error subtracting conqueror geometry from opponent {t_def.name}: {e}")
            item["final_geom"] = final_sh
        else:
            # Winner or other modes (like partition/treaty)
            final_sh = base_sh
            if add_sh:
                if final_sh:
                    final_sh = final_sh.union(add_sh)
                else:
                    final_sh = add_sh
                    
            if not is_conquest:
                # Standard treaty partition mutual subtraction logic
                for j, other_item in enumerate(resolved_territories):
                    if i == j:
                        continue
                    other_add = other_item["additions_geom"]
                    if other_add and final_sh:
                        try:
                            final_sh = final_sh.difference(other_add)
                        except Exception as e:
                            print(f"[SIMULATOR] Error subtracting geometry: {e}")
            item["final_geom"] = final_sh
        
    # Step 3: Format back into GeoJSON Features
    features = []
    for item in resolved_territories:
        t = item["definition"]
        final_sh = item["final_geom"]
        if not final_sh or final_sh.is_empty:
            continue
            
        # Color coding for map presentation
        color = t.color
        if not color:
            name_lower = t.name.lower()
            if "umayyad" in name_lower:
                color = "#10b981" # green
            elif "frank" in name_lower or "caroling" in name_lower:
                color = "#ef4444" # red
            elif "byzant" in name_lower:
                color = "#8b5cf6" # purple
            elif "india" in name_lower:
                color = "#fbbf24" # saffron/yellow
            elif "pakistan" in name_lower:
                color = "#047857" # emerald green
            else:
                color = "#d4a853" # default gold
            
        features.append({
            "type": "Feature",
            "properties": {
                "name": t.name,
                "color": color,
                "status": t.status,
                "description": t.description,
                "capital": t.capital,
                "population": t.population_estimate
            },
            "geometry": mapping(final_sh)
        })
        
    # Populate resolved geoms collector if present in context
    if context is not None:
        compounding_resolved = context.get("compounding_resolved_geoms")
        if compounding_resolved is not None:
            compounding_resolved.clear()
            baseline_polities = context.get("baseline_polities", [])
            for item in resolved_territories:
                t = item["definition"]
                # Resolve actual_name
                actual_name = t.name
                if actual_name not in baseline_polities:
                    for bp in baseline_polities:
                        if bp.lower() in t.name.lower() or t.name.lower() in bp.lower():
                            actual_name = bp
                            break
                final_sh = item["final_geom"]
                if final_sh and not final_sh.is_empty:
                    compounding_resolved[t.name] = final_sh
                    compounding_resolved[actual_name] = final_sh
        
    return features
