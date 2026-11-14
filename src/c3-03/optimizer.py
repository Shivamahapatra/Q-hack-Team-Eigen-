"""
QC-03-03: Quantum Circuit Optimization Using QSDK.

Provides safe, conservative, pass-based quantum circuit optimization
reusing verified Qniverse SDK adapters and profiling infrastructure.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Dict, Set

# Ensure parent directory is accessible for sibling imports
_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from c1_01_final import Op, profile, unitary, equal_up_to_phase, NON_UNITARY
import qniverse_adapter as qa

# Supported optimization passes
PASS_IDENTITY_REMOVAL = "identity_removal"
PASS_SELF_INVERSE_CANCELLATION = "self_inverse_cancellation"
PASS_CX_CANCELLATION = "cx_cancellation"

SUPPORTED_PASSES = [
    PASS_IDENTITY_REMOVAL,
    PASS_SELF_INVERSE_CANCELLATION,
    PASS_CX_CANCELLATION,
]

SELF_INVERSE_GATES = {"x", "h", "z"}


@dataclass
class OptimizationResult:
    """Encapsulates the optimization outcome and diagnostics report."""
    circuit: Any
    report: Dict[str, Any]


def _pass_identity_removal(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 1: IDENTITY REMOVAL
    Removes explicit identity gates ('id') from the circuit.
    Does not touch non-unitary operations or gates with other names.
    """
    new_ops = []
    removed = 0
    for op in ops:
        if op.name == "id":
            removed += 1
        else:
            new_ops.append(op)
    return new_ops, removed


def _pass_self_inverse_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 2: SELF-INVERSE GATE CANCELLATION
    Cancels identical adjacent gates operating on the exact same qubit:
    - X-X
    - H-H
    - Z-Z
    Uses conservative adjacency: only cancels when strictly consecutive in the sequence.
    """
    new_ops = []
    removed = 0
    i = 0
    n = len(ops)
    while i < n:
        if (
            i + 1 < n
            and ops[i].name in SELF_INVERSE_GATES
            and ops[i].name == ops[i + 1].name
            and ops[i].qubits == ops[i + 1].qubits
        ):
            # Consecutive identical self-inverse pair found
            removed += 2
            i += 2
        else:
            new_ops.append(ops[i])
            i += 1
    return new_ops, removed


def _pass_cx_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 3: CX CANCELLATION
    Cancels consecutive CX operations only when:
    - Both are CX gates.
    - Control qubits match.
    - Target qubits match.
    - Control and target ordering is identical (e.g. (c, t) == (c, t)).
    - No intervening operation between them.
    """
    new_ops = []
    removed = 0
    i = 0
    n = len(ops)
    while i < n:
        if (
            i + 1 < n
            and ops[i].name == "cx"
            and ops[i + 1].name == "cx"
            and ops[i].qubits == ops[i + 1].qubits
        ):
            # Consecutive identical CX pair with matching control and target
            removed += 2
            i += 2
        else:
            new_ops.append(ops[i])
            i += 1
    return new_ops, removed


def _run_optimization_pipeline(ops: List[Op], passes: List[str]) -> Tuple[List[Op], List[str]]:
    """
    Applies the enabled passes iteratively until convergence (fixed point).
    Maintains strict conservative adjacency without reordering operations.
    """
    current_ops = list(ops)
    passes_applied: Set[str] = set()

    changed = True
    iteration = 0
    max_iterations = max(len(ops) * 2, 100)

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1

        if PASS_IDENTITY_REMOVAL in passes:
            current_ops, count = _pass_identity_removal(current_ops)
            if count > 0:
                passes_applied.add(PASS_IDENTITY_REMOVAL)
                changed = True

        if PASS_SELF_INVERSE_CANCELLATION in passes:
            current_ops, count = _pass_self_inverse_cancellation(current_ops)
            if count > 0:
                passes_applied.add(PASS_SELF_INVERSE_CANCELLATION)
                changed = True

        if PASS_CX_CANCELLATION in passes:
            current_ops, count = _pass_cx_cancellation(current_ops)
            if count > 0:
                passes_applied.add(PASS_CX_CANCELLATION)
                changed = True

    return current_ops, sorted(passes_applied)


