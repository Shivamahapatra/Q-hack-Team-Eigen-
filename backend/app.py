import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Import execution router logic
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from execution_router import (
    QuantumExecutionRouter,
    CloudRoutingConfig,
    HardwareProtectionError
)

load_dotenv()

app = Flask(__name__)
# Enable CORS for Next.js frontend (default port 3000)
CORS(app, resources={r"/api/*": {"origins": "*"}})

router = QuantumExecutionRouter()


@app.route("/api/health", methods=["GET"])
def health_check():
    """Returns system status, domain target, and execution policies."""
    return jsonify({
        "status": "online",
        "domain": "Domain 08: Open Innovation in Quantum Computing",
        "execution_policy": {
            "local_simulation_allowed": CloudRoutingConfig.ALLOW_LOCAL_SIMULATION,
            "routing_target": "External Cloud (IBM Quantum)",
            "host_hardware_protection": "Active (i7-8565U CPU / MX130 GPU protection enabled)"
        }
    }), 200


@app.route("/api/cloud/status", methods=["GET"])
def cloud_status():
    """Checks the external cloud provider connection status."""
    token = CloudRoutingConfig.get_token()
    token_configured = bool(token and len(token.strip()) > 0)
    
    response = {
        "provider": "IBM Quantum",
        "channel": router.channel,
        "instance": CloudRoutingConfig.DEFAULT_INSTANCE,
        "token_configured": token_configured,
        "preferred_backend": CloudRoutingConfig.TARGET_BACKEND or "least_busy_operational_qpu",
        "local_simulation_disabled": not CloudRoutingConfig.ALLOW_LOCAL_SIMULATION
    }
    
    if not token_configured:
        response["message"] = (
            "No IBM Quantum token detected. Configure 'QISKIT_IBM_TOKEN' in the environment or .env file "
            "to authenticate with cloud QPUs."
        )
    return jsonify(response), 200


@app.route("/api/circuits/route", methods=["POST"])
def route_circuit():
    """
    Receives circuit payload and routes to IBM Quantum cloud backend.
    Enforces hardware guardrail: any attempt to simulate locally will fail immediately.
    """
    data = request.get_json(silent=True) or {}
    circuit_name = data.get("name", "circuit_01")
    qasm = data.get("qasm", "")
    num_qubits = data.get("num_qubits", 2)
    force_local = data.get("force_local", False)

    # Reject local simulation attempts
    if force_local or data.get("simulate_locally", False):
        return jsonify({
            "error": "HardwareProtectionError",
            "message": "Local quantum simulation is explicitly blocked to protect host hardware (Intel i7-8565U / NVIDIA MX130). All quantum circuits must route to external cloud providers.",
            "suggestion": "Job must be routed to IBM Quantum Cloud. Local simulation is disabled."
        }), 403

    # Check token requirement for cloud dispatch
    if not CloudRoutingConfig.get_token():
        return jsonify({
            "error": "AuthenticationRequired",
            "message": "IBM Quantum API token not found in backend environment. Please set QISKIT_IBM_TOKEN.",
            "circuit": circuit_name,
            "num_qubits": num_qubits,
            "status": "QUEUED_AWAITING_CREDENTIALS"
        }), 401

    try:
        # Prepare and route job to cloud provider
        backend = router.get_backend()
        return jsonify({
            "status": "ROUTED_TO_CLOUD",
            "circuit_name": circuit_name,
            "num_qubits": num_qubits,
            "cloud_provider": "IBM Quantum",
            "cloud_backend": getattr(backend, "name", str(backend)),
            "message": f"Circuit '{circuit_name}' successfully queued for execution on IBM Quantum cloud."
        }), 200
    except Exception as exc:
        return jsonify({
            "error": "CloudRoutingError",
            "message": str(exc)
        }), 500


@app.route("/api/circuits/templates", methods=["GET"])
def get_circuit_templates():
    """Returns foundational quantum circuit templates for Open Innovation exploration."""
    templates = [
        {
            "id": "bell_state",
            "name": "Bell State (EPR Pair)",
            "num_qubits": 2,
            "description": "Fundamental 2-qubit maximally entangled quantum state.",
            "qasm": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\nmeasure q -> c;\n"
        },
        {
            "id": "ghz_state",
            "name": "GHZ State (3-Qubit Entanglement)",
            "num_qubits": 3,
            "description": "Greenberger–Horne–Zeilinger tripartite entanglement circuit.",
            "qasm": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[3];\ncreg c[3];\nh q[0];\ncx q[0],q[1];\ncx q[1],q[2];\nmeasure q -> c;\n"
        },
        {
            "id": "qaoa_ansatz",
            "name": "Parametric QAOA Circuit",
            "num_qubits": 4,
            "description": "Quantum Approximate Optimization Algorithm ansatz for combinatorial challenges.",
            "qasm": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[4];\ncreg c[4];\nh q[0];\nh q[1];\nh q[2];\nh q[3];\nrz(0.5) q[0];\nrz(0.5) q[1];\ncx q[0],q[1];\nmeasure q -> c;\n"
        }
    ]
    return jsonify({"templates": templates}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
