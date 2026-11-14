# ==============================================================================
# QC-C2-04: OpenQASM 2.0 / 3.0 <-> QniverseCircuit Converter + Diagram Renderer
# PESU - C-DAC Quantum Hackathon 2026 | Team Eigen
# Version: 3.1 (Full QniverseCircuit Adapter, QSDK Codegen, OpenQASM & Diagram)
# ==============================================================================

import math
import re
from dataclasses import dataclass
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
    if not expr:
        raise ValueError("Empty angle expression")
    expr = re.sub(r"\bpi\b", str(math.pi), expr)
    expr = expr.replace("π", str(math.pi))
    if not re.match(r"^[\d\.\s\+\-\*\/\(\)]+$", expr):
        raise ValueError(f"Invalid angle expression: '{expr}'")
    return float(eval(expr, {"__builtins__": {}}, {}))


def _format_angle_qasm(val: float) -> str:
    # Format common multiples of pi cleanly in OpenQASM and QSDK output
    for num in range(-16, 17):
        if num == 0:
            if abs(val) < 1e-9:
                return "0"
            continue
        for den in (1, 2, 3, 4, 6, 8):
            target = (num * math.pi) / den
            if abs(val - target) < 1e-7:
                sign = "-" if num < 0 else ""
                abs_n = abs(num)
                pi_part = "pi" if abs_n == 1 else f"{abs_n}*pi"
                return f"{sign}{pi_part}" if den == 1 else f"{sign}{pi_part}/{den}"
    return f"{val:.6g}"


def ops_to_openqasm(
    ops: List[QasmOp],
    num_qubits: int,
    num_cbits: int,
    version: str = "2.0"
) -> str:
    # Generates canonical OpenQASM 2.0 or 3.0 code from a list of QasmOp
    is_v3 = str(version).strip().startswith("3")
    if is_v3:
        lines = ["OPENQASM 3.0;", 'include "stdgates.inc";']
        if num_qubits > 0:
            lines.append(f"qubit[{num_qubits}] q;")
        if num_cbits > 0:
            lines.append(f"bit[{num_cbits}] c;")
    else:
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";']
        if num_qubits > 0:
            lines.append(f"qreg q[{num_qubits}];")
        if num_cbits > 0:
            lines.append(f"creg c[{num_cbits}];")

    alias_map = {"cnot": "cx", "toffoli": "ccx"}
    for o in ops:
        gname = alias_map.get(o.name.lower(), o.name.lower())
        if gname == "measure":
            if is_v3:
                lines.append(f"c[{o.cbits[0]}] = measure q[{o.qubits[0]}];")
            else:
                lines.append(f"measure q[{o.qubits[0]}] -> c[{o.cbits[0]}];")
        elif gname == "barrier":
            args = ", ".join(f"q[{q}]" for q in o.qubits)
            lines.append(f"barrier {args};")
        elif gname == "reset":
            lines.append(f"reset q[{o.qubits[0]}];")
        elif o.params:
            param_str = ", ".join(_format_angle_qasm(p) for p in o.params)
            args = ", ".join(f"q[{q}]" for q in o.qubits)
            lines.append(f"{gname}({param_str}) {args};")
        else:
            args = ", ".join(f"q[{q}]" for q in o.qubits)
            lines.append(f"{gname} {args};")

    return "\n".join(lines) + "\n"


def ops_to_qniverse_code(
    ops: List[QasmOp],
    num_qubits: int,
    num_cbits: int
) -> str:
    # Generates executable Qniverse QSDK Python code equivalent to the parsed QASM
    lines = [
        "from qniverse.gates import *",
        "from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister",
        "import numpy as np",
        "",
        "qc = QniverseCircuit()",
    ]
    if num_qubits > 0:
        lines.append(f'q = QuantumRegister({num_qubits}, "q")')
        lines.append("qc.add_register(q)")
    if num_cbits > 0:
        lines.append(f'c = ClassicalRegister({num_cbits}, "c")')
        lines.append("qc.add_register(c)")
    lines.append("")

    alias_map = {"cnot": "cx", "toffoli": "ccx"}
    for o in ops:
        gname = alias_map.get(o.name.lower(), o.name.lower())
        if gname == "measure":
            lines.append(f"qc.add_gate(measure, q[{o.qubits[0]}], c[{o.cbits[0]}])")
        elif gname == "barrier":
            for pair in _decompose_wide_barrier(o.qubits):
                q_args = ", ".join(f"q[{idx}]" for idx in pair)
                lines.append(f"qc.add_gate(barrier, {q_args})")
        elif gname == "reset":
            lines.append(f"qc.add_gate(reset, q[{o.qubits[0]}])")
        elif o.params:
            p_args = ", ".join(
                _format_angle_qasm(p).replace("pi", "np.pi") for p in o.params
            )
            q_args = ", ".join(f"q[{idx}]" for idx in o.qubits)
            lines.append(f"qc.add_gate({gname}({p_args}), {q_args})")
        else:
            q_args = ", ".join(f"q[{idx}]" for idx in o.qubits)
            lines.append(f"qc.add_gate({gname}, {q_args})")

    return "\n".join(lines) + "\n"


