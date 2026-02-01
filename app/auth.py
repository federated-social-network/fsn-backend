from datetime import datetime, timedelta
from jose import jwt
from app.config import settings
from app.models import User

def verify_password(plain_password, hashed_password):
    # Assuming User model has a method or you use passlib here
    # Since your code used User.verify_password, we assume the model handles it
    pass 

def create_access_token(data: dict, expires_minutes: int = 60):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def authenticate_user(username: str, password: str, db):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.verify_password(password):
        return None
    return user