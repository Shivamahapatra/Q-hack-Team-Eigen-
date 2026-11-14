"""
QC-C2-04: OpenQASM 2.0 / 3.0 to QniverseCircuit Converter.
PESU - C-DAC Quantum Hackathon 2026 | Team Eigen

Accepts OpenQASM 2.0 or 3.0 source strings, detects the version,
parses quantum/classical registers, standard and parameterized gates,
barriers, and measurements, and constructs a live QniverseCircuit
using official QSDK interfaces (with offline mock fallback).
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class QasmOp:
    name: str
    qubits: Tuple[int, ...]
    cbits: Tuple[int, ...] = ()
    params: Tuple[float, ...] = ()
    line_no: int = 0


# Safe angle expression evaluator (e.g. "pi/2", "3*pi/4", "1.57", "-pi")
def _safe_eval_angle(expr: str) -> float:
    expr = expr.strip()
    # Replace common pi notations
    expr = re.sub(r"\bpi\b", str(math.pi), expr)
    expr = expr.replace("π", str(math.pi))
    # Validate characters (only numbers, math operators, decimals)
    if not re.match(r"^[\d\.\s\+\-\*\/\(\)]+$", expr):
        raise ValueError(f"Invalid angle expression: '{expr}'")
    # Evaluate using restricted globals
    return float(eval(expr, {"__builtins__": {}}, {}))


class QasmConverter:
    """
    Universal Parser and Converter for OpenQASM 2.0 and 3.0 to QniverseCircuit.
    """

    STANDARD_1Q_GATES = {
        "id", "x", "y", "z", "h", "s", "sdg", "t", "tdg", "sx", "sxdg"
    }
    STANDARD_2Q_GATES = {"cx", "cnot", "cz", "swap", "ch"}
    STANDARD_3Q_GATES = {"ccx", "toffoli"}
    PARAM_GATES = {"rx", "ry", "rz", "p", "u1", "u2", "u3", "cp", "crz"}
    NON_UNITARY = {"measure", "reset", "barrier"}

    def __init__(self):
        self.reset()

    def reset(self):
        self.version: Optional[str] = None
        self.qreg_map: Dict[str, Tuple[int, int]] = {}  # name -> (start_idx, size)
        self.creg_map: Dict[str, Tuple[int, int]] = {}  # name -> (start_idx, size)
        self.total_qubits: int = 0
        self.total_cbits: int = 0
        self.ops: List[QasmOp] = []
        self.warnings: List[str] = []
        self.unsupported: List[Dict[str, Any]] = []

    def detect_version(self, text: str) -> str:
        """Identifies OpenQASM version from header or syntax."""
        for line in text.splitlines():
            clean = line.split("//")[0].strip()
            m = re.match(r"^OPENQASM\s+([0-9\.]+)\s*;?$", clean, re.IGNORECASE)
            if m:
                ver = m.group(1).strip()
                if ver.startswith("2"):
                    return "2.0"
                elif ver.startswith("3"):
                    return "3.0"
                return ver
            if clean.startswith("qubit[") or clean.startswith("bit["):
                return "3.0"
        return "2.0"  # default fallback per standard convention

    def parse(self, qasm_str: str, override_version: Optional[str] = None) -> Tuple[List[QasmOp], Dict[str, Any]]:
        """
        Parses OpenQASM 2.0 / 3.0 text into internal QasmOp list.
        Returns (ops, report_metadata).
        """
        self.reset()
        if not isinstance(qasm_str, str) or not qasm_str.strip():
            raise ValueError("Input QASM source is empty or invalid.")

        self.version = override_version or self.detect_version(qasm_str)
        lines = qasm_str.strip().splitlines()

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.split("//")[0].strip()
            if not line:
                continue
            if line.endswith(";"):
                line = line[:-1].strip()

            # Skip header / include
            if re.match(r"^OPENQASM\s+", line, re.IGNORECASE) or line.startswith("include"):
                continue

            # Check for unsupported dynamic control flow in MVP
            if re.match(r"^(for|while|if)\b", line):
                self.unsupported.append({
                    "line": line_no,
                    "statement": line,
                    "reason": "Dynamic control flow (loops/conditionals) unsupported in standard QSDK"
                })
                continue

            # ---------------- Register Declarations ----------------
            # OpenQASM 2.0: qreg q[2]; creg c[2];
            m_qreg2 = re.match(r"^qreg\s+([A-Za-z_]\w*)\s*\[(\d+)\]$", line)
            if m_qreg2:
                name, size = m_qreg2.group(1), int(m_qreg2.group(2))
                self.qreg_map[name] = (self.total_qubits, size)
                self.total_qubits += size
                continue

            m_creg2 = re.match(r"^creg\s+([A-Za-z_]\w*)\s*\[(\d+)\]$", line)
            if m_creg2:
                name, size = m_creg2.group(1), int(m_creg2.group(2))
                self.creg_map[name] = (self.total_cbits, size)
                self.total_cbits += size
                continue

            # OpenQASM 3.0: qubit[2] q; bit[2] c; or single qubit q;
            m_qreg3 = re.match(r"^qubit\s*(?:\[(\d+)\])?\s+([A-Za-z_]\w*)$", line)
            if m_qreg3:
                size_str, name = m_qreg3.group(1), m_qreg3.group(2)
                size = int(size_str) if size_str else 1
                self.qreg_map[name] = (self.total_qubits, size)
                self.total_qubits += size
                continue

            m_creg3 = re.match(r"^bit\s*(?:\[(\d+)\])?\s+([A-Za-z_]\w*)$", line)
            if m_creg3:
                size_str, name = m_creg3.group(1), m_creg3.group(2)
                size = int(size_str) if size_str else 1
                self.creg_map[name] = (self.total_cbits, size)
                self.total_cbits += size
                continue

            # ---------------- Measurements ----------------
            # OpenQASM 2.0: measure q[0] -> c[0];
            m_meas2 = re.match(r"^measure\s+([A-Za-z_]\w*)\s*\[(\d+)\]\s*->\s*([A-Za-z_]\w*)\s*\[(\d+)\]$", line)
            if m_meas2:
                qr, qidx, cr, cidx = m_meas2.group(1), int(m_meas2.group(2)), m_meas2.group(3), int(m_meas2.group(4))
                if qr not in self.qreg_map or cr not in self.creg_map:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": "Unknown register"})
                    continue
                if qidx < 0 or qidx >= self.qreg_map[qr][1]:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": f"Qubit index {qidx} out of range for '{qr}'"})
                    continue
                if cidx < 0 or cidx >= self.creg_map[cr][1]:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": f"Classical bit index {cidx} out of range for '{cr}'"})
                    continue
                gq = self.qreg_map[qr][0] + qidx
                gc = self.creg_map[cr][0] + cidx
                self.ops.append(QasmOp("measure", (gq,), (gc,), line_no=line_no))
                continue

            # OpenQASM 3.0: c[0] = measure q[0];
            m_meas3 = re.match(r"^([A-Za-z_]\w*)\s*\[(\d+)\]\s*=\s*measure\s+([A-Za-z_]\w*)\s*\[(\d+)\]$", line)
            if m_meas3:
                cr, cidx, qr, qidx = m_meas3.group(1), int(m_meas3.group(2)), m_meas3.group(3), int(m_meas3.group(4))
                if qr not in self.qreg_map or cr not in self.creg_map:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": "Unknown register"})
                    continue
                if qidx < 0 or qidx >= self.qreg_map[qr][1]:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": f"Qubit index {qidx} out of range for '{qr}'"})
                    continue
                if cidx < 0 or cidx >= self.creg_map[cr][1]:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": f"Classical bit index {cidx} out of range for '{cr}'"})
                    continue
                gq = self.qreg_map[qr][0] + qidx
                gc = self.creg_map[cr][0] + cidx
                self.ops.append(QasmOp("measure", (gq,), (gc,), line_no=line_no))
                continue

            # ---------------- Resets ----------------
            m_reset = re.match(r"^reset\s+([A-Za-z_]\w*)\s*\[(\d+)\]$", line)
            if m_reset:
                qr, qidx = m_reset.group(1), int(m_reset.group(2))
                if qr not in self.qreg_map:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": "Unknown register"})
                    continue
                if qidx < 0 or qidx >= self.qreg_map[qr][1]:
                    self.unsupported.append({"line": line_no, "statement": line, "reason": f"Qubit index {qidx} out of range for '{qr}'"})
                    continue
                gq = self.qreg_map[qr][0] + qidx
                self.ops.append(QasmOp("reset", (gq,), line_no=line_no))
                continue

            # ---------------- Barriers ----------------
            m_barr = re.match(r"^barrier(?:\s+(.+))?$", line)
            if m_barr:
                arg_str = m_barr.group(1)
                q_indices = []
                if arg_str:
                    for a in arg_str.split(","):
                        a = a.strip()
                        m_a = re.match(r"^([A-Za-z_]\w*)\s*\[(\d+)\]$", a)
                        if m_a and m_a.group(1) in self.qreg_map:
                            q_indices.append(self.qreg_map[m_a.group(1)][0] + int(m_a.group(2)))
                else:
                    q_indices = list(range(self.total_qubits))
                self.ops.append(QasmOp("barrier", tuple(q_indices), line_no=line_no))
                continue

            # ---------------- Standard & Parameterized Gates ----------------
            # e.g., "h q[0]" or "cx q[0], q[1]" or "rx(pi/2) q[0]" or "u3(0.1, 0.2, 0.3) q[0]"
            m_gate = re.match(r"^([A-Za-z_]\w*)(?:\(([^)]*)\))?\s+(.+)$", line)
            if not m_gate:
                self.unsupported.append({
                    "line": line_no,
                    "statement": line,
                    "reason": "Malformed syntax or unrecognized statement"
                })
                continue

            gate_name = m_gate.group(1).lower()
            params_str = m_gate.group(2)
            args_str = m_gate.group(3)

            # Standardize aliases
            if gate_name == "cnot":
                gate_name = "cx"
            elif gate_name == "toffoli":
                gate_name = "ccx"

            # Parse rotation angles / parameters
            params: List[float] = []
            if params_str:
                try:
                    for p in params_str.split(","):
                        params.append(_safe_eval_angle(p))
                except Exception as e:
                    self.unsupported.append({
                        "line": line_no,
                        "statement": line,
                        "reason": f"Failed to parse parameter: {e}"
                    })
                    continue

            # Parse qubit wires
            q_indices: List[int] = []
            args_ok = True
            for a in args_str.split(","):
                a = a.strip()
                m_a = re.match(r"^([A-Za-z_]\w*)\s*\[(\d+)\]$", a)
                if not m_a or m_a.group(1) not in self.qreg_map:
                    self.unsupported.append({
                        "line": line_no,
                        "statement": line,
                        "reason": f"Unknown or invalid qubit argument '{a}'"
                    })
                    args_ok = False
                    break
                reg_name = m_a.group(1)
                idx = int(m_a.group(2))
                start_offset, reg_size = self.qreg_map[reg_name]
                if idx < 0 or idx >= reg_size:
                    self.unsupported.append({
                        "line": line_no,
                        "statement": line,
                        "reason": f"Qubit index {idx} out of range for register '{reg_name}' of size {reg_size}"
                    })
                    args_ok = False
                    break
                q_indices.append(start_offset + idx)

            if not args_ok:
                continue

            # Check supported gate catalog
            all_known = (
                self.STANDARD_1Q_GATES | self.STANDARD_2Q_GATES | 
                self.STANDARD_3Q_GATES | self.PARAM_GATES
            )
            if gate_name not in all_known:
                self.unsupported.append({
                    "line": line_no,
                    "statement": line,
                    "reason": f"Unknown or unsupported quantum gate '{gate_name}'"
                })
                continue

            self.ops.append(QasmOp(gate_name, tuple(q_indices), params=tuple(params), line_no=line_no))

        meta = {
            "version": self.version,
            "total_qubits": self.total_qubits,
            "total_cbits": self.total_cbits,
            "unsupported": self.unsupported,
            "warnings": self.warnings
        }
        return self.ops, meta


# ------------------------------------------------ QSDK Circuit Builder
def build_qniverse_circuit(ops: List[QasmOp], num_qubits: int, num_cbits: int):
    """
    Constructs an official QniverseCircuit object from parsed QasmOp list.
    Falls back cleanly to MockQniverseCircuit if running outside the platform container.
    """
    try:
        from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
        import qniverse.gates as G
        has_real_sdk = True
    except ImportError:
        has_real_sdk = False

    if not has_real_sdk:
        # Offline Mock representation for unit tests and local development
        class MockQniverseCircuit:
            def __init__(self, ops, n_q, n_c):
                self._ops = list(ops)
                self.num_qubits = n_q
                self.num_clbits = n_c

            def qasm(self) -> str:
                lines = ["OPENQASM 2.0;", 'include "qelib1.inc";']
                lines.append(f"qreg q[{self.num_qubits}];")
                if self.num_clbits:
                    lines.append(f"creg c[{self.num_clbits}];")
                for o in self._ops:
                    if o.name == "measure":
                        lines.append(f"measure q[{o.qubits[0]}] -> c[{o.cbits[0]}];")
                    elif o.name == "barrier":
                        args = ", ".join(f"q[{q}]" for q in o.qubits)
                        lines.append(f"barrier {args};")
                    elif o.name == "reset":
                        lines.append(f"reset q[{o.qubits[0]}];")
                    elif o.params:
                        param_str = ", ".join(f"{p:.6f}" for p in o.params)
                        args = ", ".join(f"q[{q}]" for q in o.qubits)
                        lines.append(f"{o.name}({param_str}) {args};")
                    else:
                        args = ", ".join(f"q[{q}]" for q in o.qubits)
                        lines.append(f"{o.name} {args};")
                return "\n".join(lines) + "\n"

            def __repr__(self):
                return f"<MockQniverseCircuit qubits={self.num_qubits} clbits={self.num_clbits} ops={len(self._ops)}>"

        return MockQniverseCircuit(ops, num_qubits, num_cbits)

    # Official Qniverse SDK Construction
    qc = QniverseCircuit()
    q = QuantumRegister(num_qubits, "q")
    qc.add_register(q)
    c = None
    if num_cbits > 0:
        c = ClassicalRegister(num_cbits, "c")
        qc.add_register(c)

    for o in ops:
        if o.name == "measure":
            gate_fn = getattr(G, "measure")
            qc.add_gate(gate_fn, q[o.qubits[0]], c[o.cbits[0]])
        elif o.name == "barrier":
            gate_fn = getattr(G, "barrier", None)
            if gate_fn:
                qc.add_gate(gate_fn, *(q[idx] for idx in o.qubits))
        elif o.name == "reset":
            gate_fn = getattr(G, "reset", None)
            if gate_fn:
                qc.add_gate(gate_fn, q[o.qubits[0]])
        elif o.params:
            # Parameterized gates in QSDK (rx, ry, rz):
            # In QSDK, G.rx(theta) is a factory function that returns a Gate object.
            gate_creator = getattr(G, o.name, None) or getattr(G, o.name.upper(), None)
            if gate_creator is None:
                raise ValueError(f"Parameterized gate '{o.name}' not found in qniverse.gates")
            
            # If qc has a direct method, try it first (e.g. qc.rx(theta, q))
            direct_method = getattr(qc, o.name, None) or getattr(qc, o.name.lower(), None)
            if callable(direct_method):
                try:
                    direct_method(*o.params, *(q[idx] for idx in o.qubits))
                    continue
                except Exception:
                    pass

            if callable(gate_creator):
                gate_obj = gate_creator(*o.params)
            else:
                gate_obj = gate_creator
            qc.add_gate(gate_obj, *(q[idx] for idx in o.qubits))
        else:
            gate_val = getattr(G, o.name, None) or getattr(G, o.name.upper(), None)
            if gate_val is None:
                raise ValueError(f"Standard gate '{o.name}' not found in qniverse.gates")
            
            # If qc has a direct method, try it first (e.g. qc.h(q))
            direct_method = getattr(qc, o.name, None) or getattr(qc, o.name.lower(), None)
            if callable(direct_method):
                try:
                    direct_method(*(q[idx] for idx in o.qubits))
                    continue
                except Exception:
                    pass

            if callable(gate_val):
                try:
                    gate_obj = gate_val()
                except TypeError:
                    gate_obj = gate_val
            else:
                gate_obj = gate_val
            qc.add_gate(gate_obj, *(q[idx] for idx in o.qubits))

    return qc


# ------------------------------------------------ Top-Level Convert API
def convert_qasm_to_qniverse(qasm_str: str, version: Optional[str] = None) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Main Converter Function for QC-C2-04.
    Accepts an OpenQASM 2.0 or 3.0 source string.
    Returns (QniverseCircuit_object, conversion_report_dict).
    """
    converter = QasmConverter()
    ops, meta = converter.parse(qasm_str, override_version=version)

    # Build gate count summary
    gate_counts = {}
    for o in ops:
        gate_counts[o.name] = gate_counts.get(o.name, 0) + 1

    report = {
        "status": "OK" if not meta["unsupported"] else "FAILED",
        "version_detected": meta["version"],
        "qubits": meta["total_qubits"],
        "classical_bits": meta["total_cbits"],
        "total_operations": len(ops),
        "mapped_operations": gate_counts,
        "warnings": meta["warnings"],
        "unsupported_statements": meta["unsupported"]
    }

    if meta["unsupported"]:
        report["status"] = "FAILED: unsupported or malformed statements detected"
        return None, report

    circuit = build_qniverse_circuit(ops, meta["total_qubits"], meta["total_cbits"])
    return circuit, report


