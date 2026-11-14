"""
QC-C1-01 core: circuit profiling + limited basis-gate decomposition.

Works on a simple internal list of Op objects, so the maths is testable
without Qniverse. Includes from_qniverse() to extract gates (via QASM fallback)
and to_qniverse() to build a fresh QniverseCircuit using documented QSDK APIs.

Depth definition:
  * Every gate / measure / reset occupies one layer on ALL qubits it uses.
  * An op goes in the earliest layer after the latest layer used by any of its qubits.
  * A barrier adds no layer, but synchronises the qubits it spans
    (ops after it cannot slide before ops that came before it on those qubits).
"""
import re
from dataclasses import dataclass
from collections import Counter
import numpy as np

NON_UNITARY = {"measure", "reset", "barrier"}

# Verified Qniverse SDK imports (available only when running on C-DAC Qniverse platform)
try:
    from qniverse.gates import *
    import qniverse.gates as qg
    from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
    _HAVE_QNIVERSE = True
except (ImportError, ModuleNotFoundError):
    _HAVE_QNIVERSE = False


@dataclass(frozen=True)
class Op:
    name: str
    qubits: tuple
    cbits: tuple = ()


# ---------------------------------------------------------------- metrics
def profile(ops, num_qubits_declared):
    gates = [o for o in ops if o.name not in NON_UNITARY]
    counts = Counter(o.name for o in gates)
    used = {q for o in ops for q in o.qubits}

    free = [0] * num_qubits_declared          # next free layer per qubit
    depth = 0
    for o in ops:
        start = max(free[q] for q in o.qubits)
        if o.name == "barrier":
            for q in o.qubits:
                free[q] = start
            continue
        for q in o.qubits:
            free[q] = start + 1
        depth = max(depth, start + 1)

    return {
        "total_gates": len(gates),
        "by_type": dict(counts),
        "qubits_declared": num_qubits_declared,
        "qubits_used": len(used),
        "single_qubit_gates": sum(1 for o in gates if len(o.qubits) == 1),
        "multi_qubit_gates": sum(1 for o in gates if len(o.qubits) >= 2),
        "two_qubit_gates": sum(1 for o in gates if len(o.qubits) == 2),
        "depth": depth,
        "measurements": sum(1 for o in ops if o.name == "measure"),
    }


# ---------------------------------------------------------- decomposition
# Rules use LOCAL indices 0,1,2 for the gate's own qubits.
RULES = {
    "id": [("x", (0,)), ("x", (0,))],
    "x": [("h", (0,)), ("z", (0,)), ("h", (0,))],
    "y": [("sdg", (0,)), ("x", (0,)), ("s", (0,))],
    "z": [("h", (0,)), ("x", (0,)), ("h", (0,))],
    "cz": [("h", (1,)), ("cx", (0, 1)), ("h", (1,))],
    "cy": [("sdg", (1,)), ("cx", (0, 1)), ("s", (1,))],
    "swap": [("cx", (0, 1)), ("cx", (1, 0)), ("cx", (0, 1))],
    "s": [("t", (0,)), ("t", (0,))],
    "sdg": [("tdg", (0,)), ("tdg", (0,))],
    "z_from_s": [("s", (0,)), ("s", (0,))],   # not used automatically
    "ccx": [("h", (2,)), ("cx", (1, 2)), ("tdg", (2,)), ("cx", (0, 2)),
            ("t", (2,)), ("cx", (1, 2)), ("tdg", (2,)), ("cx", (0, 2)),
            ("t", (1,)), ("t", (2,)), ("h", (2,)), ("cx", (0, 1)),
            ("t", (0,)), ("tdg", (1,)), ("cx", (0, 1))],
}
# Alternative rules tried if the first expansion hits a non-basis gate.
ALT_RULES = {
    "z": [("s", (0,)), ("s", (0,))],
    "id": [("h", (0,)), ("h", (0,))],
}


