# ==============================================================================
# QC-C2-04: OpenQASM 2.0 / 3.0 to QniverseCircuit Converter
# PESU - C-DAC Quantum Hackathon 2026 | Team Eigen
# Version: 2.0 (Jupyter-safe, no triple-quoted module docstrings)
# ==============================================================================

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


def _safe_eval_angle(expr: str) -> float:
    # Safely evaluate angle expressions like "pi/2", "3*pi/4", "1.57"
    expr = expr.strip()
    expr = re.sub(r"\bpi\b", str(math.pi), expr)
    expr = expr.replace("π", str(math.pi))
    if not re.match(r"^[\d\.\s\+\-\*\/\(\)]+$", expr):
        raise ValueError(f"Invalid angle expression: '{expr}'")
    return float(eval(expr, {"__builtins__": {}}, {}))


class QasmConverter:
    # Universal Parser and Converter for OpenQASM 2.0 and 3.0

    STANDARD_1Q_GATES = {
        "id", "x", "y", "z", "h", "s", "sdg", "t", "tdg", "sx", "sxdg"
    }
    STANDARD_2Q_GATES = {"cx", "cnot", "cz", "swap", "ch"}
    STANDARD_3Q_GATES = {"ccx", "toffoli"}
    PARAM_GATES = {"rx", "ry", "rz", "p", "u1", "u2", "u3", "cp", "crz"}

    ALL_KNOWN_GATES = (
        STANDARD_1Q_GATES | STANDARD_2Q_GATES | STANDARD_3Q_GATES | PARAM_GATES
    )

    _GATE_QUBIT_COUNT = {
        **{g: 1 for g in STANDARD_1Q_GATES | PARAM_GATES},
        **{g: 2 for g in STANDARD_2Q_GATES},
        "ccx": 3, "toffoli": 3,
        "u2": 1, "u3": 1, "cp": 2, "crz": 2,
    }

    def _detect_version(self, source: str) -> str:
        for line in source.splitlines():
            line = line.strip()
            if line.startswith("OPENQASM"):
                m = re.search(r"OPENQASM\s+([\d]+\.[\d]+)", line)
                if m:
                    ver = m.group(1)
                    if ver.startswith("2"):
                        return "2.0"
                    if ver.startswith("3"):
                        return "3.0"
        return "2.0"

    def _strip_comments(self, source: str) -> str:
        lines = []
        for line in source.splitlines():
            idx = line.find("//")
            if idx != -1:
                line = line[:idx]
            lines.append(line)
        return "\n".join(lines)

    def _parse_registers_v2(self, source: str) -> Tuple[Dict[str, int], Dict[str, int]]:
        qregs, cregs = {}, {}
        for m in re.finditer(r"qreg\s+(\w+)\s*\[(\d+)\]\s*;", source):
            qregs[m.group(1)] = int(m.group(2))
        for m in re.finditer(r"creg\s+(\w+)\s*\[(\d+)\]\s*;", source):
            cregs[m.group(1)] = int(m.group(2))
        return qregs, cregs

    def _parse_registers_v3(self, source: str) -> Tuple[Dict[str, int], Dict[str, int]]:
        qregs, cregs = {}, {}
        # Must match "qubit[N] name;" but NOT "bit[N] name;" — use \bqubit\b anchor
        for m in re.finditer(r"\bqubit\s*\[\s*(\d+)\s*\]\s+(\w+)\s*;", source):
            qregs[m.group(2)] = int(m.group(1))
        # Must match "bit[N] name;" but NOT "qubit[N] name;" — use (?<!\w) negative lookbehind
        for m in re.finditer(r"(?<!\w)bit\s*\[\s*(\d+)\s*\]\s+(\w+)\s*;", source):
            cregs[m.group(2)] = int(m.group(1))
        return qregs, cregs

    def _resolve_qubit(self, reg_name: str, idx: int,
                       qregs: Dict[str, int], offset_map: Dict[str, int]) -> int:
        if reg_name not in qregs:
            raise ValueError(f"Undeclared quantum register: '{reg_name}'")
        reg_size = qregs[reg_name]
        if idx < 0 or idx >= reg_size:
            raise ValueError(
                f"Qubit index {idx} out of bounds for register '{reg_name}[{reg_size}]'"
            )
        return offset_map[reg_name] + idx

    def _resolve_cbit(self, reg_name: str, idx: int,
                      cregs: Dict[str, int], coffset_map: Dict[str, int]) -> int:
        if reg_name not in cregs:
            raise ValueError(f"Undeclared classical register: '{reg_name}'")
        reg_size = cregs[reg_name]
        if idx < 0 or idx >= reg_size:
            raise ValueError(
                f"Classical bit index {idx} out of bounds for register '{reg_name}[{reg_size}]'"
            )
        return coffset_map[reg_name] + idx

    def _build_offset_maps(self, regs: Dict[str, int]) -> Dict[str, int]:
        offset_map = {}
        total = 0
        for name, size in regs.items():
            offset_map[name] = total
            total += size
        return offset_map

    def _parse_gate_args(self, args_str: str, qregs: Dict[str, int],
                         offset_map: Dict[str, int]) -> Tuple[int, ...]:
        qubits = []
        for token in args_str.split(","):
            token = token.strip()
            m = re.match(r"(\w+)\[(\d+)\]", token)
            if not m:
                raise ValueError(f"Cannot parse qubit argument: '{token}'")
            qubits.append(self._resolve_qubit(m.group(1), int(m.group(2)), qregs, offset_map))
        return tuple(qubits)

    def _parse_statements(self, source: str, version: str,
                           qregs: Dict[str, int], cregs: Dict[str, int],
                           offset_map: Dict[str, int], coffset_map: Dict[str, int]
                           ) -> Tuple[List[QasmOp], List[str], List[Dict]]:
        ops = []
        warnings = []
        unsupported = []
        line_no = 0

        # Remove register declarations and version headers for statement parsing
        skip_patterns = [
            r"^OPENQASM\s+[\d\.]+\s*;?",
            r"^include\s+\"[^\"]+\"\s*;",
            r"^qreg\s+\w+\s*\[\d+\]\s*;",
            r"^creg\s+\w+\s*\[\d+\]\s*;",
            r"^\bqubit\b\s*\[\d+\]\s+\w+\s*;",
            r"^(?<!\w)bit\s*\[\d+\]\s+\w+\s*;",
        ]

        for raw_line in source.splitlines():
            line_no += 1
            stmt = raw_line.strip().rstrip(";")
            if not stmt:
                continue
            if any(re.match(p, stmt + ";") for p in skip_patterns):
                continue

            # Barrier
            m = re.match(r"barrier\s+(.+)", stmt)
            if m:
                try:
                    q_args = self._parse_gate_args(m.group(1), qregs, offset_map)
                    ops.append(QasmOp("barrier", q_args, line_no=line_no))
                except ValueError as e:
                    unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                continue

            # Reset
            m = re.match(r"reset\s+(\w+)\[(\d+)\]", stmt)
            if m:
                try:
                    q = self._resolve_qubit(m.group(1), int(m.group(2)), qregs, offset_map)
                    ops.append(QasmOp("reset", (q,), line_no=line_no))
                except ValueError as e:
                    unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                continue

            # Measure v2: measure q[i] -> c[j]
            m = re.match(r"measure\s+(\w+)\[(\d+)\]\s*->\s*(\w+)\[(\d+)\]", stmt)
            if m:
                try:
                    q = self._resolve_qubit(m.group(1), int(m.group(2)), qregs, offset_map)
                    c = self._resolve_cbit(m.group(3), int(m.group(4)), cregs, coffset_map)
                    ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                except ValueError as e:
                    unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                continue

            # Measure v3: c[j] = measure q[i]
            m = re.match(r"(\w+)\[(\d+)\]\s*=\s*measure\s+(\w+)\[(\d+)\]", stmt)
            if m:
                try:
                    c = self._resolve_cbit(m.group(1), int(m.group(2)), cregs, coffset_map)
                    q = self._resolve_qubit(m.group(3), int(m.group(4)), qregs, offset_map)
                    ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                except ValueError as e:
                    unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                continue

            # Parameterized gate: rx(theta) q[i]
            m = re.match(r"(\w+)\(([^)]+)\)\s+(.+)", stmt)
            if m:
                gate_name = m.group(1).lower()
                param_str = m.group(2)
                args_str = m.group(3)
                if gate_name in self.ALL_KNOWN_GATES or gate_name in self.PARAM_GATES:
                    try:
                        params = tuple(_safe_eval_angle(p) for p in param_str.split(","))
                        q_args = self._parse_gate_args(args_str, qregs, offset_map)
                        ops.append(QasmOp(gate_name, q_args, params=params, line_no=line_no))
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                else:
                    unsupported.append({
                        "line": line_no,
                        "statement": stmt,
                        "reason": f"Unknown parameterized gate '{gate_name}'"
                    })
                continue

            # Standard gate: h q[0] or cx q[0], q[1]
            m = re.match(r"(\w+)\s+(.+)", stmt)
            if m:
                gate_name = m.group(1).lower()
                args_str = m.group(2)
                if gate_name in self.ALL_KNOWN_GATES:
                    try:
                        q_args = self._parse_gate_args(args_str, qregs, offset_map)
                        ops.append(QasmOp(gate_name, q_args, line_no=line_no))
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                else:
                    unsupported.append({
                        "line": line_no,
                        "statement": stmt,
                        "reason": f"Unknown or unsupported gate/statement '{gate_name}'"
                    })
                continue

            # Anything else not matched
            if stmt:
                unsupported.append({
                    "line": line_no,
                    "statement": stmt,
                    "reason": "Unrecognized statement"
                })

        return ops, warnings, unsupported

    def parse(self, source: str, override_version: Optional[str] = None):
        source = self._strip_comments(source)
        version = override_version or self._detect_version(source)

        if version.startswith("2"):
            qregs, cregs = self._parse_registers_v2(source)
        else:
            qregs, cregs = self._parse_registers_v3(source)

        offset_map = self._build_offset_maps(qregs)
        coffset_map = self._build_offset_maps(cregs)

        total_qubits = sum(qregs.values())
        total_cbits = sum(cregs.values())

        ops, warnings, unsupported = self._parse_statements(
            source, version, qregs, cregs, offset_map, coffset_map
        )

        meta = {
            "version": version,
            "qregs": qregs,
            "cregs": cregs,
            "total_qubits": total_qubits,
            "total_cbits": total_cbits,
            "warnings": warnings,
            "unsupported": unsupported,
        }
        return ops, meta


