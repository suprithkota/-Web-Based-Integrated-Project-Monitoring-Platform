import unittest
import json
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from app import create_app
from database import db
from database.models import User, Project
from services.risk_service import update_project_risk

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class APITestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            user = User(username='officer', email='officer@test.com', role='officer')
            user.set_password('officer123')
            
            p = Project(
                project_code='PRJ-API-1',
                project_name='API Test Project',
                ministry='Ministry of Railways',
                sector='Railways',
                state='Telangana',
                approved_cost=1500.0,
                revised_cost=1650.0,
                expenditure=700.0,
                physical_progress=50.0,
                planned_progress=65.0,
                delay_days=60,
                reporting_date=date.today()
            )
            db.session.add_all([user, p])
            db.session.flush()
            update_project_risk(p)
            db.session.commit()
            self.project_id = p.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self):
        return self.client.post('/login', data={'username': 'officer', 'password': 'officer123'})

    def test_dashboard_api(self):
        self._login()
        res = self.client.get('/api/dashboard')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['kpis']['total_projects'], 1)
        self.assertIn('risk_distribution', data['charts'])

    def test_simulate_api(self):
        self._login()
        payload = {
            'project_id': self.project_id,
            'physical_progress': 30.0,  # stress test: lower progress
            'delay_days': 180           # increase delay
        }
        res = self.client.post('/api/simulate', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('current', data)
        self.assertIn('simulated', data)
        self.assertGreater(data['simulated']['risk_score'], data['current']['risk_score'])

    def test_assistant_api(self):
        self._login()
        payload = {'query': 'Which projects have the highest delay risk?'}
        res = self.client.post('/api/assistant', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('PRJ-API-1', data['response'])

    def test_map_data_api(self):
        self._login()
        res = self.client.get('/api/map-data')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['count'], 1)
        self.assertIsNotNone(data['markers'][0]['lat'])

if __name__ == '__main__':
    unittest.main()
