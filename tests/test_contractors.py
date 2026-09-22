import unittest
from datetime import datetime, date, timedelta
from app import create_app
from config import TestingConfig
from database import db
from database.models import (
    User, Project, Contractor, ContractorBranch, MaterialSupplier,
    ProjectMaterial, MaterialQualityTest, ProjectDelayRecord,
    PublicComplaint, DocumentEvidence
)
from services.contractor_service import ContractorService

class ContractorIntelligenceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Users: admin, officer, viewer
        self.admin = User(username='test_admin', email='admin@test.gov.in', role='admin', email_verified=True, status='active')
        self.admin.set_password('AdminPass123!')

        self.officer = User(username='test_officer', email='officer@test.gov.in', role='officer', email_verified=True, status='active', technical_designation='Assistant Engineer')
        self.officer.set_password('OfficerPass123!')

        self.viewer = User(username='test_viewer', email='viewer@test.gov.in', role='viewer', email_verified=True, status='active')
        self.viewer.set_password('ViewerPass123!')

        db.session.add_all([self.admin, self.officer, self.viewer])
        db.session.commit()

        # Seed test contractor
        self.contractor = Contractor(
            name='Test Infrastructure Enterprises Ltd',
            contractor_code='CON-TEST-01',
            registration_number='REG-TEST-9988',
            contractor_license_number='LIC-TEST-001',
            company_type='Public Limited',
            contractor_class='Class-1',
            headquarters='New Delhi',
            year_established=2012,
            years_of_experience=12,
            owner_representative='A.K. Sharma',
            contact_email='contact@testinfra.gov.in',
            contact_phone='+91 11 2345 6789',
            address='Barakhamba Road, New Delhi',
            data_source='CPPP Central Public Procurement Portal',
            verification_status='Verified',
            registration_status='Active'
        )
        db.session.add(self.contractor)
        db.session.commit()

        # Seed two test projects linked to contractor
        self.p1 = Project(
            project_code='PRJ-TEST-1',
            project_name='Highway Package Alpha',
            ministry='Ministry of Road Transport & Highways',
            sector='Roads',
            state='Haryana',
            approved_cost=1000.0,
            revised_cost=1050.0,
            original_budget=1000.0,
            expenditure=850.0,
            physical_progress=85.0,
            planned_progress=85.0,
            delay_days=0,
            project_status='Ongoing',
            contractor_id=self.contractor.id
        )
        self.p2 = Project(
            project_code='PRJ-TEST-2',
            project_name='Bridge Package Beta',
            ministry='Ministry of Road Transport & Highways',
            sector='Bridges',
            state='Punjab',
            approved_cost=500.0,
            revised_cost=620.0,
            original_budget=500.0,
            expenditure=620.0,
            physical_progress=100.0,
            planned_progress=100.0,
            delay_days=120,
            project_status='Completed',
            contractor_id=self.contractor.id
        )
        db.session.add_all([self.p1, self.p2])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, username, password):
        self.client.get('/logout')
        return self.client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    def test_contractor_dashboard_accessible_by_all_roles(self):
        """Verify contractor intelligence dashboard is publicly viewable by viewer, officer, and admin."""
        # Unauthenticated / viewer
        resp = self.client.get('/contractor-intelligence')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Section 25 Verified Intelligence Standard', resp.data)

        # Viewer authenticated
        self.login('test_viewer', 'ViewerPass123!')
        resp = self.client.get('/contractor-intelligence')
        self.assertEqual(resp.status_code, 200)

        # Officer authenticated
        self.login('test_officer', 'OfficerPass123!')
        resp = self.client.get('/contractor-intelligence')
        self.assertEqual(resp.status_code, 200)

    def test_contractors_directory_search_and_filter(self):
        """Test contractor listing and filtering by keyword and class."""
        resp = self.client.get('/contractors?search=Test+Infrastructure')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test Infrastructure Enterprises Ltd', resp.data)

        resp_none = self.client.get('/contractors?search=NonExistentCompany')
        self.assertEqual(resp_none.status_code, 200)
        self.assertNotIn(b'Test Infrastructure Enterprises Ltd', resp_none.data)

    def test_contractor_10_tab_profile_metrics(self):
        """Verify contractor detail metrics calculation and fairness rules."""
        metrics = ContractorService.calculate_contractor_metrics(self.contractor)
        self.assertEqual(metrics['total_projects'], 2)
        self.assertEqual(metrics['completed_projects'], 1)
        self.assertEqual(metrics['ongoing_projects'], 1)
        # Cost variance: (1050 + 620) - (1000 + 500) = 170.0 Cr
        self.assertEqual(metrics['total_cost_variance'], 170.0)

        # Grounded AI summary must be purely objective without subjective labels
        summary = ContractorService.generate_contractor_ai_summary(self.contractor)
        self.assertNotIn('fraud', summary['text'].lower())
        self.assertNotIn('worst', summary['text'].lower())
        self.assertNotIn('best', summary['text'].lower())
        self.assertIn('Test Infrastructure Enterprises Ltd', summary['text'])

        # Browser route
        resp = self.client.get(f'/contractors/{self.contractor.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test Infrastructure Enterprises Ltd', resp.data)
        self.assertIn(b'REG-TEST-9988', resp.data)

    def test_citizen_grievance_filing_by_public_or_viewer(self):
        """Verify that any public citizen / viewer can submit a grievance with location and details."""
        resp = self.client.post('/contractors/complaints/new', data={
            'project_id': self.p1.id,
            'category': 'Potholes / Pavement Breakdown',
            'location': 'NH-44 Near Sector 14, Panipat',
            'gps_lat': 29.3909,
            'gps_lng': 76.9635,
            'description': 'Deep potholes causing major traffic slow down and motorcycle hazard.',
            'complainant_name': 'Ramesh Kumar',
            'complainant_contact': '+91 98765 11223'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        complaint = PublicComplaint.query.filter_by(location='NH-44 Near Sector 14, Panipat').first()
        self.assertIsNotNone(complaint)
        self.assertEqual(complaint.status, 'Submitted')
        self.assertEqual(complaint.category, 'Potholes / Pavement Breakdown')

    def test_viewer_blocked_from_contractor_modification(self):
        """Verify that viewer role cannot edit or register contractors (RBAC enforcement)."""
        self.login('test_viewer', 'ViewerPass123!')
        
        # Attempt to access contractor registration form
        resp = self.client.get('/contractors/new')
        # Viewer should be forbidden (403)
        self.assertEqual(resp.status_code, 403)

        # Attempt to post new contractor
        post_resp = self.client.post('/contractors/new', data={
            'name': 'Unauthorized Contractor',
            'contractor_code': 'CON-BAD',
            'registration_number': 'REG-BAD-01'
        })
        self.assertEqual(post_resp.status_code, 403)

    def test_officer_can_log_quality_test_and_delay(self):
        """Verify that officer can record BIS quality tests and delay root causes."""
        self.login('test_officer', 'OfficerPass123!')

        # 1. Create a project material
        mat = ProjectMaterial(
            project_id=self.p1.id,
            contractor_id=self.contractor.id,
            material_name='Fe500D TMT Rebar',
            material_category='Steel',
            brand_manufacturer='Tata Tiscon',
            batch_number='TIS-BATCH-001',
            quantity=500.0,
            unit='MT'
        )
        db.session.add(mat)
        db.session.commit()

        # 2. Officer records quality lab test
        resp_test = self.client.post('/contractors/materials/test/new', data={
            'material_id': mat.id,
            'project_id': self.p1.id,
            'test_name': 'Tensile Strength IS 1786',
            'required_standard': 'IS 1786:2008',
            'test_result_value': 'Yield: 540 N/mm2, Elongation: 14.5%',
            'status': 'PASS',
            'testing_laboratory': 'CRRI Testing Facility',
            'quality_certificate_ref': 'CRRI-2026-901'
        }, follow_redirects=True)
        self.assertEqual(resp_test.status_code, 200)

        saved_test = MaterialQualityTest.query.filter_by(material_id=mat.id).first()
        self.assertIsNotNone(saved_test)
        self.assertEqual(saved_test.status, 'PASS')
        self.assertEqual(saved_test.verified_by, 'test_officer')

        # 3. Officer records project delay record
        resp_delay = self.client.post('/contractors/delays/new', data={
            'project_id': self.p1.id,
            'contractor_id': self.contractor.id,
            'delay_category': 'Land / Legal',
            'delay_description': 'Land parcel compensation dispute in village Kundli.',
            'affected_days': 45,
            'official_source': 'District Collectorate Meeting Minutes',
            'responsible_authority': 'State Revenue Department',
            'corrective_action': 'Consent award signed with landowners.'
        }, follow_redirects=True)
        self.assertEqual(resp_delay.status_code, 200)

        saved_delay = ProjectDelayRecord.query.filter_by(project_id=self.p1.id).first()
        self.assertIsNotNone(saved_delay)
        self.assertEqual(saved_delay.delay_category, 'Land / Legal')
        self.assertEqual(saved_delay.affected_days, 45)

    def test_contractor_rest_apis(self):
        """Test JSON REST endpoints for contractor intelligence."""
        resp = self.client.get('/api/contractors')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertGreaterEqual(data['count'], 1)

        resp_single = self.client.get(f'/api/contractors/{self.contractor.id}')
        self.assertEqual(resp_single.status_code, 200)
        data_single = resp_single.get_json()
        self.assertEqual(data_single['status'], 'success')
        self.assertEqual(data_single['contractor']['registration_number'], 'REG-TEST-9988')

if __name__ == '__main__':
    unittest.main()
