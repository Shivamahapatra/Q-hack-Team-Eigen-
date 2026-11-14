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

# Verified Qniverse SDK imports (available only when running on C-DAC Qniverse platform)
try:
    from qniverse.gates import *
    import qniverse.gates as G
    from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
    _HAVE_QNIVERSE = True
except (ImportError, ModuleNotFoundError):
    _HAVE_QNIVERSE = False

# Supported optimization passes
PASS_IDENTITY_REMOVAL = "identity_removal"
PASS_SELF_INVERSE_CANCELLATION = "self_inverse_cancellation"
PASS_CX_CANCELLATION = "cx_cancellation"

# Individual gate passes
PASS_X_CANCELLATION = "x_cancellation"
PASS_Y_CANCELLATION = "y_cancellation"
PASS_Z_CANCELLATION = "z_cancellation"
PASS_H_CANCELLATION = "h_cancellation"
PASS_CY_CANCELLATION = "cy_cancellation"
PASS_CZ_CANCELLATION = "cz_cancellation"
PASS_CH_CANCELLATION = "ch_cancellation"
PASS_SWAP_CANCELLATION = "swap_cancellation"
PASS_CCX_CANCELLATION = "ccx_cancellation"
PASS_CSWAP_CANCELLATION = "cswap_cancellation"
PASS_S_SDG_CANCELLATION = "s_sdg_cancellation"
PASS_T_TDG_CANCELLATION = "t_tdg_cancellation"

DEFAULT_PASSES = [
    PASS_IDENTITY_REMOVAL,
    PASS_SELF_INVERSE_CANCELLATION,
    PASS_CX_CANCELLATION,
]

SUPPORTED_PASSES = [
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
]

SELF_INVERSE_GATES = {
    "x", "y", "z", "h", "cx", "cy", "cz", "ch", "swap", "ccx", "cswap"
}
SYMMETRIC_GATES = {"cz", "swap"}
INVERSE_PAIRS = {
    ("s", "sdg"), ("sdg", "s"),
    ("t", "tdg"), ("tdg", "t"),
}
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
    "cx": (2, 0), "cy": (2, 0), "cz": (2, 0), "ch": (2, 0), "swap": (2, 0),
    # 3-qubit gates
    "ccx": (3, 0), "cswap": (3, 0),
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


def _cancel_per_wire_adjacent_pairs(
    ops: List[Op],
    target_gates: Set[str],
    allow_symmetric: bool = True
) -> Tuple[List[Op], int]:
    """
    Cancels pairs of identical self-inverse operations using a per-qubit frontier.

    Frontier tracking:
    For every qubit touched by an operation, we maintain the index of the most recent operation.
    Two operations ops[i] and ops[j] (where i < j) cancel if:
      - ops[i].name == ops[j].name and ops[j].name in target_gates
      - Qubit operands match:
        * For symmetric gates (cz, swap): set(ops[i].qubits) == set(ops[j].qubits)
        * For all other gates (x, y, z, h, cx, cy, ch, ccx, cswap): ops[i].qubits == ops[j].qubits (strict order)
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

            if cand_i is not None and cand_i not in cancelled_indices:
                cand_op = ops[cand_i]
                qubits_match = (
                    (set(cand_op.qubits) == set(op.qubits))
                    if (allow_symmetric and op.name in SYMMETRIC_GATES)
                    else (cand_op.qubits == op.qubits)
                )
                if (
                    qubits_match
                    and all(last_op_on_qubit.get(q) == cand_i for q in op.qubits)
                    and cand_op.name == op.name
                    and cand_op.name not in NON_UNITARY_GATES
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


def _cancel_inverse_pairs(ops: List[Op], target_pairs: Set[Tuple[str, str]]) -> Tuple[List[Op], int]:
    """
    Cancels pairs of mutually inverse operations on identical wires using per-wire frontier tracking.
    E.g. S-SDG, SDG-S, T-TDG, TDG-T.
    """
    last_op_on_qubit: Dict[int, Optional[int]] = {}
    cancelled_indices: Set[int] = set()

    for j, op in enumerate(ops):
        is_delimiter = op.name in NON_UNITARY_GATES

        if not is_delimiter and op.qubits:
            cand_i = last_op_on_qubit.get(op.qubits[0])

            if (
                cand_i is not None
                and cand_i not in cancelled_indices
                and all(last_op_on_qubit.get(q) == cand_i for q in op.qubits)
                and (ops[cand_i].name, op.name) in target_pairs
                and ops[cand_i].qubits == op.qubits
                and ops[cand_i].name not in NON_UNITARY_GATES
            ):
                cancelled_indices.add(cand_i)
                cancelled_indices.add(j)
                for q in op.qubits:
                    last_op_on_qubit[q] = None
                continue

        for q in op.qubits:
            last_op_on_qubit[q] = j

    if not cancelled_indices:
        return ops, 0

    new_ops = [op for idx, op in enumerate(ops) if idx not in cancelled_indices]
    return new_ops, len(cancelled_indices)


def _pass_self_inverse_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 2: SELF-INVERSE GATE CANCELLATION
    Cancels identical self-inverse gates operating on matching qubits:
    - 1-qubit: x, y, z, h
    - 2-qubit: cx, cy, cz, ch, swap (cz and swap accept symmetric qubit ordering)
    - 3-qubit: ccx, cswap
    """
    return _cancel_per_wire_adjacent_pairs(ops, SELF_INVERSE_GATES, allow_symmetric=True)


