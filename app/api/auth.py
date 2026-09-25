from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import db, hash_password
from app.db.repositories.users import verify_password
from app.models import (
    User, UserRegister, UserLogin, VerifyOTPRequest,
    UserResponse, Token, UserRole
)

router = APIRouter(prefix="/auth", tags=["Authentication & Verification"])
security = HTTPBearer(auto_error=False)


import secrets

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
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload: missing subject identifier.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = db.get_user(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account associated with this token not found.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # In explicit demo mode only, fallback to demo patient
    if settings.DEMO_MODE:
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

    # Always enforce PATIENT role for self-registration with is_verified=False pending OTP
    new_user = db.create_user(
        name=payload.name,
        email=payload.email,
        password=payload.password,
        role=UserRole.PATIENT,
        phone=payload.phone,
        is_verified=False
    )

    # Generate secure random 6-digit OTP
    otp_code = str(secrets.randbelow(900000) + 100000)
    db.set_otp(payload.email, otp_code)

    response_data = {
        "status": "success",
        "message": "User registered. Please verify identity using the OTP sent to your email.",
        "user_id": new_user.user_id,
        "email": new_user.email
    }
    # Only expose OTP in response if running in explicit DEMO_MODE
    if settings.DEMO_MODE:
        response_data["demo_otp"] = otp_code

    return response_data


@router.post("/verify-otp", response_model=dict)
async def verify_otp(payload: VerifyOTPRequest):
    """Verify one-time passcode for identity verification and activate account."""
    expected_otp = db.get_otp(payload.email)
    if not expected_otp or payload.otp != expected_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    user = db.get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Persist verification in database and clear single-use OTP
    db.update_user_verification(user.user_id, is_verified=True)
    db.clear_otp(payload.email)
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
    if not user or not verify_password(payload.password, user.hashed_password):
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
