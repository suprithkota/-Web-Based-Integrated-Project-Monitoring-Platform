import unittest
import json
from app import create_app
from config import TestingConfig
from database import db
from database.models import User, Project, Alert, ProjectAssignment
from services.risk_service import update_project_risk, calculate_project_risk_dna

class RBACObjectAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Create 3 distinct users with active & verified status
        self.admin = User(
            username='test_admin',
            email='admin@test.gov.in',
            role='admin',
            email_verified=True,
            status='active'
        )
        self.admin.set_password('AdminPass123!')

        self.officer = User(
            username='test_officer',
            email='officer@test.gov.in',
            role='officer',
            email_verified=True,
            status='active'
        )
        self.officer.set_password('OfficerPass123!')

        self.viewer = User(
            username='test_viewer',
            email='viewer@test.gov.in',
            role='viewer',
            email_verified=True,
            status='active'
        )
        self.viewer.set_password('ViewerPass123!')

        db.session.add_all([self.admin, self.officer, self.viewer])
        db.session.commit()

        # Create two projects:
        # Project 1: Assigned to officer
        # Project 2: UNASSIGNED to officer (to test object-level authorization denial)
        self.proj_assigned = Project(
            project_code='PRJ-AUTH-001',
            project_name='Assigned Metro Extension',
            ministry='Ministry of Housing and Urban Affairs',
            sector='Urban Transport',
            state='Delhi',
            approved_cost=1500.0,
            revised_cost=1650.0,
            expenditure=700.0,
            physical_progress=45.0,
            planned_progress=55.0,
            delay_days=45,
            milestones_total=5,
            milestones_completed=2,
            milestones_delayed=1,
            contractor_status='Minor Delay',
            land_acquisition_status='In Progress',
            environmental_clearance_status='Completed'
        )
        self.proj_unassigned = Project(
            project_code='PRJ-UNAUTH-002',
            project_name='Unassigned Coastal Expressway',
            ministry='Ministry of Road Transport and Highways',
            sector='Road Transport',
            state='Maharashtra',
            approved_cost=4500.0,
            revised_cost=5200.0,
            expenditure=2100.0,
            physical_progress=30.0,
            planned_progress=60.0,
            delay_days=120,
            milestones_total=6,
            milestones_completed=1,
            milestones_delayed=3,
            contractor_status='Delayed',
            land_acquisition_status='Delayed',
            environmental_clearance_status='Delayed'
        )
        db.session.add_all([self.proj_assigned, self.proj_unassigned])
        db.session.commit()

        update_project_risk(self.proj_assigned)
        update_project_risk(self.proj_unassigned)

        # Assign ONLY proj_assigned to officer
        self.assignment = ProjectAssignment(
            user_id=self.officer.id,
            project_id=self.proj_assigned.id,
            can_edit=True,
            role_scope='Monitoring Officer'
        )
        db.session.add(self.assignment)

        # Create alerts for both projects
        self.alert_assigned = Alert(
            project_id=self.proj_assigned.id,
            severity='MEDIUM',
            title='Progress Lag Alert',
            description='10% progress lag detected',
            trigger='10% progress lag',
            status='Open'
        )
        self.alert_unassigned = Alert(
            project_id=self.proj_unassigned.id,
            severity='CRITICAL',
            title='Schedule Overrun Alert',
            description='120 days schedule delay detected',
            trigger='120 days schedule delay',
            status='Open'
        )
        db.session.add_all([self.alert_assigned, self.alert_unassigned])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login_as(self, user, password):
        return self.client.post('/login', data={
            'username': user.username,
            'password': password
        }, follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. VIEWER TESTS: READ-ONLY ENFORCEMENT & STRICT PROHIBITIONS
    # -------------------------------------------------------------------------
    def test_viewer_read_only_access(self):
        self.login_as(self.viewer, 'ViewerPass123!')
        
        # Can view dashboard
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 200)

        # Can view projects registry
        res = self.client.get('/projects')
        self.assertEqual(res.status_code, 200)

        # Can view project detail
        res = self.client.get(f'/projects/{self.proj_assigned.id}')
        self.assertEqual(res.status_code, 200)

        # Can access read API
        res = self.client.get('/api/projects')
        self.assertEqual(res.status_code, 200)

    def test_viewer_blocked_from_admin_urls(self):
        self.login_as(self.viewer, 'ViewerPass123!')

        # Direct access to admin URLs must return 403 Forbidden
        for path in ['/admin', '/admin/users', '/admin/audit-logs', '/admin/settings']:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 403, f"Viewer accessed {path} without 403!")

    def test_viewer_blocked_from_project_mutations(self):
        self.login_as(self.viewer, 'ViewerPass123!')

        # POST /api/projects -> 403
        res = self.client.post('/api/projects', json={
            'project_code': 'PRJ-FAIL',
            'project_name': 'Unauthorized Creation'
        })
        self.assertEqual(res.status_code, 403)

        # PUT /api/projects/<id> -> 403
        res = self.client.put(f'/api/projects/{self.proj_assigned.id}', json={
            'project_name': 'Tampered'
        })
        self.assertEqual(res.status_code, 403)

        # DELETE /api/projects/<id> -> 403
        res = self.client.delete(f'/api/projects/{self.proj_assigned.id}')
        self.assertEqual(res.status_code, 403)

        # POST /projects/<id>/delete -> 403
        res = self.client.post(f'/projects/{self.proj_assigned.id}/delete')
        self.assertEqual(res.status_code, 403)

    def test_viewer_blocked_from_import_and_export(self):
        self.login_as(self.viewer, 'ViewerPass123!')

        # POST /api/import -> 403
        res = self.client.post('/api/import')
        self.assertEqual(res.status_code, 403)

        # GET /projects/export -> 403 (unauthorized export rejected)
        res = self.client.get('/projects/export')
        self.assertEqual(res.status_code, 403)

    def test_viewer_blocked_from_alert_modifications(self):
        self.login_as(self.viewer, 'ViewerPass123!')

        # POST /api/alerts/<id>/resolve -> 403
        res = self.client.post(f'/api/alerts/{self.alert_assigned.id}/resolve', json={'notes': 'Done'})
        self.assertEqual(res.status_code, 403)

        # POST /alerts/<id>/status -> 403
        res = self.client.post(f'/alerts/{self.alert_assigned.id}/status', data={'status': 'Resolved'})
        self.assertEqual(res.status_code, 403)

    # -------------------------------------------------------------------------
    # 2. OFFICER TESTS: OBJECT-LEVEL AUTHORIZATION & PRIVILEGE BOUNDARIES
    # -------------------------------------------------------------------------
    def test_officer_assigned_project_access_allowed(self):
        self.login_as(self.officer, 'OfficerPass123!')

        # Officer can view assigned project detail (HTTP 200)
        res = self.client.get(f'/projects/{self.proj_assigned.id}')
        self.assertEqual(res.status_code, 200)

        # Officer can access assigned project API (HTTP 200)
        res = self.client.get(f'/api/projects/{self.proj_assigned.id}')
        self.assertEqual(res.status_code, 200)

        # Officer can update assigned project via API
        res = self.client.put(f'/api/projects/{self.proj_assigned.id}', json={
            'physical_progress': 50.0
        })
        self.assertEqual(res.status_code, 200)

        # Officer can resolve alert on assigned project
        res = self.client.post(f'/api/alerts/{self.alert_assigned.id}/resolve', json={'notes': 'Reviewed'})
        self.assertEqual(res.status_code, 200)

    def test_officer_unassigned_project_access_denied_object_level(self):
        self.login_as(self.officer, 'OfficerPass123!')

        # Officer attempting to view unassigned project -> 403 Forbidden!
        res = self.client.get(f'/projects/{self.proj_unassigned.id}')
        self.assertEqual(res.status_code, 403, "Officer accessed unassigned project HTML without 403!")

        # Officer attempting to view unassigned project API -> 403 Forbidden!
        res = self.client.get(f'/api/projects/{self.proj_unassigned.id}')
        self.assertEqual(res.status_code, 403, "Officer accessed unassigned project API without 403!")

        # Officer attempting to update unassigned project API -> 403 Forbidden!
        res = self.client.put(f'/api/projects/{self.proj_unassigned.id}', json={
            'physical_progress': 99.0
        })
        self.assertEqual(res.status_code, 403, "Officer updated unassigned project without 403!")

        # Officer attempting to resolve alert for unassigned project -> 403 Forbidden!
        res = self.client.post(f'/api/alerts/{self.alert_unassigned.id}/resolve', json={'notes': 'Hacked'})
        self.assertEqual(res.status_code, 403, "Officer resolved alert for unassigned project without 403!")

    def test_officer_blocked_from_admin_functions(self):
        self.login_as(self.officer, 'OfficerPass123!')

        # User management -> 403
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 403)

        # Audit logs -> 403
        res = self.client.get('/admin/audit-logs')
        self.assertEqual(res.status_code, 403)

        # System settings -> 403
        res = self.client.get('/admin/settings')
        self.assertEqual(res.status_code, 403)

        # Officer cannot delete projects -> 403
        res = self.client.delete(f'/api/projects/{self.proj_assigned.id}')
        self.assertEqual(res.status_code, 403)

        res = self.client.post(f'/projects/{self.proj_assigned.id}/delete')
        self.assertEqual(res.status_code, 403)

    # -------------------------------------------------------------------------
    # 3. ADMINISTRATOR TESTS: FULL OVERSIGHT
    # -------------------------------------------------------------------------
    def test_admin_universal_access(self):
        self.login_as(self.admin, 'AdminPass123!')

        # Admin can access user management
        res = self.client.get('/admin/users')
        self.assertEqual(res.status_code, 200)

        # Admin can access audit logs
        res = self.client.get('/admin/audit-logs')
        self.assertEqual(res.status_code, 200)

        # Admin can access system settings
        res = self.client.get('/admin/settings')
        self.assertEqual(res.status_code, 200)

        # Admin can view both assigned and unassigned projects
        res1 = self.client.get(f'/projects/{self.proj_assigned.id}')
        self.assertEqual(res1.status_code, 200)
        res2 = self.client.get(f'/projects/{self.proj_unassigned.id}')
        self.assertEqual(res2.status_code, 200)

        # Admin can delete a project
        res = self.client.delete(f'/api/projects/{self.proj_unassigned.id}')
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------------------
    # 4. UNAUTHENTICATED PROTECTION
    # -------------------------------------------------------------------------
    def test_unauthenticated_requests(self):
        # HTML dashboard requires auth -> redirects to login
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

        # API endpoint requires auth -> returns 401
        res = self.client.get('/api/projects')
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------------------
    # 5. DETERMINISTIC PROJECT RISK DNA
    # -------------------------------------------------------------------------
    def test_project_risk_dna_calculation(self):
        dna = calculate_project_risk_dna(self.proj_assigned)
        self.assertIn('dimensions', dna)
        self.assertEqual(len(dna['dimensions']), 8)
        
        dim_names = [d['name'] for d in dna['dimensions']]
        expected_dims = ['Schedule', 'Cost', 'Progress', 'Milestones', 'Land', 'Environment', 'Contractor', 'Financial']
        for ed in expected_dims:
            self.assertIn(ed, dim_names)

        # Every score must be bounded between 0 and 100
        for dim in dna['dimensions']:
            self.assertGreaterEqual(dim['score'], 0.0)
            self.assertLessEqual(dim['score'], 100.0)

if __name__ == '__main__':
    unittest.main()
