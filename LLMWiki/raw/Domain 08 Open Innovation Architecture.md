# Domain 08: Open Innovation in Quantum Computing

## Overview
This project is developed for **Domain 08: Open Innovation in Quantum Computing** at the [[CDAC Quantum Hackathon Overview]].
It focuses on building an interactive, cloud-routed quantum web tool that provides accessible quantum circuit exploration, analysis, and execution while safeguarding local resources.

## System Architecture
The application consists of a decoupled full-stack architecture:
- **Frontend**: Next.js (TypeScript, React, Tailwind CSS) providing an interactive quantum workbench UI.
- **Backend API**: Python REST API (`backend/app.py`) providing circuit validation, template management, and cloud dispatch.
- **Execution & Routing Layer**: [[Cloud Execution Routing]] via Qiskit Runtime Service, strictly routing all quantum computations to [[IBM Quantum]] or remote cloud QPUs.
- **Hardware Protection**: Prohibits local simulation to prevent thermal throttling and bottlenecks on the host Intel i7-8565U CPU and NVIDIA MX130 GPU.

## Key Links
- [[Nextjs and Python API Bridge]]
- [[Cloud Execution Routing]]
- [[Qiskit Integration]]
- [[CDAC Quantum Hackathon Overview]]

