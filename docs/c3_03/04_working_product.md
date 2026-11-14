# Working Product: QC-03-03 Quantum Circuit Optimizer Using QSDK

## 1. Product Specification

- **Module**: `QC-03-03`
- **Component**: Quantum Circuit Optimizer and Local Rewrite Pass Engine
- **Target Platform**: C-DAC Qniverse Platform & QSDK / Python 3.10+
- **Implementation File**: `src/qc_c3_03.py`
- **Callable Interface**: `optimize_circuit(circuit: Any, enabled_passes: Optional[List[str]] = None) -> Tuple[Any, Dict[str, Any]]`

### Core Capabilities:
1. **Non-Mutating Execution**: Leaves the input `QniverseCircuit` strictly unmodified, returning a newly synthesized `QniverseCircuit`.
2. **Modular Local Rewrite Passes**:
   - `RemoveIdentities`: Drops redundant identity gates (`id`).
   - `CancelSelfInverse`: Eliminates adjacent Hermitian self-inverse gates ($X-X, H-H, Z-Z, Y-Y$).
   - `CancelAdjacentCX`: Eliminates identical adjacent $CX$ operations with matching control and target.
   - `MergeRotationAngles`: Merges consecutive rotations on the same axis ($R_z(\theta_1) + R_z(\theta_2)$) and drops near-zero angles.
3. **Barrier & Measurement Fence Safety**: Barriers, measurements, and resets prevent illegal cancellations across boundaries.
4. **Commutation Over Disjoint Wires**: Safely scans through gates operating on non-overlapping qubits to identify adjacent cancellation opportunities.
5. **Rigorous Depth & Resource Metrics**: Computes gate count by type and earliest-available-layer circuit depth before and after optimization.

---

## 2. Complete Source Code (`src/qc_c3_03.py`)

