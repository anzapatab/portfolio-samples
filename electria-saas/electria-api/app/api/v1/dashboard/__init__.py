"""Dashboard endpoints - Market data and analytics."""

from datetime import datetime
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class MarginalCost(BaseModel):
    """Marginal cost data point."""

    timestamp: datetime
    barra_codigo: str
    barra_nombre: str
    cmg_usd_mwh: float
    cmg_clp_mwh: float | None


class GenerationData(BaseModel):
    """Generation data by technology."""

    timestamp: datetime
    tecnologia: str
    generacion_mwh: float
    porcentaje: float


class DemandData(BaseModel):
    """System demand data."""

    timestamp: datetime
    zona: str
    demanda_mwh: float


class DashboardSummary(BaseModel):
    """Summary data for dashboard overview."""

    cmg_promedio: float
    cmg_variacion_24h: float
    demanda_actual_mw: float
    demanda_variacion_24h: float
    generacion_renovable_pct: float
    ultima_actualizacion: datetime


@router.get("/summary")
async def get_dashboard_summary(
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
) -> DashboardSummary:
    """
    Get dashboard summary with key metrics.

    Returns current marginal cost average, demand, and renewable generation percentage.
    """
    # TODO: Implement with TimescaleDB queries
    return DashboardSummary(
        cmg_promedio=42.5,
        cmg_variacion_24h=2.3,
        demanda_actual_mw=10234.0,
        demanda_variacion_24h=-1.2,
        generacion_renovable_pct=57.0,
        ultima_actualizacion=datetime.now(),
    )


@router.get("/cmg")
async def get_marginal_costs(
    barra: str | None = Query(None, description="Filter by barra code"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", pattern="^(1h|1d|1w|1M)$", description="Aggregation interval"),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(168, ge=1, le=8760),  # Default: 1 week of hourly data
) -> list[MarginalCost]:
    """
    Get marginal cost time series.

    Supports filtering by barra and date range, with different aggregation intervals.
    """
    # TODO: Implement with TimescaleDB
    return []


@router.get("/generation")
async def get_generation_data(
    tecnologia: str | None = Query(None, description="Filter by technology"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    interval: str = Query("1h", pattern="^(1h|1d|1w|1M)$"),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(168, ge=1, le=8760),
) -> list[GenerationData]:
    """
    Get generation data by technology.

    Returns generation mix over time with breakdown by technology type.
    """
    # TODO: Implement with TimescaleDB
    return []


@router.get("/demand")
async def get_demand_data(
    zona: str | None = Query(None, description="Filter by zone"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    interval: str = Query("1h", pattern="^(1h|1d|1w|1M)$"),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(168, ge=1, le=8760),
) -> list[DemandData]:
    """
    Get system demand data.

    Returns demand time series, optionally filtered by zone.
    """
    # TODO: Implement with TimescaleDB
    return []


@router.get("/barras")
async def list_barras(
    search: str | None = Query(None, description="Search by name or code"),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """
    List available barras for filtering.

    Used for autocomplete in dashboard filters.
    """
    # TODO: Implement from PostgreSQL catalog
    return []


@router.get("/centrales")
async def list_centrales(
    tecnologia: str | None = Query(None),
    search: str | None = Query(None),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """
    List generation plants.

    Used for filtering and plant-specific analysis.
    """
    # TODO: Implement from PostgreSQL catalog
    return []
