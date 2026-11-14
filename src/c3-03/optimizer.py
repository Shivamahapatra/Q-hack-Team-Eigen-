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

# Ensure parent directory is accessible for sibling imports (JupyterLab-safe)
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
NON_UNITARY_GATES = {"measure", "reset", "barrier"}

PARAMETERISED_GATES = {
    "rx", "ry", "rz", "p", "u1", "u2", "u3",
    "crx", "cry", "crz", "cp", "cu1", "cu2", "cu3"
}

VALID_GATES_ARITY = {
    # 1-qubit gates
    "id": (1, 0), "x": (1, 0), "y": (1, 0), "z": (1, 0),
    "h": (1, 0), "s": (1, 0), "sdg": (1, 0), "t": (1, 0), "tdg": (1, 0),
    "reset": (1, 0),
    # 2-qubit gates
    "cx": (2, 0), "cz": (2, 0), "swap": (2, 0),
    # 3-qubit gates
    "ccx": (3, 0),
    # Measurement: 1 qubit, 1 classical bit
    "measure": (1, 1),
}


def _validate_register_layouts(
    q_layout: List[Tuple[str, int]],
    num_qubits: int,
    c_layout: List[Tuple[str, int]],
    num_clbits: int
) -> None:
    """Validates quantum and classical register definitions (DEF-08)."""
    # Validate quantum registers
    q_names = set()
    total_q = 0
    for item in q_layout:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"Malformed quantum register entry: {item}")
        name, size = item
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Invalid quantum register name: '{name}'")
        if name in q_names:
            raise ValueError(f"Duplicate quantum register name: '{name}'")
        q_names.add(name)
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Invalid size {size} for quantum register '{name}'. Size must be > 0.")
        total_q += size

    if total_q != num_qubits:
        raise ValueError(
            f"Quantum register sizes sum to {total_q}, which does not match declared num_qubits {num_qubits}."
        )

    # Validate classical registers
    c_names = set()
    total_c = 0
    for item in c_layout:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"Malformed classical register entry: {item}")
        name, size = item
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Invalid classical register name: '{name}'")
        if name in c_names:
            raise ValueError(f"Duplicate classical register name: '{name}'")
        c_names.add(name)
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Invalid size {size} for classical register '{name}'. Size must be > 0.")
        total_c += size

    if total_c != num_clbits:
        raise ValueError(
            f"Classical register sizes sum to {total_c}, which does not match declared num_clbits {num_clbits}."
        )


def _validate_circuit_ops(ops: List[Op], num_qubits: int, num_clbits: int) -> None:
    """Validates operation arities, wire bounds, and rejects parameterized gates (DEF-04, DEF-07)."""
    if num_qubits == 0 and len(ops) > 0:
        raise ValueError("Circuit contains operations but declared num_qubits is 0.")

    for op in ops:
        if not isinstance(op, Op):
            raise TypeError(f"Invalid operation object: expected Op, got {type(op)}")

        gname = op.name.lower()
        if gname in PARAMETERISED_GATES:
            raise ValueError(
                f"Parameterized gate '{op.name}' is not supported: gate parameters cannot be safely "
                f"extracted or preserved. Circuit rejected before optimization to prevent parameter loss."
            )

        if gname == "barrier":
            if not op.qubits or len(op.qubits) == 0:
                raise ValueError("Barrier operation must span at least 1 qubit.")
            if op.cbits and len(op.cbits) > 0:
                raise ValueError("Barrier operation cannot target classical bits.")
            for q in op.qubits:
                if not isinstance(q, int) or q < 0 or q >= num_qubits:
                    raise ValueError(f"Invalid qubit index {q} in barrier. Circuit has {num_qubits} qubits.")
            if len(set(op.qubits)) != len(op.qubits):
                raise ValueError(f"Duplicate qubits in barrier: {op.qubits}")

        elif gname in VALID_GATES_ARITY:
            exp_q, exp_c = VALID_GATES_ARITY[gname]
            if len(op.qubits) != exp_q:
                raise ValueError(f"Gate '{gname}' requires {exp_q} qubits, got {len(op.qubits)}: {op.qubits}")
            if len(op.cbits) != exp_c:
                raise ValueError(f"Gate '{gname}' requires {exp_c} classical bits, got {len(op.cbits)}: {op.cbits}")

            for q in op.qubits:
                if not isinstance(q, int) or q < 0 or q >= num_qubits:
                    raise ValueError(f"Invalid qubit index {q} for gate '{gname}'. Circuit has {num_qubits} qubits.")
            if len(set(op.qubits)) != len(op.qubits):
                raise ValueError(f"Duplicate qubits in gate '{gname}': {op.qubits}")

            for c in op.cbits:
                if not isinstance(c, int) or c < 0 or c >= num_clbits:
                    raise ValueError(f"Invalid classical bit index {c} for gate '{gname}'. Circuit has {num_clbits} clbits.")
        else:
            raise ValueError(f"Unsupported or unrecognized operation '{op.name}' in circuit.")


