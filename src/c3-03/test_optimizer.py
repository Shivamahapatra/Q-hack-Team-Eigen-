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

from c1_01_final import Op, unitary, equal_up_to_phase, profile
import qniverse_adapter as qa
from optimizer import (
    optimize,
    draw_text,
    CircuitDiagram,
    verify_equivalence,
    OptimizationResult,
    PASS_IDENTITY_REMOVAL,
    PASS_SELF_INVERSE_CANCELLATION,
    PASS_CX_CANCELLATION,
    PASS_X_CANCELLATION,
    PASS_Y_CANCELLATION,
    PASS_Z_CANCELLATION,
    PASS_H_CANCELLATION,
    PASS_CY_CANCELLATION,
    PASS_CZ_CANCELLATION,
    PASS_CH_CANCELLATION,
    PASS_SWAP_CANCELLATION,
    PASS_CCX_CANCELLATION,
    PASS_CSWAP_CANCELLATION,
    PASS_S_SDG_CANCELLATION,
    PASS_T_TDG_CANCELLATION,
    SUPPORTED_PASSES,
    _reconstruct_circuit,
    _validate_register_layouts,
    _validate_circuit_ops,
    _verify_structural_placement,
    _decompose_wide_barrier,
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
        self.assertEqual(res.report["fallback_reason"], "Qniverse SDK not installed (qniverse package missing)")
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

    # --------------------------------------------- PRIORITY 4: EXPANDED RULES TESTS
    def test_priority4_y_cancellation(self):
        """P4: Y-Y cancellation enabled individually with unitary equivalence verified."""
        ops = [Op("y", (0,)), Op("y", (0,))]
        res = optimize(ops, enabled_passes=[PASS_Y_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_priority4_cy_cancellation_and_asymmetry(self):
        """P4: CY-CY cancels on identical (c, t); reversed (t, c) does NOT cancel."""
        # Matching control-target
        ops1 = [Op("cy", (0, 1)), Op("cy", (0, 1))]
        res1 = optimize(ops1, enabled_passes=[PASS_CY_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        # Reversed control-target
        ops2 = [Op("cy", (0, 1)), Op("cy", (1, 0))]
        res2 = optimize(ops2, enabled_passes=[PASS_CY_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 0)
        self.assertEqual(res2.report["after"]["total_gates"], 2)

    def test_priority4_cz_cancellation_and_symmetric_qubits(self):
        """P4: CZ-CZ cancels on identical (c, t) AND symmetric swapped (t, c) qubits."""
        # Matching
        ops1 = [Op("cz", (0, 1)), Op("cz", (0, 1))]
        res1 = optimize(ops1, enabled_passes=[PASS_CZ_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        # Swapped qubits: CZ(0,1) and CZ(1,0) are mathematically identical
        ops2 = [Op("cz", (0, 1)), Op("cz", (1, 0))]
        res2 = optimize(ops2, enabled_passes=[PASS_CZ_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 2)
        self.assertEqual(res2.report["after"]["total_gates"], 0)
        self.assertTrue(res2.report["equivalence"]["equivalent"])

    def test_priority4_ch_cancellation_and_asymmetry(self):
        """P4: CH-CH cancels on matching (c, t); reversed (t, c) does NOT cancel."""
        ops1 = [Op("ch", (0, 1)), Op("ch", (0, 1))]
        res1 = optimize(ops1, enabled_passes=[PASS_CH_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        ops2 = [Op("ch", (0, 1)), Op("ch", (1, 0))]
        res2 = optimize(ops2, enabled_passes=[PASS_CH_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 0)
        self.assertEqual(res2.report["after"]["total_gates"], 2)

    def test_priority4_swap_cancellation_and_symmetric_qubits(self):
        """P4: SWAP-SWAP cancels on identical AND swapped qubit tuples."""
        # Matching
        ops1 = [Op("swap", (0, 1)), Op("swap", (0, 1))]
        res1 = optimize(ops1, enabled_passes=[PASS_SWAP_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        # Swapped: SWAP(0,1) and SWAP(1,0) are identical operations
        ops2 = [Op("swap", (0, 1)), Op("swap", (1, 0))]
        res2 = optimize(ops2, enabled_passes=[PASS_SWAP_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 2)
        self.assertEqual(res2.report["after"]["total_gates"], 0)
        self.assertTrue(res2.report["equivalence"]["equivalent"])

    def test_priority4_ccx_cancellation(self):
        """P4: CCX (Toffoli) consecutive pair on identical wires cancels out."""
        ops = [Op("ccx", (0, 1, 2)), Op("ccx", (0, 1, 2))]
        res = optimize(ops, enabled_passes=[PASS_CCX_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_priority4_cswap_cancellation(self):
        """P4: CSWAP (Fredkin) consecutive pair on identical wires cancels out."""
        ops = [Op("cswap", (0, 1, 2)), Op("cswap", (0, 1, 2))]
        res = optimize(ops, enabled_passes=[PASS_CSWAP_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_priority4_s_sdg_inverse_pair_cancellation(self):
        """P4: S and SDG inverse pairs cancel on identical wires in both directions."""
        # S then SDG
        ops1 = [Op("s", (0,)), Op("sdg", (0,))]
        res1 = optimize(ops1, enabled_passes=[PASS_S_SDG_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        # SDG then S
        ops2 = [Op("sdg", (0,)), Op("s", (0,))]
        res2 = optimize(ops2, enabled_passes=[PASS_S_SDG_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 2)
        self.assertEqual(res2.report["after"]["total_gates"], 0)
        self.assertTrue(res2.report["equivalence"]["equivalent"])

    def test_priority4_t_tdg_inverse_pair_cancellation(self):
        """P4: T and TDG inverse pairs cancel on identical wires in both directions."""
        # T then TDG
        ops1 = [Op("t", (0,)), Op("tdg", (0,))]
        res1 = optimize(ops1, enabled_passes=[PASS_T_TDG_CANCELLATION])
        self.assertEqual(res1.report["gates_removed"], 2)
        self.assertEqual(res1.report["after"]["total_gates"], 0)
        self.assertTrue(res1.report["equivalence"]["equivalent"])

        # TDG then T
        ops2 = [Op("tdg", (0,)), Op("t", (0,))]
        res2 = optimize(ops2, enabled_passes=[PASS_T_TDG_CANCELLATION])
        self.assertEqual(res2.report["gates_removed"], 2)
        self.assertEqual(res2.report["after"]["total_gates"], 0)
        self.assertTrue(res2.report["equivalence"]["equivalent"])

    def test_priority4_grouped_self_inverse_pass_cancels_all(self):
        """P4: Grouped PASS_SELF_INVERSE_CANCELLATION reduces all supported self-inverses."""
        ops = [
            Op("y", (0,)), Op("y", (0,)),
            Op("cz", (0, 1)), Op("cz", (1, 0)),
            Op("swap", (0, 1)), Op("swap", (0, 1)),
            Op("ccx", (0, 1, 2)), Op("ccx", (0, 1, 2)),
            Op("cswap", (0, 1, 2)), Op("cswap", (0, 1, 2)),
        ]
        res = optimize(ops, enabled_passes=[PASS_SELF_INVERSE_CANCELLATION])
        self.assertEqual(res.report["gates_removed"], 10)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    # --------------------------------------------- WIDE BARRIER & REBUILD HANDLING TESTS
    def test_decompose_wide_barrier_structure(self):
        """Wide barrier decomposition creates forward and backward 2-qubit chains."""
        # 1-qubit and 2-qubit barriers remain unchanged
        self.assertEqual(_decompose_wide_barrier((0,)), [(0,)])
        self.assertEqual(_decompose_wide_barrier((0, 1)), [(0, 1)])

        # 3-qubit barrier: forward (0,1), (1,2) and backward (0,1)
        self.assertEqual(
            _decompose_wide_barrier((0, 1, 2)),
            [(0, 1), (1, 2), (0, 1)]
        )

        # 4-qubit barrier: forward (0,1), (1,2), (2,3) and backward (1,2), (0,1)
        self.assertEqual(
            _decompose_wide_barrier((0, 1, 2, 3)),
            [(0, 1), (1, 2), (2, 3), (1, 2), (0, 1)]
        )

    def test_wide_barrier_rebuild_on_real_sdk_emits_at_most_2_qubits(self):
        """Real SDK finding: Rebuild decomposes wide barriers into <=2 qubit gates without fallback."""
        import types
        from unittest.mock import patch

        mock_gates_mod = types.ModuleType("qniverse.gates")
        class FakeBarrier:
            pass
        class FakeH:
            pass
        mock_gates_mod.barrier = FakeBarrier()
        mock_gates_mod.h = FakeH()

        barrier_calls = []

        mock_qc_mod = types.ModuleType("qniverse.QniverseCircuit")
        class FakeQC:
            def __init__(self):
                self.operations = []
                self.registers = []
            def add_register(self, reg):
                self.registers.append(reg)
            def add_gate(self, gate, *qubits):
                if gate is mock_gates_mod.barrier:
                    if len(qubits) > 2:
                        raise ValueError(f"Gate 'BARRIER' requires 1 or 2 qubits, but got {len(qubits)}")
                    barrier_calls.append(tuple(q[1] for q in qubits))
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
            ops = [Op("h", (0,)), Op("barrier", (0, 1, 2)), Op("h", (2,))]
            res = optimize(ops)
            # Must successfully rebuild on qniverse backend without falling back
            self.assertEqual(res.report["backend"], "qniverse")
            self.assertIsNone(res.report["fallback_reason"])
            # Verified that barrier was emitted as (0,1), (1,2), (0,1)
            self.assertEqual(barrier_calls, [(0, 1), (1, 2), (0, 1)])
            # All barrier calls had at most 2 qubits
            self.assertTrue(all(len(c) <= 2 for c in barrier_calls))

    def test_profiler_depth_identical_for_wide_barrier_and_chain(self):
        """Profiler depth rule gives identical depth for wide barrier and rebuilt chain."""
        # Scenario 1: 3-qubit barrier with gates on different qubits
        ops_wide1 = [Op("h", (0,)), Op("x", (1,)), Op("barrier", (0, 1, 2)), Op("z", (2,))]
        ops_chain1 = [
            Op("h", (0,)), Op("x", (1,)),
            Op("barrier", (0, 1)), Op("barrier", (1, 2)), Op("barrier", (0, 1)),
            Op("z", (2,))
        ]
        p_wide1 = profile(ops_wide1, 3)
        p_chain1 = profile(ops_chain1, 3)
        self.assertEqual(p_wide1["depth"], p_chain1["depth"])
        self.assertEqual(p_wide1["depth"], 2)

        # Scenario 2: 4-qubit barrier with staggered initial depths
        ops_wide2 = [
            Op("h", (0,)), Op("x", (0,)), Op("y", (2,)),
            Op("barrier", (0, 1, 2, 3)),
            Op("h", (3,))
        ]
        ops_chain2 = [
            Op("h", (0,)), Op("x", (0,)), Op("y", (2,)),
            Op("barrier", (0, 1)), Op("barrier", (1, 2)), Op("barrier", (2, 3)),
            Op("barrier", (1, 2)), Op("barrier", (0, 1)),
            Op("h", (3,))
        ]
        p_wide2 = profile(ops_wide2, 4)
        p_chain2 = profile(ops_chain2, 4)
        self.assertEqual(p_wide2["depth"], p_chain2["depth"])
        self.assertEqual(p_wide2["depth"], 3)

    def test_wide_barrier_blocks_cancellation_h0(self):
        """Wide barrier (0,1,2) blocks H(0) - H(0) cancellation across it."""
        ops = [Op("h", (0,)), Op("barrier", (0, 1, 2)), Op("h", (0,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)

    def test_wide_barrier_blocks_cancellation_x2(self):
        """Wide barrier (0,1,2) blocks X(2) - X(2) cancellation across it."""
        ops = [Op("x", (2,)), Op("barrier", (0, 1, 2)), Op("x", (2,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 0)
        self.assertEqual(res.report["after"]["total_gates"], 2)

    def test_disjoint_barrier_allows_cancellation_x2(self):
        """Barrier on (0,1) does NOT touch qubit 2; X(2) - X(2) cancels."""
        ops = [Op("x", (2,)), Op("barrier", (0, 1)), Op("x", (2,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 0)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_real_sdk_rejection_reports_fallback_reason(self):
        """When real SDK rejects an operation during rebuild, report sets backend=fallback and fallback_reason."""
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
                raise RuntimeError("Simulated Qniverse hardware constraint: gate rejected")

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
            self.assertEqual(res.report["backend"], "fallback")
            self.assertEqual(res.report["fallback_reason"], "Simulated Qniverse hardware constraint: gate rejected")
            self.assertTrue(any("Simulated Qniverse hardware constraint" in w for w in res.report["warnings"]))

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

    # ---------------------------------- DRAW_TEXT & CIRCUIT DIAGRAM TESTS
    def test_draw_text_column_count_matches_circuit_depth(self):
        """Verifies that the number of columns in draw_text matches the circuit depth."""
        test_cases = [
            # 1. Single qubit sequential gates
            ([Op("h", (0,)), Op("x", (0,)), Op("z", (0,))], 1),
            # 2. Multi-qubit disjoint parallel gates
            ([Op("h", (0,)), Op("x", (1,)), Op("y", (2,))], 3),
            # 3. Entangling Bell pair + single-qubit gate
            ([Op("h", (0,)), Op("cx", (0, 1)), Op("t", (1,))], 2),
            # 4. Mixed gates with terminal measurements
            ([Op("h", (0,)), Op("cx", (0, 1)), Op("measure", (0,), (0,)), Op("measure", (1,), (1,))], 2),
            # 5. Staggered gates on 3 qubits
            ([Op("h", (0,)), Op("x", (1,)), Op("cx", (0, 1)), Op("cx", (1, 2)), Op("z", (2,))], 3),
            # 6. Empty circuit
            ([], 2),
            # 7. Circuit with barrier (BUG-04: num_columns matches profile depth)
            ([Op("h", (0,)), Op("barrier", (0, 1)), Op("h", (0,))], 2),
            ([Op("h", (0,)), Op("barrier", (0, 1)), Op("h", (1,))], 2),
        ]

        for ops, nq in test_cases:
            p = profile(ops, nq)
            diagram = draw_text(ops, nq, print_output=False)

            # 1. Assert metadata num_columns matches profiler depth
            self.assertEqual(
                diagram.num_columns,
                p["depth"],
                f"Failed for ops={ops}: expected depth {p['depth']}, got {diagram.num_columns}"
            )

            # 2. Assert diagram has one line per qubit
            lines = [line for line in diagram.strip().splitlines() if line]
            self.assertEqual(len(lines), nq)

            # 3. If there are columns, assert every wire has the exact same total character length
            if diagram.num_columns > 0:
                first_len = len(lines[0])
                for line in lines:
                    self.assertEqual(len(line), first_len, "All qubit lines must have identical column length")

    def test_draw_text_barrier_vertical_marker(self):
        """draw_text places vertical marker '|' on barrier qubits."""
        ops = [Op("h", (0,)), Op("barrier", (0, 1)), Op("h", (0,))]
        diagram = draw_text(ops, 2, print_output=False)
        self.assertIn("|", diagram)
        lines = diagram.strip().splitlines()
        self.assertIn("|", lines[0])  # q0 has barrier
        self.assertIn("|", lines[1])  # q1 has barrier

    def test_draw_text_qniverse_circuit_input(self):
        """draw_text accepts a circuit object directly."""
        ops = [Op("h", (0,)), Op("cx", (0, 1)), Op("measure", (1,), (0,))]
        res = optimize(ops)
        diagram = draw_text(res.circuit, print_output=False)
        p = profile(ops, 2)
        self.assertEqual(diagram.num_columns, p["depth"])
        self.assertEqual(diagram.num_columns, 3)
        self.assertIn("@", diagram)
        self.assertIn("(+)", diagram)
        self.assertIn("M", diagram)

    def test_draw_text_formatting_structure(self):
        """draw_text produces expected wire labels and gate symbols."""
        ops = [
            Op("h", (0,)),
            Op("cx", (0, 1)),
            Op("t", (1,)),
            Op("measure", (0,), (0,)),
        ]
        diagram = draw_text(ops, 2, print_output=False)
        lines = diagram.strip().splitlines()
        self.assertTrue(lines[0].startswith("q0: --"))
        self.assertTrue(lines[1].startswith("q1: --"))
        # q0 should contain H, @, M
        self.assertIn("H", lines[0])
        self.assertIn("@", lines[0])
        self.assertIn("M", lines[0])
        # q1 should contain (+), T
        self.assertIn("(+)", lines[1])
        self.assertIn("T", lines[1])

    # ---------------------------------- BUG-01 TO BUG-08 REGRESSION TESTS
    def test_bug01_illegal_cancellation_across_shared_barrier_rejected(self):
        """BUG-01: verify_equivalence rejects circuits where gates cancelled across a shared barrier."""
        orig = [Op("x", (0,)), Op("barrier", (0,)), Op("x", (0,))]
        corrupted = [Op("barrier", (0,))]
        res = verify_equivalence(orig, corrupted, 1)
        self.assertFalse(res["equivalent"])
        self.assertFalse(res["structural_preservation_verified"])

        # Terminal measurement variant with illegal cancellation across barrier
        orig_term = [Op("h", (0,)), Op("x", (0,)), Op("barrier", (0,)), Op("x", (0,)), Op("measure", (0,), (0,))]
        corrupted_term = [Op("h", (0,)), Op("barrier", (0,)), Op("measure", (0,), (0,))]
        res_term = verify_equivalence(orig_term, corrupted_term, 1)
        self.assertFalse(res_term["equivalent"])
        self.assertFalse(res_term["structural_preservation_verified"])

        # Mid-circuit measurement variant with illegal cancellation across measurement
        orig_mid = [Op("x", (0,)), Op("measure", (0,), (0,)), Op("x", (0,))]
        corrupted_mid = [Op("measure", (0,), (0,))]
        res_mid = verify_equivalence(orig_mid, corrupted_mid, 1)
        self.assertFalse(res_mid["structural_preservation_verified"])

    def test_bug02_uppercase_op_names_normalized_and_optimized(self):
        """BUG-02: Uppercase gate names in Op are normalized and optimize cleanly without crashing."""
        ops = [Op("H", (0,)), Op("H", (0,)), Op("X", (1,))]
        res = optimize(ops)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.report["after"]["total_gates"], 1)
        self.assertTrue(res.report["equivalence"]["equivalent"])

    def test_bug03_out_of_bounds_register_index_rejected_in_qasm_and_adapter(self):
        """BUG-03: Out-of-bounds register index in multi-register QASM or wire repr raises ValueError."""
        from c1_01_final import parse_qasm
        bad_qasm = "OPENQASM 2.0;\nqreg a[2];\nqreg b[2];\nx a[2];\n"
        with self.assertRaises(ValueError) as ctx:
            parse_qasm(bad_qasm)
        self.assertIn("out of bounds", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            qa._parse_wire("Qubit(QuantumRegister(2, 'a'), 2)")
        self.assertIn("out of bounds", str(ctx2.exception).lower())

    def test_bug05_verify_equivalence_checks_optimized_ops_for_non_unitary(self):
        """BUG-05: verify_equivalence detects injected reset or measure in optimized_ops."""
        res_reset = verify_equivalence([Op("h", (0,))], [Op("h", (0,)), Op("reset", (0,))], 1)
        self.assertNotEqual(res_reset["type"], "unitary")
        self.assertFalse(res_reset["mathematical_equivalence_verified"])
        self.assertFalse(res_reset["structural_preservation_verified"])

        res_meas = verify_equivalence([Op("h", (0,))], [Op("h", (0,)), Op("measure", (0,), (0,))], 1)
        self.assertNotEqual(res_meas["type"], "unitary")
        self.assertFalse(res_meas["structural_preservation_verified"])

    def test_bug06_qasm_string_preserves_multi_registers_and_unmeasured_cregs(self):
        """BUG-06: Optimizing a raw OpenQASM string preserves multi-register layout and declared creg size."""
        qasm_str = (
            "OPENQASM 2.0;\n"
            'include "qelib1.inc";\n'
            "qreg data[2];\n"
            "qreg anc[1];\n"
            "creg c_out[4];\n"
            "x anc[0];\n"
            "x anc[0];\n"
            "h data[0];\n"
            "measure data[0] -> c_out[0];\n"
        )
        res = optimize(qasm_str)
        self.assertEqual(res.report["gates_removed"], 2)
        self.assertEqual(res.circuit.num_qubits, 3)
        self.assertEqual(res.circuit.num_clbits, 4)
        reg_reprs = [repr(r) for r in res.circuit.registers]
        self.assertIn("QuantumRegister(2, 'data')", reg_reprs)
        self.assertIn("QuantumRegister(1, 'anc')", reg_reprs)
        self.assertIn("ClassicalRegister(4, 'c_out')", reg_reprs)

    def test_bug07_decompose_supports_ch_and_cswap(self):
        """BUG-07: decompose() in c1_01_final supports ch and cswap into Clifford+T."""
        from c1_01_final import decompose
        for gname, nq in [("ch", 2), ("cswap", 3)]:
            orig = [Op(gname, tuple(range(nq)))]
            dec, rep = decompose(orig, nq, {"h", "t", "tdg", "cx"})
            self.assertEqual(rep["status"], "OK")
            self.assertIsNotNone(dec)
            self.assertTrue(equal_up_to_phase(unitary(orig, nq), unitary(dec, nq)))


if __name__ == "__main__":
    unittest.main()