def _reconstruct_circuit(ops: List[Op], num_qubits: int, num_clbits: int) -> Any:
    """
    Reconstructs a new QniverseCircuit from the optimized Op list.
    Preserves qubit indices, classical registers, and non-unitary ordering.
    Falls back cleanly to an in-memory mock if the proprietary runtime is not installed.
    """
    try:
        return qa.to_qniverse(ops, num_qubits, num_clbits)
    except (ImportError, ModuleNotFoundError, NotImplementedError):
        # Create an offline representation conforming to Qniverse runtime structure
        class _MockReg:
            def __init__(self, kind: str, size: int, name: str):
                self.kind = kind
                self.size = size
                self.name = name

            def __repr__(self):
                return f"{self.kind}Register({self.size}, '{self.name}')"

        class _MockWire:
            def __init__(self, kind: str, reg_name: str, size: int, idx: int):
                self.kind = kind
                self.reg_name = reg_name
                self.size = size
                self.idx = idx

            def __repr__(self):
                reg_cls = "QuantumRegister" if self.kind == "Qubit" else "ClassicalRegister"
                return f"{self.kind}({reg_cls}({self.size}, '{self.reg_name}'), {self.idx})"

        class _MockGate:
            def __init__(self, name: str):
                if name.lower() == "measure":
                    self.name = "Measure"
                elif name.lower() == "barrier":
                    self.name = "Barrier"
                elif name.lower() == "reset":
                    self.name = "Reset"
                else:
                    self.name = name.upper()

        class _MockQniverseCircuit:
            def __init__(self, n_q: int, n_c: int, op_list: List[Op]):
                self.num_qubits = n_q
                self.num_clbits = n_c
                self.registers = [_MockReg("Quantum", n_q, "q")]
                if n_c > 0:
                    self.registers.append(_MockReg("Classical", n_c, "c"))
                self.operations = []
                for o in op_list:
                    if o.name == "measure":
                        wires = (
                            _MockWire("Qubit", "q", n_q, o.qubits[0]),
                            _MockWire("Clbit", "c", n_c, o.cbits[0])
                        )
                    else:
                        wires = tuple(_MockWire("Qubit", "q", n_q, q) for q in o.qubits)
                    self.operations.append((_MockGate(o.name), wires))

            def qasm(self) -> str:
                lines = [
                    "OPENQASM 2.0;",
                    'include "qelib1.inc";',
                    f"qreg q[{self.num_qubits}];"
                ]
                if self.num_clbits > 0:
                    lines.append(f"creg c[{self.num_clbits}];")
                for gate, wires in self.operations:
                    gname = gate.name.lower()
                    if gname == "measure":
                        lines.append(f"measure q[{wires[0].idx}] -> c[{wires[1].idx}];")
                    elif gname == "barrier":
                        args = ", ".join(f"q[{w.idx}]" for w in wires)
                        lines.append(f"barrier {args};")
                    elif gname == "reset":
                        lines.append(f"reset q[{wires[0].idx}];")
                    else:
                        args = ", ".join(f"q[{w.idx}]" for w in wires)
                        lines.append(f"{gname} {args};")
                return "\n".join(lines) + "\n"

        return _MockQniverseCircuit(num_qubits, num_clbits, ops)


def verify_equivalence(
    original_ops: List[Op],
    optimized_ops: List[Op],
    num_qubits: int
) -> Dict[str, Any]:
    """
    Validates semantic and structural equivalence between original and optimized circuits.
    - Purely unitary circuits: verified via NumPy matrix multiplication up to global phase.
    - Non-unitary circuits: verified via structural invariance (measurements, barriers, resets).
    """
    has_non_unitary = any(o.name in NON_UNITARY for o in original_ops)
    
    if not has_non_unitary:
        if num_qubits == 0:
            return {
                "type": "unitary",
                "equivalent": True,
                "method": "trivial_empty_circuit"
            }
        u_orig = unitary(original_ops, num_qubits)
        u_opt = unitary(optimized_ops, num_qubits)
        is_equiv = equal_up_to_phase(u_orig, u_opt)
        return {
            "type": "unitary",
            "equivalent": bool(is_equiv),
            "method": "equal_up_to_phase (tolerance 1e-9)"
        }

    # Non-unitary circuit verification
    orig_non_unitaries = [o for o in original_ops if o.name in NON_UNITARY]
    opt_non_unitaries = [o for o in optimized_ops if o.name in NON_UNITARY]

    structural_match = (
        len(orig_non_unitaries) == len(opt_non_unitaries)
        and all(o1 == o2 for o1, o2 in zip(orig_non_unitaries, opt_non_unitaries))
    )

    return {
        "type": "non_unitary_structural",
        "equivalent": structural_match,
        "method": "structural_invariance (measurements, barriers, resets preserved in-order)"
    }


