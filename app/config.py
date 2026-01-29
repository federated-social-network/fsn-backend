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

    class Config:
        env_file = ".env"

settings = Settings()
