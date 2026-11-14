"""
QC-03-03: Quantum Circuit Optimization Using QSDK.
"""
import sys
import os

# Add parent directory (src/) to sys.path to allow sibling module imports
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from .optimizer import (
    optimize,
    OptimizationResult,
    verify_equivalence,
    SUPPORTED_PASSES,
)

__all__ = [
    "optimize",
    "OptimizationResult",
    "verify_equivalence",
    "SUPPORTED_PASSES",
]
