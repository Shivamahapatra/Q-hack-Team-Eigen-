"""
QC-03-03: Quantum Circuit Optimization Using QSDK.

Provides safe, conservative, pass-based quantum circuit optimization
reusing verified Qniverse SDK adapters and profiling infrastructure.
"""

import os
import sys
import copy
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


def _reconstruct_circuit(
    ops: List[Op],
    num_qubits: int,
    num_clbits: int,
    q_layout: Optional[List[Tuple[str, int]]] = None,
    c_layout: Optional[List[Tuple[str, int]]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Reconstructs a new QniverseCircuit from the optimized Op list.
    Preserves:
    - Original register names and sizes (multi-register support)
    - Qubit and classical bit ordering
    - Measurement destinations and non-unitary ordering
    - Circuit metadata
    Falls back cleanly to an in-memory mock if the proprietary runtime is not installed.
    """
    # Normalize layouts
    if not q_layout:
        q_layout = [("q", num_qubits)] if num_qubits > 0 else []
    if not c_layout:
        c_layout = [("c", num_clbits)] if num_clbits > 0 else []

    # Attempt to build via live Qniverse SDK if available
    try:
        from qniverse.circuit import QniverseCircuit
        from qniverse.registers import QuantumRegister, ClassicalRegister
        import qniverse.gates as G

        new_qc = QniverseCircuit()
        q_map = {}
        curr_q = 0
        for name, size in q_layout:
            reg = QuantumRegister(size, name)
            new_qc.add_register(reg)
            for i in range(size):
                q_map[curr_q + i] = reg[i]
            curr_q += size

        c_map = {}
        curr_c = 0
        for name, size in c_layout:
            reg = ClassicalRegister(size, name)
            new_qc.add_register(reg)
            for i in range(size):
                c_map[curr_c + i] = reg[i]
            curr_c += size

        for o in ops:
            if o.name == "measure":
                new_qc.add_gate(G.measure, q_map[o.qubits[0]], c_map[o.cbits[0]])
            elif o.name == "barrier":
                gate_fn = getattr(G, "barrier", None)
                if gate_fn:
                    new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])
            elif o.name == "reset":
                gate_fn = getattr(G, "reset", None)
                if gate_fn:
                    new_qc.add_gate(gate_fn, q_map[o.qubits[0]])
            else:
                gate_fn = getattr(G, o.name, None)
                if gate_fn:
                    new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])

        if metadata:
            new_qc.metadata = copy.deepcopy(metadata)
        return new_qc

    except (ImportError, ModuleNotFoundError, NotImplementedError, AttributeError):
        # Offline representation conforming strictly to Qniverse runtime structure
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

        def _map_wire(idx: int, layout: List[Tuple[str, int]], kind: str) -> _MockWire:
            curr = 0
            for name, size in layout:
                if curr <= idx < curr + size:
                    return _MockWire(kind, name, size, idx - curr)
                curr += size
            # Default fallback wire
            reg_name = "q" if kind == "Qubit" else "c"
            return _MockWire(kind, reg_name, idx + 1, idx)

        class _MockQniverseCircuit:
            def __init__(
                self,
                n_q: int,
                n_c: int,
                op_list: List[Op],
                q_lay: List[Tuple[str, int]],
                c_lay: List[Tuple[str, int]],
                meta: Optional[Dict[str, Any]]
            ):
                self.num_qubits = n_q
                self.num_clbits = n_c
                self.registers = []
                for name, size in q_lay:
                    self.registers.append(_MockReg("Quantum", size, name))
                for name, size in c_lay:
                    self.registers.append(_MockReg("Classical", size, name))

                self.operations = []
                for o in op_list:
                    if o.name == "measure":
                        wires = (
                            _map_wire(o.qubits[0], q_lay, "Qubit"),
                            _map_wire(o.cbits[0], c_lay, "Clbit")
                        )
                    else:
                        wires = tuple(_map_wire(q, q_lay, "Qubit") for q in o.qubits)
                    self.operations.append((_MockGate(o.name), wires))

                self.metadata = copy.deepcopy(meta) if meta else None

            def qasm(self) -> str:
                lines = [
                    "OPENQASM 2.0;",
                    'include "qelib1.inc";'
                ]
                for reg in self.registers:
                    if reg.kind == "Quantum":
                        lines.append(f"qreg {reg.name}[{reg.size}];")
                    else:
                        lines.append(f"creg {reg.name}[{reg.size}];")
                for gate, wires in self.operations:
                    gname = gate.name.lower()
                    if gname == "measure":
                        lines.append(f"measure {wires[0].reg_name}[{wires[0].idx}] -> {wires[1].reg_name}[{wires[1].idx}];")
                    elif gname == "barrier":
                        args = ", ".join(f"{w.reg_name}[{w.idx}]" for w in wires)
                        lines.append(f"barrier {args};")
                    elif gname == "reset":
                        lines.append(f"reset {wires[0].reg_name}[{wires[0].idx}];")
                    else:
                        args = ", ".join(f"{w.reg_name}[{w.idx}]" for w in wires)
                        lines.append(f"{gname} {args};")
                return "\n".join(lines) + "\n"

        return _MockQniverseCircuit(num_qubits, num_clbits, ops, q_layout, c_layout, metadata)


def verify_equivalence(
    original_ops: List[Op],
    optimized_ops: List[Op],
    num_qubits: int
) -> Dict[str, Any]:
    """
    Validates semantic and structural equivalence between original and optimized circuits.

    Rules:
    A. Purely unitary circuits (+ barriers):
       - Mathematical equivalence verified up to global phase using unitary matrix calculation.
       - Barriers are treated as compilation boundaries and do not affect the unitary matrix.
    B. Circuits with terminal measurements:
       - Verified that measurements appear strictly at the end of the circuit.
       - The unitary prefix is mathematically verified up to global phase.
       - Measurement operations, target qubits, destination bits, and order are verified structurally.
       - Returns 'equivalent': True only if BOTH pass.
    C. Mid-circuit measurements or resets:
       - Semantic equivalence cannot be verified via simple unitary simulation.
       - Returns 'equivalent': None with explicit warning.
       - Structural preservation of non-unitary ops is verified and reported separately.
    """
    has_measure = any(o.name == "measure" for o in original_ops)
    has_reset = any(o.name == "reset" for o in original_ops)

    # ------------------------------------------------- CASE A: Purely Unitary (+ Barriers)
    if not has_measure and not has_reset:
        if num_qubits == 0:
            return {
                "type": "unitary",
                "equivalent": True,
                "mathematical_equivalence_verified": True,
                "structural_preservation_verified": True,
                "method": "trivial_empty_circuit",
                "details": "Empty circuit trivially equivalent."
            }

        # Compute unitary matrices (barriers are automatically ignored by unitary())
        u_orig = unitary(original_ops, num_qubits)
        u_opt = unitary(optimized_ops, num_qubits)
        is_equiv = equal_up_to_phase(u_orig, u_opt)

        # Check barrier preservation if barriers exist
        orig_barriers = [o for o in original_ops if o.name == "barrier"]
        opt_barriers = [o for o in optimized_ops if o.name == "barrier"]
        barriers_preserved = (orig_barriers == opt_barriers)

        return {
            "type": "unitary",
            "equivalent": bool(is_equiv and barriers_preserved),
            "mathematical_equivalence_verified": bool(is_equiv),
            "structural_preservation_verified": barriers_preserved,
            "method": "equal_up_to_phase (tolerance 1e-9)",
            "details": "Mathematical unitary equivalence proven up to global phase."
        }

    # ------------------------------------------------- Check for Terminal Measurements
    # Measurements are terminal if after the first measurement, only measurements or barriers follow.
    first_meas_orig = next((i for i, o in enumerate(original_ops) if o.name == "measure"), -1)
    orig_post_meas = original_ops[first_meas_orig:] if first_meas_orig != -1 else []
    orig_is_terminal = (
        first_meas_orig != -1
        and not has_reset
        and all(o.name in ("measure", "barrier") for o in orig_post_meas)
    )

    first_meas_opt = next((i for i, o in enumerate(optimized_ops) if o.name == "measure"), -1)
    opt_post_meas = optimized_ops[first_meas_opt:] if first_meas_opt != -1 else []
    opt_is_terminal = (
        first_meas_opt != -1
        and all(o.name in ("measure", "barrier") for o in opt_post_meas)
    )

    if orig_is_terminal and opt_is_terminal:
        # --------------------------------------------- CASE B: Terminal Measurements
        orig_prefix = original_ops[:first_meas_orig]
        opt_prefix = optimized_ops[:first_meas_opt]

        # Verify mathematical equivalence of unitary prefix
        if num_qubits > 0:
            u_orig = unitary(orig_prefix, num_qubits)
            u_opt = unitary(opt_prefix, num_qubits)
            prefix_equiv = bool(equal_up_to_phase(u_orig, u_opt))
        else:
            prefix_equiv = True

        # Verify exact structural preservation of terminal measurements
        orig_meas_list = [o for o in original_ops if o.name == "measure"]
        opt_meas_list = [o for o in optimized_ops if o.name == "measure"]
        meas_preserved = (orig_meas_list == opt_meas_list)

        both_passed = prefix_equiv and meas_preserved

        return {
            "type": "terminal_measurement_verified",
            "equivalent": both_passed,
            "mathematical_equivalence_verified": prefix_equiv,
            "structural_preservation_verified": meas_preserved,
            "method": "unitary_prefix_matrix_and_measurement_preservation",
            "details": (
                "Unitary prefix mathematically verified via equal_up_to_phase; "
                "terminal measurements verified structurally in-order."
                if both_passed
                else "Terminal measurement verification failed."
            )
        }

    # ------------------------------------------------- CASE C: Mid-Circuit Non-Unitary / Resets
    orig_non_unitaries = [o for o in original_ops if o.name in NON_UNITARY]
    opt_non_unitaries = [o for o in optimized_ops if o.name in NON_UNITARY]
    structural_match = (
        len(orig_non_unitaries) == len(opt_non_unitaries)
        and all(o1 == o2 for o1, o2 in zip(orig_non_unitaries, opt_non_unitaries))
    )

    return {
        "type": "mid_circuit_non_unitary_unverified",
        "equivalent": None,
        "mathematical_equivalence_verified": False,
        "structural_preservation_verified": structural_match,
        "method": "semantic_equivalence_not_verified",
        "details": (
            "Semantic equivalence cannot be verified via unitary simulation for circuits "
            "with mid-circuit measurements or resets. Structural preservation is checked separately."
        )
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
    q_layout: List[Tuple[str, int]] = []
    c_layout: List[Tuple[str, int]] = []
    circuit_metadata: Optional[Dict[str, Any]] = None

    # Ingestion: convert to internal Op representation and extract layout/metadata
    num_clbits = 0
    if hasattr(qc, "operations"):
        try:
            ops, num_qubits, num_clbits, extra = qa.from_qniverse(qc)
            if extra and "warnings" in extra:
                warnings.extend(extra["warnings"])
            # Extract detailed register layout
            q_sizes, c_sizes = qa._register_sizes(qc)
            q_layout = list(q_sizes.items())
            c_layout = list(c_sizes.items())
            if hasattr(qc, "metadata") and qc.metadata:
                circuit_metadata = copy.deepcopy(qc.metadata)
        except Exception as e:
            raise ValueError(f"Failed to extract operations from QniverseCircuit: {e}")
    elif isinstance(qc, str):
        # OpenQASM string fallback
        import c1_01_final as cf
        ops, num_qubits = cf.parse_qasm(qc)
        num_clbits = max((c for o in ops for c in o.cbits), default=-1) + 1
        q_layout = [("q", num_qubits)] if num_qubits > 0 else []
        c_layout = [("c", num_clbits)] if num_clbits > 0 else []
    elif isinstance(qc, list):
        ops = list(qc)
        num_qubits = max((q for o in ops for q in o.qubits), default=-1) + 1
        num_clbits = max((c for o in ops for c in o.cbits), default=-1) + 1
        q_layout = [("q", num_qubits)] if num_qubits > 0 else []
        c_layout = [("c", num_clbits)] if num_clbits > 0 else []
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

    if eq_check["equivalent"] is False:
        warnings.append("Equivalence check failed!")
        status = "FAILED_EQUIVALENCE"
    elif eq_check["equivalent"] is None:
        warnings.append(
            "Semantic equivalence not verified: circuit contains mid-circuit measurements or resets. "
            "Structural preservation verified."
        )
        status = "OK_SEMANTIC_UNVERIFIED"
    else:
        status = "OK"

    if any(o.name in NON_UNITARY for o in original_ops_snapshot):
        warnings.append("Circuit contains non-unitary operations (measure/barrier/reset) preserved structurally.")

    report = {
        "status": status,
        "passes_enabled": selected_passes,
        "passes_applied": passes_applied,
        "before": metrics_before,
        "after": metrics_after,
        "gates_removed": gates_removed,
        "reduction_percentage": reduction_pct,
        "equivalence": eq_check,
        "warnings": warnings,
    }

    # Reconstruct fresh circuit object preserving layout and metadata
    new_circuit = _reconstruct_circuit(
        optimized_ops,
        num_qubits,
        num_clbits,
        q_layout=q_layout,
        c_layout=c_layout,
        metadata=circuit_metadata
    )

    return OptimizationResult(circuit=new_circuit, report=report)
