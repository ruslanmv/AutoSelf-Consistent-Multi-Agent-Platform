# scripts/export_for_latex.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exports \newcommand{} macros to latex_values.tex for manuscript inclusion.
Sources:
- results/throughput.summary.json
- results/makespan.summary.json
- results/ALL.summary.json (optional roll-up)
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
import pandas as pd

def macro(name: str, value: str) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}"

def load_json(path: str):
    if not os.path.exists(path):
        print(f"[export_for_latex] Missing {path}", file=sys.stderr)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_row(records, **match):
    for r in records:
        ok = all(r.get(k) == v for k, v in match.items())
        if ok: return r
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.environ.get("AUTOSELF_RESULTS_DIR","results"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = args.out or os.path.join(args.results, "latex_values.tex")

    macros = []

    # Throughput medians & CI for p=0.5 (autoself)
    thr = load_json(os.path.join(args.results, "throughput_summary.summary.json"))
    if thr and isinstance(thr, list):
        row = find_row(thr, scenario="autoself", p=0.5, metric="throughput_tpc")
        if row:
            m, lo, hi = row["median"], row["ci_low"], row["ci_high"]
            macros += [
                macro("ThroughputMedianPfive", f"{m:.2f}"),
                macro("ThroughputCIloPfive", f"{lo:.2f}"),
                macro("ThroughputCIhiPfive", f"{hi:.2f}"),
            ]
    # Delta % autoself vs baseline at p=0.5
    # Use raw CSV if needed
    tp_csv = os.path.join(args.results, "throughput.csv")
    if os.path.exists(tp_csv):
        df = pd.read_csv(tp_csv)
        df["p"] = pd.to_numeric(df["p"], errors="coerce")
        # median per (scenario, p)
        g = df.groupby(["scenario","p"]).throughput_tpc.median().unstack(0)
        if 0.5 in g.index and {"autoself","baseline"}.issubset(g.columns):
            baseline = float(g.loc[0.5, "baseline"])
            autoself = float(g.loc[0.5, "autoself"])
            if baseline != 0.0:
                delta = 100.0 * (autoself - baseline) / baseline
                macros.append(macro("ThroughputDeltaPctPfive", f"{delta:.1f}\\%"))

    # Makespan deltas (hazard, failure vs nominal)
    mk = load_json(os.path.join(args.results, "makespan_summary.summary.json"))
    if mk and isinstance(mk, list):
        df = pd.DataFrame(mk)
        if not df.empty:
            df = df[df["metric"]=="makespan_s"].set_index("scenario")
            if {"nominal","hazard","failure"}.issubset(df.index):
                nominal = float(df.loc["nominal","median"])
                if nominal > 0:
                    hazard_delta = 100.0*(float(df.loc["hazard","median"])/nominal - 1.0)
                    failure_delta = 100.0*(float(df.loc["failure","median"])/nominal - 1.0)
                    macros += [
                        macro("MakespanDeltaHazard", f"{hazard_delta:.1f}\\%"),
                        macro("MakespanDeltaFailure", f"{failure_delta:.1f}\\%"),
                    ]

    if not macros:
        print("[export_for_latex] No macros produced.", file=sys.stderr)
        return

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(macros) + "\n")
    print(f"[export_for_latex] wrote {out_path} ({len(macros)} macros)")

if __name__ == "__main__":
    main()
