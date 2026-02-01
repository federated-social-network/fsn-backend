from datetime import datetime, timedelta
from jose import jwt
from app.config import settings
from app.models import User, PasswordReset
from app.email_service import generate_otp, send_otp_email
import uuid

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


def initiate_password_reset(email: str, db) -> tuple[bool, str]:
    """
    Initiate password reset by sending OTP to email
    Returns (success, message)
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False, "Email not found"
    
    # Generate OTP
    otp = generate_otp()
    otp_expiry = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    
    # Create password reset record
    reset_record = PasswordReset(
        id=str(uuid.uuid4()),
        user_id=user.id,
        otp=otp,
        otp_expires_at=otp_expiry,
        is_used=False
    )
    
    # Send OTP via email
    if send_otp_email(email, otp, user.username):
        db.add(reset_record)
        db.commit()
        return True, "OTP sent to your email"
    else:
        return False, "Failed to send OTP"


def verify_otp(email: str, otp: str, db) -> tuple[bool, str, str]:
    """
    Verify OTP for password reset
    Returns (success, message, reset_token)
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False, "Email not found", ""
    
    # Find valid OTP
    reset_record = db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id,
        PasswordReset.otp == otp,
        PasswordReset.is_used == False,
        PasswordReset.otp_expires_at > datetime.utcnow()
    ).first()
    
    if not reset_record:
        return False, "Invalid or expired OTP", ""
    
    # Mark OTP as used
    reset_record.is_used = True
    db.commit()
    
    # Create a reset token valid for 30 minutes
    reset_token = jwt.encode(
        {
            "user_id": user.id,
            "email": email,
            "purpose": "password_reset",
            "exp": datetime.utcnow() + timedelta(minutes=30)
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return True, "OTP verified successfully", reset_token


def reset_password(reset_token: str, new_password: str, db) -> tuple[bool, str]:
    """
    Reset password using reset token
    Returns (success, message)
    """
    try:
        payload = jwt.decode(reset_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        purpose = payload.get("purpose")
        
        if purpose != "password_reset":
            return False, "Invalid token"
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"
        
        user.password_hash = User.hash_password(new_password)
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return True, "Password reset successfully"
    except jwt.ExpiredSignatureError:
        return False, "Token expired"
    except Exception as e:
        return False, f"Error: {str(e)}"