def _expand(op, basis, stack=()):
    """Return list of basis-only ops, or None if impossible."""
    if op.name in basis or op.name in NON_UNITARY:
        return [op]
    if op.name in stack:
        return None
    options = [RULES.get(op.name)]
    if op.name in ALT_RULES:
        options.append(ALT_RULES[op.name])
    for rule in options:
        if not rule:
            continue
        out, ok = [], True
        for name, local in rule:
            sub = _expand(Op(name, tuple(op.qubits[i] for i in local)),
                          basis, stack + (op.name,))
            if sub is None:
                ok = False
                break
            out.extend(sub)
        if ok:
            return out
    return None


def decompose(ops, num_qubits_declared, basis):
    """Return (new_ops, report). Input list is never modified."""
    if not basis:
        raise ValueError("basis gate set must not be empty")
    basis = set(basis)
    new_ops, unsupported = [], []
    for i, o in enumerate(ops):
        res = _expand(o, basis)
        if res is None:
            unsupported.append({"index": i, "gate": o.name, "qubits": o.qubits})
        else:
            new_ops.extend(res)
    report = {"basis": sorted(basis),
              "before": profile(ops, num_qubits_declared),
              "unsupported": unsupported}
    if unsupported:
        report["status"] = "FAILED: unsupported operations, no circuit emitted"
        return None, report
    report["after"] = profile(new_ops, num_qubits_declared)
    report["status"] = "OK"
    return new_ops, report


# ------------------------------------------------------ verification (numpy)
_I = np.eye(2)
_H = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
_X = np.array([[0, 1], [1, 0]])
_Y = np.array([[0, -1j], [1j, 0]])
_Z = np.diag([1, -1])
_S = np.diag([1, 1j])
_T = np.diag([1, np.exp(1j * np.pi / 4)])
_SINGLE = {
    "id": _I, "h": _H, "x": _X, "y": _Y, "z": _Z,
    "s": _S, "sdg": _S.conj().T, "t": _T, "tdg": _T.conj().T
}


def _op_matrix(o, n):
    dim = 2 ** n
    m = np.zeros((dim, dim), dtype=complex)
    for col in range(dim):
        bits = [(col >> (n - 1 - k)) & 1 for k in range(n)]   # qubit 0 = leftmost
        if o.name in _SINGLE:
            q = o.qubits[0]
            for b in (0, 1):
                amp = _SINGLE[o.name][b, bits[q]]
                if amp != 0:
                    nb = bits.copy(); nb[q] = b
                    m[int("".join(map(str, nb)), 2), col] += amp
            continue
        nb = bits.copy()
        if o.name == "cx":
            if bits[o.qubits[0]]: nb[o.qubits[1]] ^= 1
        elif o.name == "cz":
            pass
        elif o.name == "cy":
            if bits[o.qubits[0]]:
                b = bits[o.qubits[1]]
                nb[o.qubits[1]] ^= 1
                phase = 1j if b == 0 else -1j
                m[int("".join(map(str, nb)), 2), col] += phase
                continue
        elif o.name == "swap":
            a, b = o.qubits; nb[a], nb[b] = bits[b], bits[a]
        elif o.name == "ccx":
            if bits[o.qubits[0]] and bits[o.qubits[1]]: nb[o.qubits[2]] ^= 1
        else:
            raise ValueError(f"verifier does not know gate {o.name}")
        phase = -1 if (o.name == "cz" and all(bits[q] for q in o.qubits)) else 1
        m[int("".join(map(str, nb)), 2), col] += phase
    return m


def unitary(ops, n):
    u = np.eye(2 ** n, dtype=complex)
    for o in ops:
        if o.name in NON_UNITARY:
            continue
        u = _op_matrix(o, n) @ u
    return u


def equal_up_to_phase(a, b, tol=1e-9):
    idx = np.unravel_index(np.argmax(np.abs(a)), a.shape)
    if abs(b[idx]) < tol:
        return False
    phase = a[idx] / b[idx]
    return np.allclose(a, phase * b, atol=tol)


