import random
import string
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.config import settings
from datetime import datetime, timedelta


def generate_otp(length: int = 6) -> str:
    """Generate a random OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))


def _send_with_gmail_oauth(email: str, subject: str, html: str, text: str) -> bool:
    """Send email using Gmail API with OAuth2 credentials"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        
        if not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET or not settings.GMAIL_REFRESH_TOKEN:
            print("Gmail OAuth2 credentials not configured")
            return False
        
        # Create credentials from OAuth2 tokens
        credentials = Credentials(
            token=None,  # Will be refreshed
            refresh_token=settings.GMAIL_REFRESH_TOKEN,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GMAIL_CLIENT_ID,
            client_secret=settings.GMAIL_CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        
        # Refresh token to get valid access token
        request = Request()
        credentials.refresh(request)
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)
        
        # Create message
        message = MIMEMultipart('alternative')
        message['to'] = email
        message['from'] = settings.FROM_EMAIL
        message['subject'] = subject
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        message.attach(part1)
        message.attach(part2)
        
        # Encode message for Gmail API
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send message
        result = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        print(f"Email sent successfully. Message ID: {result.get('id')}")
        return True
    except Exception as e:
        print(f"Error sending email with Gmail API: {str(e)}")
        import traceback
        traceback.print_exc()
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
            <p style="color: #808080;">Tips for new password : Keep your password long and ensure that it does not contain any common terms that could be cracked easily</p>
            <p>Your OTP for password reset is:</p>
            <h2 style="color: #007bff;">{otp}</h2>
            <p>This OTP will expire in {settings.OTP_EXPIRY_MINUTES} minutes.</p>
            <p style="color: #666;">If you didn't request this, please ignore this email.</p>
        </body>
    </html>
    """
    
    provider = settings.EMAIL_PROVIDER.lower()
    
    if provider == "gmail_oauth":
        return _send_with_gmail_oauth(email, subject, html, text)
    elif provider == "smtp":
        return _send_with_smtp(email, subject, html, text)
    else:
        print(f"Unknown email provider: {provider}")
        return False
