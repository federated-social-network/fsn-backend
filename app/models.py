from sqlalchemy import Column, String, Boolean, Text
from app.database import Base
import uuid
from app.config import settings

class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    origin_instance = Column(String, nullable=False)
    is_remote = Column(Boolean, default=False)
