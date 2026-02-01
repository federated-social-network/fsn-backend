from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    INSTANCE_NAME : str
    DATABASE_URL : str
    SEND_TO_OTHER_INSTANCE: bool = False
    SECRET_KEY : str
    ALGORITHM : str = "HS256"
    BASE_URL : str
    REMOTE_INBOX_URL: Optional[str] = None
    DELIVERY_ENABLED: bool = SEND_TO_OTHER_INSTANCE
    
    # Email settings
    EMAIL_PROVIDER: str = "gmail"  # "gmail" (SMTP), "smtp", "sendgrid", "ses"
    FROM_EMAIL: str = ""
    OTP_EXPIRY_MINUTES: int = 10
    
    # Gmail SMTP settings
    GMAIL_SMTP_USER: str = ""  # Your Gmail address
    GMAIL_SMTP_PASSWORD: str = ""  # App-specific password (not regular password)
    
    # SMTP settings (for backwards compatibility)
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
