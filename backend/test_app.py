import unittest
import json
import os
import sys

# Ensure backend path is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app


class TestBackendAPI(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "online")
        self.assertIn("Domain 08", data["domain"])
        self.assertIn("i7-8565U", data["execution_policy"]["host_hardware_protection"])

    def test_cloud_status(self):
        response = self.client.get("/api/cloud/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["provider"], "IBM Quantum")
        self.assertTrue(data["local_simulation_disabled"])

    def test_circuit_templates(self):
        response = self.client.get("/api/circuits/templates")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("templates", data)
        self.assertGreaterEqual(len(data["templates"]), 3)

    def test_route_circuit_blocks_local_simulation(self):
        payload = {
            "name": "test_circuit",
            "qasm": "OPENQASM 2.0;",
            "force_local": True
        }
        response = self.client.post(
            "/api/circuits/route",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"], "HardwareProtectionError")

    def test_route_circuit_requires_authentication_if_token_unset(self):
        # Clear token if any
        orig_token = os.environ.get("QISKIT_IBM_TOKEN")
        if "QISKIT_IBM_TOKEN" in os.environ:
            del os.environ["QISKIT_IBM_TOKEN"]

        payload = {
            "name": "bell_pair",
            "num_qubits": 2
        }
        response = self.client.post(
            "/api/circuits/route",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"], "AuthenticationRequired")

        if orig_token:
            os.environ["QISKIT_IBM_TOKEN"] = orig_token


if __name__ == "__main__":
    unittest.main()

