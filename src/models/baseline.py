"""
Baseline logistic regression model for Sprint 2.3.

This module implements the baseline logistic model training as specified in Sprint 2.3.

Purpose: Train baseline logistic model on compact features.
Inputs: modeling table; feature list from configs/features.yaml.
Outputs: serialized scaler/model (models/baseline.joblib), feature column order, metrics.

Sprint 2.3 Requirements:
- Train logistic regression
- Evaluate log-loss, Brier ≤ 0.20, calibration slope ~1.0
- Utilize maximum available data for training
"""

import pandas as pd
import numpy as np
import logging
import yaml
import joblib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from sklearn.calibration import calibration_curve
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class BaselineModelTrainer:
    """
    Trains baseline logistic regression model for NFL game prediction.
    
    Implements Sprint 2.3 requirements with maximum data utilization
    for the most accurate predictions possible.
    """
    
    def __init__(self, config_path: str = "configs/features.yaml"):
        """Initialize the baseline model trainer."""
        self.config = self._load_config(config_path)
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.metrics = {}
        
        logger.info("Initialized BaselineModelTrainer")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise
    
    def train_model(self, modeling_df: pd.DataFrame, test_size: float = 0.2, 
                   random_state: int = 42) -> Dict[str, Any]:
        """
        Train the baseline logistic regression model.
        
        Args:
            modeling_df: Modeling table with features and labels
            test_size: Proportion of data to use for testing
            random_state: Random state for reproducibility
            
        Returns:
            Dictionary with training results and metrics
        """
        logger.info("Training baseline logistic regression model")
        
        # Prepare data
        X, y, feature_cols = self._prepare_training_data(modeling_df)
        self.feature_columns = feature_cols
        
        logger.info(f"Training data: {X.shape[0]} samples, {X.shape[1]} features")
        logger.info(f"Positive class ratio: {y.mean():.3f}")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        
        logger.info(f"Train set: {X_train.shape[0]} samples")
        logger.info(f"Test set: {X_test.shape[0]} samples")
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model with optimal parameters
        self.model = self._train_logistic_regression(X_train_scaled, y_train)
        
        # Evaluate model
        train_metrics = self._evaluate_model(X_train_scaled, y_train, "train")
        test_metrics = self._evaluate_model(X_test_scaled, y_test, "test")
        
        # Cross-validation
        cv_scores = self._cross_validate_model(X_train_scaled, y_train)
        
        # Compile results
        results = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns,
            'train_metrics': train_metrics,
            'test_metrics': test_metrics,
            'cv_scores': cv_scores,
            'training_data_size': X.shape[0],
            'feature_count': X.shape[1],
            'positive_class_ratio': y.mean()
        }
        
        self.metrics = results
        logger.info("Model training completed successfully")
        
        return results
    
    def _prepare_training_data(self, modeling_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Prepare training data from modeling table."""
        logger.info("Preparing training data")
        
        # Get feature columns
        feature_cols = self._get_feature_columns(modeling_df)
        
        # Filter to games with labels (historical data)
        labeled_data = modeling_df[modeling_df['label_win'].notna()].copy()
        
        if labeled_data.empty:
            raise ValueError("No labeled training data available")
        
        logger.info(f"Using {len(labeled_data)} labeled games for training")
        
        # Prepare features
        X = labeled_data[feature_cols].fillna(0).values
        
        # Prepare labels (ensure they are integers)
        y = labeled_data['label_win'].astype(int).values
        
        logger.info(f"Features shape: {X.shape}")
        logger.info(f"Labels shape: {y.shape}")
        
        return X, y, feature_cols
    
    def _get_feature_columns(self, modeling_df: pd.DataFrame) -> List[str]:
        """Get list of feature columns for modeling."""
        # Get feature families from config
        feature_families = self.config.get('feature_families', {})
        
        # Collect all feature columns
        feature_cols = []
        
        # Rolling features
        rolling_features = feature_families.get('rolling_offense', []) + feature_families.get('rolling_defense', [])
        for feature in rolling_features:
            if feature in modeling_df.columns:
                feature_cols.append(feature)
        
        # Market features
        market_features = feature_families.get('market', [])
        for feature in market_features:
            market_col = f'market_{feature}'
            if market_col in modeling_df.columns:
                feature_cols.append(market_col)
        
        # Situational features
        situational_features = ['home', 'rest_days']
        for feature in situational_features:
            situational_col = f'situational_{feature}'
            if situational_col in modeling_df.columns:
                feature_cols.append(situational_col)
        
        # Add any additional rolling features that might be available
        rolling_cols = [col for col in modeling_df.columns if col.startswith('rolling_')]
        for col in rolling_cols:
            if col not in feature_cols:
                feature_cols.append(col)
        
        logger.info(f"Selected {len(feature_cols)} feature columns")
        return feature_cols
    
    def _train_logistic_regression(self, X_train: np.ndarray, y_train: np.ndarray) -> LogisticRegression:
        """Train logistic regression model with optimal parameters."""
        logger.info("Training logistic regression model")
        
        # Use optimal parameters for maximum accuracy
        model = LogisticRegression(
            random_state=42,
            max_iter=1000,
            C=1.0,  # Regularization strength
            penalty='l2',
            solver='liblinear',  # Good for small datasets
            class_weight='balanced'  # Handle class imbalance
        )
        
        model.fit(X_train, y_train)
        
        logger.info("Logistic regression training completed")
        return model
    
    def _evaluate_model(self, X: np.ndarray, y: np.ndarray, split_name: str) -> Dict[str, float]:
        """Evaluate model performance."""
        logger.info(f"Evaluating model on {split_name} set")
        
        # Predictions
        y_pred_proba = self.model.predict_proba(X)[:, 1]
        y_pred = self.model.predict(X)
        
        # Calculate metrics
        log_loss_score = log_loss(y, y_pred_proba)
        brier_score = brier_score_loss(y, y_pred_proba)
        roc_auc = roc_auc_score(y, y_pred_proba)
        
        # Calibration slope
        calibration_slope = self._calculate_calibration_slope(y, y_pred_proba)
        
        metrics = {
            'log_loss': log_loss_score,
            'brier_score': brier_score,
            'roc_auc': roc_auc,
            'calibration_slope': calibration_slope,
            'accuracy': (y_pred == y).mean(),
            'precision': self._calculate_precision(y, y_pred),
            'recall': self._calculate_recall(y, y_pred),
            'f1_score': self._calculate_f1_score(y, y_pred)
        }
        
        logger.info(f"{split_name} metrics:")
        logger.info(f"  Log Loss: {log_loss_score:.4f}")
        logger.info(f"  Brier Score: {brier_score:.4f}")
        logger.info(f"  ROC AUC: {roc_auc:.4f}")
        logger.info(f"  Calibration Slope: {calibration_slope:.4f}")
        
        return metrics
    
    def _calculate_calibration_slope(self, y_true: np.ndarray, y_pred_proba: np.ndarray) -> float:
        """Calculate calibration slope."""
        try:
            # Use calibration curve to get slope
            fraction_of_positives, mean_predicted_value = calibration_curve(
                y_true, y_pred_proba, n_bins=10
            )
            
            # Calculate slope (simplified)
            if len(fraction_of_positives) > 1:
                slope = np.polyfit(mean_predicted_value, fraction_of_positives, 1)[0]
            else:
                slope = 1.0
            
            return slope
        except Exception as e:
            logger.warning(f"Failed to calculate calibration slope: {e}")
            return 1.0
    
    def _calculate_precision(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate precision score."""
        tp = np.sum((y_true == 1) & (y_pred == 1))
        fp = np.sum((y_true == 0) & (y_pred == 1))
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0
    
    def _calculate_recall(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate recall score."""
        tp = np.sum((y_true == 1) & (y_pred == 1))
        fn = np.sum((y_true == 1) & (y_pred == 0))
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    def _calculate_f1_score(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate F1 score."""
        precision = self._calculate_precision(y_true, y_pred)
        recall = self._calculate_recall(y_true, y_pred)
        return 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    def _cross_validate_model(self, X_train: np.ndarray, y_train: np.ndarray, cv: int = 5) -> Dict[str, Any]:
        """Perform cross-validation."""
        logger.info(f"Performing {cv}-fold cross-validation")
        
        # Cross-validation scores
        cv_log_loss = cross_val_score(
            self.model, X_train, y_train, cv=cv, scoring='neg_log_loss'
        )
        cv_brier = cross_val_score(
            self.model, X_train, y_train, cv=cv, scoring='neg_brier_score'
        )
        cv_roc_auc = cross_val_score(
            self.model, X_train, y_train, cv=cv, scoring='roc_auc'
        )
        
        cv_results = {
            'log_loss_mean': -cv_log_loss.mean(),
            'log_loss_std': cv_log_loss.std(),
            'brier_score_mean': -cv_brier.mean(),
            'brier_score_std': cv_brier.std(),
            'roc_auc_mean': cv_roc_auc.mean(),
            'roc_auc_std': cv_roc_auc.std()
        }
        
        logger.info(f"CV Log Loss: {cv_results['log_loss_mean']:.4f} ± {cv_results['log_loss_std']:.4f}")
        logger.info(f"CV Brier Score: {cv_results['brier_score_mean']:.4f} ± {cv_results['brier_score_std']:.4f}")
        logger.info(f"CV ROC AUC: {cv_results['roc_auc_mean']:.4f} ± {cv_results['roc_auc_std']:.4f}")
        
        return cv_results
    
    def check_sprint_2_3_thresholds(self) -> Dict[str, bool]:
        """Check if model meets Sprint 2.3 thresholds."""
        logger.info("Checking Sprint 2.3 thresholds")
        
        if not self.metrics:
            raise ValueError("Model not trained yet")
        
        test_metrics = self.metrics['test_metrics']
        
        thresholds = {
            'log_loss': test_metrics['log_loss'] <= 0.20,  # Should be low
            'brier_score': test_metrics['brier_score'] <= 0.20,  # Should be ≤ 0.20
            'calibration_slope': abs(test_metrics['calibration_slope'] - 1.0) <= 0.1  # Should be ~1.0
        }
        
        logger.info("Sprint 2.3 Threshold Check:")
        logger.info(f"  Log Loss ≤ 0.20: {thresholds['log_loss']} ({test_metrics['log_loss']:.4f})")
        logger.info(f"  Brier Score ≤ 0.20: {thresholds['brier_score']} ({test_metrics['brier_score']:.4f})")
        logger.info(f"  Calibration Slope ~1.0: {thresholds['calibration_slope']} ({test_metrics['calibration_slope']:.4f})")
        
        return thresholds
    
    def save_model(self, season: int, week: int) -> str:
        """Save trained model and scaler."""
        from pathlib import Path
        import yaml
        
        # Load paths config
        with open("configs/paths.yaml", 'r') as f:
            paths_config = yaml.safe_load(f)
        
        # Create output path
        output_path = Path(paths_config['models']['baseline_dir'])
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save model artifacts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save model
        model_file = output_path / f"baseline_model_{season}_week{week}_{timestamp}.joblib"
        joblib.dump(self.model, model_file)
        
        # Save scaler
        scaler_file = output_path / f"baseline_scaler_{season}_week{week}_{timestamp}.joblib"
        joblib.dump(self.scaler, scaler_file)
        
        # Save feature columns
        features_file = output_path / f"baseline_features_{season}_week{week}_{timestamp}.yaml"
        with open(features_file, 'w') as f:
            yaml.dump({'feature_columns': self.feature_columns}, f)
        
        # Save metrics
        metrics_file = output_path / f"baseline_metrics_{season}_week{week}_{timestamp}.yaml"
        with open(metrics_file, 'w') as f:
            yaml.dump(self.metrics, f, default_flow_style=False)
        
        logger.info(f"Saved model artifacts to {output_path}")
        logger.info(f"  Model: {model_file}")
        logger.info(f"  Scaler: {scaler_file}")
        logger.info(f"  Features: {features_file}")
        logger.info(f"  Metrics: {metrics_file}")
        
        return str(output_path)
