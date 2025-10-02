"""
Validation gate module for Sprint 2.5.

This module implements the validation gate system that determines if the model
meets the required thresholds for Sprint 2.5.

Purpose: Validation gate: meets thresholds → PASS.
Features:
- Threshold evaluation (log-loss ≤ 0.20, Brier ≤ 0.20, calibration slope ~1.0)
- Comprehensive validation reporting
- Pass/fail determination
- Integration with model training results
"""

import pandas as pd
import numpy as np
import logging
import yaml
import joblib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import json

from src.models.baseline import BaselineModelTrainer

logger = logging.getLogger(__name__)


class ValidationGate:
    """
    Validation gate for Sprint 2.5.
    
    Implements Sprint 2.5 requirements:
    - Threshold evaluation (log-loss ≤ 0.20, Brier ≤ 0.20, calibration slope ~1.0)
    - Comprehensive validation reporting
    - Pass/fail determination
    """
    
    def __init__(self, model_dir: str = "models/baseline"):
        """Initialize the validation gate."""
        self.model_dir = Path(model_dir)
        self.thresholds = {
            'log_loss': 0.20,
            'brier_score': 0.20,
            'calibration_slope_min': 0.8,
            'calibration_slope_max': 1.2
        }
        
        logger.info("Initialized ValidationGate")
    
    def load_latest_model_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Load the latest model metrics from saved artifacts.
        
        Returns:
            Dictionary with model metrics or None if not found
        """
        logger.info("Loading latest model metrics")
        
        try:
            # Find the latest metrics file
            metrics_files = list(self.model_dir.glob("baseline_metrics_*.yaml"))
            
            if not metrics_files:
                logger.error("No metrics files found")
                return None
            
            # Get the latest file
            latest_metrics = max(metrics_files, key=lambda x: x.stem.split('_')[-1])
            
            # Load metrics
            with open(latest_metrics, 'r') as f:
                metrics = yaml.safe_load(f)
            
            logger.info(f"Loaded metrics from: {latest_metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to load model metrics: {e}")
            return None
    
    def evaluate_thresholds(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate model performance against Sprint 2.5 thresholds.
        
        Args:
            metrics: Model performance metrics
            
        Returns:
            Dictionary with threshold evaluation results
        """
        logger.info("Evaluating Sprint 2.5 thresholds")
        
        if not metrics:
            return {
                'status': 'FAIL',
                'reason': 'No metrics available',
                'thresholds': {}
            }
        
        test_metrics = metrics.get('test_metrics', {})
        cv_scores = metrics.get('cv_scores', {})
        
        threshold_results = {}
        
        # Log Loss evaluation
        log_loss = test_metrics.get('log_loss', float('inf'))
        threshold_results['log_loss'] = {
            'value': log_loss,
            'threshold': self.thresholds['log_loss'],
            'passed': log_loss <= self.thresholds['log_loss'],
            'description': f"Log Loss ≤ {self.thresholds['log_loss']}"
        }
        
        # Brier Score evaluation
        brier_score = test_metrics.get('brier_score', float('inf'))
        threshold_results['brier_score'] = {
            'value': brier_score,
            'threshold': self.thresholds['brier_score'],
            'passed': brier_score <= self.thresholds['brier_score'],
            'description': f"Brier Score ≤ {self.thresholds['brier_score']}"
        }
        
        # Calibration Slope evaluation
        calibration_slope = test_metrics.get('calibration_slope', 0.0)
        threshold_results['calibration_slope'] = {
            'value': calibration_slope,
            'threshold_min': self.thresholds['calibration_slope_min'],
            'threshold_max': self.thresholds['calibration_slope_max'],
            'passed': (self.thresholds['calibration_slope_min'] <= calibration_slope <= self.thresholds['calibration_slope_max']),
            'description': f"Calibration Slope ~1.0 ({self.thresholds['calibration_slope_min']}-{self.thresholds['calibration_slope_max']})"
        }
        
        # Overall status determination
        all_passed = all(result['passed'] for result in threshold_results.values())
        
        result = {
            'status': 'PASS' if all_passed else 'FAIL',
            'thresholds': threshold_results,
            'summary': {
                'total_thresholds': len(threshold_results),
                'passed_thresholds': sum(1 for r in threshold_results.values() if r['passed']),
                'failed_thresholds': sum(1 for r in threshold_results.values() if not r['passed'])
            }
        }
        
        logger.info(f"Threshold evaluation completed: {result['status']}")
        logger.info(f"Passed: {result['summary']['passed_thresholds']}/{result['summary']['total_thresholds']}")
        
        return result
    
    def generate_validation_report(self, metrics: Dict[str, Any], threshold_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive validation report.
        
        Args:
            metrics: Model performance metrics
            threshold_results: Threshold evaluation results
            
        Returns:
            Comprehensive validation report
        """
        logger.info("Generating validation report")
        
        test_metrics = metrics.get('test_metrics', {})
        cv_scores = metrics.get('cv_scores', {})
        
        report = {
            'validation_timestamp': datetime.now().isoformat(),
            'sprint': '2.5',
            'validation_gate': 'Sprint 2.5 Threshold Evaluation',
            'overall_status': threshold_results['status'],
            'model_info': {
                'training_samples': metrics.get('training_data_size', 'Unknown'),
                'feature_count': metrics.get('feature_count', 'Unknown'),
                'positive_class_ratio': metrics.get('positive_class_ratio', 'Unknown')
            },
            'threshold_evaluation': threshold_results,
            'detailed_metrics': {
                'test_metrics': test_metrics,
                'cross_validation': cv_scores
            },
            'recommendations': self._generate_recommendations(threshold_results, test_metrics)
        }
        
        return report
    
    def _generate_recommendations(self, threshold_results: Dict[str, Any], test_metrics: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []
        
        if threshold_results['status'] == 'PASS':
            recommendations.append("✅ All Sprint 2.5 thresholds met - ready for Sprint 3")
            recommendations.append("✅ Model performance is satisfactory for production use")
            recommendations.append("✅ Proceed with advanced feature engineering (Sprint 3)")
        else:
            recommendations.append("❌ Some thresholds not met - review model performance")
            
            # Specific recommendations for failed thresholds
            for threshold_name, result in threshold_results['thresholds'].items():
                if not result['passed']:
                    if threshold_name == 'log_loss':
                        recommendations.append(f"❌ Log Loss too high ({result['value']:.4f} > {result['threshold']:.2f}) - consider feature engineering or model tuning")
                    elif threshold_name == 'brier_score':
                        recommendations.append(f"❌ Brier Score too high ({result['value']:.4f} > {result['threshold']:.2f}) - improve calibration")
                    elif threshold_name == 'calibration_slope':
                        recommendations.append(f"❌ Calibration Slope out of range ({result['value']:.4f}) - improve model calibration")
        
        return recommendations
    
    def run_validation_gate(self) -> Dict[str, Any]:
        """
        Run the complete validation gate process.
        
        Returns:
            Complete validation report
        """
        logger.info("Running Sprint 2.5 validation gate")
        
        # Load model metrics
        metrics = self.load_latest_model_metrics()
        if not metrics:
            return {
                'status': 'FAIL',
                'reason': 'No model metrics found',
                'validation_timestamp': datetime.now().isoformat()
            }
        
        # Evaluate thresholds
        threshold_results = self.evaluate_thresholds(metrics)
        
        # Generate comprehensive report
        validation_report = self.generate_validation_report(metrics, threshold_results)
        
        # Save validation report
        self.save_validation_report(validation_report)
        
        logger.info(f"Validation gate completed: {validation_report['overall_status']}")
        return validation_report
    
    def save_validation_report(self, report: Dict[str, Any]) -> str:
        """
        Save validation report to file.
        
        Args:
            report: Validation report to save
            
        Returns:
            Path to saved report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.model_dir / f"validation_report_sprint_2_5_{timestamp}.json"
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Validation report saved to: {report_file}")
        return str(report_file)
    
    def print_validation_summary(self, report: Dict[str, Any]) -> None:
        """Print a formatted validation summary."""
        print("\n" + "="*60)
        print("🏆 SPRINT 2.5 VALIDATION GATE RESULTS")
        print("="*60)
        
        print(f"📅 Validation Date: {report['validation_timestamp']}")
        print(f"🎯 Overall Status: {report['overall_status']}")
        print(f"📊 Sprint: {report['sprint']}")
        
        print(f"\n📈 Model Information:")
        model_info = report['model_info']
        print(f"  Training Samples: {model_info['training_samples']:,}")
        print(f"  Feature Count: {model_info['feature_count']}")
        print(f"  Positive Class Ratio: {model_info['positive_class_ratio']:.3f}")
        
        print(f"\n🎯 Threshold Evaluation:")
        threshold_eval = report['threshold_evaluation']
        summary = threshold_eval['summary']
        print(f"  Total Thresholds: {summary['total_thresholds']}")
        print(f"  Passed: {summary['passed_thresholds']}")
        print(f"  Failed: {summary['failed_thresholds']}")
        
        print(f"\n📊 Detailed Threshold Results:")
        for threshold_name, result in threshold_eval['thresholds'].items():
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"  {threshold_name.upper()}: {status}")
            print(f"    Value: {result['value']:.4f}")
            print(f"    Threshold: {result['description']}")
        
        print(f"\n💡 Recommendations:")
        for rec in report['recommendations']:
            print(f"  {rec}")
        
        print("\n" + "="*60)
        
        if report['overall_status'] == 'PASS':
            print("🎉 SPRINT 2.5 VALIDATION GATE: PASSED!")
            print("✅ Ready to proceed with Sprint 3: Matchup Context")
        else:
            print("⚠️ SPRINT 2.5 VALIDATION GATE: FAILED")
            print("❌ Review recommendations before proceeding")
        
        print("="*60)


def main():
    """Main validation gate function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sprint 2.5 Validation Gate")
    parser.add_argument('--model-dir', type=str, default='models/baseline', help='Model directory path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize validation gate
        validator = ValidationGate(args.model_dir)
        
        # Run validation
        report = validator.run_validation_gate()
        
        # Print summary
        validator.print_validation_summary(report)
        
        # Return appropriate exit code
        return 0 if report['overall_status'] == 'PASS' else 1
        
    except Exception as e:
        print(f"❌ Validation gate failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
