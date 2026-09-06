import smtplib
from email.message import EmailMessage
from config.config import Config

def send_password_reset_otp(recipient, otp, expires_minutes):
    if not Config.SMTP_HOST or not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD or not Config.SMTP_FROM:
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM in .env.")

    message = EmailMessage()
    message["Subject"] = "GovSync Password Reset OTP"
    message["From"] = Config.SMTP_FROM
    message["To"] = recipient
    message.set_content(
        f"""Hello,

We received a request to reset your GovSync password.

Your one-time password (OTP) is: {otp}

This OTP expires in {expires_minutes} minutes. If you did not request a password reset, you can safely ignore this email.

For your security, never share this OTP with anyone.

Regards,
GovSync Team
"""
    )

    if Config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(message)
    else:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(message)
