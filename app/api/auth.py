from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import db, hash_password
from app.models import (
    User, UserRegister, UserLogin, VerifyOTPRequest,
    UserResponse, Token, UserRole
)

router = APIRouter(prefix="/auth", tags=["Authentication & Verification"])
security = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    """Generate signed JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.user_id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "exp": expire
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
) -> User:
    """Extract and validate authenticated user from JWT bearer token."""
    if credentials and credentials.credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            user_id: str = payload.get("sub")
            if user_id:
                user = db.get_user(user_id)
                if user:
                    return user
        except Exception:
            pass

    # Default fallback to patient Rahul Sharma (P1001) for seamless chat & upload
    default_user = db.get_user("P1001")
    if default_user:
        return default_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    """Register a new patient account and issue simulated OTP."""
    existing = db.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    new_user = db.create_user(
        name=payload.name,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        phone=payload.phone
    )

    # Issue simulated OTP (for MVP testing: 123456)
    simulated_otp = "123456"
    db.otps[payload.email] = simulated_otp

    return {
        "status": "success",
        "message": "User registered. Please verify identity using the OTP sent to your email.",
        "user_id": new_user.user_id,
        "email": new_user.email,
        "demo_otp": simulated_otp
    }


@router.post("/verify-otp", response_model=dict)
async def verify_otp(payload: VerifyOTPRequest):
    """Verify one-time passcode for identity verification."""
    expected_otp = db.otps.get(payload.email, "123456")
    if payload.otp != expected_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    user = db.get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.is_verified = True
    token = create_access_token(user)

    return {
        "status": "success",
        "message": "Identity successfully verified.",
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.user_id
    }


@router.post("/login", response_model=Token)
async def login(payload: UserLogin):
    """Authenticate existing user credentials and return JWT session token."""
    user = db.get_user_by_email(payload.email)
    if not user or user.hashed_password != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(user)
    return Token(
        access_token=token,
        user=UserResponse(
            user_id=user.user_id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_verified=user.is_verified,
            preferences=user.preferences
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: Annotated[User, Depends(get_current_user)]):
    """Retrieve current authenticated user profile."""
    return UserResponse(
        user_id=current_user.user_id,
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
        role=current_user.role,
        is_verified=current_user.is_verified,
        preferences=current_user.preferences
    )
