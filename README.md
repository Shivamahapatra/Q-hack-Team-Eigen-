# Q-Hack: Team Eigen (C-DAC Quantum Hackathon)

Target Domain: **Domain 08: Open Innovation in Quantum Computing**

## Architecture Overview
This repository contains a full-stack quantum circuit studio designed to explore and prototype quantum applications while enforcing strict hardware protection for local developer environments:
- **Frontend (`frontend/`)**: Next.js 14 (React, TypeScript, Tailwind CSS) interactive user interface.
- **Backend (`backend/`)**: Python REST API (Flask, Flask-CORS) providing circuit validation and cloud dispatch.
- **Execution & Routing Layer**: Qiskit & Qiskit Runtime Service, strictly routing all quantum computations to external cloud providers (**IBM Quantum**).
- **Hardware Protection Guardrail**: Enforces `HardwareProtectionError` and permanently blocks local statevector and tensor-network simulation to prevent thermal throttling and bottlenecks on host hardware (Intel Core i7-8565U CPU and NVIDIA MX130 GPU).

---

## Directory Structure
```text
├── backend/
│   ├── app.py                 # REST API endpoints & route handling
│   ├── execution_router.py    # Cloud routing & hardware guardrails
│   └── test_app.py            # Automated test suite (100% pass)
├── frontend/
│   ├── app/
│   │   ├── api-client.ts      # Typed client bridge to Python API
│   │   ├── layout.tsx         # Root layout
│   │   └── page.tsx           # Interactive Quantum Cloud Studio UI
│   ├── package.json
│   └── next.config.mjs        # API proxy rewrites to Python backend
├── LLMWiki/
│   └── raw/                   # Obsidian-linked knowledge base & plans
├── context.md                 # Project context & architecture tracker
├── requirements.txt           # Python dependencies
└── .env.example               # Cloud credential configuration template
```

---

## Getting Started

### 1. Python Cloud Routing Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run backend API tests
python -m unittest backend/test_app.py

# Start backend server
python backend/app.py
```
Backend runs at `http://127.0.0.1:5000`.

### 2. Next.js Interactive Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` to interact with the Quantum Cloud Studio.

---

## Cloud Configuration
Set your IBM Quantum API token in `.env`:
```bash
QISKIT_IBM_TOKEN=your_token_here
ALLOW_LOCAL_SIMULATION=false
```