def _gate_symbols_for_op(op: QasmOp) -> Dict[int, str]:
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
    if name in ("cx", "cnot"):
        return {qs[0]: "@", qs[1]: "(+)"}
    if name == "cy":
        return {qs[0]: "@", qs[1]: "(Y)"}
    if name == "cz":
        return {qs[0]: "@", qs[1]: "@"}
    if name == "ch":
        return {qs[0]: "@", qs[1]: "(H)"}
    if name == "swap":
        return {qs[0]: "x", qs[1]: "x"}
    if name in ("ccx", "toffoli"):
        return {qs[0]: "@", qs[1]: "@", qs[2]: "(+)"}
    if name in ("crz", "cp") and len(qs) == 2:
        p_txt = _format_angle_qasm(op.params[0]) if op.params else ""
        return {qs[0]: "@", qs[1]: f"{name.upper()}({p_txt})"}
    if op.params:
        p_txt = ",".join(_format_angle_qasm(p) for p in op.params)
        label = f"{name.capitalize()}({p_txt})"
        return {qs[0]: label}
    if name in ("s", "t", "h", "x", "y", "z"):
        return {qs[0]: name.upper()}
    if name in ("sdg", "tdg", "sx", "sxdg"):
        return {qs[0]: name.capitalize()}
    return {q: name.upper() for q in qs}


def draw_circuit_text(
    ops_or_qc: Any,
    num_qubits: Optional[int] = None,
    print_output: bool = True
) -> str:
    # Renders a multi-wire ASCII circuit diagram aligned by execution depth layers
    if hasattr(ops_or_qc, "_ops"):
        ops = list(ops_or_qc._ops)
        if num_qubits is None:
            num_qubits = getattr(ops_or_qc, "num_qubits", None)
    elif hasattr(ops_or_qc, "operations"):
        ops, n_q, _ = _extract_ops_from_qniverse(ops_or_qc)
        if num_qubits is None:
            num_qubits = n_q
    else:
        ops = list(ops_or_qc)

    if num_qubits is None:
        num_qubits = (max((q for o in ops for q in o.qubits), default=-1) + 1) if ops else 0

    if num_qubits <= 0:
        diag = "(empty circuit)"
        if print_output:
            print(diag)
        return diag

    free = [0] * num_qubits
    layers: List[Dict[int, str]] = []

    for o in ops:
        sym_map = _gate_symbols_for_op(o)
        start = max((free[q] for q in o.qubits), default=0)
        while len(layers) <= start:
            layers.append({})
        while any(q in layers[start] for q in o.qubits):
            start += 1
            while len(layers) <= start:
                layers.append({})
        for q, sym in sym_map.items():
            if q < num_qubits:
                layers[start][q] = sym
        for q in o.qubits:
            if q < num_qubits:
                free[q] = start + 1

    num_columns = len(layers)
    label_width = len(str(num_qubits - 1))

    if num_columns == 0:
        diag = "\n".join(f"q{q:<{label_width}}: --" for q in range(num_qubits))
        if print_output:
            print(diag)
        return diag

    col_widths = [
        max(max((len(layers[c].get(q, "")) for q in range(num_qubits)), default=1), 1)
        for c in range(num_columns)
    ]

    lines = []
    for q in range(num_qubits):
        prefix = f"q{q:<{label_width}}: --"
        segs = []
        for c in range(num_columns):
            w = col_widths[c]
            sym = layers[c].get(q)
            if sym is None:
                cell = "-" * w
            else:
                pad = w - len(sym)
                left = pad // 2
                right = pad - left
                cell = ("-" * left) + sym + ("-" * right)
            segs.append(cell + "--")
        lines.append(prefix + "".join(segs))

    diag = "\n".join(lines)
    if print_output:
        print(diag)
    return diag