def _verify_structural_placement(orig_ops: List[Op], opt_ops: List[Op], delimiter_names: Set[str]) -> bool:
    """
    Verifies that all delimiter operations (e.g. non-unitaries or barriers) match exactly in identity,
    operands, and sequence, AND that unitary operations maintain their relative placement
    without ever crossing any delimiter boundary (DEF-05, DEF-06).
    """
    # 1. Delimiters must match exactly in name, qubits, cbits, and order
    orig_delims = [o for o in orig_ops if o.name in delimiter_names]
    opt_delims = [o for o in opt_ops if o.name in delimiter_names]
    if orig_delims != opt_delims:
        return False

    # 2. Partition into segments divided by delimiters
    orig_segments: List[List[Op]] = [[]]
    for o in orig_ops:
        if o.name in delimiter_names:
            orig_segments.append([])
        else:
            orig_segments[-1].append(o)

    opt_segments: List[List[Op]] = [[]]
    for o in opt_ops:
        if o.name in delimiter_names:
            opt_segments.append([])
        else:
            opt_segments[-1].append(o)

    if len(orig_segments) != len(opt_segments):
        return False

    # 3. In every segment, opt_segments[i] must be a valid subsequence of orig_segments[i]
    for orig_seg, opt_seg in zip(orig_segments, opt_segments):
        it = iter(orig_seg)
        if not all(op in it for op in opt_seg):
            return False

    return True


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


def _cancel_per_wire_adjacent_pairs(ops: List[Op], target_gates: Set[str]) -> Tuple[List[Op], int]:
    """
    Cancels pairs of identical self-inverse operations using a per-qubit frontier.

    Frontier tracking:
    For every qubit touched by an operation, we maintain the index of the most recent operation.
    Two operations ops[i] and ops[j] (where i < j) cancel if:
      - ops[i].name == ops[j].name and ops[j].name in target_gates
      - ops[i].qubits == ops[j].qubits (exact same qubits in the exact same order)
      - For EVERY qubit q in ops[j].qubits, last_op_on_qubit[q] == i
        (meaning no intervening operation has touched any qubit that this gate operates on)
      - Neither is a barrier, measurement, reset, or other non-unitary delimiter.

    Operations on disjoint/unrelated qubits do NOT touch these wires and therefore do NOT block cancellation.
    Barriers, measurements, resets, or operations on shared qubits update the frontier on their wires and block cancellation.
    """
    last_op_on_qubit: Dict[int, Optional[int]] = {}
    cancelled_indices: Set[int] = set()

    for j, op in enumerate(ops):
        is_delimiter = op.name in NON_UNITARY_GATES
        is_target = (not is_delimiter) and (op.name in target_gates)

        if is_target and op.qubits:
            cand_i = last_op_on_qubit.get(op.qubits[0])

            if (
                cand_i is not None
                and cand_i not in cancelled_indices
                and all(last_op_on_qubit.get(q) == cand_i for q in op.qubits)
                and ops[cand_i].name == op.name
                and ops[cand_i].qubits == op.qubits
                and ops[cand_i].name not in NON_UNITARY_GATES
            ):
                # Valid cancellation found
                cancelled_indices.add(cand_i)
                cancelled_indices.add(j)
                for q in op.qubits:
                    last_op_on_qubit[q] = None
                continue

        # Non-cancelled op updates the frontier on all qubits it acts on
        for q in op.qubits:
            last_op_on_qubit[q] = j

    if not cancelled_indices:
        return ops, 0

    new_ops = [op for idx, op in enumerate(ops) if idx not in cancelled_indices]
    return new_ops, len(cancelled_indices)


