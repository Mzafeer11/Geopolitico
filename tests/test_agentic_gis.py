import sys
import os
from pathlib import Path

# Add root folder to python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.agents.prompt_guardrail import refine_user_prompt
from backend.tools.gis_tools import geocode_landmark_tool, natural_boundary_tool
from backend.simulation_engine import simulate_start

def test_prompt_guardrail():
    print("=== Testing Prompt Guardrail ===")
    
    # 1. Spelling test
    typo_prompt = "What if the chenab river formular was accepted at 1960"
    res = refine_user_prompt(typo_prompt)
    print(f"Original: {typo_prompt}")
    print(f"Refined: {res['refined_prompt']}")
    print(f"Corrections: {res['corrections_made']}")
    assert "formula" in res["refined_prompt"].lower(), "Spelling was not corrected."
    
    # 2. Historical contradiction test
    conflict_prompt = "What if the partition boundary was drawn along the Chenab River instead of the Radcliffe Line?"
    res2 = refine_user_prompt(conflict_prompt)
    print(f"Original: {conflict_prompt}")
    print(f"Refined: {res2['refined_prompt']}")
    print(f"Corrections: {res2['corrections_made']}")
    assert res2["refined_prompt"] != conflict_prompt, "Historical contradiction was not corrected/aligned."
    print("Prompt Guardrail Tests Passed!\n")

def test_nominatim_geocode():
    print("=== Testing Nominatim Geocoding ===")
    res = geocode_landmark_tool("Louvre")
    print(res)
    assert res["status"] == "success", "Geocoding failed."
    assert 48.8 <= res["latitude"] <= 48.9, "Latitude out of range for Louvre (Paris)."
    assert 2.3 <= res["longitude"] <= 2.4, "Longitude out of range for Louvre (Paris)."
    print("Nominatim Geocoding Tests Passed!\n")

def test_osm_overpass():
    print("=== Testing OSM Overpass Natural Boundary ===")
    res = natural_boundary_tool("Chenab River")
    print(f"OSM Boundary Status: {res['status']}")
    if res["status"] == "success":
        print(f"Found {len(res['paths'])} segments. Message: {res['message']}")
        assert len(res["paths"]) > 0, "No paths returned."
    else:
        print(f"OSM retrieval returned: {res['message']}")
    print("OSM Overpass Tests Passed!\n")

def test_full_pipeline_compilation():
    print("=== Testing Full Pipeline Compilation ===")
    prompt = "What if the chenab river formular was accepted at 1960 and kashmir was divided along the chenab river?"
    res = simulate_start(prompt)
    assert res["status"] == "completed", "Simulation start pipeline failed."
    print("Full Pipeline Compilation Tests Passed!\n")

if __name__ == "__main__":
    if not os.environ.get("GITHUB_TOKEN"):
        print("Please set GITHUB_TOKEN environment variable.")
        sys.exit(1)
        
    try:
        test_prompt_guardrail()
        test_nominatim_geocode()
        test_osm_overpass()
        test_wikipedia_demographics()
        test_full_pipeline_compilation()
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
    except Exception as e:
        print(f"Test Execution Failed: {e}")
        sys.exit(1)
