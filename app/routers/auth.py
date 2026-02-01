import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import User
from app.auth import authenticate_user, create_access_token
from app.config import settings


router = APIRouter()

@router.post("/register")
def register(username: str, password: str, email: str, db: Session = Depends(get_db)):
    try:
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=User.hash_password(password),
            email=email
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"message": "user created"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="username already exists")

@router.post("/login")
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = authenticate_user(username, password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid Credentials")

    token = create_access_token({
        "user_id": user.id,
        "username": user.username,
        "instance": settings.INSTANCE_NAME
    })
    return {"access_token": token}