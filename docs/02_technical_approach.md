# Technical Approach: QC-C1-01 (Circuit Profiling & Limited Basis-Gate Decomposition)

## 1. Problem Overview (In Simple Words)

In quantum computing, real quantum hardware cannot run every type of gate directly. Each quantum processor only supports a small collection of native gates, called its **basis gate set** (for example: `{rx, ry, rz, cx}`).

**Our Goal for QC-C1-01**:
Build a tool for C-DAC's **Qniverse / QSDK** platform that does two things:
1. **Circuit Profiler**: Takes a quantum circuit and calculates its vital stats (how many qubits it uses, how many gates it has, and how deep/long it is).
2. **Basis Decomposer**: Takes a user-selected list of allowed gates (the basis set) and breaks down any non-basis gates into equivalent supported gates, returning a fresh new circuit without touching the original.

---

## 2. Part 1: Circuit Profiler (Resource Counter)

The profiler inspects the circuit and outputs a clear report with the following metrics:

### The Metrics We Report:
- **Qubits Declared vs Used**: Total qubits allocated in the circuit vs how many actually have gates applied.
- **Total Gate Count**: Sum of all quantum operations.
- **Gate Breakdown**: Exact count of each gate type (e.g., 4 Hadamards, 2 CNOTs, 1 Rz).
- **Single-Qubit vs Multi-Qubit Gates**: Separate counts for 1-qubit operations and entangling multi-qubit gates (like CX/CNOT, CZ, SWAP).
- **Two-Qubit Gate Count**: Specifically counts 2-qubit interactions (the most error-prone operations on real hardware).
- **Circuit Depth**: The number of parallel time steps the circuit takes to run from start to finish.

### How Circuit Depth is Calculated (Earliest-Layer Rule)
Think of depth as time moving from left to right:
- **Disjoint Qubits run in Parallel**: If a gate runs on Qubit 0 and another gate runs on Qubit 1 at the same time, they share the same layer (Depth = 1).
- **Shared Qubits must Wait**: If two gates act on the same Qubit 0, the second gate must wait for the first to finish (Depth = 2).
- **Multi-Qubit Gates sync wires**: A CNOT on Qubit 0 and Qubit 1 occupies a layer across both qubits. Both qubits advance to that new layer together.
- **Total Depth**: The layer number reached by the slowest qubit wire.

---

## 3. Part 2: Limited Basis-Gate Decomposition

The user provides a target basis set (e.g., `['rx', 'ry', 'rz', 'cx']` or `['h', 't', 'cx']`).

For every gate in the circuit:
1. **Already in Basis?**  
   If the gate is already in the target set, keep it as-is.
2. **Supported for Decomposition?**  
   If the gate is not in the basis, replace it with equivalent gates from the allowed set.
   - Example 1: Replace an `X` gate with a rotation: `Rx(pi)`.
   - Example 2: Replace an `H` (Hadamard) gate with rotation gates: `Rz(pi/2) -> Rx(pi/2) -> Rz(pi/2)`.
   - Example 3: Replace a `SWAP` gate between two qubits with 3 CNOT gates: `CX -> CX -> CX`.
3. **Unsupported Gate?**  
   If a gate cannot be converted into the requested basis, the tool **stops and reports an explicit error**. It will never secretly produce a broken or inaccurate circuit.

---

## 4. Key Rules and Guarantees (For Viva Evaluation)

When explaining this solution to the judges, highlight these three guarantees:

1. **Non-Mutating (Safe Input)**:  
   The original input circuit is never modified. The decomposer always returns a brand new `QniverseCircuit` object.
2. **Preserves Non-Unitary Operations**:  
   Measurements, resets, and barriers are copied over in their exact positions and order—never dropped or reordered.
3. **Before-and-After Comparison**:  
   The tool generates a structured profile report comparing metrics **before** decomposition vs **after** decomposition so users can see how gate counts and depth expanded to fit the hardware.
