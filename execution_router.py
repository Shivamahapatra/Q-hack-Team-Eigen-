"""
Execution Router for Quantum Workloads
Enforces routing of quantum circuits to external cloud providers (IBM Quantum).
Local simulation is strictly disabled to prevent bottlenecking the host system.
"""

import os
from typing import Optional, Any
from dotenv import load_dotenv

# Load local environment configuration if present
load_dotenv()


class HardwareProtectionError(RuntimeError):
    """Raised when an attempt is made to run heavy quantum simulation locally."""
    pass


class CloudRoutingConfig:
    """Manages cloud execution configuration and guards against local CPU/GPU bottlenecks."""

    ALLOW_LOCAL_SIMULATION: bool = os.getenv("ALLOW_LOCAL_SIMULATION", "false").lower() == "true"
    DEFAULT_INSTANCE: str = os.getenv("QISKIT_IBM_INSTANCE", "ibm-q/open/main")
    TARGET_BACKEND: Optional[str] = os.getenv("QISKIT_IBM_BACKEND", None)

    @classmethod
    def get_token(cls) -> Optional[str]:
        return os.getenv("QISKIT_IBM_TOKEN") or os.getenv("IBMQ_API_TOKEN")

    @classmethod
    def assert_cloud_routing_enforced(cls):
        """Strictly disallow local execution."""
        if not cls.ALLOW_LOCAL_SIMULATION:
            # Enforce guardrail
            return
        raise HardwareProtectionError(
            "Local quantum simulation is explicitly disabled to prevent bottlenecking "
            "the host CPU (Intel i7-8565U) and GPU (NVIDIA MX130). "
            "All quantum jobs must be routed to external cloud providers."
        )


class QuantumExecutionRouter:
    """Routes quantum circuit execution to external cloud backends (e.g., IBM Quantum)."""

    def __init__(self, channel: str = "ibm_quantum"):
        self.channel = channel
        self.token = CloudRoutingConfig.get_token()
        self._service = None

    def get_service(self):
        """Initializes and returns the QiskitRuntimeService connection."""
        if not self.token:
            raise ValueError(
                "IBM Quantum API token not found! Please set 'QISKIT_IBM_TOKEN' in your environment or .env file.\n"
                "You can get your token from https://quantum.ibm.com/"
            )

        if self._service is None:
            try:
                from qiskit_ibm_runtime import QiskitRuntimeService
                self._service = QiskitRuntimeService(
                    channel=self.channel,
                    token=self.token,
                    instance=CloudRoutingConfig.DEFAULT_INSTANCE
                )
            except ImportError:
                raise ImportError(
                    "qiskit-ibm-runtime is required for cloud execution. "
                    "Install dependencies using 'pip install -r requirements.txt'."
                )
        return self._service

    def get_backend(self, backend_name: Optional[str] = None):
        """Returns the cloud backend (e.g. ibm_brisbane, least busy cloud QPU)."""
        service = self.get_service()
        target = backend_name or CloudRoutingConfig.TARGET_BACKEND
        if target:
            return service.backend(target)
        # Select least busy operational hardware backend
        return service.least_busy(operational=True, simulator=False)

    def route_circuit(self, circuit: Any, backend_name: Optional[str] = None):
        """
        Validates cloud routing policy and prepares circuit for execution on cloud backend.
        Refuses any fallback to local simulation.
        """
        # Block any local execution attempts
        CloudRoutingConfig.assert_cloud_routing_enforced()

        backend = self.get_backend(backend_name)
        return {
            "status": "ROUTED_TO_CLOUD",
            "backend": backend.name,
            "provider": "IBM Quantum Cloud",
            "num_qubits": circuit.num_qubits if hasattr(circuit, "num_qubits") else None
        }

    def block_local_simulation(self):
        """Explicitly halts any local simulator invocation."""
        raise HardwareProtectionError(
            "Local quantum simulation blocked: Host hardware protection active "
            "(Intel i7-8565U / NVIDIA MX130). Route all simulations to IBM Quantum."
        )