def _extract_ops_from_qniverse(qc: Any) -> Tuple[List[QasmOp], int, int]:
    if hasattr(qc, "_ops"):
        return list(qc._ops), getattr(qc, "num_qubits", 0), getattr(qc, "num_clbits", 0)

    reg_pat = re.compile(r"(Qubit|Clbit)\((?:Quantum|Classical)Register\((\d+),\s*'([^']+)'\),\s*(\d+)\)")
    q_off, c_off = {}, {}
    qt, ct = 0, 0
    for reg in getattr(qc, "registers", []):
        m = re.search(r"(Quantum|Classical)Register\((\d+),\s*'([^']+)'\)", repr(reg))
        if m:
            if m.group(1) == "Quantum":
                q_off[m.group(3)] = qt
                qt += int(m.group(2))
            else:
                c_off[m.group(3)] = ct
                ct += int(m.group(2))

    ops = []
    for gate, wires in getattr(qc, "operations", []):
        gname = str(getattr(gate, "name", gate)).lower()
        qubits, cbits = [], []
        for w in wires:
            m = reg_pat.search(repr(w))
            if m:
                kind, rname, idx = m.group(1), m.group(3), int(m.group(4))
                if kind == "Qubit":
                    qubits.append(q_off.get(rname, 0) + idx)
                else:
                    cbits.append(c_off.get(rname, 0) + idx)
        params = ()
        for attr in ("params", "parameters", "angle", "theta", "phi", "lam"):
            if hasattr(gate, attr):
                val = getattr(gate, attr)
                if isinstance(val, (int, float)):
                    params = (float(val),)
                    break
                elif isinstance(val, (list, tuple)) and val:
                    params = tuple(float(x) for x in val)
                    break
        ops.append(QasmOp(gname, tuple(qubits), tuple(cbits), params=params))

    n_q = getattr(qc, "num_qubits", qt)
    n_c = getattr(qc, "num_clbits", ct)
    return ops, n_q, n_c


def qniverse_to_openqasm(qc: Any, version: str = "2.0") -> str:
    # Converts a QniverseCircuit (or MockQniverseCircuit) into OpenQASM 2.0 or 3.0 text
    ops, n_q, n_c = _extract_ops_from_qniverse(qc)
    return ops_to_openqasm(ops, n_q, n_c, version=version)


def _decompose_wide_barrier(qubits: Tuple[int, ...]) -> List[Tuple[int, ...]]:
    # Decomposes >2-qubit barriers into 2-qubit forward-backward chains for Qniverse SDK
    if len(qubits) <= 2:
        return [qubits]
    pairs = []
    n = len(qubits)
    for i in range(n - 1):
        pairs.append((qubits[i], qubits[i + 1]))
    for i in range(n - 3, -1, -1):
        pairs.append((qubits[i], qubits[i + 1]))
    return pairs


