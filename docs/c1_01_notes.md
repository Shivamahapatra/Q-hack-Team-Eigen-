# QC-C1-01: Circuit Profiling and Basis-Gate Decomposition Notes

## 1. Depth Definition & Layer Scheduling
The circuit depth is calculated using an **earliest-available-layer schedule**:
- **Gate / Measurement / Reset Operations**:
  - Each unitary gate, measurement, and reset operation occupies **one layer** across all qubits it touches.
  - An operation is placed at `start + 1`, where `start = max(free[q] for q in o.qubits)`.
  - Operations sharing a qubit preserve their sequential order.
  - Operations acting on disjoint qubits can execute in parallel within the same layer.
- **Barriers**:
  - A `barrier` adds **no layer** to the overall depth (`free[q] = start`).
  - However, it **synchronises** all qubits it spans, ensuring that operations scheduled after the barrier cannot slide earlier than any operation scheduled before the barrier on those qubits.

---

## 2. Treatment of Measurements and Barriers
- **Non-Unitary Operations**:
  - `measure`, `reset`, and `barrier` are tracked as non-unitary instructions (`NON_UNITARY`).
  - They are excluded from unitary matrix verifications.
- **Preservation During Decomposition**:
  - All measurements, resets, and barriers are copied directly into the decomposed circuit without reordering, modification, or omission.
  - Classical register assignments (`cbits`) and qubit indices (`qubits`) are strictly preserved.

---

## 3. Supported Basis Gate Decomposition Rules
All decomposition rules are mathematically verified against their target gates using `equal_up_to_phase` ($U_{orig} \approx e^{i\theta} U_{decomp}$):

| Gate | Target Decomposition Rule | Notes / Local Qubit Map |
| :--- | :--- | :--- |
| `id` | `x(0) -> x(0)` | Self-inverse identity |
| `x` | `h(0) -> z(0) -> h(0)` | Clifford relationship |
| `y` | `sdg(0) -> x(0) -> s(0)` | $Y = S X S^\dagger$ |
| `z` | `h(0) -> x(0) -> h(0)` | Alternate rule: `s(0) -> s(0)` |
| `cz` | `h(1) -> cx(0, 1) -> h(1)` | Controlled-Z to CNOT |
| `swap` | `cx(0, 1) -> cx(1, 0) -> cx(0, 1)` | Standard 3-CNOT exchange |
| `s` | `t(0) -> t(0)` | Phase $T^2 = S$ |
| `sdg` | `tdg(0) -> tdg(0)` | $(T^\dagger)^2 = S^\dagger$ |
| `ccx` (Toffoli) | 15-gate Clifford+T decomposition | Uses `h`, `cx`, `t`, `tdg` |

---

## 4. Known Limitations
1. **No Parameterised Gates**: Continuous rotation gates (e.g. `rx(θ)`, `ry(θ)`, `rz(θ)`, `u3`) are not decomposed by this discrete Clifford+T engine.
2. **No Classically Conditioned Operations**: Dynamically conditioned gates (`c_if` or mid-circuit classical feedforward) are not modeled.
3. **Discrete Basis Focus**: Targeted at discrete universal fault-tolerant basis sets (e.g., Clifford+T: `{h, cx, t, tdg}`).
