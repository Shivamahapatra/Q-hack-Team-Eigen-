"""
Comprehensive Unit Test Suite for QC-03-03: Quantum Circuit Optimization Using QSDK.
"""

import os
import sys
import unittest

# Ensure src and src/c3-03 are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from c1_01_final import Op, unitary, equal_up_to_phase
import qniverse_adapter as qa
from optimizer import (
    optimize,
    verify_equivalence,
    OptimizationResult,
    PASS_IDENTITY_REMOVAL,
    PASS_SELF_INVERSE_CANCELLATION,
    PASS_CX_CANCELLATION,
    SUPPORTED_PASSES,
)


def _make_mock_circuit(num_qubits, num_clbits, ops, q_registers=None, c_registers=None):
    """Helper to create a mock QniverseCircuit for testing runtime integration."""
    class Reg:
        def __init__(self, kind, size, name):
            self.kind = kind
            self.size = size
            self.name = name
        def __repr__(self):
            return f"{self.kind}Register({self.size}, '{self.name}')"

    class W:
        def __init__(self, kind, reg_name, size, idx):
            self.kind = kind
            self.reg_name = reg_name
            self.size = size
            self.idx = idx
        def __repr__(self):
            reg = "QuantumRegister" if self.kind == "Qubit" else "ClassicalRegister"
            return f"{self.kind}({reg}({self.size}, '{self.reg_name}'), {self.idx})"

    class G:
        def __init__(self, name):
            self.name = name.upper() if name not in ("measure", "barrier", "reset") else name.capitalize()

    class MockQC:
        def __init__(self):
            self.num_qubits = num_qubits
            self.num_clbits = num_clbits
            self.registers = []

            q_regs = q_registers or ([("q", num_qubits)] if num_qubits > 0 else [])
            c_regs = c_registers or ([("c", num_clbits)] if num_clbits > 0 else [])

            for name, size in q_regs:
                self.registers.append(Reg("Quantum", size, name))
            for name, size in c_regs:
                self.registers.append(Reg("Classical", size, name))

            def _map_wire(idx, regs, kind):
                curr = 0
                for name, size in regs:
                    if curr <= idx < curr + size:
                        return W(kind, name, size, idx - curr)
                    curr += size
                reg_name = "q" if kind == "Qubit" else "c"
                return W(kind, reg_name, idx + 1, idx)

            self.operations = []
            for o in ops:
                if o.name == "measure":
                    wires = (
                        _map_wire(o.qubits[0], q_regs, "Qubit"),
                        _map_wire(o.cbits[0], c_regs, "Clbit")
                    )
                else:
                    wires = tuple(_map_wire(q, q_regs, "Qubit") for q in o.qubits)
                self.operations.append((G(o.name), wires))

    return MockQC()


