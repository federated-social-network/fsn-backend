import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import User
from app.auth import (
    authenticate_user, 
    create_access_token,
    initiate_password_reset,
    verify_otp,
    reset_password
)
from app.config import settings


router = APIRouter()


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyOTPRequest(BaseModel):
    email: str
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


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


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Initiate password reset by sending OTP to email
    """
    success, message = initiate_password_reset(request.email, db)
    
    if not success:
        raise HTTPException(status_code=404, detail=message)
    
    return {"message": message}


@router.post("/verify-otp")
def verify_password_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Verify OTP sent to email
    """
    success, message, reset_token = verify_otp(request.email, request.otp, db)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "message": message,
        "reset_token": reset_token
    }


@router.post("/reset-password")
def reset_user_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using reset token
    """
    success, message = reset_password(request.reset_token, request.new_password, db)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {"message": message}
