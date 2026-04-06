#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exp1_analyze.py — Concise analyzer for Experiment 1 (Hazards & Failures)

Reads the CSVs emitted by `first_experiment.py` and prints a short, paper-oriented
summary; also writes LaTeX tables and a Markdown report.

Inputs (under results/):
- timeline_nominal.csv, timeline_hazard.csv, timeline_failure.csv
- tasks_nominal.csv,    tasks_hazard.csv,    tasks_failure.csv   (optional)
- makespan.csv, conflicts.csv, overhead.csv                      (optional)

Outputs (under manuscript_results/):
- table_hazard_safety.tex, table_energy_delta.tex (mean ±95% CI)
- exp1_report.md (human-readable summary)

Usage:
    python exp1_analyze.py
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

# ---------------- util ----------------

def _ensure_dirs() -> None:
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)


def _read_csv(path: str, required: bool = True) -> pd.DataFrame:
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError(f"Missing required file: {path}")
        return pd.DataFrame()
    return pd.read_csv(path)


def _mean_ci95(x: np.ndarray) -> Tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0:
        return float("nan"), float("nan"), 0
    m = float(np.mean(x))
    if n == 1:
        return m, 0.0, 1
    s = float(np.std(x, ddof=1))
    ci = 1.96 * (s / np.sqrt(n))
    return m, ci, n


# ---------------- analysis ----------------

