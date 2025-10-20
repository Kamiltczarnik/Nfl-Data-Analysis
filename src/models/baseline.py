"""
Baseline logistic regression model trainer for NFL game prediction.

This module implements a comprehensive baseline model trainer that handles
data preparation, scaling, hyperparameter tuning, cross-validation, and evaluation.
"""

import logging
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime

from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score, accuracy_score
from sklearn.calibration import calibration_curve
import yaml

logger = logging.getLogger(__name__)


class BaselineModelTrainer:
    """
    Train and evaluate a baseline logistic regression model for NFL game prediction.
    
    Features:
    - Data preparation and scaling
    - Hyperparameter tuning with cross-validation
    - Comprehensive evaluation metrics
    - Model persistence and artifact management
    - Feature importance analysis
    """
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        
        # Model parameters
        self.test_size = 0.2
        self.random_state = 42
        self.cv_folds = 5
        
        logger.info("Initialized BaselineModelTrainer")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    
    def train_model(self, modeling_df: pd.DataFrame, test_size: float = 0.2, 
                   hyperparameter_tuning: bool = True, save_model: bool = True) -> Dict[str, Any]:
        """
        Train the baseline logistic regression model.
        
        Args:
            modeling_df: DataFrame with features and target
            test_size: Fraction of data to use for testing
            hyperparameter_tuning: Whether to perform hyperparameter tuning
            save_model: Whether to save model artifacts
            
        Returns:
            Dictionary with training results and metrics
        """
        logger.info("Starting baseline model training")
        
        # Prepare data
        X, y = self._prepare_data(modeling_df)
        logger.info(f"Prepared data: {X.shape[0]} samples, {X.shape[1]} features")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=self.random_state, stratify=y
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        if hyperparameter_tuning:
            self.model = self._train_with_tuning(X_train_scaled, y_train)
        else:
            self.model = LogisticRegression(random_state=self.random_state, max_iter=1000)
            self.model.fit(X_train_scaled, y_train)
        
        # Evaluate model
        train_metrics = self._evaluate_model(X_train_scaled, y_train, "Training")
        test_metrics = self._evaluate_model(X_test_scaled, y_test, "Test")
        
        # Cross-validation
        cv_scores = cross_val_score(
            self.model, X_train_scaled, y_train, 
            cv=self.cv_folds, scoring='neg_log_loss'
        )
        
        # Feature importance
        feature_importance = self._get_feature_importance()
        
        # Compile results
        results = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns,
            'training_metrics': train_metrics,
            'test_metrics': test_metrics,
            'cv_scores': cv_scores,
            'cv_mean': cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'feature_importance': feature_importance,
            'training_data_size': len(X_train),
            'test_data_size': len(X_test),
            'feature_count': X.shape[1]
        }
        
        # Save model if requested
        if save_model:
            self._save_model_artifacts(results)
        
        logger.info(f"Model training completed. Test Log Loss: {test_metrics['log_loss']:.4f}")
        return results
    
    def _prepare_data(self, modeling_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features and target for training."""
        # Get feature columns
        feature_cols = self._get_feature_columns(modeling_df)
        self.feature_columns = feature_cols
        
        # Extract features and target
        X = modeling_df[feature_cols].fillna(0).values
        y = modeling_df['result'].values
        
        logger.info(f"Prepared {len(feature_cols)} features for training")
        return X, y
    
    def _get_feature_columns(self, modeling_df: pd.DataFrame) -> List[str]:
        """Get list of feature columns for training."""
        # Exclude non-feature columns
        exclude_cols = [
            'season', 'week', 'game_id', 'team', 'opponent', 'home', 
            'team_type', 'home_score', 'away_score', 'result'
        ]
        
        # Get all numeric columns that aren't excluded
        feature_cols = [
            col for col in modeling_df.columns 
            if col not in exclude_cols and modeling_df[col].dtype in ['int64', 'float64']
        ]
        
        return feature_cols
    
    def _train_with_tuning(self, X_train: np.ndarray, y_train: np.ndarray) -> LogisticRegression:
        """Train model with hyperparameter tuning."""
        logger.info("Performing hyperparameter tuning")
        
        # Define parameter grid
        param_grid = {
            'C': [0.1, 1.0, 10.0, 100.0],
            'penalty': ['l1', 'l2'],
            'solver': ['liblinear', 'saga']
        }
        
        # Grid search with cross-validation
        grid_search = GridSearchCV(
            LogisticRegression(random_state=self.random_state, max_iter=1000),
            param_grid,
            cv=self.cv_folds,
            scoring='neg_log_loss',
            n_jobs=-1
        )
        
        grid_search.fit(X_train, y_train)
        
        logger.info(f"Best parameters: {grid_search.best_params_}")
        logger.info(f"Best CV score: {-grid_search.best_score_:.4f}")
        
        return grid_search.best_estimator_
    
    def _evaluate_model(self, X: np.ndarray, y: np.ndarray, split_name: str) -> Dict[str, float]:
        """Evaluate model performance."""
        # Predictions
        y_pred_proba = self.model.predict_proba(X)[:, 1]
        y_pred = self.model.predict(X)
        
        # Calculate metrics
        metrics = {
            'log_loss': log_loss(y, y_pred_proba),
            'brier_score': brier_score_loss(y, y_pred_proba),
            'roc_auc': roc_auc_score(y, y_pred_proba),
            'accuracy': accuracy_score(y, y_pred)
        }
        
        # Calibration slope
        try:
            fraction_of_positives, mean_predicted_value = calibration_curve(y, y_pred_proba, n_bins=10)
            if len(fraction_of_positives) > 1:
                calibration_slope = np.polyfit(mean_predicted_value, fraction_of_positives, 1)[0]
            else:
                calibration_slope = 1.0
        except:
            calibration_slope = 1.0
        
        metrics['calibration_slope'] = calibration_slope
        
        logger.info(f"{split_name} Metrics:")
        logger.info(f"  Log Loss: {metrics['log_loss']:.4f}")
        logger.info(f"  Brier Score: {metrics['brier_score']:.4f}")
        logger.info(f"  ROC AUC: {metrics['roc_auc']:.4f}")
        logger.info(f"  Accuracy: {metrics['accuracy']:.4f}")
        logger.info(f"  Calibration Slope: {metrics['calibration_slope']:.4f}")
        
        return metrics
    
    def _get_feature_importance(self) -> pd.DataFrame:
        """Get feature importance from the trained model."""
        if self.model is None or self.feature_columns is None:
            return pd.DataFrame()
        
        # Get coefficients (absolute values for importance)
        importance = np.abs(self.model.coef_[0])
        
        # Create DataFrame
        importance_df = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': importance
        }).sort_values('importance', ascending=False)
        
        return importance_df
    
    def _save_model_artifacts(self, results: Dict[str, Any]) -> str:
        """Save model artifacts to disk."""
        # Create run directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path("models/baseline") / f"2024_week18_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Save artifacts
        model_file = run_dir / "model.joblib"
        scaler_file = run_dir / "scaler.joblib"
        feature_columns_file = run_dir / "feature_columns.joblib"
        metrics_file = run_dir / "metrics.joblib"
        
        joblib.dump(self.model, model_file)
        joblib.dump(self.scaler, scaler_file)
        joblib.dump(self.feature_columns, feature_columns_file)
        joblib.dump(results['test_metrics'], metrics_file)
        
        logger.info(f"Model artifacts saved to {run_dir}")
        return str(run_dir)
    
    def load_model_artifacts(self, model_dir: str) -> Dict[str, Any]:
        """Load model artifacts from disk."""
        model_path = Path(model_dir)
        
        self.model = joblib.load(model_path / "model.joblib")
        self.scaler = joblib.load(model_path / "scaler.joblib")
        self.feature_columns = joblib.load(model_path / "feature_columns.joblib")
        metrics = joblib.load(model_path / "metrics.joblib")
        
        logger.info(f"Model artifacts loaded from {model_dir}")
        
        return {
            'model': self.model,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns,
            'metrics': metrics
        }
    
    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Make predictions using the trained model."""
        if self.model is None:
            raise ValueError("Model not trained. Call train_model() first.")
        
        X_scaled = self.scaler.transform(X)
        y_pred_proba = self.model.predict_proba(X_scaled)[:, 1]
        y_pred = self.model.predict(X_scaled)
        
        return y_pred, y_pred_proba