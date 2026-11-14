# Technical Approach - Team Eigen

## 1. The Big Picture (In Plain Words)

Quantum programs are usually written in **OpenQASM** (a text format for quantum circuits, similar to assembly code). Real quantum hardware can only run a limited set of native gates, and noisy hardware requires circuits to be as short as possible.

Our project builds a 3-step pipeline for C-DAC's **Qniverse** platform:

```
[ Step 1: Converter ]         [ Step 2: Optimizer ]            [ Step 3: Profiler & Decomposer ]
OpenQASM 2.0 / 3.0 text  -->  Delete useless / duplicate  -->  Count gates & depth,
converted into a              gates to make the circuit        and break complex gates into
QniverseCircuit               faster and less noisy            hardware-supported basis gates
```

---

## 2. Step-by-Step Breakdown

### Step 1: OpenQASM Converter (`QC-C2-04`)
- **What it does**: Reads quantum code written in OpenQASM 2.0 or 3.0 and turns it into a Python `QniverseCircuit` object.
- **What it handles**:
  - Qubit and classical bit registers (`qreg`, `qubit`).
  - Standard gates: `H`, `X`, `Y`, `Z`, `S`, `T`.
  - Angle rotation gates: `Rx`, `Ry`, `Rz`.
  - Entangling two-qubit gates: `CX` (CNOT), `CZ`, `SWAP`.
  - Measurements and barriers.
- **Safety**: If someone feeds in invalid or unsupported code, the tool explains the error clearly instead of crashing silently.

---

### Step 2: Circuit Optimizer (`QC-03-03`)
- **What it does**: Removes redundant gates to make the circuit shorter without changing its mathematical result.
- **The 3 Rules**:
  1. **Drop Identity gates**: An `Identity` gate does nothing to a qubit. We simply remove it.
  2. **Cancel Self-Inverse Pairs**: Certain gates cancel themselves out when run twice in a row:
     - `H` followed by `H` = does nothing (cancels out).
     - `X` followed by `X` = does nothing (cancels out).
     - `Z` followed by `Z` = does nothing (cancels out).
  3. **Cancel Consecutive CX Gates**: A `CX` gate run twice on the same control and target qubits cancels out:
     - `CX(q0, q1)` followed by `CX(q0, q1)` = does nothing (cancels out).
- **Golden Rule on Barriers**: If the user placed a `barrier` between two gates, we never cancel across it. Barriers act as stop signs.

---

### Step 3: Profiler and Basis-Gate Decomposer (`QC-C1-01`)
- **What it does**: 
  1. Counts all resources (total gates, 1-qubit gates, 2-qubit gates, and circuit depth).
  2. Replaces any gate that is not supported by the hardware with equivalent supported basis gates.

#### How Circuit Depth is Calculated (Earliest-Layer Rule)
- Imagine time moving left to right.
- Gates acting on **different qubits** can run at the exact same time (same layer).
- Gates acting on the **same qubit** must wait for the previous gate on that qubit to finish.
- The total depth is simply how many time steps the slowest qubit takes.

#### How Decomposition Works
If the hardware only knows rotation gates (`Rx`, `Ry`, `Rz`) and `CX`:
- We convert `H` into rotations: $Rz \rightarrow Rx \rightarrow Rz$.
- We convert `X` into a rotation: $Rx(\pi)$.
- We convert `SWAP` into 3 CNOT gates: $CX \rightarrow CX \rightarrow CX$.

---

## 3. Guarantees for the Judges (Viva Highlights)

1. **Non-Mutating**: We never modify the user's original circuit in-place. We always output a clean, new circuit object.
2. **Deterministic & Safe**: If a gate cannot be decomposed, we return a clear diagnostic report rather than producing an incorrect circuit.
3. **Real Metrics**: All reported gate counts and depths are computed directly from actual runs.
