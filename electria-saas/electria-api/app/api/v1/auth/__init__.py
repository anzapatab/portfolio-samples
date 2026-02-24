"""Authentication endpoints - Supabase Auth integration."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()


class SignUpRequest(BaseModel):
    """Request body for sign up."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    company_name: str | None = Field(None, max_length=255)


class SignInRequest(BaseModel):
    """Request body for sign in."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response with auth tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


@router.post("/signup")
async def sign_up(request: SignUpRequest) -> dict:
    """
    Create a new user account.

    Sends a confirmation email to the user.
    """
    # TODO: Implement with Supabase Auth
    return {
        "message": "Cuenta creada. Por favor revisa tu email para confirmar.",
        "email": request.email,
    }


@router.post("/signin")
async def sign_in(request: SignInRequest) -> TokenResponse:
    """
    Sign in with email and password.

    Returns access and refresh tokens.
    """
    # TODO: Implement with Supabase Auth
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/signout")
async def sign_out() -> dict:
    """Sign out the current user."""
    # TODO: Implement
    return {"message": "Signed out successfully"}


@router.post("/refresh")
async def refresh_token(request: RefreshRequest) -> TokenResponse:
    """Refresh the access token."""
    # TODO: Implement with Supabase Auth
    raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/forgot-password")
async def forgot_password(email: EmailStr) -> dict:
    """
    Send password reset email.

    Always returns success to prevent email enumeration.
    """
    # TODO: Implement with Supabase Auth
    return {
        "message": "Si existe una cuenta con ese email, recibirás instrucciones para restablecer tu contraseña."
    }


@router.post("/reset-password")
async def reset_password(token: str, new_password: str = Field(..., min_length=8)) -> dict:
    """Reset password with token from email."""
    # TODO: Implement with Supabase Auth
    raise HTTPException(status_code=400, detail="Invalid or expired token")
