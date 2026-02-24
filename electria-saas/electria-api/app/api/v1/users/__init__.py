"""Users endpoints - Profile and usage management."""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class UserProfile(BaseModel):
    """User profile information."""

    id: str
    email: str
    company_name: str | None
    role: str | None
    country_code: str
    plan: str
    created_at: datetime


class UserUsage(BaseModel):
    """User usage statistics."""

    queries_used: int
    queries_limit: int
    queries_remaining: int
    tokens_used_today: int
    tokens_limit_daily: int
    reset_date: datetime


class UserProfileUpdate(BaseModel):
    """Request body for profile update."""

    company_name: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=100)
    country_code: str | None = Field(None, pattern="^[a-z]{2}$")


@router.get("/me")
async def get_current_user() -> UserProfile:
    """Get current user's profile."""
    # TODO: Implement with auth
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.patch("/me")
async def update_current_user(updates: UserProfileUpdate) -> UserProfile:
    """Update current user's profile."""
    # TODO: Implement with auth
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/me/usage")
async def get_current_user_usage() -> UserUsage:
    """Get current user's usage statistics."""
    # TODO: Implement with auth
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/me/subscription")
async def get_current_user_subscription() -> dict:
    """Get current user's subscription details."""
    # TODO: Implement with Stripe
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.post("/me/subscription/portal")
async def create_billing_portal_session() -> dict:
    """
    Create a Stripe billing portal session.

    Returns a URL to redirect the user to manage their subscription.
    """
    # TODO: Implement with Stripe
    raise HTTPException(status_code=401, detail="Not authenticated")
