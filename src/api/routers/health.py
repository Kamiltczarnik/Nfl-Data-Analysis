"""
Health check endpoints for NFL Data Analysis API.

Provides system health and data availability status.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
import logging
from pathlib import Path
import os
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

def check_data_availability() -> Dict[str, Any]:
    """Check data availability across all sources."""
    data_status = {}
    
    # Check parquet lake structure
    parquet_lake = Path("data/parquet")
    if parquet_lake.exists():
        data_status["parquet_lake"] = {
            "exists": True,
            "path": str(parquet_lake),
            "tables": []
        }
        
        # Check each table
        tables = ["schedules", "pbp", "weekly", "rosters", "injuries", 
                 "snap_counts", "depth_charts", "starters", "players", "teams", "ff_playerids"]
        
        for table in tables:
            table_path = parquet_lake / table
            if table_path.exists():
                # Count files
                parquet_files = list(table_path.glob("**/*.parquet"))
                data_status["parquet_lake"]["tables"].append({
                    "name": table,
                    "exists": True,
                    "files": len(parquet_files),
                    "path": str(table_path)
                })
            else:
                data_status["parquet_lake"]["tables"].append({
                    "name": table,
                    "exists": False,
                    "files": 0,
                    "path": str(table_path)
                })
    else:
        data_status["parquet_lake"] = {
            "exists": False,
            "path": str(parquet_lake),
            "tables": []
        }
    
    return data_status

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "NFL Data Analysis API"
    }

@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with data availability."""
    try:
        data_status = check_data_availability()
        
        # Check configuration files
        config_files = {
            "paths": Path("configs/paths.yaml").exists(),
            "features": Path("configs/features.yaml").exists(),
            "requirements": Path("requirements.txt").exists()
        }
        
        # Check source modules
        source_modules = {
            "readers": Path("src/data/readers.py").exists(),
            "transforms": Path("src/data/transforms.py").exists(),
            "starters": Path("src/data/starters.py").exists()
        }
        
        # Overall health status
        overall_healthy = (
            data_status["parquet_lake"]["exists"] and
            all(config_files.values()) and
            all(source_modules.values())
        )
        
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.now().isoformat(),
            "service": "NFL Data Analysis API",
            "data_availability": data_status,
            "configuration": config_files,
            "source_modules": source_modules,
            "overall_healthy": overall_healthy
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@router.get("/health/data")
async def data_health_check():
    """Data-specific health check."""
    try:
        data_status = check_data_availability()
        
        # Count total files
        total_files = sum(
            table["files"] for table in data_status["parquet_lake"]["tables"]
        )
        
        # Check for recent data (last 7 days)
        recent_data = []
        parquet_lake = Path("data/parquet")
        
        if parquet_lake.exists():
            for table_path in parquet_lake.glob("**/*.parquet"):
                file_time = datetime.fromtimestamp(table_path.stat().st_mtime)
                if (datetime.now() - file_time).days <= 7:
                    recent_data.append({
                        "file": str(table_path),
                        "modified": file_time.isoformat()
                    })
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "data_summary": {
                "total_tables": len(data_status["parquet_lake"]["tables"]),
                "total_files": total_files,
                "recent_files": len(recent_data)
            },
            "data_availability": data_status,
            "recent_data": recent_data[:10]  # Show first 10 recent files
        }
        
    except Exception as e:
        logger.error(f"Data health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Data health check failed: {str(e)}")

@router.get("/health/ready")
async def readiness_check():
    """Readiness check for deployment."""
    try:
        # Check critical dependencies
        critical_checks = {
            "parquet_lake_exists": Path("data/parquet").exists(),
            "config_files_exist": all([
                Path("configs/paths.yaml").exists(),
                Path("configs/features.yaml").exists()
            ]),
            "source_modules_exist": all([
                Path("src/data/readers.py").exists(),
                Path("src/data/transforms.py").exists(),
                Path("src/data/starters.py").exists()
            ])
        }
        
        ready = all(critical_checks.values())
        
        return {
            "ready": ready,
            "timestamp": datetime.now().isoformat(),
            "checks": critical_checks
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "ready": False,
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }