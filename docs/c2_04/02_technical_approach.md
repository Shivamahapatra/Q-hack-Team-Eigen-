# Technical Approach: QC-C2-04 (OpenQASM 2.0/3.0 to Qniverse Circuit Converter)

## 1. Problem Overview & Scope

OpenQASM (Open Quantum Assembly Language) is the de facto standard intermediate representation across the quantum computing ecosystem. However, quantum hardware backends and simulation environments—such as C-DAC's **Qniverse QSDK**—utilize native object-oriented circuit abstractions (`QniverseCircuit`).

### QC-C2-04 Objectives:
1. **Universal Ingestion**: Accept OpenQASM 2.0 and OpenQASM 3.0 source code supplied as a raw string through a unified interface `convert_qasm(qasm_str, version=None)`.
2. **Deterministic Mapping**: Correctly map supported quantum/classical registers, single-qubit gates, multi-qubit gates, parameterized rotations, barriers, and measurements to `QniverseCircuit` calls.
3. **Semantic Preservation**: Guarantee 100% preservation of qubit indices, wire ordering, gate parameters (evaluating expressions like $\pi/2$), execution sequence, and measurement destinations.
4. **Actionable Diagnostics**: Provide clear, informative error reporting for malformed syntax, unregistered qubits, out-of-range indexing, and explicit warnings for unsupported dynamic constructs.
5. **Strict QSDK Compliance**: Construct circuits exclusively through documented Qniverse QSDK APIs without assuming private or undocumented internals, providing an offline fallback for testing outside Qniverse.

---

## 2. Architecture & Processing Pipeline