def analyze() -> Dict[str, Any]:
    _ensure_dirs()
    out: Dict[str, Any] = {}

    # --- Nominal timeline ---
    t_nom = _read_csv(os.path.join(RESULTS_DIR, "timeline_nominal.csv"), required=False)
    makespan_nom = float(t_nom["time_s"].max()) if not t_nom.empty else float("nan")
    tasks_nom = float(t_nom.get("tasks_completed", pd.Series([np.nan])).max())

    # --- Hazard timeline ---
    t_haz = _read_csv(os.path.join(RESULTS_DIR, "timeline_hazard.csv"), required=False)
    n_seeds_h = int(t_haz.get("seed", pd.Series([0])).nunique()) if not t_haz.empty else 0

    interrupted_counts: List[int] = []
    pause_durations: List[float] = []
    unsafe_entries: List[int] = []
    if not t_haz.empty:
        for s, sub in t_haz.groupby(t_haz.get("seed", pd.Series([0]))):
            sub = sub.sort_values("time_s")

            # FIX: Detect hazard from the 'issue_kinds' column, which exists in the data.
            # The original code looked for 'hazard_active', which is not saved in the CSV.
            if "issue_kinds" in sub.columns:
                is_hazard = sub["issue_kinds"].str.contains("dust_storm_active", na=False)
            else:
                is_hazard = pd.Series(False, index=sub.index)

            plateau = ((sub["tasks_completed"].diff().fillna(0) == 0) & is_hazard).sum()
            pause_duration = is_hazard.sum() * np.mean(np.diff(sub['time_s'])) if is_hazard.any() else 0.0

            interrupted_counts.append(int(plateau))
            pause_durations.append(float(pause_duration))
            unsafe_entries.append(int(sub.get("unsafe_entries", pd.Series([0])).max()))
    m_inter, ci_inter, n_inter = _mean_ci95(np.array(interrupted_counts, float))
    m_pause, ci_pause, n_pause = _mean_ci95(np.array(pause_durations, float))
    m_unsafe, ci_unsafe, n_unsafe = _mean_ci95(np.array(unsafe_entries, float))

    # --- Failure timeline & tasks ---
    t_fail = _read_csv(os.path.join(RESULTS_DIR, "timeline_failure.csv"), required=False)
    tasks_fail = _read_csv(os.path.join(RESULTS_DIR, "tasks_failure.csv"), required=False)
    retries_by_seed: List[float] = []
    if not tasks_fail.empty:
        # NOTE: If retries are 0, it's likely a data generation issue. This logic correctly sums them.
        for s, sub in tasks_fail.groupby(tasks_fail.get("seed", pd.Series([0]))):
            retries_by_seed.append(float(sub.get("retry_count", 0).sum()))
    m_retry, ci_retry, n_retry = _mean_ci95(np.array(retries_by_seed, float))

    # --- Energy/Makespan Delta Calculation ---
    delta_pct_by_seed: List[float] = []
    delta_metric = "Energy" # Assume we are using energy first
    # Try to calculate using 'energy_j' column
    if not t_fail.empty and not t_nom.empty and ("energy_j" in t_fail.columns) and ("energy_j" in t_nom.columns):
        e_nom = t_nom.groupby(t_nom.get("seed", pd.Series([0])))["energy_j"].max()
        e_fail = t_fail.groupby(t_fail.get("seed", pd.Series([0])))["energy_j"].max()
        seeds = sorted(set(e_nom.index).union(set(e_fail.index)))
        for s in seeds:
            en = float(e_nom.get(s, np.nan))
            ef = float(e_fail.get(s, np.nan))
            if en > 0 and not (np.isnan(en) or np.isnan(ef)):
                delta_pct_by_seed.append(100.0 * (ef / en - 1.0))

    # FIX: If energy calculation failed (e.g., column missing), fall back to makespan.
    if not delta_pct_by_seed and not t_fail.empty and not t_nom.empty:
        delta_metric = "Makespan" # Update the metric name for the report
        m_nom = t_nom.groupby(t_nom.get("seed", pd.Series([0])))["time_s"].max()
        m_fail = t_fail.groupby(t_fail.get("seed", pd.Series([0])))["time_s"].max()
        seeds = sorted(set(m_nom.index).union(set(m_fail.index)))
        for s in seeds:
            mn = float(m_nom.get(s, np.nan))
            mf = float(m_fail.get(s, np.nan))
            if mn > 0 and not (np.isnan(mn) or np.isnan(mf)):
                delta_pct_by_seed.append(100.0 * (mf / mn - 1.0))

    m_dE, ci_dE, n_dE = _mean_ci95(np.array(delta_pct_by_seed, float))

    # --- Write LaTeX tables ---
    lines_h = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Hazard safety metrics (mean $\\pm$ 95\\% CI) across seeds.}",
        "\\label{tab:hazard_safety}",
        "\\begin{tabular}{lcc}",
        "\\toprule",
        "Metric & Value & N \\\\",
        "\\midrule",
        f"Unsafe-state entries & {m_unsafe:.2f} $\\pm$ {ci_unsafe:.2f} & {n_unsafe} \\\\",
        f"Interrupted cycles & {m_inter:.2f} $\\pm$ {ci_inter:.2f} & {n_inter} \\\\",
        f"Pause duration (s) & {m_pause:.2f} $\\pm$ {ci_pause:.2f} & {n_pause} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ]
    with open(os.path.join(MANUSCRIPT_DIR, "table_hazard_safety.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines_h))

    lines_e = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{delta_metric} delta for failure runs relative to nominal (mean $\\pm$ 95\\% CI).}}",
        "\\label{tab:energy_delta}",
        "\\begin{tabular}{lcc}",
        "\\toprule",
        "Statistic & Value & N \\\\",
        "\\midrule",
        f"Mean $\\Delta${delta_metric} (%) & {m_dE:.2f} $\\pm$ {ci_dE:.2f} & {n_dE} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ]
    with open(os.path.join(MANUSCRIPT_DIR, "table_energy_delta.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines_e))

    # --- Markdown report ---
    rep = [
        "# Experiment 1 — Summary (auto-generated)\n",
        f"Nominal makespan: **{makespan_nom:.2f} s** with **{tasks_nom:.0f}** tasks completed.",
        "",
        f"Hazard seeds detected: **{n_seeds_h}**.",
        f"- Unsafe-state entries: **{m_unsafe:.2f} ± {ci_unsafe:.2f}** (N={n_unsafe})",
        f"- Interrupted cycles: **{m_inter:.2f} ± {ci_inter:.2f}** (N={n_inter})",
        f"- Pause duration: **{m_pause:.2f} ± {ci_pause:.2f} s** (N={n_pause})",
        "",
        f"Failure retries per run: **{m_retry:.2f} ± {ci_retry:.2f}** (N={n_retry})",
        f"{delta_metric} delta vs nominal: **{m_dE:.2f}% ± {ci_dE:.2f}%** (N={n_dE})\n",
        "Data sources: results/timeline_*.csv and tasks_*.csv. Figures generated separately by paper_artifacts_exp1_fixed.py.",
    ]
    with open(os.path.join(MANUSCRIPT_DIR, "exp1_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep))

    out.update({
        "makespan_nominal_s": makespan_nom,
        "tasks_nominal": tasks_nom,
        "hazard_n_seeds": n_seeds_h,
        "unsafe_entries_mean_ci_n": (m_unsafe, ci_unsafe, n_unsafe),
        "interrupted_cycles_mean_ci_n": (m_inter, ci_inter, n_inter),
        "pause_duration_mean_ci_n": (m_pause, ci_pause, n_pause),
        "retries_mean_ci_n": (m_retry, ci_retry, n_retry),
        "delta_metric_pct_mean_ci_n": (m_dE, ci_dE, n_dE),
        "tables": {
            "hazard_safety": os.path.join(MANUSCRIPT_DIR, "table_hazard_safety.tex"),
            "energy_delta": os.path.join(MANUSCRIPT_DIR, "table_energy_delta.tex"),
        },
        "report": os.path.join(MANUSCRIPT_DIR, "exp1_report.md"),
    })
    return out


if __name__ == "__main__":
    res = analyze()
    print("Experiment 1 analysis summary:\n")
    for k, v in res.items():
        if isinstance(v, (float, np.floating)):
            print(f"- {k}: {v:.3f}")
        else:
            print(f"- {k}: {v}")