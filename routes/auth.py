from functools import wraps
from datetime import datetime, timedelta
import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from extensions import limiter
from database import db
from database.models import User, SecurityAuditLog, Project, ProjectAssignment
from services.auth_validator import (
    validate_password_strength,
    validate_password_confirmation,
    validate_username,
    validate_email
)
from services.email_service import (
    send_verification_email,
    send_password_reset_email
)
from services.sms_service import send_sms_code
from services.audit_service import log_security_event
from services.data_minimization_service import serialize_user_for_user

auth_bp = Blueprint('auth', __name__)

def ensure_demo_users():
    """Ensure standard baseline accounts are present, verified, and active."""
    demo_accounts = [
        {
            'username': 'admin',
            'email': 'admin@projectpulse.gov.in',
            'phone_number': '+91 98765 43210',
            'role': 'admin',
            'full_name': 'Dr. Rajesh Verma',
            'organization': 'Central Project Monitoring Group',
            'password': 'admin123'
        },
        {
            'username': 'officer',
            'email': 'officer@projectpulse.gov.in',
            'phone_number': '+91 98765 43211',
            'role': 'officer',
            'full_name': 'Priya Sharma',
            'organization': 'Infrastructure Monitoring & Review',
            'password': 'officer123'
        },
        {
            'username': 'viewer',
            'email': 'viewer@projectpulse.gov.in',
            'phone_number': '+91 98765 43212',
            'role': 'viewer',
            'full_name': 'Anil Sengupta',
            'organization': 'Public Analytics & Research',
            'password': 'viewer123'
        }
    ]
    for acc in demo_accounts:
        user = User.query.filter(
            (func.lower(User.username) == acc['username']) |
            (func.lower(User.email) == acc['email'])
        ).first()
        if not user:
            user = User(
                username=acc['username'],
                email=acc['email'],
                phone_number=acc.get('phone_number', ''),
                role=acc['role'],
                full_name=acc['full_name'],
                organization=acc['organization'],
                department=acc['organization'],
                email_verified=True,
                status='active'
            )
            user.set_password(acc['password'])
            db.session.add(user)
        else:
            user.email_verified = True
            user.status = 'active'
            if not user.phone_number:
                user.phone_number = acc.get('phone_number', '')
            if not user.password_hash:
                user.set_password(acc['password'])
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Seed initial project assignments for officer demo user if missing
    try:
        officer = User.query.filter_by(username='officer').first()
        if officer:
            from database.models import ProjectAssignment, Project
            if ProjectAssignment.query.filter_by(user_id=officer.id).count() == 0:
                projects = Project.query.order_by(Project.id.asc()).limit(3).all()
                for p in projects:
                    db.session.add(ProjectAssignment(user_id=officer.id, project_id=p.id, can_edit=True, role_scope='Monitoring Officer'))
                db.session.commit()
    except Exception:
        db.session.rollback()

# Re-export standardized RBAC and Object-level authorization decorators
from services.rbac_service import (
    role_required,
    project_access_required,
    admin_required,
    officer_required,
    viewer_allowed
)

