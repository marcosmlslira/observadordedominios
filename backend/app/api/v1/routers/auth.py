"""Admin authentication router — login endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Admin login",
)
def login(body: LoginRequest):
    """Authenticate admin and return JWT access token."""
    if (
        not settings.ADMIN_PASSWORD_HASH
        or body.email != settings.ADMIN_EMAIL
        or not verify_password(body.password, settings.ADMIN_PASSWORD_HASH)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": body.email})
    return TokenResponse(access_token=access_token)