class TestQC0303Optimizer(unittest.TestCase):

    # ---------------------------------------------------- IDENTITY TESTS
    def test_identity_removal(self):
        """Pass 1: Removes explicit identity gates while preserving other gates."""
        ops = [Op("id", (0,)), Op("h", (0,)), Op("id", (0,))]
        res = optimize(ops, enabled_passes=[PASS_IDENTITY_REMOVAL])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["after"]["by_type"], {"h": 1})
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_identity_preserves_other_qubits(self):
        """Pass 1: Identity on qubit 0 does not alter gates on qubit 1."""
        ops = [Op("id", (0,)), Op("x", (1,))]
        res = optimize(ops, enabled_passes=[PASS_IDENTITY_REMOVAL])
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["after"]["by_type"], {"x": 1})

    # ------------------------------------------------ SELF-INVERSE TESTS
    def test_self_inverse_xx_cancellation(self):
        """Pass 2: Adjacent X-X on the same qubit cancel out."""
        ops = [Op("x", (0,)), Op("x", (0,))]
        res = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_self_inverse_hh_cancellation(self):
        """Pass 2: Adjacent H-H on the same qubit cancel out."""
        ops = [Op("h", (0,)), Op("h", (0,))]
        res = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_self_inverse_zz_cancellation(self):
        """Pass 2: Adjacent Z-Z on the same qubit cancel out."""
        ops = [Op("z", (1,)), Op("z", (1,))]
        res = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_self_inverse_different_qubits_do_not_cancel(self):
        """Pass 2: X on qubit 0 and X on qubit 1 do not cancel."""
        ops = [Op("x", (0,)), Op("x", (1,))]
        res = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)

    # ---------------------------------------------------- CX TESTS
    def test_cx_cx_cancellation(self):
        """Pass 3: Consecutive CX operations with matching control and target cancel."""
        ops = [Op("cx", (0, 1)), Op("cx", (0, 1))]
        res = optimize(ops, enabled_passes=[PASS_CX_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_cx_reversed_control_target_does_not_cancel(self):
        """Pass 3: CX(0, 1) and CX(1, 0) do NOT cancel (they form a SWAP building block)."""
        ops = [Op("cx", (0, 1)), Op("cx", (1, 0))]
        res = optimize(ops, enabled_passes=[PASS_CX_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    # ---------------------------------------------------- SAFETY TESTS
    def test_intervening_gate_prevents_cancellation(self):
        """Safety: An intervening gate on the same qubit prevents cancellation."""
        ops = [Op("x", (0,)), Op("z", (0,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 3)

    def test_barrier_prevents_cancellation(self):
        """Safety: A barrier strictly blocks cancellation across it."""
        ops = [Op("h", (0,)), Op("barrier", (0,)), Op("h", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_measurement_prevents_cancellation(self):
        """Safety: Measurements are non-unitary boundaries and prevent cancellation."""
        ops = [Op("x", (0,)), Op("measure", (0,), (0,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        self.assertEqual(res.report["after"]["measurements"], 1)

    def test_reset_prevents_cancellation(self):
        """Safety: Reset operations strictly prevent cancellation."""
        ops = [Op("x", (0,)), Op("reset", (0,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)

    # ------------------------------------------------ NON-MUTATION TESTS
    def test_original_circuit_immutability(self):
        """Safety: Original circuit object and operations remain 100% untouched."""
        ops = [Op("h", (0,)), Op("h", (0,)), Op("x", (1,))]
        mock_qc = _make_mock_circuit(2, 0, ops)
        orig_ops_count = len(mock_qc.operations)

        res = optimize(mock_qc)

        self.assertEqual(len(mock_qc.operations), orig_ops_count)
        self.assertIsNot(res.circuit, mock_qc)
        # Verify original mock still has both H gates
        extracted_orig, _, _, _ = qa.from_qniverse(mock_qc)
        self.assertEqual(len(extracted_orig), 3)

    # --------------------------------------------- CONFIGURATION TESTS
    def test_selective_pass_enabling(self):
        """Configuration: Only specifically enabled passes execute."""
        ops = [Op("id", (0,)), Op("x", (0,)), Op("x", (0,))]
        # Enable only identity removal
        res1 = optimize(ops, enabled_passes=[PASS_IDENTITY_REMOVAL])
        self.assertEqual(res1.report["passes_applied"], [PASS_IDENTITY_REMOVAL])
        self.assertEqual(res1.report["gates_removed"], 1)
        self.assertEqual(res1.report["after"]["total_gates"], 2)

        # Enable only self-inverse
        res2 = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res2.report["passes_applied"], [PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 2)
        self.assertEqual(res2.report["after"]["total_gates"], 1)

    def test_unknown_pass_rejected(self):
        """Configuration: Passing an invalid pass name raises ValueError."""
        ops = [Op("h", (0,))]
        with self.assertRaises(ValueError) as ctx:
            optimize(ops, enabled_passes=["invalid_pass_name"])
        self.assertIn("Unknown optimization pass", str(ctx.exception))

    # ------------------------------------------------- EDGE CASES TESTS
    def test_empty_circuit(self):
        """Edge Case: Empty circuit optimizes gracefully without error."""
        res = optimize([])
        self.assertEqual(res.report["status"], "OK")
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_no_improvement_circuit(self):
        """Edge Case: Optimal circuit has 0 gates removed and 0% reduction."""
        ops = [Op("h", (0,)), Op("cx", (0, 1)), Op("t", (1,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["reduction_percentage"], 0.0)
        self.assertEqual(res.report["after"]["total_gates"], 3)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_circuit_with_measurement(self):
        """Edge Case: Circuits with measurements preserve classical register mapping."""
        ops = [
            Op("x", (0,)), Op("x", (0,)),
            Op("h", (0,)),
            Op("measure", (0,), (0,))
        ]
        mock_qc = _make_mock_circuit(1, 1, ops)
        res = optimize(mock_qc)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["after"]["measurements"], 1)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    # ----------------------------------------------- EQUIVALENCE TESTS
    def test_mathematical_unitary_equivalence(self):
        """Equivalence: Multi-qubit circuit with cancellations is mathematically equal."""
        # Circuit has H-H on q0, CX-CX on q0-q1, and Z-Z on q1
        ops = [
            Op("h", (0,)), Op("h", (0,)),
            Op("x", (0,)),
            Op("cx", (0, 1)), Op("cx", (0, 1)),
            Op("z", (1,)), Op("z", (1,)),
            Op("h", (1,))
        ]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 6)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        # Verification using existing numpy unitary check
        u_orig = unitary(ops, 2)
        u_opt = unitary([Op("x", (0,)), Op("h", (1,))], 2)
        self.assertTrue(equal_up_to_phase(u_orig, u_opt))
        self.assertTrue(res.report["equivalence"]["equivalent"])

    # ---------------------------------- AUDIT DEFECT REGRESSION TESTS
    def test_equivalence_purely_unitary(self):
        """DEF-01: Purely unitary circuits report mathematical equivalence verified up to global phase."""
        ops = [Op("x", (0,)), Op("x", (0,)), Op("h", (0,))]
        res = optimize(ops)
        eq = res.report["equivalence"]
        self.assertEqual(eq["type"], "unitary")
        self.assertTrue(eq["equivalent"])
        self.assertTrue(eq["mathematical_equivalence_verified"])
        self.assertTrue(eq["structural_preservation_verified"])
        self.assertEqual(res.report["status"], "OK")

    def test_equivalence_terminal_measurement(self):
        """DEF-01: Terminal measurement circuits verify unitary prefix mathematically and measurements structurally."""
        ops = [
            Op("h", (0,)), Op("h", (0,)),
            Op("x", (0,)),
            Op("measure", (0,), (0,))
        ]
        res = optimize(ops)
        eq = res.report["equivalence"]
        self.assertEqual(eq["type"], "terminal_measurement_verified")
        self.assertTrue(eq["equivalent"])
        self.assertTrue(eq["mathematical_equivalence_verified"])
        self.assertTrue(eq["structural_preservation_verified"])
        self.assertEqual(res.report["status"], "OK")

    def test_equivalence_mid_circuit_measurement(self):
        """DEF-01: Mid-circuit measurements must return equivalent: None and OK_SEMANTIC_UNVERIFIED."""
        ops = [
            Op("h", (0,)),
            Op("measure", (0,), (0,)),
            Op("h", (0,))
        ]
        res = optimize(ops)
        eq = res.report["equivalence"]
        self.assertEqual(eq["type"], "mid_circuit_non_unitary_unverified")
        self.assertIsNone(eq["equivalent"])
        self.assertFalse(eq["mathematical_equivalence_verified"])
        self.assertTrue(eq["structural_preservation_verified"])
        self.assertEqual(res.report["status"], "OK_SEMANTIC_UNVERIFIED")
        self.assertTrue(any("Semantic equivalence not verified" in w for w in res.report["warnings"]))

    def test_equivalence_with_reset(self):
        """DEF-01: Resets prevent unitary simulation; return equivalent: None and OK_SEMANTIC_UNVERIFIED."""
        ops = [
            Op("x", (0,)),
            Op("reset", (0,)),
            Op("x", (0,))
        ]
        res = optimize(ops)
        eq = res.report["equivalence"]
        self.assertEqual(eq["type"], "mid_circuit_non_unitary_unverified")
        self.assertIsNone(eq["equivalent"])
        self.assertFalse(eq["mathematical_equivalence_verified"])
        self.assertTrue(eq["structural_preservation_verified"])
        self.assertEqual(res.report["status"], "OK_SEMANTIC_UNVERIFIED")

    def test_barrier_isolation_and_unitary_equivalence(self):
        """DEF-01: Barrier blocks cancellation and is preserved without treating barrier as non-unitary quantum op."""
        ops = [
            Op("h", (0,)),
            Op("barrier", (0,)),
            Op("h", (0,))
        ]
        res = optimize(ops)
        eq = res.report["equivalence"]
        self.assertEqual(eq["type"], "unitary")
        self.assertTrue(eq["equivalent"])
        self.assertTrue(eq["mathematical_equivalence_verified"])
        self.assertTrue(eq["structural_preservation_verified"])
        self.assertEqual(res.report["gates_removed"], 0)

    def test_multi_register_preservation(self):
        """DEF-02: Multi-register circuits preserve names, sizes, and wire mappings in reconstructed circuit."""
        q_regs = [("data", 2), ("ancilla", 1)]
        c_regs = [("c_data", 2), ("c_flag", 1)]
        ops = [
            Op("h", (0,)),                      # data[0]
            Op("x", (2,)), Op("x", (2,)),       # ancilla[0] (should cancel)
            Op("measure", (0,), (0,)),          # data[0] -> c_data[0]
            Op("measure", (2,), (2,))           # ancilla[0] -> c_flag[0]
        ]
        mock_qc = _make_mock_circuit(3, 3, ops, q_registers=q_regs, c_registers=c_regs)
        res = optimize(mock_qc)

        self.assertEqual(res.report["gates_removed"], 2)
        new_c = res.circuit
        # Check registers
        reg_reprs = [repr(r) for r in new_c.registers]
        self.assertIn("QuantumRegister(2, 'data')", reg_reprs)
        self.assertIn("QuantumRegister(1, 'ancilla')", reg_reprs)
        self.assertIn("ClassicalRegister(2, 'c_data')", reg_reprs)
        self.assertIn("ClassicalRegister(1, 'c_flag')", reg_reprs)

        # Re-extract with from_qniverse to verify wire decoding
        extracted_ops, nq, nc, _ = qa.from_qniverse(new_c)
        self.assertEqual(nq, 3)
        self.assertEqual(nc, 3)
        self.assertEqual(len(extracted_ops), 3) # H(0), measure(0->0), measure(2->2)
        self.assertEqual(extracted_ops[0], Op("h", (0,)))
        self.assertEqual(extracted_ops[1], Op("measure", (0,), (0,)))
        self.assertEqual(extracted_ops[2], Op("measure", (2,), (2,)))

    def test_mismatched_verification_detected(self):
        """DEF-01: Non-equivalent circuits or mutated measurements are detected as equivalent: False."""
        # 1. Purely unitary mismatch
        res1 = verify_equivalence([Op("x", (0,))], [Op("z", (0,))], 1)
        self.assertFalse(res1["equivalent"])
        self.assertFalse(res1["mathematical_equivalence_verified"])

        # 2. Terminal measurement mismatch: prefix different
        res2 = verify_equivalence(
            [Op("x", (0,)), Op("measure", (0,), (0,))],
            [Op("z", (0,)), Op("measure", (0,), (0,))],
            1
        )
        self.assertFalse(res2["equivalent"])
        self.assertFalse(res2["mathematical_equivalence_verified"])

        # 3. Terminal measurement mismatch: classical bit destination changed
        res3 = verify_equivalence(
            [Op("x", (0,)), Op("measure", (0,), (0,))],
            [Op("x", (0,)), Op("measure", (0,), (1,))],
            1
        )
        self.assertFalse(res3["equivalent"])
        self.assertFalse(res3["structural_preservation_verified"])


if __name__ == "__main__":
    unittest.main()