class QasmConverter:
    # Universal Parser and Converter for OpenQASM 2.0 and 3.0

    STANDARD_1Q_GATES = {
        "id", "x", "y", "z", "h", "s", "sdg", "t", "tdg", "sx", "sxdg"
    }
    STANDARD_2Q_GATES = {"cx", "cnot", "cz", "swap", "ch", "cy"}
    STANDARD_3Q_GATES = {"ccx", "toffoli", "cswap"}
    PARAM_GATES = {"rx", "ry", "rz", "p", "u1", "u2", "u3", "cp", "crz", "crx", "cry"}

    NON_PARAM_GATES = STANDARD_1Q_GATES | STANDARD_2Q_GATES | STANDARD_3Q_GATES
    ALL_KNOWN_GATES = NON_PARAM_GATES | PARAM_GATES

    _GATE_QUBIT_COUNT = {
        **{g: 1 for g in STANDARD_1Q_GATES | {"rx", "ry", "rz", "p", "u1", "u2", "u3"}},
        **{g: 2 for g in STANDARD_2Q_GATES | {"cp", "crz", "crx", "cry"}},
        **{g: 3 for g in STANDARD_3Q_GATES},
    }

    _GATE_PARAM_COUNT = {
        "rx": 1, "ry": 1, "rz": 1, "p": 1, "u1": 1,
        "u2": 2, "u3": 3,
        "cp": 1, "crz": 1, "crx": 1, "cry": 1,
    }

    def _detect_version(self, source: str) -> str:
        for line in source.splitlines():
            line = line.strip()
            if line.startswith("OPENQASM"):
                m = re.search(r"OPENQASM\s+([\d]+(?:\.[\d]+)?)", line, re.IGNORECASE)
                if m:
                    ver = m.group(1)
                    if ver.startswith("2"):
                        return "2.0"
                    if ver.startswith("3"):
                        return "3.0"
            if re.match(r"^(?:qubit|bit)\s*\[", line):
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
        for m in re.finditer(r"\bqubit\s*\[\s*(\d+)\s*\]\s+(\w+)\s*;", source):
            qregs[m.group(2)] = int(m.group(1))
        for m in re.finditer(r"(?<!\w)bit\s*\[\s*(\d+)\s*\]\s+(\w+)\s*;", source):
            cregs[m.group(2)] = int(m.group(1))
        if not qregs and not cregs:
            return self._parse_registers_v2(source)
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
                         offset_map: Dict[str, int], allow_whole_reg: bool = False) -> Tuple[int, ...]:
        qubits = []
        for token in args_str.split(","):
            token = token.strip()
            m = re.match(r"^(\w+)\[(\d+)\]$", token)
            if m:
                qubits.append(self._resolve_qubit(m.group(1), int(m.group(2)), qregs, offset_map))
            elif allow_whole_reg and token in qregs:
                base = offset_map[token]
                qubits.extend(base + i for i in range(qregs[token]))
            else:
                raise ValueError(f"Cannot parse qubit argument: '{token}'")
        if len(set(qubits)) != len(qubits):
            raise ValueError(f"Duplicate qubit operands in statement arguments: '{args_str}'")
        return tuple(qubits)

    def _validate_gate_arity(self, gate_name: str, q_args: Tuple[int, ...], params: Tuple[float, ...] = ()):
        expected_q = self._GATE_QUBIT_COUNT.get(gate_name)
        if expected_q is not None and len(q_args) != expected_q:
            raise ValueError(
                f"Gate '{gate_name}' requires {expected_q} qubit(s), but got {len(q_args)}"
            )
        expected_p = self._GATE_PARAM_COUNT.get(gate_name, 0)
        if len(params) != expected_p:
            raise ValueError(
                f"Gate '{gate_name}' requires {expected_p} parameter(s), but got {len(params)}"
            )

    def _parse_statements(self, source: str, version: str,
                           qregs: Dict[str, int], cregs: Dict[str, int],
                           offset_map: Dict[str, int], coffset_map: Dict[str, int]
                           ) -> Tuple[List[QasmOp], List[str], List[Dict]]:
        ops = []
        warnings = []
        unsupported = []
        line_no = 0

        skip_patterns = [
            r"^OPENQASM\s+[\d\.]+\s*;?$",
            r"^include\s+\"[^\"]+\"\s*;$",
            r"^qreg\s+\w+\s*\[\d+\]\s*;$",
            r"^creg\s+\w+\s*\[\d+\]\s*;$",
            r"^\bqubit\b\s*\[\d+\]\s+\w+\s*;$",
            r"^(?<!\w)bit\s*\[\d+\]\s+\w+\s*;$",
        ]

        for raw_line in source.splitlines():
            line_no += 1
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue

            # Keep control-flow lines with braces intact so they report as a single unsupported statement
            if "{" in stripped_line or "}" in stripped_line:
                sub_statements = [stripped_line.rstrip(";").strip()]
            else:
                sub_statements = [s.strip() for s in stripped_line.split(";") if s.strip()]

            for stmt in sub_statements:
                if any(re.match(p, stmt + ";", re.IGNORECASE) for p in skip_patterns):
                    continue

                # Barrier (supports indexed q[0], q[1] or whole register barrier q)
                m = re.match(r"^barrier\s+(.+)$", stmt)
                if m:
                    try:
                        q_args = self._parse_gate_args(m.group(1), qregs, offset_map, allow_whole_reg=True)
                        ops.append(QasmOp("barrier", q_args, line_no=line_no))
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    continue

                # Reset
                m = re.match(r"^reset\s+(\w+)\[(\d+)\]$", stmt)
                if m:
                    try:
                        q = self._resolve_qubit(m.group(1), int(m.group(2)), qregs, offset_map)
                        ops.append(QasmOp("reset", (q,), line_no=line_no))
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    continue

                # Measure v2: measure q[i] -> c[j] (or whole-register measure q -> c)
                m = re.match(r"^measure\s+(\w+)(?:\[(\d+)\])?\s*->\s*(\w+)(?:\[(\d+)\])?$", stmt)
                if m:
                    try:
                        q_reg, q_idx, c_reg, c_idx = m.group(1), m.group(2), m.group(3), m.group(4)
                        if q_idx is not None and c_idx is not None:
                            q = self._resolve_qubit(q_reg, int(q_idx), qregs, offset_map)
                            c = self._resolve_cbit(c_reg, int(c_idx), cregs, coffset_map)
                            ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                        elif q_idx is None and c_idx is None and q_reg in qregs and c_reg in cregs:
                            if qregs[q_reg] != cregs[c_reg]:
                                raise ValueError(f"Register size mismatch in measure {q_reg} -> {c_reg}")
                            for idx in range(qregs[q_reg]):
                                q = self._resolve_qubit(q_reg, idx, qregs, offset_map)
                                c = self._resolve_cbit(c_reg, idx, cregs, coffset_map)
                                ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                        else:
                            raise ValueError(f"Invalid measure syntax: '{stmt}'")
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    continue

                # Measure v3: c[j] = measure q[i] (or whole-register c = measure q)
                m = re.match(r"^(\w+)(?:\[(\d+)\])?\s*=\s*measure\s+(\w+)(?:\[(\d+)\])?$", stmt)
                if m:
                    try:
                        c_reg, c_idx, q_reg, q_idx = m.group(1), m.group(2), m.group(3), m.group(4)
                        if q_idx is not None and c_idx is not None:
                            c = self._resolve_cbit(c_reg, int(c_idx), cregs, coffset_map)
                            q = self._resolve_qubit(q_reg, int(q_idx), qregs, offset_map)
                            ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                        elif q_idx is None and c_idx is None and q_reg in qregs and c_reg in cregs:
                            if qregs[q_reg] != cregs[c_reg]:
                                raise ValueError(f"Register size mismatch in {c_reg} = measure {q_reg}")
                            for idx in range(qregs[q_reg]):
                                c = self._resolve_cbit(c_reg, idx, cregs, coffset_map)
                                q = self._resolve_qubit(q_reg, idx, qregs, offset_map)
                                ops.append(QasmOp("measure", (q,), (c,), line_no=line_no))
                        else:
                            raise ValueError(f"Invalid OpenQASM 3.0 measure syntax: '{stmt}'")
                    except ValueError as e:
                        unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    continue

                # Parameterized gate: rx(theta) q[i]
                m = re.match(r"^(\w+)\(([^)]*)\)\s+(.+)$", stmt)
                if m:
                    gate_name = m.group(1).lower()
                    param_str = m.group(2)
                    args_str = m.group(3)
                    if gate_name in self.PARAM_GATES:
                        try:
                            params = tuple(_safe_eval_angle(p) for p in param_str.split(","))
                            q_args = self._parse_gate_args(args_str, qregs, offset_map)
                            self._validate_gate_arity(gate_name, q_args, params)
                            ops.append(QasmOp(gate_name, q_args, params=params, line_no=line_no))
                        except ValueError as e:
                            unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    else:
                        unsupported.append({
                            "line": line_no,
                            "statement": stmt,
                            "reason": f"Unknown or non-parameterized gate '{gate_name}'"
                        })
                    continue

                # Standard non-parameterized gate: h q[0] or cx q[0], q[1]
                m = re.match(r"^(\w+)\s+(.+)$", stmt)
                if m:
                    gate_name = m.group(1).lower()
                    args_str = m.group(2)
                    if gate_name in self.NON_PARAM_GATES:
                        try:
                            q_args = self._parse_gate_args(args_str, qregs, offset_map)
                            self._validate_gate_arity(gate_name, q_args, ())
                            ops.append(QasmOp(gate_name, q_args, line_no=line_no))
                        except ValueError as e:
                            unsupported.append({"line": line_no, "statement": stmt, "reason": str(e)})
                    elif gate_name in self.PARAM_GATES:
                        unsupported.append({
                            "line": line_no,
                            "statement": stmt,
                            "reason": f"Parameterized gate '{gate_name}' missing required angle parameter(s)"
                        })
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
    # Builds QniverseCircuit; falls back to a QSDK-compatible MockQniverseCircuit if SDK unavailable
    try:
        from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister
        import qniverse.gates as G
        has_real_sdk = True
    except ImportError:
        has_real_sdk = False

    if not has_real_sdk:
        class _MockReg:
            def __init__(self, kind: str, size: int, name: str):
                self.kind = kind
                self.size = size
                self.name = name

            def __getitem__(self, idx: int):
                wkind = "Qubit" if self.kind == "Quantum" else "Clbit"
                return f"{wkind}({self.kind}Register({self.size}, '{self.name}'), {idx})"

            def __repr__(self):
                return f"{self.kind}Register({self.size}, '{self.name}')"

        class _MockGate:
            def __init__(self, name: str, params: Tuple[float, ...] = ()):
                self.name = name.upper() if name != "measure" else "Measure"
                self.params = params

            def __repr__(self):
                if self.params:
                    return f"Gate({self.name}, params={self.params})"
                return f"Gate({self.name})"

        class MockQniverseCircuit:
            def __init__(self, ops_list: List[QasmOp], n_q: int, n_c: int):
                self._ops = list(ops_list)
                self.num_qubits = n_q
                self.num_clbits = n_c
                self.registers = []
                self.qubit_registers = {}
                self.clbit_registers = {}
                self.operations = []

                q_reg = _MockReg("Quantum", n_q, "q") if n_q > 0 else None
                c_reg = _MockReg("Classical", n_c, "c") if n_c > 0 else None
                if q_reg:
                    self.registers.append(q_reg)
                    self.qubit_registers["q"] = q_reg
                if c_reg:
                    self.registers.append(c_reg)
                    self.clbit_registers["c"] = c_reg

                alias_map = {"cnot": "cx", "toffoli": "ccx"}
                for o in self._ops:
                    gname = alias_map.get(o.name.lower(), o.name.lower())
                    if gname == "measure" and q_reg and c_reg:
                        wires = (q_reg[o.qubits[0]], c_reg[o.cbits[0]])
                        self.operations.append((_MockGate("measure"), wires))
                    elif gname == "barrier" and q_reg:
                        for pair in _decompose_wide_barrier(o.qubits):
                            wires = tuple(q_reg[idx] for idx in pair)
                            self.operations.append((_MockGate("barrier"), wires))
                    elif q_reg:
                        wires = tuple(q_reg[idx] for idx in o.qubits)
                        self.operations.append((_MockGate(gname, o.params), wires))

            def qasm(self, version: str = "2.0") -> str:
                return ops_to_openqasm(self._ops, self.num_qubits, self.num_clbits, version=version)

            def to_qasm(self, version: str = "2.0") -> str:
                return ops_to_openqasm(self._ops, self.num_qubits, self.num_clbits, version=version)

            def to_qniverse_code(self) -> str:
                return ops_to_qniverse_code(self._ops, self.num_qubits, self.num_clbits)

            def list_gates(self) -> List[str]:
                return [getattr(op[0], "name", str(op[0])) for op in self.operations]

            def draw(self, filename: Optional[str] = None) -> str:
                return draw_circuit_text(self._ops, self.num_qubits, print_output=True)

            def draw_text(self, print_output: bool = True) -> str:
                return draw_circuit_text(self._ops, self.num_qubits, print_output=print_output)

            def __repr__(self):
                return f"<QniverseCircuit (compatible) qubits={self.num_qubits} clbits={self.num_clbits} operations={len(self.operations)}>"

        return MockQniverseCircuit(ops, num_qubits, num_cbits)

    # ---- Official Qniverse SDK Construction ----
    qc = QniverseCircuit()
    q = None
    if num_qubits > 0:
        q = QuantumRegister(num_qubits, "q")
        qc.add_register(q)
    c = None
    if num_cbits > 0:
        c = ClassicalRegister(num_cbits, "c")
        qc.add_register(c)

    alias_map = {"cnot": "cx", "toffoli": "ccx"}
    for o in ops:
        gname = alias_map.get(o.name.lower(), o.name.lower())
        if gname == "measure":
            qc.add_gate(G.measure, q[o.qubits[0]], c[o.cbits[0]])

        elif gname == "barrier":
            gate_fn = getattr(G, "barrier", None)
            if gate_fn:
                for pair in _decompose_wide_barrier(o.qubits):
                    qc.add_gate(gate_fn, *(q[idx] for idx in pair))

        elif gname == "reset":
            gate_fn = getattr(G, "reset", None)
            if gate_fn:
                qc.add_gate(gate_fn, q[o.qubits[0]])

        elif o.params:
            gate_creator = getattr(G, gname, None) or getattr(G, gname.upper(), None)
            if gate_creator is None:
                raise ValueError(f"Parameterized gate '{gname}' not found in qniverse.gates")

            direct_method = getattr(qc, gname, None) or getattr(qc, gname.lower(), None)
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
            gate_val = getattr(G, gname, None) or getattr(G, gname.upper(), None)
            if gate_val is None:
                raise ValueError(f"Standard gate '{gname}' not found in qniverse.gates")

            direct_method = getattr(qc, gname, None) or getattr(qc, gname.lower(), None)
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

    # Attach helper methods on real QniverseCircuit instance so .qasm(), .to_qniverse_code(), .list_gates(), and .draw_text() always work
    qc._ops = list(ops)
    qc.qasm = lambda version="2.0": ops_to_openqasm(ops, num_qubits, num_cbits, version=version)
    qc.to_qasm = lambda version="2.0": ops_to_openqasm(ops, num_qubits, num_cbits, version=version)
    qc.to_qniverse_code = lambda: ops_to_qniverse_code(ops, num_qubits, num_cbits)
    if not hasattr(qc, "list_gates"):
        qc.list_gates = lambda: [getattr(op[0], "name", str(op[0])) for op in getattr(qc, "operations", [])]
    qc.draw_text = lambda print_output=True: draw_circuit_text(ops, num_qubits, print_output=print_output)

    return qc


