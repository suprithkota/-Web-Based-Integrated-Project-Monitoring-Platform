import os
import smtplib
import json
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app

# Thread-safe in-memory mailbox for development & testing inspection
DEV_SENT_EMAILS = []

def get_email_config():
    """Retrieves email configuration from environment or app config."""
    app_config = current_app.config if current_app else {}
    return {
        'server': os.environ.get('MAIL_SERVER') or app_config.get('MAIL_SERVER', 'localhost'),
        'port': int(os.environ.get('MAIL_PORT') or app_config.get('MAIL_PORT', 587)),
        'use_tls': str(os.environ.get('MAIL_USE_TLS') or app_config.get('MAIL_USE_TLS', 'true')).lower() in ['true', '1'],
        'username': os.environ.get('MAIL_USERNAME') or app_config.get('MAIL_USERNAME', ''),
        'password': os.environ.get('MAIL_PASSWORD') or app_config.get('MAIL_PASSWORD', ''),
        'default_sender': os.environ.get('MAIL_DEFAULT_SENDER') or app_config.get('MAIL_DEFAULT_SENDER', 'noreply@projectpulse.gov.in'),
        'base_url': os.environ.get('APP_BASE_URL') or app_config.get('APP_BASE_URL', 'http://127.0.0.1:5000')
    }

