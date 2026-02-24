"""
ELECTRIA API - Main Application Entry Point

Electric Market Intelligence Platform
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.
    Setup and teardown logic for the application.
    """
    # Startup
    print(f"Starting {settings.app_name} in {settings.app_env} mode...")

    # TODO: Initialize connections
    # - Supabase client
    # - Pinecone index
    # - Redis connection

    yield

    # Shutdown
    print(f"Shutting down {settings.app_name}...")
    # TODO: Close connections gracefully


def create_app() -> FastAPI:
    """Application factory."""

    app = FastAPI(
        title="ELECTRIA API",
        description="Inteligencia Artificial para el Mercado Eléctrico",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # Local frontend
            "https://electria.cl",    # Production
            "https://*.vercel.app",   # Vercel previews
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


# Create app instance
app = create_app()


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": "ELECTRIA API",
        "docs": "/docs" if settings.debug else "Disabled in production",
        "health": "/health",
    }
