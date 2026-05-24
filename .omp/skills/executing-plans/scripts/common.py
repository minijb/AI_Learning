"""Thin wrapper — all implementation lives in .omp/lib/_planning_common.py"""
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[3] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from _planning_common import *  # noqa: E402, F403
