# Team Information - Team Eigen (QC-03-03)

## Team Overview
- **Team Name**: Team Eigen
- **Institution**: PES University (PESU), Bengaluru
- **Event**: PESU - C-DAC Quantum Hackathon 2026
- **Target Platform**: C-DAC Qniverse Platform & QSDK
- **Challenge**:
  - **QC-03-03**: Quantum Circuit Optimization Using QSDK (Class III)
- **Track Scope**:
  Build a high-performance quantum circuit optimization module that accepts a `QniverseCircuit`, applies a documented set of safe, local circuit rewrite passes (identity removal, self-inverse gate cancellation, adjacent identical CX cancellation, phase merging), and returns a fresh, valid `QniverseCircuit` without mutating the input, with full before-and-after gate count and depth profiling.

---

## Team Members

| Name | GitHub Username | Role | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **Advik Singla** | `adviksingla` | **Team Leader** & Core Developer | Technical direction, task coordination, commutative commutation rules, unitary invariance verification, PR approvals. |
| **Shiva Mahapatra** | `Shivamahapatra` | Lead Developer (Architecture & Optimization Passes) | Pass manager design, DAG-based gate cancellation engine, Qniverse QSDK circuit reconstruction, repository administration. |
| **Dhruti** | `dhruti218` | Documentation & Compliance Lead | Architecture documentation, AI usage compliance, test validation matrices, Git workflow hygiene, report drafting. |
| **Saumitra Gupta** | `saumitraguptafr` | Presenter & Evaluation Lead | Technical presentation, live demonstration scripts, benchmark validation against C-DAC hackathon criteria, jury walkthrough. |

---

## Roles and Responsibilities Matrix

### 1. Advik Singla (Team Leader & Core Developer)
- Direct mathematical formulation for identity elimination and self-inverse gate cancellation ($U \cdot U^\dagger = I$).
- Formulate commutation analysis allowing gates on disjoint qubits to commute safely past each other during optimization scans.
- Validate unitary matrix equivalence between unoptimized and optimized circuits ($U_{\text{opt}} = U_{\text{orig}}$).

### 2. Shiva Mahapatra (Lead Developer - Architecture & Optimization Passes)
- Implement non-mutating `optimize_circuit(circuit, passes=None)` engine returning a new `QniverseCircuit` while leaving input untouched.
- Implement individual rewrite passes: `RemoveIdentities`, `CancelSelfInverse`, `CancelAdjacentCX`, and `MergeRotationAngles`.
- Enforce strict barrier, measurement, and reset fences preventing illegal cancellations across synchronization points.

### 3. Dhruti (Documentation, QA & Compliance Lead)
- Maintain and curate all documentation across `docs/c3_03/` (`01_team_info.md`, `02_technical_approach.md`, `03_performance_report.md`, `04_working_product.md`, `05_ai_usage_declaration.md`).
- Maintain the official AI usage declaration log for C3-03 tracking all prompts, models, and contributor attributions.
- Execute validation test suites on both local Python and Qniverse target environments.

### 4. Saumitra Gupta (Presenter & Demonstration Lead)
- Design live evaluation walkthroughs demonstrating dramatic gate count and depth reductions across redundant benchmark circuits.
- Explain non-mutating guarantees, barrier safety, and QSDK compliance during judge reviews.
