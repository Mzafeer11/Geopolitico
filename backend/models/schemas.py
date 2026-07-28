"""
Canonical Pydantic models for Geopolitico simulation engine.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


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
    provinces: List[str] = Field(default=[], description="List of modern province names within the country.")
    historical_provinces: List[str] = Field(default=[], description="List of precomputed historical sub-provinces/themes (e.g. ['Aquitaine', 'Septimania', 'Provence', 'Neustria']) conquered or transferred.")
    split_provinces: List[SplitProvince] = Field(default=[], description="List of custom geometric splitting configurations for shared/partitioned provinces.")
    clip_method: Literal["historical_provinces", "provinces", "natural_boundary", "coordinate_latitude", "coordinate_longitude"] = Field(
        default="provinces",
        description="Method to clip/select geometry: 'historical_provinces' (use historical_provinces list), 'provinces' (use provinces list), 'natural_boundary' (clip country by river/mountains)."
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
    countries_absorbed: List[str] = Field(default=[], description="Modern countries fully controlled.")
    historical_provinces: List[str] = Field(default=[], description="List of precomputed historical sub-provinces/themes (e.g. ['Aquitaine', 'Septimania', 'Provence']) conquered or transferred.")
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


__all__ = [
    "PlanningResult",
    "SequentialScenarioPlan",
    "SplitProvince",
    "PartialRegion",
    "EnclaveResolutionOption",
    "ValidationAnomalyQuestion",
    "AnomalyCheckResult",
    "TerritoryChange",
    "ValidationTerritoriesResult",
    "TimelineEvent",
    "ScenarioStateResult",
]
