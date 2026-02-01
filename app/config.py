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
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = ""
    OTP_EXPIRY_MINUTES: int = 10

    class Config:
        env_file = ".env"

settings = Settings()
