# Working Product: QC-C1-01 Profiler & Decomposer

## 1. Product Summary

**Module**: `QC-C1-01` Quantum Circuit Profiler and Limited Basis-Gate Decomposition  
**Entry File**: [`src/qc_c1_01.py`](file:///C:/Users/DELL/.gemini/antigravity/scratch/Q-hack-Team-Eigen-/src/qc_c1_01.py)  
**Compatibility**: Native C-DAC Qniverse QSDK (`QniverseCircuit`) with OpenQASM 2.0 fallback.

The product provides an automated pipeline for quantum circuit analysis and hardware basis compilation:
1. **Profiler**: Analyzes circuit resource footprint and calculates exact execution depth via earliest-available-layer DAG scheduling.
2. **Decomposer**: Translates arbitrary non-basis gates into target hardware-supported basis sets using recursive expansion rules.
3. **Safety Engine**: Validates unitary equivalence, catches cyclic expansion, preserves non-unitary operators (barriers, measurements, resets), and strictly enforces input immutability.

---

## 2. Setup & Installation

### Prerequisites
- Python 3.10 or newer (tested on Python 3.11.9)
- Dependencies installed from `requirements.txt`:
  ```powershell
  pip install -r requirements.txt
  ```

### Activating the Virtual Environment
```powershell
# In PowerShell:
.\.venv\Scripts\Activate.ps1
```

---

## 3. How to Run

### Run All Built-in Unit Tests & Demonstration
To execute the automated test suite and view a sample decomposition report:
```powershell
python src/qc_c1_01.py
```

Expected output:
```
all tests passed
{
  "basis": ["cx", "h"],
  "before": {
    "total_gates": 2,
    "by_type": {"h": 1, "swap": 1},
    "qubits_declared": 2,
    "qubits_used": 2,
    "single_qubit_gates": 1,
    "multi_qubit_gates": 1,
    "two_qubit_gates": 1,
    "depth": 3,
    "measurements": 1
  },
  "unsupported": [],
  "after": {
    "total_gates": 4,
    "by_type": {"h": 1, "cx": 3},
    "qubits_declared": 2,
    "qubits_used": 2,
    "single_qubit_gates": 1,
    "multi_qubit_gates": 3,
    "two_qubit_gates": 3,
    "depth": 5,
    "measurements": 1
  },
  "status": "OK"
}
```

---

## 4. Python API Usage

You can import and use the tool directly in your own scripts or Jupyter notebooks:

```python
from src.qc_c1_01 import Op, profile, decompose, analyze

# 1. Define operations
circuit_ops = [
    Op("h", (0,)),
    Op("swap", (0, 1)),
    Op("measure", (0,), (0,))
]

# 2. Profile circuit metrics
metrics = profile(circuit_ops, num_qubits_declared=2)
print("Total gates:", metrics["total_gates"])
print("Circuit depth:", metrics["depth"])

# 3. Decompose into target basis ['cx', 'h']
decomposed_ops, report = decompose(circuit_ops, num_qubits_declared=2, basis={"h", "cx"})

# 4. End-to-end analyze from QASM or QniverseCircuit
qasm_str = """
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
h q[0];
cx q[0], q[1];
"""
new_circuit, report = analyze(qasm_str, basis={"h", "cx"})
```

---

## 5. Viva Demonstration Script (For the Judges)

When presenting to the evaluation panel, Saumitra and Dhruti can demonstrate the core deliverables in 4 quick steps:

### Step 1: Explain Earliest-Available-Layer Depth
- **Code**: `chain = [Op("h", (0,)), Op("cx", (0, 1)), Op("x", (1,))]` vs `disjoint = [Op("h", (0,)), Op("h", (1,)), Op("h", (2,))]`
- **Explanation**: Dependent gates wait in series ($Depth = 3$). Disjoint gates execute in parallel in the exact same layer ($Depth = 1$).

### Step 2: Demonstrate Basis Decomposition
- **Code**: Decompose `SWAP(0, 1)` into basis `{h, cx}`.
- **Explanation**: Show how the SWAP is cleanly expanded into 3 CNOT gates (`CX(0,1) -> CX(1,0) -> CX(0,1)`). The report shows total gate count increasing from 2 to 4 while preserving the measurement intact.

### Step 3: Demonstrate Immutability & Error Rejection
- **Code**: Request decomposition into an incompatible basis: `decompose(circuit, basis={"h"})`.
- **Explanation**: The tool returns `status: FAILED: unsupported operations, no circuit emitted`, identifies the offending gate (`swap`), returns `None`, and leaves the input circuit completely unmutated.

### Step 4: Mathematical Equivalence
- **Code**: `equal_up_to_phase(unitary(orig), unitary(decomposed))`
- **Explanation**: Proves matrix fidelity $|\text{Tr}(U^\dagger V)| / 2^n = 1.0$ across all 9 elementary gate decomposition rules.
