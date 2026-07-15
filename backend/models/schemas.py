from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field

class HistoricalFact(BaseModel):
    fact: str = Field(description="A specific, verified historical fact relevant to the event.")
    source: str = Field(description="The source URL or citation (e.g. Wikipedia).")
    confidence: str = Field(description="Confidence rating: high, medium, or low.")

class TimelineEvent(BaseModel):
    year: int = Field(description="The year the event occurs in the simulated timeline.")
    event: str = Field(description="Description of what happens in this year.")

class PartialRegion(BaseModel):
    country: str = Field(description="The modern country name containing the region (e.g. France).")
    portion: str = Field(description="The portion of the country: southern, northern, eastern, western, or custom.")
    clip_method: str = Field(description="Method to clip polygon: 'latitude', 'longitude', or 'provinces'. Prefer 'provinces' when specific province names are known.")
    clip_value: Optional[float] = Field(None, description="The coordinate value for clipping (used when clip_method is latitude or longitude).")
    clip_description: str = Field(description="Human-readable description of the clip boundary (e.g. 'South of the Loire River').")
    landmark_city: Optional[str] = Field(None, description="A landmark city to geocode as a reference point for coordinate-based clipping.")
    provinces: List[str] = Field(default=[], description="Specific province/state/region names within the country to include (used when clip_method is 'provinces'). Example: ['Occitanie', 'Nouvelle-Aquitaine', 'Provence-Alpes-Cote d Azur']")
    status: Literal["direct_control", "vassal", "tributary"] = Field(
        default="direct_control",
        description="Relationship status: 'direct_control' for fully annexed territory, 'vassal' for autonomous vassal states, 'tributary' for tribute-paying buffer zones."
    )

class TerritoryChange(BaseModel):
    name: str = Field(description="Name of the alternate history territory or empire.")
    type: str = Field(description="Type of entity: empire, kingdom, republic, or region.")
    color: str = Field(description="A hex code color representing the territory on the map.")
    status: Literal["direct_control", "vassal", "tributary"] = Field(
        default="direct_control",
        description="Relationship status: 'direct_control' for fully annexed territory, 'vassal' for autonomous vassal states, 'tributary' for tribute-paying buffer zones."
    )
    countries_absorbed: List[str] = Field(description="List of modern country names FULLY absorbed by this territory. Include all countries where the empire controlled the entire modern country.")
    partial_countries: List[PartialRegion] = Field(default=[], description="List of sub-regions or partial countries absorbed. Use this for countries where only part was controlled (e.g. only southern France).")
    description: str = Field(description="A description of the territory and its significance in the simulation.")
    population_estimate: Optional[str] = Field(None, description="Estimated population of the territory.")
    capital: Optional[str] = Field(None, description="Proposed or historical capital city.")

class HistoricalRegionMapping(BaseModel):
    historical_name: str = Field(description="The historical name of the region as used in medieval/ancient times (e.g. 'Aquitaine', 'Septimania', 'Khurasan').")
    modern_country: str = Field(description="The modern country this region falls within.")
    modern_provinces: List[str] = Field(description="The modern province/state/region names that correspond to this historical region.")
    notes: str = Field(description="Brief explanation of the mapping and any caveats.")

class ScenarioResult(BaseModel):
    title: str = Field(description="Short descriptive title of the simulation.")
    base_year: int = Field(description="The starting year of the alternate timeline.")
    historical_context: str = Field(description="Summary of the actual historical context.")
    what_actually_happened: str = Field(description="Brief summary of the real-world outcome.")
    alternate_outcome: str = Field(description="The simulated geopolitical alternate history outcome.")
    key_changes: List[str] = Field(description="Key structural changes in geopolitics, borders, or institutions.")
    timeline: List[TimelineEvent] = Field(description="Chronological timeline of events leading from the split to the final state.")

    # Before state: the actual historical empire/borders at the base year
    territories_before: List[TerritoryChange] = Field(
        description="The FULL empire/territories as they ACTUALLY existed in the base year. Must include ALL countries the empire controlled, not just the disputed region."
    )

    # After state: TWO scenarios — realistic and optimistic
    territories_after_realistic: List[TerritoryChange] = Field(
        description="Scenario 1 (Realistic): The FULL empire including all original territories PLUS the most plausible new conquests. Show the entire empire, not just gains."
    )
    territories_after_optimistic: List[TerritoryChange] = Field(
        description="Scenario 2 (Optimistic/Maximum): The FULL empire including all original territories PLUS maximum plausible expansion under best-case conditions. Show the entire empire, not just gains."
    )

    realistic_scenario_summary: str = Field(
        description="One or two sentences describing what the Realistic scenario represents and why these gains are considered most plausible."
    )
    optimistic_scenario_summary: str = Field(
        description="One or two sentences describing what the Optimistic scenario represents and what conditions would have been needed for this maximum expansion."
    )

    butterfly_effects: List[str] = Field(description="Speculative broader long-term ripple effects on world history.")
    confidence_score: float = Field(description="Self-rated score of simulation plausibility from 0.0 to 1.0.")
    sources: List[str] = Field(description="List of source URLs referenced during research.")

