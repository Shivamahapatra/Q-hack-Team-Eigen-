# Project Context: C-DAC Quantum Hackathon

## Overview
This repository hosts the project for the **C-DAC Quantum Hackathon**.

## Hackathon Target
- **Selected Domain**: Domain 08: Open Innovation in Quantum Computing
- **Project Type**: Full-Stack Quantum Web Tool (Next.js UI + Python Cloud Routing Backend)

## Architecture & Boundaries
- Application root: `c:\Users\PC\Documents\Q hackthon\`
  - `frontend/`: Next.js interactive web interface (React, TypeScript, Tailwind CSS)
  - `backend/`: Python REST API (`app.py`, `execution_router.py`)
- `LLMWiki/`: Second brain / knowledge base and research documentation.
  - `LLMWiki/raw/`: Generated artifacts, implementation plans, notes, and research using Obsidian bidirectional linking (`[[Node Name]]`).

## Framework & Environment
- **Quantum SDK**: Qiskit (`qiskit`, `qiskit-ibm-runtime`)
- **Backend API**: Python (Flask, Flask-CORS, python-dotenv)
- **Frontend**: Next.js 14 (App Router, TypeScript, Tailwind CSS)
- **Execution Backend**: IBM Quantum Cloud (Cloud Routing enforced)
- **Local Simulation**: Disabled (hardware protection for i7-8565U / MX130)

## Status & Progress
- Project initialized in assigned directory `c:\Users\PC\Documents\Q hackthon`.
- Execution router (`backend/execution_router.py`) and API server (`backend/app.py`) implemented.
- Local simulation guardrails and API endpoints verified via automated test suite (`backend/test_app.py` - 5/5 passed).
- Next.js frontend scaffold in progress.
- Foundational API bridge established between Next.js and Python cloud routing logic.

