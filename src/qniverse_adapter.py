"""
Adapter between QniverseCircuit and the profiler's Op list.

VERIFIED from real output (dir(qc), vars(qc)) in the Qniverse JupyterLab:
  * qc.operations is a list of (Gate, qubits_tuple)
  * Gate has .name like 'H', 'CX', 'Measure' and a .matrix
  * a qubit prints as  Qubit(QuantumRegister(2, 'q'), 0)
    a clbit prints as  Clbit(ClassicalRegister(2, 'c'), 0)
  * qc.num_qubits, qc.num_clbits, qc.qubit_registers (dict name->register)

NOT YET VERIFIED (check in the JupyterLab, see TODO markers):
  * how barrier / reset appear in qc.operations
  * where rotation angles (rx, rz, u3 ...) are stored on a Gate
"""
import re
from c1_01_profiler import Op

_REG = re.compile(r"(Qubit|Clbit)\((?:Quantum|Classical)Register\((\d+), '([^']+)'\), (\d+)\)")
PARAMETERISED = {"rx", "ry", "rz", "p", "u1", "u2", "u3",
                 "crx", "cry", "crz", "cp", "cu1", "cu2", "cu3"}


def _parse_wire(w):
    """Return (kind, register_name, index) from the wire's printed form."""
    m = _REG.search(repr(w))
    if not m:
        raise ValueError(f"cannot read wire {w!r}")
    return m.group(1), m.group(3), int(m.group(4))


def _register_sizes(qc):
    """Return {name: size} for quantum and classical registers, in order."""
    q_sizes, c_sizes = {}, {}
    for reg in qc.registers:
        m = re.search(r"(Quantum|Classical)Register\((\d+), '([^']+)'\)", repr(reg))
        (q_sizes if m.group(1) == "Quantum" else c_sizes)[m.group(3)] = int(m.group(2))
    return q_sizes, c_sizes


def from_qniverse(qc):
    """QniverseCircuit -> (list[Op], num_qubits, num_clbits, report_extra)."""
    if qc is None or not hasattr(qc, "operations"):
        raise ValueError("input is not a QniverseCircuit (no .operations)")
    q_sizes, c_sizes = _register_sizes(qc)
    q_off, c_off, t = {}, {}, 0
    for name, size in q_sizes.items():
        q_off[name] = t; t += size
    t = 0
    for name, size in c_sizes.items():
        c_off[name] = t; t += size

    ops, warnings = [], []
    for gate, wires in qc.operations:
        name = str(gate.name).lower()
        qubits, cbits = [], []
        for w in wires:
            kind, reg, idx = _parse_wire(w)
            (qubits if kind == "Qubit" else cbits).append(
                (q_off if kind == "Qubit" else c_off)[reg] + idx)
        if name in PARAMETERISED:
            # TODO: find where the angle lives (print(vars(gate)) for an rz gate).
            warnings.append(f"parameterised gate '{name}' read WITHOUT its angle")
        ops.append(Op(name, tuple(qubits), tuple(cbits)))
    return ops, qc.num_qubits, qc.num_clbits, {"warnings": warnings}


def to_qniverse(ops, num_qubits, num_clbits):
    """list[Op] -> NEW QniverseCircuit (single register 'q' and 'c')."""
    import qniverse.gates as G
    from qniverse.QniverseCircuit import QniverseCircuit, QuantumRegister, ClassicalRegister

    qc = QniverseCircuit()
    q = QuantumRegister(num_qubits, "q")
    qc.add_register(q)
    c = None
    if num_clbits:
        c = ClassicalRegister(num_clbits, "c")
        qc.add_register(c)

    for o in ops:
        if o.name == "measure":
            qc.add_gate(G.measure, q[o.qubits[0]], c[o.cbits[0]])
        elif o.name in ("barrier", "reset"):
            # TODO: confirm the call for barrier/reset in the notebooks.
            raise NotImplementedError(f"building '{o.name}' not verified yet")
        elif o.name in PARAMETERISED:
            raise NotImplementedError(f"rebuilding '{o.name}' needs its angle")
        else:
            gate = getattr(G, o.name, None)
            if gate is None:
                raise ValueError(f"gate '{o.name}' not found in qniverse.gates")
            qc.add_gate(gate, *[q[i] for i in o.qubits])
    return qc


# ------------------------------------------------ offline self-test (mock)
def _selftest():
    class W:                      # prints exactly like the real wires
        def __init__(s, r): s.r = r
        def __repr__(s): return s.r
    class Gt:
        def __init__(s, n): s.name = n
    class QC:
        num_qubits, num_clbits = 2, 2
        registers = [W("QuantumRegister(2, 'q')"), W("ClassicalRegister(2, 'c')")]
        q0, q1 = W("Qubit(QuantumRegister(2, 'q'), 0)"), W("Qubit(QuantumRegister(2, 'q'), 1)")
        c0, c1 = W("Clbit(ClassicalRegister(2, 'c'), 0)"), W("Clbit(ClassicalRegister(2, 'c'), 1)")
    qc = QC()
    qc.operations = [(Gt("H"), (qc.q0,)), (Gt("CX"), (qc.q0, qc.q1)),
                     (Gt("Measure"), (qc.q0, qc.c0)), (Gt("Measure"), (qc.q1, qc.c1))]
    ops, nq, nc, extra = from_qniverse(qc)
    assert ops == [Op("h", (0,)), Op("cx", (0, 1)),
                   Op("measure", (0,), (0,)), Op("measure", (1,), (1,))], ops
    assert (nq, nc) == (2, 2)
    print("adapter self-test passed")


if __name__ == "__main__":
    _selftest()