def _record_dev_email(email_data):
    """Stores outgoing email in dev mailbox for local development & automated test inspection."""
    DEV_SENT_EMAILS.append(email_data)
    try:
        os.makedirs('instance', exist_ok=True)
        mailbox_file = 'instance/dev_mailbox.json'
        records = []
        if os.path.exists(mailbox_file):
            try:
                with open(mailbox_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except Exception:
                records = []
        records.append(email_data)
        # Keep last 50 emails
        records = records[-50:]
        with open(mailbox_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        print(f"[EMAIL DEV STORE ERROR]: {e}")

def get_latest_dev_email(recipient=None, email_type=None):
    """Helper for testing: fetches the most recent dev email matching criteria."""
    for email in reversed(DEV_SENT_EMAILS):
        if recipient and email.get('recipient').lower() != recipient.lower():
            continue
        if email_type and email.get('type') != email_type:
            continue
        return email
    return None

def clear_dev_mailbox():
    """Clears development in-memory mailbox."""
    global DEV_SENT_EMAILS
    DEV_SENT_EMAILS.clear()

def send_verification_email(user, token):
    """
    Sends time-limited, single-use account verification link.
    """
    config = get_email_config()
    verification_url = f"{config['base_url']}/verify-email/{token}"
    subject = "ProjectPulse AI — Verify Your Official Email Address"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #0d1b2a, #1d3557); color: #ffffff; padding: 24px; text-align: center; }}
        .body {{ padding: 32px 24px; color: #334155; line-height: 1.6; }}
        .btn {{ display: inline-block; background-color: #1d3557; color: #ffffff !important; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 20px 0; }}
        .footer {{ background: #f1f5f9; padding: 16px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
        .badge {{ display: inline-block; background: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h2 style="margin: 0;">ProjectPulse AI</h2>
          <div style="font-size: 13px; opacity: 0.85; margin-top: 4px;">Infrastructure Project Intelligence & Early Warning Platform</div>
        </div>
        <div class="body">
          <h3>Verify Your Official Account</h3>
          <p>Hello <strong>{user.full_name or user.username}</strong>,</p>
          <p>An official registration was submitted for your email address with the role of <strong>{user.role.title()}</strong>.</p>
          <p>To confirm your identity and activate your email address, please click the secure button below:</p>
          <div style="text-align: center;">
            <a href="{verification_url}" class="btn">Verify Official Email</a>
          </div>
          <p style="font-size: 13px; color: #64748b;">This verification link is time-limited (valid for 24 hours) and can only be used once.</p>
          <p style="font-size: 12px; color: #94a3b8; word-break: break-all;">Direct Link: <a href="{verification_url}">{verification_url}</a></p>
        </div>
        <div class="footer">
          Authorized Government Infrastructure Decision Support System &bull; SIH26103 Prototype
        </div>
      </div>
    </body>
    </html>
    """

    email_data = {
        'recipient': user.email,
        'subject': subject,
        'type': 'verification',
        'token': token,
        'link': verification_url,
        'timestamp': datetime.utcnow().isoformat()
    }
    _record_dev_email(email_data)

    print(f"[EMAIL SERVICE - VERIFICATION DISPATCH] To: {user.email} | Token: {token[:8]}... | Link: {verification_url}")

    # If real SMTP credentials are provided, attempt real dispatch
    if config['username'] and config['password'] and config['server'] != 'localhost':
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = config['default_sender']
            msg['To'] = user.email
            msg.attach(MIMEText(f"Please verify your account by visiting: {verification_url}", 'plain'))
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(config['server'], config['port']) as server:
                if config['use_tls']:
                    server.starttls()
                server.login(config['username'], config['password'])
                server.sendmail(config['default_sender'], [user.email], msg.as_string())
            print(f"[EMAIL SERVICE - REAL SMTP SUCCESS] Sent to {user.email}")
        except Exception as e:
            print(f"[EMAIL SERVICE - SMTP ERROR]: {e}")

    return verification_url

def send_password_reset_email(user, token):
    """
    Sends time-limited, single-use password reset link.
    """
    config = get_email_config()
    reset_url = f"{config['base_url']}/reset-password/{token}"
    subject = "ProjectPulse AI — Password Reset Request"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #0d1b2a, #1d3557); color: #ffffff; padding: 24px; text-align: center; }}
        .body {{ padding: 32px 24px; color: #334155; line-height: 1.6; }}
        .btn {{ display: inline-block; background-color: #dc2626; color: #ffffff !important; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 20px 0; }}
        .footer {{ background: #f1f5f9; padding: 16px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h2 style="margin: 0;">ProjectPulse AI</h2>
          <div style="font-size: 13px; opacity: 0.85; margin-top: 4px;">Infrastructure Project Intelligence & Early Warning Platform</div>
        </div>
        <div class="body">
          <h3>Password Reset Request</h3>
          <p>Hello <strong>{user.full_name or user.username}</strong>,</p>
          <p>We received a request to reset the password for your official account (<strong>{user.username}</strong>).</p>
          <p>Click the button below to choose a new password:</p>
          <div style="text-align: center;">
            <a href="{reset_url}" class="btn">Reset Password</a>
          </div>
          <p style="font-size: 13px; color: #dc2626;"><strong>Important:</strong> This link will expire in 1 hour and can only be used once.</p>
          <p style="font-size: 13px; color: #64748b;">If you did not request this change, please ignore this email or notify your system administrator immediately.</p>
          <p style="font-size: 12px; color: #94a3b8; word-break: break-all;">Direct Link: <a href="{reset_url}">{reset_url}</a></p>
        </div>
        <div class="footer">
          Authorized Government Infrastructure Decision Support System &bull; SIH26103 Prototype
        </div>
      </div>
    </body>
    </html>
    """

    email_data = {
        'recipient': user.email,
        'subject': subject,
        'type': 'password_reset',
        'token': token,
        'link': reset_url,
        'timestamp': datetime.utcnow().isoformat()
    }
    _record_dev_email(email_data)

    print(f"[EMAIL SERVICE - RESET DISPATCH] To: {user.email} | Token: {token[:8]}... | Link: {reset_url}")

    if config['username'] and config['password'] and config['server'] != 'localhost':
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = config['default_sender']
            msg['To'] = user.email
            msg.attach(MIMEText(f"Please reset your password by visiting: {reset_url}", 'plain'))
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(config['server'], config['port']) as server:
                if config['use_tls']:
                    server.starttls()
                server.login(config['username'], config['password'])
                server.sendmail(config['default_sender'], [user.email], msg.as_string())
            print(f"[EMAIL SERVICE - REAL SMTP SUCCESS] Sent reset to {user.email}")
        except Exception as e:
            print(f"[EMAIL SERVICE - SMTP ERROR]: {e}")

    return reset_url
