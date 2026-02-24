"""Alerts endpoints - User alert configuration and management."""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


class AlertConfig(BaseModel):
    """Alert configuration details."""

    # For price alerts
    barra_codigo: str | None = None
    threshold_value: float | None = None
    comparison: str | None = Field(None, pattern="^(above|below)$")

    # For document alerts
    doc_types: list[str] | None = None
    sources: list[str] | None = None
    keywords: list[str] | None = None


class AlertCreate(BaseModel):
    """Request body for creating an alert."""

    name: str = Field(..., min_length=1, max_length=255)
    alert_type: str = Field(
        ..., pattern="^(price_threshold|new_document|regulatory_change)$"
    )
    config: AlertConfig
    channels: list[str] = Field(default=["email"])
    country_code: str = Field(default="cl", pattern="^[a-z]{2}$")


class AlertResponse(BaseModel):
    """Alert response with full details."""

    id: str
    name: str
    alert_type: str
    config: AlertConfig
    channels: list[str]
    country_code: str
    is_active: bool
    trigger_count: int
    last_triggered_at: datetime | None
    created_at: datetime


class AlertHistoryItem(BaseModel):
    """A single alert trigger history item."""

    id: str
    triggered_at: datetime
    trigger_reason: str
    payload: dict


@router.post("")
async def create_alert(alert: AlertCreate) -> AlertResponse:
    """
    Create a new alert.

    Supported alert types:
    - price_threshold: Triggers when CMg crosses a threshold
    - new_document: Triggers when new documents match criteria
    - regulatory_change: Triggers on regulatory updates
    """
    # TODO: Implement with Supabase
    return AlertResponse(
        id="alert-123",
        name=alert.name,
        alert_type=alert.alert_type,
        config=alert.config,
        channels=alert.channels,
        country_code=alert.country_code,
        is_active=True,
        trigger_count=0,
        last_triggered_at=None,
        created_at=datetime.now(),
    )


@router.get("")
async def list_alerts(
    is_active: bool | None = Query(None),
    alert_type: str | None = Query(None),
) -> list[AlertResponse]:
    """List user's configured alerts."""
    # TODO: Implement with auth
    return []


@router.get("/{alert_id}")
async def get_alert(alert_id: str) -> AlertResponse:
    """Get alert details."""
    # TODO: Implement
    raise HTTPException(status_code=404, detail="Alert not found")


@router.patch("/{alert_id}")
async def update_alert(alert_id: str, updates: dict) -> AlertResponse:
    """Update alert configuration."""
    # TODO: Implement
    raise HTTPException(status_code=404, detail="Alert not found")


@router.delete("/{alert_id}")
async def delete_alert(alert_id: str) -> dict:
    """Delete an alert."""
    # TODO: Implement
    return {"deleted": True}


@router.post("/{alert_id}/toggle")
async def toggle_alert(alert_id: str) -> AlertResponse:
    """Toggle alert active/inactive status."""
    # TODO: Implement
    raise HTTPException(status_code=404, detail="Alert not found")


@router.get("/{alert_id}/history")
async def get_alert_history(
    alert_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AlertHistoryItem]:
    """Get alert trigger history."""
    # TODO: Implement
    return []
