from sqlalchemy import Column, String, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import settings
from passlib.context import CryptContext
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from datetime import datetime
import uuid

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True)
    content = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    origin_instance = Column(String, nullable=False)
    is_remote = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

class User(Base):
    __tablename__ = "users"

    id = Column(String,primary_key=True)
    username = Column(String,unique=True,nullable=False)
    password_hash = Column(String,nullable=False)
    email = Column(String,nullable=True)
    #profile_photo_url = Column(String,nullable=True)

    @staticmethod
    def hash_password(password:str) -> str:
        return pwd_context.hash(password)
    
    def verify_password(self,password:str) -> bool:
        return pwd_context.verify(password,self.password_hash)
    
class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    object = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_local = Column(Boolean, default=True)
    is_delivered = Column(Boolean, default=False)
