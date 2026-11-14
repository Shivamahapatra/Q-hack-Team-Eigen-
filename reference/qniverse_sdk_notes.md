# Qniverse SDK (QSDK) Reference Notes

This document records the exact classes, methods, signatures, and gate names documented for C-DAC's **Qniverse** platform and **QSDK**, gathered from official public documentation on `https://qniverse.in`.

---

## 1. Classes, Methods, and Signatures

### 1.1 Circuit & Register Creation
* **`QniverseCircuit`**:
  - **Status**: Found (`https://qniverse.in`)
  - **Import**: `from qniverse.circuit import QniverseCircuit` (also documented under `qniverse.api` and `Qniverse.QniverseCircuit`)
  - **Constructor**: `qc = QniverseCircuit()`
  - **Purpose**: Central circuit container for quantum and classical registers, gate operations, and measurements.

* **`QuantumRegister`**:
  - **Status**: Found (`https://qniverse.in`)
  - **Import**: `from qniverse.registers import QuantumRegister` (or `from qniverse.api import QuantumRegister`)
  - **Constructor**: `QuantumRegister(size: int, name: str)`
  - **Rules**: Name prefix must contain alphabetic characters only (no digits or symbols). Indexed like `q[0]`, `q[1]`.

* **`ClassicalRegister`**:
  - **Status**: Found (`https://qniverse.in`)
  - **Import**: `from qniverse.registers import ClassicalRegister` (or `from qniverse.api import ClassicalRegister`)
  - **Constructor**: `ClassicalRegister(size: int, name: str)`
  - **Rules**: Name prefix must be alphabetic. Indexed like `c[0]`, `c[1]`.

* **Adding Registers to Circuit**:
  - **Status**: Found (`https://qniverse.in`)
  - **Method**: `qc.add_register(reg: QuantumRegister | ClassicalRegister)`
  - **Usage**:
    ```python
    qc.add_register(q1)
    qc.add_register(c)
    ```

---

### 1.2 Adding Gates and Operations
* **Method `qc.add_gate()`**:
  - **Status**: Found (`https://qniverse.in`)
  - **Import**: `from qniverse.gates import *`
  - **Signatures & Patterns**:
    - Single-qubit gate: `qc.add_gate(gate, qubit)` e.g. `qc.add_gate(h, q[0])`
    - Two-qubit gate: `qc.add_gate(gate, control_qubit, target_qubit)` e.g. `qc.add_gate(cx, q[0], q[1])`
    - Parameterised gate: `qc.add_gate(gate, qubit, parameter)` (e.g., `rx`, `ry`, `rz` with angle $\theta$)
    - Measurement: `qc.add_gate(measure, qubit, cbit)` e.g. `qc.add_gate(measure, q[0], c[0])`

* **Non-Unitary Instructions**:
  - **`measure`**: Found (`https://qniverse.in`) — `qc.add_gate(measure, q[i], c[j])`
  - **`barrier`**: Found in documentation as an instruction / block preventing compiler reordering (`https://qniverse.in`)
  - **`reset`**: Found in documentation as an instruction bringing a qubit to $|0\rangle$ (`https://qniverse.in`)

---

### 1.3 Reading Gates Back Out & Exporting
* **`qc.qasm()`**:
  - **Status**: Found (`https://qniverse.in`)
  - **Usage**: `qasm_str = qc.qasm()` returns the OpenQASM 2.0 text representation of the circuit.
* **Internal Gate Traversal Attribute (e.g., `qc.gates` / `qc.data`)**:
  - **Status**: Not found in public web documentation.
  - **Note**: The public documentation documents OpenQASM export (`qc.qasm()`) and the high-level `add_gate()` API, but does not publish the internal AST attribute structure. Therefore, extracting gates from an existing `QniverseCircuit` requires parsing its OpenQASM output via `qc.qasm()` as specified in the problem fallback.

---

## 2. Complete List of Supported Gate Names (From Documentation)

As listed in the Qniverse Gates Palette and QSDK documentation (`https://qniverse.in`):

### 2.1 Single-Qubit Gates
* `id` (Identity gate)
* `h` (Hadamard gate)
* `x` (Pauli-X / NOT gate)
* `y` (Pauli-Y gate)
* `z` (Pauli-Z gate)
* `s` (Phase gate / $S$)
* `sdg` ($S^\dagger$)
* `t` ($T$ gate / $\pi/8$)
* `tdg` ($T^\dagger$)

### 2.2 Parameterised / Rotation Gates
* `rx` ($R_x(\theta)$)
* `ry` ($R_y(\theta)$)
* `rz` ($R_z(\theta)$)
* `u1` ($U_1(\lambda)$)
* `u2` ($U_2(\phi, \lambda)$)
* `u3` ($U_3(\theta, \phi, \lambda)$)

### 2.3 Multi-Qubit & Controlled Gates
* `cx` (Controlled-NOT / CNOT)
* `cz` (Controlled-Z)
* `swap` (SWAP gate)
* `ccx` (Toffoli / Controlled-Controlled-NOT)
* `crx` (Controlled $R_x$)
* `cry` (Controlled $R_y$)
* `crz` (Controlled $R_z$)

### 2.4 Non-Unitary Instructions & Blocks
* `measure` (Measurement)
* `barrier` (Compilation barrier)
* `reset` (Qubit reset to $|0\rangle$)
* `qft` (Quantum Fourier Transform block)
* `iqft` (Inverse Quantum Fourier Transform block)

---

## 3. Item-by-Item Verification Summary

| Item | Status | Source URL |
| :--- | :--- | :--- |
| `QniverseCircuit` class | Found | `https://qniverse.in` |
| `QuantumRegister` class | Found | `https://qniverse.in` |
| `ClassicalRegister` class | Found | `https://qniverse.in` |
| `qc.add_register()` method | Found | `https://qniverse.in` |
| `qc.add_gate()` method | Found | `https://qniverse.in` |
| Single-qubit gates (`h`, `x`, `y`, `z`, `s`, `sdg`, `t`, `tdg`, `id`) | Found | `https://qniverse.in` |
| Parameterised gates (`rx`, `ry`, `rz`, `u1`, `u2`, `u3`) | Found | `https://qniverse.in` |
| Two/three-qubit gates (`cx`, `cz`, `swap`, `ccx`) | Found | `https://qniverse.in` |
| Controlled rotations (`crx`, `cry`, `crz`) | Found | `https://qniverse.in` |
| Non-unitary (`measure`, `barrier`, `reset`) | Found | `https://qniverse.in` |
| OpenQASM export (`qc.qasm()`) | Found | `https://qniverse.in` |
| In-memory gate list attribute (e.g., `qc.gates` / `qc.data`) | Not found | N/A (Internal/undocumented in public docs; fallback to OpenQASM parser) |