# ------------------------------------------------ Mathematical Verifier
_I = np.eye(2)
_H = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
_X = np.array([[0, 1], [1, 0]])
_Y = np.array([[0, -1j], [1j, 0]])
_Z = np.diag([1, -1])
_S = np.diag([1, 1j])
_T = np.diag([1, np.exp(1j * np.pi / 4)])


def _matrix_for_gate(name: str, params: Tuple[float, ...]) -> np.ndarray:
    if name == "id": return _I
    if name == "x": return _X
    if name == "y": return _Y
    if name == "z": return _Z
    if name == "h": return _H
    if name == "s": return _S
    if name == "sdg": return _S.conj().T
    if name == "t": return _T
    if name == "tdg": return _T.conj().T
    if name == "rx":
        theta = params[0]
        return np.array([[np.cos(theta / 2), -1j * np.sin(theta / 2)],
                         [-1j * np.sin(theta / 2), np.cos(theta / 2)]])
    if name == "rz":
        phi = params[0]
        return np.diag([np.exp(-1j * phi / 2), np.exp(1j * phi / 2)])
    raise ValueError(f"No verification matrix defined for '{name}'")


def compute_qasm_unitary(ops: List[QasmOp], n: int) -> np.ndarray:
    """Computes total 2^n x 2^n unitary matrix for non-measurement operations."""
    dim = 2 ** n
    u = np.eye(dim, dtype=complex)
    for o in ops:
        if o.name in {"measure", "reset", "barrier"}:
            continue
        m = np.zeros((dim, dim), dtype=complex)
        for col in range(dim):
            bits = [(col >> (n - 1 - k)) & 1 for k in range(n)]
            if len(o.qubits) == 1:
                gmat = _matrix_for_gate(o.name, o.params)
                q = o.qubits[0]
                for b in (0, 1):
                    amp = gmat[b, bits[q]]
                    if amp != 0:
                        nb = bits.copy(); nb[q] = b
                        m[int("".join(map(str, nb)), 2), col] += amp
            elif o.name == "cx":
                nb = bits.copy()
                if bits[o.qubits[0]]: nb[o.qubits[1]] ^= 1
                m[int("".join(map(str, nb)), 2), col] += 1
            elif o.name == "cz":
                phase = -1 if (bits[o.qubits[0]] and bits[o.qubits[1]]) else 1
                m[col, col] += phase
            elif o.name == "swap":
                nb = bits.copy()
                a, b = o.qubits; nb[a], nb[b] = bits[b], bits[a]
                m[int("".join(map(str, nb)), 2), col] += 1
            else:
                continue
        u = m @ u
    return u


