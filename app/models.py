from sqlalchemy import Column, String, Boolean, Text
from app.database import Base
import uuid
from app.config import settings
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    origin_instance = Column(String, nullable=False)
    is_remote = Column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String,primary_key=True)
    username = Column(String,unique=True,nullable=False)
    password_hash = Column(String,nullable=False)

    @staticmethod
    def hash_password(password:str) -> str:
        return pwd_context.hash(password)
    
    def verify_password(self,password:str) -> bool:
        return pwd_context.verify(password,self.password_hash)