"""
Starter mapping and injury scoring module for NFL Data Analysis.

This module handles:
- Starter determination based on depth charts, snap counts, and overrides
- Injury availability scoring by position group
- Weekly starter table generation
- Validation gate implementation

Sprint 1.6: Rosters & backups + Injuries ingestion
"""

import pandas as pd
import numpy as np
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime, timedelta
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StarterMapper:
    """Handles starter determination based on depth charts, snap counts, and overrides."""
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize starter mapper with configuration."""
        self.config = self._load_config(config_path)
        self.priority_order = self.config.get('starter_mapping', {}).get('priority_order', ['depth_chart', 'snaps', 'override'])
        self.position_groups = self.config.get('starter_mapping', {}).get('position_groups', {})
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def determine_starters_from_depth_charts(self, depth_charts_df: pd.DataFrame, 
                                           season: int, week: int) -> pd.DataFrame:
        """Determine starters from depth charts data."""
        logger.info(f"Determining starters from depth charts for season {season}, week {week}")
        
        # Filter for the specific season and week
        depth_data = depth_charts_df[
            (depth_charts_df['season'] == season) & 
            (depth_charts_df['week'] == week)
        ].copy()
        
        if depth_data.empty:
            logger.warning(f"No depth chart data found for season {season}, week {week}")
            return pd.DataFrame()
        
        # Create starter records
        starters = []
        
        for team in depth_data['depth_team'].unique():
            team_data = depth_data[depth_data['depth_team'] == team]
            
            for position in team_data['position'].unique():
                pos_data = team_data[team_data['position'] == position]
                
                # Sort by depth position (1 = starter, 2 = backup, etc.)
                pos_data = pos_data.sort_values('depth_position')
                
                # Get the starter (depth_position = 1)
                starter = pos_data[pos_data['depth_position'] == 1]
                
                if not starter.empty:
                    starter_record = {
                        'season': season,
                        'week': week,
                        'team': team,
                        'position': position,
                        'player_id': starter.iloc[0]['gsis_id'],
                        'is_starter': True,
                        'source': 'depth_chart',
                        'as_of': datetime.now().isoformat()
                    }
                    starters.append(starter_record)
        
        starters_df = pd.DataFrame(starters)
        logger.info(f"Determined {len(starters_df)} starters from depth charts")
        
        return starters_df
    
    def determine_starters_from_snap_counts(self, snap_counts_df: pd.DataFrame, 
                                         season: int, week: int) -> pd.DataFrame:
        """Determine starters from snap counts data."""
        logger.info(f"Determining starters from snap counts for season {season}, week {week}")
        
        # Filter for the specific season and week
        snap_data = snap_counts_df[
            (snap_counts_df['season'] == season) & 
            (snap_counts_df['week'] == week)
        ].copy()
        
        if snap_data.empty:
            logger.warning(f"No snap count data found for season {season}, week {week}")
            return pd.DataFrame()
        
        # Create starter records based on snap counts
        starters = []
        
        for team in snap_data['team'].unique():
            team_data = snap_data[snap_data['team'] == team]
            
            for position in team_data['position'].unique():
                pos_data = team_data[team_data['position'] == position].copy()
                
                # Calculate total snaps (offense + defense)
                pos_data['total_snaps'] = pos_data['offense_snaps'].fillna(0) + pos_data['defense_snaps'].fillna(0)
                
                # Sort by total snaps (descending)
                pos_data = pos_data.sort_values('total_snaps', ascending=False)
                
                # Get the player with most snaps as starter
                if not pos_data.empty and pos_data.iloc[0]['total_snaps'] > 0:
                    starter_record = {
                        'season': season,
                        'week': week,
                        'team': team,
                        'position': position,
                        'player_id': pos_data.iloc[0]['player'],
                        'is_starter': True,
                        'source': 'snaps',
                        'as_of': datetime.now().isoformat()
                    }
                    starters.append(starter_record)
        
        starters_df = pd.DataFrame(starters)
        logger.info(f"Determined {len(starters_df)} starters from snap counts")
        
        return starters_df
    
    def merge_starter_sources(self, depth_chart_starters: pd.DataFrame, 
                            snap_count_starters: pd.DataFrame) -> pd.DataFrame:
        """Merge starter sources with priority: depth_chart > snaps > override."""
        logger.info("Merging starter sources with priority order")
        
        # Start with depth chart starters (or empty DataFrame if none)
        if depth_chart_starters.empty:
            merged_starters = pd.DataFrame(columns=['season', 'week', 'team', 'position', 'player_id', 'is_starter', 'source', 'as_of'])
        else:
            merged_starters = depth_chart_starters.copy()
        
        # Add snap count starters for positions not covered by depth charts
        if not snap_count_starters.empty:
            for _, snap_starter in snap_count_starters.iterrows():
                key = (snap_starter['season'], snap_starter['week'], 
                      snap_starter['team'], snap_starter['position'])
                
                # Check if this position is already covered by depth chart
                if not merged_starters.empty:
                    existing = merged_starters[
                        (merged_starters['season'] == key[0]) &
                        (merged_starters['week'] == key[1]) &
                        (merged_starters['team'] == key[2]) &
                        (merged_starters['position'] == key[3])
                    ]
                else:
                    existing = pd.DataFrame()
                
                if existing.empty:
                    merged_starters = pd.concat([merged_starters, snap_starter.to_frame().T], ignore_index=True)
        
        logger.info(f"Merged {len(merged_starters)} total starters")
        return merged_starters
    
    def generate_weekly_starter_table(self, season: int, week: int, 
                                    depth_charts_df: pd.DataFrame,
                                    snap_counts_df: pd.DataFrame) -> pd.DataFrame:
        """Generate weekly starter table combining all sources."""
        logger.info(f"Generating weekly starter table for season {season}, week {week}")
        
        # Determine starters from each source
        depth_chart_starters = self.determine_starters_from_depth_charts(
            depth_charts_df, season, week)
        snap_count_starters = self.determine_starters_from_snap_counts(
            snap_counts_df, season, week)
        
        # Merge sources with priority
        weekly_starters = self.merge_starter_sources(
            depth_chart_starters, snap_count_starters)
        
        # Add backup records (non-starters)
        weekly_starters = self._add_backup_records(
            weekly_starters, depth_charts_df, snap_counts_df, season, week)
        
        logger.info(f"Generated weekly starter table with {len(weekly_starters)} records")
        return weekly_starters
    
    def _add_backup_records(self, starters_df: pd.DataFrame, 
                          depth_charts_df: pd.DataFrame,
                          snap_counts_df: pd.DataFrame,
                          season: int, week: int) -> pd.DataFrame:
        """Add backup (non-starter) records to the starter table."""
        logger.info("Adding backup records to starter table")
        
        # Get all unique team-position combinations from depth charts
        depth_data = depth_charts_df[
            (depth_charts_df['season'] == season) & 
            (depth_charts_df['week'] == week)
        ]
        
        all_combinations = depth_data[['depth_team', 'position', 'gsis_id']].drop_duplicates()
        
        # Add backup records for players not marked as starters
        backup_records = []
        
        for _, row in all_combinations.iterrows():
            team, position, player_id = row['depth_team'], row['position'], row['gsis_id']
            
            # Check if this player is already a starter
            is_starter = starters_df[
                (starters_df['team'] == team) &
                (starters_df['position'] == position) &
                (starters_df['player_id'] == player_id)
            ]
            
            if is_starter.empty:
                backup_record = {
                    'season': season,
                    'week': week,
                    'team': team,
                    'position': position,
                    'player_id': player_id,
                    'is_starter': False,
                    'source': 'depth_chart',
                    'as_of': datetime.now().isoformat()
                }
                backup_records.append(backup_record)
        
        # Combine starters and backups
        if backup_records:
            backup_df = pd.DataFrame(backup_records)
            combined_df = pd.concat([starters_df, backup_df], ignore_index=True)
        else:
            combined_df = starters_df
        
        logger.info(f"Added {len(backup_records)} backup records")
        return combined_df


class InjuryScorer:
    """Handles injury availability scoring by position group."""
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize injury scorer with configuration."""
        self.config = self._load_config(config_path)
        self.position_priority = self.config.get('injury_scoring', {}).get('position_priority', {})
        self.status_scores = self.config.get('injury_scoring', {}).get('status_scores', {})
        self.practice_scores = self.config.get('injury_scoring', {}).get('practice_scores', {})
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def calculate_injury_scores(self, injuries_df: pd.DataFrame, 
                              season: int, week: int) -> pd.DataFrame:
        """Calculate injury availability scores for all players."""
        logger.info(f"Calculating injury scores for season {season}, week {week}")
        
        # Filter for the specific season and week
        injury_data = injuries_df[
            (injuries_df['season'] == season) & 
            (injuries_df['week'] == week)
        ].copy()
        
        if injury_data.empty:
            logger.warning(f"No injury data found for season {season}, week {week}")
            return pd.DataFrame()
        
        # Calculate availability scores
        injury_data['status_score'] = injury_data['report_status'].map(self.status_scores).fillna(1.0)
        injury_data['practice_score'] = injury_data['practice_status'].map(self.practice_scores).fillna(1.0)
        
        # Combined availability score (weighted average)
        injury_data['availability_score'] = (
            injury_data['status_score'] * 0.7 + 
            injury_data['practice_score'] * 0.3
        )
        
        # Position priority score
        injury_data['position_priority'] = injury_data['position'].map(self.position_priority).fillna(1)
        
        # Weighted availability score
        injury_data['weighted_availability'] = (
            injury_data['availability_score'] * injury_data['position_priority']
        )
        
        logger.info(f"Calculated injury scores for {len(injury_data)} players")
        return injury_data
    
    def calculate_team_injury_metrics(self, injury_scores_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate team-level injury metrics."""
        logger.info("Calculating team-level injury metrics")
        
        team_metrics = []
        
        for team in injury_scores_df['team'].unique():
            team_data = injury_scores_df[injury_scores_df['team'] == team]
            
            # Count players by injury status
            out_count = len(team_data[team_data['report_status'] == 'out'])
            questionable_count = len(team_data[team_data['report_status'] == 'questionable'])
            
            # Calculate position-weighted availability index
            total_weighted_availability = team_data['weighted_availability'].sum()
            total_position_priority = team_data['position_priority'].sum()
            availability_index = total_weighted_availability / total_position_priority if total_position_priority > 0 else 1.0
            
            team_metric = {
                'team': team,
                'inj_out_count': out_count,
                'inj_q_count': questionable_count,
                'availability_index': availability_index,
                'total_players': len(team_data)
            }
            team_metrics.append(team_metric)
        
        team_metrics_df = pd.DataFrame(team_metrics)
        logger.info(f"Calculated injury metrics for {len(team_metrics_df)} teams")
        
        return team_metrics_df


class ValidationGate:
    """Implements validation gate for Sprint 1.6."""
    
    def __init__(self, config_path: str = "configs/paths.yaml"):
        """Initialize validation gate with configuration."""
        self.config = self._load_config(config_path)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def validate_data_quality(self, season: int, week: int) -> Dict[str, bool]:
        """Validate data quality for Sprint 1.6 requirements."""
        logger.info(f"Running validation gate for season {season}, week {week}")
        
        validation_results = {}
        
        try:
            # Check spreads present
            spreads_present = self._check_spreads_present(season, week)
            validation_results['spreads_present'] = spreads_present
            
            # Check EPA/WP/cp non-null in PBP
            pbp_valid = self._check_pbp_valid(season, week)
            validation_results['pbp_valid'] = pbp_valid
            
            # Check injuries observed for ≥ 28 teams
            injuries_valid = self._check_injuries_valid(season, week)
            validation_results['injuries_valid'] = injuries_valid
            
            # Check weekly starter table populated
            starters_valid = self._check_starters_valid(season, week)
            validation_results['starters_valid'] = starters_valid
            
            # Overall validation
            all_valid = all(validation_results.values())
            validation_results['overall'] = all_valid
            
            logger.info(f"Validation results: {validation_results}")
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            validation_results['overall'] = False
        
        return validation_results
    
    def _check_spreads_present(self, season: int, week: int) -> bool:
        """Check if spreads are present in schedules data."""
        try:
            schedules_path = Path(self.config['data']['parquet_lake']) / 'schedules'
            schedule_files = list(schedules_path.glob(f'**/season={season}/**/*.parquet'))
            
            if not schedule_files:
                logger.warning(f"No schedule files found for season {season}")
                return False
            
            # Read the most recent schedule file
            latest_file = max(schedule_files, key=os.path.getctime)
            schedules_df = pd.read_parquet(latest_file)
            
            # Filter for the specific week
            week_data = schedules_df[schedules_df['week'] == week]
            
            # Check if spreads are present
            spreads_present = (
                'spread_line' in week_data.columns and 
                week_data['spread_line'].notna().any()
            )
            
            logger.info(f"Spreads present: {spreads_present}")
            return spreads_present
            
        except Exception as e:
            logger.error(f"Failed to check spreads: {e}")
            return False
    
    def _check_pbp_valid(self, season: int, week: int) -> bool:
        """Check if EPA/WP/cp are non-null in PBP data."""
        try:
            pbp_path = Path(self.config['data']['parquet_lake']) / 'pbp'
            pbp_files = list(pbp_path.glob(f'**/season={season}/**/*.parquet'))
            
            if not pbp_files:
                logger.warning(f"No PBP files found for season {season}")
                return False
            
            # Read the most recent PBP file
            latest_file = max(pbp_files, key=os.path.getctime)
            pbp_df = pd.read_parquet(latest_file)
            
            # Filter for the specific week
            week_data = pbp_df[pbp_df['week'] == week]
            
            # Check if EPA/WP/cp are non-null
            epa_valid = 'epa' in week_data.columns and week_data['epa'].notna().any()
            wp_valid = 'wp' in week_data.columns and week_data['wp'].notna().any()
            cp_valid = 'cp' in week_data.columns and week_data['cp'].notna().any()
            
            pbp_valid = epa_valid and wp_valid and cp_valid
            
            logger.info(f"PBP valid (EPA: {epa_valid}, WP: {wp_valid}, CP: {cp_valid}): {pbp_valid}")
            return pbp_valid
            
        except Exception as e:
            logger.error(f"Failed to check PBP: {e}")
            return False
    
    def _check_injuries_valid(self, season: int, week: int) -> bool:
        """Check if injuries observed for ≥ 28 teams."""
        try:
            injuries_path = Path(self.config['data']['parquet_lake']) / 'injuries'
            injury_files = list(injuries_path.glob(f'**/season={season}/**/*.parquet'))
            
            if not injury_files:
                logger.warning(f"No injury files found for season {season}")
                return False
            
            # Read the most recent injury file
            latest_file = max(injury_files, key=os.path.getctime)
            injuries_df = pd.read_parquet(latest_file)
            
            # Filter for the specific week
            week_data = injuries_df[injuries_df['week'] == week]
            
            # Count teams with injury data
            teams_with_injuries = week_data['team'].nunique()
            injuries_valid = teams_with_injuries >= 28
            
            logger.info(f"Injuries valid ({teams_with_injuries} teams): {injuries_valid}")
            return injuries_valid
            
        except Exception as e:
            logger.error(f"Failed to check injuries: {e}")
            return False
    
    def _check_starters_valid(self, season: int, week: int) -> bool:
        """Check if weekly starter table is populated."""
        try:
            starters_path = Path(self.config['data']['parquet_lake']) / 'starters'
            starter_files = list(starters_path.glob(f'**/season={season}/**/*.parquet'))
            
            if not starter_files:
                logger.warning(f"No starter files found for season {season}")
                return False
            
            # Read the most recent starter file
            latest_file = max(starter_files, key=os.path.getctime)
            starters_df = pd.read_parquet(latest_file)
            
            # Filter for the specific week
            week_data = starters_df[starters_df['week'] == week]
            
            # Check if starter table is populated
            starters_valid = len(week_data) > 0
            
            logger.info(f"Starters valid ({len(week_data)} records): {starters_valid}")
            return starters_valid
            
        except Exception as e:
            logger.error(f"Failed to check starters: {e}")
            return False


def main():
    """CLI interface for testing the starter mapping and injury scoring."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Starter Mapping and Injury Scoring')
    parser.add_argument('--season', type=int, default=2024, help='Season to process')
    parser.add_argument('--week', type=int, default=1, help='Week to process')
    parser.add_argument('--action', choices=['starters', 'injuries', 'validate'], 
                       default='starters', help='Action to perform')
    args = parser.parse_args()
    
    if args.action == 'starters':
        # Test starter mapping
        logger.info(f"Testing starter mapping for season {args.season}, week {args.week}")
        
        # Load data
        from src.data.readers import DepthChartsReader, SnapCountsReader
        
        depth_reader = DepthChartsReader()
        snap_reader = SnapCountsReader()
        
        depth_charts_df = depth_reader.load_depth_charts(args.season, args.week)
        snap_counts_df = snap_reader.load_snap_counts(args.season, args.week)
        
        # Generate starter table
        starter_mapper = StarterMapper()
        weekly_starters = starter_mapper.generate_weekly_starter_table(
            args.season, args.week, depth_charts_df, snap_counts_df)
        
        print(f"Generated {len(weekly_starters)} starter records")
        print(f"Starters by source:")
        print(weekly_starters['source'].value_counts())
        
    elif args.action == 'injuries':
        # Test injury scoring
        logger.info(f"Testing injury scoring for season {args.season}, week {args.week}")
        
        from src.data.readers import InjuriesReader
        
        injuries_reader = InjuriesReader()
        injuries_df = injuries_reader.load_injuries(args.season, args.week)
        
        # Calculate injury scores
        injury_scorer = InjuryScorer()
        injury_scores = injury_scorer.calculate_injury_scores(
            injuries_df, args.season, args.week)
        
        team_metrics = injury_scorer.calculate_team_injury_metrics(injury_scores)
        
        print(f"Calculated injury scores for {len(injury_scores)} players")
        print(f"Team injury metrics:")
        print(team_metrics.head())
        
    elif args.action == 'validate':
        # Test validation gate
        logger.info(f"Testing validation gate for season {args.season}, week {args.week}")
        
        validation_gate = ValidationGate()
        validation_results = validation_gate.validate_data_quality(args.season, args.week)
        
        print(f"Validation results: {validation_results}")
        
        if validation_results.get('overall', False):
            print("✅ Validation gate PASSED - Ready to proceed!")
        else:
            print("❌ Validation gate FAILED - Issues need to be resolved")


if __name__ == "__main__":
    main()
