import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
from datetime import datetime, timedelta


def generate_otp(length: int = 6) -> str:
    """Generate a random OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))


def send_otp_email(email: str, otp: str, username: str) -> bool:
    """
    Send OTP to user's email
    Returns True if successful, False otherwise
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print("Email credentials not configured")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Password Reset OTP"
        message["From"] = settings.FROM_EMAIL
        message["To"] = email

        # Plain text version
        text = f"Hello {username},\n\nYour OTP for password reset is: {otp}\n\nThis OTP will expire in {settings.OTP_EXPIRY_MINUTES} minutes.\n\nIf you didn't request this, please ignore this email."

        # HTML version
        html = f"""\
        <html>
            <body>
                <p>Hello {username},</p>
                <p>Your OTP for password reset is:</p>
                <h2 style="color: #007bff;">{otp}</h2>
                <p>This OTP will expire in {settings.OTP_EXPIRY_MINUTES} minutes.</p>
                <p style="color: #666;">If you didn't request this, please ignore this email.</p>
            </body>
        </html>
        """

        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)

        # Send email
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.FROM_EMAIL, email, message.as_string())

        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False
