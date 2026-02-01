import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.config import settings
from datetime import datetime, timedelta


def generate_otp(length: int = 6) -> str:
    """Generate a random OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))


def _send_with_gmail_smtp(email: str, subject: str, html: str, text: str) -> bool:
    """Send email using Gmail SMTP"""
    try:
        if not settings.GMAIL_SMTP_USER or not settings.GMAIL_SMTP_PASSWORD:
            print("Gmail SMTP credentials not configured")
            return False
        
        # Create message
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = settings.FROM_EMAIL or settings.GMAIL_SMTP_USER
        message['To'] = email
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        message.attach(part1)
        message.attach(part2)
        
        # Send via Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(settings.GMAIL_SMTP_USER, settings.GMAIL_SMTP_PASSWORD)
            server.sendmail(settings.FROM_EMAIL or settings.GMAIL_SMTP_USER, email, message.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending email with Gmail SMTP: {str(e)}")
        return False


def _send_with_smtp(email: str, subject: str, html: str, text: str) -> bool:
    """Send email using SMTP (legacy)"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            print("Email credentials not configured")
            return False
        
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = settings.FROM_EMAIL
        message["To"] = email
        
        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)
        
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.FROM_EMAIL, email, message.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending email with SMTP: {str(e)}")
        return False


def send_otp_email(email: str, otp: str, username: str) -> bool:
    """
    Send OTP to user's email
    Uses configured email provider (Resend by default, SMTP as fallback)
    Returns True if successful, False otherwise
    """
    subject = "Password Reset OTP"
    
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
    
    provider = settings.EMAIL_PROVIDER.lower()
    
    if provider == "gmail":
        return _send_with_gmail_smtp(email, subject, html, text)
    elif provider == "smtp":
        return _send_with_smtp(email, subject, html, text)
    else:
        print(f"Unknown email provider: {provider}")
        return False