# =========================================================================
# 1. LOGIN ROUTE
# =========================================================================
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    ensure_demo_users()

    if request.method == 'POST':
        raw_username = request.form.get('username', '').strip()
        raw_password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not raw_username or not raw_password:
            flash("Please enter both username and password.", "danger")
            return render_template('login.html', username=raw_username)

        # Look up user case-insensitively by username or email
        user = User.query.filter(
            (func.lower(User.username) == raw_username.lower()) |
            (func.lower(User.email) == raw_username.lower())
        ).first()

        if not user:
            log_security_event('LOGIN_FAILURE', username=raw_username, resource_type='auth', details='Unknown username or email', status='FAILURE')
            flash("Invalid username. Please verify your credentials.", "danger")
            return render_template('login.html', username=raw_username)

        # Check account lockout due to excessive failed attempts
        if user.is_locked:
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds()) // 60 + 1
            log_security_event('LOGIN_BLOCKED_LOCKED', user_id=user.id, username=user.username, resource_type='auth', details='Login attempt on locked account', status='WARNING')
            flash(f"Account is temporarily locked due to excessive failed attempts. Please try again in {remaining} minute(s).", "danger")
            return render_template('login.html', username=raw_username)

        # Check password hash
        if not user.check_password(raw_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=5)
                db.session.commit()
                log_security_event('ACCOUNT_LOCKED', user_id=user.id, username=user.username, resource_type='auth', details='Account locked for 5 minutes due to 5 consecutive failures', status='WARNING')
                flash("Too many failed login attempts. Account temporarily locked for 5 minutes for security.", "danger")
            else:
                db.session.commit()
                log_security_event('LOGIN_FAILURE', user_id=user.id, username=user.username, resource_type='auth', details=f"Incorrect password attempt ({user.failed_login_attempts}/5)", status='FAILURE')
                flash("Invalid username or password. Please verify your credentials.", "danger")
            return render_template('login.html', username=raw_username)

        # MANDATORY CHECK: Email Verification
        if not user.email_verified:
            log_security_event('LOGIN_BLOCKED_UNVERIFIED', user_id=user.id, username=user.username, resource_type='auth', details='Sign-in attempt on unverified email', status='WARNING')
            flash("Your email address is unverified. Please verify your email before signing in.", "warning")
            return render_template('login.html', username=raw_username, unverified_user=user)

        # MANDATORY CHECK: Account Lifecycle & Approval Status
        if user.status == 'pending_approval':
            log_security_event('LOGIN_BLOCKED_PENDING', user_id=user.id, username=user.username, resource_type='auth', details='Sign-in attempt on pending administrator approval account', status='WARNING')
            flash("Your account has verified email but is pending administrator approval. You will receive an email once activated.", "warning")
            return render_template('login.html', username=raw_username)

        if user.status in ['suspended', 'inactive']:
            log_security_event('LOGIN_BLOCKED_SUSPENDED', user_id=user.id, username=user.username, resource_type='auth', details='Sign-in attempt on suspended account', status='WARNING')
            flash("This account has been deactivated or suspended. Please contact system administration.", "danger")
            return render_template('login.html', username=raw_username)

        # Successful Login
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        login_user(user, remember=remember)
        log_security_event('LOGIN_SUCCESS', user_id=user.id, username=user.username, resource_type='auth', details='Successful password authentication')
        flash(f"Welcome back, {user.full_name or user.username}! ({user.role.title()} Access)", "success")
        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard.index'))

    return render_template('login.html')