def _pass_cx_cancellation(ops: List[Op]) -> Tuple[List[Op], int]:
    """
    PASS 3: CX CANCELLATION
    Cancels CX operations when:
    - Both are CX gates.
    - Control and target qubits match in exact order: (c, t) == (c, t).
    - Uses per-wire frontier tracking (neither control nor target touched in between).
    - Blocked by barriers, measurements, resets, or any intervening op touching control or target.
    """
    return _cancel_per_wire_adjacent_pairs(ops, {"cx"}, allow_symmetric=False)


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

    # Individual gate pass mapping
    individual_gate_map = {
        PASS_CX_CANCELLATION: ({"cx"}, False),
        PASS_X_CANCELLATION: ({"x"}, False),
        PASS_Y_CANCELLATION: ({"y"}, False),
        PASS_Z_CANCELLATION: ({"z"}, False),
        PASS_H_CANCELLATION: ({"h"}, False),
        PASS_CY_CANCELLATION: ({"cy"}, False),
        PASS_CZ_CANCELLATION: ({"cz"}, True),
        PASS_CH_CANCELLATION: ({"ch"}, False),
        PASS_SWAP_CANCELLATION: ({"swap"}, True),
        PASS_CCX_CANCELLATION: ({"ccx"}, False),
        PASS_CSWAP_CANCELLATION: ({"cswap"}, False),
    }

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

        # Run individually enabled passes (if not already handled by self-inverse group)
        for pass_name, (gate_set, sym) in individual_gate_map.items():
            if pass_name in passes and (PASS_SELF_INVERSE_CANCELLATION not in passes or pass_name == PASS_CX_CANCELLATION):
                current_ops, count = _cancel_per_wire_adjacent_pairs(current_ops, gate_set, allow_symmetric=sym)
                if count > 0:
                    passes_applied.add(pass_name)
                    changed = True

        if PASS_S_SDG_CANCELLATION in passes:
            current_ops, count = _cancel_inverse_pairs(current_ops, {("s", "sdg"), ("sdg", "s")})
            if count > 0:
                passes_applied.add(PASS_S_SDG_CANCELLATION)
                changed = True

        if PASS_T_TDG_CANCELLATION in passes:
            current_ops, count = _cancel_inverse_pairs(current_ops, {("t", "tdg"), ("tdg", "t")})
            if count > 0:
                passes_applied.add(PASS_T_TDG_CANCELLATION)
                changed = True

    return current_ops, sorted(passes_applied)