# ----------------------------------------------------------- Qniverse hooks
def parse_qasm(qasm_str):
    """
    Parses OpenQASM 2.0 text representation into (ops, num_qubits).
    Maps Qniverse gate identifiers to lowercase profiler Op names.
    """
    if not isinstance(qasm_str, str) or not qasm_str.strip():
        raise ValueError("Invalid OpenQASM: empty or non-string input provided")

    qreg_map = {}   # reg_name -> (start_idx, size)
    creg_map = {}   # reg_name -> (start_idx, size)
    total_qubits = 0
    total_cbits = 0
    ops = []

    lines = qasm_str.strip().splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.split("//")[0].strip()
        if not line or line.endswith(";"):
            line = line[:-1].strip() if line.endswith(";") else line
        if not line:
            continue

        if line.startswith("OPENQASM") or line.startswith("include"):
            continue

        # Register declarations
        m_qreg = re.match(r"^qreg\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]$", line)
        if m_qreg:
            name, size = m_qreg.group(1), int(m_qreg.group(2))
            qreg_map[name] = (total_qubits, size)
            total_qubits += size
            continue

        m_creg = re.match(r"^creg\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]$", line)
        if m_creg:
            name, size = m_creg.group(1), int(m_creg.group(2))
            creg_map[name] = (total_cbits, size)
            total_cbits += size
            continue

        # Measurement: measure q[0] -> c[0]
        m_meas = re.match(r"^measure\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]\s*->\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]$", line)
        if m_meas:
            qr, qidx, cr, cidx = m_meas.group(1), int(m_meas.group(2)), m_meas.group(3), int(m_meas.group(4))
            if qr not in qreg_map or cr not in creg_map:
                raise ValueError(f"Line {line_no}: Unknown register in measurement: {line}")
            global_q = qreg_map[qr][0] + qidx
            global_c = creg_map[cr][0] + cidx
            ops.append(Op("measure", (global_q,), (global_c,)))
            continue

        # Reset: reset q[0]
        m_reset = re.match(r"^reset\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]$", line)
        if m_reset:
            qr, qidx = m_reset.group(1), int(m_reset.group(2))
            if qr not in qreg_map:
                raise ValueError(f"Line {line_no}: Unknown quantum register: {qr}")
            global_q = qreg_map[qr][0] + qidx
            ops.append(Op("reset", (global_q,)))
            continue

        # General gates & barrier: name arg1, arg2, ...
        parts = re.split(r"\s+", line, maxsplit=1)
        gate_name = parts[0].strip().lower()
        args_str = parts[1].strip() if len(parts) > 1 else ""

        # Parse qubit args like q[0], p[1]
        raw_args = [a.strip() for a in args_str.split(",") if a.strip()]
        q_indices = []
        for arg in raw_args:
            m_arg = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]$", arg)
            if not m_arg:
                raise ValueError(f"Line {line_no}: Malformed gate argument '{arg}' in '{line}'")
            reg, idx = m_arg.group(1), int(m_arg.group(2))
            if reg not in qreg_map:
                raise ValueError(f"Line {line_no}: Unknown register '{reg}'")
            q_indices.append(qreg_map[reg][0] + idx)

        # Standardise gate names
        norm_name = gate_name
        if norm_name == "cnot":
            norm_name = "cx"
        elif norm_name == "toffoli":
            norm_name = "ccx"

        ops.append(Op(norm_name, tuple(q_indices)))

    return ops, total_qubits


