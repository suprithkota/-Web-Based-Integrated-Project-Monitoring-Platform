import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ml.preprocessing import extract_features_from_dict
from ml.risk_model import risk_engine

class RiskEngineTestCase(unittest.TestCase):
    def test_low_risk_project_evaluation(self):
        low_risk_project = {
            'physical_progress': 85.0,
            'planned_progress': 87.0,
            'approved_cost': 1000.0,
            'revised_cost': 1020.0,
            'expenditure': 820.0,
            'delay_days': 10,
            'milestones_total': 4,
            'milestones_delayed': 0,
            'contractor_status': 'On Track',
            'land_acquisition_status': 'Completed',
            'environmental_clearance_status': 'Completed',
            'utility_shifting_status': 'Completed'
        }
        result = risk_engine.evaluate_project(low_risk_project)
        
        self.assertIn(result['risk_level'], ['LOW', 'MEDIUM'])
        self.assertLess(result['delay_probability'], 45.0)
        self.assertGreater(result['health_score'], 55.0)
        self.assertIn('Physical progress gap', result['contributing_factors'])

    def test_critical_risk_project_evaluation(self):
        critical_project = {
            'physical_progress': 42.0,
            'planned_progress': 85.0,
            'approved_cost': 5000.0,
            'revised_cost': 7200.0,
            'expenditure': 4800.0,
            'delay_days': 360,
            'milestones_total': 6,
            'milestones_delayed': 4,
            'contractor_status': 'Critical',
            'land_acquisition_status': 'Delayed',
            'environmental_clearance_status': 'Pending',
            'utility_shifting_status': 'Delayed'
        }
        result = risk_engine.evaluate_project(critical_project)
        
        self.assertIn(result['risk_level'], ['HIGH', 'CRITICAL'])
        self.assertGreater(result['delay_probability'], 65.0)
        self.assertGreater(result['cost_overrun_probability'], 60.0)
        self.assertLess(result['health_score'], 45.0)
        self.assertTrue(len(result['root_causes']) >= 2)

    def test_feature_extraction_dimensions(self):
        sample = {
            'physical_progress': 50.0,
            'planned_progress': 60.0,
            'approved_cost': 1000.0,
            'revised_cost': 1100.0,
            'expenditure': 500.0,
            'delay_days': 30,
            'milestones_total': 4,
            'milestones_delayed': 1
        }
        vec, raw = extract_features_from_dict(sample)
        self.assertEqual(len(vec), 11)
        self.assertAlmostEqual(raw['progress_gap'], 10.0)

if __name__ == '__main__':
    unittest.main()