# =========================================================================
# 2. REGISTRATION ROUTE
# =========================================================================
@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        organization = request.form.get('organization', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone_number = request.form.get('phone_number', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', '').strip().lower()

        form_data = {
            'full_name': full_name,
            'organization': organization,
            'email': email,
            'phone_number': phone_number,
            'username': username,
            'role': role
        }

        # 1. Required Fields Check
        if not full_name or not organization or not email or not username or not password or not confirm_password or not role:
            flash("All fields are required. Please fill in the complete registration form.", "danger")
            return render_template('register.html', form_data=form_data)

        # 2. Role Restriction (Administrators cannot be self-registered)
        if role in ['admin', 'administrator']:
            log_security_event('ADMIN_REGISTRATION_ATTEMPT', username=username, resource_type='auth', details='Attempted to self-register as administrator', status='WARNING')
            flash("Administrator accounts cannot be created via public registration. Please contact system governance.", "danger")
            return render_template('register.html', form_data=form_data)

        if role not in ['officer', 'viewer']:
            flash("Please select an authorized role: Monitoring Officer or Observer / Viewer.", "danger")
            return render_template('register.html', form_data=form_data)

        # 3. Username Validation & Uniqueness
        valid_u, u_msg = validate_username(username)
        if not valid_u:
            flash(u_msg, "danger")
            return render_template('register.html', form_data=form_data)

        # 4. Email Validation & Uniqueness
        valid_e, e_msg = validate_email(email)
        if not valid_e:
            existing_user = User.query.filter(func.lower(User.email) == email).first()
            if existing_user and not existing_user.email_verified:
                flash("This email is already registered but unverified. Please check your email or request a new verification link below.", "warning")
                return render_template('register.html', form_data=form_data, existing_unverified_email=email)
            flash(e_msg, "danger")
            return render_template('register.html', form_data=form_data)

        # 5. Password Strength Validation (Alphabet, Number, Symbol, >= 8 chars)
        valid_p, p_msg = validate_password_strength(password)
        if not valid_p:
            flash(p_msg, "danger")
            return render_template('register.html', form_data=form_data)

        # 6. Password Confirmation Check
        valid_c, c_msg = validate_password_confirmation(password, confirm_password)
        if not valid_c:
            flash(c_msg, "danger")
            return render_template('register.html', form_data=form_data)

        # 7. Create Account with Unverified Status
        new_user = User(
            username=username,
            email=email,
            phone_number=phone_number,
            role=role,
            full_name=full_name,
            organization=organization,
            department=organization,
            email_verified=False,
            status='pending_verification'
        )
        new_user.set_password(password)
        token = new_user.generate_verification_token(expires_in_hours=24)

        try:
            db.session.add(new_user)
            db.session.commit()
            log_security_event('USER_REGISTERED', user_id=new_user.id, username=new_user.username, resource_type='user', details=f"Registered role '{role}' (unverified)")
        except Exception as e:
            db.session.rollback()
            flash("Database registration error. The username or email may already exist.", "danger")
            return render_template('register.html', form_data=form_data)

        # 8. Send Verification Email
        verification_link = send_verification_email(new_user, token)

        return render_template(
            'register.html',
            registration_success=True,
            registered_email=email,
            registered_username=username,
            registered_role=role,
            verification_link=verification_link
        )

    return render_template('register.html', form_data={})

# =========================================================================
# 3. EMAIL VERIFICATION ROUTE
# =========================================================================
@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    if not token:
        return render_template('verify_email_status.html', success=False, message="No verification token provided.")

    user = User.query.filter_by(verification_token=token).first()

    if not user:
        log_security_event('EMAIL_VERIFICATION_FAILED', resource_type='auth', details='Invalid or expired verification token supplied', status='WARNING')
        return render_template(
            'verify_email_status.html',
            success=False,
            message="Invalid or already used verification link. If your account is already verified, you may sign in."
        )

    # Check expiration (24 hours)
    if user.verification_token_expires_at and datetime.utcnow() > user.verification_token_expires_at:
        expired_email = user.email
        log_security_event('EMAIL_VERIFICATION_EXPIRED', user_id=user.id, username=user.username, resource_type='auth', details='Verification link expired', status='WARNING')
        return render_template(
            'verify_email_status.html',
            success=False,
            expired=True,
            email=expired_email,
            message="This verification link has expired (valid for 24 hours). Please request a new verification email."
        )

    # Verify and update lifecycle status
    success, msg = user.verify_email(token)
    db.session.commit()
    log_security_event('EMAIL_VERIFIED', user_id=user.id, username=user.username, resource_type='user', details=f"Email verified, status={user.status}")

    return render_template(
        'verify_email_status.html',
        success=True,
        role=user.role,
        status=user.status,
        username=user.username,
        email=user.email,
        message=msg
    )

# =========================================================================
# 4. RESEND VERIFICATION EMAIL ROUTE
# =========================================================================
@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def resend_verification():
    email_query = request.args.get('email', '')

    if request.method == 'POST':
        identifier = (request.form.get('identifier', '') or request.form.get('email', '')).strip().lower()
        if not identifier:
            flash("Please enter your registered email address or username.", "danger")
            return render_template('resend_verification.html', identifier=identifier)

        user = User.query.filter(
            (func.lower(User.email) == identifier) |
            (func.lower(User.username) == identifier)
        ).first()

        if user:
            if user.email_verified:
                flash("This account is already verified. You can sign in directly.", "info")
                return redirect(url_for('auth.login'))

            # Rate Limiting: Minimum 60 seconds between resend requests
            if user.last_resend_at and (datetime.utcnow() - user.last_resend_at) < timedelta(seconds=60):
                wait_sec = 60 - int((datetime.utcnow() - user.last_resend_at).total_seconds())
                flash(f"Please wait {max(1, wait_sec)} second(s) before requesting another verification email.", "warning")
                return render_template('resend_verification.html', identifier=identifier)

            # Generate fresh token
            token = user.generate_verification_token(expires_in_hours=24)
            user.last_resend_at = datetime.utcnow()
            user.resend_count = (user.resend_count or 0) + 1
            db.session.commit()

            verification_link = send_verification_email(user, token)
            log_security_event('VERIFICATION_RESENT', user_id=user.id, username=user.username, resource_type='user', details='Fresh verification link dispatched')
            flash("A new verification email has been dispatched. Please check your inbox.", "success")
            return render_template('resend_verification.html', sent=True, email=user.email, verification_link=verification_link)

        # Security-conscious generic response (prevent user enumeration)
        flash("If an unverified account matches that information, a new verification link has been sent.", "info")
        return render_template('resend_verification.html', sent=True, email=identifier)

    return render_template('resend_verification.html', identifier=email_query)

# =========================================================================
# 5. FORGOT PASSWORD ROUTE
# =========================================================================
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash("Please enter your registered official email address.", "danger")
            return render_template('forgot_password.html')

        user = User.query.filter(func.lower(User.email) == email).first()

        if user and user.email_verified and user.status != 'suspended':
            # Rate limiting for password reset (at least 60 seconds between resets)
            if user.last_resend_at and (datetime.utcnow() - user.last_resend_at) < timedelta(seconds=60):
                wait_sec = 60 - int((datetime.utcnow() - user.last_resend_at).total_seconds())
                flash(f"Please wait {max(1, wait_sec)} second(s) before requesting another password reset.", "warning")
                return render_template('forgot_password.html')

            token = user.generate_reset_token(expires_in_hours=1)
            user.last_resend_at = datetime.utcnow()
            db.session.commit()

            reset_link = send_password_reset_email(user, token)
            log_security_event('PASSWORD_RESET_REQUESTED', user_id=user.id, username=user.username, resource_type='auth', details='Password reset link requested')
            flash("Password reset instructions have been sent to your email address.", "success")
            return render_template('forgot_password.html', sent=True, email=email, reset_link=reset_link)

        # Security-conscious response to prevent email enumeration
        flash("If an active account exists for that email, password reset instructions have been dispatched.", "info")
        return render_template('forgot_password.html', sent=True, email=email)

    return render_template('forgot_password.html')

# =========================================================================
# 6. RESET PASSWORD ROUTE
# =========================================================================
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        flash("This password reset link is invalid or has already been used.", "danger")
        return redirect(url_for('auth.forgot_password'))

    if user.reset_token_expires_at and datetime.utcnow() > user.reset_token_expires_at:
        flash("This password reset link has expired (valid for 1 hour). Please request a new one.", "danger")
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        valid_p, p_msg = validate_password_strength(password)
        if not valid_p:
            flash(p_msg, "danger")
            return render_template('reset_password.html', token=token)

        valid_c, c_msg = validate_password_confirmation(password, confirm_password)
        if not valid_c:
            flash(c_msg, "danger")
            return render_template('reset_password.html', token=token)

        # Execute reset
        success, msg = user.reset_password(token, password)
        if success:
            db.session.commit()
            log_security_event('PASSWORD_RESET_COMPLETED', user_id=user.id, username=user.username, resource_type='auth', details='Password updated via single-use reset token')
            flash("Your password has been successfully updated. You can now sign in with your new password.", "success")
            return redirect(url_for('auth.login'))
        else:
            flash(msg, "danger")
            return render_template('reset_password.html', token=token)

    return render_template('reset_password.html', token=token)

# =========================================================================
# 7. SMS-BASED PASSWORD RESET ROUTE (UNAUTHENTICATED)
# =========================================================================
@auth_bp.route('/reset-password-sms', methods=['GET', 'POST'])
@limiter.limit("15 per minute")
def reset_password_sms():
    """Update or reset password using SMS verification code."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        action = request.form.get('action', 'verify_update')
        identifier = request.form.get('identifier', '').strip()

        # Step 1: Send SMS code
        if action == 'send_code':
            if not identifier:
                flash("Please enter your registered mobile number, username, or official email.", "danger")
                return render_template('reset_password_sms.html')

            user = User.query.filter(
                (User.phone_number == identifier) |
                (func.lower(User.username) == identifier.lower()) |
                (func.lower(User.email) == identifier.lower())
            ).first()

            if user and user.status != 'suspended':
                target_phone = user.phone_number or identifier
                code = user.generate_sms_code(expires_in_minutes=10)
                db.session.commit()

                send_sms_code(target_phone, code, purpose="Password Reset", username=user.username)
                log_security_event('SMS_RESET_CODE_SENT', user_id=user.id, username=user.username, resource_type='auth', details=f"SMS verification code sent to {target_phone}")

                flash("A 6-digit verification code has been dispatched via SMS.", "success")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier, username=user.username, phone_number=target_phone, dev_code=code)
            else:
                # Security-conscious feedback
                flash("If an active account exists for that identifier, a verification code has been dispatched via SMS.", "info")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier)

        # Step 2: Verify code and update password
        elif action == 'verify_update':
            sms_code = request.form.get('sms_code', '').strip()
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not identifier or not sms_code or not new_password or not confirm_password:
                flash("All fields (Identifier, 6-digit Code, New Password, Confirm Password) are required.", "danger")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier)

            user = User.query.filter(
                (User.phone_number == identifier) |
                (func.lower(User.username) == identifier.lower()) |
                (func.lower(User.email) == identifier.lower())
            ).first()

            if not user:
                flash("Account not found. Please verify your mobile number or username.", "danger")
                return render_template('reset_password_sms.html')

            valid_p, p_msg = validate_password_strength(new_password)
            if not valid_p:
                flash(p_msg, "danger")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier, username=user.username)

            valid_c, c_msg = validate_password_confirmation(new_password, confirm_password)
            if not valid_c:
                flash(c_msg, "danger")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier, username=user.username)

            success, msg = user.update_password_with_sms_code(sms_code, new_password)
            if success:
                db.session.commit()
                log_security_event('PASSWORD_RESET_SMS_SUCCESS', user_id=user.id, username=user.username, resource_type='auth', details="Password updated successfully via SMS verification code")
                flash("Your password has been successfully updated via SMS verification code. You can now sign in with your new password.", "success")
                return redirect(url_for('auth.login'))
            else:
                flash(msg, "danger")
                return render_template('reset_password_sms.html', code_sent=True, identifier=identifier, username=user.username)

    return render_template('reset_password_sms.html')

# =========================================================================
# 8. CHANGE PASSWORD ROUTE (AUTHENTICATED USERS - PASSWORD OR SMS CODE)
# =========================================================================
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")
def change_password():
    if request.method == 'POST':
        auth_method = request.form.get('auth_method', 'password')  # 'password' or 'sms_code'
        current_password = request.form.get('current_password', '')
        sms_code = request.form.get('sms_code', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # User must provide current password OR SMS verification code
        if auth_method == 'sms_code' or sms_code:
            if not sms_code:
                flash("Please enter the 6-digit SMS verification code dispatched to your phone.", "danger")
                return render_template('change_password.html')
            valid_code, code_msg = current_user.verify_sms_code(sms_code)
            if not valid_code:
                log_security_event('PASSWORD_CHANGE_SMS_FAILED', user_id=current_user.id, username=current_user.username, resource_type='auth', details='Invalid or expired SMS code during password change', status='FAILURE')
                flash(code_msg, "danger")
                return render_template('change_password.html')
        else:
            if not current_password:
                flash("Please provide your current password or request an SMS verification code.", "danger")
                return render_template('change_password.html')
            if not current_user.check_password(current_password):
                log_security_event('PASSWORD_CHANGE_FAILED', user_id=current_user.id, username=current_user.username, resource_type='auth', details='Incorrect current password entered', status='FAILURE')
                flash("Current password is incorrect.", "danger")
                return render_template('change_password.html')

        if not new_password or not confirm_password:
            flash("Please enter and confirm your new password.", "danger")
            return render_template('change_password.html')

        if current_password and current_password == new_password:
            flash("New password cannot be identical to your current password.", "warning")
            return render_template('change_password.html')

        valid_p, p_msg = validate_password_strength(new_password)
        if not valid_p:
            flash(p_msg, "danger")
            return render_template('change_password.html')

        valid_c, c_msg = validate_password_confirmation(new_password, confirm_password)
        if not valid_c:
            flash(c_msg, "danger")
            return render_template('change_password.html')

        if auth_method == 'sms_code' or sms_code:
            success, msg = current_user.update_password_with_sms_code(sms_code, new_password)
            audit_detail = 'User updated password via SMS verification code'
        else:
            success, msg = current_user.change_password(current_password, new_password)
            audit_detail = 'User updated password via current password authentication'

        if success:
            db.session.commit()
            log_security_event('PASSWORD_CHANGED', user_id=current_user.id, username=current_user.username, resource_type='auth', details=audit_detail)
            flash("Your password has been successfully updated.", "success")
            return redirect(url_for('dashboard.index'))
        else:
            flash(msg, "danger")
            return render_template('change_password.html')

    return render_template('change_password.html')

@auth_bp.route('/api/auth/send-change-password-code', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def send_change_password_code():
    """Dispatches SMS verification code to logged-in user for changing password."""
    phone = ""
    if request.is_json and request.json:
        phone = request.json.get('phone_number', '').strip()
    elif request.form:
        phone = request.form.get('phone_number', '').strip()

    if not phone:
        phone = current_user.phone_number or '+91 98765 43210'

    current_user.phone_number = phone
    code = current_user.generate_sms_code(expires_in_minutes=10)
    db.session.commit()

    send_sms_code(phone, code, purpose="Change Password", username=current_user.username)
    log_security_event('SMS_CHANGE_CODE_SENT', user_id=current_user.id, username=current_user.username, resource_type='auth', details=f"Sent password change SMS code to {phone}")

    return jsonify({
        'success': True,
        'message': f"A 6-digit verification code has been dispatched to {phone} via SMS.",
        'phone_number': phone,
        'dev_code': code
    })

# =========================================================================
# 8. ADMINISTRATOR USER APPROVAL MANAGEMENT
# =========================================================================
@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    status_filter = request.args.get('status', '')
    query = User.query
    if status_filter:
        query = query.filter(User.status == status_filter)
    users = query.order_by(User.created_at.desc()).all()

    counts = {
        'total': User.query.count(),
        'pending_approval': User.query.filter_by(status='pending_approval').count(),
        'pending_verification': User.query.filter_by(status='pending_verification').count(),
        'active': User.query.filter_by(status='active').count()
    }

    projects = Project.query.order_by(Project.project_name).all()

    return render_template('admin_users.html', users=users, counts=counts, current_filter=status_filter, projects=projects)

@auth_bp.route('/admin/users/create', methods=['POST'])
@admin_required
def admin_create_user():
    full_name = request.form.get('full_name', '').strip()
    organization = request.form.get('organization', '').strip()
    department = request.form.get('department', '').strip() or organization
    email = request.form.get('email', '').strip().lower()
    phone_number = request.form.get('phone_number', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    role = request.form.get('role', '').strip().lower()
    is_active = request.form.get('is_active') in ['1', 'true', 'on', 'yes']
    assigned_project_ids = request.form.getlist('assigned_projects')

    # Basic validations
    if not full_name or not username or not email or not password or not role:
        flash("All mandatory fields (Full Name, Username, Email, Role, Password) must be provided.", "danger")
        return redirect(url_for('auth.admin_users'))

    if role not in ['admin', 'officer', 'viewer']:
        flash("Invalid role specified. Role must be Administrator, Monitoring Officer, or Observer / Viewer.", "danger")
        return redirect(url_for('auth.admin_users'))

    # Validate username
    valid_u, u_msg = validate_username(username)
    if not valid_u:
        flash(u_msg, "danger")
        return redirect(url_for('auth.admin_users'))

    # Validate email
    valid_e, e_msg = validate_email(email)
    if not valid_e:
        flash(e_msg, "danger")
        return redirect(url_for('auth.admin_users'))

    # Validate password strength & match
    valid_p, p_msg = validate_password_strength(password)
    if not valid_p:
        flash(p_msg, "danger")
        return redirect(url_for('auth.admin_users'))

    valid_c, c_msg = validate_password_confirmation(password, confirm_password)
    if not valid_c:
        flash(c_msg, "danger")
        return redirect(url_for('auth.admin_users'))

    # Check existence
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        flash(f"Username '{username}' is already taken. Please choose another.", "danger")
        return redirect(url_for('auth.admin_users'))

    if User.query.filter(func.lower(User.email) == email.lower()).first():
        flash(f"Email '{email}' is already registered.", "danger")
        return redirect(url_for('auth.admin_users'))

    # Create user
    new_user = User(
        username=username,
        email=email,
        phone_number=phone_number,
        role=role,
        full_name=full_name,
        organization=organization,
        department=department,
        email_verified=is_active,
        status='active' if is_active else 'pending_verification'
    )
    new_user.set_password(password)

    if not is_active:
        token = new_user.generate_verification_token(expires_in_hours=24)
        send_verification_email(new_user, token)

    try:
        db.session.add(new_user)
        db.session.flush()

        # Handle project assignments for officers
        if role == 'officer' and assigned_project_ids:
            for pid in assigned_project_ids:
                try:
                    pid_int = int(pid)
                    proj = db.session.get(Project, pid_int)
                    if proj:
                        assignment = ProjectAssignment(
                            user_id=new_user.id,
                            project_id=proj.id,
                            can_edit=True,
                            role_scope='Monitoring Officer'
                        )
                        db.session.add(assignment)
                except (ValueError, TypeError):
                    continue

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Database error during account creation: " + str(e), "danger")
        return redirect(url_for('auth.admin_users'))

    log_security_event(
        'ADMIN_USER_CREATED',
        user_id=new_user.id,
        username=new_user.username,
        resource_type='user',
        details=f"Admin '{current_user.username}' created account with role '{role}' (status: {new_user.status})"
    )

    status_note = "Account is active and ready for immediate sign-in." if is_active else "Verification email dispatched. Account pending email verification."
    flash(f"User account '{new_user.username}' ({new_user.full_name}) created successfully. {status_note}", "success")
    return redirect(url_for('auth.admin_users'))

@auth_bp.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('auth.admin_users'))

    if user.status == 'active':
        flash(f"User '{user.username}' is already active.", "info")
    else:
        user.status = 'active'
        db.session.commit()
        log_security_event('USER_APPROVED', resource_type='user', resource_id=str(user.id), details=f"Admin approved and activated user '{user.username}'")
        flash(f"User '{user.username}' ({user.full_name}) has been approved and activated.", "success")

    return redirect(url_for('auth.admin_users'))

@auth_bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('auth.admin_users'))

    if user.id == current_user.id:
        flash("You cannot deactivate your own administrative account.", "danger")
        return redirect(url_for('auth.admin_users'))

    if user.status == 'active':
        user.status = 'suspended'
        log_security_event('USER_STATUS_CHANGE', resource_type='user', resource_id=str(user.id), details=f"Admin suspended user '{user.username}'")
        flash(f"Account for '{user.username}' has been suspended.", "warning")
    else:
        user.status = 'active'
        log_security_event('USER_STATUS_CHANGE', resource_type='user', resource_id=str(user.id), details=f"Admin activated user '{user.username}'")
        flash(f"Account for '{user.username}' has been activated.", "success")

    db.session.commit()
    return redirect(url_for('auth.admin_users'))

# =========================================================================
# 9. ADMINISTRATOR SECURITY AUDIT LOGS VIEWER
# =========================================================================
@auth_bp.route('/admin/audit-logs')
@admin_required
def admin_audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    query = SecurityAuditLog.query

    if action_filter:
        query = query.filter(SecurityAuditLog.action == action_filter)
    if status_filter:
        query = query.filter(SecurityAuditLog.status == status_filter)
    if search:
        query = query.filter(
            (SecurityAuditLog.username.ilike(f"%{search}%")) |
            (SecurityAuditLog.details.ilike(f"%{search}%")) |
            (SecurityAuditLog.ip_address.ilike(f"%{search}%"))
        )

    pagination = query.order_by(SecurityAuditLog.created_at.desc()).paginate(page=page, per_page=30, error_out=False)

    distinct_actions = [a[0] for a in db.session.query(SecurityAuditLog.action).distinct().all() if a[0]]

    return render_template(
        'admin_audit_logs.html',
        logs=pagination.items,
        pagination=pagination,
        distinct_actions=distinct_actions,
        action_filter=action_filter,
        status_filter=status_filter,
        search=search
    )

# =========================================================================
# 10. LOGOUT & UTILITY
# =========================================================================
@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username if current_user.is_authenticated else 'unknown'
    user_id = current_user.id if current_user.is_authenticated else None
    log_security_event('LOGOUT', user_id=user_id, username=username, resource_type='auth', details='User signed out')
    logout_user()
    flash("You have been securely signed out.", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/auth/current_user')
def get_current_user():
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': serialize_user_for_user(current_user, current_user)
        })
    return jsonify({'authenticated': False, 'user': None})

# =========================================================================
# 11. ADMIN ROOT & SYSTEM SETTINGS
# =========================================================================
@auth_bp.route('/admin')
@admin_required
def admin_root():
    return redirect(url_for('auth.admin_users'))

@auth_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    from flask import current_app
    settings = current_app.config.get('SYSTEM_SECURITY_SETTINGS', {
        'critical_risk_threshold': 70,
        'high_risk_threshold': 45,
        'medium_risk_threshold': 25,
        'session_timeout_minutes': 120,
        'rate_limit_rpm': 100,
        'lockout_threshold': 5
    })

    if request.method == 'POST':
        try:
            crit = int(request.form.get('critical_risk_threshold', 70))
            high = int(request.form.get('high_risk_threshold', 45))
            med = int(request.form.get('medium_risk_threshold', 25))
            timeout = int(request.form.get('session_timeout_minutes', 120))
            rpm = int(request.form.get('rate_limit_rpm', 100))
            lockout = int(request.form.get('lockout_threshold', 5))

            settings['critical_risk_threshold'] = crit
            settings['high_risk_threshold'] = high
            settings['medium_risk_threshold'] = med
            settings['session_timeout_minutes'] = timeout
            settings['rate_limit_rpm'] = rpm
            settings['lockout_threshold'] = lockout
            current_app.config['SYSTEM_SECURITY_SETTINGS'] = settings

            log_security_event('ADMIN_SETTINGS_UPDATE', resource_type='system_settings', details=f"Updated risk thresholds (Crit:{crit}, High:{high}, Med:{med}) and limits")
            flash("System configuration and risk thresholds updated successfully.", "success")
        except Exception as e:
            flash(f"Error updating configuration: {str(e)}", "danger")

    return render_template('admin_settings.html', settings=settings)
