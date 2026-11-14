import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from c1_01_final import (
    Op, profile, decompose, analyze, from_qniverse, to_qniverse,
    equal_up_to_phase, unitary
)


class TestC1_01ProfilerAndDecomposer(unittest.TestCase):

    def test_single_qubit_gates(self):
        """Tests profiling of circuits containing only single-qubit gates."""
        ops = [Op("h", (0,)), Op("x", (0,)), Op("z", (0,))]
        p = profile(ops, 1)
        self.assertEqual(p["total_gates"], 3)
        self.assertEqual(p["single_qubit_gates"], 3)
        self.assertEqual(p["two_qubit_gates"], 0)
        self.assertEqual(p["depth"], 3)
        self.assertEqual(p["qubits_used"], 1)

    def test_two_qubit_gates(self):
        """Tests profiling with two-qubit entangling gates."""
        ops = [Op("h", (0,)), Op("cx", (0, 1)), Op("cz", (0, 1))]
        p = profile(ops, 2)
        self.assertEqual(p["total_gates"], 3)
        self.assertEqual(p["two_qubit_gates"], 2)
        self.assertEqual(p["multi_qubit_gates"], 2)
        self.assertEqual(p["depth"], 3)

    def test_disjoint_qubit_gates(self):
        """Tests that independent operations on disjoint qubits share the same depth layer."""
        ops = [Op("h", (0,)), Op("h", (1,)), Op("x", (2,))]
        p = profile(ops, 3)
        self.assertEqual(p["total_gates"], 3)
        self.assertEqual(p["depth"], 1)
        self.assertEqual(p["qubits_used"], 3)

    def test_dependent_gate_chain(self):
        """Tests that cascading dependencies across qubits serialize depth."""
        ops = [
            Op("h", (0,)),
            Op("cx", (0, 1)),
            Op("cx", (1, 2)),
            Op("x", (2,))
        ]
        p = profile(ops, 3)
        self.assertEqual(p["total_gates"], 4)
        self.assertEqual(p["depth"], 4)

    def test_valid_decomposition_swap(self):
        """Tests decomposing a SWAP gate into basis {h, cx}."""
        ops = [Op("swap", (0, 1))]
        new_ops, report = decompose(ops, 2, {"h", "cx"})
        self.assertIsNotNone(new_ops)
        self.assertEqual(report["status"], "OK")
        self.assertEqual(len(report["unsupported"]), 0)
        self.assertTrue(all(o.name in {"h", "cx"} for o in new_ops))
        # Mathematical verification
        self.assertTrue(equal_up_to_phase(unitary(ops, 2), unitary(new_ops, 2)))

    def test_unsupported_operation_reported(self):
        """Tests that an operation without decomposition rule returns an explicit report."""
        ops = [Op("h", (0,)), Op("unsupported_gate", (0,))]
        new_ops, report = decompose(ops, 1, {"h", "cx"})
        self.assertIsNone(new_ops)
        self.assertIn("FAILED: unsupported operations", report["status"])
        self.assertEqual(len(report["unsupported"]), 1)
        self.assertEqual(report["unsupported"][0]["gate"], "unsupported_gate")

    def test_empty_basis_rejected(self):
        """Tests that an empty basis set raises ValueError."""
        ops = [Op("h", (0,))]
        with self.assertRaises(ValueError):
            decompose(ops, 1, set())

    def test_malformed_input_rejected(self):
        """Tests that None or invalid input formats raise ValueError or TypeError."""
        with self.assertRaises(ValueError):
            from_qniverse(None)
        with self.assertRaises(TypeError):
            from_qniverse(12345)
        with self.assertRaises(ValueError):
            from_qniverse("")

    def test_input_immutability(self):
        """Tests that the input circuit/ops list remains completely unmodified."""
        qasm_in = """
        OPENQASM 2.0;
        include "qelib1.inc";
        qreg q[2];
        h q[0];
        swap q[0], q[1];
        """
        orig_copy = str(qasm_in)
        new_circ, report = analyze(qasm_in, {"h", "cx"})
        self.assertEqual(qasm_in, orig_copy)
        self.assertIsNotNone(new_circ)
        self.assertEqual(report["status"], "OK")


if __name__ == "__main__":
    unittest.main()
