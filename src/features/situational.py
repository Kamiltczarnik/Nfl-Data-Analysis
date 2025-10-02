"""
Situational features module for Sprint 2.2.

This module implements situational and market features as specified in Sprint 2.2.

Features implemented:
- home: Home field advantage (boolean)
- rest_days: Days of rest between games
- spread_close: Closing spread line
- Basic opponent-adjusted strength-of-schedule (SoS) for recent EPA/success aggregates
"""

import pandas as pd
import numpy as np
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from src.data.readers import SchedulesReader, PBPReader
from src.features.rolling import RollingFeatureCalculator

logger = logging.getLogger(__name__)


class SituationalFeatureCalculator:
    """
    Calculates situational and market features for NFL games.
    
    Implements Sprint 2.2 requirements:
    - Situational: home, rest_days
    - Market: spread_close
    - Basic opponent-adjusted strength-of-schedule (SoS) for recent EPA/success aggregates
    """
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize the situational feature calculator."""
        self.config = self._load_config(config_path)
        self.rolling_calc = RollingFeatureCalculator(config_path)
        
        logger.info("Initialized SituationalFeatureCalculator")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def calculate_situational_features(self, season: int, week: int) -> pd.DataFrame:
        """
        Calculate situational and market features for all games up to the specified week.
        
        Args:
            season: NFL season year
            week: Week to calculate features up to
            
        Returns:
            DataFrame with situational and market features for each team-game
        """
        # Input validation
        if season < 2000 or season > 2030:
            raise ValueError(f"Invalid season: {season}. Must be between 2000-2030")
        
        if week < 1 or week > 22:
            raise ValueError(f"Invalid week: {week}. Must be between 1-22")
        
        logger.info(f"Calculating situational features for season {season}, week {week}")
        
        # Load required data
        schedules_df = self._load_schedules_data(season)
        
        # Calculate basic situational features
        situational_features = self._calculate_basic_situational_features(schedules_df, season, week)
        
        # Calculate strength-of-schedule adjustments
        sos_features = self._calculate_sos_adjustments(situational_features, season, week)
        
        # Combine features
        combined_features = pd.merge(situational_features, sos_features, on=['season', 'week', 'team'], how='left')
        
        logger.info(f"Calculated situational features for {len(combined_features)} team-games")
        return combined_features
    
    def _load_schedules_data(self, season: int) -> pd.DataFrame:
        """Load schedules data for the season."""
        schedules_reader = SchedulesReader()
        schedules_df = schedules_reader.load_schedules(season)
        logger.info(f"Loaded schedules data: {len(schedules_df)} games")
        return schedules_df
    
    def _calculate_basic_situational_features(self, schedules_df: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        """
        Calculate basic situational features: home, rest_days, spread_close.
        
        Args:
            schedules_df: Schedules data
            season: Season year
            week: Current week
            
        Returns:
            DataFrame with basic situational features
        """
        logger.info("Calculating basic situational features")
        
        # Filter for games up to the specified week
        games_df = schedules_df[schedules_df['week'] <= week].copy()
        
        situational_features = []
        
        for _, game in games_df.iterrows():
            game_id = game['game_id']
            game_season = game['season']
            game_week = game['week']
            home_team = game['home_team']
            away_team = game['away_team']
            
            # Calculate rest days for both teams
            home_rest_days = self._calculate_rest_days(games_df, home_team, game_week)
            away_rest_days = self._calculate_rest_days(games_df, away_team, game_week)
            
            # Get market data
            spread_close = game.get('spread_line', 0.0)
            total_close = game.get('total_line', 0.0)
            moneyline_close = game.get('moneyline', 0)
            
            # Add features for home team
            situational_features.append({
                'season': game_season,
                'week': game_week,
                'game_id': game_id,
                'team': home_team,
                'opponent': away_team,
                'situational_home': True,
                'situational_rest_days': home_rest_days,
                'situational_spread_close': spread_close,
                'total_close': total_close,
                'moneyline_close': moneyline_close,
                'opponent_rest_days': away_rest_days
            })
            
            # Add features for away team
            situational_features.append({
                'season': game_season,
                'week': game_week,
                'game_id': game_id,
                'team': away_team,
                'opponent': home_team,
                'situational_home': False,
                'situational_rest_days': away_rest_days,
                'situational_spread_close': -spread_close,  # Flip spread for away team
                'total_close': total_close,
                'moneyline_close': moneyline_close,
                'opponent_rest_days': home_rest_days
            })
        
        features_df = pd.DataFrame(situational_features)
        logger.info(f"Calculated basic situational features for {len(features_df)} team-games")
        return features_df
    
    def _calculate_rest_days(self, games_df: pd.DataFrame, team: str, current_week: int) -> int:
        """
        Calculate rest days for a team before the current week.
        
        Args:
            games_df: Games data
            team: Team abbreviation
            current_week: Current week
            
        Returns:
            Number of rest days
        """
        # Find the team's previous game
        home_games = games_df[games_df['home_team'] == team].copy()
        away_games = games_df[games_df['away_team'] == team].copy()
        team_games = pd.concat([home_games, away_games], ignore_index=True)
        team_games = team_games.sort_values('week')
        
        # Find the most recent game before current week
        previous_games = team_games[team_games['week'] < current_week]
        
        if previous_games.empty:
            # No previous game, assume standard rest (7 days)
            return 7
        
        last_game_week = previous_games['week'].max()
        
        # Calculate days between games (assuming games are on Sundays)
        # This is a simplified calculation - in reality, games can be on different days
        days_between_weeks = (current_week - last_game_week) * 7
        
        # Apply some logic for different rest scenarios
        if days_between_weeks == 7:
            return 7  # Standard week
        elif days_between_weeks == 6:
            return 6  # Short week (Thursday game)
        elif days_between_weeks == 10:
            return 10  # Bye week
        elif days_between_weeks == 14:
            return 14  # Two bye weeks
        else:
            return days_between_weeks  # Other scenarios
    
    def _calculate_sos_adjustments(self, situational_features: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        """
        Calculate basic opponent-adjusted strength-of-schedule (SoS) for recent EPA/success aggregates.
        
        Args:
            situational_features: Basic situational features
            season: Season year
            week: Current week
            
        Returns:
            DataFrame with SoS-adjusted features
        """
        logger.info("Calculating strength-of-schedule adjustments")
        
        # Get rolling features for SoS calculation
        rolling_features = self.rolling_calc.calculate_rolling_features(season, week)
        
        # Calculate opponent strength metrics
        sos_features = []
        
        for _, row in situational_features.iterrows():
            team = row['team']
            opponent = row['opponent']
            game_week = row['week']
            
            # Get team's rolling features
            team_rolling = rolling_features[
                (rolling_features['team'] == team) & 
                (rolling_features['week'] == game_week)
            ]
            
            # Get opponent's rolling features
            opponent_rolling = rolling_features[
                (rolling_features['team'] == opponent) & 
                (rolling_features['week'] == game_week)
            ]
            
            if team_rolling.empty or opponent_rolling.empty:
                # No rolling data available, use default values
                sos_row = {
                    'season': row['season'],
                    'week': row['week'],
                    'team': team,
                    'opponent_off_epa_l3': 0.0,
                    'opponent_def_epa_allowed_l3': 0.0,
                    'opponent_off_success_l3': 0.0,
                    'opponent_def_success_allowed_l3': 0.0,
                    'sos_adjustment_factor': 1.0
                }
            else:
                team_data = team_rolling.iloc[0]
                opponent_data = opponent_rolling.iloc[0]
                
                # Calculate opponent strength metrics
                opponent_off_epa = opponent_data.get('off_epa_play_l3', 0.0)
                opponent_def_epa_allowed = opponent_data.get('def_epa_play_allowed_l3', 0.0)
                opponent_off_success = opponent_data.get('off_success_rate_l3', 0.0)
                opponent_def_success_allowed = opponent_data.get('def_success_rate_allowed_l3', 0.0)
                
                # Calculate SoS adjustment factor
                # This is a simplified SoS calculation
                # In practice, this would be more sophisticated
                sos_adjustment_factor = self._calculate_sos_factor(
                    opponent_off_epa, opponent_def_epa_allowed,
                    opponent_off_success, opponent_def_success_allowed
                )
                
                sos_row = {
                    'season': row['season'],
                    'week': row['week'],
                    'team': team,
                    'opponent_off_epa_l3': opponent_off_epa,
                    'opponent_def_epa_allowed_l3': opponent_def_epa_allowed,
                    'opponent_off_success_l3': opponent_off_success,
                    'opponent_def_success_allowed_l3': opponent_def_success_allowed,
                    'sos_adjustment_factor': sos_adjustment_factor
                }
            
            sos_features.append(sos_row)
        
        sos_df = pd.DataFrame(sos_features)
        logger.info(f"Calculated SoS adjustments for {len(sos_df)} team-games")
        return sos_df
    
    def _calculate_sos_factor(self, opponent_off_epa: float, opponent_def_epa_allowed: float,
                             opponent_off_success: float, opponent_def_success_allowed: float) -> float:
        """
        Calculate strength-of-schedule adjustment factor.
        
        Args:
            opponent_off_epa: Opponent's offensive EPA
            opponent_def_epa_allowed: Opponent's defensive EPA allowed
            opponent_off_success: Opponent's offensive success rate
            opponent_def_success_allowed: Opponent's defensive success rate allowed
            
        Returns:
            SoS adjustment factor
        """
        # Simple SoS calculation based on opponent strength
        # Stronger opponents (higher EPA, lower EPA allowed) increase difficulty
        
        # Offensive strength factor (higher is better for opponent)
        off_strength = opponent_off_epa
        
        # Defensive strength factor (lower EPA allowed is better for opponent)
        def_strength = -opponent_def_epa_allowed
        
        # Success rate factors
        off_success_factor = opponent_off_success
        def_success_factor = 1.0 - opponent_def_success_allowed
        
        # Combine factors (normalize to around 1.0)
        combined_strength = (off_strength + def_strength + off_success_factor + def_success_factor) / 4
        
        # Convert to adjustment factor (1.0 = no adjustment, >1.0 = harder opponent)
        sos_factor = 1.0 + (combined_strength * 0.1)  # 10% adjustment per standard deviation
        
        # Clamp to reasonable range
        sos_factor = max(0.5, min(2.0, sos_factor))
        
        return sos_factor
    
    def save_situational_features(self, situational_features: pd.DataFrame, season: int, week: int) -> str:
        """Save situational features to parquet file."""
        from pathlib import Path
        import yaml
        
        # Load paths config
        with open("configs/paths.yaml", 'r') as f:
            paths_config = yaml.safe_load(f)
        
        # Create output path
        output_path = Path(paths_config['data']['parquet_lake']) / 'situational_features' / f"season={season}" / f"week={week}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"situational_features_{season}_week{week}_{timestamp}.parquet"
        filepath = output_path / filename
        
        situational_features.to_parquet(filepath, index=False)
        logger.info(f"Saved situational features to {filepath}")
        
        return str(filepath)
    
    def save_features(self, features_df: pd.DataFrame, season: int, week: int) -> str:
        """Alias for save_situational_features method."""
        return self.save_situational_features(features_df, season, week)
