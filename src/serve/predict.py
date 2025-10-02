"""
CLI baseline prediction module for Sprint 2.4.

This module implements CLI baseline prediction functionality as specified in Sprint 2.4.

Purpose: Save model + scaler + column order; add CLI baseline prediction.
Features:
- Load trained model artifacts
- Make predictions for specific games
- Command-line interface for predictions
- Support for single game or batch predictions
"""

import pandas as pd
import numpy as np
import logging
import yaml
import joblib
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from src.features.assemble import FeatureAssembler
from src.models.baseline import BaselineModelTrainer

logger = logging.getLogger(__name__)


class BaselinePredictor:
    """
    CLI baseline predictor for NFL game predictions.
    
    Implements Sprint 2.4 requirements:
    - Load saved model artifacts (model, scaler, column order)
    - Make predictions for specific games
    - Command-line interface for predictions
    """
    
    def __init__(self, model_dir: str = "models/baseline"):
        """Initialize the baseline predictor."""
        self.model_dir = Path(model_dir)
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.metrics = None
        
        logger.info("Initialized BaselinePredictor")
    
    def load_latest_model(self) -> bool:
        """
        Load the latest trained model artifacts.
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        logger.info("Loading latest model artifacts")
        
        try:
            # Find the latest model files
            model_files = list(self.model_dir.glob("baseline_model_*.joblib"))
            scaler_files = list(self.model_dir.glob("baseline_scaler_*.joblib"))
            features_files = list(self.model_dir.glob("baseline_features_*.yaml"))
            metrics_files = list(self.model_dir.glob("baseline_metrics_*.yaml"))
            
            if not model_files:
                logger.error("No model files found")
                return False
            
            # Get the latest files (by timestamp in filename)
            latest_model = max(model_files, key=lambda x: x.stem.split('_')[-1])
            latest_scaler = max(scaler_files, key=lambda x: x.stem.split('_')[-1])
            latest_features = max(features_files, key=lambda x: x.stem.split('_')[-1])
            latest_metrics = max(metrics_files, key=lambda x: x.stem.split('_')[-1])
            
            # Load model artifacts
            self.model = joblib.load(latest_model)
            self.scaler = joblib.load(latest_scaler)
            
            with open(latest_features, 'r') as f:
                features_data = yaml.safe_load(f)
                self.feature_columns = features_data['feature_columns']
            
            with open(latest_metrics, 'r') as f:
                self.metrics = yaml.safe_load(f)
            
            logger.info(f"Loaded model artifacts:")
            logger.info(f"  Model: {latest_model}")
            logger.info(f"  Scaler: {latest_scaler}")
            logger.info(f"  Features: {latest_features}")
            logger.info(f"  Metrics: {latest_metrics}")
            logger.info(f"  Feature count: {len(self.feature_columns)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model artifacts: {e}")
            return False
    
    def predict_game(self, home_team: str, away_team: str, season: int, week: int) -> Dict[str, Any]:
        """
        Predict the outcome of a specific game.
        
        Args:
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            season: NFL season year
            week: Week number
            
        Returns:
            Dictionary with prediction results
        """
        logger.info(f"Predicting {away_team} @ {home_team} (Season {season}, Week {week})")
        
        if not self.model or not self.scaler:
            raise ValueError("Model not loaded. Call load_latest_model() first.")
        
        try:
            # Assemble features for the game
            assembler = FeatureAssembler()
            modeling_table = assembler.assemble_modeling_table(season, week, use_historical_data=True)
            
            # Filter for the specific game
            game_data = modeling_table[
                (modeling_table['team'].isin([home_team, away_team])) &
                (modeling_table['season'] == season) &
                (modeling_table['week'] == week)
            ]
            
            if game_data.empty:
                raise ValueError(f"No data found for {away_team} @ {home_team} in season {season}, week {week}")
            
            # Prepare features for both teams
            predictions = {}
            
            for _, team_data in game_data.iterrows():
                team = team_data['team']
                is_home = team_data['home']
                
                # Extract features
                features = team_data[self.feature_columns].fillna(0).values.reshape(1, -1)
                
                # Scale features
                features_scaled = self.scaler.transform(features)
                
                # Make prediction
                win_probability = self.model.predict_proba(features_scaled)[0, 1]
                
                predictions[team] = {
                    'team': team,
                    'is_home': is_home,
                    'win_probability': win_probability,
                    'predicted_outcome': 'Win' if win_probability > 0.5 else 'Loss'
                }
            
            # Create game summary
            home_pred = predictions[home_team]
            away_pred = predictions[away_team]
            
            result = {
                'game': f"{away_team} @ {home_team}",
                'season': season,
                'week': week,
                'home_team': {
                    'team': home_team,
                    'win_probability': home_pred['win_probability'],
                    'predicted_outcome': home_pred['predicted_outcome']
                },
                'away_team': {
                    'team': away_team,
                    'win_probability': away_pred['win_probability'],
                    'predicted_outcome': away_pred['predicted_outcome']
                },
                'predicted_winner': home_team if home_pred['win_probability'] > away_pred['win_probability'] else away_team,
                'confidence': abs(home_pred['win_probability'] - away_pred['win_probability']),
                'model_info': {
                    'feature_count': len(self.feature_columns),
                    'training_samples': self.metrics.get('training_data_size', 'Unknown'),
                    'model_performance': {
                        'log_loss': self.metrics.get('test_metrics', {}).get('log_loss', 'Unknown'),
                        'brier_score': self.metrics.get('test_metrics', {}).get('brier_score', 'Unknown'),
                        'roc_auc': self.metrics.get('test_metrics', {}).get('roc_auc', 'Unknown')
                    }
                }
            }
            
            logger.info(f"Prediction completed: {result['predicted_winner']} wins (confidence: {result['confidence']:.3f})")
            return result
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise
    
    def predict_week(self, season: int, week: int) -> List[Dict[str, Any]]:
        """
        Predict all games for a specific week.
        
        Args:
            season: NFL season year
            week: Week number
            
        Returns:
            List of prediction results for all games
        """
        logger.info(f"Predicting all games for Season {season}, Week {week}")
        
        try:
            # Get all games for the week
            assembler = FeatureAssembler()
            modeling_table = assembler.assemble_modeling_table(season, week, use_historical_data=True)
            
            # Get unique games
            games = modeling_table[modeling_table['week'] == week]['game_id'].unique()
            
            predictions = []
            
            for game_id in games:
                # Extract teams from game_id (format: YYYY_WW_HOME_AWAY)
                parts = game_id.split('_')
                if len(parts) >= 4:
                    home_team = parts[2]
                    away_team = parts[3]
                    
                    try:
                        prediction = self.predict_game(home_team, away_team, season, week)
                        predictions.append(prediction)
                    except Exception as e:
                        logger.warning(f"Failed to predict {game_id}: {e}")
                        continue
            
            logger.info(f"Completed predictions for {len(predictions)} games")
            return predictions
            
        except Exception as e:
            logger.error(f"Week prediction failed: {e}")
            raise


def create_cli_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="NFL Game Prediction CLI - Sprint 2.4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Predict a specific game
  python -m src.serve.predict --home KC --away BUF --season 2024 --week 1
  
  # Predict all games in a week
  python -m src.serve.predict --season 2024 --week 1 --all-games
  
  # Predict with custom model directory
  python -m src.serve.predict --home KC --away BUF --season 2024 --week 1 --model-dir models/custom
        """
    )
    
    parser.add_argument('--home', type=str, help='Home team abbreviation (e.g., KC)')
    parser.add_argument('--away', type=str, help='Away team abbreviation (e.g., BUF)')
    parser.add_argument('--season', type=int, required=True, help='NFL season year (e.g., 2024)')
    parser.add_argument('--week', type=int, required=True, help='Week number (e.g., 1)')
    parser.add_argument('--all-games', action='store_true', help='Predict all games for the specified week')
    parser.add_argument('--model-dir', type=str, default='models/baseline', help='Model directory path')
    parser.add_argument('--output', type=str, help='Output file path (JSON format)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    return parser


def format_prediction_output(prediction: Dict[str, Any], verbose: bool = False) -> str:
    """Format prediction output for display."""
    output = []
    
    # Game header
    output.append(f"🏈 {prediction['game']} (Season {prediction['season']}, Week {prediction['week']})")
    output.append("=" * 60)
    
    # Team predictions
    home = prediction['home_team']
    away = prediction['away_team']
    
    output.append(f"🏠 {home['team']}: {home['win_probability']:.1%} chance to win")
    output.append(f"✈️  {away['team']}: {away['win_probability']:.1%} chance to win")
    output.append("")
    
    # Winner prediction
    winner = prediction['predicted_winner']
    confidence = prediction['confidence']
    output.append(f"🎯 Predicted Winner: {winner}")
    output.append(f"📊 Confidence: {confidence:.1%}")
    output.append("")
    
    if verbose:
        # Model info
        model_info = prediction['model_info']
        output.append("📈 Model Information:")
        output.append(f"  Features: {model_info['feature_count']}")
        output.append(f"  Training samples: {model_info['training_samples']:,}")
        
        perf = model_info['model_performance']
        output.append(f"  Log Loss: {perf['log_loss']:.4f}")
        output.append(f"  Brier Score: {perf['brier_score']:.4f}")
        output.append(f"  ROC AUC: {perf['roc_auc']:.4f}")
        output.append("")
    
    return "\n".join(output)


def main():
    """Main CLI function."""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize predictor
        predictor = BaselinePredictor(args.model_dir)
        
        # Load model
        if not predictor.load_latest_model():
            print("❌ Failed to load model. Make sure you have trained a model first.")
            return 1
        
        print("✅ Model loaded successfully")
        print("")
        
        # Make predictions
        if args.all_games:
            # Predict all games for the week
            predictions = predictor.predict_week(args.season, args.week)
            
            print(f"🏈 Week {args.week} Predictions (Season {args.season})")
            print("=" * 50)
            print("")
            
            for i, prediction in enumerate(predictions, 1):
                print(f"Game {i}: {prediction['game']}")
                print(f"  Winner: {prediction['predicted_winner']} (confidence: {prediction['confidence']:.1%})")
                print("")
            
            # Save to file if requested
            if args.output:
                import json
                with open(args.output, 'w') as f:
                    json.dump(predictions, f, indent=2)
                print(f"✅ Predictions saved to {args.output}")
        
        else:
            # Predict specific game
            if not args.home or not args.away:
                print("❌ Error: --home and --away are required for single game prediction")
                return 1
            
            prediction = predictor.predict_game(args.home, args.away, args.season, args.week)
            
            # Display results
            output = format_prediction_output(prediction, args.verbose)
            print(output)
            
            # Save to file if requested
            if args.output:
                import json
                with open(args.output, 'w') as f:
                    json.dump(prediction, f, indent=2)
                print(f"✅ Prediction saved to {args.output}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