def equal_up_to_phase(a: np.ndarray, b: np.ndarray, tol=1e-8) -> bool:
    """Verifies matrix equivalence up to physically unmeasurable global phase."""
    idx = np.unravel_index(np.argmax(np.abs(a)), a.shape)
    if abs(b[idx]) < tol:
        return False
    phase = a[idx] / b[idx]
    return np.allclose(a, phase * b, atol=tol)


# ------------------------------------------------ Self-Test Suite
def run_all_tests():
    print("--- Running QC-C2-04 Converter Test Suite ---")

    # Test 1: OpenQASM 2.0 Bell State
    qasm_2 = """
    OPENQASM 2.0;
    include "qelib1.inc";
    qreg q[2];
    creg c[2];
    h q[0];
    cx q[0], q[1];
    barrier q[0], q[1];
    measure q[0] -> c[0];
    """
    circ, rep = convert_qasm_to_qniverse(qasm_2)
    assert rep["status"] == "OK"
    assert rep["version_detected"] == "2.0"
    assert rep["qubits"] == 2 and rep["classical_bits"] == 2
    assert rep["mapped_operations"]["h"] == 1
    assert rep["mapped_operations"]["cx"] == 1
    assert circ is not None
    print("[PASS] Test 1: OpenQASM 2.0 Bell State conversion verified.")

    # Test 2: OpenQASM 3.0 Modern Syntax
    qasm_3 = """
    OPENQASM 3.0;
    qubit[3] q;
    bit[3] c;
    h q[0];
    cz q[0], q[1];
    swap q[1], q[2];
    c[0] = measure q[0];
    """
    circ3, rep3 = convert_qasm_to_qniverse(qasm_3)
    assert rep3["status"] == "OK"
    assert rep3["version_detected"] == "3.0"
    assert rep3["qubits"] == 3 and rep3["classical_bits"] == 3
    assert rep3["mapped_operations"]["swap"] == 1
    assert circ3 is not None
    print("[PASS] Test 2: OpenQASM 3.0 Modern Syntax conversion verified.")

    # Test 3: Parameterized Gates & Angle Expressions (pi/2, 1.570796)
    qasm_param = """
    OPENQASM 2.0;
    qreg q[1];
    rx(pi/2) q[0];
    rz(pi) q[0];
    """
    circ_p, rep_p = convert_qasm_to_qniverse(qasm_param)
    assert rep_p["status"] == "OK"
    assert rep_p["mapped_operations"]["rx"] == 1
    assert rep_p["mapped_operations"]["rz"] == 1
    print("[PASS] Test 3: Parameterized rotations with pi math verified.")

    # Test 4: Diagnostic Safety & Unsupported Gate Rejection
    qasm_bad = """
    OPENQASM 2.0;
    qreg q[2];
    magic_gate q[0];
    while(c == 0) { h q[0]; }
    """
    circ_bad, rep_bad = convert_qasm_to_qniverse(qasm_bad)
    assert circ_bad is None
    assert "FAILED" in rep_bad["status"]
    assert len(rep_bad["unsupported_statements"]) == 2
    assert rep_bad["unsupported_statements"][0]["statement"] == "magic_gate q[0]"
    print("[PASS] Test 4: Explicit diagnostics and rejection of unsupported features verified.")

    # Test 5: Semantic Unitary Equivalence Verification
    # Compare Bell state QASM matrix with manual Bell state matrix
    bell_qasm = """
    OPENQASM 2.0;
    qreg q[2];
    h q[0];
    cx q[0], q[1];
    """
    converter = QasmConverter()
    ops, _ = converter.parse(bell_qasm)
    u_computed = compute_qasm_unitary(ops, 2)
    # Expected Bell unitary matrix
    u_expected = np.array([
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 1, 0, -1],
        [1, 0, -1, 0]
    ]) / np.sqrt(2)
    assert equal_up_to_phase(u_computed, u_expected)
    print("[PASS] Test 5: Semantic unitary equivalence verified up to global phase.")

    print("\n--- ALL QC-C2-04 CONVERTER TESTS PASSED SUCCESSFULLY! ---")


if __name__ == "__main__":
    run_all_tests()
    # Sample run demo
    sample = """
    OPENQASM 3.0;
    qubit[2] q;
    bit[2] c;
    h q[0];
    cx q[0], q[1];
    c[0] = measure q[0];
    """
    circ, report = convert_qasm_to_qniverse(sample)
    import json
    print("\nGenerated Conversion Report:")
    print(json.dumps(report, indent=2))