```
+--------------------------------------------------------------------------+
|                    Input: OpenQASM Source Code (String)                  |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                      Stage 1: Version Identification                     |
|           - Explicit argument OR regex header detection                  |
|           - "OPENQASM 2.0;" vs "OPENQASM 3.0;" / "OPENQASM 3;"           |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Stage 2: Lexical Analysis & Tokenizer                  |
|           - Comment stripping (`// ...` and `/* ... */`)                 |
|           - Semicolon-delimited statement tokenization                   |
|           - Parameter expression isolation (`gate(param) q;`)            |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                 Stage 3: Abstract Syntax & IR Generation                 |
|           - Register Cataloging: global qubit/cbit offsets               |
|           - AST Op Representation: Op(name, qubits, params, cbits)       |
|           - Expression Evaluator: safe math parsing for pi, / , *        |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                 Stage 4: Semantic Validation & Diagnostics               |
|           - Qubit index boundary verification                            |
|           - Distinct operand check in multi-qubit gates                  |
|           - Warning logger for unsupported statements                    |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|               Stage 5: Qniverse Circuit Synthesis & Output               |
|     - Instantiates QuantumRegister / ClassicalRegister / QniverseCircuit |
|     - Emits `(circuit_object, conversion_report_dict)`                   |
+--------------------------------------------------------------------------+
```

---

## 3. Supported QASM Grammar & Dialect Mapping

### 3.1 Version Detection
- **OpenQASM 2.0**: Indicated by `OPENQASM 2.0;` at file start. Uses `qreg name[size];` and `creg name[size];`.
- **OpenQASM 3.0**: Indicated by `OPENQASM 3.0;` or `OPENQASM 3;`. Uses modern `qubit[size] name;` and `bit[size] name;` as well as legacy `qreg`/`creg`.
- **Auto-detection**: If `version` is not explicitly supplied, the engine inspects the header declaration and falls back to structural grammar heuristics.

### 3.2 Register Mapping & Multi-Register Offset Table
In OpenQASM, circuits may declare multiple disjoint registers (e.g., `qreg a[2]; qreg b[3];`).
- The converter maintains a **Register Catalog** mapping `(reg_name, index)` to global sequential wire index $0, 1, \dots, N-1$.
- Standalone 1D qubit references (e.g., QASM 3 `qubit[5] q;` or bare `q[i]`) are automatically resolved to contiguous indices.

### 3.3 Gate Set Translation Matrix

| Category | QASM Operation | Parameters | Target Qniverse Method | Mathematical Unitary |
| :--- | :--- | :--- | :--- | :--- |
| **Pauli & Cliffords** | `h q;` | None | `circuit.h(q)` | $\frac{1}{\sqrt{2}}\begin{bmatrix}1 & 1 \\ 1 & -1\end{bmatrix}$ |
| | `x q;` | None | `circuit.x(q)` | $\begin{bmatrix}0 & 1 \\ 1 & 0\end{bmatrix}$ |
| | `y q;` | None | `circuit.y(q)` | $\begin{bmatrix}0 & -i \\ i & 0\end{bmatrix}$ |
| | `z q;` | None | `circuit.z(q)` | $\begin{bmatrix}1 & 0 \\ 0 & -1\end{bmatrix}$ |
| | `s q;` / `sdg q;` | None | `circuit.s(q)` / `circuit.sdg(q)` | $\text{diag}(1, i)$ / $\text{diag}(1, -i)$ |
| | `t q;` / `tdg q;` | None | `circuit.t(q)` / `circuit.tdg(q)` | $\text{diag}(1, e^{i\pi/4})$ |
| | `id q;` | None | `circuit.id(q)` (or skip) | $I_2$ |
| **Entangling Gates** | `cx c, t;` | None | `circuit.cx(c, t)` | Controlled-NOT |
| | `cz c, t;` | None | `circuit.cz(c, t)` | Controlled-Z |
| | `swap a, b;` | None | `circuit.swap(a, b)` | Swap two qubit states |
| | `ccx a, b, c;`| None | `circuit.ccx(a, b, c)` | Toffoli (Controlled-Controlled-X)|
| **Rotations** | `rx(theta) q;` | $\theta$ | `circuit.rx(theta, q)` | $e^{-i \frac{\theta}{2} X}$ |
| | `ry(theta) q;` | $\theta$ | `circuit.ry(theta, q)` | $e^{-i \frac{\theta}{2} Y}$ |
| | `rz(theta) q;` | $\theta$ | `circuit.rz(theta, q)` | $e^{-i \frac{\theta}{2} Z}$ |
| | `p(lambda) q;` | $\lambda$ | `circuit.p(lambda, q)` | $\text{diag}(1, e^{i\lambda})$ |
| | `u3(th, ph, lm) q;` | $\theta, \phi, \lambda$ | `circuit.u3(th, ph, lm, q)` | Standard arbitrary single-qubit Euler unitary |
| **Non-Unitary** | `barrier q0, q1;`| None | `circuit.barrier([q0, q1])` | Synchronization barrier |
| | `measure q -> c;`| None | `circuit.measure(q, c)` | Computational basis readout |
| | `reset q;` | None | `circuit.reset(q)` | $|0\rangle$ state initialization |

### 3.4 Parameter Expression Parser
QASM files often contain parameterized angles written as arithmetic expressions:
- Examples: `rx(pi/2) q;`, `rz(2*pi) q;`, `u3(pi/4, -pi/2, 0) q;`
- The parser implements a safe, sandboxed mathematical expression evaluator supporting `pi`, `+`, `-`, `*`, `/`, and floating point numbers without using unsafe `eval()`.

---

## 4. Diagnostics & Validation Engine

The converter enforces strict validation:
1. **Declaration Before Use**: Any gate operation referencing an undeclared register immediately raises a clear diagnostic error with line number and token context.
2. **Index Bounds Checking**: Checks that index $i$ in $q[i]$ satisfies $0 \le i < \text{size}$.
3. **Operand Disjointness**: For multi-qubit gates (e.g., `cx q[0], q[0];`), raises a validation error for identical control and target wires.
4. **Graceful Warnings for Unsupported Statements**:
   - Advanced QASM 3 classical features (such as `for` loops, classical branching `if`, `defcal` pulses) are flagged in the `warnings` and `unsupported_statements` fields of the conversion report without crashing standard circuit synthesis.

---

## 5. Verification & Semantic Equivalence Methodology

To verify that the resulting `QniverseCircuit` is mathematically equivalent to the original QASM input:
1. **Matrix Invariance**: For small circuits ($n \le 5$), simulate the unitary matrix $U_{\text{src}}$ from parsed QASM AST and compare against the unitary matrix $U_{\text{dst}}$ of the reconstructed `QniverseCircuit` up to global phase:
   $$| \text{Tr}(U_{\text{src}}^\dagger U_{\text{dst}}) | = 2^n$$
2. **Statevector Fidelity**: Simulate state outputs for canonical test states ($|00\dots0\rangle$, $|++\dots+\rangle$) and ensure output fidelity $F \ge 1 - 10^{-7}$.
3. **Roundtrip Invariance**: Re-export QASM from the generated `QniverseCircuit` (`circuit.qasm()`) and verify topological equivalence of operations.
