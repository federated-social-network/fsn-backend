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
    EMAIL_PROVIDER: str = "gmail_oauth"  # "gmail_oauth", "smtp"
    FROM_EMAIL: str = ""
    OTP_EXPIRY_MINUTES: int = 10
    
    # Gmail OAuth2 settings
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    
    # SMTP settings (for backwards compatibility)
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
