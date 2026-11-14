"""
Demonstration script for QC-C1-01:
Profiles and decomposes a sample circuit into basis set {'h', 'cx'}.
Saves report to results/c1_01_sample_report.json.
"""
import json
import os
import sys

# Ensure src is accessible (safe for scripts and Jupyter notebooks)
_file = globals().get("__file__")
_base_dir = os.path.dirname(os.path.abspath(_file)) if _file else os.getcwd()
_candidates = [
    os.path.abspath(os.path.join(_base_dir, "..", "src")),
    os.path.abspath(os.path.join(_base_dir, "src")),
    _base_dir,
]
for _p in _candidates:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from c1_01_final import analyze


def run_demo():
    sample_qasm = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[1];
h q[0];
swap q[0], q[1];
measure q[0] -> c[0];
"""
    basis_set = {"h", "cx"}

    print("=" * 60)
    print("QC-C1-01: Quantum Circuit Profiling & Decomposition Demo")
    print("=" * 60)
    print(f"Target Basis Gate Set: {sorted(basis_set)}")
    print("\n[Input OpenQASM Circuit]:")
    print(sample_qasm)

    new_circuit, report = analyze(sample_qasm, basis_set)

    print("-" * 60)
    print(f"Decomposition Status: {report['status']}")
    print("-" * 60)
    print("Before Decomposition Metrics:")
    for k, v in report["before"].items():
        print(f"  {k:22s}: {v}")

    print("\nAfter Decomposition Metrics:")
    for k, v in report["after"].items():
        print(f"  {k:22s}: {v}")

    # Save to results/c1_01_sample_report.json
    results_dir = os.path.abspath(os.path.join(_base_dir, "..", "results"))
    os.makedirs(results_dir, exist_ok=True)
    report_path = os.path.join(results_dir, "c1_01_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[Saved]: Report saved successfully to {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
