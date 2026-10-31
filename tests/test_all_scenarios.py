"""
Comprehensive Pytest Suite for Geopolitico Simulation Engine.
Tests graph orchestration and pipeline execution for all scenario modes.
"""

import pytest
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.simulation_engine import simulate_start


def test_conquest_scenario_imports_and_structure():
    """Verify backend modules import cleanly."""
    import backend.simulation_engine
    import backend.orchestrator.graph
    import backend.pipelines.partition
    import backend.pipelines.conquest
    import backend.pipelines.compounding
    import backend.pipelines.demographic
    import backend.tools.compiler
    assert True


def test_partition_scenario_mode():
    """Test Treaty Partition simulation pipeline mode."""
    scenario = "What if the Chenab Formula was accepted during the 1960s as partition of Kashmir between Pakistan and India?"
    res = simulate_start(scenario)
    assert res["status"] in ["completed", "awaiting_verification"]
    assert "result" in res
    assert res["session_id"] is not None


def test_conquest_scenario_mode():
    """Test Military Expansion Conquest simulation pipeline mode."""
    scenario = "What if the Umayyad Caliphate conquered the Kingdom of the Franks at Tours in 732 AD?"
    res = simulate_start(scenario)
    assert res["status"] in ["completed", "awaiting_verification"]
    assert "result" in res


def test_demographics_scenario_mode():
    """Test Demographic Shift simulation pipeline mode."""
    scenario = "What if Muslims were 60 percent of British India's population during partition?"
    res = simulate_start(scenario)
    assert res["status"] in ["completed", "awaiting_verification"]
    assert "result" in res
