# Technical Approach: QC-03-03 (Quantum Circuit Optimization Using QSDK)

## 1. Problem Overview & Scope

Quantum processing units (QPUs) have limited coherence times and gate fidelity constraints. Executing unnecessary or redundant operations degrades circuit fidelity and wastes quantum resources.

### QC-03-03 Core Objectives:
1. **Non-Mutating Circuit Optimization**: Accept a `QniverseCircuit` object and return a brand-new, valid `QniverseCircuit` without modifying the original input object.
2. **Modular Rewrite Passes**: Implement independently testable, documented rewrite passes:
   - **Identity Elimination**: Remove redundant identity gates (`id`).
   - **Self-Inverse Cancellation**: Cancel adjacent identical self-inverse gates ($X \cdot X = I, H \cdot H = I, Z \cdot Z = I, Y \cdot Y = I$).
   - **Adjacent CX Cancellation**: Cancel sequential $CX$ operations sharing identical control and target qubits ($CX(c, t) \cdot CX(c, t) = I$).
   - **Rotation Merging**: Merge consecutive rotations around identical axes ($R_x(\theta_1) \cdot R_x(\theta_2) = R_x(\theta_1 + \theta_2)$).
3. **Fence & Boundary Preservation**: Ensure barriers, measurements, resets, and classical conditions act as impassable synchronization barriers preventing illegal cancellations.
4. **Comprehensive Before/After Metrics**: Calculate and report total gate counts, per-gate breakdown, and earliest-available-layer circuit depth before and after optimization.
5. **Behavioral Invariance Proof**: Provide rigorous mathematical verification that optimized circuits produce identical unitary transformations up to global phase.

---

## 2. Architecture & Pass Manager Pipeline

```
+--------------------------------------------------------------------------+
|                     Input: QniverseCircuit (Untouched)                   |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                       Stage 1: Circuit Ingestion                         |
|     - Extract operations, registers, parameters, and metadata            |
|     - Profile Initial State: gate counts and initial DAG depth           |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                 Stage 2: Pass Manager (Configurable Pipeline)            |
|   Enabled Passes:                                                        |
|     [Pass 1] RemoveIdentities        -> Eliminates explicit `id` gates   |
|     [Pass 2] CancelSelfInverse       -> Eliminates X-X, H-H, Z-Z, Y-Y    |
|     [Pass 3] CancelAdjacentCX        -> Eliminates identical CX-CX pairs |
|     [Pass 4] MergeRotationAngles     -> Merges sequential Rx, Ry, Rz     |
|   Enforces: Fence safety (Barriers, Measurements, Resets)                |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Stage 3: Fixed-Point Convergence Loop                  |
|     - Iterate passes until no further reduction occurs                   |
|     - Prevents infinite loops via bounded pass iterations                |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|               Stage 4: New QniverseCircuit Reconstruction                |
|     - Rebuilds fresh QniverseCircuit using documented QSDK APIs          |
|     - Preserves qubit and classical register mappings                    |
|     - Profile Final State: optimized gate counts and final DAG depth     |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Output: (New QniverseCircuit, Metrics Report)          |
+--------------------------------------------------------------------------+
```

---

## 3. Rewrite Pass Specifications & Mathematical Formulations

### 3.1 Pass 1: Identity Gate Elimination (`RemoveIdentities`)
- **Mathematical Basis**: $U \cdot I = I \cdot U = U$.
- **Action**: Any operation with name `id` acting on wire $q$ is dropped from the circuit unless it serves as a delay placeholder.
- **Fence Safety**: Never crosses measurements or resets.

### 3.2 Pass 2: Self-Inverse Gate Cancellation (`CancelSelfInverse`)
- **Mathematical Basis**: For any unitary $U$ such that $U = U^\dagger$ (Hermitian unitary), $U^2 = I$.
  - Pauli Gates: $X^2 = I, Y^2 = I, Z^2 = I$.
  - Hadamard Gate: $H^2 = I$.
- **Action**: If two identical self-inverse gates occur consecutively on the same qubit wire $q$ with no intervening non-commuting operations:
  $$U(q) \dots U(q) \longrightarrow \emptyset$$
- **Commutation Awareness**: If intervening operations act entirely on disjoint wires $\{q' \mid q' \ne q\}$, the gates commute and cancellation proceeds safely.

### 3.3 Pass 3: Adjacent Identical CX Cancellation (`CancelAdjacentCX`)
- **Mathematical Basis**: Since $CX$ is an involution:
  $$CX(c, t) \cdot CX(c, t) = I$$
- **Action**: Two $CX$ operations with the same control wire $c$ and target wire $t$ cancel out completely if no intervening operation affects wire $c$ or wire $t$.
- **Negative Case**: $CX(c, t) \cdot CX(t, c) \ne I$ (non-commuting reversal of control and target is strictly preserved).

### 3.4 Pass 4: Consecutive Rotation Merging (`MergeRotationAngles`)
- **Mathematical Basis**: Continuous rotation generators commute with themselves:
  $$R_k(\theta_1) \cdot R_k(\theta_2) = R_k(\theta_1 + \theta_2), \quad k \in \{X, Y, Z\}$$
- **Action**: Two adjacent rotations on the same wire around the same axis are combined into a single gate with parameter $(\theta_1 + \theta_2) \pmod{2\pi}$. If $\theta_1 + \theta_2 \approx 0 \pmod{2\pi}$, the combined gate collapses to identity and is removed.

---

## 4. Barrier & Measurement Fence Safety

The optimizer strictly respects quantum circuit causality and synchronization:
1. **Barrier Fence**: A `barrier [q0, q1]` creates an impenetrable boundary. Gates scheduled before the barrier cannot commute past it or cancel with gates scheduled after it.
2. **Measurement Fence**: Once a qubit is measured (`measure q[i] -> c[j]`), state collapse has occurred. No subsequent quantum gate on $q[i]$ can cancel with a pre-measurement gate.
3. **Reset Fence**: `reset q[i]` projects the state to $|0\rangle$, invalidating any cancellation across the reset boundary.

---

## 5. Metrics & Depth Profiling Protocol

Circuit depth and gate resource counts are computed consistently before and after optimization using an **Earliest-Available-Layer DAG Scheduler**:
- Each qubit wire tracks its next free layer: `free[q]`.
- For gate $G$ spanning qubits $Q$:
  $$\text{start} = \max_{q \in Q} \text{free}[q]$$
  $$\forall q \in Q: \quad \text{free}[q] \leftarrow \text{start} + 1$$
- Barrier synchronization updates wires without incrementing layer count.
- Optimization efficiency is evaluated as:
  $$\Delta_{\text{gates}} = \frac{N_{\text{before}} - N_{\text{after}}}{N_{\text{before}}} \times 100\%, \quad \Delta_{\text{depth}} = \frac{D_{\text{before}} - D_{\text{after}}}{D_{\text{before}}} \times 100\%$$
