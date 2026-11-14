"""
QC-03-03 Demonstration Script
Demonstrates:
  A. Improvement Case: multiple removable operations where gate count & depth decrease.
  B. No-Improvement Case: circuit containing no supported optimization opportunity.
"""

import os
import sys
import json

_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from c1_01_final import Op
from optimizer import optimize


def run_demonstrations():
    print("=" * 70)
    print("QC-03-03: Quantum Circuit Optimization Using QSDK - DEMO")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # CASE A: Improvement Case
    # Circuit with redundant operations:
    # - Explicit identity gate: id(0)
    # - Self-inverse pairs: X(0)-X(0), H(1)-H(1)
    # - Redundant entangling pair: CX(0, 1)-CX(0, 1)
    # -------------------------------------------------------------------------
    print("\n" + "#" * 50)
    print("CASE A: Improvement Case (Redundant Gates)")
    print("#" * 50)

    circuit_a = [
        Op("id", (0,)),
        Op("h", (0,)),
        Op("x", (0,)),
        Op("x", (0,)),            # X-X cancels
        Op("cx", (0, 1)),
        Op("cx", (0, 1)),        # CX-CX cancels
        Op("h", (1,)),
        Op("h", (1,)),            # H-H cancels
        Op("z", (1,)),
        Op("measure", (0,), (0,)),
        Op("measure", (1,), (1,)),
    ]

    res_a = optimize(circuit_a)

    print("\nBefore Optimization:")
    for k, v in res_a.report["before"].items():
        print(f"  {k:22s}: {v}")

    print("\nAfter Optimization:")
    for k, v in res_a.report["after"].items():
        print(f"  {k:22s}: {v}")

    print("\nPasses Applied        :", res_a.report["passes_applied"])
    print("Gates Removed         :", res_a.report["gates_removed"])
    print("Reduction Percentage  :", f"{res_a.report['reduction_percentage']}%")
    print("Depth Reduction       :", f"{res_a.report['before']['depth']} -> {res_a.report['after']['depth']}")
    print("Equivalence Result    :", res_a.report["equivalence"])

    # -------------------------------------------------------------------------
    # CASE B: No-Improvement Case
    # Optimal circuit (e.g., Bell State preparation + single T gate):
    # - H(0)
    # - CX(0, 1)
    # - T(1)
    # Contains no identities, no adjacent self-inverse pairs, and no redundant CX.
    # -------------------------------------------------------------------------
    print("\n" + "#" * 50)
    print("CASE B: No-Improvement Case (Already Optimal)")
    print("#" * 50)

    circuit_b = [
        Op("h", (0,)),
        Op("cx", (0, 1)),
        Op("t", (1,)),
        Op("measure", (0,), (0,)),
        Op("measure", (1,), (1,)),
    ]

    res_b = optimize(circuit_b)

    print("\nBefore Optimization:")
    for k, v in res_b.report["before"].items():
        print(f"  {k:22s}: {v}")

    print("\nAfter Optimization:")
    for k, v in res_b.report["after"].items():
        print(f"  {k:22s}: {v}")

    print("\nPasses Applied        :", res_b.report["passes_applied"])
    print("Gates Removed         :", res_b.report["gates_removed"])
    print("Reduction Percentage  :", f"{res_b.report['reduction_percentage']}%")
    print("Depth Reduction       :", f"{res_b.report['before']['depth']} -> {res_b.report['after']['depth']}")
    print("Equivalence Result    :", res_b.report["equivalence"])
    print("\n" + "=" * 70)


if __name__ == "__main__":
    run_demonstrations()