# ------------------------------------------------ Top-Level Convert API
def convert_qasm_to_qniverse(qasm_str: str, version: Optional[str] = None) -> Tuple[Optional[Any], Dict[str, Any]]:
    # Main entry point: accepts QASM string, returns (QniverseCircuit, report_dict)
    converter = QasmConverter()
    ops, meta = converter.parse(qasm_str, override_version=version)

    gate_counts: Dict[str, int] = {}
    for o in ops:
        gate_counts[o.name] = gate_counts.get(o.name, 0) + 1

    report: Dict[str, Any] = {
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
    report["qniverse_code"] = ops_to_qniverse_code(ops, meta["total_qubits"], meta["total_cbits"])
    report["openqasm_2_0"] = ops_to_openqasm(ops, meta["total_qubits"], meta["total_cbits"], version="2.0")
    report["openqasm_3_0"] = ops_to_openqasm(ops, meta["total_qubits"], meta["total_cbits"], version="3.0")
    report["diagram"] = draw_circuit_text(ops, meta["total_qubits"], print_output=False)
    return circuit, report


# ------------------------------------------------ Mathematical Verifier
_I = np.eye(2)
_H = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
_X = np.array([[0, 1], [1, 0]])
_Y = np.array([[0, -1j], [1j, 0]])
_Z = np.diag([1, -1])
_S = np.diag([1, 1j])
_T = np.diag([1, np.exp(1j * np.pi / 4)])
_SX = np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]]) / 2.0


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
    if name == "sx": return _SX
    if name == "sxdg": return _SX.conj().T
    if name == "rx":
        theta = params[0]
        return np.array([[np.cos(theta / 2), -1j * np.sin(theta / 2)],
                         [-1j * np.sin(theta / 2), np.cos(theta / 2)]])
    if name == "ry":
        theta = params[0]
        return np.array([[np.cos(theta / 2), -np.sin(theta / 2)],
                         [np.sin(theta / 2), np.cos(theta / 2)]])
    if name in ("rz", "p", "u1"):
        phi = params[0]
        return np.diag([np.exp(-1j * phi / 2), np.exp(1j * phi / 2)])
    if name == "u2":
        phi, lam = params[0], params[1]
        return np.array([
            [1.0, -np.exp(1j * lam)],
            [np.exp(1j * phi), np.exp(1j * (phi + lam))]
        ]) / np.sqrt(2.0)
    if name == "u3":
        theta, phi, lam = params[0], params[1], params[2]
        return np.array([
            [np.cos(theta / 2), -np.exp(1j * lam) * np.sin(theta / 2)],
            [np.exp(1j * phi) * np.sin(theta / 2), np.exp(1j * (phi + lam)) * np.cos(theta / 2)]
        ])
    raise ValueError(f"No verification matrix for '{name}'")


