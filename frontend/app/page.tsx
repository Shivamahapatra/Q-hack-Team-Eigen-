'use client';

import React, { useState, useEffect } from 'react';
import {
  fetchHealth,
  fetchCloudStatus,
  fetchCircuitTemplates,
  routeCircuit,
  HealthResponse,
  CloudStatusResponse,
  CircuitTemplate,
  RouteCircuitResponse,
} from './api-client';

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [cloudStatus, setCloudStatus] = useState<CloudStatusResponse | null>(null);
  const [templates, setTemplates] = useState<CircuitTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('bell_state');
  const [circuitName, setCircuitName] = useState<string>('Bell_State_Circuit');
  const [qasmCode, setQasmCode] = useState<string>('');
  const [numQubits, setNumQubits] = useState<number>(2);
  const [loading, setLoading] = useState<boolean>(false);
  const [dispatchLog, setDispatchLog] = useState<RouteCircuitResponse[]>([]);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      try {
        const [h, c, t] = await Promise.all([
          fetchHealth().catch((err) => {
            console.error(err);
            return null;
          }),
          fetchCloudStatus().catch((err) => {
            console.error(err);
            return null;
          }),
          fetchCircuitTemplates().catch((err) => {
            console.error(err);
            return [];
          }),
        ]);

        if (h) setHealth(h);
        if (c) setCloudStatus(c);
        if (t && t.length > 0) {
          setTemplates(t);
          setQasmCode(t[0].qasm);
          setNumQubits(t[0].num_qubits);
          setCircuitName(t[0].name.replace(/\s+/g, '_'));
        }
      } catch (err: unknown) {
        if (err instanceof Error) {
          setBackendError(err.message);
        } else {
          setBackendError('Unknown connection error');
        }
      }
    }
    init();
  }, []);

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const tmpl = templates.find((t) => t.id === templateId);
    if (tmpl) {
      setQasmCode(tmpl.qasm);
      setNumQubits(tmpl.num_qubits);
      setCircuitName(tmpl.name.replace(/\s+/g, '_'));
    }
  };

  const handleRouteToCloud = async (forceLocal = false) => {
    setLoading(true);
    try {
      const res = await routeCircuit({
        name: circuitName,
        qasm: qasmCode,
        num_qubits: numQubits,
        force_local: forceLocal,
      });
      setDispatchLog((prev) => [res, ...prev]);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to reach backend';
      setDispatchLog((prev) => [
        {
          error: 'ConnectionError',
          message: errorMsg,
          suggestion: 'Ensure the Python backend is running on http://127.0.0.1:5000',
        },
        ...prev,
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
              C-DAC Quantum Hackathon
            </span>
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
              Domain 08: Open Innovation
            </span>
          </div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white mt-1">
            Quantum Cloud Execution & Open Studio
          </h1>
        </div>

        {/* Status badges */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700">
            <span className={`w-2 h-2 rounded-full ${health ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
            <span>Backend: {health ? 'Online' : 'Standby / Connecting'}</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700">
            <span className="text-cyan-400">☁</span>
            <span>Target: IBM Quantum Cloud</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/30">
            <span>🛡 Local Sim: Prohibited (i7-8565U Protected)</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Circuit Configuration */}
        <section className="lg:col-span-7 flex flex-col gap-6">
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center justify-between">
              <span>Circuit Specification</span>
              <span className="text-xs text-slate-400 font-normal">OpenQASM 2.0 / 3.0</span>
            </h2>

            {/* Template Selector */}
            <div className="mb-4">
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Load Architecture Template:
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {templates.map((tmpl) => (
                  <button
                    key={tmpl.id}
                    onClick={() => handleTemplateChange(tmpl.id)}
                    className={`text-left p-2.5 rounded-lg border text-xs transition-all ${
                      selectedTemplateId === tmpl.id
                        ? 'bg-cyan-500/10 border-cyan-500/60 text-cyan-300'
                        : 'bg-slate-800/50 border-slate-700/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                    }`}
                  >
                    <div className="font-semibold text-slate-200">{tmpl.name}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5">{tmpl.num_qubits} Qubits</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Inputs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Circuit Identifier</label>
                <input
                  type="text"
                  value={circuitName}
                  onChange={(e) => setCircuitName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Target Qubits</label>
                <input
                  type="number"
                  min="1"
                  max="127"
                  value={numQubits}
                  onChange={(e) => setNumQubits(parseInt(e.target.value, 10) || 1)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            {/* QASM Code Area */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">QASM Definition</label>
              <textarea
                rows={10}
                value={qasmCode}
                onChange={(e) => setQasmCode(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs font-mono text-emerald-400 focus:outline-none focus:border-cyan-500 leading-relaxed"
                spellCheck={false}
              />
            </div>

            {/* Actions */}
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                onClick={() => handleRouteToCloud(false)}
                disabled={loading}
                className="flex-1 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white font-medium px-4 py-2.5 rounded-lg text-xs transition-all shadow-md flex items-center justify-center gap-2"
              >
                {loading ? 'Routing to Cloud...' : '☁ Route to IBM Quantum Cloud'}
              </button>
              <button
                onClick={() => handleRouteToCloud(true)}
                disabled={loading}
                className="bg-slate-800 hover:bg-rose-950/40 text-rose-300 border border-rose-500/30 font-medium px-3 py-2.5 rounded-lg text-xs transition-all flex items-center gap-1.5"
                title="Test hardware protection guardrails"
              >
                <span>🛡 Test Local Guardrail</span>
              </button>
            </div>
          </div>
        </section>

        {/* Right Column: Execution Monitoring & Diagnostics */}
        <section className="lg:col-span-5 flex flex-col gap-6">
          {/* Cloud Connection Panel */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h2 className="text-base font-semibold text-white mb-3">Cloud Routing Diagnostics</h2>
            <div className="space-y-2.5 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Provider:</span>
                <span className="font-semibold text-cyan-400">{cloudStatus?.provider || 'IBM Quantum'}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Instance Hub:</span>
                <span className="font-mono text-slate-300">{cloudStatus?.instance || 'ibm-q/open/main'}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Target QPU:</span>
                <span className="font-mono text-slate-300">
                  {cloudStatus?.preferred_backend || 'least_busy_operational_qpu'}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800">
                <span className="text-slate-400">Local Simulation:</span>
                <span className="font-semibold text-rose-400">Disabled (Hardware Protected)</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-slate-400">API Token:</span>
                <span className={cloudStatus?.token_configured ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold'}>
                  {cloudStatus?.token_configured ? 'Active / Configured' : 'Awaiting QISKIT_IBM_TOKEN in .env'}
                </span>
              </div>
            </div>

            {(!cloudStatus?.token_configured || backendError) && (
              <div className="mt-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-300">
                <strong>Authentication Notice:</strong> To dispatch jobs to live IBM Quantum hardware, add your API token to <code>.env</code> as <code>QISKIT_IBM_TOKEN=...</code>.
              </div>
            )}
          </div>

          {/* Dispatch Logs */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 shadow-lg flex-1 flex flex-col">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center justify-between">
              <span>Dispatch Monitor</span>
              <span className="text-xs text-slate-400 font-normal">{dispatchLog.length} events</span>
            </h2>

            <div className="space-y-3 flex-1 overflow-y-auto max-h-[360px] pr-1">
              {dispatchLog.length === 0 ? (
                <div className="text-xs text-slate-500 italic p-4 text-center border border-dashed border-slate-800 rounded-lg">
                  No circuits dispatched yet. Click &quot;Route to IBM Quantum Cloud&quot; or test hardware protection.
                </div>
              ) : (
                dispatchLog.map((log, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border text-xs ${
                      log.error === 'HardwareProtectionError'
                        ? 'bg-rose-500/10 border-rose-500/40 text-rose-200'
                        : log.error === 'AuthenticationRequired'
                        ? 'bg-amber-500/10 border-amber-500/40 text-amber-200'
                        : log.status === 'ROUTED_TO_CLOUD'
                        ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300'
                    }`}
                  >
                    <div className="flex justify-between items-center font-semibold mb-1">
                      <span>{log.error || log.status || 'Response'}</span>
                      <span className="text-[10px] opacity-75">{new Date().toLocaleTimeString()}</span>
                    </div>
                    <p className="text-[11px] leading-relaxed opacity-90">{log.message}</p>
                    {log.suggestion && (
                      <p className="text-[10px] mt-1.5 text-cyan-300 opacity-90">
                        💡 {log.suggestion}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
