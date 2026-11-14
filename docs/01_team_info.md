# Team Information - Team Eigen

## Team Overview
- **Team Name**: Team Eigen
- **Institution**: PES University (PESU), Bengaluru
- **Event**: PESU - C-DAC Quantum Hackathon 2026
- **Target Platform**: C-DAC Qniverse Platform & QSDK
- **Current Primary Challenge**:
  - **QC-C1-01**: Circuit Profiling and Limited Basis-Gate Decomposition (Class I)
- **Additional Track Roadmap**:
  - **QC-C2-04**: OpenQASM 2.0/3.0 to QniverseCircuit Converter (Class II)
  - **QC-03-03**: Quantum Circuit Optimization Using QSDK (Class III)

Together, these three problem statements form an integrated, end-to-end **Quantum Compilation, Optimization, and Profiling Suite** for C-DAC's Qniverse platform.

---

## Team Members

| Name | GitHub Username | Role | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **Dhruti** | `dhruti218` | Documentation & Compliance Lead | Architecture documentation, AI usage compliance, test validation, Git workflow hygiene, report drafting. |
| **Shiva Mahapatra** | `Shivamahapatra` | Lead Developer (Coding) | Core QSDK integration, QASM parsing engine, circuit synthesis, repository administration. |
| **Advik Singla** | `adviksingla` | Core Developer (Coding) | Circuit optimization passes, rewrite rule engine, basis-gate decomposition algorithms, unit testing. |
| **Saumitra Gupta** | `saumitraguptafr` | Presenter & Evaluation Lead | Viva presentation, demonstration script, problem validation against hackathon requirements, judge walkthrough. |

---

## Roles and Responsibilities Matrix

### 1. Dhruti (Documentation, QA & Compliance Lead)
- Maintain and curate all repository documentation across `docs/` (`01_team_info.md`, `02_technical_approach.md`, `03_performance_report.md`, `04_working_product.md`, `05_ai_usage_declaration.md`).
- Ensure 100% adherence to hackathon AI declaration policies and maintain the real-time AI usage log.
- Verify environment reproducibility on local and Qniverse environments.
- Conduct code reviews on documentation PRs and enforce branch hygiene (`no direct pushes to main`).

### 2. Shiva Mahapatra (Lead Developer - Architecture & Parser)
- Architect the shared circuit representation layer compatible with Qniverse QSDK.
- Implement QC-C2-04: OpenQASM 2.0 / 3.0 parsing engine and conversion to native `QniverseCircuit` objects.
- Manage repository settings, branching policies, and pull request reviews.

### 3. Advik Singla (Developer - Optimization & Profiling Engine)
- Implement QC-03-03: Rule-based circuit optimization engine (identity cancellation, adjacent self-inverse cancellation, CX cancellation).
- Implement QC-C1-01: Earliest-available-layer DAG scheduler for circuit depth profiling and target basis-gate decomposition.
- Develop unit tests and verify physical non-mutating guarantees.

### 4. Saumitra Gupta (Presenter & Demonstration Lead)
- Formulate the viva presentation narrative and technical slide deck/walkthrough.
- Design live demonstration scripts proving input-output correctness across all three problem statements.
- Coordinate with judges during evaluations, explaining algorithmic tradeoffs and Qniverse platform integration.
