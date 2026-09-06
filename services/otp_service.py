import hashlib
import secrets
from datetime import datetime, timezone

def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"

def hash_otp(otp):
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()

def otp_expiry(minutes):
    from datetime import timedelta
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
