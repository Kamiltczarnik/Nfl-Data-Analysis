"""
NFL Data Analysis API

FastAPI application for NFL game prediction and data access.
This is a scaffold implementation with no business logic.

Sprint 1.7: FastAPI scaffold (no logic)
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Any, Optional, List
import yaml
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="NFL Data Analysis API",
    description="API for NFL game prediction and data access",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global configuration
config = None

def load_config() -> Dict[str, Any]:
    """Load application configuration."""
    global config
    if config is None:
        try:
            config_path = Path("configs/paths.yaml")
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise HTTPException(status_code=500, detail="Configuration error")
    return config

def get_config() -> Dict[str, Any]:
    """Dependency to get configuration."""
    return load_config()

# Include routers
from src.api.routers import health, games, predict

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(games.router, prefix="/api/v1", tags=["games"])
app.include_router(predict.router, prefix="/api/v1", tags=["predict"])

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "NFL Data Analysis API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/api/v1/info")
async def api_info(config: Dict[str, Any] = Depends(get_config)):
    """API information endpoint."""
    return {
        "api_name": "NFL Data Analysis API",
        "version": "1.0.0",
        "description": "API for NFL game prediction and data access",
        "data_sources": {
            "schedules": "NFL game schedules with market data",
            "pbp": "Play-by-play data with EPA/WP/cp",
            "weekly": "Weekly player statistics",
            "rosters": "Team rosters",
            "injuries": "Injury reports",
            "snap_counts": "Player snap counts",
            "depth_charts": "Team depth charts",
            "starters": "Weekly starter tables",
            "players": "Player information",
            "teams": "Team information"
        },
        "endpoints": {
            "health": "/api/v1/health",
            "games": "/api/v1/games",
            "predict": "/api/v1/predict"
        }
    }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)