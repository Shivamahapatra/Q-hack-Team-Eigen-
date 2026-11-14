# Technical Approach: QC-C1-01 (Circuit Profiling & Limited Basis-Gate Decomposition)

## 1. Problem Overview

In quantum compilation, target quantum processing units (QPUs) cannot execute arbitrary high-level gates directly. Hardware backends only support a calibrated native **basis gate set** (such as $\{cx, h\}$ or Clifford+T $\{h, t, t^\dagger, cx\}$).

**QC-C1-01 Core Objectives**:
1. **Circuit Profiling**: Calculate rigorous circuit statistics (total gates, 1-qubit vs multi-qubit gates, 2-qubit count, and circuit depth via an earliest-available-layer schedule).
2. **Limited Basis-Gate Decomposition**: Translate any non-basis gates into equivalent sequences of target basis gates using recursive rule substitution, while ensuring the original circuit is completely untouched (immutability).
3. **Qniverse QSDK Compatibility**: Support native `QniverseCircuit` ingestion and emission with fallback OpenQASM 2.0 parsing.

---

## 2. Architecture & Data Flow

```
+-------------------------------------------------------------+
|              Input: QniverseCircuit / QASM 2.0              |
+-------------------------------------------------------------+
                              |
                              v  (from_qniverse / parse_qasm)
+-------------------------------------------------------------+
|               Internal Op Representation (Tuple)            |
|            Op(name="h", qubits=(0,), cbits=())              |
+-------------------------------------------------------------+
          |                                       |
          v                                       v
+------------------------+             +----------------------+
|    profile(ops, n)     |             | decompose(ops, basis)|
|  - Earliest Layer DAG  |             |  - Recursive Rule    |
|  - Barrier Sync        |             |  - Cycle Detection   |
|  - Gate Counts         |             |  - Error on Unsup.   |
+------------------------+             +----------------------+
          |                                       |
          v                                       v
    Before Profile                            Decomposed Ops
                                                  |
                                                  v  (to_qniverse)
                                       +----------------------+
                                       | New QniverseCircuit  |
                                       | (Input Unmodified)   |
                                       +----------------------+
```

---

## 3. Core Algorithms

### 3.1 Earliest-Available-Layer Depth Scheduler (`profile`)
Circuit depth represents the runtime duration of the circuit assuming gates execute as soon as their operand qubits are free.

1. **Free-Layer Tracking**: Maintain an array `free = [0] * num_qubits`, representing the next available layer for each wire.
2. **Gate Scheduling**: For an operation acting on qubits $Q$:
   $$\text{start} = \max_{q \in Q} \text{free}[q]$$
   $$\forall q \in Q: \quad \text{free}[q] \leftarrow \text{start} + 1$$
   $$\text{depth} \leftarrow \max(\text{depth}, \text{start} + 1)$$
3. **Barrier Synchronization**:
   A `barrier` consumes **0 layers** of execution time, but acts as a synchronization fence:
   $$\text{start} = \max_{q \in Q} \text{free}[q]$$
   $$\forall q \in Q: \quad \text{free}[q] \leftarrow \text{start}$$
   Operations following the barrier on any spanned wire cannot slide backward ahead of gates preceding the barrier.

---

### 3.2 Recursive Basis Decomposition (`decompose` & `_expand`)
The decomposition engine translates arbitrary gates into a user-specified target basis $\mathcal{B}$:

1. **Base Case**: If an operation's name is already in $\mathcal{B}$ or belongs to `NON_UNITARY` (`measure`, `reset`, `barrier`), it is retained as-is.
2. **Rule Tree Lookup**: High-level gates are mapped through local decomposition rules:
   - $X = H \cdot Z \cdot H$
   - $Y = S^\dagger \cdot X \cdot S$
   - $Z = H \cdot X \cdot H$ (with alternative $Z = S \cdot S$)
   - $CZ(q_0, q_1) = H(q_1) \cdot CX(q_0, q_1) \cdot H(q_1)$
   - $SWAP(q_0, q_1) = CX(q_0, q_1) \cdot CX(q_1, q_0) \cdot CX(q_0, q_1)$
   - $S = T \cdot T, \quad S^\dagger = T^\dagger \cdot T^\dagger$
   - $CCX$ (Toffoli): 15-gate Clifford+T decomposition.
3. **Cycle Prevention**: A recursion stack `stack` tracks active expansions. If a cyclic dependency occurs (e.g. $X \leftrightarrow Z$), the engine prunes the branch and falls back to alternative rules (`ALT_RULES`).
4. **Unsupported Gate Handling**: If a gate cannot be expanded into the basis $\mathcal{B}$, decomposition halts and emits:
   ```json
   { "status": "FAILED: unsupported operations, no circuit emitted", "unsupported": [...] }
   ```
   No invalid or partially decomposed circuit is ever emitted.

---

### 3.3 Unitary Equivalence Verification (`unitary` & `equal_up_to_phase`)
To mathematically prove correctness without depending on external simulators:
1. Matrix representations are generated on $2^n$-dimensional Hilbert space using binary column decomposition.
2. Equivalence between the original circuit $U$ and decomposed circuit $V$ is evaluated up to global phase $e^{i\phi}$:
   $$\exists \phi \in \mathbb{R} \quad \text{such that} \quad U = e^{i\phi} V \iff \frac{U_{ij}}{V_{ij}} \cdot V \approx U$$

---

### 3.4 Qniverse QSDK Integration (`from_qniverse` & `to_qniverse`)
- **Ingestion**: Accepts native `QniverseCircuit` objects, inspecting `.qasm()`, `.gates`, or raw OpenQASM 2.0 text.
- **Emission**: Rebuilds a fresh `QniverseCircuit` using documented QSDK modules (`qniverse.circuit.QniverseCircuit`, `qniverse.registers.QuantumRegister`, `qniverse.registers.ClassicalRegister`, `qniverse.gates.*`).
- **Offline Fallback**: If the Qniverse environment container is not present, emits a standard `MockQniverseCircuit` conforming to the identical API and QASM export contract.
