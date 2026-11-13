"""
Tests for Quantum Execution Router
Verifies cloud routing enforcement and local simulation prohibition.
"""

import os
import unittest
from execution_router import QuantumExecutionRouter, HardwareProtectionError, CloudRoutingConfig


class TestExecutionRouter(unittest.TestCase):

    def test_local_simulation_is_strictly_prohibited(self):
        router = QuantumExecutionRouter()
        with self.assertRaises(HardwareProtectionError) as context:
            router.block_local_simulation()
        self.assertIn("Local quantum simulation blocked", str(context.exception))

    def test_token_validation_without_token(self):
        # Ensure token is cleared for this test
        original_token = os.environ.get("QISKIT_IBM_TOKEN")
        if "QISKIT_IBM_TOKEN" in os.environ:
            del os.environ["QISKIT_IBM_TOKEN"]

        router = QuantumExecutionRouter()
        with self.assertRaises(ValueError) as context:
            router.get_service()
        self.assertIn("IBM Quantum API token not found", str(context.exception))

        if original_token:
            os.environ["QISKIT_IBM_TOKEN"] = original_token


if __name__ == "__main__":
    unittest.main()

