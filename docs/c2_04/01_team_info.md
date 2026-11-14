# Team Information - Team Eigen (QC-C2-04)

## Team Overview
- **Team Name**: Team Eigen
- **Institution**: PES University (PESU), Bengaluru
- **Event**: PESU - C-DAC Quantum Hackathon 2026
- **Target Platform**: C-DAC Qniverse Platform & QSDK
- **Challenge**:
  - **QC-C2-04**: OpenQASM 2.0/3.0 to Qniverse Circuit Converter (Class II)
- **Track Scope**:
  Develop a robust, production-grade converter that accepts OpenQASM 2.0 or OpenQASM 3.0 source code as a string and returns an equivalent `QniverseCircuit` object using documented Qniverse QSDK interfaces, preserving all quantum semantics, registers, parameters, barriers, and measurement mappings.

---

## Team Members

| Name | GitHub Username | Role | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **Advik Singla** | `adviksingla` | **Team Leader** & Core Developer | Technical direction, task coordination, grammar validation, semantic equivalence verification, PR approvals. |
| **Shiva Mahapatra** | `Shivamahapatra` | Lead Developer (Architecture & Converter Engine) | AST parser design, OpenQASM 2.0/3.0 dialect handling, Qniverse QSDK API integration, repository administration. |
| **Dhruti** | `dhruti218` | Documentation & Compliance Lead | Architecture documentation, AI usage compliance, test validation matrices, Git workflow hygiene, report drafting. |
| **Saumitra Gupta** | `saumitraguptafr` | Presenter & Evaluation Lead | Technical presentation, live demonstration scripts, benchmark validation against C-DAC hackathon criteria, jury walkthrough. |

---

## Roles and Responsibilities Matrix

### 1. Advik Singla (Team Leader & Core Developer)
- Direct algorithmic approach for syntax analysis and QASM 2.0 vs 3.0 feature detection.
- Formulate verification routines comparing statevectors and unitaries between input QASM strings and output `QniverseCircuit` objects.
- Ensure strict adherence to hackathon evaluation guidelines and approve team pull requests.

### 2. Shiva Mahapatra (Lead Developer - Architecture & Ingestion)
- Develop the core parsing engine supporting register declarations (`qreg`, `creg`, `qubit`, `bit`), standard gates, parameterized gates, barriers, and measurements.
- Map parsed statements to native `qniverse.circuit.QniverseCircuit` calls with documented interfaces and robust offline mock fallback.
- Enforce strict typing, index bounds checking, and graceful error reporting for unsupported syntax.

### 3. Dhruti (Documentation, QA & Compliance Lead)
- Maintain and curate all documentation across `docs/c2_04/` (`01_team_info.md`, `02_technical_approach.md`, `03_performance_report.md`, `04_working_product.md`, `05_ai_usage_declaration.md`).
- Maintain the real-time AI usage declaration log for C2-04 with model specifications and contributor attributions.
- Execute validation test suites on both local Python and Qniverse target environments.

### 4. Saumitra Gupta (Presenter & Demonstration Lead)
- Prepare demonstration workflows showcasing seamless conversion of complex QASM 2.0/3.0 algorithms (e.g., Bell State, GHZ, QFT, Teleportation, Grover iterations).
- Detail actionable diagnostics, warnings for unsupported statements, and semantic fidelity proofs during judge reviews.
