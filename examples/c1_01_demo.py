"""
Demonstration script for QC-C1-01:
Profiles and decomposes a sample circuit with basis gates {h, cx, t, tdg}.
Saves report to results/c1_01_sample_report.json.
"""
import json
import os
import sys

# Ensure src is accessible
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from c1_01_profiler import analyze


def run_demo():
    sample_qasm = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
creg c[2];
h q[0];
swap q[0], q[1];
cz q[1], q[2];
y q[0];
barrier q[0], q[1], q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
    basis_set = {"h", "cx", "t", "tdg", "s", "sdg"}

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
    results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results"))
    os.makedirs(results_dir, exist_ok=True)
    report_path = os.path.join(results_dir, "c1_01_sample_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[Saved]: Report saved successfully to {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
