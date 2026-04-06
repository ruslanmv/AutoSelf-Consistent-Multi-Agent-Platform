# autoself/metrics.py
# -*- coding: utf-8 -*-
"""
CSV helpers enforcing shared schema.
"""
from __future__ import annotations
import csv, os
from typing import Dict, Any, Iterable

SCHEMA = [
    "scenario","seed","p","makespan_s","throughput_tpc","conflicts","unsafe_entries","energy_j",
    "rules_ms","sim_ms","llm_ms","correction_ms","total_verif_ms"
]

TYPES = {
    "scenario": str, "seed": int, "p": float, "makespan_s": float, "throughput_tpc": float,
    "conflicts": int, "unsafe_entries": int, "energy_j": float,
    "rules_ms": float, "sim_ms": float, "llm_ms": float, "correction_ms": float, "total_verif_ms": float,
}

def ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

def normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in SCHEMA:
        v = row.get(k, None)
        if v is None:
            out[k] = None
            continue
        try:
            typ = TYPES[k]
            if typ is int:
                out[k] = int(v)
            elif typ is float:
                out[k] = float(v)
            else:
                out[k] = str(v)
        except Exception:
            out[k] = None
    return out

def append_row_csv(path: str, row: Dict[str, Any]) -> None:
    ensure_dir(path)
    write_header = not os.path.exists(path)
    norm = normalize(row)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if write_header:
            w.writeheader()
        w.writerow(norm)

def append_rows_csv(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    for r in rows:
        append_row_csv(path, r)
