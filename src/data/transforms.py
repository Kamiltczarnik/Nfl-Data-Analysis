"""
Data transformation and ID mapping module for NFL Data Analysis.

This module handles cleaning, normalization, ID mapping, and assembling drive-level tables
as specified in the architecture documentation.
"""

import pandas as pd
import numpy as np
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class IDMapper:
    """Handles ID mapping and normalization for team/player IDs."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        """Initialize ID mapper with configuration."""
        self.config = self._load_config(config_path)
        self.player_id_map = None
        self.team_id_map = None
        self._load_id_mappings()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def _load_id_mappings(self):
        """Load ID mappings from parquet files."""
        try:
            # Load player ID mappings
            players_path = Path(self.config['data']['parquet_lake']) / 'players'
            if players_path.exists():
                player_files = list(players_path.glob('**/*.parquet'))
                if player_files:
                    latest_file = max(player_files, key=os.path.getctime)
                    self.player_id_map = pd.read_parquet(latest_file)
                    logger.info(f"Loaded player ID map: {len(self.player_id_map)} records")
            
            # Load team ID mappings
            teams_path = Path(self.config['data']['parquet_lake']) / 'teams'
            if teams_path.exists():
                team_files = list(teams_path.glob('**/*.parquet'))
                if team_files:
                    latest_file = max(team_files, key=os.path.getctime)
                    self.team_id_map = pd.read_parquet(latest_file)
                    logger.info(f"Loaded team ID map: {len(self.team_id_map)} records")
            
            # Load FF player IDs for additional mapping
            ff_path = Path(self.config['data']['parquet_lake']) / 'ff_playerids'
            if ff_path.exists():
                ff_files = list(ff_path.glob('**/*.parquet'))
                if ff_files:
                    latest_file = max(ff_files, key=os.path.getctime)
                    self.ff_player_ids = pd.read_parquet(latest_file)
                    logger.info(f"Loaded FF player IDs: {len(self.ff_player_ids)} records")
            
        except Exception as e:
            logger.error(f"Failed to load ID mappings: {e}")
            raise
    
    def normalize_player_id(self, player_id: str, source: str = 'gsis_id') -> Optional[str]:
        """
        Normalize player ID to standard format.
        
        Args:
            player_id: Player ID to normalize
            source: Source ID type (gsis_id, espn_id, pfr_id, etc.)
            
        Returns:
            Normalized player ID or None if not found
        """
        if not self.player_id_map is not None:
            logger.warning("Player ID map not loaded")
            return player_id
        
        try:
            # Look up player in the ID map
            if source == 'gsis_id':
                match = self.player_id_map[self.player_id_map['gsis_id'] == player_id]
            elif source == 'espn_id':
                match = self.player_id_map[self.player_id_map['espn_id'] == player_id]
            elif source == 'pfr_id':
                match = self.player_id_map[self.player_id_map['pfr_id'] == player_id]
            else:
                logger.warning(f"Unknown source ID type: {source}")
                return player_id
            
            if not match.empty:
                return match.iloc[0]['gsis_id']  # Return GSIS ID as standard
            else:
                logger.debug(f"Player ID {player_id} not found in {source} mapping")
                return player_id
                
        except Exception as e:
            logger.error(f"Error normalizing player ID {player_id}: {e}")
            return player_id
    
    def normalize_team_id(self, team_id: str, source: str = 'team') -> Optional[str]:
        """
        Normalize team ID to standard format.
        
        Args:
            team_id: Team ID to normalize
            source: Source ID type (team, nfl, espn, etc.)
            
        Returns:
            Normalized team ID or None if not found
        """
        if self.team_id_map is None:
            logger.warning("Team ID map not loaded")
            return team_id
        
        try:
            # Look up team in the ID map
            if source == 'team':
                match = self.team_id_map[self.team_id_map['team'] == team_id]
            elif source == 'nfl':
                match = self.team_id_map[self.team_id_map['nfl'] == team_id]
            elif source == 'espn':
                match = self.team_id_map[self.team_id_map['espn'] == team_id]
            else:
                logger.warning(f"Unknown source ID type: {source}")
                return team_id
            
            if not match.empty:
                return match.iloc[0]['team']  # Return team abbreviation as standard
            else:
                logger.debug(f"Team ID {team_id} not found in {source} mapping")
                return team_id
                
        except Exception as e:
            logger.error(f"Error normalizing team ID {team_id}: {e}")
            return team_id
    
    def get_player_info(self, player_id: str, source: str = 'gsis_id') -> Optional[Dict[str, Any]]:
        """
        Get comprehensive player information.
        
        Args:
            player_id: Player ID to look up
            source: Source ID type
            
        Returns:
            Dictionary with player information or None if not found
        """
        if self.player_id_map is None:
            return None
        
        try:
            # Look up player
            if source == 'gsis_id':
                match = self.player_id_map[self.player_id_map['gsis_id'] == player_id]
            elif source == 'espn_id':
                match = self.player_id_map[self.player_id_map['espn_id'] == player_id]
            elif source == 'pfr_id':
                match = self.player_id_map[self.player_id_map['pfr_id'] == player_id]
            else:
                return None
            
            if not match.empty:
                player_info = match.iloc[0].to_dict()
                return player_info
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting player info for {player_id}: {e}")
            return None
    
    def get_team_info(self, team_id: str, source: str = 'team') -> Optional[Dict[str, Any]]:
        """
        Get comprehensive team information.
        
        Args:
            team_id: Team ID to look up
            source: Source ID type
            
        Returns:
            Dictionary with team information or None if not found
        """
        if self.team_id_map is None:
            return None
        
        try:
            # Look up team
            if source == 'team':
                match = self.team_id_map[self.team_id_map['team'] == team_id]
            elif source == 'nfl':
                match = self.team_id_map[self.team_id_map['nfl'] == team_id]
            elif source == 'espn':
                match = self.team_id_map[self.team_id_map['espn'] == team_id]
            else:
                return None
            
            if not match.empty:
                team_info = match.iloc[0].to_dict()
                return team_info
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting team info for {team_id}: {e}")
            return None


class DataTransformer:
    """Handles data cleaning, normalization, and transformation."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        """Initialize data transformer with configuration."""
        self.config = self._load_config(config_path)
        self.id_mapper = IDMapper(config_path)
        self.features_config = self._load_features_config()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def _load_features_config(self) -> Dict[str, Any]:
        """Load features configuration."""
        try:
            with open('configs/features.yaml', 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load features config: {e}")
            return {}
    
    def clean_schedules_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and normalize schedules data.
        
        Args:
            df: Raw schedules DataFrame
            
        Returns:
            Cleaned schedules DataFrame
        """
        logger.info(f"Cleaning schedules data: {len(df)} records")
        
        # Create a copy to avoid modifying original
        cleaned_df = df.copy()
        
        # Normalize team IDs
        if 'home_team' in cleaned_df.columns:
            cleaned_df['home_team'] = cleaned_df['home_team'].apply(
                lambda x: self.id_mapper.normalize_team_id(x, 'team') if pd.notna(x) else x
            )
        
        if 'away_team' in cleaned_df.columns:
            cleaned_df['away_team'] = cleaned_df['away_team'].apply(
                lambda x: self.id_mapper.normalize_team_id(x, 'team') if pd.notna(x) else x
            )
        
        # Ensure stable keys for joins
        required_keys = ['game_id', 'season', 'week', 'home_team', 'away_team']
        for key in required_keys:
            if key in cleaned_df.columns:
                cleaned_df[key] = cleaned_df[key].astype(str)
        
        # Validate no leakage across weeks (basic check)
        if 'season' in cleaned_df.columns and 'week' in cleaned_df.columns:
            max_week = cleaned_df['week'].max()
            current_season = cleaned_df['season'].iloc[0]
            logger.info(f"Data covers season {current_season}, max week {max_week}")
        
        logger.info(f"Cleaned schedules data: {len(cleaned_df)} records")
        return cleaned_df
    
    def clean_pbp_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and normalize PBP data.
        
        Args:
            df: Raw PBP DataFrame
            
        Returns:
            Cleaned PBP DataFrame
        """
        logger.info(f"Cleaning PBP data: {len(df)} records")
        
        # Create a copy to avoid modifying original
        cleaned_df = df.copy()
        
        # Normalize team IDs
        if 'posteam' in cleaned_df.columns:
            cleaned_df['posteam'] = cleaned_df['posteam'].apply(
                lambda x: self.id_mapper.normalize_team_id(x, 'team') if pd.notna(x) else x
            )
        
        if 'defteam' in cleaned_df.columns:
            cleaned_df['defteam'] = cleaned_df['defteam'].apply(
                lambda x: self.id_mapper.normalize_team_id(x, 'team') if pd.notna(x) else x
            )
        
        # Ensure stable keys for joins
        required_keys = ['game_id', 'play_id', 'season', 'week']
        for key in required_keys:
            if key in cleaned_df.columns:
                cleaned_df[key] = cleaned_df[key].astype(str)
        
        logger.info(f"Cleaned PBP data: {len(cleaned_df)} records")
        return cleaned_df
    
    def clean_weekly_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and normalize weekly stats data.
        
        Args:
            df: Raw weekly DataFrame
            
        Returns:
            Cleaned weekly DataFrame
        """
        logger.info(f"Cleaning weekly data: {len(df)} records")
        
        # Create a copy to avoid modifying original
        cleaned_df = df.copy()
        
        # Normalize player IDs
        if 'player_id' in cleaned_df.columns:
            cleaned_df['player_id'] = cleaned_df['player_id'].apply(
                lambda x: self.id_mapper.normalize_player_id(x, 'gsis_id') if pd.notna(x) else x
            )
        
        # Normalize team IDs
        if 'team' in cleaned_df.columns:
            cleaned_df['team'] = cleaned_df['team'].apply(
                lambda x: self.id_mapper.normalize_team_id(x, 'team') if pd.notna(x) else x
            )
        
        # Ensure stable keys for joins
        required_keys = ['player_id', 'team', 'season', 'week']
        for key in required_keys:
            if key in cleaned_df.columns:
                cleaned_df[key] = cleaned_df[key].astype(str)
        
        logger.info(f"Cleaned weekly data: {len(cleaned_df)} records")
        return cleaned_df
    
    def assemble_drive_level_table(self, pbp_df: pd.DataFrame, schedules_df: pd.DataFrame) -> pd.DataFrame:
        """
        Assemble drive-level table from PBP and schedules data.
        
        Args:
            pbp_df: Cleaned PBP DataFrame
            schedules_df: Cleaned schedules DataFrame
            
        Returns:
            Drive-level DataFrame
        """
        logger.info("Assembling drive-level table")
        
        try:
            # Group PBP data by drive
            drive_stats = pbp_df.groupby(['game_id', 'drive']).agg({
                'epa': ['sum', 'mean', 'count'],
                'wp': ['first', 'last'],
                'play_type': 'count',
                'posteam': 'first',
                'defteam': 'first'
            }).reset_index()
            
            # Flatten column names
            drive_stats.columns = ['_'.join(col).strip() if col[1] else col[0] for col in drive_stats.columns]
            
            # Rename columns for clarity
            drive_stats = drive_stats.rename(columns={
                'epa_sum': 'drive_epa',
                'epa_mean': 'avg_epa_per_play',
                'epa_count': 'plays_in_drive',
                'wp_first': 'wp_start',
                'wp_last': 'wp_end',
                'play_type_count': 'total_plays'
            })
            
            # Join with schedules data for additional context
            drive_stats = drive_stats.merge(
                schedules_df[['game_id', 'season', 'week', 'home_team', 'away_team']],
                on='game_id',
                how='left'
            )
            
            # Add drive outcome
            drive_stats['drive_outcome'] = drive_stats.apply(
                lambda row: 'touchdown' if row['wp_end'] > 0.9 else 
                           'field_goal' if row['wp_end'] > 0.7 else
                           'punt' if row['wp_end'] < 0.3 else
                           'turnover' if row['wp_end'] < 0.1 else 'other',
                axis=1
            )
            
            logger.info(f"Assembled drive-level table: {len(drive_stats)} drives")
            return drive_stats
            
        except Exception as e:
            logger.error(f"Error assembling drive-level table: {e}")
            raise
    
    def validate_data_quality(self, df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
        """
        Validate data quality for a given table.
        
        Args:
            df: DataFrame to validate
            table_name: Name of the table
            
        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'table_name': table_name,
            'total_records': len(df),
            'total_columns': len(df.columns),
            'missing_values': df.isnull().sum().to_dict(),
            'duplicate_records': df.duplicated().sum(),
            'data_types': df.dtypes.to_dict(),
            'issues': []
        }
        
        # Check for required keys
        required_keys = ['game_id', 'season', 'week', 'team', 'opponent']
        missing_keys = [key for key in required_keys if key not in df.columns]
        if missing_keys:
            validation_results['issues'].append(f"Missing required keys: {missing_keys}")
        
        # Check for data leakage (basic check)
        if 'season' in df.columns and 'week' in df.columns:
            max_week = df['week'].max()
            if max_week > 22:  # NFL season typically has max 22 weeks
                validation_results['issues'].append(f"Suspicious max week: {max_week}")
        
        logger.info(f"Data quality validation for {table_name}: {len(validation_results['issues'])} issues found")
        return validation_results


def main():
    """CLI interface for testing the transforms module."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Data Transforms')
    parser.add_argument('--test-id-mapping', action='store_true', help='Test ID mapping functionality')
    parser.add_argument('--test-data-cleaning', action='store_true', help='Test data cleaning functionality')
    parser.add_argument('--season', type=int, default=2024, help='Season to test with')
    
    args = parser.parse_args()
    
    if args.test_id_mapping:
        print("Testing ID mapping functionality...")
        id_mapper = IDMapper()
        
        # Test player ID normalization
        test_player_id = "00-0023459"  # Example GSIS ID
        normalized = id_mapper.normalize_player_id(test_player_id, 'gsis_id')
        print(f"Player ID normalization: {test_player_id} -> {normalized}")
        
        # Test team ID normalization
        test_team_id = "ARI"
        normalized = id_mapper.normalize_team_id(test_team_id, 'team')
        print(f"Team ID normalization: {test_team_id} -> {normalized}")
        
        # Test getting player info
        player_info = id_mapper.get_player_info(test_player_id, 'gsis_id')
        if player_info:
            print(f"Player info: {player_info.get('display_name', 'Unknown')}")
        
        # Test getting team info
        team_info = id_mapper.get_team_info(test_team_id, 'team')
        if team_info:
            print(f"Team info: {team_info.get('full', 'Unknown')}")
    
    if args.test_data_cleaning:
        print("Testing data cleaning functionality...")
        transformer = DataTransformer()
        
        # Load sample data for testing
        from src.data.readers import SchedulesReader, PBPReader
        
        schedules_reader = SchedulesReader()
        schedules_df = schedules_reader.load_schedules(args.season)
        
        pbp_reader = PBPReader()
        pbp_df = pbp_reader.load_pbp(args.season, mvp_only=True)
        
        # Test data cleaning
        cleaned_schedules = transformer.clean_schedules_data(schedules_df)
        cleaned_pbp = transformer.clean_pbp_data(pbp_df)
        
        print(f"Cleaned schedules: {len(cleaned_schedules)} records")
        print(f"Cleaned PBP: {len(cleaned_pbp)} records")
        
        # Test drive-level table assembly
        drive_table = transformer.assemble_drive_level_table(cleaned_pbp, cleaned_schedules)
        print(f"Drive-level table: {len(drive_table)} drives")
        
        # Test data quality validation
        validation = transformer.validate_data_quality(cleaned_schedules, 'schedules')
        print(f"Data quality validation: {validation['issues']}")


if __name__ == "__main__":
    main()