def from_qniverse(qc):
    """
    Converts a QniverseCircuit (or an object with a .qasm() / QASM string)
    into a list of Op objects and declared qubit count: (ops, num_qubits).
    Rejects missing or malformed circuits with a descriptive error.
    """
    if qc is None:
        raise ValueError("Invalid circuit: None supplied to from_qniverse")

    # If it's a QniverseCircuit with a .qasm() export method
    if hasattr(qc, "qasm") and callable(qc.qasm):
        qasm_str = qc.qasm()
        return parse_qasm(qasm_str)

    # If it's an object with a direct string qasm property
    if hasattr(qc, "qasm") and isinstance(qc.qasm, str):
        return parse_qasm(qc.qasm)

    # If a raw OpenQASM string was provided
    if isinstance(qc, str):
        return parse_qasm(qc)

    # If it exposes a gate list directly in memory
    if hasattr(qc, "gates") and isinstance(qc.gates, (list, tuple)):
        # Extract from in-memory gate list
        ops = []
        num_q = getattr(qc, "num_qubits", 0)
        for g in qc.gates:
            name = str(getattr(g, "name", "")).lower()
            qubits = tuple(getattr(g, "qubits", ()))
            cbits = tuple(getattr(g, "cbits", ()))
            ops.append(Op(name, qubits, cbits))
        return ops, num_q

    raise TypeError(
        f"Malformed circuit: expected a QniverseCircuit instance or OpenQASM string, got {type(qc)}"
    )


def to_qniverse(ops, num_qubits):
    """
    Builds a new QniverseCircuit from the Op list, preserving qubit indices
    and the order of operations, measurements, resets, and barriers.
    Uses only verified Qniverse SDK imports:
      from qniverse.gates import *
      from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
    """
    if not _HAVE_QNIVERSE:
        # Fallback representation if running outside the Qniverse execution container
        class MockQniverseCircuit:
            def __init__(self, ops, num_qubits):
                self._ops = list(ops)
                self.num_qubits = num_qubits

            def qasm(self):
                lines = [
                    "OPENQASM 2.0;",
                    'include "qelib1.inc";',
                    f"qreg q[{self.num_qubits}];"
                ]
                has_meas = any(o.name == "measure" for o in self._ops)
                if has_meas:
                    num_c = max((c for o in self._ops for c in o.cbits), default=0) + 1
                    lines.append(f"creg c[{num_c}];")
                for o in self._ops:
                    if o.name == "measure":
                        lines.append(f"measure q[{o.qubits[0]}] -> c[{o.cbits[0]}];")
                    elif o.name == "barrier":
                        args = ", ".join(f"q[{q}]" for q in o.qubits)
                        lines.append(f"barrier {args};")
                    elif o.name == "reset":
                        lines.append(f"reset q[{o.qubits[0]}];")
                    else:
                        args = ", ".join(f"q[{q}]" for q in o.qubits)
                        lines.append(f"{o.name} {args};")
                return "\n".join(lines) + "\n"

        return MockQniverseCircuit(ops, num_qubits)

    # Documented Qniverse SDK construction
    qc = QniverseCircuit()
    q = QuantumRegister(num_qubits, "q")
    qc.add_register(q)

    # Check if classical register needed
    has_meas = any(o.name == "measure" for o in ops)
    if has_meas:
        num_c = max((c for o in ops for c in o.cbits), default=0) + 1
        c = ClassicalRegister(num_c, "c")
        qc.add_register(c)

    for o in ops:
        if o.name == "measure":
            gate_fn = getattr(qg, "measure")
            qc.add_gate(gate_fn, q[o.qubits[0]], c[o.cbits[0]])
        elif o.name == "barrier":
            gate_fn = getattr(qg, "barrier", None)
            if gate_fn:
                qc.add_gate(gate_fn, *(q[idx] for idx in o.qubits))
        elif o.name == "reset":
            gate_fn = getattr(qg, "reset", None)
            if gate_fn:
                qc.add_gate(gate_fn, q[o.qubits[0]])
        else:
            gate_fn = getattr(qg, o.name, None)
            if gate_fn is None:
                raise ValueError(f"Documented gate '{o.name}' not found in qniverse.gates")
            qc.add_gate(gate_fn, *(q[idx] for idx in o.qubits))

    return qc


