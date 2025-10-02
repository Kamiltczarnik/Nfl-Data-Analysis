#!/usr/bin/env python3
"""
Sprint 2.5 Validation Gate CLI

Command-line interface for running the Sprint 2.5 validation gate.

Usage:
    python validate.py
    python validate.py --verbose
    python validate.py --model-dir models/custom
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.eval.validation import main

if __name__ == "__main__":
    exit(main())
