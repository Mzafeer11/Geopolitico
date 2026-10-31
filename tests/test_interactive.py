import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI app
from backend.main import app

client = TestClient(app)

def test_root_route():
    response = client.get("/")
    # If index.html exists, it mounts static files at /, otherwise returns a JSON message.
    # We can check either status code 200 or the returned content.
    assert response.status_code == 200

@patch("backend.main.simulate_start")
def test_simulate_endpoint(mock_simulate_start):
    # Mock the return value of simulate_start
    mock_simulate_start.return_value = {
        "status": "completed",
        "result": {
            "title": "Test Scenario",
            "base_year": 732,
            "historical_context": "Actual context",
            "what_actually_happened": "What happened",
            "alternate_outcome": "Alt outcome",
            "key_changes": ["Change 1"],
            "timeline": [{"year": 732, "event": "Event 1"}],
            "territories_before": [],
            "territories_after_realistic": [],
            "territories_after_optimistic": [],
            "realistic_scenario_summary": "Realistic",
            "optimistic_scenario_summary": "Optimistic",
            "butterfly_effects": ["Effect 1"],
            "confidence_score": 0.8,
            "sources": ["http://test.com"]
        },
        "session_id": "test-session-id"
    }

    # Send simulation request
    response = client.post(
        "/api/simulate",
        json={"scenario": "What if test?", "token": "test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"

@patch("backend.main.simulate_step")
def test_interactive_step_endpoint(mock_step_session):
    # Mock the return value of simulate_step
    mock_step_session.return_value = {
        "status": "success",
        "result": {
            "title": "Refined Outcome",
            "geojson_before": {"type": "FeatureCollection", "features": []},
            "geojson_after_realistic": {"type": "FeatureCollection", "features": []},
            "geojson_after_optimistic": {"type": "FeatureCollection", "features": []},
            "territories_before": [],
            "territories_after_realistic": [],
            "territories_after_optimistic": []
        },
        "session_id": "test-session-id"
    }

    response = client.post(
        "/api/interactive/step",
        json={"session_id": "test-session-id", "message": "hello", "token": "test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] is not None
    assert data["status"] == "queued"