# ------------------------------------------------ QSDK Circuit Builder
def build_qniverse_circuit(ops: List[QasmOp], num_qubits: int, num_cbits: int):
    # Builds QniverseCircuit; falls back to MockQniverseCircuit if SDK unavailable
    try:
        from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
        import qniverse.gates as G
        has_real_sdk = True
    except ImportError:
        has_real_sdk = False

    if not has_real_sdk:
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

    # ---- Official Qniverse SDK Construction ----
    qc = QniverseCircuit()
    q = QuantumRegister(num_qubits, "q")
    qc.add_register(q)
    c = None
    if num_cbits > 0:
        c = ClassicalRegister(num_cbits, "c")
        qc.add_register(c)

    for o in ops:
        if o.name == "measure":
            qc.add_gate(G.measure, q[o.qubits[0]], c[o.cbits[0]])

        elif o.name == "barrier":
            gate_fn = getattr(G, "barrier", None)
            if gate_fn:
                qc.add_gate(gate_fn, *(q[idx] for idx in o.qubits))

        elif o.name == "reset":
            gate_fn = getattr(G, "reset", None)
            if gate_fn:
                qc.add_gate(gate_fn, q[o.qubits[0]])

        elif o.params:
            # Parameterized gates (rx, ry, rz, etc.)
            # KEY FIX: G.rx is a FACTORY FUNCTION. Must call G.rx(theta) FIRST to get a Gate object.
            # WRONG: qc.add_gate(G.rx, theta, q[0])   <-- causes "Name conflict" ValueError
            # RIGHT: gate_obj = G.rx(theta); qc.add_gate(gate_obj, q[0])
            gate_creator = getattr(G, o.name, None) or getattr(G, o.name.upper(), None)
            if gate_creator is None:
                raise ValueError(f"Parameterized gate '{o.name}' not found in qniverse.gates")

            # Try qc.rx(theta, q[0]) direct method first
            direct_method = getattr(qc, o.name, None) or getattr(qc, o.name.lower(), None)
            if callable(direct_method):
                try:
                    direct_method(*o.params, *(q[idx] for idx in o.qubits))
                    continue
                except Exception:
                    pass  # Fall through to factory method

            # Factory method: G.rx(theta) → Gate object → add_gate
            if callable(gate_creator):
                gate_obj = gate_creator(*o.params)
            else:
                gate_obj = gate_creator
            qc.add_gate(gate_obj, *(q[idx] for idx in o.qubits))

        else:
            # Standard non-parameterized gates (h, cx, cz, swap, etc.)
            gate_val = getattr(G, o.name, None) or getattr(G, o.name.upper(), None)
            if gate_val is None:
                raise ValueError(f"Standard gate '{o.name}' not found in qniverse.gates")

            # Try qc.h(q[0]) direct method first
            direct_method = getattr(qc, o.name, None) or getattr(qc, o.name.lower(), None)
            if callable(direct_method):
                try:
                    direct_method(*(q[idx] for idx in o.qubits))
                    continue
                except Exception:
                    pass  # Fall through to add_gate

            # G.h is a static Gate object, pass directly
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
    # Main entry point: accepts QASM string, returns (QniverseCircuit, report_dict)
    converter = QasmConverter()
    ops, meta = converter.parse(qasm_str, override_version=version)

    gate_counts: Dict[str, int] = {}
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
    raise ValueError(f"No verification matrix for '{name}'")


