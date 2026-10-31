import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.pipelines.demographic import run_demographic_simulation

class TestDemographicEngine(unittest.TestCase):

    def test_year_guardrail_error(self):
        context = {
            "scenario": "What if Muslims were 60% of France in 1600?",
            "year": 1600,
            "simulation_mode": "demographic_shift"
        }
        res = run_demographic_simulation(context)
        self.assertEqual(res["status"], "error")
        self.assertIn("year >= 1900", res["error_message"])

    def test_partition_60_percent_simulation(self):
        context = {
            "scenario": "What if Muslims were 60% of Indian population at the time of Partition in 1941?",
            "year": 1941,
            "simulation_mode": "demographic_shift"
        }
        res = run_demographic_simulation(context)
        self.assertEqual(res["status"], "success")
        self.assertTrue(len(res["realistic_features"]) > 0)
        self.assertTrue(len(res["optimistic_features"]) > 0)

if __name__ == "__main__":
    unittest.main()