def optimize(
    qc: Any,
    enabled_passes: Optional[List[str]] = None
) -> OptimizationResult:
    """
    Optimizes a quantum circuit using QSDK APIs and verified conservative passes.

    Parameters:
        qc: Input QniverseCircuit instance (or QASM string / Op list).
        enabled_passes: Optional list of pass names to apply. Defaults to all supported passes.

    Returns:
        OptimizationResult with .circuit (new object) and .report (metrics and diagnostics).
    """
    if qc is None:
        raise ValueError("Cannot optimize: input circuit is None")

    # Validate passes configuration
    if enabled_passes is None:
        selected_passes = list(SUPPORTED_PASSES)
    else:
        for p in enabled_passes:
            if p not in SUPPORTED_PASSES:
                raise ValueError(
                    f"Unknown optimization pass: '{p}'. Supported passes: {SUPPORTED_PASSES}"
                )
        selected_passes = list(enabled_passes)

    warnings: List[str] = []

    # Ingestion: convert to internal Op representation
    num_clbits = 0
    if hasattr(qc, "operations"):
        try:
            ops, num_qubits, num_clbits, extra = qa.from_qniverse(qc)
            if extra and "warnings" in extra:
                warnings.extend(extra["warnings"])
        except Exception as e:
            raise ValueError(f"Failed to extract operations from QniverseCircuit: {e}")
    elif isinstance(qc, str):
        # OpenQASM string fallback
        import c1_01_final as cf
        ops, num_qubits = cf.parse_qasm(qc)
        num_clbits = max((c for o in ops for c in o.cbits), default=-1) + 1
    elif isinstance(qc, list):
        ops = list(qc)
        num_qubits = max((q for o in ops for q in o.qubits), default=-1) + 1
        num_clbits = max((c for o in ops for c in o.cbits), default=-1) + 1
    else:
        raise TypeError(f"Unsupported circuit type for optimization: {type(qc)}")

    # Strict immutability snapshot
    original_ops_snapshot = list(ops)

    # Initial metrics
    metrics_before = profile(ops, num_qubits)

    # Execute optimization pipeline
    optimized_ops, passes_applied = _run_optimization_pipeline(ops, selected_passes)

    # Verify input immutability
    assert ops == original_ops_snapshot, "CRITICAL ERROR: Original circuit operations were mutated!"

    # Final metrics
    metrics_after = profile(optimized_ops, num_qubits)

    gates_removed = metrics_before["total_gates"] - metrics_after["total_gates"]
    reduction_pct = (
        round((gates_removed / metrics_before["total_gates"]) * 100.0, 2)
        if metrics_before["total_gates"] > 0
        else 0.0
    )

    # Equivalence check
    eq_check = verify_equivalence(original_ops_snapshot, optimized_ops, num_qubits)
    if not eq_check["equivalent"]:
        warnings.append("Equivalence check failed or could not be established!")

    # Check for non-unitary / parameterised presence
    if any(o.name in NON_UNITARY for o in original_ops_snapshot):
        warnings.append("Circuit contains non-unitary operations (measure/barrier/reset) preserved structurally.")

    report = {
        "status": "OK" if eq_check["equivalent"] else "WARNING_EQUIVALENCE",
        "passes_enabled": selected_passes,
        "passes_applied": passes_applied,
        "before": metrics_before,
        "after": metrics_after,
        "gates_removed": gates_removed,
        "reduction_percentage": reduction_pct,
        "equivalence": eq_check,
        "warnings": warnings,
    }

    # Reconstruct fresh circuit object
    new_circuit = _reconstruct_circuit(optimized_ops, num_qubits, num_clbits)

    return OptimizationResult(circuit=new_circuit, report=report)
