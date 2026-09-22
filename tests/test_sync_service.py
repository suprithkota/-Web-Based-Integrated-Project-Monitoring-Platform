import unittest
from datetime import datetime, timedelta
from app import create_app
from config import TestingConfig
from database import db
from database.models import (
    User, Project, Contractor, DataSourceConfig, DataSyncLog,
    DataVersionHistory, DataConflictRecord
)
from services.sync_service import SyncService

class SyncServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Users: admin, officer, viewer
        self.admin = User(username='test_admin', email='admin@test.gov.in', role='admin', email_verified=True, status='active')
        self.admin.set_password('AdminPass123!')

        self.officer = User(username='test_officer', email='officer@test.gov.in', role='officer', email_verified=True, status='active')
        self.officer.set_password('OfficerPass123!')

        self.viewer = User(username='test_viewer', email='viewer@test.gov.in', role='viewer', email_verified=True, status='active')
        self.viewer.set_password('ViewerPass123!')

        db.session.add_all([self.admin, self.officer, self.viewer])
        db.session.commit()

        # Seed data source
        self.source = DataSourceConfig(
            source_name='CPPP Central Public Procurement Portal',
            department='Ministry of Road Transport & Highways',
            source_type='REST API',
            endpoint_url='',
            auth_method='None',
            sync_method='Polling',
            sync_frequency='1 hour',
            source_priority=1,
            connection_status='Connected',
            is_active=True
        )
        db.session.add(self.source)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, username, password):
        self.client.get('/logout')
        return self.client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    def test_normalize_incoming_project(self):
        """Test normalization handles heterogeneous schema keys and formats."""
        raw_payload = {
            'tender_id': 'PRJ-SYNC-01',
            'projectTitle': 'Greenfield Expressway Section 4',
            'dept': 'NHAI',
            'contractValue': '₹ 2,450.50 Cr',
            'amountSpent': '1,200.0 Cr',
            'progress_percent': '45.8%',
            'plannedProgress': '60.0%',
            'daysDelayed': '90',
            'status': 'Delayed',
            'contractor': 'Dilip Buildcon Limited',
            'contractor_reg': 'CIN-L45201MP2006PLC018689'
        }

        normalized = SyncService.normalize_incoming_project(raw_payload, 'CPPP Portal')
        self.assertEqual(normalized['project_code'], 'PRJ-SYNC-01')
        self.assertEqual(normalized['project_name'], 'Greenfield Expressway Section 4')
        self.assertEqual(normalized['approved_cost'], 2450.50)
        self.assertEqual(normalized['expenditure'], 1200.0)
        self.assertEqual(normalized['physical_progress'], 45.8)
        self.assertEqual(normalized['planned_progress'], 60.0)
        self.assertEqual(normalized['delay_days'], 90)
        self.assertEqual(normalized['contractor_registration'], 'CIN-L45201MP2006PLC018689')

    def test_exact_contractor_matching_rule(self):
        """Requirement 7: Matching contractor strictly by registration number without fuzzy merging."""
        # 1. Create a contractor with exact registration
        c1 = Contractor(
            name='Alpha Infra Projects Pvt Ltd',
            contractor_code='CON-ALPHA',
            registration_number='CIN-ALPHA-12345',
            company_type='Private Limited'
        )
        db.session.add(c1)
        db.session.commit()

        # Exact reg number match
        matched = SyncService.match_or_create_contractor('Alpha Infra Ltd', 'CIN-ALPHA-12345')
        self.assertEqual(matched.id, c1.id)

        # Different reg number must NOT merge even if name is similar
        different = SyncService.match_or_create_contractor('Alpha Infra Projects', 'CIN-ALPHA-DIFF-999')
        self.assertNotEqual(different.id, c1.id)
        self.assertEqual(different.registration_number, 'CIN-ALPHA-DIFF-999')

    def test_process_normalized_project_and_versioning(self):
        """Test initial insertion and subsequent versioning audit logging."""
        norm_data = {
            'project_code': 'PRJ-NORM-01',
            'project_name': 'Bypass Road Phase 1',
            'approved_cost': 500.0,
            'expenditure': 200.0,
            'physical_progress': 40.0,
            'planned_progress': 40.0,
            'delay_days': 0,
            'project_status': 'Ongoing'
        }

        # 1. Initial Insertion
        outcome, msg = SyncService.process_normalized_project(norm_data, self.source)
        self.assertEqual(outcome, 'inserted')

        proj = Project.query.filter_by(project_code='PRJ-NORM-01').first()
        self.assertIsNotNone(proj)
        self.assertEqual(proj.approved_cost, 500.0)

        # 2. Update with same source creates DataVersionHistory
        update_data = dict(norm_data)
        update_data['physical_progress'] = 55.0
        outcome2, msg2 = SyncService.process_normalized_project(update_data, self.source)
        self.assertEqual(outcome2, 'updated')

        db.session.refresh(proj)
        self.assertEqual(proj.physical_progress, 55.0)

        # Check version history entry
        v = DataVersionHistory.query.filter_by(entity_id=proj.id, field_name='physical_progress').first()
        self.assertIsNotNone(v)
        self.assertEqual(v.previous_value, '40.0')
        self.assertEqual(v.new_value, '55.0')

    def test_conflict_detection_and_resolution_workflow(self):
        """Test conflict detection when a secondary official source reports differing values."""
        # 1. Ingest base project from Source A (CPPP)
        norm_data = {
            'project_code': 'PRJ-CONF-01',
            'project_name': 'Interstate Highway Corridor',
            'approved_cost': 1200.0,
            'expenditure': 600.0,
            'physical_progress': 50.0,
            'delay_days': 10,
            'project_status': 'Ongoing'
        }
        SyncService.process_normalized_project(norm_data, self.source)

        # 2. Register Source B (State PWD)
        source_b = DataSourceConfig(
            source_name='State PWD E-Procurement Portal',
            department='State PWD',
            is_active=True
        )
        db.session.add(source_b)
        db.session.commit()

        # 3. Source B sends conflicting progress: 42.0% instead of 50.0%
        conflict_data = dict(norm_data)
        conflict_data['physical_progress'] = 42.0

        outcome, msg = SyncService.process_normalized_project(conflict_data, source_b)
        self.assertEqual(outcome, 'conflict')

        proj = Project.query.filter_by(project_code='PRJ-CONF-01').first()
        self.assertEqual(proj.verification_status, 'Conflicting data')

        # Verify DataConflictRecord was created
        conf = DataConflictRecord.query.filter_by(entity_id=proj.id, field_name='physical_progress').first()
        self.assertIsNotNone(conf)
        self.assertEqual(conf.status, 'Unresolved')
        self.assertEqual(conf.source_a_value, '50.0')
        self.assertEqual(conf.source_b_value, '42.0')

        # 4. Officer resolves the conflict via Conflict Resolution Center route
        self.login('test_officer', 'OfficerPass123!')
        res_resp = self.client.post(f'/admin/data-conflicts/{conf.id}/resolve', data={
            'resolution_choice': 'source_b',
            'resolution_notes': 'Verified through on-site drone survey'
        }, follow_redirects=True)
        self.assertEqual(res_resp.status_code, 200)

        db.session.refresh(conf)
        self.assertEqual(conf.status, 'Resolved')
        self.assertEqual(conf.resolved_value, '42.0')
        self.assertEqual(conf.resolved_by, 'test_officer')

        db.session.refresh(proj)
        self.assertEqual(proj.physical_progress, 42.0)
        self.assertEqual(proj.verification_status, 'Verified')

    def test_sync_execution_and_audit_logging(self):
        """Test full sync execution cycle and DataSyncLog entry generation."""
        res = SyncService.sync_source(self.source.id)
        self.assertEqual(res['status'], 'SUCCESS')
        self.assertGreater(res['records_received'], 0)

        # Check sync log
        log = DataSyncLog.query.filter_by(source_id=self.source.id).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SUCCESS')
        self.assertGreater(log.records_received, 0)

if __name__ == '__main__':
    unittest.main()
