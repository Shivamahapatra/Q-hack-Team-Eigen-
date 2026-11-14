# AI Usage Declaration - Team Eigen (QC-03-03)

## Overview
In accordance with the regulations of the **PESU – C-DAC Quantum Hackathon 2026**, Team Eigen declares all instances of Artificial Intelligence tools and foundation models used during the development of **QC-03-03: Quantum Circuit Optimization Using QSDK**.

All AI interactions are logged with exact timestamps, contributor attribution, AI tool and model names, and specific outputs produced.

---

## AI Usage Log

| Date / Time | Member | Task | AI Tool | Model Used | What It Produced |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2026-11-14 15:50** | Dhruti | Track Scoping & Document Suite Initialization | Antigravity | Gemini 3.8 Flash | Initialized documentation suite for QC-03-03 across `docs/c3_03/` (`01_team_info.md` to `05_ai_usage_declaration.md`). |
| **2026-11-14 16:00** | Shiva | Non-Mutating Pass Manager Architecture | Claude | Claude 3.7 Sonnet | Designed `optimize_circuit()` non-mutating pipeline and fixed-point pass loop. |
| **2026-11-14 16:10** | Advik | Commutation Analysis & Self-Inverse Rules | ChatGPT | GPT-4o | Formulated backward scan algorithm for self-inverse cancellation ($X-X, H-H, Z-Z, CX-CX$) commuting safely across disjoint wires. |
| **2026-11-14 16:15** | Saumitra | Fence Barrier Test Matrix & Reduction Scenarios | Gemini | Gemini 1.5 Pro | Formulated barrier safety verification cases ensuring synchronization points prevent illegal gate merges. |
| **2026-11-14 16:20** | Shiva | Continuous Rotation Merging Pass | Claude | Claude 3.7 Sonnet | Implemented $R_x, R_y, R_z$ angle accumulation pass with modulo $2\pi$ simplification. |
| **2026-11-14 16:25** | Dhruti | Integration, Benchmarks & Final Documentation | Antigravity | Gemini 3.8 Flash | Consolidated optimizer engine in `src/qc_c3_03.py`, verified unit test execution, and compiled metrics report. |
