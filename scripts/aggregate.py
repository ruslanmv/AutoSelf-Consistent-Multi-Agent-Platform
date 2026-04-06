#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggregate CSVs -> medians and 95% CI (percentile or bootstrap) into results/*.summary.json
"""
from __future__ import annotations
import argparse, json, os, sys
from typing import Dict, Any
import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# FIX: Define statistical functions locally to remove 'autoself' dependency
# -----------------------------------------------------------------------------
def percentile_ci(data: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """Calculate a percentile-based confidence interval (e.g., 95% CI)."""
    if len(data) == 0:
        return np.nan, np.nan
    low_percentile = 100 * (alpha / 2.0)
    high_percentile = 100 * (1.0 - alpha / 2.0)
    return np.percentile(data, low_percentile), np.percentile(data, high_percentile)

def bootstrap_ci(data: np.ndarray, n_boot: int = 1000, seed: int | None = None, alpha: float = 0.05) -> tuple[float, float]:
    """Calculate a bootstrap confidence interval for the median."""
    if len(data) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    # Generate bootstrap samples and calculate their medians
    boot_medians = [
        np.median(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_boot)
    ]
    # Calculate the confidence interval from the distribution of medians
    low_percentile = 100 * (alpha / 2.0)
    high_percentile = 100 * (1.0 - alpha / 2.0)
    return np.percentile(boot_medians, low_percentile), np.percentile(boot_medians, high_percentile)
# -----------------------------------------------------------------------------

SCHEMA_COLS = [
    "scenario","seed","p","makespan_s","throughput_tpc","conflicts","unsafe_entries","energy_j",
    "rules_ms","sim_ms","llm_ms","correction_ms","total_verif_ms"
]

def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(f"[aggregate] Missing CSV: {path}", file=sys.stderr)
        return pd.DataFrame(columns=SCHEMA_COLS)
    return pd.read_csv(path)

def summarize_metric(df: pd.DataFrame, group_cols, metric: str, ci_method: str="percentile") -> pd.DataFrame:
    if df.empty or metric not in df.columns:
        return pd.DataFrame()
    agg = []
    for keys, grp in df.groupby(group_cols):
        vals = grp[metric].dropna().to_numpy()
        if len(vals) == 0:
            continue
        med = float(np.median(vals))
        if ci_method == "bootstrap":
            lo, hi = bootstrap_ci(vals, n_boot=2000, seed=123)
        else:
            lo, hi = percentile_ci(vals)
        record = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
        record.update({"metric": metric, "median": med, "ci_low": float(lo), "ci_high": float(hi), "n": int(len(vals))})
        agg.append(record)
    return pd.DataFrame(agg)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.environ.get("AUTOSELF_RESULTS_DIR","results"))
    ap.add_argument("--ci", choices=["percentile","bootstrap"], default="percentile")
    args = ap.parse_args()

    os.makedirs(args.results, exist_ok=True)

    throughput = load_csv(os.path.join(args.results, "throughput.csv"))
    makespan   = load_csv(os.path.join(args.results, "makespan.csv"))
    conflicts  = load_csv(os.path.join(args.results, "conflicts.csv"))
    overhead   = load_csv(os.path.join(args.results, "overhead.csv"))
    ablations  = load_csv(os.path.join(args.results, "ablations.csv"))

    summaries: Dict[str, Any] = {}

    if not throughput.empty:
        s = summarize_metric(throughput, ["scenario","p"], "throughput_tpc", ci_method=args.ci)
        summaries["throughput_summary"] = s.to_dict(orient="records")

    if not makespan.empty:
        s = summarize_metric(makespan, ["scenario"], "makespan_s", ci_method=args.ci)
        summaries["makespan_summary"] = s.to_dict(orient="records")

    if not conflicts.empty:
        s = summarize_metric(conflicts, ["scenario","p"], "conflicts", ci_method=args.ci)
        summaries["conflicts_summary"] = s.to_dict(orient="records")

    if not overhead.empty:
        for col in ["rules_ms","sim_ms","llm_ms","correction_ms","total_verif_ms"]:
            s = summarize_metric(overhead, ["scenario"], col, ci_method=args.ci)
            summaries.setdefault("overhead_summary", {})[col] = s.to_dict(orient="records")

    # Write individual summary json files
    def dump(name: str, obj: Any):
        path = os.path.join(args.results, f"{name}.summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        print(f"[aggregate] wrote {path}")

    for k, v in summaries.items():
        dump(k, v)

    # convenience combined file
    dump("ALL", summaries)

if __name__ == "__main__":
    main()