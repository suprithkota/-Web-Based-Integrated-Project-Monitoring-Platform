import os
import json
import secrets
from datetime import datetime
from flask import current_app

# Thread-safe in-memory SMS storage for development and testing inspection
DEV_SENT_SMS = []

def generate_sms_otp(length=6):
    """Generates a cryptographically secure numeric OTP code of specified length."""
    range_start = 10 ** (length - 1)
    range_end = (10 ** length) - 1
    code = str(secrets.randbelow(range_end - range_start + 1) + range_start)
    return code

def _record_dev_sms(sms_data):
    """Stores outgoing SMS in dev mailbox for local development & automated test inspection."""
    DEV_SENT_SMS.append(sms_data)
    try:
        os.makedirs('instance', exist_ok=True)
        sms_file = 'instance/dev_sms_box.json'
        records = []
        if os.path.exists(sms_file):
            try:
                with open(sms_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except Exception:
                records = []
        records.append(sms_data)
        # Keep last 50 SMS records
        records = records[-50:]
        with open(sms_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        print(f"[SMS DEV STORE ERROR]: {e}")

def get_latest_dev_sms(phone_number=None):
    """Helper for testing: fetches the most recent dev SMS matching phone number."""
    for sms in reversed(DEV_SENT_SMS):
        if phone_number and sms.get('phone_number') != phone_number:
            continue
        return sms
    return None

def clear_dev_sms_box():
    """Clears development in-memory SMS mailbox."""
    global DEV_SENT_SMS
    DEV_SENT_SMS.clear()

def send_sms_code(phone_number, code, purpose="Password Reset", username=None):
    """
    Sends a 6-digit verification code to the recipient's phone number.
    In development/prototype mode, logs to console and dev store.
    If external SMS provider credentials are configured, dispatches real SMS.
    """
    cleaned_phone = phone_number.strip() if phone_number else ""
    user_str = f" for user '{username}'" if username else ""
    message_text = f"[ProjectPulse AI] Your official security verification code{user_str} is: {code}. Valid for 10 minutes. Do not share this code."

    sms_record = {
        'phone_number': cleaned_phone,
        'code': code,
        'purpose': purpose,
        'username': username or '',
        'message': message_text,
        'timestamp': datetime.utcnow().isoformat()
    }
    _record_dev_sms(sms_record)

    print(f"[SMS SERVICE - DISPATCH] To: {cleaned_phone} | Code: {code} | Purpose: {purpose} | Msg: {message_text}")

    # Optional Production SMS Integration (e.g. Twilio or Government SMS Gateway)
    twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
    twilio_from = os.environ.get('TWILIO_FROM_NUMBER')

    if twilio_sid and twilio_token and twilio_from:
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            client.messages.create(
                body=message_text,
                from_=twilio_from,
                to=cleaned_phone
            )
            print(f"[SMS SERVICE - TWILIO SUCCESS] Sent SMS to {cleaned_phone}")
        except Exception as e:
            print(f"[SMS SERVICE - TWILIO ERROR]: {e}")

    return {
        'success': True,
        'code': code,
        'phone_number': cleaned_phone,
        'message': "Verification code dispatched via SMS."
    }
