# Next.js and Python API Bridge

## Overview
This document specifies the communication contract between the Next.js interactive frontend and the Python backend for the [[Domain 08 Open Innovation Architecture]].

## Core Endpoints
1. `GET /api/health`
   - Returns service health, domain identifier, and active execution guardrails.
2. `GET /api/cloud/status`
   - Returns external cloud provider status ([[IBM Quantum]]), authentication state, and default backend settings.
3. `GET /api/circuits/templates`
   - Provides ready-to-explore quantum circuits (Bell State, GHZ State, QAOA Ansatz).
4. `POST /api/circuits/route`
   - Accepts circuit payload and routes execution to IBM Quantum cloud backends.
   - Rejects local simulation attempts with `403 HardwareProtectionError`.

## Client-Side Integration
The Next.js frontend interfaces with these endpoints using typed fetch clients and reactive state hooks, displaying real-time cloud dispatch status and circuit metrics.

## Related Links
- [[Domain 08 Open Innovation Architecture]]
- [[Cloud Execution Routing]]
- [[Qiskit Integration]]

