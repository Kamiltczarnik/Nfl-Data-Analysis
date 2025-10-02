"""
Rolling features module for Sprint 2.1.

This module implements rolling window calculations for offensive and defensive EPA,
success rates, and other key metrics as specified in Sprint 2.1.

Features implemented:
- off_epa_play_l3: Offensive EPA per play (last 3 games)
- def_epa_play_allowed_l3: Defensive EPA allowed per play (last 3 games)
- early_down_pass_epa_l3: Early down pass EPA (last 3 games)
- Additional rolling features as configured
"""

import pandas as pd
import numpy as np
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from src.data.readers import PBPReader, SchedulesReader
from src.data.transforms import IDMapper

logger = logging.getLogger(__name__)


class RollingFeatureCalculator:
    """
    Calculates rolling window features for NFL teams.
    
    Implements configurable sliding windows (L3/L5/EWMA) with early-season
    shrinkage when weeks < window size.
    """
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize the rolling feature calculator."""
        self.config = self._load_config(config_path)
        self.windows = self.config['windows']
        self.id_mapper = IDMapper()
        
        # Window configurations
        self.l3_window = self.windows['l3']
        self.l5_window = self.windows['l5']
        self.l6_window = self.windows['l6']
        self.ewma_alpha = self.windows['ewma']['alpha']
        self.ewma_min_periods = self.windows['ewma']['min_periods']
        self.early_season_min_weeks = self.windows['early_season']['min_weeks_for_window']
        self.early_season_shrinkage = self.windows['early_season']['shrinkage_factor']
        
        logger.info(f"Initialized RollingFeatureCalculator with windows: L3={self.l3_window}, L5={self.l5_window}, L6={self.l6_window}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def calculate_rolling_features(self, season: int, week: int) -> pd.DataFrame:
        """
        Calculate rolling features for all teams up to the specified week.
        
        Args:
            season: NFL season year
            week: Week to calculate features up to
            
        Returns:
            DataFrame with rolling features for each team
        """
        # Input validation
        if season < 2000 or season > 2030:
            raise ValueError(f"Invalid season: {season}. Must be between 2000-2030")
        
        if week < 1 or week > 22:
            raise ValueError(f"Invalid week: {week}. Must be between 1-22")
        
        logger.info(f"Calculating rolling features for season {season}, week {week}")
        
        # Load required data
        pbp_df = self._load_pbp_data(season, week)
        schedules_df = self._load_schedules_data(season)
        
        # Calculate team-game level metrics
        team_game_metrics = self._calculate_team_game_metrics(pbp_df, schedules_df)
        
        # Calculate rolling features
        rolling_features = self._calculate_rolling_windows(team_game_metrics, season, week)
        
        logger.info(f"Calculated rolling features for {len(rolling_features)} team-week combinations")
        return rolling_features
    
    def _load_pbp_data(self, season: int, week: int) -> pd.DataFrame:
        """Load PBP data for the season up to the specified week."""
        pbp_reader = PBPReader()
        
        # Load all weeks up to the specified week
        all_pbp_data = []
        for w in range(1, week + 1):
            try:
                week_pbp = pbp_reader.load_pbp(season, w, use_cache=True, mvp_only=True)
                all_pbp_data.append(week_pbp)
            except Exception as e:
                logger.warning(f"Failed to load PBP data for season {season}, week {w}: {e}")
                continue
        
        if not all_pbp_data:
            raise ValueError(f"No PBP data available for season {season}, weeks 1-{week}")
        
        combined_pbp = pd.concat(all_pbp_data, ignore_index=True)
        logger.info(f"Loaded PBP data: {len(combined_pbp)} plays across {week} weeks")
        return combined_pbp
    
    def _load_schedules_data(self, season: int) -> pd.DataFrame:
        """Load schedules data for the season."""
        schedules_reader = SchedulesReader()
        schedules_df = schedules_reader.load_schedules(season)
        logger.info(f"Loaded schedules data: {len(schedules_df)} games")
        return schedules_df
    
    def _calculate_team_game_metrics(self, pbp_df: pd.DataFrame, schedules_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate team-game level metrics from PBP data.
        
        Args:
            pbp_df: Play-by-play data
            schedules_df: Schedules data
            
        Returns:
            DataFrame with team-game level metrics
        """
        logger.info("Calculating team-game level metrics")
        
        team_game_metrics = []
        
        # Group PBP data by game and team
        for game_id in pbp_df['game_id'].unique():
            game_pbp = pbp_df[pbp_df['game_id'] == game_id]
            
            # Get game info from schedules
            game_info = schedules_df[schedules_df['game_id'] == game_id]
            if game_info.empty:
                continue
            
            game_info = game_info.iloc[0]
            season = game_info['season']
            week = game_info['week']
            home_team = game_info['home_team']
            away_team = game_info['away_team']
            
            # Calculate metrics for home team (offense)
            home_offense = self._calculate_offensive_metrics(game_pbp, home_team)
            home_defense = self._calculate_defensive_metrics(game_pbp, home_team)
            
            # Calculate metrics for away team (offense)
            away_offense = self._calculate_offensive_metrics(game_pbp, away_team)
            away_defense = self._calculate_defensive_metrics(game_pbp, away_team)
            
            # Add team-game records
            team_game_metrics.extend([
                {
                    'season': season,
                    'week': week,
                    'game_id': game_id,
                    'team': home_team,
                    'opponent': away_team,
                    'home': True,
                    **home_offense,
                    **{f"def_{k}": v for k, v in home_defense.items()}
                },
                {
                    'season': season,
                    'week': week,
                    'game_id': game_id,
                    'team': away_team,
                    'opponent': home_team,
                    'home': False,
                    **away_offense,
                    **{f"def_{k}": v for k, v in away_defense.items()}
                }
            ])
        
        metrics_df = pd.DataFrame(team_game_metrics)
        logger.info(f"Calculated team-game metrics for {len(metrics_df)} team-games")
        return metrics_df
    
    def _calculate_offensive_metrics(self, game_pbp: pd.DataFrame, team: str) -> Dict[str, float]:
        """Calculate offensive metrics for a team in a game."""
        team_offense = game_pbp[game_pbp['posteam'] == team].copy()
        
        if team_offense.empty:
            return self._get_empty_offensive_metrics()
        
        # Basic metrics
        total_plays = len(team_offense)
        total_epa = team_offense['epa'].sum()
        epa_per_play = total_epa / total_plays if total_plays > 0 else 0
        
        # Pass metrics
        pass_plays = team_offense[team_offense['pass'] == 1]
        pass_epa = pass_plays['epa'].sum() if not pass_plays.empty else 0
        pass_epa_per_play = pass_epa / len(pass_plays) if len(pass_plays) > 0 else 0
        
        # Run metrics
        run_plays = team_offense[team_offense['rush'] == 1]
        run_epa = run_plays['epa'].sum() if not run_plays.empty else 0
        run_epa_per_play = run_epa / len(run_plays) if len(run_plays) > 0 else 0
        
        # Early down metrics (1st and 2nd down)
        early_down_plays = team_offense[team_offense['down'].isin([1, 2])]
        early_down_pass = early_down_plays[early_down_plays['pass'] == 1]
        early_down_pass_epa = early_down_pass['epa'].sum() if not early_down_pass.empty else 0
        early_down_pass_epa_per_play = early_down_pass_epa / len(early_down_pass) if len(early_down_pass) > 0 else 0
        
        # Success rate (EPA > 0)
        successful_plays = len(team_offense[team_offense['epa'] > 0])
        success_rate = successful_plays / total_plays if total_plays > 0 else 0
        
        return {
            'off_epa_play': epa_per_play,
            'off_pass_epa_play': pass_epa_per_play,
            'off_run_epa_play': run_epa_per_play,
            'off_early_down_pass_epa_play': early_down_pass_epa_per_play,
            'off_success_rate': success_rate,
            'off_total_plays': total_plays,
            'off_pass_plays': len(pass_plays),
            'off_run_plays': len(run_plays)
        }
    
    def _calculate_defensive_metrics(self, game_pbp: pd.DataFrame, team: str) -> Dict[str, float]:
        """Calculate defensive metrics for a team in a game."""
        team_defense = game_pbp[game_pbp['defteam'] == team].copy()
        
        if team_defense.empty:
            return self._get_empty_defensive_metrics()
        
        # Basic metrics
        total_plays_faced = len(team_defense)
        total_epa_allowed = team_defense['epa'].sum()
        epa_allowed_per_play = total_epa_allowed / total_plays_faced if total_plays_faced > 0 else 0
        
        # Pass defense metrics
        pass_plays_faced = team_defense[team_defense['pass'] == 1]
        pass_epa_allowed = pass_plays_faced['epa'].sum() if not pass_plays_faced.empty else 0
        pass_epa_allowed_per_play = pass_epa_allowed / len(pass_plays_faced) if len(pass_plays_faced) > 0 else 0
        
        # Run defense metrics
        run_plays_faced = team_defense[team_defense['rush'] == 1]
        run_epa_allowed = run_plays_faced['epa'].sum() if not run_plays_faced.empty else 0
        run_epa_allowed_per_play = run_epa_allowed / len(run_plays_faced) if len(run_plays_faced) > 0 else 0
        
        # Success rate allowed (EPA > 0)
        successful_plays_allowed = len(team_defense[team_defense['epa'] > 0])
        success_rate_allowed = successful_plays_allowed / total_plays_faced if total_plays_faced > 0 else 0
        
        return {
            'def_epa_play_allowed': epa_allowed_per_play,
            'def_pass_epa_play_allowed': pass_epa_allowed_per_play,
            'def_run_epa_play_allowed': run_epa_allowed_per_play,
            'def_success_rate_allowed': success_rate_allowed,
            'def_total_plays_faced': total_plays_faced,
            'def_pass_plays_faced': len(pass_plays_faced),
            'def_run_plays_faced': len(run_plays_faced)
        }
    
    def _get_empty_offensive_metrics(self) -> Dict[str, float]:
        """Return empty offensive metrics."""
        return {
            'off_epa_play': 0.0,
            'off_pass_epa_play': 0.0,
            'off_run_epa_play': 0.0,
            'off_early_down_pass_epa_play': 0.0,
            'off_success_rate': 0.0,
            'off_total_plays': 0,
            'off_pass_plays': 0,
            'off_run_plays': 0
        }
    
    def _get_empty_defensive_metrics(self) -> Dict[str, float]:
        """Return empty defensive metrics."""
        return {
            'def_epa_play_allowed': 0.0,
            'def_pass_epa_play_allowed': 0.0,
            'def_run_epa_play_allowed': 0.0,
            'def_success_rate_allowed': 0.0,
            'def_total_plays_faced': 0,
            'def_pass_plays_faced': 0,
            'def_run_plays_faced': 0
        }
    
    def _calculate_rolling_windows(self, team_game_metrics: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        """
        Calculate rolling window features for each team.
        
        Args:
            team_game_metrics: Team-game level metrics
            season: Season year
            week: Current week
            
        Returns:
            DataFrame with rolling features
        """
        logger.info("Calculating rolling window features")
        
        rolling_features = []
        
        for team in team_game_metrics['team'].unique():
            team_data = team_game_metrics[team_game_metrics['team'] == team].copy()
            team_data = team_data.sort_values('week')
            
            # Calculate rolling features for each week
            for current_week in range(1, week + 1):
                # Get data up to current week
                historical_data = team_data[team_data['week'] < current_week]
                
                if historical_data.empty:
                    # No historical data, use default values
                    rolling_feature_row = self._create_default_rolling_features(team, season, current_week)
                else:
                    # Calculate rolling features
                    rolling_feature_row = self._calculate_team_rolling_features(
                        historical_data, team, season, current_week
                    )
                
                rolling_features.append(rolling_feature_row)
        
        rolling_df = pd.DataFrame(rolling_features)
        logger.info(f"Calculated rolling features for {len(rolling_df)} team-weeks")
        return rolling_df
    
    def _calculate_team_rolling_features(self, historical_data: pd.DataFrame, team: str, season: int, week: int) -> Dict[str, Any]:
        """Calculate rolling features for a specific team and week."""
        # L3 features (last 3 games)
        l3_data = historical_data.tail(self.l3_window)
        l3_features = self._calculate_window_features(l3_data, 'l3', week)
        
        # L5 features (last 5 games)
        l5_data = historical_data.tail(self.l5_window)
        l5_features = self._calculate_window_features(l5_data, 'l5', week)
        
        # L6 features (last 6 games)
        l6_data = historical_data.tail(self.l6_window)
        l6_features = self._calculate_window_features(l6_data, 'l6', week)
        
        # EWMA features
        ewma_features = self._calculate_ewma_features(historical_data)
        
        # Combine all features
        rolling_features = {
            'season': season,
            'week': week,
            'team': team,
            **l3_features,
            **l5_features,
            **l6_features,
            **ewma_features
        }
        
        return rolling_features
    
    def _calculate_window_features(self, window_data: pd.DataFrame, window_name: str, current_week: int) -> Dict[str, float]:
        """Calculate features for a specific window."""
        if window_data.empty:
            return self._get_empty_window_features(window_name)
        
        # Apply early season shrinkage if needed
        shrinkage_factor = self._get_shrinkage_factor(len(window_data), window_name, current_week)
        
        # Calculate weighted averages
        features = {}
        
        # Offensive features
        features[f'off_epa_play_{window_name}'] = window_data['off_epa_play'].mean() * shrinkage_factor
        features[f'off_pass_epa_play_{window_name}'] = window_data['off_pass_epa_play'].mean() * shrinkage_factor
        features[f'off_run_epa_play_{window_name}'] = window_data['off_run_epa_play'].mean() * shrinkage_factor
        features[f'off_early_down_pass_epa_play_{window_name}'] = window_data['off_early_down_pass_epa_play'].mean() * shrinkage_factor
        features[f'off_success_rate_{window_name}'] = window_data['off_success_rate'].mean() * shrinkage_factor
        
        # Defensive features
        features[f'def_epa_play_allowed_{window_name}'] = window_data['def_def_epa_play_allowed'].mean() * shrinkage_factor
        features[f'def_pass_epa_play_allowed_{window_name}'] = window_data['def_def_pass_epa_play_allowed'].mean() * shrinkage_factor
        features[f'def_run_epa_play_allowed_{window_name}'] = window_data['def_def_run_epa_play_allowed'].mean() * shrinkage_factor
        features[f'def_success_rate_allowed_{window_name}'] = window_data['def_def_success_rate_allowed'].mean() * shrinkage_factor
        
        return features
    
    def _calculate_ewma_features(self, historical_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate exponentially weighted moving average features."""
        if historical_data.empty:
            return self._get_empty_ewma_features()
        
        features = {}
        
        # Offensive EWMA features
        features['off_epa_play_ewma'] = historical_data['off_epa_play'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['off_pass_epa_play_ewma'] = historical_data['off_pass_epa_play'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['off_run_epa_play_ewma'] = historical_data['off_run_epa_play'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['off_early_down_pass_epa_play_ewma'] = historical_data['off_early_down_pass_epa_play'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['off_success_rate_ewma'] = historical_data['off_success_rate'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        
        # Defensive EWMA features
        features['def_epa_play_allowed_ewma'] = historical_data['def_def_epa_play_allowed'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['def_pass_epa_play_allowed_ewma'] = historical_data['def_def_pass_epa_play_allowed'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['def_run_epa_play_allowed_ewma'] = historical_data['def_def_run_epa_play_allowed'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        features['def_success_rate_allowed_ewma'] = historical_data['def_def_success_rate_allowed'].ewm(alpha=self.ewma_alpha, min_periods=self.ewma_min_periods).mean().iloc[-1]
        
        return features
    
    def _get_shrinkage_factor(self, data_length: int, window_name: str, current_week: int) -> float:
        """Calculate shrinkage factor for early season adjustments."""
        if current_week >= self.early_season_min_weeks:
            return 1.0
        
        # Apply shrinkage for early season
        window_size = getattr(self, f'{window_name}_window', 3)
        if data_length < window_size:
            return self.early_season_shrinkage
        return 1.0
    
    def _get_empty_window_features(self, window_name: str) -> Dict[str, float]:
        """Return empty features for a window."""
        return {
            f'off_epa_play_{window_name}': 0.0,
            f'off_pass_epa_play_{window_name}': 0.0,
            f'off_run_epa_play_{window_name}': 0.0,
            f'off_early_down_pass_epa_play_{window_name}': 0.0,
            f'off_success_rate_{window_name}': 0.0,
            f'def_epa_play_allowed_{window_name}': 0.0,
            f'def_pass_epa_play_allowed_{window_name}': 0.0,
            f'def_run_epa_play_allowed_{window_name}': 0.0,
            f'def_success_rate_allowed_{window_name}': 0.0
        }
    
    def _get_empty_ewma_features(self) -> Dict[str, float]:
        """Return empty EWMA features."""
        return {
            'off_epa_play_ewma': 0.0,
            'off_pass_epa_play_ewma': 0.0,
            'off_run_epa_play_ewma': 0.0,
            'off_early_down_pass_epa_play_ewma': 0.0,
            'off_success_rate_ewma': 0.0,
            'def_epa_play_allowed_ewma': 0.0,
            'def_pass_epa_play_allowed_ewma': 0.0,
            'def_run_epa_play_allowed_ewma': 0.0,
            'def_success_rate_allowed_ewma': 0.0
        }
    
    def _create_default_rolling_features(self, team: str, season: int, week: int) -> Dict[str, Any]:
        """Create default rolling features when no historical data is available."""
        features = {
            'season': season,
            'week': week,
            'team': team
        }
        
        # Add empty window features
        for window in ['l3', 'l5', 'l6']:
            features.update(self._get_empty_window_features(window))
        
        # Add empty EWMA features
        features.update(self._get_empty_ewma_features())
        
        return features
    
    def save_rolling_features(self, rolling_features: pd.DataFrame, season: int, week: int) -> str:
        """Save rolling features to parquet file."""
        from pathlib import Path
        import yaml
        
        # Load paths config
        with open("configs/paths.yaml", 'r') as f:
            paths_config = yaml.safe_load(f)
        
        # Create output path
        output_path = Path(paths_config['data']['parquet_lake']) / 'rolling_features' / f"season={season}" / f"week={week}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rolling_features_{season}_week{week}_{timestamp}.parquet"
        filepath = output_path / filename
        
        rolling_features.to_parquet(filepath, index=False)
        logger.info(f"Saved rolling features to {filepath}")
        
        return str(filepath)
    
    def save_features(self, features_df: pd.DataFrame, season: int, week: int) -> str:
        """Alias for save_rolling_features method."""
        return self.save_rolling_features(features_df, season, week)
