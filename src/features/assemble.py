"""
Feature assembly module for Sprint 2.3.

This module combines all engineered features into the modeling table (two rows per game)
as specified in the architecture documentation.

Purpose: Join all engineered features into the modeling table (two rows per game).
Inputs: outputs from other feature modules; market priors from schedules.
Outputs: modeling Parquet table and/or feature store table; training labels (`label_win`) for historical rows only.
Key contracts: no leakage; column order/versioning tracked for modeling.
"""

import pandas as pd
import numpy as np
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from src.features.rolling import RollingFeatureCalculator
from src.features.situational import SituationalFeatureCalculator
from src.data.readers import SchedulesReader

logger = logging.getLogger(__name__)


class FeatureAssembler:
    """
    Assembles all engineered features into a modeling table.
    
    Combines rolling features, situational features, and market data
    into a comprehensive modeling dataset with training labels.
    """
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize the feature assembler."""
        self.config = self._load_config(config_path)
        self.rolling_calc = RollingFeatureCalculator(config_path)
        self.situational_calc = SituationalFeatureCalculator(config_path)
        
        logger.info("Initialized FeatureAssembler")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def assemble_modeling_table(self, season: int, week: int, use_historical_data: bool = True) -> pd.DataFrame:
        """
        Assemble the complete modeling table with all features and training labels.
        
        Args:
            season: NFL season year
            week: Week to assemble features up to
            use_historical_data: Whether to include historical data for training
            
        Returns:
            DataFrame with modeling table (two rows per game)
        """
        logger.info(f"Assembling modeling table for season {season}, week {week}")
        
        # Determine data range for maximum training data
        if use_historical_data:
            # Use maximum available historical data
            start_season = 2020  # Start from 2020 for maximum data
            start_week = 1
        else:
            start_season = season
            start_week = 1
        
        # Load schedules data for all seasons/weeks
        all_schedules = self._load_all_schedules(start_season, season, start_week, week)
        
        # Assemble features for all games
        modeling_data = []
        
        for _, game in all_schedules.iterrows():
            game_season = game['season']
            game_week = game['week']
            
            # Skip future games (no training labels available)
            if game_season > season or (game_season == season and game_week > week):
                continue
            
            # Assemble features for this game
            game_features = self._assemble_game_features(game, game_season, game_week)
            if game_features is not None:
                modeling_data.extend(game_features)
        
        modeling_df = pd.DataFrame(modeling_data)
        
        # Add training labels for historical games
        modeling_df = self._add_training_labels(modeling_df, all_schedules)
        
        # Ensure no data leakage
        modeling_df = self._ensure_no_leakage(modeling_df)
        
        logger.info(f"Assembled modeling table: {len(modeling_df)} records")
        return modeling_df
    
    def _load_all_schedules(self, start_season: int, end_season: int, start_week: int, end_week: int) -> pd.DataFrame:
        """Load schedules data for all seasons/weeks."""
        logger.info(f"Loading schedules data from season {start_season} to {end_season}")
        
        all_schedules = []
        schedules_reader = SchedulesReader()
        
        for season in range(start_season, end_season + 1):
            try:
                season_schedules = schedules_reader.load_schedules(season)
                all_schedules.append(season_schedules)
                logger.info(f"Loaded {len(season_schedules)} games for season {season}")
            except Exception as e:
                logger.warning(f"Failed to load schedules for season {season}: {e}")
                continue
        
        if not all_schedules:
            raise ValueError("No schedules data available")
        
        combined_schedules = pd.concat(all_schedules, ignore_index=True)
        logger.info(f"Loaded total schedules: {len(combined_schedules)} games")
        return combined_schedules
    
    def _assemble_game_features(self, game: pd.Series, season: int, week: int) -> Optional[List[Dict[str, Any]]]:
        """Assemble features for a single game."""
        try:
            # Get rolling features
            rolling_features = self.rolling_calc.calculate_rolling_features(season, week)
            
            # Get situational features
            situational_features = self.situational_calc.calculate_situational_features(season, week)
            
            # Combine features for both teams
            game_features = []
            
            home_team = game['home_team']
            away_team = game['away_team']
            
            # Home team features
            home_rolling = rolling_features[rolling_features['team'] == home_team]
            home_situational = situational_features[situational_features['team'] == home_team]
            
            if not home_rolling.empty and not home_situational.empty:
                home_features = self._combine_team_features(
                    home_rolling.iloc[0], home_situational.iloc[0], game, 'home'
                )
                game_features.append(home_features)
            
            # Away team features
            away_rolling = rolling_features[rolling_features['team'] == away_team]
            away_situational = situational_features[situational_features['team'] == away_team]
            
            if not away_rolling.empty and not away_situational.empty:
                away_features = self._combine_team_features(
                    away_rolling.iloc[0], away_situational.iloc[0], game, 'away'
                )
                game_features.append(away_features)
            
            return game_features if game_features else None
            
        except Exception as e:
            logger.warning(f"Failed to assemble features for game {game['game_id']}: {e}")
            return None
    
    def _combine_team_features(self, rolling_data: pd.Series, situational_data: pd.Series, 
                             game_data: pd.Series, team_type: str) -> Dict[str, Any]:
        """Combine rolling and situational features for a team."""
        # Start with basic game info
        features = {
            'season': game_data['season'],
            'week': game_data['week'],
            'game_id': game_data['game_id'],
            'team': rolling_data['team'],
            'opponent': situational_data['opponent'],
            'home': situational_data['home'],
            'team_type': team_type
        }
        
        # Add rolling features
        rolling_cols = [col for col in rolling_data.index if col not in ['season', 'week', 'team']]
        for col in rolling_cols:
            features[f'rolling_{col}'] = rolling_data[col]
        
        # Add situational features
        situational_cols = [col for col in situational_data.index if col not in ['season', 'week', 'team', 'opponent']]
        for col in situational_cols:
            features[f'situational_{col}'] = situational_data[col]
        
        # Add market features
        features['market_spread_close'] = game_data.get('spread_line', 0.0)
        features['market_total_close'] = game_data.get('total_line', 0.0)
        features['market_moneyline_close'] = game_data.get('moneyline', 0)
        
        # Add game outcome features (for training labels)
        features['home_score'] = game_data.get('home_score', None)
        features['away_score'] = game_data.get('away_score', None)
        features['result'] = game_data.get('result', None)
        
        return features
    
    def _add_training_labels(self, modeling_df: pd.DataFrame, schedules_df: pd.DataFrame) -> pd.DataFrame:
        """Add training labels for historical games."""
        logger.info("Adding training labels for historical games")
        
        # Create labels based on game outcomes
        modeling_df['label_win'] = None
        
        for idx, row in modeling_df.iterrows():
            game_id = row['game_id']
            team = row['team']
            is_home = row['home']
            
            # Get game outcome
            game_data = schedules_df[schedules_df['game_id'] == game_id]
            if game_data.empty:
                continue
            
            game_data = game_data.iloc[0]
            
            # Determine if team won
            if pd.notna(game_data.get('result')):
                # Use result column if available
                if is_home:
                    # Home team wins if result > 0
                    modeling_df.at[idx, 'label_win'] = int(1 if game_data['result'] > 0 else 0)
                else:
                    # Away team wins if result < 0
                    modeling_df.at[idx, 'label_win'] = int(1 if game_data['result'] < 0 else 0)
            elif pd.notna(game_data.get('home_score')) and pd.notna(game_data.get('away_score')):
                # Use scores if available
                home_score = game_data['home_score']
                away_score = game_data['away_score']
                
                if is_home:
                    modeling_df.at[idx, 'label_win'] = int(1 if home_score > away_score else 0)
                else:
                    modeling_df.at[idx, 'label_win'] = int(1 if away_score > home_score else 0)
        
        # Count labeled games
        labeled_games = modeling_df['label_win'].notna().sum()
        logger.info(f"Added training labels for {labeled_games} games")
        
        return modeling_df
    
    def _ensure_no_leakage(self, modeling_df: pd.DataFrame) -> pd.DataFrame:
        """Ensure no data leakage in the modeling table."""
        logger.info("Ensuring no data leakage")
        
        # Remove future information
        future_cols = ['home_score', 'away_score', 'result']
        for col in future_cols:
            if col in modeling_df.columns:
                modeling_df = modeling_df.drop(columns=[col])
        
        # Ensure features are point-in-time
        # (This is already handled by the rolling and situational calculators)
        
        logger.info("Data leakage prevention completed")
        return modeling_df
    
    def save_modeling_table(self, modeling_df: pd.DataFrame, season: int, week: int) -> str:
        """Save modeling table to parquet file."""
        from pathlib import Path
        import yaml
        
        # Load paths config
        with open("configs/paths.yaml", 'r') as f:
            paths_config = yaml.safe_load(f)
        
        # Create output path
        output_path = Path(paths_config['data']['parquet_lake']) / 'modeling_table' / f"season={season}" / f"week={week}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"modeling_table_{season}_week{week}_{timestamp}.parquet"
        filepath = output_path / filename
        
        modeling_df.to_parquet(filepath, index=False)
        logger.info(f"Saved modeling table to {filepath}")
        
        return str(filepath)
    
    def get_feature_columns(self, modeling_df: pd.DataFrame) -> List[str]:
        """Get list of feature columns for modeling."""
        # Exclude non-feature columns
        exclude_cols = [
            'season', 'week', 'game_id', 'team', 'opponent', 'home', 'team_type',
            'label_win', 'home_score', 'away_score', 'result'
        ]
        
        feature_cols = [col for col in modeling_df.columns if col not in exclude_cols]
        return feature_cols