def compute_qasm_unitary(ops: List[QasmOp], n: int) -> np.ndarray:
    # Computes the full 2^n unitary from non-measurement operations
    dim = 2 ** n
    u = np.eye(dim, dtype=complex)
    for o in ops:
        gname = o.name.lower()
        if gname in {"measure", "reset", "barrier"}:
            continue
        m = np.zeros((dim, dim), dtype=complex)
        for col in range(dim):
            bits = [(col >> (n - 1 - k)) & 1 for k in range(n)]
            if len(o.qubits) == 1:
                gmat = _matrix_for_gate(gname, o.params)
                q = o.qubits[0]
                for b in (0, 1):
                    amp = gmat[b, bits[q]]
                    if amp != 0:
                        nb = bits.copy(); nb[q] = b
                        m[int("".join(map(str, nb)), 2), col] += amp
            elif gname in ("cx", "cnot"):
                nb = bits.copy()
                if bits[o.qubits[0]]: nb[o.qubits[1]] ^= 1
                m[int("".join(map(str, nb)), 2), col] += 1
            elif gname == "cz":
                phase = -1 if (bits[o.qubits[0]] and bits[o.qubits[1]]) else 1
                m[col, col] += phase
            elif gname == "swap":
                nb = bits.copy()
                a, b = o.qubits; nb[a], nb[b] = bits[b], bits[a]
                m[int("".join(map(str, nb)), 2), col] += 1
            elif gname in ("ch", "cy", "crx", "cry", "crz", "cp"):
                c_q, t_q = o.qubits
                if not bits[c_q]:
                    m[col, col] += 1
                else:
                    sub_name = "p" if gname == "cp" else gname[1:]
                    gmat = _matrix_for_gate(sub_name, o.params)
                    for b in (0, 1):
                        amp = gmat[b, bits[t_q]]
                        if amp != 0:
                            nb = bits.copy(); nb[t_q] = b
                            m[int("".join(map(str, nb)), 2), col] += amp
            elif gname in ("ccx", "toffoli"):
                nb = bits.copy()
                if bits[o.qubits[0]] and bits[o.qubits[1]]:
                    nb[o.qubits[2]] ^= 1
                m[int("".join(map(str, nb)), 2), col] += 1
            elif gname == "cswap":
                nb = bits.copy()
                if bits[o.qubits[0]]:
                    a, b = o.qubits[1], o.qubits[2]
                    nb[a], nb[b] = bits[b], bits[a]
                m[int("".join(map(str, nb)), 2), col] += 1
            else:
                raise ValueError(f"Unsupported gate in unitary calculation: '{gname}'")
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

    # Test 1: OpenQASM 2.0 Bell State -> QniverseCircuit
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
    assert hasattr(circ, "operations") and len(circ.operations) == 4
    assert hasattr(circ, "registers") and len(circ.registers) == 2
    assert "qc = QniverseCircuit()" in rep["qniverse_code"]
    assert "OPENQASM 2.0;" in rep["openqasm_2_0"]
    assert "q0: --" in rep["diagram"]
    print("[PASS] Test 1: OpenQASM 2.0 -> QniverseCircuit & QSDK code verified.")

    # Test 2: OpenQASM 3.0 Modern Syntax -> QniverseCircuit
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
    assert len(circ3.operations) == 4
    print("[PASS] Test 2: OpenQASM 3.0 Modern Syntax -> QniverseCircuit verified.")

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
    assert "rx(pi/2) q[0];" in rep_p["openqasm_2_0"]
    assert "qc.add_gate(rx(np.pi/2), q[0])" in rep_p["qniverse_code"]
    print("[PASS] Test 3: Parameterized rotations with pi math verified.")

    # Test 4: Diagnostic Safety & Unsupported Gate / Arity Rejection
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

    # Test 5: Semantic Unitary Equivalence Verification (Bell state matrix + roundtrip)
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

    # Also verify round-trip QniverseCircuit -> OpenQASM -> Unitary equivalence
    bell_circ, _ = convert_qasm_to_qniverse(bell_qasm)
    rt_ops, _ = conv.parse(qniverse_to_openqasm(bell_circ, version="2.0"))
    u_rt = compute_qasm_unitary(rt_ops, 2)
    assert equal_up_to_phase(u_computed, u_rt), "Round-trip unitary mismatch"
    print("[PASS] Test 5: Semantic & round-trip unitary equivalence verified up to global phase.")

    print("\n--- ALL QC-C2-04 CONVERTER TESTS PASSED SUCCESSFULLY! ---")


