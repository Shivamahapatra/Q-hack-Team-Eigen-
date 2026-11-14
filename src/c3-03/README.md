# QC-03-03: Quantum Circuit Optimization Using QSDK

## 1. Problem Statement
In Noisy Intermediate-Scale Quantum (NISQ) devices, physical qubits are subject to rapid decoherence, gate infidelities, and cross-talk. Circuit optimization compiles quantum programs to mathematically equivalent, reduced forms to decrease gate execution count and critical-path depth, significantly improving quantum circuit fidelity on target hardware.

This module implements a conservative, provably safe, pass-based quantum circuit optimizer designed for C-DAC's **Qniverse QSDK**.

---

## 2. Architecture & Design Principles

```text
Input Circuit (QniverseCircuit / QASM / Op list)
                     │
                     ▼
             [ Ingestion Layer ]
          (qa.from_qniverse / QASM)
                     │
                     ▼
          [ Baseline Metrics Profiler ]
            (c1_01_final.profile)
                     │
                     ▼
     [ Conservative Optimization Pipeline ]
     ┌────────────────────────────────────┐
     │  Pass 1: Identity Removal ('id')   │
     │  Pass 2: Self-Inverse (X-X, H-H,   │
     │          Z-Z cancellation)         │
     │  Pass 3: CX Cancellation (CX-CX)   │
     └────────────────────────────────────┘
                     │ (Iterates until fixed point)
                     ▼
         [ Post-Optimization Metrics ]
            (c1_01_final.profile)
                     │
                     ▼
        [ Equivalence Verification ]
         (Unitary / Structural Invariance)
                     │
                     ▼
        [ Reconstruction & Output ]
          (New QniverseCircuit Object)
```

### Core Design Principles:
1. **Zero-Mutation Guarantee**: The input circuit is never modified. All operations are snapshot and verified.
2. **Conservative Adjacency**: Only strictly consecutive operations in the execution stream are cancelled. No commutation or gate reordering is performed in this tier.
3. **Hardware & Classical Boundary Safety**: Non-unitary operations (`measure`, `barrier`, `reset`) serve as hard compilation barriers and are preserved strictly in place.

---

## 3. Supported Optimization Rules & Preconditions

| Optimization Pass | Identifier | Target Gates | Preconditions for Cancellation |
| :--- | :--- | :--- | :--- |
| **Pass 1: Identity Removal** | `identity_removal` | `id` | Gate name is explicitly `'id'`. Removed safely without altering wire states. |
| **Pass 2: Self-Inverse Cancellation** | `self_inverse_cancellation` | `x`, `h`, `z` | Consecutive gates on the **exact same qubit** with identical names: $X \cdot X = I$, $H \cdot H = I$, $Z \cdot Z = I$. |
| **Pass 3: CX Cancellation** | `cx_cancellation` | `cx` | Consecutive two-qubit CX gates where **control qubits match**, **target qubits match**, and control/target ordering is identical: $\text{CX}(c, t) \cdot \text{CX}(c, t) = I$. Reversed controls $\text{CX}(c, t) \cdot \text{CX}(t, c)$ are **not** cancelled. |

---

## 4. Public API & Usage

```python
from optimizer import optimize, OptimizationResult

# Optimize with all passes enabled by default:
result: OptimizationResult = optimize(qc)

# Inspect the returned circuit and report:
new_circuit = result.circuit
report = result.report

# Or selectively enable passes:
result = optimize(
    qc,
    enabled_passes=["identity_removal", "self_inverse_cancellation"]
)
```

### Report Output Structure:
```json
{
  "status": "OK",
  "passes_enabled": ["identity_removal", "self_inverse_cancellation", "cx_cancellation"],
  "passes_applied": ["cx_cancellation", "identity_removal", "self_inverse_cancellation"],
  "before": {
    "total_gates": 9,
    "by_type": {"id": 1, "h": 3, "x": 2, "cx": 2, "z": 1},
    "qubits_declared": 2,
    "qubits_used": 2,
    "single_qubit_gates": 7,
    "multi_qubit_gates": 2,
    "two_qubit_gates": 2,
    "depth": 10,
    "measurements": 2
  },
  "after": {
    "total_gates": 2,
    "by_type": {"h": 1, "z": 1},
    "qubits_declared": 2,
    "qubits_used": 2,
    "single_qubit_gates": 2,
    "multi_qubit_gates": 0,
    "two_qubit_gates": 0,
    "depth": 2,
    "measurements": 2
  },
  "gates_removed": 7,
  "reduction_percentage": 77.78,
  "equivalence": {
    "type": "terminal_measurement_verified",
    "equivalent": true,
    "mathematical_equivalence_verified": true,
    "structural_preservation_verified": true,
    "method": "unitary_prefix_matrix_and_measurement_preservation",
    "details": "Unitary prefix mathematically verified via equal_up_to_phase; terminal measurements verified structurally in-order."
  },
  "warnings": [
    "Circuit contains non-unitary operations (measure/barrier/reset) preserved structurally."
  ]
}
```

---

