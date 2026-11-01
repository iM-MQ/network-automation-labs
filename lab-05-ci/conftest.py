"""Shared set-up for the network tests."""

import sys
from pathlib import Path

# Reuse the Lab 04 functions instead of copying them
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lab-04-python-automation"))