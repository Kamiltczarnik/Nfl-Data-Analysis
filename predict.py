#!/usr/bin/env python3
"""
NFL Game Prediction CLI - Sprint 2.4

Command-line interface for making NFL game predictions using the trained baseline model.

Usage:
    python predict.py --home KC --away BUF --season 2024 --week 1
    python predict.py --season 2024 --week 1 --all-games
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.serve.predict import main

if __name__ == "__main__":
    exit(main())
