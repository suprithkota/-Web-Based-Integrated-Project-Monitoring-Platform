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
from database.models import User, Project
from services.risk_service import update_project_risk

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProjectsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            # Demo admin
            admin = User(username='admin', email='admin@test.com', role='admin', full_name='Admin User')
            admin.set_password('admin123')
            
            p = Project(
                project_code='PRJ-TEST-1',
                project_name='Test Expressway Package 1',
                ministry='Ministry of Road Transport & Highways',
                sector='Roads',
                state='Maharashtra',
                approved_cost=1000.0,
                revised_cost=1200.0,
                expenditure=600.0,
                physical_progress=45.0,
                planned_progress=70.0,
                delay_days=120,
                contractor_status='Delayed',
                land_acquisition_status='Delayed',
                reporting_date=date.today()
            )
            db.session.add_all([admin, p])
            db.session.flush()
            update_project_risk(p)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self):
        return self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

    def test_project_retrieval(self):
        self._login()
        res = self.client.get('/projects')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Test Expressway Package 1', res.data)
        self.assertIn(b'PRJ-TEST-1', res.data)

    def test_project_detail_view(self):
        self._login()
        res = self.client.get('/projects/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Explainable Risk Factors', res.data)
        self.assertIn(b'Overall Project Health Score', res.data)

    def test_project_api(self):
        self._login()
        res = self.client.get('/api/projects/1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['project']['project_code'], 'PRJ-TEST-1')
        self.assertGreater(data['project']['delay_probability'], 0)

if __name__ == '__main__':
    unittest.main()
