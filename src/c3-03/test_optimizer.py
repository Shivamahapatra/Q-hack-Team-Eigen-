"""
Comprehensive Unit Test Suite for QC-03-03: Quantum Circuit Optimization Using QSDK.
"""

import os
import sys
import unittest

# Ensure src and src/c3-03 are in sys.path (safe for scripts and Jupyter notebooks)
_file = globals().get("__file__")
_base_dir = os.path.dirname(os.path.abspath(_file)) if _file else os.getcwd()
_candidates = [
    os.path.abspath(os.path.join(_base_dir, "..")),
    os.path.abspath(os.path.join(_base_dir, "src")),
    _base_dir,
    os.path.abspath(os.path.join(_base_dir, "src", "c3-03")),
]
for _p in _candidates:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

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
    _reconstruct_circuit,
    _validate_register_layouts,
    _validate_circuit_ops,
    _verify_structural_placement,
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

    # --------------------------------------------- PRIORITY 1: PER-WIRE ADJACENCY TESTS
    def test_per_wire_x_cancels_across_disjoint_y(self):
        """P1: X(0), Y(1), X(0) -> X gates cancel across disjoint wire, Y stays."""
        ops = [Op("x", (0,)), Op("y", (1,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["after"]["by_type"], {"y": 1})
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_cx_cancels_across_disjoint_h(self):
        """P1: CX(0,1), H(2), CX(0,1) -> CX pair cancels across disjoint wire."""
        ops = [Op("cx", (0, 1)), Op("h", (2,)), Op("cx", (0, 1))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["after"]["by_type"], {"h": 1})
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_cx_blocked_by_intervening_h_on_target(self):
        """P1: CX(0,1), H(1), CX(0,1) -> does NOT cancel (H touches target qubit 1)."""
        ops = [Op("cx", (0, 1)), Op("h", (1,)), Op("cx", (0, 1))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 3)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_h_blocked_by_shared_barrier(self):
        """P1: H(0), barrier on (0,1), H(0) -> does NOT cancel (barrier spans qubit 0)."""
        ops = [Op("h", (0,)), Op("barrier", (0, 1)), Op("h", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_h_blocked_by_measure(self):
        """P1: H(0), measure(0 -> c0), H(0) -> does NOT cancel (measure touches qubit 0)."""
        ops = [Op("h", (0,)), Op("measure", (0,), (0,)), Op("h", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)
        self.assertEqual(res.report["after"]["measurements"], 1)
        self.assertTrue(res.report["equivalence"]["structural_preservation_verified"])
        self.assertIsNone(res.report["equivalence"]["equivalent"])

    def test_per_wire_x_cancels_across_disjoint_barrier(self):
        """P1: X(0), barrier on qubit 1 only, X(0) -> cancels (barrier does not touch qubit 0)."""
        ops = [Op("x", (0,)), Op("barrier", (1,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_depth_and_gate_count_both_decrease(self):
        """P1: Explicit assertion that depth AND gate count both decrease on one circuit."""
        ops = [Op("x", (0,)), Op("y", (1,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertLess(res.report["after"]["total_gates"], res.report["before"]["total_gates"])
        self.assertLess(res.report["after"]["depth"], res.report["before"]["depth"])
        self.assertEqual(res.report["before"]["total_gates"], 3)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertEqual(res.report["before"]["depth"], 2)
        self.assertEqual(res.report["after"]["depth"], 1)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_cx_cx_cx_blocked_on_shared_qubit(self):
        """P1: CX(0,1), CX(1,2), CX(0,1) must NOT cancel (the middle gate touches qubit 1)."""
        ops = [Op("cx", (0, 1)), Op("cx", (1, 2)), Op("cx", (0, 1))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 3)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_per_wire_x_cx_x_blocked_on_shared_qubit(self):
        """P1: X(0), CX(0,1), X(0) must NOT cancel (the CX touches qubit 0)."""
        ops = [Op("x", (0,)), Op("cx", (0, 1)), Op("x", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 3)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    # --------------------------------------------- PRIORITY 2: BACKEND AND IMPORTS TESTS
    def test_priority2_backend_fallback_reported(self):
        """P2: When real Qniverse SDK is missing, report explicitly flags backend as fallback."""
        ops = [Op("h", (0,))]
        res = optimize(ops)
        self.assertIn("backend", res.report)
        self.assertEqual(res.report["backend"], "fallback")
        self.assertTrue(any("fallback" in w.lower() for w in res.report["warnings"]))

    def test_priority2_backend_qniverse_reported_when_live(self):
        """P2: When live Qniverse SDK is simulated/imported, report sets backend to qniverse."""
        import types
        from unittest.mock import patch

        mock_gates_mod = types.ModuleType("qniverse.gates")
        class FakeGate:
            pass
        mock_gates_mod.h = FakeGate()

        mock_qc_mod = types.ModuleType("qniverse.QniverseCircuit")
        class FakeQC:
            def __init__(self):
                self.operations = []
                self.registers = []
            def add_register(self, reg):
                self.registers.append(reg)
            def add_gate(self, gate, *qubits):
                self.operations.append((gate, qubits))
        class FakeReg:
            def __init__(self, size, name):
                self.size = size
                self.name = name
            def __getitem__(self, idx):
                return (self.name, idx)
        mock_qc_mod.QniverseCircuit = FakeQC
        mock_qc_mod.QuantumRegister = FakeReg
        mock_qc_mod.ClassicalRegister = FakeReg

        with patch.dict(sys.modules, {
            "qniverse": types.ModuleType("qniverse"),
            "qniverse.gates": mock_gates_mod,
            "qniverse.QniverseCircuit": mock_qc_mod
        }):
            ops = [Op("h", (0,))]
            res = optimize(ops)
            self.assertEqual(res.report["backend"], "qniverse")

    # --------------------------------------------- PRIORITY 3: CONDITIONAL GATES TESTS
    def test_priority3_conditional_circuit_skipped_and_unchanged(self):
        """P3: Circuits with has_conditional=True are returned unchanged with a warning."""
        mock_qc = _make_mock_circuit(2, 1, [Op("x", (0,)), Op("x", (0,))])
        mock_qc.has_conditional = True

        res = optimize(mock_qc)

        # Circuit returned unchanged without modifying or inspecting operations
        self.assertIs(res.circuit, mock_qc)
        self.assertEqual(res.report["status"], "optimization skipped: conditional gates present")
        self.assertIn("optimization skipped: conditional gates present", res.report["warnings"])
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["reduction_percentage"], 0.0)
        self.assertEqual(res.report["passes_applied"], [])

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

    # ---------------------------------- DEF-03: RECONSTRUCTION TESTS
    def test_def03_reconstruction_unsupported_gate_raises(self):
        """DEF-03: Unsupported or unknown gates raise ValueError and are never dropped."""
        with self.assertRaises(ValueError) as ctx:
            _reconstruct_circuit([Op("completely_unsupported_gate", (0,))], 1, 0)
        self.assertIn("unsupported", str(ctx.exception).lower())

    def test_def03_reconstruction_preserves_all_ops_in_order(self):
        """DEF-03: Circuit reconstruction preserves exact operation count and ordering without silent drops."""
        ops = [
            Op("h", (0,)),
            Op("barrier", (0, 1)),
            Op("cx", (0, 1)),
            Op("reset", (1,)),
            Op("measure", (0,), (0,))
        ]
        qc = _reconstruct_circuit(ops, 2, 1)
        self.assertEqual(len(qc.operations), 5)
        self.assertEqual(qc.operations[0][0].name, "H")
        self.assertEqual(qc.operations[1][0].name, "Barrier")
        self.assertEqual(qc.operations[2][0].name, "CX")
        self.assertEqual(qc.operations[3][0].name, "Reset")
        self.assertEqual(qc.operations[4][0].name, "Measure")

    # ---------------------------------- DEF-04: PARAMETERIZED GATES TESTS
    def test_def04_parameterized_rx_rejected(self):
        """DEF-04: Parameterized RX gates are rejected with ValueError to prevent parameter loss."""
        with self.assertRaises(ValueError) as ctx:
            optimize([Op("rx", (0,))])
        self.assertIn("parameterized gate", str(ctx.exception).lower())

    def test_def04_parameterized_ry_rejected(self):
        """DEF-04: Parameterized RY gates are rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            optimize([Op("ry", (0,))])
        self.assertIn("parameterized gate", str(ctx.exception).lower())

    def test_def04_parameterized_rz_rejected(self):
        """DEF-04: Parameterized RZ gates are rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            optimize([Op("rz", (0,))])
        self.assertIn("parameterized gate", str(ctx.exception).lower())

    def test_def04_parameterized_controlled_gate_rejected(self):
        """DEF-04: Controlled parameterized gates (e.g. CRX) are rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            optimize([Op("crx", (0, 1))])
        self.assertIn("parameterized gate", str(ctx.exception).lower())

    def test_def04_equivalence_rejects_parameterized_circuit(self):
        """DEF-04: Equivalence engine never claims mathematical equivalence for parameterized circuits."""
        res = verify_equivalence([Op("rx", (0,))], [Op("rx", (0,))], 1)
        self.assertEqual(res["type"], "parameterized_unsupported")
        self.assertFalse(res["equivalent"])
        self.assertFalse(res["mathematical_equivalence_verified"])

    # ---------------------------------- DEF-05: MID-CIRCUIT STRUCTURAL TESTS
    def test_def05_adversarial_unitary_moved_across_measurement(self):
        """DEF-05: Unitary operations moved across a mid-circuit measurement fail structural verification."""
        orig = [Op("h", (0,)), Op("measure", (0,), (0,)), Op("x", (0,))]
        corrupted = [Op("h", (0,)), Op("x", (0,)), Op("measure", (0,), (0,))]  # X moved before measure
        res = verify_equivalence(orig, corrupted, 1)
        self.assertFalse(res["structural_preservation_verified"])
        self.assertIsNone(res["equivalent"])

    def test_def05_adversarial_unitary_moved_across_reset(self):
        """DEF-05: Unitary operations moved across a reset fail structural verification."""
        orig = [Op("x", (0,)), Op("reset", (0,)), Op("h", (0,))]
        corrupted = [Op("x", (0,)), Op("h", (0,)), Op("reset", (0,))]  # H moved before reset
        res = verify_equivalence(orig, corrupted, 1)
        self.assertFalse(res["structural_preservation_verified"])
        self.assertIsNone(res["equivalent"])

    def test_def05_mid_circuit_equivalent_remains_none(self):
        """DEF-05: Valid mid-circuit structural preservation still sets equivalent: None (semantic unverified)."""
        ops = [Op("h", (0,)), Op("measure", (0,), (0,)), Op("x", (0,)), Op("x", (0,))]
        res = optimize(ops)
        self.assertIsNone(res.report["equivalence"]["equivalent"])
        self.assertTrue(res.report["equivalence"]["structural_preservation_verified"])
        self.assertEqual(res.report["status"], "OK_SEMANTIC_UNVERIFIED")

    # ---------------------------------- DEF-06: TERMINAL MEASUREMENT BARRIERS TESTS
    def test_def06_terminal_measurement_removed_barrier_fails(self):
        """DEF-06: Removing a barrier in a terminal measurement circuit fails structural verification."""
        orig = [Op("h", (0,)), Op("barrier", (0,)), Op("measure", (0,), (0,))]
        corrupted = [Op("h", (0,)), Op("measure", (0,), (0,))]  # Barrier removed!
        res = verify_equivalence(orig, corrupted, 1)
        self.assertFalse(res["equivalent"])
        self.assertFalse(res["structural_preservation_verified"])

    def test_def06_terminal_measurement_relocated_barrier_fails(self):
        """DEF-06: Relocating a barrier across unitary operations in a terminal circuit fails structural verification."""
        orig = [Op("h", (0,)), Op("barrier", (0,)), Op("x", (0,)), Op("measure", (0,), (0,))]
        corrupted = [Op("h", (0,)), Op("x", (0,)), Op("barrier", (0,)), Op("measure", (0,), (0,))]  # Barrier moved
        res = verify_equivalence(orig, corrupted, 1)
        self.assertFalse(res["equivalent"])
        self.assertFalse(res["structural_preservation_verified"])

    # ---------------------------------- DEF-07: MALFORMED INPUTS & EMPTY CIRCUITS TESTS
    def test_def07_zero_qubit_with_operations_rejected(self):
        """DEF-07: Having operations with 0 declared qubits is rejected as dimension mismatch."""
        res = verify_equivalence([Op("x", (0,))], [Op("x", (0,))], 0)
        self.assertFalse(res["equivalent"])
        self.assertEqual(res["type"], "invalid")
        self.assertEqual(res["method"], "dimension_mismatch")

    def test_def07_invalid_qubit_index_rejected(self):
        """DEF-07: Out-of-range qubit indices in operations raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _validate_circuit_ops([Op("x", (5,))], num_qubits=2, num_clbits=0)
        self.assertIn("invalid qubit index", str(ctx.exception).lower())

    def test_def07_invalid_gate_arity_rejected(self):
        """DEF-07: Multi-qubit gates with invalid arity or duplicate operands raise ValueError."""
        # CX requires 2 qubits
        with self.assertRaises(ValueError):
            _validate_circuit_ops([Op("cx", (0,))], num_qubits=2, num_clbits=0)
        # CX cannot have duplicate qubits
        with self.assertRaises(ValueError):
            _validate_circuit_ops([Op("cx", (0, 0))], num_qubits=2, num_clbits=0)

    def test_def07_invalid_classical_index_rejected(self):
        """DEF-07: Out-of-range classical bit indices in measurements raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _validate_circuit_ops([Op("measure", (0,), (9,))], num_qubits=1, num_clbits=1)
        self.assertIn("invalid classical bit index", str(ctx.exception).lower())

    # ---------------------------------- DEF-08: REGISTER LAYOUT TESTS
    def test_def08_inconsistent_register_sum_rejected(self):
        """DEF-08: Inconsistent register sizes that do not sum to declared wire counts raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _validate_register_layouts([("q", 2)], num_qubits=3, c_layout=[], num_clbits=0)
        self.assertIn("does not match declared num_qubits", str(ctx.exception))

    def test_def08_duplicate_register_names_rejected(self):
        """DEF-08: Duplicate register names raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _validate_register_layouts([("q", 1), ("q", 1)], num_qubits=2, c_layout=[], num_clbits=0)
        self.assertIn("duplicate quantum register name", str(ctx.exception).lower())

    def test_def08_never_fabricates_fallback_wire(self):
        """DEF-08: Querying an out-of-range wire index raises ValueError rather than fabricating fallback wire."""
        with self.assertRaises(ValueError) as ctx:
            _reconstruct_circuit([Op("x", (2,))], num_qubits=2, num_clbits=0, q_layout=[("q", 2)])
        err_msg = str(ctx.exception).lower()
        self.assertTrue("out of range" in err_msg or "invalid qubit index" in err_msg)


if __name__ == "__main__":
    unittest.main()
