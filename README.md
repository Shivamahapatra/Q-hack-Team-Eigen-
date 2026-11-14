# Team Eigen — PESU - C-DAC Quantum Hackathon 2026

**Institution**: PES University (PESU), Bengaluru  
**Target Platform**: C-DAC Qniverse Platform & QSDK  
**Primary Challenge**: **QC-C1-01** — Circuit Profiling and Limited Basis-Gate Decomposition  

---

## 🚀 Quickstart

### 1. Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run All Tests & Benchmarks
```powershell
python src/qc_c1_01.py
```

Expected output:
```
all tests passed
{
  "basis": ["cx", "h"],
  "before": { "total_gates": 2, "by_type": {"h": 1, "swap": 1}, "depth": 3 },
  "after":  { "total_gates": 4, "by_type": {"h": 1, "cx": 3},   "depth": 5 },
  "status": "OK"
}
```

---

## 📚 Documentation Index

All hackathon deliverables are organized across dedicated documents in [`docs/`](docs/):

| Document | Purpose |
| :--- | :--- |
| **[`docs/01_team_info.md`](docs/01_team_info.md)** | Team members, GitHub handles, role matrix, and problem statement scope. |
| **[`docs/02_technical_approach.md`](docs/02_technical_approach.md)** | Earliest-layer DAG depth scheduler, recursive basis decomposition rules, and matrix verification. |
| **[`docs/03_performance_report.md`](docs/03_performance_report.md)** | Genuine execution benchmarks (depth comparisons, gate expansion tables, matrix fidelity). |
| **[`docs/04_working_product.md`](docs/04_working_product.md)** | Product summary, execution instructions, Python API reference, and judge viva demonstration script. |
| **[`docs/05_ai_usage_declaration.md`](docs/05_ai_usage_declaration.md)** | Official hackathon AI compliance log for all team members (Antigravity, Claude, ChatGPT, Gemini). |

---

## 👥 Team Eigen Members

- **Dhruti** (`dhruti218`) — Documentation, QA & AI Compliance Lead
- **Shiva Mahapatra** (`Shivamahapatra`) — Lead Developer (QSDK & Ingestion)
- **Advik Singla** (`adviksingla`) — Core Developer (Decomposition & Verifier)
- **Saumitra Gupta** (`saumitraguptafr`) — Presenter & Viva Evaluation Lead
