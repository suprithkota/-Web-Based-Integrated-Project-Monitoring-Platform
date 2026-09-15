import re
from sqlalchemy import func
from database.models import User

# Special symbols regex pattern
SPECIAL_SYMBOL_PATTERN = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]""")

def validate_password_strength(password):
    """
    Validates that password satisfies:
    1. Minimum 8 characters
    2. At least one capital letter (A-Z)
    3. At least one small letter (a-z)
    4. At least one numeric character (0-9)
    5. At least one special symbol
    """
    if not password:
        return False, "Password is required."

    if len(password) < 8:
        return False, "Password must be at least 8 characters long."

    if not re.search(r'[a-zA-Z]', password):
        return False, "Password must contain at least one alphabetic character (A-Z or a-z)."

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one capital letter (A-Z)."

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one small letter (a-z)."

    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one numeric character (0-9)."

    if not SPECIAL_SYMBOL_PATTERN.search(password):
        return False, "Password must contain at least one special symbol (e.g. !@#$%^&*()_+-=)."

    return True, "Password meets all security requirements."

def validate_password_confirmation(password, confirm_password):
    """Verifies that password and confirm_password match."""
    if password != confirm_password:
        return False, "Passwords do not match."
    return True, "Passwords match."

def validate_username(username, exclude_user_id=None):
    """
    Validates username format and enforces case-insensitive uniqueness:
    - 3 to 30 characters
    - Letters, numbers, underscores only
    - Unique across all users
    """
    if not username:
        return False, "Username is required."

    username = username.strip()

    if len(username) < 3 or len(username) > 30:
        return False, "Username must be between 3 and 30 characters in length."

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores."

    # Authoritative case-insensitive database check
    query = User.query.filter(func.lower(User.username) == username.lower())
    if exclude_user_id:
        query = query.filter(User.id != exclude_user_id)

    existing = query.first()
    if existing:
        return False, "Username already exists. Please choose another username."

    return True, "Username is valid and available."

def validate_email(email, exclude_user_id=None):
    """
    Validates email format and checks for case-insensitive uniqueness.
    """
    if not email:
        return False, "Official email is required."

    email = email.strip().lower()
    email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

    if not re.match(email_pattern, email):
        return False, "Please enter a valid official email address."

    # Check existing user
    query = User.query.filter(func.lower(User.email) == email)
    if exclude_user_id:
        query = query.filter(User.id != exclude_user_id)

    existing = query.first()
    if existing:
        return False, "This email is already registered."

    return True, "Email is valid and available."
