import unittest
import sys
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from app import create_app
from database import db
from database.models import User
from services.email_service import get_latest_dev_email

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            
            # 1. Active verified officer
            u = User(
                username='testofficer',
                email='officer@test.com',
                role='officer',
                full_name='Test Officer',
                email_verified=True,
                status='active'
            )
            u.set_password('Secure@123')
            db.session.add(u)

            # 2. System Administrator
            admin = User(
                username='admin',
                email='admin@test.com',
                role='admin',
                full_name='System Admin',
                email_verified=True,
                status='active'
            )
            admin.set_password('Admin@2026!')
            db.session.add(admin)

            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_login_success(self):
        res = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome back, Test Officer', res.data)

    def test_login_invalid_password(self):
        res = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'WrongPassword@99'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Invalid username or password', res.data)

    def test_login_unverified_account_rejected(self):
        with self.app.app_context():
            unverified = User(
                username='unverifieduser',
                email='unverified@test.com',
                role='viewer',
                full_name='Unverified User',
                organization='Testing Dept',
                email_verified=False,
                status='pending_verification'
            )
            unverified.set_password('Secure@123')
            db.session.add(unverified)
            db.session.commit()

        res = self.client.post('/login', data={
            'username': 'unverifieduser',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Your email address is unverified', res.data)

    def test_login_pending_approval_rejected(self):
        with self.app.app_context():
            pending = User(
                username='waitingofficer',
                email='waiting@test.com',
                role='officer',
                full_name='Waiting Officer',
                organization='NHAI',
                email_verified=True,
                status='pending_approval'
            )
            pending.set_password('Secure@123')
            db.session.add(pending)
            db.session.commit()

        res = self.client.post('/login', data={
            'username': 'waitingofficer',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'pending administrator approval', res.data)

    def test_login_lockout_after_5_failed_attempts(self):
        for i in range(5):
            res = self.client.post('/login', data={
                'username': 'testofficer',
                'password': 'WrongPassword@99'
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)

        # 6th attempt should be locked out
        res = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Account is temporarily locked', res.data)

    def test_unauthorized_access_redirects_to_login(self):
        res = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

    def test_register_password_strength_validation(self):
        # Case 1: Too short (< 8 chars)
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'shortpassuser',
            'email': 'short@gov.in',
            'password': 'Aa1!',
            'confirm_password': 'Aa1!',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must be at least 8 characters long', res.data)

        # Case 2: Missing alphabet
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'noalphapass',
            'email': 'noalpha@gov.in',
            'password': '12345678!@#',
            'confirm_password': '12345678!@#',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must contain at least one alphabetic character', res.data)

        # Case 3: Missing number
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'nonumpass',
            'email': 'nonum@gov.in',
            'password': 'Password!@#',
            'confirm_password': 'Password!@#',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must contain at least one numeric character', res.data)

        # Case 4: Missing special symbol
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'nosymbolpass',
            'email': 'nosymbol@gov.in',
            'password': 'Password1234',
            'confirm_password': 'Password1234',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must contain at least one special symbol', res.data)

        # Case 5: Missing capital letter
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'nocappass',
            'email': 'nocap@gov.in',
            'password': 'password123!',
            'confirm_password': 'password123!',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must contain at least one capital letter', res.data)

        # Case 6: Missing small letter
        res = self.client.post('/register', data={
            'full_name': 'Test User',
            'organization': 'NHAI',
            'username': 'nosmallpass',
            'email': 'nosmall@gov.in',
            'password': 'PASSWORD123!',
            'confirm_password': 'PASSWORD123!',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Password must contain at least one small letter', res.data)

    def test_register_password_mismatch(self):
        res = self.client.post('/register', data={
            'full_name': 'Mismatch User',
            'organization': 'NHAI',
            'username': 'mismatchuser',
            'email': 'mismatch@gov.in',
            'password': 'Secure@123',
            'confirm_password': 'Different@123',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Passwords do not match', res.data)

    def test_register_admin_rejected(self):
        res = self.client.post('/register', data={
            'full_name': 'Rogue Admin',
            'organization': 'Ministry of Finance',
            'username': 'rogueadmin',
            'email': 'admin@rogue.gov.in',
            'password': 'Secure@123',
            'confirm_password': 'Secure@123',
            'role': 'admin'
        }, follow_redirects=True)
        self.assertIn(b'Administrator accounts cannot be created via public registration', res.data)

    def test_register_duplicate_username(self):
        res = self.client.post('/register', data={
            'full_name': 'Duplicate User',
            'organization': 'Ministry of Power',
            'username': 'TestOfficer',  # Case-insensitive duplicate
            'email': 'different@gov.in',
            'password': 'Secure@123',
            'confirm_password': 'Secure@123',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertIn(b'Username already exists', res.data)

    def test_register_and_verify_viewer_flow(self):
        # Register viewer
        res = self.client.post('/register', data={
            'full_name': 'Observer User',
            'organization': 'Citizen Advisory Council',
            'username': 'observer_one',
            'email': 'observer@domain.com',
            'password': 'Observer@2026',
            'confirm_password': 'Observer@2026',
            'role': 'viewer'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Account created. Please check your email to verify your account', res.data)

        # Retrieve user and verification token
        with self.app.app_context():
            u = User.query.filter_by(username='observer_one').first()
            self.assertIsNotNone(u)
            self.assertFalse(u.email_verified)
            self.assertEqual(u.status, 'pending_verification')
            token = u.verification_token
            self.assertIsNotNone(token)

        # Verify email via token
        res_verify = self.client.get(f'/verify-email/{token}', follow_redirects=True)
        self.assertEqual(res_verify.status_code, 200)
        self.assertIn(b'Email Verified Successfully', res_verify.data)

        # Viewer status should now be active
        with self.app.app_context():
            u = User.query.filter_by(username='observer_one').first()
            self.assertTrue(u.email_verified)
            self.assertEqual(u.status, 'active')
            self.assertIsNone(u.verification_token)  # Single-use

        # Viewer can now login
        res_login = self.client.post('/login', data={
            'username': 'observer_one',
            'password': 'Observer@2026'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Observer User', res_login.data)

    def test_register_and_officer_approval_flow(self):
        # 1. Register Officer
        res = self.client.post('/register', data={
            'full_name': 'Project Officer',
            'username': 'project_off1',
            'email': 'officer1@infra.gov.in',
            'password': 'Project@2026',
            'confirm_password': 'Project@2026',
            'role': 'officer',
            'organization': 'NHAI'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # 2. Verify Officer's Email
        with self.app.app_context():
            u = User.query.filter_by(username='project_off1').first()
            token = u.verification_token

        res_verify = self.client.get(f'/verify-email/{token}', follow_redirects=True)
        self.assertIn(b'Awaiting Admin Approval', res_verify.data)

        # 3. Officer cannot login yet
        res_fail = self.client.post('/login', data={
            'username': 'project_off1',
            'password': 'Project@2026'
        }, follow_redirects=True)
        self.assertIn(b'pending administrator approval', res_fail.data)

        # 4. Admin logs in and approves the officer
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'Admin@2026!'}, follow_redirects=True)
            with self.app.app_context():
                officer_id = User.query.filter_by(username='project_off1').first().id
            res_approve = self.client.post(f'/admin/users/{officer_id}/approve', follow_redirects=True)
            self.assertIn(b'approved and activated', res_approve.data)
            self.client.get('/logout')

        # 5. Officer can now login
        res_success = self.client.post('/login', data={
            'username': 'project_off1',
            'password': 'Project@2026'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Project Officer', res_success.data)

    def test_forgot_password_and_reset_flow(self):
        # 1. Request password reset
        res = self.client.post('/forgot-password', data={'email': 'officer@test.com'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'password reset link has been dispatched', res.data)

        # 2. Retrieve reset token
        with self.app.app_context():
            u = User.query.filter_by(email='officer@test.com').first()
            reset_token = u.reset_token
            self.assertIsNotNone(reset_token)

        # 3. Perform reset with new password
        res_reset = self.client.post(f'/reset-password/{reset_token}', data={
            'password': 'NewPassword@2026',
            'confirm_password': 'NewPassword@2026'
        }, follow_redirects=True)
        self.assertEqual(res_reset.status_code, 200)
        self.assertIn(b'Your password has been successfully updated', res_reset.data)

        # 4. Old password fails
        res_old = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertIn(b'Invalid username or password', res_old.data)

        # 5. New password succeeds
        res_new = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'NewPassword@2026'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Test Officer', res_new.data)

        # Sign out before testing reset token reuse
        self.client.get('/logout')

        # 6. Reset token cannot be reused
        res_reuse = self.client.get(f'/reset-password/{reset_token}', follow_redirects=True)
        self.assertIn(b'This password reset link is invalid', res_reuse.data)

    def test_admin_create_user_direct_activation(self):
        """Test that an administrator can directly provision an active user."""
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'Admin@2026!'}, follow_redirects=True)

            res = self.client.post('/admin/users/create', data={
                'full_name': 'Direct Provisioned Officer',
                'username': 'direct_officer',
                'email': 'direct_officer@infra.gov.in',
                'organization': 'MoRTH',
                'department': 'Highways',
                'role': 'officer',
                'password': 'DirectPassword@2026',
                'confirm_password': 'DirectPassword@2026',
                'is_active': '1'
            }, follow_redirects=True)

            self.assertEqual(res.status_code, 200)
            self.assertIn(b'created successfully', res.data)

            with self.app.app_context():
                u = User.query.filter_by(username='direct_officer').first()
                self.assertIsNotNone(u)
                self.assertTrue(u.email_verified)
                self.assertEqual(u.status, 'active')

            self.client.get('/logout')

        # Direct provisioned officer can immediately log in without extra verification
        res_login = self.client.post('/login', data={
            'username': 'direct_officer',
            'password': 'DirectPassword@2026'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Direct Provisioned Officer', res_login.data)

    def test_non_admin_cannot_access_admin_user_creation(self):
        """Test that non-administrators are blocked from creating users via admin endpoint."""
        with self.client:
            self.client.post('/login', data={'username': 'testofficer', 'password': 'Secure@123'}, follow_redirects=True)
            res = self.client.post('/admin/users/create', data={
                'full_name': 'Unauthorized User',
                'username': 'unauth_user',
                'email': 'unauth@test.com',
                'role': 'admin',
                'password': 'Password@2026',
                'confirm_password': 'Password@2026'
            })
            self.assertEqual(res.status_code, 403)

    def test_password_reset_via_sms_flow(self):
        """Test the end-to-end flow of resetting a password using a 6-digit SMS verification code."""
        # 1. Ensure user has a phone number set
        with self.app.app_context():
            u = User.query.filter_by(username='testofficer').first()
            u.phone_number = '+91 98765 43211'
            db.session.commit()

        # 2. Request SMS verification code
        res_send = self.client.post('/reset-password-sms', data={
            'action': 'send_code',
            'identifier': 'testofficer'
        }, follow_redirects=True)
        self.assertEqual(res_send.status_code, 200)
        self.assertIn(b'verification code has been dispatched', res_send.data)

        # 3. Retrieve generated SMS code from user model
        with self.app.app_context():
            u = User.query.filter_by(username='testofficer').first()
            self.assertIsNotNone(u.sms_code)
            sms_code = u.sms_code

        # 4. Verify code and update password with compliant strong password
        res_verify = self.client.post('/reset-password-sms', data={
            'action': 'verify_update',
            'identifier': 'testofficer',
            'sms_code': sms_code,
            'new_password': 'UpdatedSMSPass@2026',
            'confirm_password': 'UpdatedSMSPass@2026'
        }, follow_redirects=True)
        self.assertEqual(res_verify.status_code, 200)
        self.assertIn(b'Your password has been successfully updated via SMS', res_verify.data)

        # 5. Old password no longer works
        res_old = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'Secure@123'
        }, follow_redirects=True)
        self.assertIn(b'Invalid username or password', res_old.data)

        # 6. New password works
        res_new = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'UpdatedSMSPass@2026'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Test Officer', res_new.data)

    def test_password_reset_via_sms_invalid_code(self):
        """Test that an incorrect SMS verification code is rejected."""
        with self.app.app_context():
            u = User.query.filter_by(username='testofficer').first()
            u.phone_number = '+91 98765 43211'
            u.generate_sms_code()
            db.session.commit()

        res = self.client.post('/reset-password-sms', data={
            'action': 'verify_update',
            'identifier': 'testofficer',
            'sms_code': '000000',  # Wrong code
            'new_password': 'UpdatedSMSPass@2026',
            'confirm_password': 'UpdatedSMSPass@2026'
        }, follow_redirects=True)
        self.assertIn(b'Invalid SMS verification code', res.data)

    def test_change_password_with_sms_code_flow(self):
        """Test changing password while authenticated using an SMS verification code."""
        with self.client:
            # Login as testofficer
            self.client.post('/login', data={'username': 'testofficer', 'password': 'Secure@123'}, follow_redirects=True)

            # Request SMS code via API
            res_api = self.client.post('/api/auth/send-change-password-code', json={'phone_number': '+91 98765 43211'})
            self.assertEqual(res_api.status_code, 200)
            data = res_api.get_json()
            self.assertTrue(data['success'])
            sms_code = data['dev_code']

            # Change password using the SMS verification code
            res_change = self.client.post('/change-password', data={
                'auth_method': 'sms_code',
                'sms_code': sms_code,
                'new_password': 'NewAuthCode@2026!',
                'confirm_password': 'NewAuthCode@2026!'
            }, follow_redirects=True)
            self.assertEqual(res_change.status_code, 200)
            self.assertIn(b'Your password has been successfully updated', res_change.data)

            # Logout
            self.client.get('/logout')

        # Verify login with new password
        res_login = self.client.post('/login', data={
            'username': 'testofficer',
            'password': 'NewAuthCode@2026!'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Test Officer', res_login.data)

if __name__ == '__main__':
    unittest.main()