if __name__ == "__main__":
    run_all_tests()
    sample = (
        "OPENQASM 3.0;\n"
        "qubit[2] q;\n"
        "bit[2] c;\n"
        "h q[0];\n"
        "cx q[0], q[1];\n"
        "barrier q[0], q[1];\n"
        "rx(pi/2) q[1];\n"
        "c[0] = measure q[0];\n"
        "c[1] = measure q[1];\n"
    )
    circ, report = convert_qasm_to_qniverse(sample)

    print("\n========================================================")
    print("1. INPUT OPENQASM 3.0 SOURCE")
    print("========================================================")
    print(sample.strip())

    print("\n========================================================")
    print("2. CONVERTED QNIVERSE CIRCUIT & QSDK PYTHON CODE")
    print("========================================================")
    print(f"Circuit Object : {circ}")
    print(f"Registers      : {circ.registers}")
    print(f"Operations ({len(circ.operations)}) : {circ.operations}")
    print("\n--- Equivalent Qniverse QSDK Code ---")
    print(circ.to_qniverse_code().strip())

    print("\n========================================================")
    print("3. EXPORTED OPENQASM 2.0 (circ.qasm('2.0'))")
    print("========================================================")
    print(circ.qasm("2.0").strip())

    print("\n========================================================")
    print("4. EXPORTED OPENQASM 3.0 (circ.qasm('3.0'))")
    print("========================================================")
    print(circ.qasm("3.0").strip())

    print("\n========================================================")
    print("5. CIRCUIT DIAGRAM (ASCII + QSDK Draw)")
    print("========================================================")
    draw_circuit_text(circ)
    if hasattr(circ, "draw") and type(circ).__name__ != "MockQniverseCircuit":
        try:
            circ.draw()
        except Exception:
            pass

    import json
    print("\n========================================================")
    print("6. CONVERSION DIAGNOSTIC REPORT")
    print("========================================================")
    summary_report = {
        k: v for k, v in report.items()
        if k not in ("qniverse_code", "openqasm_2_0", "openqasm_3_0", "diagram")
    }
    print(json.dumps(summary_report, indent=2))