def _decompose_wide_barrier(qubits: Tuple[int, ...]) -> List[Tuple[int, ...]]:
    """
    Decomposes a barrier spanning >2 qubits into a chain of 2-qubit barriers
    forward (a,b), (b,c), ... and backward back to (a,b) to ensure full synchronization
    across all qubits without exceeding Qniverse's 2-qubit barrier limit.
    Single-qubit and two-qubit barriers are returned as-is.
    """
    if len(qubits) <= 2:
        return [qubits]

    pairs = []
    n = len(qubits)
    # Forward pairs: (q_0, q_1), (q_1, q_2), ..., (q_{n-2}, q_{n-1})
    for i in range(n - 1):
        pairs.append((qubits[i], qubits[i + 1]))
    # Backward pairs back to (q_0, q_1): (q_{n-3}, q_{n-2}), ..., (q_0, q_1)
    for i in range(n - 3, -1, -1):
        pairs.append((qubits[i], qubits[i + 1]))
    return pairs


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
    live_G = sys.modules.get("qniverse.gates") if "qniverse.gates" in sys.modules else (globals().get("G") if _HAVE_QNIVERSE else None)
    live_qc_cls = None
    live_qreg_cls = None
    live_creg_cls = None
    if "qniverse.QniverseCircuit" in sys.modules:
        m = sys.modules["qniverse.QniverseCircuit"]
        live_qc_cls = getattr(m, "QniverseCircuit", None)
        live_qreg_cls = getattr(m, "QuantumRegister", None)
        live_creg_cls = getattr(m, "ClassicalRegister", None)
    elif _HAVE_QNIVERSE:
        live_qc_cls = globals().get("QniverseCircuit")
        live_qreg_cls = globals().get("QuantumRegister")
        live_creg_cls = globals().get("ClassicalRegister")

    if live_G and live_qc_cls and live_qreg_cls and live_creg_cls:
        try:
            new_qc = live_qc_cls()
            new_qc._backend = "qniverse"
            q_map = {}
            curr_q = 0
            for name, size in q_layout:
                reg = live_qreg_cls(size, name)
                new_qc.add_register(reg)
                for i in range(size):
                    q_map[curr_q + i] = reg[i]
                curr_q += size

            c_map = {}
            curr_c = 0
            for name, size in c_layout:
                reg = live_creg_cls(size, name)
                new_qc.add_register(reg)
                for i in range(size):
                    c_map[curr_c + i] = reg[i]
                curr_c += size

            for o in ops:
                if o.name == "measure":
                    gate_fn = getattr(live_G, "measure", None)
                    if not gate_fn:
                        raise ValueError("Cannot reconstruct circuit: 'measure' not supported in Qniverse gates")
                    new_qc.add_gate(gate_fn, q_map[o.qubits[0]], c_map[o.cbits[0]])
                elif o.name == "barrier":
                    gate_fn = getattr(live_G, "barrier", None)
                    if not gate_fn:
                        raise ValueError("Cannot reconstruct circuit: 'barrier' not supported in Qniverse gates")
                    if len(o.qubits) <= 2:
                        new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])
                    else:
                        for pair in _decompose_wide_barrier(o.qubits):
                            new_qc.add_gate(gate_fn, *[q_map[q] for q in pair])
                elif o.name == "reset":
                    gate_fn = getattr(live_G, "reset", None)
                    if not gate_fn:
                        raise ValueError("Cannot reconstruct circuit: 'reset' not supported in Qniverse gates")
                    new_qc.add_gate(gate_fn, q_map[o.qubits[0]])
                else:
                    gate_fn = getattr(live_G, o.name, None)
                    if not gate_fn:
                        raise ValueError(f"Cannot reconstruct circuit: gate '{o.name}' not supported in Qniverse gates")
                    new_qc.add_gate(gate_fn, *[q_map[q] for q in o.qubits])

            expected_qc_ops = sum(
                len(_decompose_wide_barrier(o.qubits)) if o.name == "barrier" and len(o.qubits) > 2 else 1
                for o in ops
            )
            if len(new_qc.operations) != expected_qc_ops:
                raise RuntimeError(
                    f"Reconstructed circuit operation count mismatch: expected {expected_qc_ops}, got {len(new_qc.operations)}"
                )

            if metadata:
                new_qc.metadata = copy.deepcopy(metadata)
            return new_qc
        except Exception as e:
            fallback_reason = str(e)
            print(f"Warning: Real SDK rejected operation during rebuild: {e}. Using fallback in-memory mock backend.")
    else:
        fallback_reason = "Qniverse SDK not installed (qniverse package missing)"
        print("Warning: Real Qniverse SDK not found (qniverse package missing). Using fallback in-memory mock backend.")

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
            self._backend = "fallback"
            self._fallback_reason = None
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

    mock_qc = _MockQniverseCircuit(num_qubits, num_clbits, ops, q_layout, c_layout, metadata)
    mock_qc._backend = "fallback"
    mock_qc._fallback_reason = fallback_reason
    return mock_qc


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

    # Priority 3: Check for conditional gates
    if getattr(qc, "has_conditional", False):
        skip_msg = "optimization skipped: conditional gates present"
        warnings.append(skip_msg)
        backend = getattr(qc, "_backend", "fallback")
        fallback_reason = getattr(qc, "_fallback_reason", None)
        report = {
            "status": skip_msg,
            "backend": backend,
            "fallback_reason": fallback_reason,
            "passes_enabled": selected_passes,
            "passes_applied": [],
            "before": None,
            "after": None,
            "gates_removed": 0,
            "reduction_percentage": 0.0,
            "equivalence": {
                "type": "skipped",
                "equivalent": None,
                "mathematical_equivalence_verified": False,
                "structural_preservation_verified": True,
                "method": "circuit_preserved_unchanged",
                "details": "Optimization skipped due to conditional gates; circuit returned unchanged."
            },
            "warnings": warnings,
        }
        return OptimizationResult(circuit=qc, report=report)

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

    # Reconstruct fresh circuit object preserving layout and metadata
    new_circuit = _reconstruct_circuit(
        optimized_ops,
        num_qubits,
        num_clbits,
        q_layout=q_layout,
        c_layout=c_layout,
        metadata=circuit_metadata
    )

    backend = getattr(new_circuit, "_backend", "fallback")
    fallback_reason = getattr(new_circuit, "_fallback_reason", None)
    if backend == "fallback":
        warnings.append(f"Backend fallback: {fallback_reason}")

    report = {
        "status": status,
        "backend": backend,
        "fallback_reason": fallback_reason,
        "passes_enabled": selected_passes,
        "passes_applied": passes_applied,
        "before": metrics_before,
        "after": metrics_after,
        "gates_removed": gates_removed,
        "reduction_percentage": reduction_pct,
        "equivalence": eq_check,
        "warnings": warnings,
    }

    return OptimizationResult(circuit=new_circuit, report=report)


