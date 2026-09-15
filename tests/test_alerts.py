import unittest
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from app import create_app
from database import db
from database.models import Project, Alert
from services.alert_service import evaluate_and_generate_alerts, update_alert_status

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class AlertsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        with self.app.app_context():
            db.create_all()
            
            p = Project(
                project_code='PRJ-ALERT-1',
                project_name='Delayed Coastal Corridor',
                ministry='Ministry of Ports, Shipping & Waterways',
                sector='Ports',
                state='Gujarat',
                approved_cost=2000.0,
                revised_cost=2600.0,  # 30% cost escalation
                expenditure=1800.0,
                physical_progress=35.0,
                planned_progress=75.0, # 40% progress gap
                delay_days=250,
                milestones_total=5,
                milestones_delayed=3,
                contractor_status='Delayed',
                land_acquisition_status='Delayed',
                environmental_clearance_status='Pending',
                reporting_date=date.today()
            )
            db.session.add(p)
            db.session.commit()
            self.project_id = p.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_alert_generation(self):
        with self.app.app_context():
            p = db.session.get(Project, self.project_id)
            alerts = evaluate_and_generate_alerts(p)
            db.session.commit()
            
            self.assertGreater(len(alerts), 0)
            triggers = [a.trigger for a in alerts]
            self.assertIn('SEVERE_PROGRESS_SLIPPAGE', triggers)
            self.assertIn('HIGH_COST_ESCALATION', triggers)

    def test_alert_triage_resolution(self):
        with self.app.app_context():
            p = db.session.get(Project, self.project_id)
            evaluate_and_generate_alerts(p)
            db.session.commit()
            
            alert = Alert.query.first()
            self.assertIsNotNone(alert)
            self.assertEqual(alert.status, 'Open')
            
            updated = update_alert_status(alert.id, 'Resolved', 'Officer Sharma', 'Land dispute resolved via fast-track tribunal')
            self.assertEqual(updated.status, 'Resolved')
            self.assertIsNotNone(updated.resolved_at)
            self.assertIn('Sharma', updated.notes)

if __name__ == '__main__':
    unittest.main()
