import secrets
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password):
    return generate_password_hash(password)

def verify_password(stored_value, password):
    if not stored_value:
        return False
    # Normal path: Werkzeug hash.
    if stored_value.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_value, password)
    # Transitional path for a legacy plain-text password column.
    # A successful login immediately replaces it with a secure hash.
    return secrets.compare_digest(str(stored_value), str(password))
