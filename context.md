# Project Context: C-DAC Quantum Hackathon 2026

## Team Overview
- **Team**: Team Eigen
- **Institution**: PES University (PESU)
- **Event**: C-DAC Quantum Hackathon 2026
- **Target Platform**: Qniverse

## Repository Status
- Current branch: `main` (feature branch `snehasish/c1-01` merged and pushed)
- Problem in progress: **QC-C1-01: Circuit Profiling and Limited Basis-Gate Decomposition**
- Core profiler, Qniverse in-memory adapter (`src/qniverse_adapter.py`), OpenQASM converter fallback (`from_qniverse`), SDK constructor (`to_qniverse`), matrix verifier, test suite, and demo merged into `main`.
- Target platform: C-DAC Qniverse (QSDK)

## Project Structure
- `src/c1_01_final.py` (alias `src/c1_01final.py`): Core profiler, rules engine, unitary verifier, and Qniverse bridges.
- `src/qniverse_adapter.py`: QniverseCircuit in-memory operations adapter.
- `tests/test_c1_01.py`: Unit tests covering single-qubit, two-qubit, disjoint, dependent, decomposition, unsupported ops, and immutability.
- `examples/c1_01_demo.py`: Executable demo script producing before/after metrics.
- `results/c1_01_report.json`: Saved output report from demo run.
- `reference/qniverse_sdk_notes.md`: Documented Qniverse SDK classes, methods, and gates.
- `docs/c1_01_notes.md`: Technical documentation of depth definition, rules, and limitations.
- `docs/05_ai_usage_declaration.md`: Log of AI tool usage.
