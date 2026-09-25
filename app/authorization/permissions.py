"""Centralized authorization utilities and dependencies for ApolloCare."""

from typing import Annotated, Callable
from fastapi import Depends, HTTPException, status
from app.models import User, UserRole
from app.api.auth import get_current_user


def require_authenticated_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Ensure that the caller has a valid, verified authenticated session."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please complete OTP verification first."
        )
    return current_user


def require_role(*allowed_roles: UserRole) -> Callable:
    """Dependency factory enforcing membership in specified roles."""
    def role_checker(current_user: Annotated[User, Depends(require_authenticated_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires one of role(s): {[r.value for r in allowed_roles]}"
            )
        return current_user
    return role_checker


def require_admin(current_user: Annotated[User, Depends(require_authenticated_user)]) -> User:
    """Enforce Administrator privileges."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrator privileges required."
        )
    return current_user


def require_staff_access(current_user: Annotated[User, Depends(require_authenticated_user)]) -> User:
    """Enforce Hospital Staff or Doctor or Admin access."""
    if current_user.role not in (UserRole.STAFF, UserRole.DOCTOR, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Hospital staff, doctor, or administrator role required."
        )
    return current_user


def check_patient_resource_ownership(current_user: User, resource_owner_id: str):
    """Enforce patient resource isolation: Patients cannot access other patients' resources."""
    if current_user.role == UserRole.PATIENT and current_user.user_id != resource_owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not authorized to view or modify another patient's data."
        )
