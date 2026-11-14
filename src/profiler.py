# profiler.py

from collections import Counter
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Operation:
    name: str
    qubits: List[int]
    kind: str = "gate"
    # kind: gate, measurement, reset, barrier, unsupported


def profile_circuit(
    operations: List[Operation],
    declared_qubits: int
) -> Dict[str, Any]:

    if declared_qubits < 0:
        raise ValueError("Declared qubit count cannot be negative.")

    gate_counts = Counter()
    used_qubits = set()

    single_qubit_gates = 0
    multi_qubit_gates = 0
    two_qubit_gates = 0

    operation_counts = Counter()
    unsupported_operations = []

    # Track the most recent occupied layer for each qubit.
    last_layer = [0] * declared_qubits

    circuit_depth = 0

    for index, op in enumerate(operations):

        if not op.name:
            raise ValueError(f"Operation {index} has no name.")

        if not op.qubits:
            raise ValueError(
                f"Operation {index} ({op.name}) has no qubits."
            )

        if len(set(op.qubits)) != len(op.qubits):
            raise ValueError(
                f"Operation {index} ({op.name}) repeats a qubit."
            )

        for q in op.qubits:
            if not isinstance(q, int) or q < 0 or q >= declared_qubits:
                raise ValueError(
                    f"Invalid qubit index {q} in operation {op.name}."
                )

        used_qubits.update(op.qubits)
        operation_counts[op.kind] += 1

        # Count quantum gates separately from measurements/resets/barriers.
        if op.kind == "gate":
            gate_counts[op.name] += 1

            if len(op.qubits) == 1:
                single_qubit_gates += 1
            else:
                multi_qubit_gates += 1

            if len(op.qubits) == 2:
                two_qubit_gates += 1

        elif op.kind == "unsupported":
            unsupported_operations.append({
                "operation": op.name,
                "qubits": op.qubits,
                "position": index
            })

        elif op.kind not in {"measurement", "reset", "barrier"}:
            raise ValueError(
                f"Unknown operation kind '{op.kind}' for {op.name}."
            )

        # Earliest available layer for this operation.
        layer = max(last_layer[q] for q in op.qubits) + 1

        # All qubits used by this operation become occupied at this layer.
        for q in op.qubits:
            last_layer[q] = layer

        circuit_depth = max(circuit_depth, layer)

    return {
        "total_gate_count": sum(gate_counts.values()),
        "gate_count_by_type": dict(gate_counts),

        "declared_qubits": declared_qubits,
        "used_qubits": len(used_qubits),
        "unused_qubits": declared_qubits - len(used_qubits),

        "single_qubit_gate_count": single_qubit_gates,
        "multi_qubit_gate_count": multi_qubit_gates,
        "two_qubit_gate_count": two_qubit_gates,

        "operation_count": len(operations),
        "operation_count_by_kind": dict(operation_counts),

        "circuit_depth": circuit_depth,
        "unsupported_operations": unsupported_operations
    }


def print_profile(profile: Dict[str, Any]) -> None:
    print("\n========== CIRCUIT PROFILE ==========")

    for key, value in profile.items():
        print(f"{key}: {value}")

    print("=====================================\n")


# Small test circuit
if __name__ == "__main__":

    sample_operations = [
        Operation("H", [0]),
        Operation("X", [1]),
        Operation("CNOT", [0, 1]),
        Operation("Z", [0]),
        Operation("measurement", [1], "measurement")
    ]

    result = profile_circuit(
        operations=sample_operations,
        declared_qubits=2
    )

    print_profile(result)