class CircuitDiagram(str):
    """String subclass representing an ASCII circuit diagram with column metadata."""

    def __new__(cls, content: str, num_columns: int = 0):
        obj = str.__new__(cls, content)
        obj.num_columns = num_columns
        return obj


def _gate_symbols(op: Op) -> Dict[int, str]:
    """Maps an Op to its ASCII display symbol on each qubit it acts on."""
    name = op.name.lower()
    qs = op.qubits
    if name == "barrier":
        return {q: "|" for q in qs}
    if name == "measure":
        return {q: "M" for q in qs}
    if name == "reset":
        return {q: "R" for q in qs}
    if name == "id":
        return {qs[0]: "Id"}
    if name == "cx":
        return {qs[0]: "@", qs[1]: "(+)"}
    if name == "cy":
        return {qs[0]: "@", qs[1]: "(Y)"}
    if name == "cz":
        return {qs[0]: "@", qs[1]: "@"}
    if name == "ch":
        return {qs[0]: "@", qs[1]: "(H)"}
    if name == "swap":
        return {qs[0]: "x", qs[1]: "x"}
    if name == "ccx":
        return {qs[0]: "@", qs[1]: "@", qs[2]: "(+)"}
    if name == "cswap":
        return {qs[0]: "@", qs[1]: "x", qs[2]: "x"}
    if name == "s":
        return {qs[0]: "S"}
    if name == "sdg":
        return {qs[0]: "Sdg"}
    if name == "t":
        return {qs[0]: "T"}
    if name == "tdg":
        return {qs[0]: "Tdg"}
    if name in ("h", "x", "y", "z"):
        return {qs[0]: name.upper()}
    if name in ("rx", "ry", "rz", "p", "u1", "u2", "u3"):
        return {qs[0]: name.capitalize()}
    if len(qs) == 1:
        return {qs[0]: name.upper()}
    return {q: name.upper() for q in qs}


