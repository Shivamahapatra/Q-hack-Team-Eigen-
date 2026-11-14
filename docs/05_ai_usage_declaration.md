# AI Usage Declaration

## Overview
This document records all AI tool interactions, models used, and artifacts generated during the PESU - C-DAC Quantum Hackathon 2026.

## AI Usage Log

| Date / Time | Task | AI Tool | Model Used | What It Produced |
| :--- | :--- | :--- | :--- | :--- |
| 2026-11-14 10:15 IST | QC-C1-01 Decomposer & Qniverse SDK Bridge | Antigravity | Gemini 3.8 Flash | SDK reference notes, OpenQASM parser fallback, to_qniverse() bridge, test suite, demo, and documentation notes |
| 2026-11-14 12:40 IST | QC-03-03 Quantum Circuit Optimizer | Antigravity | Gemini 3.8 Flash | Conservative optimizer pipeline (`src/c3-03/optimizer.py`), 19 unit tests (`src/c3-03/test_optimizer.py`), executable demo (`src/c3-03/demo.py`), and documentation (`src/c3-03/README.md`) |
| 2026-11-14 14:30 IST | QC-03-03 Comprehensive Adversarial Review | Antigravity | Gemini 3.8 Flash | Full adversarial audit report against problem statement requirements A-J, top 5 risks, missing tests, and verification test outputs |
| 2026-11-14 14:55 IST | QC-03-03 Defect Resolution & Safety Hardening | Antigravity | Gemini 3.8 Flash | Implemented Priorities 1-5: per-wire frontier adjacency, verified Qniverse imports, backend status transparency (qniverse vs fallback), conditional circuit bypass handling, expanded self-inverse/inverse-pair rules (Y, CY, CZ, CH, SWAP, CCX, CSWAP, S/SDG, T/TDG), 67 automated unit tests, and documentation |
| 2026-11-14 15:20 IST | QC-03-03 Real SDK Wide Barrier Decomposer & Rejection Transparency | Antigravity | Gemini 3.8 Flash | Implemented 2-qubit forward-backward chain decomposition for >2-qubit barriers to respect Qniverse hardware constraint, verified profiler depth invariance, captured explicit SDK rebuild exceptions in `fallback_reason`, added 7 unit tests (74 total), and resolved Jupyter notebook `__file__` execution error. |
| 2026-11-14 15:33 IST | QC-03-03 ASCII Circuit Visualizer & Depth Alignment Verification | Antigravity | Gemini 3.8 Flash | Implemented `draw_text(ops, num_qubits)` ASCII circuit renderer in `src/c3-03/` with chronological depth-layer scheduling, multi-qubit symbol mapping (`@`, `(+)`, `x`), vertical barrier markers (`|`), integrated before/after diagram rendering into `src/c3-03/demo.py`, and added 4 unit tests (78 total) verifying column count matches circuit depth. |