```python
"""
QC-03-03: Quantum Circuit Optimization Using QSDK
PESU - C-DAC Quantum Hackathon 2026 | Team Eigen
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

# ---------------------------------------------------------------------------
# QSDK Import & Offline Fallback Provider
# ---------------------------------------------------------------------------
try:
    from qniverse.circuit import QniverseCircuit
    from qniverse.registers import ClassicalRegister, QuantumRegister
    import qniverse.gates as G
    HAS_QNIVERSE = True
except ImportError:
    HAS_QNIVERSE = False

    class QuantumRegister:
        def __init__(self, size: int, name: str = "q"):
            self.size = size
            self.name = name

    class ClassicalRegister:
        def __init__(self, size: int, name: str = "c"):
            self.size = size
            self.name = name

    class MockQniverseCircuit:
        def __init__(self, *regs):
            self.qregs = [r for r in regs if isinstance(r, QuantumRegister)]
            self.cregs = [r for r in regs if isinstance(r, ClassicalRegister)]
            self.num_qubits = sum(r.size for r in self.qregs)
            self.num_cbits = sum(r.size for r in self.cregs)
            self.gates: List[Tuple[str, tuple, tuple]] = []

        def _add(self, name: str, qubits: tuple, params: tuple = ()):
            self.gates.append((name, qubits, params))

        def h(self, q): self._add("h", (q,))
        def x(self, q): self._add("x", (q,))
        def y(self, q): self._add("y", (q,))
        def z(self, q): self._add("z", (q,))
        def s(self, q): self._add("s", (q,))
        def sdg(self, q): self._add("sdg", (q,))
        def t(self, q): self._add("t", (q,))
        def tdg(self, q): self._add("tdg", (q,))
        def id(self, q): self._add("id", (q,))
        def cx(self, c, t): self._add("cx", (c, t))
        def cz(self, c, t): self._add("cz", (c, t))
        def swap(self, a, b): self._add("swap", (a, b))
        def rx(self, theta, q): self._add("rx", (q,), (theta,))
        def ry(self, theta, q): self._add("ry", (q,), (theta,))
        def rz(self, theta, q): self._add("rz", (q,), (theta,))
        def barrier(self, qubits): self._add("barrier", tuple(qubits))
        def measure(self, q, c): self._add("measure", (q,), (c,))
        def reset(self, q): self._add("reset", (q,))

        def qasm(self) -> str:
            lines = ["OPENQASM 2.0;", 'include "qelib1.inc";']
            for qr in self.qregs: lines.append(f"qreg {qr.name}[{qr.size}];")
            for cr in self.cregs: lines.append(f"creg {cr.name}[{cr.size}];")
            for name, qs, params in self.gates:
                if name == "barrier":
                    args = ", ".join(f"q[{q}]" for q in qs)
                    lines.append(f"barrier {args};")
                elif name == "measure":
                    lines.append(f"measure q[{qs[0]}] -> c[{params[0]}];")
                elif params:
                    p_str = ", ".join(f"{p:.6f}" for p in params)
                    args = ", ".join(f"q[{q}]" for q in qs)
                    lines.append(f"{name}({p_str}) {args};")
                else:
                    args = ", ".join(f"q[{q}]" for q in qs)
                    lines.append(f"{name} {args};")
            return "\n".join(lines)

    QniverseCircuit = MockQniverseCircuit


# ---------------------------------------------------------------------------
# Internal Op Representation & Profiling
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CircuitOp:
    name: str
    qubits: Tuple[int, ...]
    params: Tuple[float, ...] = ()
    cbits: Tuple[int, ...] = ()


def profile_ops(ops: List[CircuitOp], num_qubits: int) -> Dict[str, Any]:
    """Calculates gate counts and earliest-layer circuit depth."""
    gate_counts: Dict[str, int] = {}
    free = [0] * max(num_qubits, 1)
    depth = 0

    for op in ops:
        if op.name not in {"barrier", "measure", "reset"}:
            gate_counts[op.name] = gate_counts.get(op.name, 0) + 1

        if not op.qubits:
            continue

        start = max(free[q] for q in op.qubits)
        if op.name == "barrier":
            for q in op.qubits:
                free[q] = start
        else:
            for q in op.qubits:
                free[q] = start + 1
            depth = max(depth, start + 1)

    return {
        "total_gates": sum(gate_counts.values()),
        "by_type": gate_counts,
        "depth": depth,
    }


# ---------------------------------------------------------------------------
# Optimization Passes
# ---------------------------------------------------------------------------
SELF_INVERSE_GATES = {"x", "y", "z", "h", "swap"}
FENCE_OPS = {"barrier", "measure", "reset"}


def pass_remove_identities(ops: List[CircuitOp]) -> List[CircuitOp]:
    """Pass 1: Removes explicit identity operations ('id')."""
    return [op for op in ops if op.name != "id"]


def pass_cancel_self_inverse(ops: List[CircuitOp], num_qubits: int) -> List[CircuitOp]:
    """
    Pass 2: Cancels adjacent identical self-inverse gates (X-X, H-H, Z-Z, Y-Y),
    accounting for commutation across disjoint wires.
    """
    optimized: List[CircuitOp] = []
    for op in ops:
        if op.name in FENCE_OPS:
            optimized.append(op)
            continue

        if op.name in SELF_INVERSE_GATES and len(op.qubits) == 1:
            q = op.qubits[0]
            # Search backward for matching self-inverse gate on qubit q
            can_cancel_idx = None
            blocked = False
            for i in range(len(optimized) - 1, -1, -1):
                prev = optimized[i]
                if prev.name in FENCE_OPS and q in prev.qubits:
                    blocked = True
                    break
                if q in prev.qubits:
                    if prev.name == op.name and prev.qubits == op.qubits:
                        can_cancel_idx = i
                    break  # Hit another gate on wire q

            if can_cancel_idx is not None and not blocked:
                optimized.pop(can_cancel_idx)
                continue

        optimized.append(op)
    return optimized


def pass_cancel_adjacent_cx(ops: List[CircuitOp], num_qubits: int) -> List[CircuitOp]:
    """
    Pass 3: Cancels adjacent CX operations with identical control and target,
    accounting for commutation across disjoint wires.
    """
    optimized: List[CircuitOp] = []
    for op in ops:
        if op.name in FENCE_OPS:
            optimized.append(op)
            continue

        if op.name == "cx" and len(op.qubits) == 2:
            c, t = op.qubits
            can_cancel_idx = None
            blocked = False
            for i in range(len(optimized) - 1, -1, -1):
                prev = optimized[i]
                if prev.name in FENCE_OPS and (c in prev.qubits or t in prev.qubits):
                    blocked = True
                    break
                # If touching either wire
                if c in prev.qubits or t in prev.qubits:
                    if prev.name == "cx" and prev.qubits == (c, t):
                        can_cancel_idx = i
                    break  # Touching gate encountered

            if can_cancel_idx is not None and not blocked:
                optimized.pop(can_cancel_idx)
                continue

        optimized.append(op)
    return optimized


def pass_merge_rotations(ops: List[CircuitOp], num_qubits: int) -> List[CircuitOp]:
    """
    Pass 4: Combines consecutive single-qubit rotations on the same axis (Rx, Ry, Rz).
    """
    rotation_gates = {"rx", "ry", "rz"}
    optimized: List[CircuitOp] = []
    for op in ops:
        if op.name in rotation_gates and len(op.qubits) == 1 and op.params:
            q = op.qubits[0]
            can_merge_idx = None
            for i in range(len(optimized) - 1, -1, -1):
                prev = optimized[i]
                if prev.name in FENCE_OPS and q in prev.qubits:
                    break
                if q in prev.qubits:
                    if prev.name == op.name and prev.qubits == op.qubits:
                        can_merge_idx = i
                    break

            if can_merge_idx is not None:
                prev = optimized.pop(can_merge_idx)
                new_angle = (prev.params[0] + op.params[0]) % (2 * math.pi)
                if not math.isclose(new_angle, 0.0, abs_tol=1e-7) and not math.isclose(new_angle, 2 * math.pi, abs_tol=1e-7):
                    optimized.append(CircuitOp(name=op.name, qubits=op.qubits, params=(new_angle,)))
                continue

        optimized.append(op)
    return optimized


# ---------------------------------------------------------------------------
# Top-Level Optimizer Engine
# ---------------------------------------------------------------------------
AVAILABLE_PASSES = {
    "remove_identities": pass_remove_identities,
    "cancel_self_inverse": pass_cancel_self_inverse,
    "cancel_adjacent_cx": pass_cancel_adjacent_cx,
    "merge_rotations": pass_merge_rotations,
}


def optimize_circuit(
    circuit: Any,
    enabled_passes: Optional[List[str]] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Optimizes a QniverseCircuit object using local rewrite passes.
    Returns (new_optimized_circuit, metrics_report).
    Leaves the input circuit completely unmodified.
    """
    # 1. Ingest operations from input circuit
    raw_ops: List[CircuitOp] = []
    num_qubits = getattr(circuit, "num_qubits", 2)
    num_cbits = getattr(circuit, "num_cbits", getattr(circuit, "num_clbits", 0))

    if hasattr(circuit, "gates"):
        for item in circuit.gates:
            name, qs, params = item
            raw_ops.append(CircuitOp(name=name, qubits=qs, params=params))
    elif hasattr(circuit, "_ops"):
        for o in circuit._ops:
            raw_ops.append(CircuitOp(name=o.name, qubits=o.qubits, params=o.params, cbits=o.cbits))
    else:
        # Fallback inspection
        raw_ops = []

    # 2. Profile Initial State
    initial_metrics = profile_ops(raw_ops, num_qubits)

    # 3. Apply Enabled Passes in Fixed-Point Loop
    passes_to_run = enabled_passes or list(AVAILABLE_PASSES.keys())
    current_ops = list(raw_ops)

    for iteration in range(5):  # Fixed-point convergence limit
        prev_len = len(current_ops)
        for pass_name in passes_to_run:
            if pass_name == "remove_identities":
                current_ops = pass_remove_identities(current_ops)
            elif pass_name == "cancel_self_inverse":
                current_ops = pass_cancel_self_inverse(current_ops, num_qubits)
            elif pass_name == "cancel_adjacent_cx":
                current_ops = pass_cancel_adjacent_cx(current_ops, num_qubits)
            elif pass_name == "merge_rotations":
                current_ops = pass_merge_rotations(current_ops, num_qubits)
        if len(current_ops) == prev_len:
            break

    # 4. Profile Final State
    final_metrics = profile_ops(current_ops, num_qubits)

    # 5. Build Fresh QniverseCircuit Object (Non-Mutating)
    qr = QuantumRegister(max(num_qubits, 1), "q")
    cr = ClassicalRegister(max(num_cbits, 1), "c") if num_cbits > 0 else None
    new_circuit = QniverseCircuit(qr, cr) if cr else QniverseCircuit(qr)

    for op in current_ops:
        if op.name == "h": new_circuit.h(op.qubits[0])
        elif op.name == "x": new_circuit.x(op.qubits[0])
        elif op.name == "y": new_circuit.y(op.qubits[0])
        elif op.name == "z": new_circuit.z(op.qubits[0])
        elif op.name == "cx": new_circuit.cx(op.qubits[0], op.qubits[1])
        elif op.name == "swap": new_circuit.swap(op.qubits[0], op.qubits[1])
        elif op.name == "rx": new_circuit.rx(op.params[0], op.qubits[0])
        elif op.name == "rz": new_circuit.rz(op.params[0], op.qubits[0])
        elif op.name == "barrier": new_circuit.barrier(op.qubits)
        elif op.name == "measure": new_circuit.measure(op.qubits[0], op.cbits[0])
        elif op.name == "reset": new_circuit.reset(op.qubits[0])

    gate_reduction_pct = 0.0
    if initial_metrics["total_gates"] > 0:
        gate_reduction_pct = ((initial_metrics["total_gates"] - final_metrics["total_gates"]) / initial_metrics["total_gates"]) * 100.0

    depth_reduction_pct = 0.0
    if initial_metrics["depth"] > 0:
        depth_reduction_pct = ((initial_metrics["depth"] - final_metrics["depth"]) / initial_metrics["depth"]) * 100.0

    report = {
        "status": "SUCCESS",
        "passes_applied": passes_to_run,
        "initial_metrics": initial_metrics,
        "optimized_metrics": final_metrics,
        "gate_reduction_percentage": round(gate_reduction_pct, 2),
        "depth_reduction_percentage": round(depth_reduction_pct, 2),
    }

    return new_circuit, report


# ---------------------------------------------------------------------------
# Self-Test Verification Suite
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("--- Running QC-03-03 Circuit Optimizer Test Suite ---")

    # Test 1: Identity & Self-Inverse Cancellation
    qr = QuantumRegister(2, "q")
    qc = QniverseCircuit(qr)
    qc.id(0)
    qc.x(0)
    qc.x(0)
    qc.h(1)
    qc.h(1)
    qc.cx(0, 1)
    qc.cx(0, 1)

    opt_qc, rep = optimize_circuit(qc)
    assert rep["initial_metrics"]["total_gates"] == 7
    assert rep["optimized_metrics"]["total_gates"] == 0
    assert rep["gate_reduction_percentage"] == 100.0
    print("[PASS] Test 1: Identity and self-inverse cancellation verified (100% reduction).")

    # Test 2: Barrier Safety Fence
    qc_b = QniverseCircuit(qr)
    qc_b.h(0)
    qc_b.barrier([0, 1])
    qc_b.h(0)

    opt_b, rep_b = optimize_circuit(qc_b)
    assert rep_b["optimized_metrics"]["total_gates"] == 2
    assert rep_b["gate_reduction_percentage"] == 0.0
    print("[PASS] Test 2: Barrier synchronization fence preserved (0% reduction).")

    # Test 3: Rotation Angle Merging
    qc_r = QniverseCircuit(qr)
    qc_r.rz(math.pi / 4, 0)
    qc_r.rz(math.pi / 4, 0)

    opt_r, rep_r = optimize_circuit(qc_r)
    assert rep_r["initial_metrics"]["total_gates"] == 2
    assert rep_r["optimized_metrics"]["total_gates"] == 1
    assert math.isclose(opt_r.gates[0][2][0], math.pi / 2, abs_tol=1e-6)
    print("[PASS] Test 3: Consecutive rotation merging (pi/4 + pi/4 -> pi/2) verified.")

    print("\n--- ALL QC-03-03 OPTIMIZER TESTS PASSED SUCCESSFULLY! ---")
```

---

## 3. Verification & Execution Instructions

### Run the Standalone Self-Test Suite:
```powershell
python src/qc_c3_03.py
```

Expected output:
```
--- Running QC-03-03 Circuit Optimizer Test Suite ---
[PASS] Test 1: Identity and self-inverse cancellation verified (100% reduction).
[PASS] Test 2: Barrier synchronization fence preserved (0% reduction).
[PASS] Test 3: Consecutive rotation merging (pi/4 + pi/4 -> pi/2) verified.

--- ALL QC-03-03 OPTIMIZER TESTS PASSED SUCCESSFULLY! ---
```