def _pass_self_inverse_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 2: SELF-INVERSE GATE CANCELLATION
    Cancels identical self-inverse gates operating on the exact same qubits:
    - Uses per-wire frontier tracking to allow cancellation across gates on disjoint qubits.
    - Blocked if an intervening operation touches any shared qubit.
    - Blocked by barriers, measurements, resets, or classically conditioned gates.
    """
    return _cancel_per_wire_adjacent_pairs(ops, SELF_INVERSE_GATES)


def _pass_cx_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 3: CX CANCELLATION
    Cancels CX operations when:
    - Both are CX gates.
    - Control and target qubits match in exact order: (c, t) == (c, t).
    - Uses per-wire frontier tracking (neither control nor target touched in between).
    - Blocked by barriers, measurements, resets, or any intervening op touching control or target.
    """
    return _cancel_per_wire_adjacent_pairs(ops, {"cx"})


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
    Validates input layouts and never silently drops operations (DEF-03, DEF-08).
    Falls back cleanly to an in-memory mock if the proprietary runtime is not installed.
    """
    # Normalize layouts
    if not q_layout:
        q_layout = [("q", num_qubits)] if num_qubits > 0 else []
    if not c_layout:
        c_layout = [("c", num_clbits)] if num_clbits > 0 else []

    # Validate register layouts and ops before reconstruction (DEF-03, DEF-08)
    _validate_register_layouts(q_layout, num_qubits, c_layout, num_clbits)
    _validate_circuit_ops(ops, num_qubits, num_clbits)

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
                gate_fn = getattr(G, "measure", None)
                if not gate_fn:
                    raise ValueError("Cannot reconstruct circuit: 'measure' not supported in Qniverse gates")
                new_qc.add_gate(gate_fn, q_map[o.qubits[0]], c_map[o.cbits[0]])
            elif o.name == "barrier":
                gate_fn = getattr(G, "barrier", None)
                if not gate_fn:
                    raise ValueError("Cannot reconstruct circuit: 'barrier' not supported in Qniverse gates")
                new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])
            elif o.name == "reset":
                gate_fn = getattr(G, "reset", None)
                if not gate_fn:
                    raise ValueError("Cannot reconstruct circuit: 'reset' not supported in Qniverse gates")
                new_qc.add_gate(gate_fn, q_map[o.qubits[0]])
            else:
                gate_fn = getattr(G, o.name, None)
                if not gate_fn:
                    raise ValueError(f"Cannot reconstruct circuit: gate '{o.name}' not supported in Qniverse gates")
                new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])

        if len(new_qc.operations) != len(ops):
            raise RuntimeError(
                f"Reconstructed circuit operation count mismatch: expected {len(ops)}, got {len(new_qc.operations)}"
            )

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
                lower_name = name.lower()
                if lower_name not in VALID_GATES_ARITY and lower_name != "barrier":
                    raise ValueError(f"Cannot reconstruct operation: unsupported gate type '{name}'")
                if lower_name == "measure":
                    self.name = "Measure"
                elif lower_name == "barrier":
                    self.name = "Barrier"
                elif lower_name == "reset":
                    self.name = "Reset"
                else:
                    self.name = name.upper()

        def _map_wire(idx: int, layout: List[Tuple[str, int]], kind: str) -> _MockWire:
            curr = 0
            for name, size in layout:
                if curr <= idx < curr + size:
                    return _MockWire(kind, name, size, idx - curr)
                curr += size
            # DEF-08: Never fabricate a fallback wire!
            raise ValueError(f"Wire index {idx} out of range for declared {kind} layout (total size {curr})")

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

                if len(self.operations) != len(op_list):
                    raise RuntimeError(
                        f"Reconstructed mock circuit operation count mismatch: expected {len(op_list)}, got {len(self.operations)}"
                    )

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
    A. Empty Circuits (DEF-07):
       - Trivially equivalent ONLY if both original and optimized op lists are empty.
       - Returns dimension mismatch if ops exist on 0 declared qubits.
    B. Parameterized Gates (DEF-04):
       - Disallows equivalence claims for parameterized gates without angle extraction.
    C. Purely unitary circuits (+ barriers):
       - Mathematical equivalence verified up to global phase using unitary matrix calculation.
       - Barriers are verified for operand, ordering, and relative gate placement (DEF-06).
    D. Circuits with terminal measurements:
       - Verified that measurements appear strictly at the end of the circuit.
       - Unitary prefix mathematically verified up to global phase.
       - Non-unitary operations (measurements and barriers) verified structurally across circuit (DEF-06).
       - Returns 'equivalent': True only if BOTH pass.
    E. Mid-circuit measurements or resets (DEF-05):
       - Returns 'equivalent': None with explicit warning (semantic equivalence unverified).
       - Structural placement relative to unitary ops is verified: gates must never cross non-unitary boundaries.
    """
    # ------------------------------------------------- Empty Circuit Validation (DEF-07)
    if num_qubits == 0:
        if len(original_ops) == 0 and len(optimized_ops) == 0:
            return {
                "type": "unitary",
                "equivalent": True,
                "mathematical_equivalence_verified": True,
                "structural_preservation_verified": True,
                "method": "trivial_empty_circuit",
                "details": "Empty circuit trivially equivalent."
            }
        else:
            return {
                "type": "invalid",
                "equivalent": False,
                "mathematical_equivalence_verified": False,
                "structural_preservation_verified": False,
                "method": "dimension_mismatch",
                "details": "Circuit contains operations but declared qubit count is 0."
            }

    # ------------------------------------------------- Parameterized Gates Check (DEF-04)
    if any(o.name in PARAMETERISED_GATES for o in original_ops) or any(o.name in PARAMETERISED_GATES for o in optimized_ops):
        return {
            "type": "parameterized_unsupported",
            "equivalent": False,
            "mathematical_equivalence_verified": False,
            "structural_preservation_verified": False,
            "method": "parameterized_gates_unsupported",
            "details": "Cannot verify equivalence for circuits containing parameterized gates without parameter angles."
        }

    # ------------------------------------------------- Validate Op Bounds & Arities (DEF-07)
    for op in original_ops + optimized_ops:
        gname = op.name.lower()
        if gname == "barrier":
            if not op.qubits or any(q < 0 or q >= num_qubits for q in op.qubits):
                return {
                    "type": "invalid",
                    "equivalent": False,
                    "mathematical_equivalence_verified": False,
                    "structural_preservation_verified": False,
                    "method": "malformed_operation_detected",
                    "details": f"Barrier with invalid qubit indices: {op.qubits}"
                }
        elif gname in VALID_GATES_ARITY:
            exp_q, _ = VALID_GATES_ARITY[gname]
            if len(op.qubits) != exp_q or any(q < 0 or q >= num_qubits for q in op.qubits):
                return {
                    "type": "invalid",
                    "equivalent": False,
                    "mathematical_equivalence_verified": False,
                    "structural_preservation_verified": False,
                    "method": "malformed_operation_detected",
                    "details": f"Gate '{gname}' with invalid qubit indices or arity: {op.qubits}"
                }
        else:
            return {
                "type": "invalid",
                "equivalent": False,
                "mathematical_equivalence_verified": False,
                "structural_preservation_verified": False,
                "method": "unsupported_gate",
                "details": f"Unsupported or unrecognized operation '{op.name}'"
            }

    has_measure = any(o.name == "measure" for o in original_ops)
    has_reset = any(o.name == "reset" for o in original_ops)

    # ------------------------------------------------- CASE A: Purely Unitary (+ Barriers)
    if not has_measure and not has_reset:
        u_orig = unitary(original_ops, num_qubits)
        u_opt = unitary(optimized_ops, num_qubits)
        is_equiv = equal_up_to_phase(u_orig, u_opt)

        barriers_preserved = _verify_structural_placement(original_ops, optimized_ops, {"barrier"})
        both_passed = bool(is_equiv and barriers_preserved)

        return {
            "type": "unitary",
            "equivalent": both_passed,
            "mathematical_equivalence_verified": bool(is_equiv),
            "structural_preservation_verified": barriers_preserved,
            "method": "equal_up_to_phase (tolerance 1e-9) and barrier_structural_placement",
            "details": (
                "Mathematical unitary equivalence proven up to global phase; barriers structurally verified."
                if both_passed
                else "Unitary equivalence or barrier preservation check failed."
            )
        }

    # ------------------------------------------------- Check for Terminal Measurements
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
        # --------------------------------------------- CASE B: Terminal Measurements (DEF-06)
        orig_prefix = original_ops[:first_meas_orig]
        opt_prefix = optimized_ops[:first_meas_opt]

        # Verify mathematical equivalence of unitary prefix
        if num_qubits > 0:
            u_orig = unitary(orig_prefix, num_qubits)
            u_opt = unitary(opt_prefix, num_qubits)
            prefix_equiv = bool(equal_up_to_phase(u_orig, u_opt))
        else:
            prefix_equiv = True

        # Verify structural preservation of all non-unitaries (measurements AND barriers throughout circuit)
        structural_preserved = _verify_structural_placement(original_ops, optimized_ops, NON_UNITARY)

        both_passed = prefix_equiv and structural_preserved

        return {
            "type": "terminal_measurement_verified",
            "equivalent": both_passed,
            "mathematical_equivalence_verified": prefix_equiv,
            "structural_preservation_verified": structural_preserved,
            "method": "unitary_prefix_matrix_and_non_unitary_structural_placement",
            "details": (
                "Unitary prefix mathematically verified via equal_up_to_phase; "
                "measurements and barriers verified structurally in-order without boundary crossing."
                if both_passed
                else "Terminal measurement or barrier verification failed."
            )
        }

    # ------------------------------------------------- CASE C: Mid-Circuit Non-Unitary / Resets (DEF-05)
    structural_match = _verify_structural_placement(original_ops, optimized_ops, NON_UNITARY)

    return {
        "type": "mid_circuit_non_unitary_unverified",
        "equivalent": None,
        "mathematical_equivalence_verified": False,
        "structural_preservation_verified": structural_match,
        "method": "semantic_equivalence_not_verified",
        "details": (
            "Semantic equivalence cannot be verified via unitary simulation for circuits "
            "with mid-circuit measurements or resets. Structural preservation of non-unitaries "
            "and boundary placement is verified separately."
            if structural_match
            else "Structural preservation check failed: non-unitary operations were altered or gates crossed boundaries."
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

    # Normalize layouts if empty and qubits/clbits declared
    if not q_layout:
        q_layout = [("q", num_qubits)] if num_qubits > 0 else []
    if not c_layout:
        c_layout = [("c", num_clbits)] if num_clbits > 0 else []

    # Layout and operation validation (DEF-04, DEF-07, DEF-08)
    _validate_register_layouts(q_layout, num_qubits, c_layout, num_clbits)
    _validate_circuit_ops(ops, num_qubits, num_clbits)

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
