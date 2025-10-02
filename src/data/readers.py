"""
NFL Data Readers

This module provides robust wrappers around nflreadpy with retry logic, caching,
and schema validation for all NFL data sources.

Sprint 1.2: Schedules ingestion with market data validation
"""

import os
import logging
import yaml
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
import pandas as pd
import polars as pl
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
import diskcache
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NFLDataReader:
    """Base class for NFL data readers with common functionality."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        """Initialize reader with configuration."""
        self.config = self._load_config(config_path)
        self.cache = diskcache.Cache(self.config['data']['cache'])
        self._setup_directories()
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def _setup_directories(self):
        """Create necessary directories if they don't exist."""
        directories = [
            self.config['data']['parquet_lake'],
            self.config['data']['raw_snapshots'],
            self.config['data']['cache'],
            self.config['data']['temp']
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, resource: str, season: int, week: Optional[int] = None, **kwargs) -> str:
        """Generate cache key for data."""
        key_parts = [resource, str(season)]
        if week is not None:
            key_parts.append(str(week))
        
        # Add any additional parameters
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        return "_".join(key_parts)
    
    def _save_to_parquet(self, df: Union[pd.DataFrame, pl.DataFrame], 
                        table_name: str, season: int, week: Optional[int] = None) -> str:
        """Save DataFrame to Parquet with partitioning."""
        # Convert polars to pandas if needed
        if isinstance(df, pl.DataFrame):
            df = df.to_pandas()
        
        # Create partition path
        base_path = Path(self.config['data']['parquet_lake']) / table_name
        if week is not None:
            partition_path = base_path / f"season={season}" / f"week={week}"
        else:
            partition_path = base_path / f"season={season}"
        
        partition_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_{season}"
        if week is not None:
            filename += f"_week{week}"
        filename += f"_{timestamp}.parquet"
        
        filepath = partition_path / filename
        
        # Save to parquet
        df.to_parquet(filepath, index=False)
        logger.info(f"Saved {len(df)} records to {filepath}")
        
        return str(filepath)
    
    def _validate_schema(self, df: pd.DataFrame, required_columns: List[str], 
                        table_name: str) -> bool:
        """Validate DataFrame schema against required columns."""
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            logger.error(f"Schema validation failed for {table_name}: missing columns {missing_columns}")
            return False
        
        logger.info(f"Schema validation passed for {table_name}: all required columns present")
        return True