def analyze(qc, basis):
    """
    Analyzes and decomposes a circuit into a given basis set without modifying the input.
    Returns (new_qniverse_circuit, report).
    """
    ops, num_qubits = from_qniverse(qc)
    # Ensure immutability: deep copy the input ops list before decomposing
    input_snapshot = list(ops)
    new_ops, report = decompose(ops, num_qubits, basis)
    assert ops == input_snapshot, "Critical error: input ops were mutated during decomposition!"

    if new_ops is None:
        return None, report

    new_circuit = to_qniverse(new_ops, num_qubits)
    return new_circuit, report


# ------------------------------------------------------------------- tests
def _tests():
    # 1) depth: dependent chain vs disjoint qubits
    chain = [Op("h", (0,)), Op("cx", (0, 1)), Op("x", (1,))]
    assert profile(chain, 2)["depth"] == 3
    disjoint = [Op("h", (0,)), Op("h", (1,)), Op("h", (2,))]
    assert profile(disjoint, 3)["depth"] == 1
    p = profile([Op("h", (0,)), Op("cx", (0, 1)), Op("measure", (0,), (0,))], 2)
    assert p["total_gates"] == 2 and p["two_qubit_gates"] == 1 and p["depth"] == 3
    # barrier synchronises but adds no layer
    b = [Op("h", (0,)), Op("barrier", (0, 1)), Op("h", (1,))]
    assert profile(b, 2)["depth"] == 2

    # 2) every rule is equivalent to the original gate (up to global phase)
    for name, n in [("id", 1), ("x", 1), ("y", 1), ("z", 1), ("s", 1), ("sdg", 1),
                    ("cz", 2), ("cy", 2), ("swap", 2), ("ccx", 3)]:
        orig = [Op(name, tuple(range(n)))]
        new, rep = decompose(orig, n, {"h", "t", "tdg", "cx"})
        assert new is not None, (name, rep)
        assert all(o.name in {"h", "t", "tdg", "cx"} for o in new)
        assert equal_up_to_phase(unitary(orig, n), unitary(new, n)), name

    # 2b) basis {"h", "cx"} support for id, cz, swap
    for name, n in [("id", 1), ("cz", 2), ("swap", 2)]:
        orig = [Op(name, tuple(range(n)))]
        new, rep = decompose(orig, n, {"h", "cx"})
        assert new is not None, (name, rep)
        assert all(o.name in {"h", "cx"} for o in new)
        assert equal_up_to_phase(unitary(orig, n), unitary(new, n)), name

    # 3) unsupported op is reported; input untouched
    src = [Op("h", (0,)), Op("swap", (0, 1))]
    snapshot = list(src)
    new, rep = decompose(src, 2, {"h"})
    assert new is None and rep["unsupported"][0]["gate"] == "swap"
    assert src == snapshot

    # 4) empty basis rejected
    try:
        decompose(src, 2, set()); assert False
    except ValueError:
        pass

    # 5) OpenQASM parser verification
    qasm_sample = """
    OPENQASM 2.0;
    include "qelib1.inc";
    qreg q[2];
    creg c[2];
    h q[0];
    cx q[0], q[1];
    measure q[0] -> c[0];
    """
    parsed_ops, q_count = parse_qasm(qasm_sample)
    assert q_count == 2
    assert len(parsed_ops) == 3
    assert parsed_ops[0] == Op("h", (0,))
    assert parsed_ops[1] == Op("cx", (0, 1))
    assert parsed_ops[2] == Op("measure", (0,), (0,))

    # 6) analyze() immutability check
    new_c, rep = analyze(qasm_sample, {"h", "cx"})
    assert rep["status"] == "OK"
    assert new_c is not None

    print("all tests passed")


if __name__ == "__main__":
    _tests()
    ops = [Op("h", (0,)), Op("swap", (0, 1)), Op("measure", (0,), (0,))]
    new, rep = decompose(ops, 2, {"h", "cx"})
    import json
    print(json.dumps(rep, indent=2, default=list))