def compute_qasm_unitary(ops: List[QasmOp], n: int) -> np.ndarray:
    # Computes the full 2^n unitary from non-measurement operations
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


def equal_up_to_phase(a: np.ndarray, b: np.ndarray, tol: float = 1e-8) -> bool:
    # Returns True if two matrices are equal up to a global phase factor
    idx = np.unravel_index(np.argmax(np.abs(a)), a.shape)
    if abs(b[idx]) < tol:
        return False
    phase = a[idx] / b[idx]
    return np.allclose(a, phase * b, atol=tol)


# ------------------------------------------------ Self-Test Suite
def run_all_tests():
    print("--- Running QC-C2-04 Converter Test Suite ---")

    # Test 1: OpenQASM 2.0 Bell State
    qasm_2 = (
        "OPENQASM 2.0;\n"
        'include "qelib1.inc";\n'
        "qreg q[2];\n"
        "creg c[2];\n"
        "h q[0];\n"
        "cx q[0], q[1];\n"
        "barrier q[0], q[1];\n"
        "measure q[0] -> c[0];\n"
    )
    circ, rep = convert_qasm_to_qniverse(qasm_2)
    assert rep["status"] == "OK", f"Test 1 failed: {rep}"
    assert rep["version_detected"] == "2.0"
    assert rep["qubits"] == 2 and rep["classical_bits"] == 2
    assert rep["mapped_operations"]["h"] == 1
    assert rep["mapped_operations"]["cx"] == 1
    assert circ is not None
    print("[PASS] Test 1: OpenQASM 2.0 Bell State conversion verified.")

    # Test 2: OpenQASM 3.0 Modern Syntax
    qasm_3 = (
        "OPENQASM 3.0;\n"
        "qubit[3] q;\n"
        "bit[3] c;\n"
        "h q[0];\n"
        "cz q[0], q[1];\n"
        "swap q[1], q[2];\n"
        "c[0] = measure q[0];\n"
    )
    circ3, rep3 = convert_qasm_to_qniverse(qasm_3)
    assert rep3["status"] == "OK", f"Test 2 failed: {rep3}"
    assert rep3["version_detected"] == "3.0"
    assert rep3["qubits"] == 3 and rep3["classical_bits"] == 3
    assert rep3["mapped_operations"]["swap"] == 1
    assert circ3 is not None
    print("[PASS] Test 2: OpenQASM 3.0 Modern Syntax conversion verified.")

    # Test 3: Parameterized Gates & Angle Expressions (pi/2, pi)
    qasm_param = (
        "OPENQASM 2.0;\n"
        "qreg q[1];\n"
        "rx(pi/2) q[0];\n"
        "rz(pi) q[0];\n"
    )
    circ_p, rep_p = convert_qasm_to_qniverse(qasm_param)
    assert rep_p["status"] == "OK", f"Test 3 failed: {rep_p}"
    assert rep_p["mapped_operations"]["rx"] == 1
    assert rep_p["mapped_operations"]["rz"] == 1
    print("[PASS] Test 3: Parameterized rotations with pi math verified.")

    # Test 4: Diagnostic Safety & Unsupported Gate Rejection
    qasm_bad = (
        "OPENQASM 2.0;\n"
        "qreg q[2];\n"
        "magic_gate q[0];\n"
        "while(c == 0) { h q[0]; }\n"
    )
    circ_bad, rep_bad = convert_qasm_to_qniverse(qasm_bad)
    assert circ_bad is None
    assert "FAILED" in rep_bad["status"]
    assert len(rep_bad["unsupported_statements"]) == 2
    assert rep_bad["unsupported_statements"][0]["statement"] == "magic_gate q[0]"
    print("[PASS] Test 4: Explicit diagnostics and rejection of unsupported features verified.")

    # Test 5: Semantic Unitary Equivalence Verification (Bell state matrix)
    bell_qasm = (
        "OPENQASM 2.0;\n"
        "qreg q[2];\n"
        "h q[0];\n"
        "cx q[0], q[1];\n"
    )
    conv = QasmConverter()
    ops, _ = conv.parse(bell_qasm)
    u_computed = compute_qasm_unitary(ops, 2)
    u_expected = np.array([
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 1, 0, -1],
        [1, 0, -1, 0]
    ]) / np.sqrt(2)
    assert equal_up_to_phase(u_computed, u_expected), "Test 5 unitary mismatch"
    print("[PASS] Test 5: Semantic unitary equivalence verified up to global phase.")

    print("\n--- ALL QC-C2-04 CONVERTER TESTS PASSED SUCCESSFULLY! ---")


if __name__ == "__main__":
    run_all_tests()
    sample = (
        "OPENQASM 3.0;\n"
        "qubit[2] q;\n"
        "bit[2] c;\n"
        "h q[0];\n"
        "cx q[0], q[1];\n"
        "c[0] = measure q[0];\n"
    )
    circ, report = convert_qasm_to_qniverse(sample)
    import json
    print("\nGenerated Conversion Report:")
    print(json.dumps(report, indent=2))
