# Team Information

## Team Overview
- **Team Name**: Team Eigen
- **Institution**: PES University (PESU), Bengaluru
- **Event**: PESU - C-DAC Quantum Hackathon 2026
- **Target Platform**: C-DAC Qniverse (QSDK / Python Environment)

---

## Selected Problem Statements
Team Eigen is implementing an integrated, modular Quantum Compilation & Optimization Toolkit addressing three interconnected challenges:

1. **QC-C1-01 | Circuit Profiling and Limited Basis-Gate Decomposition**
   - Calculation of circuit metrics (total gate counts, 1-qubit & 2-qubit breakdown, earliest-available-layer scheduled depth).
   - Equivalence-preserving decomposition into user-specified basis gate sets (e.g., `{u3, cx}`, `{rx, ry, rz, cx}`).
2. **QC-C2-04 | OpenQASM 2.0/3.0 to QniverseCircuit Converter**
   - High-fidelity parser translating OpenQASM 2.0 and 3.0 programs directly into native `QniverseCircuit` objects.
   - Preserves qubit registers, gate parameters, barriers, and measurement semantics with clear diagnostic reporting.
3. **QC-03-03 | Quantum Circuit Optimization Using QSDK**
   - Rule-based circuit optimization engine applying safe local rewrite passes (identity gate removal, adjacent self-inverse cancellation, adjacent identical CX cancellation).
   - Preserves circuit semantics, classical dependencies, and barriers without mutating the source circuit.

---

## Team Members and Roles

| Name | GitHub Username | Role & Primary Responsibilities |
| :--- | :--- | :--- |
| **Dhruti** | `dhruti218` | **Quantum Software Developer**: Profiler implementation, basis gate decomposition algorithms, local setup, and AI compliance logging. |
| **Advik Singla** | `adviksingla` | **Core Developer**: OpenQASM parsing engine, circuit synthesis, optimization pass logic, and test suites. |
| **Saumitra Gupta** | `saumitraguptafr` | **Lead Presenter & Documentation Specialist**: Viva preparation, technical documentation, slide deck, and judge presentation. |
| **Shiva Mahapatra** | `Shivamahapatra` | **Repository Lead & Platform Coordinator**: Repository hygiene, Qniverse platform integration, benchmarking, and review approvals. |

---

## Collaboration & Governance
- **Branching Model**: Dedicated feature branches (`<name>/<feature>`) off `main`. Direct pushes to `main` are strictly prohibited.
- **Code Review**: All merges require a Pull Request (PR) with at least one peer approval.
- **AI Compliance**: Every AI-assisted contribution is logged in [`docs/05_ai_usage_declaration.md`](05_ai_usage_declaration.md) with tool and model names in accordance with hackathon rules.
