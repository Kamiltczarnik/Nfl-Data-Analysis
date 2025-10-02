"""
Game data endpoints for NFL Data Analysis API.

Provides access to schedules, play-by-play, and game-related data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging
import pandas as pd
from pathlib import Path
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

def get_config() -> Dict[str, Any]:
    """Get application configuration."""
    try:
        with open("configs/paths.yaml", 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise HTTPException(status_code=500, detail="Configuration error")

def load_parquet_data(table_name: str, season: Optional[int] = None, week: Optional[int] = None) -> pd.DataFrame:
    """Load data from parquet files."""
    try:
        config = get_config()
        parquet_lake = Path(config['data']['parquet_lake'])
        table_path = parquet_lake / table_name
        
        if not table_path.exists():
            raise HTTPException(status_code=404, detail=f"Table {table_name} not found")
        
        # Find the most recent file
        if season and week:
            # Look for specific season/week
            pattern = f"season={season}/week={week}/*.parquet"
            files = list(table_path.glob(pattern))
            
            # If no week-specific files, try season-only files
            if not files:
                pattern = f"season={season}/*.parquet"
                files = list(table_path.glob(pattern))
        elif season:
            # Look for specific season
            pattern = f"season={season}/**/*.parquet"
            files = list(table_path.glob(pattern))
        else:
            # Look for any files
            files = list(table_path.glob("**/*.parquet"))
        
        if not files:
            raise HTTPException(status_code=404, detail=f"No data found for {table_name}")
        
        # Get the most recent file
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        
        # Load the data
        df = pd.read_parquet(latest_file)
        logger.info(f"Loaded {len(df)} records from {latest_file}")
        
        return df
        
    except Exception as e:
        logger.error(f"Failed to load data from {table_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load data: {str(e)}")

@router.get("/games/schedules")
async def get_schedules(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    limit: int = Query(100, description="Maximum number of records to return")
):
    """Get NFL game schedules with market data."""
    try:
        df = load_parquet_data("schedules", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/pbp")
async def get_play_by_play(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    game_id: Optional[str] = Query(None, description="Specific game ID"),
    limit: int = Query(1000, description="Maximum number of records to return")
):
    """Get play-by-play data with EPA/WP/cp."""
    try:
        df = load_parquet_data("pbp", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if game_id:
            df = df[df['game_id'] == game_id]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "game_id": game_id,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get play-by-play data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/weekly")
async def get_weekly_stats(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    position: Optional[str] = Query(None, description="Player position"),
    limit: int = Query(500, description="Maximum number of records to return")
):
    """Get weekly player statistics."""
    try:
        df = load_parquet_data("weekly", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if position:
            df = df[df['position'] == position]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "position": position,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get weekly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/starters")
async def get_starters(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    position: Optional[str] = Query(None, description="Player position"),
    limit: int = Query(200, description="Maximum number of records to return")
):
    """Get weekly starter tables."""
    try:
        df = load_parquet_data("starters", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if team:
            df = df[df['team'] == team]
        if position:
            df = df[df['position'] == position]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "team": team,
            "position": position,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get starters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/injuries")
async def get_injuries(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(200, description="Maximum number of records to return")
):
    """Get injury reports."""
    try:
        df = load_parquet_data("injuries", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if team:
            df = df[df['team'] == team]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "team": team,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get injuries: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/snap-counts")
async def get_snap_counts(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(500, description="Maximum number of records to return")
):
    """Get player snap counts."""
    try:
        df = load_parquet_data("snap_counts", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if team:
            df = df[df['team'] == team]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "team": team,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get snap counts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/depth-charts")
async def get_depth_charts(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(500, description="Maximum number of records to return")
):
    """Get team depth charts."""
    try:
        df = load_parquet_data("depth_charts", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if team:
            df = df[df['depth_team'] == team]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "team": team,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get depth charts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/rosters")
async def get_rosters(
    season: Optional[int] = Query(None, description="NFL season year"),
    week: Optional[int] = Query(None, description="Specific week"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(200, description="Maximum number of records to return")
):
    """Get team rosters."""
    try:
        df = load_parquet_data("rosters", season, week)
        
        # Apply filters
        if season:
            df = df[df['season'] == season]
        if week:
            df = df[df['week'] == week]
        if team:
            df = df[df['team'] == team]
        
        # Limit results
        df = df.head(limit)
        
        # Convert to dict for JSON response
        result = {
            "data": df.to_dict('records'),
            "count": len(df),
            "season": season,
            "week": week,
            "team": team,
            "columns": list(df.columns)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get rosters: {e}")
        raise HTTPException(status_code=500, detail=str(e))