class SchedulesReader(NFLDataReader):
    """Reader for NFL schedules with betting market data."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'game_id', 'season', 'week', 'home_team', 'away_team', 
            'spread_line', 'total_line', 'moneyline'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_schedules(self, season: int) -> pl.DataFrame:
        """Fetch schedules data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching schedules for season {season}")
            
            schedules = nflreadpy.load_schedules(season)
            logger.info(f"Successfully fetched {len(schedules)} games for season {season}")
            
            return schedules
            
        except Exception as e:
            logger.error(f"Failed to fetch schedules for season {season}: {e}")
            raise
    
    def _validate_market_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate market data quality and completeness."""
        validation_results = {
            'total_games': len(df),
            'spread_line_valid': 0,
            'total_line_valid': 0,
            'moneyline_valid': 0,
            'issues': []
        }
        
        # Check spread_line
        spread_valid = df['spread_line'].notna().sum()
        validation_results['spread_line_valid'] = spread_valid
        
        if spread_valid < len(df) * 0.95:  # Less than 95% valid
            validation_results['issues'].append(f"Only {spread_valid}/{len(df)} games have valid spread_line")
        
        # Check total_line
        total_valid = df['total_line'].notna().sum()
        validation_results['total_line_valid'] = total_valid
        
        if total_valid < len(df) * 0.95:
            validation_results['issues'].append(f"Only {total_valid}/{len(df)} games have valid total_line")
        
        # Check moneyline (can be home or away moneyline)
        moneyline_cols = ['home_moneyline', 'away_moneyline']
        moneyline_valid = 0
        for col in moneyline_cols:
            if col in df.columns:
                moneyline_valid += df[col].notna().sum()
        
        validation_results['moneyline_valid'] = moneyline_valid
        
        if moneyline_valid < len(df) * 0.90:  # Less than 90% valid
            validation_results['issues'].append(f"Only {moneyline_valid}/{len(df)} games have valid moneyline data")
        
        # Check for reasonable ranges
        if 'spread_line' in df.columns:
            spread_range = df['spread_line'].dropna()
            if len(spread_range) > 0:
                min_spread, max_spread = spread_range.min(), spread_range.max()
                if min_spread < -30 or max_spread > 30:
                    validation_results['issues'].append(f"Spread range suspicious: {min_spread} to {max_spread}")
        
        if 'total_line' in df.columns:
            total_range = df['total_line'].dropna()
            if len(total_range) > 0:
                min_total, max_total = total_range.min(), total_range.max()
                if min_total < 20 or max_total > 80:
                    validation_results['issues'].append(f"Total range suspicious: {min_total} to {max_total}")
        
        return validation_results
    
    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names and create missing columns if needed."""
        # Convert to pandas if polars
        if isinstance(df, pl.DataFrame):
            df = df.to_pandas()
        
        # Create moneyline column if it doesn't exist
        if 'moneyline' not in df.columns:
            if 'home_moneyline' in df.columns and 'away_moneyline' in df.columns:
                # Use home moneyline as primary (can be enhanced later)
                df['moneyline'] = df['home_moneyline']
            else:
                logger.warning("No moneyline columns found, creating placeholder")
                df['moneyline'] = None
        
        # Ensure required columns exist
        for col in self.required_columns:
            if col not in df.columns:
                logger.warning(f"Required column {col} not found, creating placeholder")
                df[col] = None
        
        return df
    
    def load_schedules(self, season: int, use_cache: bool = True) -> pd.DataFrame:
        """
        Load schedules data for a given season.
        
        Args:
            season: NFL season year
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with schedules and market data
        """
        cache_key = self._get_cache_key('schedules', season)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading schedules for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} games from cache")
                return df
        
        # Fetch from API
        try:
            schedules_df = self._fetch_schedules(season)
            
            # Convert to pandas and standardize
            df = self._standardize_columns(schedules_df)
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'schedules'):
                raise ValueError("Schema validation failed")
            
            # Validate market data
            validation_results = self._validate_market_data(df)
            logger.info(f"Market data validation: {validation_results}")
            
            if validation_results['issues']:
                logger.warning(f"Market data issues found: {validation_results['issues']}")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat(),
                    'validation': validation_results
                }
                logger.info(f"Cached schedules data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'schedules', season)
            
            logger.info(f"Successfully loaded and processed {len(df)} games for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load schedules for season {season}: {e}")
            raise
    
    def get_season_summary(self, season: int) -> Dict[str, Any]:
        """Get summary statistics for a season's schedules."""
        df = self.load_schedules(season)
        
        summary = {
            'season': season,
            'total_games': len(df),
            'weeks': df['week'].nunique() if 'week' in df.columns else 0,
            'teams': len(set(df['home_team'].tolist() + df['away_team'].tolist())) if 'home_team' in df.columns else 0,
            'market_data_quality': self._validate_market_data(df)
        }
        
        return summary


class PBPReader(NFLDataReader):
    """Reader for NFL play-by-play data with EPA/WP/cp validation."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'game_id', 'play_id', 'posteam', 'defteam', 'epa', 'wp', 'cp',
            'down', 'distance', 'yardline_100', 'score_differential', 
            'game_seconds_remaining', 'pass', 'rush', 'play_type'
        ]
        
        # Minimal columns for MVP
        self.mvp_columns = [
            'game_id', 'play_id', 'posteam', 'defteam', 'epa', 'wp', 'cp',
            'down', 'distance', 'yardline_100', 'score_differential',
            'game_seconds_remaining', 'pass', 'rush', 'play_type',
            'season', 'week', 'quarter', 'drive', 'desc'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_pbp(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch PBP data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching PBP data for season {season}" + (f", week {week}" if week else ""))
            
            if week:
                # For specific week (if supported by API)
                pbp = nflreadpy.load_pbp(season)
                # Filter by week
                pbp = pbp.filter(pl.col('week') == week)
            else:
                pbp = nflreadpy.load_pbp(season)
            
            logger.info(f"Successfully fetched {len(pbp)} plays for season {season}")
            return pbp
            
        except Exception as e:
            logger.error(f"Failed to fetch PBP data for season {season}: {e}")
            raise
    
    def _validate_pbp_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate PBP data quality and completeness."""
        validation_results = {
            'total_plays': len(df),
            'epa_valid': 0,
            'wp_valid': 0,
            'cp_valid': 0,
            'posteam_valid': 0,
            'defteam_valid': 0,
            'issues': []
        }
        
        # Check EPA data quality
        epa_valid = df['epa'].notna().sum()
        validation_results['epa_valid'] = epa_valid
        
        if epa_valid < len(df) * 0.95:  # Less than 95% valid
            validation_results['issues'].append(f"Only {epa_valid}/{len(df)} plays have valid EPA")
        
        # Check WP data quality
        wp_valid = df['wp'].notna().sum()
        validation_results['wp_valid'] = wp_valid
        
        if wp_valid < len(df) * 0.95:
            validation_results['issues'].append(f"Only {wp_valid}/{len(df)} plays have valid WP")
        
        # Check CP data quality (lower threshold as it's only for pass plays)
        cp_valid = df['cp'].notna().sum()
        validation_results['cp_valid'] = cp_valid
        
        if cp_valid < len(df) * 0.30:  # CP only exists for pass plays
            validation_results['issues'].append(f"Only {cp_valid}/{len(df)} plays have valid CP")
        
        # Check team data quality
        posteam_valid = df['posteam'].notna().sum()
        defteam_valid = df['defteam'].notna().sum()
        validation_results['posteam_valid'] = posteam_valid
        validation_results['defteam_valid'] = defteam_valid
        
        if posteam_valid < len(df) * 0.90:
            validation_results['issues'].append(f"Only {posteam_valid}/{len(df)} plays have valid posteam")
        
        if defteam_valid < len(df) * 0.90:
            validation_results['issues'].append(f"Only {defteam_valid}/{len(df)} plays have valid defteam")
        
        return validation_results
    
    def _select_mvp_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Select minimal columns for MVP."""
        # Get available columns from MVP list
        available_mvp_cols = [col for col in self.mvp_columns if col in df.columns]
        
        # Add any missing required columns
        missing_required = [col for col in self.required_columns if col not in available_mvp_cols and col in df.columns]
        final_cols = available_mvp_cols + missing_required
        
        logger.info(f"Selected {len(final_cols)} columns for MVP: {final_cols}")
        return df[final_cols]
    
    def load_pbp(self, season: int, week: Optional[int] = None, use_cache: bool = True, mvp_only: bool = True) -> pd.DataFrame:
        """
        Load PBP data for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            mvp_only: Whether to select only MVP columns
            
        Returns:
            DataFrame with PBP data
        """
        cache_key = self._get_cache_key('pbp', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading PBP data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} plays from cache")
                return df
        
        # Fetch from API
        try:
            pbp_df = self._fetch_pbp(season, week)
            
            # Convert to pandas and standardize
            df = pbp_df.to_pandas()
            
            # Select MVP columns if requested
            if mvp_only:
                df = self._select_mvp_columns(df)
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'pbp'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Validate PBP data
            validation_results = self._validate_pbp_data(df)
            logger.info(f"PBP data validation: {validation_results}")
            
            if validation_results['issues']:
                logger.warning(f"PBP data issues found: {validation_results['issues']}")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat(),
                    'validation': validation_results
                }
                logger.info(f"Cached PBP data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'pbp', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} plays for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load PBP data for season {season}: {e}")
            raise


class WeeklyReader(NFLDataReader):
    """Reader for NFL weekly player statistics."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'player_id', 'team', 'season', 'week', 'position'
        ]
        
        # Minimal columns for MVP
        self.mvp_columns = [
            'player_id', 'player_name', 'team', 'season', 'week', 'position',
            'passing_yards', 'passing_tds', 'passing_interceptions', 'passing_epa', 'passing_cpoe',
            'rushing_yards', 'rushing_tds', 'rushing_epa',
            'receiving_yards', 'receiving_tds', 'receiving_epa',
            'targets', 'receptions', 'air_yards', 'yards_after_catch'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_weekly(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch weekly stats from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching weekly stats for season {season}" + (f", week {week}" if week else ""))
            
            weekly = nflreadpy.load_player_stats(season)
            
            if week:
                # Filter by week
                weekly = weekly.filter(pl.col('week') == week)
            
            logger.info(f"Successfully fetched {len(weekly)} weekly records for season {season}")
            return weekly
            
        except Exception as e:
            logger.error(f"Failed to fetch weekly stats for season {season}: {e}")
            raise
    
    def _validate_weekly_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate weekly stats data quality and completeness."""
        validation_results = {
            'total_records': len(df),
            'player_id_valid': 0,
            'team_valid': 0,
            'position_valid': 0,
            'issues': []
        }
        
        # Check player_id data quality
        player_id_valid = df['player_id'].notna().sum()
        validation_results['player_id_valid'] = player_id_valid
        
        if player_id_valid < len(df) * 0.95:
            validation_results['issues'].append(f"Only {player_id_valid}/{len(df)} records have valid player_id")
        
        # Check team data quality
        team_valid = df['team'].notna().sum()
        validation_results['team_valid'] = team_valid
        
        if team_valid < len(df) * 0.95:
            validation_results['issues'].append(f"Only {team_valid}/{len(df)} records have valid team")
        
        # Check position data quality
        position_valid = df['position'].notna().sum()
        validation_results['position_valid'] = position_valid
        
        if position_valid < len(df) * 0.95:
            validation_results['issues'].append(f"Only {position_valid}/{len(df)} records have valid position")
        
        return validation_results
    
    def _select_mvp_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Select minimal columns for MVP."""
        # Get available columns from MVP list
        available_mvp_cols = [col for col in self.mvp_columns if col in df.columns]
        
        # Add any missing required columns
        missing_required = [col for col in self.required_columns if col not in available_mvp_cols and col in df.columns]
        final_cols = available_mvp_cols + missing_required
        
        logger.info(f"Selected {len(final_cols)} columns for MVP: {final_cols}")
        return df[final_cols]
    
    def load_weekly(self, season: int, week: Optional[int] = None, use_cache: bool = True, mvp_only: bool = True) -> pd.DataFrame:
        """
        Load weekly stats for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            mvp_only: Whether to select only MVP columns
            
        Returns:
            DataFrame with weekly stats
        """
        cache_key = self._get_cache_key('weekly', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading weekly stats for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            weekly_df = self._fetch_weekly(season, week)
            
            # Convert to pandas and standardize
            df = weekly_df.to_pandas()
            
            # Select MVP columns if requested
            if mvp_only:
                df = self._select_mvp_columns(df)
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'weekly'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Validate weekly data
            validation_results = self._validate_weekly_data(df)
            logger.info(f"Weekly data validation: {validation_results}")
            
            if validation_results['issues']:
                logger.warning(f"Weekly data issues found: {validation_results['issues']}")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat(),
                    'validation': validation_results
                }
                logger.info(f"Cached weekly data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'weekly', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} weekly records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load weekly stats for season {season}: {e}")
            raise


class RostersReader(NFLDataReader):
    """Reader for NFL team rosters."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'season', 'team', 'position', 'gsis_id', 'full_name', 'status', 'week'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_rosters(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch rosters data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching rosters data for season {season}" + (f", week {week}" if week else ""))
            
            rosters = nflreadpy.load_rosters(season)
            
            if week:
                rosters = rosters.filter(pl.col('week') == week)
            
            logger.info(f"Successfully fetched {len(rosters)} roster records for season {season}")
            return rosters
            
        except Exception as e:
            logger.error(f"Failed to fetch rosters data for season {season}: {e}")
            raise
    
    def load_rosters(self, season: int, week: Optional[int] = None, use_cache: bool = True) -> pd.DataFrame:
        """
        Load rosters data for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with rosters data
        """
        cache_key = self._get_cache_key('rosters', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading rosters data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            rosters_df = self._fetch_rosters(season, week)
            
            # Convert to pandas and standardize
            df = rosters_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'rosters'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Cached rosters data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'rosters', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} roster records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load rosters data for season {season}: {e}")
            raise


class InjuriesReader(NFLDataReader):
    """Reader for NFL injury reports."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'season', 'team', 'week', 'gsis_id', 'position', 'full_name', 
            'report_status', 'practice_status'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_injuries(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch injuries data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching injuries data for season {season}" + (f", week {week}" if week else ""))
            
            injuries = nflreadpy.load_injuries(season)
            
            if week:
                injuries = injuries.filter(pl.col('week') == week)
            
            logger.info(f"Successfully fetched {len(injuries)} injury records for season {season}")
            return injuries
            
        except Exception as e:
            logger.error(f"Failed to fetch injuries data for season {season}: {e}")
            raise
    
    def load_injuries(self, season: int, week: Optional[int] = None, use_cache: bool = True) -> pd.DataFrame:
        """
        Load injuries data for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with injuries data
        """
        cache_key = self._get_cache_key('injuries', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading injuries data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            injuries_df = self._fetch_injuries(season, week)
            
            # Convert to pandas and standardize
            df = injuries_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'injuries'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Cached injuries data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'injuries', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} injury records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load injuries data for season {season}: {e}")
            raise


class SnapCountsReader(NFLDataReader):
    """Reader for NFL snap counts data."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'game_id', 'season', 'week', 'player', 'position', 'team', 
            'opponent', 'offense_snaps', 'defense_snaps'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_snap_counts(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch snap counts data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching snap counts data for season {season}" + (f", week {week}" if week else ""))
            
            snaps = nflreadpy.load_snap_counts(season)
            
            if week:
                snaps = snaps.filter(pl.col('week') == week)
            
            logger.info(f"Successfully fetched {len(snaps)} snap count records for season {season}")
            return snaps
            
        except Exception as e:
            logger.error(f"Failed to fetch snap counts data for season {season}: {e}")
            raise
    
    def load_snap_counts(self, season: int, week: Optional[int] = None, use_cache: bool = True) -> pd.DataFrame:
        """
        Load snap counts data for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with snap counts data
        """
        cache_key = self._get_cache_key('snap_counts', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading snap counts data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            snaps_df = self._fetch_snap_counts(season, week)
            
            # Convert to pandas and standardize
            df = snaps_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'snap_counts'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Cached snap counts data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'snap_counts', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} snap count records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load snap counts data for season {season}: {e}")
            raise


class DepthChartsReader(NFLDataReader):
    """Reader for NFL depth charts data."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'season', 'week', 'depth_team', 'position', 'gsis_id', 
            'full_name', 'depth_position'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_depth_charts(self, season: int, week: Optional[int] = None) -> pl.DataFrame:
        """Fetch depth charts data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching depth charts data for season {season}" + (f", week {week}" if week else ""))
            
            depth = nflreadpy.load_depth_charts(season)
            
            if week:
                depth = depth.filter(pl.col('week') == week)
            
            logger.info(f"Successfully fetched {len(depth)} depth chart records for season {season}")
            return depth
            
        except Exception as e:
            logger.error(f"Failed to fetch depth charts data for season {season}: {e}")
            raise
    
    def load_depth_charts(self, season: int, week: Optional[int] = None, use_cache: bool = True) -> pd.DataFrame:
        """
        Load depth charts data for a given season and optionally week.
        
        Args:
            season: NFL season year
            week: Specific week (optional)
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with depth charts data
        """
        cache_key = self._get_cache_key('depth_charts', season, week=week)
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading depth charts data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            depth_df = self._fetch_depth_charts(season, week)
            
            # Convert to pandas and standardize
            df = depth_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'depth_charts'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Cached depth charts data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'depth_charts', season, week)
            
            logger.info(f"Successfully loaded and processed {len(df)} depth chart records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load depth charts data for season {season}: {e}")
            raise


class PlayersReader(NFLDataReader):
    """Reader for NFL players data with ID mapping."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'gsis_id', 'display_name', 'first_name', 'last_name', 'position', 
            'nfl_id', 'pfr_id', 'pff_id', 'espn_id'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_players(self) -> pl.DataFrame:
        """Fetch players data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info("Fetching players data")
            
            players = nflreadpy.load_players()
            
            logger.info(f"Successfully fetched {len(players)} player records")
            return players
            
        except Exception as e:
            logger.error(f"Failed to fetch players data: {e}")
            raise
    
    def load_players(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Load players data for ID mapping.
        
        Args:
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with players data
        """
        cache_key = "players_all"
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info("Loading players data from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            players_df = self._fetch_players()
            
            # Convert to pandas and standardize
            df = players_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'players'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info("Cached players data")
            
            # Save to parquet
            self._save_to_parquet(df, 'players', 2024)  # Players data is not season-specific
            
            logger.info(f"Successfully loaded and processed {len(df)} player records")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load players data: {e}")
            raise


class TeamsReader(NFLDataReader):
    """Reader for NFL teams data with ID mapping."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'season', 'team', 'nfl', 'nfl_team_id', 'espn', 'pfr', 'pff', 'full'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_teams(self, season: int) -> pl.DataFrame:
        """Fetch teams data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info(f"Fetching teams data for season {season}")
            
            teams = nflreadpy.load_teams()
            
            # Filter by season if needed
            teams = teams.filter(pl.col('season') == season)
            
            logger.info(f"Successfully fetched {len(teams)} team records for season {season}")
            return teams
            
        except Exception as e:
            logger.error(f"Failed to fetch teams data for season {season}: {e}")
            raise
    
    def load_teams(self, season: int, use_cache: bool = True) -> pd.DataFrame:
        """
        Load teams data for ID mapping.
        
        Args:
            season: NFL season year
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with teams data
        """
        cache_key = f"teams_{season}"
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info(f"Loading teams data for season {season} from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            teams_df = self._fetch_teams(season)
            
            # Convert to pandas and standardize
            df = teams_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'teams'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Cached teams data for season {season}")
            
            # Save to parquet
            self._save_to_parquet(df, 'teams', season)
            
            logger.info(f"Successfully loaded and processed {len(df)} team records for season {season}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load teams data for season {season}: {e}")
            raise


class FFPlayerIdsReader(NFLDataReader):
    """Reader for Fantasy Football player IDs data."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        super().__init__(config_path)
        self.required_columns = [
            'gsis_id', 'espn_id', 'pfr_id', 'pff_id', 'sportradar_id', 
            'name', 'position', 'team'
        ]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError))
    )
    def _fetch_ff_playerids(self) -> pl.DataFrame:
        """Fetch FF player IDs data from nflreadpy with retry logic."""
        try:
            import nflreadpy
            logger.info("Fetching FF player IDs data")
            
            ff_ids = nflreadpy.load_ff_playerids()
            
            logger.info(f"Successfully fetched {len(ff_ids)} FF player ID records")
            return ff_ids
            
        except Exception as e:
            logger.error(f"Failed to fetch FF player IDs data: {e}")
            raise
    
    def load_ff_playerids(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Load FF player IDs data for ID mapping.
        
        Args:
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with FF player IDs data
        """
        cache_key = "ff_playerids_all"
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            logger.info("Loading FF player IDs data from cache")
            cached_data = self.cache[cache_key]
            if isinstance(cached_data, dict) and 'data' in cached_data:
                df = pd.DataFrame(cached_data['data'])
                logger.info(f"Loaded {len(df)} records from cache")
                return df
        
        # Fetch from API
        try:
            ff_ids_df = self._fetch_ff_playerids()
            
            # Convert to pandas and standardize
            df = ff_ids_df.to_pandas()
            
            # Validate schema
            if not self._validate_schema(df, self.required_columns, 'ff_playerids'):
                logger.warning("Schema validation failed, but continuing with available columns")
            
            # Cache the data
            if use_cache:
                self.cache[cache_key] = {
                    'data': df.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info("Cached FF player IDs data")
            
            # Save to parquet
            self._save_to_parquet(df, 'ff_playerids', 2024)  # FF IDs data is not season-specific
            
            logger.info(f"Successfully loaded and processed {len(df)} FF player ID records")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load FF player IDs data: {e}")
            raise


def main():
    """CLI interface for testing the readers."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Data Readers')
    parser.add_argument('--season', type=int, default=2024, help='Season to load')
    parser.add_argument('--week', type=int, help='Specific week to load')
    parser.add_argument('--resource', choices=['schedules', 'pbp', 'weekly', 'rosters', 'injuries', 'snap_counts', 'depth_charts', 'players', 'teams', 'ff_playerids'], default='schedules', help='Resource to load')
    parser.add_argument('--no-cache', action='store_true', help='Disable caching')
    parser.add_argument('--no-mvp', action='store_true', help='Load all columns (not just MVP)')
    
    args = parser.parse_args()
    
    if args.resource == 'schedules':
        reader = SchedulesReader()
        df = reader.load_schedules(args.season, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} games for season {args.season}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show summary
        summary = reader.get_season_summary(args.season)
        print(f"\nSeason Summary:")
        print(f"Total games: {summary['total_games']}")
        print(f"Weeks: {summary['weeks']}")
        print(f"Teams: {summary['teams']}")
        print(f"Market data quality: {summary['market_data_quality']}")
    
    elif args.resource == 'pbp':
        reader = PBPReader()
        df = reader.load_pbp(args.season, week=args.week, use_cache=not args.no_cache, mvp_only=not args.no_mvp)
        print(f"Loaded {len(df)} plays for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        epa_valid = df['epa'].notna().sum() if 'epa' in df.columns else 0
        wp_valid = df['wp'].notna().sum() if 'wp' in df.columns else 0
        cp_valid = df['cp'].notna().sum() if 'cp' in df.columns else 0
        print(f"\nData Quality:")
        print(f"EPA valid: {epa_valid}/{len(df)} ({epa_valid/len(df)*100:.1f}%)")
        print(f"WP valid: {wp_valid}/{len(df)} ({wp_valid/len(df)*100:.1f}%)")
        print(f"CP valid: {cp_valid}/{len(df)} ({cp_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'weekly':
        reader = WeeklyReader()
        df = reader.load_weekly(args.season, week=args.week, use_cache=not args.no_cache, mvp_only=not args.no_mvp)
        print(f"Loaded {len(df)} weekly records for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        player_id_valid = df['player_id'].notna().sum() if 'player_id' in df.columns else 0
        team_valid = df['team'].notna().sum() if 'team' in df.columns else 0
        position_valid = df['position'].notna().sum() if 'position' in df.columns else 0
        print(f"\nData Quality:")
        print(f"Player ID valid: {player_id_valid}/{len(df)} ({player_id_valid/len(df)*100:.1f}%)")
        print(f"Team valid: {team_valid}/{len(df)} ({team_valid/len(df)*100:.1f}%)")
        print(f"Position valid: {position_valid}/{len(df)} ({position_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'rosters':
        reader = RostersReader()
        df = reader.load_rosters(args.season, week=args.week, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} roster records for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        gsis_id_valid = df['gsis_id'].notna().sum() if 'gsis_id' in df.columns else 0
        team_valid = df['team'].notna().sum() if 'team' in df.columns else 0
        position_valid = df['position'].notna().sum() if 'position' in df.columns else 0
        print(f"\nData Quality:")
        print(f"GSIS ID valid: {gsis_id_valid}/{len(df)} ({gsis_id_valid/len(df)*100:.1f}%)")
        print(f"Team valid: {team_valid}/{len(df)} ({team_valid/len(df)*100:.1f}%)")
        print(f"Position valid: {position_valid}/{len(df)} ({position_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'injuries':
        reader = InjuriesReader()
        df = reader.load_injuries(args.season, week=args.week, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} injury records for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        gsis_id_valid = df['gsis_id'].notna().sum() if 'gsis_id' in df.columns else 0
        team_valid = df['team'].notna().sum() if 'team' in df.columns else 0
        report_status_valid = df['report_status'].notna().sum() if 'report_status' in df.columns else 0
        print(f"\nData Quality:")
        print(f"GSIS ID valid: {gsis_id_valid}/{len(df)} ({gsis_id_valid/len(df)*100:.1f}%)")
        print(f"Team valid: {team_valid}/{len(df)} ({team_valid/len(df)*100:.1f}%)")
        print(f"Report status valid: {report_status_valid}/{len(df)} ({report_status_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'snap_counts':
        reader = SnapCountsReader()
        df = reader.load_snap_counts(args.season, week=args.week, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} snap count records for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        player_valid = df['player'].notna().sum() if 'player' in df.columns else 0
        team_valid = df['team'].notna().sum() if 'team' in df.columns else 0
        offense_snaps_valid = df['offense_snaps'].notna().sum() if 'offense_snaps' in df.columns else 0
        print(f"\nData Quality:")
        print(f"Player valid: {player_valid}/{len(df)} ({player_valid/len(df)*100:.1f}%)")
        print(f"Team valid: {team_valid}/{len(df)} ({team_valid/len(df)*100:.1f}%)")
        print(f"Offense snaps valid: {offense_snaps_valid}/{len(df)} ({offense_snaps_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'depth_charts':
        reader = DepthChartsReader()
        df = reader.load_depth_charts(args.season, week=args.week, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} depth chart records for season {args.season}")
        if args.week:
            print(f"Week: {args.week}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        gsis_id_valid = df['gsis_id'].notna().sum() if 'gsis_id' in df.columns else 0
        depth_team_valid = df['depth_team'].notna().sum() if 'depth_team' in df.columns else 0
        depth_position_valid = df['depth_position'].notna().sum() if 'depth_position' in df.columns else 0
        print(f"\nData Quality:")
        print(f"GSIS ID valid: {gsis_id_valid}/{len(df)} ({gsis_id_valid/len(df)*100:.1f}%)")
        print(f"Depth team valid: {depth_team_valid}/{len(df)} ({depth_team_valid/len(df)*100:.1f}%)")
        print(f"Depth position valid: {depth_position_valid}/{len(df)} ({depth_position_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'players':
        reader = PlayersReader()
        df = reader.load_players(use_cache=not args.no_cache)
        print(f"Loaded {len(df)} player records")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        gsis_id_valid = df['gsis_id'].notna().sum() if 'gsis_id' in df.columns else 0
        display_name_valid = df['display_name'].notna().sum() if 'display_name' in df.columns else 0
        position_valid = df['position'].notna().sum() if 'position' in df.columns else 0
        print(f"\nData Quality:")
        print(f"GSIS ID valid: {gsis_id_valid}/{len(df)} ({gsis_id_valid/len(df)*100:.1f}%)")
        print(f"Display name valid: {display_name_valid}/{len(df)} ({display_name_valid/len(df)*100:.1f}%)")
        print(f"Position valid: {position_valid}/{len(df)} ({position_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'teams':
        reader = TeamsReader()
        df = reader.load_teams(args.season, use_cache=not args.no_cache)
        print(f"Loaded {len(df)} team records for season {args.season}")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        team_valid = df['team'].notna().sum() if 'team' in df.columns else 0
        nfl_team_id_valid = df['nfl_team_id'].notna().sum() if 'nfl_team_id' in df.columns else 0
        full_name_valid = df['full'].notna().sum() if 'full' in df.columns else 0
        print(f"\nData Quality:")
        print(f"Team valid: {team_valid}/{len(df)} ({team_valid/len(df)*100:.1f}%)")
        print(f"NFL Team ID valid: {nfl_team_id_valid}/{len(df)} ({nfl_team_id_valid/len(df)*100:.1f}%)")
        print(f"Full name valid: {full_name_valid}/{len(df)} ({full_name_valid/len(df)*100:.1f}%)")
    
    elif args.resource == 'ff_playerids':
        reader = FFPlayerIdsReader()
        df = reader.load_ff_playerids(use_cache=not args.no_cache)
        print(f"Loaded {len(df)} FF player ID records")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        # Show data quality
        gsis_id_valid = df['gsis_id'].notna().sum() if 'gsis_id' in df.columns else 0
        name_valid = df['name'].notna().sum() if 'name' in df.columns else 0
        position_valid = df['position'].notna().sum() if 'position' in df.columns else 0
        print(f"\nData Quality:")
        print(f"GSIS ID valid: {gsis_id_valid}/{len(df)} ({gsis_id_valid/len(df)*100:.1f}%)")
        print(f"Name valid: {name_valid}/{len(df)} ({name_valid/len(df)*100:.1f}%)")
        print(f"Position valid: {position_valid}/{len(df)} ({position_valid/len(df)*100:.1f}%)")


if __name__ == "__main__":
    main()
