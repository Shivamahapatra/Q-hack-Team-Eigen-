export interface HealthResponse {
  status: string;
  domain: string;
  execution_policy: {
    local_simulation_allowed: boolean;
    routing_target: string;
    host_hardware_protection: string;
  };
}

export interface CloudStatusResponse {
  provider: string;
  channel: string;
  instance: string;
  token_configured: boolean;
  preferred_backend: string;
  local_simulation_disabled: boolean;
  message?: string;
}

export interface CircuitTemplate {
  id: string;
  name: string;
  num_qubits: number;
  description: string;
  qasm: string;
}

export interface RouteCircuitPayload {
  name: string;
  qasm: string;
  num_qubits: number;
  force_local?: boolean;
}

export interface RouteCircuitResponse {
  status?: string;
  circuit_name?: string;
  num_qubits?: number;
  cloud_provider?: string;
  cloud_backend?: string;
  message?: string;
  error?: string;
  suggestion?: string;
}

const BACKEND_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:5000';

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BACKEND_BASE}/api/health`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function fetchCloudStatus(): Promise<CloudStatusResponse> {
  const res = await fetch(`${BACKEND_BASE}/api/cloud/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Cloud status check failed: ${res.status}`);
  return res.json();
}

export async function fetchCircuitTemplates(): Promise<CircuitTemplate[]> {
  const res = await fetch(`${BACKEND_BASE}/api/circuits/templates`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to fetch circuit templates: ${res.status}`);
  const data = await res.json();
  return data.templates || [];
}

export async function routeCircuit(payload: RouteCircuitPayload): Promise<RouteCircuitResponse> {
  const res = await fetch(`${BACKEND_BASE}/api/circuits/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}
