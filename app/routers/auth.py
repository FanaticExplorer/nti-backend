"""
Authentication & authorization router.

Provides the full auth lifecycle:
- **Registration** with GDPR consent tracking and welcome email
- **Login** returning JWT access + refresh tokens
- **Token refresh** to obtain a new access token without re-login
- **Email verification** via token
- **Forgot / reset password** flow (with anti-enumeration on forgot)
- **Current user** retrieval (``GET /me``)

Rate limiting is applied to sensitive endpoints (register, login,
forgot-password) via ``slowapi``.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
)
from app.utils.email import send_welcome_email
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request,
    body: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    - Hashes the password before storing
    - Records GDPR consent timestamp if consent is given
    - Queues a welcome email via background task
    - Returns 409 if the email is already registered

    **Rate limit**: 10 requests per minute per client IP
    """
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        gdpr_consent=body.gdpr_consent,
        gdpr_consent_at=datetime.now(timezone.utc) if body.gdpr_consent else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    background_tasks.add_task(send_welcome_email, user.email)

    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate a user and return JWT tokens.

    Returns an access token (short-lived) and a refresh token (long-lived).
    The access token carries the user's ID and role for authorization.

    - 401 if credentials are invalid
    - 403 if the account is deactivated (``is_active == False``)

    **Rate limit**: 5 requests per minute per client IP
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token_data = {"sub": str(user.id), "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token remains valid until expiry; this endpoint issues
    a fresh pair, allowing the client to rotate tokens.

    Returns 401 if the refresh token is invalid or the user no longer exists.
    """
    payload = decode_token(body.refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    token_data = {"sub": str(user.id), "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token_new = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_new)


@router.post("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a user's email address using a JWT verification token.

    Decodes the token, looks up the user by ``sub`` claim, and sets
    ``is_email_verified`` to ``True``.

    Returns 400 if the token is invalid, 404 if the user is not found.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_email_verified = True
    await db.commit()

    return {"detail": "Email verified successfully"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate the password reset flow.

    Always returns a success response regardless of whether the email
    exists — this prevents email enumeration attacks. If the email is
    found, a password-reset JWT is generated (in production this would
    be sent via email).

    **Rate limit**: 5 requests per minute per client IP
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return success to avoid email enumeration
    if user:
        token_data = {"sub": str(user.id), "purpose": "password_reset"}
        _ = create_access_token(token_data)
        # In production: send email with token

    return {"detail": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reset the user's password using a valid reset token.

    Decodes the JWT, validates the ``purpose`` claim is ``password_reset``,
    looks up the user, and hashes + stores the new password.

    Returns 400 if the token is invalid/missing purpose, 404 if the user
    is not found.
    """
    payload = decode_token(body.token)
    user_id = payload.get("sub")
    purpose = payload.get("purpose")
    if not user_id or purpose != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = hash_password(body.new_password)
    await db.commit()

    return {"detail": "Password reset successfully"}


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Return the currently authenticated user's profile.

    Uses the ``get_current_user`` dependency which extracts and validates
    the JWT from the ``Authorization`` header.

    **Access**: any authenticated user
    """
    return current_user
