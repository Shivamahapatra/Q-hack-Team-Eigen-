"""
QC-03-03: Quantum Circuit Optimization Using QSDK.
"""
import sys
import os

# Add parent directory (src/) to sys.path to allow sibling module imports
_file = globals().get("__file__")
_base_dir = os.path.dirname(os.path.abspath(_file)) if _file else os.getcwd()
_candidates = [
    os.path.abspath(os.path.join(_base_dir, "..")),
    os.path.abspath(os.path.join(_base_dir, "src")),
    _base_dir,
]
for _p in _candidates:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from .optimizer import (
    optimize,
    OptimizationResult,
    verify_equivalence,
    SUPPORTED_PASSES,
    DEFAULT_PASSES,
    PASS_IDENTITY_REMOVAL,
    PASS_SELF_INVERSE_CANCELLATION,
    PASS_CX_CANCELLATION,
    PASS_X_CANCELLATION,
    PASS_Y_CANCELLATION,
    PASS_Z_CANCELLATION,
    PASS_H_CANCELLATION,
    PASS_CY_CANCELLATION,
    PASS_CZ_CANCELLATION,
    PASS_CH_CANCELLATION,
    PASS_SWAP_CANCELLATION,
    PASS_CCX_CANCELLATION,
    PASS_CSWAP_CANCELLATION,
    PASS_S_SDG_CANCELLATION,
    PASS_T_TDG_CANCELLATION,
)

__all__ = [
    "optimize",
    "OptimizationResult",
    "verify_equivalence",
    "SUPPORTED_PASSES",
    "DEFAULT_PASSES",
    "PASS_IDENTITY_REMOVAL",
    "PASS_SELF_INVERSE_CANCELLATION",
    "PASS_CX_CANCELLATION",
    "PASS_X_CANCELLATION",
    "PASS_Y_CANCELLATION",
    "PASS_Z_CANCELLATION",
    "PASS_H_CANCELLATION",
    "PASS_CY_CANCELLATION",
    "PASS_CZ_CANCELLATION",
    "PASS_CH_CANCELLATION",
    "PASS_SWAP_CANCELLATION",
    "PASS_CCX_CANCELLATION",
    "PASS_CSWAP_CANCELLATION",
    "PASS_S_SDG_CANCELLATION",
    "PASS_T_TDG_CANCELLATION",
]