## 5. Safety & Register Preservation
- **Zero Operation Dropping (DEF-03)**: Every input operation must be reconstructed successfully or raise an explicit `ValueError`. Reconstructed operation counts and sequence ordering are strictly validated.
- **Fail-Fast Parameterized Gate Rejection (DEF-04)**: Circuits with continuous parameterized rotation gates (`rx`, `ry`, `rz`, `p`, `u1`, `u2`, `u3`, `crx`, etc.) are explicitly rejected before optimization to guarantee parameters are never silently discarded.
- **Rigorous Boundary Preservation (DEF-05, DEF-06)**: Unitary operations are strictly validated never to cross non-unitary delimiters (`measure`, `reset`, `barrier`). Missing, moved, or reordered barriers or measurements immediately fail structural verification.
- **Register Architecture Preservation (DEF-08)**: Multi-register layouts (`QuantumRegister` and `ClassicalRegister`) maintain their exact names, sizes, ordering, and wire indices. Register size sums are verified against wire declarations. Out-of-range wire indices raise an explicit exception and are never fabricated. Circuit metadata is deepcopied and preserved intact.
- **Dimension & Arity Validation (DEF-07)**: Malformed operations, invalid qubit indices, arity violations, and dimension mismatches are strictly rejected upfront.
- **No Gate Permutation / Commutation**: The sequence of gates is never reordered. Only strictly adjacent identical self-inverse pairs or identical CX pairs are cancelled.
- **Reversed CX Safeguard**: `CX(0, 1)` followed by `CX(1, 0)` is strictly preserved because $\text{CX}(0, 1)\text{CX}(1, 0) \neq I$.

---

## 6. Equivalence Validation Methodology
Reuses verified numerical linear algebra utilities from `src/c1_01_final.py` across three rigorous validation tiers:

1. **Tier A: Purely Unitary Circuits (+ Barriers)**:
   - Calculates the exact full system matrix: $U_{\text{orig}} = \prod_k U_k$ and $U_{\text{opt}} = \prod_j U_j$.
   - Validates that $U_{\text{orig}} \approx e^{i\theta} U_{\text{opt}}$ within absolute tolerance $10^{-9}$ using `equal_up_to_phase()`.
   - Barriers are treated as compilation boundaries: verified for operand, sequence, and relative gate placement via delimiter segment matching (`_verify_structural_placement`).
   - Returns `"equivalent": True` only when mathematical equivalence AND barrier placement pass.

2. **Tier B: Circuits with Terminal Measurements**:
   - Asserts that measurements appear strictly at the end of the circuit execution.
   - Extracts the unitary operations executed prior to measurements.
   - Mathematically verifies the unitary prefix up to global phase using `equal_up_to_phase()`.
   - Structurally checks that all non-unitary operations (terminal measurements AND barriers across the circuit) are preserved without gate boundary crossing.
   - Returns `"equivalent": True` only when BOTH mathematical and structural checks pass.

3. **Tier C: Circuits with Mid-Circuit Measurements or Resets**:
   - Because state collapse / non-unitary resets prevent unitary matrix comparison, semantic equivalence is **not** claimed.
   - Returns `"equivalent": None`, status `"OK_SEMANTIC_UNVERIFIED"`, and an explicit diagnostic warning.
   - Structural preservation of non-unitary operations and boundary placement relative to unitary gates is verified separately via delimiter segment matching and reported as `"structural_preservation_verified": True`.

---

## 7. Execution & Testing Instructions

### Run Unit Tests:
```bash
python src/c3-03/test_optimizer.py
```
Or with unittest:
```bash
python -m unittest discover -s src/c3-03 -p "test_*.py"
```

### Run Demonstration:
```bash
python src/c3-03/demo.py
```

---

## 8. Reproducible Demonstration Cases (Actual Runs)

### Case A: Improvement Case (Redundant Circuit)
- **Input Circuit**: `id(0)`, `H(0)`, `X(0)`, `X(0)`, `CX(0, 1)`, `CX(0, 1)`, `H(1)`, `H(1)`, `Z(1)`, `measure(0->0)`, `measure(1->1)`
- **Gates Before**: 9 (`id: 1`, `h: 3`, `x: 2`, `cx: 2`, `z: 1`), Depth: 10
- **Gates After**: 2 (`h: 1`, `z: 1`), Depth: 2
- **Net Improvement**: **7 gates removed (77.78% reduction)**, Depth reduced from **10 to 2**.
- **Equivalence**: Verified `True`.

### Case B: No-Improvement Case (Already Optimal)
- **Input Circuit**: `H(0)`, `CX(0, 1)`, `T(1)`, `measure(0->0)`, `measure(1->1)`
- **Gates Before**: 3 (`h: 1`, `cx: 1`, `t: 1`), Depth: 4
- **Gates After**: 3 (`h: 1`, `cx: 1`, `t: 1`), Depth: 4
- **Net Improvement**: **0 gates removed (0.0% reduction)**. Circuit returned intact.
- **Equivalence**: Verified `True`.

---

## 9. Known Limitations
1. **Conservative Adjacency Only**: Does not commute independent single-qubit gates across CNOT controls/targets to discover non-adjacent cancellations.
2. **Phase Fusion Omitted**: Advanced multi-gate fusions (e.g. $T \cdot T \to S$, $S \cdot S \to Z$) are reserved for higher optimization tiers to maintain conservative certification.
3. **Parameterized Rotations (DEF-04 Fail-Fast)**: Circuits with parameterized gates (`rx`, `ry`, `rz`, `u3`, `crx`, etc.) are explicitly rejected before optimization because runtime parameter preservation is not implemented in the current SDK adapter. Parameterized circuits will raise `ValueError` to ensure parameters are never lost.
