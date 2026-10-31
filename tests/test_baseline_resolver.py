import sys
import pytest
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.tools.baseline_resolver import get_historical_units, _calculate_boundary_direction
from shapely.geometry import Polygon, LineString

def test_umayyad_historical_units():
    print("=== Testing Baseline Resolver: Umayyad Caliphate (732 AD) ===")
    res = get_historical_units("Umayyad Caliphate", 732, "Middle East")
    print(f"Polity: {res['polity']}")
    print(f"Tier: {res['tier']} (Confidence: {res['confidence']})")
    print(f"Core Provinces count: {len(res['provinces_core'])}")
    print(f"Edge Provinces count: {len(res['provinces_edge'])}")
    print(f"Metadata: {res['metadata']}")
    
    assert res["tier"] in ["wikidata_structured", "wikidata_structured_advanced", "wikipedia_parsed"], f"Unexpected tier: {res['tier']}"
    assert res["confidence"] in ["high", "medium"]
    assert len(res["provinces_core"]) + len(res["provinces_edge"]) >= 3
    assert res["geometry"] is not None
    print("Umayyad Caliphate Test Passed!\n")

def test_alandalus_historical_units():
    print("=== Testing Baseline Resolver: Al-Andalus (756 AD) ===")
    res = get_historical_units("Al-Andalus", 756, "Iberia")
    print(f"Polity: {res['polity']}")
    print(f"Tier: {res['tier']} (Confidence: {res['confidence']})")
    print(f"Core Provinces count: {len(res['provinces_core'])}")
    print(f"Edge Provinces count: {len(res['provinces_edge'])}")
    assert res["tier"] in ["wikidata_structured", "wikidata_structured_advanced", "wikipedia_parsed"], f"Unexpected tier: {res['tier']}"
    assert len(res["provinces_core"]) + len(res["provinces_edge"]) >= 3
    assert res["geometry"] is not None
    print("Al-Andalus Test Passed!\n")

def test_byzantine_historical_units():
    print("=== Testing Baseline Resolver: Byzantine Empire (717 AD) ===")
    res = get_historical_units("Byzantine Empire", 717, "Anatolia")
    print(f"Polity: {res['polity']}")
    print(f"Tier: {res['tier']} (Confidence: {res['confidence']})")
    print(f"Core Provinces count: {len(res['provinces_core'])}")
    
    assert res["tier"] in ["wikidata_structured", "wikidata_structured_advanced", "wikipedia_parsed"], f"Unexpected tier: {res['tier']}"
    assert res["geometry"] is not None
    print("Byzantine Empire Test Passed!\n")

def test_franks_historical_units():
    print("=== Testing Baseline Resolver: Kingdom of the Franks (732 AD) ===")
    res = get_historical_units("Kingdom of the Franks", 732, "Western Europe")
    print(f"Polity: {res['polity']}")
    print(f"Tier: {res['tier']} (Confidence: {res['confidence']})")
    print(f"Core Provinces count: {len(res['provinces_core'])}")
    
    assert res["tier"] in ["wikidata_structured", "wikidata_structured_advanced", "wikipedia_parsed"]
    assert res["geometry"] is not None
    print("Kingdom of the Franks Test Passed!\n")

def test_direction_calculation():
    print("=== Testing Boundary Direction Centroid Calculation ===")
    # Polygon centered at (10, 10) - South of line
    poly = Polygon([(5, 5), (15, 5), (15, 12), (5, 12)])
    # East-West boundary line at Y = 20
    line_ew = LineString([(0, 20), (20, 20)])
    
    direction = _calculate_boundary_direction(poly, line_ew)
    assert direction == "south_of_natural_boundary", f"Expected south_of_natural_boundary, got {direction}"
    
    # North-South boundary line at X = 20
    line_ns = LineString([(20, 0), (20, 20)])
    direction_ns = _calculate_boundary_direction(poly, line_ns)
    assert direction_ns == "west_of_natural_boundary", f"Expected west_of_natural_boundary, got {direction_ns}"
    print("Boundary Direction Calculation Test Passed!\n")

def test_fallback_cliopatria_coarse():
    print("=== Testing Baseline Resolver Fallback ===")
    res = get_historical_units("NonExistentPolity12345", 1500)
    print(f"Tier: {res['tier']} (Confidence: {res['confidence']})")
    assert res["tier"] in ["cliopatria_coarse", "cliopatria_province_breakdown", "llm_boundary"]
    assert res["confidence"] in ["low", "medium", "inferred"]
    print("Fallback Test Passed!\n")

if __name__ == "__main__":
    test_umayyad_historical_units()
    test_alandalus_historical_units()
    test_byzantine_historical_units()
    test_franks_historical_units()
    test_direction_calculation()
    test_fallback_cliopatria_coarse()
    print("ALL BASELINE RESOLVER TESTS PASSED!")
