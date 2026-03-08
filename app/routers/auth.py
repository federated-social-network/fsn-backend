import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    initiate_password_reset,
    reset_password,
    verify_otp,
)
from app.config import settings
from app.database import get_db
from app.models import User
from app.services.crypto import generate_rsa_keypair

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
    username = username.strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise HTTPException(
            status_code=400, detail="Username can only contain alphanumeric characters, dashes (-), and underscores (_)"
        )
    try:
        private_key, public_key = generate_rsa_keypair()
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=User.hash_password(password),
            email=email,
            public_key=public_key,
            private_key=private_key,
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
    username = username.strip()
    user = authenticate_user(username, password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid Credentials")

    payload = {"user_id": user.id, "username": user.username,
               "instance": settings.INSTANCE_NAME}
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)

    return {"access_token": access_token, "refresh_token": refresh_token}


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

    return {"message": message, "reset_token": reset_token}


@router.post("/reset-password")
def reset_user_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using reset token
    """
    success, message = reset_password(
        request.reset_token, request.new_password, db)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"message": message}


@router.post("/refresh")
def refresh_token(refresh_token: str):

    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM])

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        new_access_token = create_access_token(
            {"user_id": payload["user_id"], "username": payload["username"],
                "instance": payload["instance"]}
        )

        return {"access_token": new_access_token}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
