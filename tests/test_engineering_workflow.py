import unittest
from datetime import datetime, date
from app import create_app
from config import TestingConfig
from database import db
from database.models import (
    User, Project, Contractor, MaterialSupplier,
    ProjectMaterial, MaterialQualityTest, ProjectDelayRecord,
    SiteInspectionRecord, PublicComplaint, DataSourceConfig
)

class EngineeringWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Create test users: admin, officer (EE/AE), and viewer
        self.admin = User(
            username='test_admin',
            email='admin@eng.gov.in',
            role='admin',
            email_verified=True,
            status='active',
            technical_designation='Superintending Engineer'
        )
        self.admin.set_password('AdminPass123!')

        self.officer = User(
            username='test_officer',
            email='officer@eng.gov.in',
            role='officer',
            email_verified=True,
            status='active',
            technical_designation='Assistant Engineer'
        )
        self.officer.set_password('OfficerPass123!')

        self.viewer = User(
            username='test_viewer',
            email='viewer@eng.gov.in',
            role='viewer',
            email_verified=True,
            status='active'
        )
        self.viewer.set_password('ViewerPass123!')

        db.session.add_all([self.admin, self.officer, self.viewer])
        db.session.commit()

        # Seed contractor
        self.contractor = Contractor(
            name='National Infrastructure Corp',
            contractor_code='CON-ENG-01',
            registration_number='REG-ENG-101',
            contractor_license_number='LIC-ENG-500',
            company_type='Public Limited',
            contractor_class='Class-1',
            headquarters='New Delhi',
            year_established=2015,
            years_of_experience=10,
            verification_status='Verified',
            registration_status='Active'
        )
        db.session.add(self.contractor)
        db.session.commit()

        # Seed project
        self.project = Project(
            project_code='PRJ-ENG-100',
            project_name='NH-44 Expressway Bypass',
            ministry='Ministry of Road Transport & Highways',
            department='National Highways Authority of India',
            sector='Roads & Highways',
            state='Haryana',
            location='Panipat Bypass',
            approved_cost=250.0,
            revised_cost=250.0,
            original_budget=250.0,
            expenditure=100.0,
            start_date=date(2025, 1, 1),
            original_completion_date=date(2027, 12, 31),
            project_status='Ongoing',
            risk_level='LOW',
            physical_progress=35.0,
            contractor_id=self.contractor.id,
            data_source='MoRTH PMIS',
            verification_status='Verified'
        )
        db.session.add(self.project)
        db.session.commit()

        # Seed material supplier and batch
        self.supplier = MaterialSupplier(
            name='UltraTech Cement Ltd',
            category='Cement & Concrete',
            registration_number='SUP-ENG-01',
            state='Maharashtra',
            city='Mumbai',
            verification_status='Verified'
        )
        db.session.add(self.supplier)
        db.session.commit()

        self.material = ProjectMaterial(
            project_id=self.project.id,
            supplier_id=self.supplier.id,
            material_name='OPC 53 Grade Cement',
            material_category='Cement',
            batch_number='BATCH-CEM-2026-X1',
            quantity=500.0,
            unit='Metric Tons',
            required_specification='IS 269:2015',
            actual_specification='IS 269:2015 Compliant',
            approval_status='Approved',
            quality_certification_status='Pending Test'
        )
        db.session.add(self.material)
        db.session.commit()

        # Seed citizen complaint
        self.complaint = PublicComplaint(
            complaint_code='CMP-2026-ENG-01',
            project_id=self.project.id,
            complainant_name='Suresh Kumar',
            complainant_contact='+91 9876543210',
            location='KM 42+500 Left Carriage',
            category='Structural Crack',
            description='Visible longitudinal cracks observed on pier cap after flyover formwork removal.',
            status='Submitted',
            gps_lat=28.6139,
            gps_lng=77.2090
        )
        db.session.add(self.complaint)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, username, password):
        self.client.get('/logout')
        return self.client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    def test_rbac_engineering_dashboard_access(self):
        """Test viewer is forbidden (403) from engineering routes; officer and admin are allowed."""
        # Viewer access -> 403
        self.login('test_viewer', 'ViewerPass123!')
        res_viewer = self.client.get('/engineering-dashboard')
        self.assertEqual(res_viewer.status_code, 403)

        res_viewer_insp = self.client.get('/engineering/inspection/new')
        self.assertEqual(res_viewer_insp.status_code, 403)

        # Officer access -> 200
        self.login('test_officer', 'OfficerPass123!')
        res_officer = self.client.get('/engineering-dashboard')
        self.assertEqual(res_officer.status_code, 200)
        self.assertIn(b'Technical Operations', res_officer.data)

        # Admin access -> 200
        self.login('test_admin', 'AdminPass123!')
        res_admin = self.client.get('/engineering-dashboard')
        self.assertEqual(res_admin.status_code, 200)

    def test_site_inspection_logging_and_progress_update(self):
        """Test site inspection submission by Field Engineer, verify stage & progress updates."""
        self.login('test_officer', 'OfficerPass123!')

        post_data = {
            'project_id': self.project.id,
            'stage_inspected': 'Pier Cap Concreting & Curing',
            'work_completed_percentage': 42.5,
            'measurements_recorded': 'Pier P3: Height 8.2m, Cross-section 1.8m x 1.8m. Rebar spacing 150mm c/c verified against drawing NH44-STR-04.',
            'gps_latitude': 28.6140,
            'gps_longitude': 77.2095,
            'inspection_date': date.today().strftime('%Y-%m-%d')
        }

        res = self.client.post('/engineering/inspection/new', data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify inspection record in database
        insp = SiteInspectionRecord.query.filter_by(project_id=self.project.id).first()
        self.assertIsNotNone(insp)
        self.assertEqual(insp.stage_inspected, 'Pier Cap Concreting & Curing')
        self.assertEqual(insp.work_completed_percentage, 42.5)
        self.assertIn('Pending EE Review', insp.verification_status)
        self.assertIn('Pier P3', insp.measurements_recorded)

        # Verify project progress was updated to 42.5%
        proj = db.session.get(Project, self.project.id)
        self.assertEqual(proj.physical_progress, 42.5)
        self.assertEqual(proj.current_construction_stage, 'Pier Cap Concreting & Curing')
        self.assertIn('inspected by test_officer', proj.latest_govt_inspection)

    def test_inspection_verification_and_certification(self):
        """Test Executive Engineer / Admin certification workflow."""
        # Create an unverified inspection
        insp = SiteInspectionRecord(
            project_id=self.project.id,
            officer_id=self.officer.id,
            officer_name='test_officer',
            officer_designation='Assistant Engineer',
            inspection_date=date.today(),
            stage_inspected='Subgrade Compaction',
            work_completed_percentage=38.0,
            measurements_recorded='Field density test achieved 98.4% MDD.',
            verification_status='Pending EE Review'
        )
        db.session.add(insp)
        db.session.commit()

        # EE / Admin logs in and certifies
        self.login('test_admin', 'AdminPass123!')
        res_verify = self.client.post(f'/engineering/inspection/{insp.id}/verify', data={
            'action': 'verify',
            'review_remarks': 'MDD test reports verified against MORTH Section 300 specifications. Certified satisfactory.'
        }, follow_redirects=True)
        self.assertEqual(res_verify.status_code, 200)

        db.session.refresh(insp)
        self.assertIn('Certified by Superintending Engineer', insp.verification_status)
        self.assertIn('test_admin', insp.reviewed_by)
        self.assertIn('MORTH Section 300', insp.review_remarks)

    def test_material_quality_lab_test_pass_and_fail(self):
        """Test logging of laboratory quality tests and status update on project materials."""
        self.login('test_officer', 'OfficerPass123!')

        # 1. PASS Test
        pass_data = {
            'project_id': self.project.id,
            'material_id': self.material.id,
            'test_name': 'IS 269:2015 28-Day Compressive Strength',
            'required_standard': 'IS 269:2015 (Min 53 MPa)',
            'test_result_value': '57.4 MPa',
            'status': 'PASS',
            'testing_laboratory': 'NABL Accredited National Testing Laboratory',
            'quality_certificate_ref': 'LAB-CERT-2026-992'
        }
        res_pass = self.client.post('/engineering/quality-tests/new', data=pass_data, follow_redirects=True)
        self.assertEqual(res_pass.status_code, 200)

        mat = db.session.get(ProjectMaterial, self.material.id)
        self.assertEqual(mat.approval_status, 'Approved')
        self.assertEqual(mat.quality_certification_status, 'BIS Certified')

        # 2. FAIL Test on a second batch
        mat_fail = ProjectMaterial(
            project_id=self.project.id,
            supplier_id=self.supplier.id,
            material_name='Fe 500D TMT Rebar',
            material_category='Steel',
            batch_number='BATCH-STL-88',
            quantity=120.0,
            unit='Metric Tons',
            required_specification='IS 1786:2008 (Yield >= 500 N/mm2)',
            actual_specification='IS 1786:2008 Sub-standard',
            approval_status='Pending',
            quality_certification_status='Testing'
        )
        db.session.add(mat_fail)
        db.session.commit()

        fail_data = {
            'project_id': self.project.id,
            'material_id': mat_fail.id,
            'test_name': 'IS 1786 Tensile & Yield Strength',
            'required_standard': 'IS 1786:2008 (Yield 500 N/mm2, Elongation 16%)',
            'test_result_value': 'Yield 462 N/mm2 (FAIL - 38 N/mm2 below standard), Elongation 11.8%',
            'status': 'FAIL',
            'testing_laboratory': 'Government Quality Control Testing Lab',
            'rejection_information': 'Batch #BATCH-STL-88 failed minimum yield threshold. Rejected immediately.',
            'replacement_information': 'Contractor directed to replace entire 120 MT lot with fresh heat-numbered batch within 7 days.'
        }
        res_fail = self.client.post('/engineering/quality-tests/new', data=fail_data, follow_redirects=True)
        self.assertEqual(res_fail.status_code, 200)

        db.session.refresh(mat_fail)
        self.assertEqual(mat_fail.approval_status, 'Rejected')
        self.assertEqual(mat_fail.quality_certification_status, 'Failed Lab Test')

    def test_delay_record_logging(self):
        """Test recording project delay cause and mitigation actions."""
        self.login('test_officer', 'OfficerPass123!')

        delay_data = {
            'project_id': self.project.id,
            'contractor_id': self.contractor.id,
            'delay_category': 'Right of Way (Land Acquisition)',
            'delay_description': 'Forest clearance pending for 4.2 km section between KM 38 and KM 42.',
            'affected_days': 45,
            'official_source': 'Joint Site Inspection Minute of Meeting',
            'responsible_authority': 'State Forest & Environment Department',
            'corrective_action': 'Deputy Conservator of Forests meeting convened; fast-track stage-2 tree felling sanction issued.'
        }
        res = self.client.post('/engineering/delays/new', data=delay_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        delay_rec = ProjectDelayRecord.query.filter_by(project_id=self.project.id).first()
        self.assertIsNotNone(delay_rec)
        self.assertEqual(delay_rec.delay_category, 'Right of Way (Land Acquisition)')
        self.assertEqual(delay_rec.affected_days, 45)

        # Verify project model updated
        proj = db.session.get(Project, self.project.id)
        self.assertEqual(proj.delay_days, 45)
        self.assertEqual(proj.responsible_stakeholder, 'State Forest & Environment Department')

    def test_public_complaint_field_triage(self):
        """Test officer field triage of citizen grievance with inspection reference."""
        self.login('test_officer', 'OfficerPass123!')

        triage_data = {
            'status': 'Site Inspection Required',
            'official_response': 'Junior Engineer deputed for non-destructive rebound hammer testing on pier cap.',
            'inspection_finding_ref': 'INSP-NH44-PC-01',
            'routed_department': 'Quality & Structural Safety Wing'
        }
        res = self.client.post(f'/engineering/complaints/{self.complaint.id}/triage', data=triage_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(self.complaint)
        self.assertEqual(self.complaint.status, 'Site Inspection Required')
        self.assertEqual(self.complaint.inspection_finding_ref, 'INSP-NH44-PC-01')
        self.assertIn('test_officer', self.complaint.assigned_officer)

    def test_engineering_rest_apis(self):
        """Test engineering statistics and inspection JSON APIs."""
        self.login('test_officer', 'OfficerPass123!')

        # Dashboard stats API
        res_stats = self.client.get('/api/engineering/dashboard-stats')
        self.assertEqual(res_stats.status_code, 200)
        data_stats = res_stats.get_json()
        self.assertEqual(data_stats['status'], 'success')
        self.assertIn('total_scoped_projects', data_stats['data'])

        # Inspections API
        res_insps = self.client.get('/api/engineering/inspections')
        self.assertEqual(res_insps.status_code, 200)
        data_insps = res_insps.get_json()
        self.assertEqual(data_insps['status'], 'success')
        self.assertIsInstance(data_insps['inspections'], list)

if __name__ == '__main__':
    unittest.main()
