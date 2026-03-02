from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    ForeignKey,
    JSON,
    Integer,
    UniqueConstraint,
)
from app.database import Base
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
    image_url = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    origin_instance = Column(String, nullable=False)
    is_remote = Column(Boolean, default=False)
    like_count = Column(Integer, default=0)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    public_key = Column(Text, nullable=True)
    private_key = Column(Text, nullable=True)
    bio = Column(String,nullable=True)
    display_name = Column(String, nullable=True)

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.password_hash)


class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    object = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_local = Column(Boolean, default=True)
    is_delivered = Column(Boolean, default=False)


class Connection(Base):
    __tablename__ = "connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    local_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    target_local_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    remote_actor_url = Column(String, nullable=True)
    remote_inbox_url = Column(String, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    otp = Column(String, nullable=False)
    otp_expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Like(Base):
    __tablename__ = "likes"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="unique_user_post_like"),
    )