def draw_text(
    ops: Any,
    num_qubits: Optional[int] = None,
    print_output: bool = True
) -> CircuitDiagram:
    """
    Renders and prints a clean ASCII circuit diagram, one line per qubit,
    with gates ordered and aligned in chronological execution layers (depth columns),
    a vertical marker '|' for barriers, and zero dependency on the Qniverse draw method.

    Example output:
      q0: --H--X--@--M--
      q2: --Y--(+)--T--M--

    Args:
        ops: A list of Op instances, or a QniverseCircuit object.
        num_qubits: Declared qubit count. If omitted, inferred from ops or circuit.
        print_output: Whether to print the diagram to stdout (default True).

    Returns:
        CircuitDiagram (str subclass with a .num_columns attribute).
    """
    # Ingest operations from QniverseCircuit if passed
    if hasattr(ops, "operations"):
        import qniverse_adapter as _qa
        parsed_ops, q_count, _, _ = _qa.from_qniverse(ops)
        if num_qubits is None:
            num_qubits = q_count
        ops = parsed_ops
    elif hasattr(ops, "__iter__"):
        ops = list(ops)
    else:
        raise TypeError(f"Expected list of Op or QniverseCircuit, got {type(ops)}")

    if num_qubits is None:
        if ops:
            num_qubits = max((q for o in ops for q in o.qubits), default=-1) + 1
        else:
            num_qubits = 0

    if num_qubits == 0:
        empty_diag = CircuitDiagram("(empty circuit)", num_columns=0)
        if print_output:
            print(empty_diag)
        return empty_diag

    # Schedule operations into column layers using DAG / depth rules
    free = [0] * num_qubits
    layers: List[Dict[int, str]] = []

    for o in ops:
        sym_map = _gate_symbols(o)
        start = max((free[q] for q in o.qubits), default=0)

        # Ensure layers list has enough capacity up to column start
        while len(layers) <= start:
            layers.append({})

        # If any qubit in o.qubits is already occupied at layers[start], advance
        while any(q in layers[start] for q in o.qubits):
            start += 1
            while len(layers) <= start:
                layers.append({})

        # Place symbols into layers[start]
        for q, sym in sym_map.items():
            if q < num_qubits:
                layers[start][q] = sym

        # Update next free layer for the qubits
        for q in o.qubits:
            if q < num_qubits:
                free[q] = start + 1

    num_columns = len(layers)
    label_width = len(str(num_qubits - 1))

    if num_columns == 0:
        lines = [f"q{q:<{label_width}}: --" for q in range(num_qubits)]
        diag = CircuitDiagram("\n".join(lines), num_columns=0)
        if print_output:
            print(diag)
        return diag

    # Calculate column widths across all qubits
    col_widths = []
    for c in range(num_columns):
        w = max((len(layers[c].get(q, "")) for q in range(num_qubits)), default=1)
        col_widths.append(max(w, 1))

    # Build ASCII wire strings
    lines = []
    for q in range(num_qubits):
        prefix = f"q{q:<{label_width}}: --"
        wire_segments = []
        for c in range(num_columns):
            w = col_widths[c]
            sym = layers[c].get(q)
            if sym is None:
                # Idle wire
                cell = "-" * w
            else:
                # Pad symbol with dashes to match column width
                pad_total = w - len(sym)
                pad_left = pad_total // 2
                pad_right = pad_total - pad_left
                cell = ("-" * pad_left) + sym + ("-" * pad_right)
            wire_segments.append(cell + "--")
        lines.append(prefix + "".join(wire_segments))

    diagram_text = "\n".join(lines)
    result = CircuitDiagram(diagram_text, num_columns=num_columns)

    if print_output:
        print(result)

    return result

