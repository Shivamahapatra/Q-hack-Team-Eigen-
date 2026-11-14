# Project Context: C-DAC Quantum Hackathon 2026

## Team Overview
- **Team**: Team Eigen
- **Institution**: PES University (PESU)
- **Event**: C-DAC Quantum Hackathon 2026
- **Target Platform**: Qniverse

## Repository Status
- Current branch: `main`
- Completed challenge: **QC-C1-01: Circuit Profiling and Limited Basis-Gate Decomposition**
- Completed challenge: **QC-03-03: Quantum Circuit Optimization Using QSDK**
- Target platform: C-DAC Qniverse (QSDK)

## Project Structure
- `src/c1_01_final.py` (alias `src/c1_01final.py`): Core profiler, rules engine, unitary verifier, and Qniverse bridges.
- `src/qniverse_adapter.py`: QniverseCircuit in-memory operations adapter.
- `src/c3-03/`:
  - `__init__.py`: Package declarations and exports.
  - `optimizer.py`: Conservative, pass-based optimizer (Identity removal, X-X / H-H / Z-Z cancellation, CX cancellation).
  - `test_optimizer.py`: 19 automated unit tests verifying identity removal, self-inverse, CX, safety, non-mutation, config, edge cases, and equivalence.
  - `demo.py`: Executable demonstration script (Case A: 77.78% reduction; Case B: optimal no-change).
  - `README.md`: Technical documentation, API, preconditions, and metrics.
- `tests/test_c1_01.py`: Unit tests covering single-qubit, two-qubit, disjoint, dependent, decomposition, unsupported ops, and immutability.
- `examples/c1_01_demo.py`: Executable demo script producing before/after metrics.
- `results/c1_01_report.json`: Saved output report from demo run.
- `reference/qniverse_sdk_notes.md`: Documented Qniverse SDK classes, methods, and gates.
- `docs/c1_01_notes.md`: Technical documentation of depth definition, rules, and limitations.
- `docs/05_ai_usage_declaration.md`: Log of AI tool usage.
