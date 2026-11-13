# Cloud Execution Routing

## Overview
Due to resource constraints on the local development machine (Intel i7-8565U CPU and NVIDIA MX130 GPU), all quantum circuit executions and multi-qubit simulations are routed strictly to external cloud providers (such as [[IBM Quantum]]).

## Guardrails
- **Local Simulation Status**: Disabled permanently.
- **Hardware Protection**: Any direct attempt to spawn local statevector or tensor-network simulators raises `HardwareProtectionError`.
- **Target Backend**: [[IBM Quantum]] Cloud / Qiskit Runtime Service.

## Configuration
- Environment variables configured via `.env` / `.env.example`:
  - `QISKIT_IBM_TOKEN`: API token for IBM Quantum Platform.
  - `QISKIT_IBM_INSTANCE`: Service hub/group/project (default: `ibm-q/open/main`).
  - `ALLOW_LOCAL_SIMULATION`: Set to `false`.

## Related Links
- [[CDAC Quantum Hackathon Overview]]
- [[Qiskit Integration]]
- [[Project Context]]

