#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_artifacts_exp2_timeline.py — Single, publication-ready key figure for Experiment 2 (Resource Contention)

Produces ONE cohesive figure:
(A) Execution dynamics (timeline overlay) at a representative p.
(B) Throughput vs. conflict probability (mean ± 95% CI) for Baseline vs AutoSelf.

Input (from second_experiment.py):
  results/timeline_contention.csv
    scenario, seed, p, cycle, tasks_completed, conflict_this_cycle, conflicts_cumulative

Output:
  manuscript_results/Experiment2_KeyFigure.(png|pdf)

Usage:
  python paper_artifacts_exp2_timeline.py
  python paper_artifacts_exp2_timeline.py --p 0.7
  python paper_artifacts_exp2_timeline.py --threshold 0.75
"""

from __future__ import annotations

import argparse
import os
from typing import List, Tuple, Optional

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

# --------------------------- paths & style ---------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

mpl.rcParams.update(
    {
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.size": 10.5,
        "axes.titlesize": 11.5,
        "axes.labelsize": 10.5,
        "legend.fontsize": 9.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.linewidth": 1.0,
        "lines.linewidth": 2.1,
        "grid.linestyle": "--",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.35,
        "font.family": "serif",
    }
)

CBLUE, CORANGE = "tab:blue", "tab:orange"
SHADE_BASELINE = "#f5b7b1"   # soft red
SHADE_AUTOSELF = "#f8c471"   # warm amber

# Raise threshold: with N=2 seeds, 0.5 shades "any conflict"; 0.75 conveys consistent contention
DEFAULT_CONFLICT_SHADE_THRESHOLD = 0.75

FIGSIZE = (7.0, 6.0)  # stacked panels


# --------------------------- helpers ---------------------------
def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)


def _read_contention_csv() -> pd.DataFrame:
    path = os.path.join(RESULTS_DIR, "timeline_contention.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing required input: {path}\nRun second_experiment.py first."
        )
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    need = [
        "scenario", "seed", "p", "cycle",
        "tasks_completed", "conflict_this_cycle", "conflicts_cumulative",
    ]
    for k in need:
        if k not in df.columns:
            raise ValueError(f"timeline_contention.csv missing column '{k}'")
    # normalize types/labels
    df["scenario"] = df["scenario"].astype(str).str.strip().str.lower()
    df["seed"] = pd.to_numeric(df["seed"], errors="coerce").fillna(0).astype(int)
    df["p"] = pd.to_numeric(df["p"], errors="coerce").astype(float)
    df["cycle"] = pd.to_numeric(df["cycle"], errors="coerce").fillna(0).astype(int)
    df["tasks_completed"] = pd.to_numeric(df["tasks_completed"], errors="coerce").astype(float)
    df["conflict_this_cycle"] = pd.to_numeric(df["conflict_this_cycle"], errors="coerce").fillna(0).astype(int)
    df["conflicts_cumulative"] = pd.to_numeric(df["conflicts_cumulative"], errors="coerce").fillna(0).astype(int)
    return df


def _mean_ci95(x: np.ndarray) -> Tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return (np.nan, np.nan, 0)
    m = float(np.mean(x))
    if n == 1:
        return (m, 0.0, 1)
    s = float(np.std(x, ddof=1))
    return (m, 1.96 * (s / np.sqrt(n)), n)


def _conflict_intervals(cycles: np.ndarray, freq: np.ndarray, thr: float) -> List[Tuple[float, float]]:
    """Contiguous [start,end] cycles where conflict frequency >= thr."""
    starts, ends, active = [], [], False
    for i, (c, f) in enumerate(zip(cycles, freq)):
        flag = (f >= thr)
        if flag and not active:
            starts.append(float(c))
            active = True
        if active and not flag:
            ends.append(float(cycles[i - 1]))
            active = False
    if active:
        ends.append(float(cycles[-1]))
    return list(zip(starts, ends))


# --------------------------- aggregations ---------------------------
def _aggregate_timeline(df: pd.DataFrame, scenario: str, p: float) -> Tuple[pd.DataFrame, int]:
    sub = df[(df["scenario"] == scenario) & (df["p"] == p)].copy()
    if sub.empty:
        return pd.DataFrame(), 0
    n = sub["seed"].nunique()
    g = sub.groupby("cycle", as_index=True)
    mean = g["tasks_completed"].mean()
    ci = pd.Series(0.0, index=mean.index)
    if n > 1:
        std = g["tasks_completed"].std(ddof=1).fillna(0.0)
        ci = 1.96 * (std / np.sqrt(n))
    conflict_rate = g["conflict_this_cycle"].mean()
    return pd.DataFrame({"tasks_mean": mean, "tasks_ci": ci, "conflict_rate": conflict_rate}), n


def _throughput_from_timeline(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, p, seed), sub in df.groupby(["scenario", "p", "seed"]):
        sub = sub.sort_values("cycle")
        if sub.empty:
            continue
        final_tasks = float(sub["tasks_completed"].iloc[-1])
        final_cycles = float(sub["cycle"].iloc[-1])
        tp = final_tasks / final_cycles if final_cycles > 0 else np.nan
        rows.append({"scenario": scenario, "p": float(p), "seed": int(seed), "throughput": tp})
    out = pd.DataFrame(rows)
    return out[np.isfinite(out["throughput"])]


def _throughput_summary(tp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, p), sub in tp.groupby(["scenario", "p"]):
        m, ci, n = _mean_ci95(sub["throughput"].values)
        rows.append({"scenario": scenario, "p": float(p), "mean": m, "ci95": ci, "n": int(n)})
    return pd.DataFrame(rows)


# --------------------------- figure builder ---------------------------
def make_key_figure(
    df: pd.DataFrame,
    representative_p: Optional[float] = None,
    conflict_shade_threshold: float = DEFAULT_CONFLICT_SHADE_THRESHOLD,
) -> Tuple[str, str]:

    # pick p (default: largest available)
    ps = sorted(df["p"].unique().tolist())
    if not ps:
        raise ValueError("No p values in timeline_contention.csv")
    if representative_p is None:
        representative_p = float(max(ps))
    else:
        representative_p = float(min(ps, key=lambda v: abs(v - representative_p)))

    # panel A data
    agg_b, nb = _aggregate_timeline(df, "baseline", representative_p)
    agg_a, na = _aggregate_timeline(df, "autoself", representative_p)
    if agg_b.empty or agg_a.empty:
        raise ValueError(f"Missing data for both strategies at p={representative_p:.2f}")

    # panel B data
    tp_runs = _throughput_from_timeline(df)
    tp_summ = _throughput_summary(tp_runs)
    summ_b = tp_summ[tp_summ["scenario"] == "baseline"].sort_values("p")
    summ_a = tp_summ[tp_summ["scenario"] == "autoself"].sort_values("p")
    if summ_b.empty or summ_a.empty:
        raise ValueError("Throughput summary missing for one or both strategies.")

    # layout
    fig = plt.figure(figsize=FIGSIZE)
    gs = fig.add_gridspec(nrows=2, ncols=1, height_ratios=[1.1, 1.0], hspace=0.35)

    # ------------- Panel (A): timeline overlay -------------
    axA = fig.add_subplot(gs[0, 0])

    # shade first (keeps lines crisp on top)
    cyc_b = agg_b.index.values.astype(float)
    for s, e in _conflict_intervals(cyc_b, agg_b["conflict_rate"].values, conflict_shade_threshold):
        axA.axvspan(s, e, color=SHADE_BASELINE, alpha=0.22, zorder=0.2)
    patch_base = Patch(facecolor=SHADE_BASELINE, edgecolor="none", alpha=0.22, label="Actual conflict (baseline)")

    cyc_a = agg_a.index.values.astype(float)
    for s, e in _conflict_intervals(cyc_a, agg_a["conflict_rate"].values, conflict_shade_threshold):
        axA.axvspan(s, e, color=SHADE_AUTOSELF, alpha=0.22, zorder=0.2)
    patch_auto = Patch(facecolor=SHADE_AUTOSELF, edgecolor="none", alpha=0.22, label="Predicted/staggered conflict (AutoSelf)")

    # CI fills (below lines)
    if nb > 1:
        axA.fill_between(cyc_b,
                         (agg_b["tasks_mean"] - agg_b["tasks_ci"]).values,
                         (agg_b["tasks_mean"] + agg_b["tasks_ci"]).values,
                         step="post", color=CORANGE, alpha=0.15, label="Baseline 95% CI", zorder=0.3)
    if na > 1:
        axA.fill_between(cyc_a,
                         (agg_a["tasks_mean"] - agg_a["tasks_ci"]).values,
                         (agg_a["tasks_mean"] + agg_a["tasks_ci"]).values,
                         step="post", color=CBLUE, alpha=0.15, label="AutoSelf 95% CI", zorder=0.3)

    # step lines on top (so they’re always visible)
    axA.step(cyc_b, agg_b["tasks_mean"].values, where="post", color=CORANGE,
             label=f"Baseline tasks (mean; N={nb})", zorder=3)
    axA.step(cyc_a, agg_a["tasks_mean"].values, where="post", color=CBLUE,
             label=f"AutoSelf tasks (mean; N={na})", zorder=3)

    # legend (compact, out of data’s way)
    hA, lA = axA.get_legend_handles_labels()
    hA += [patch_base, patch_auto]
    lA += [patch_base.get_label(), patch_auto.get_label()]
    seen, H, L = set(), [], []
    for hh, ll in zip(hA, lA):
        if ll not in seen:
            H.append(hh); L.append(ll); seen.add(ll)
    axA.legend(H, L, loc="upper left", frameon=True)

    # cosmetics
    axA.set_xlabel("Cycle")
    axA.set_ylabel("Cumulative tasks (count)")
    axA.yaxis.set_major_locator(MaxNLocator(integer=True))
    axA.grid(True, which="both")
    axA.set_title(f"(A) Execution dynamics under contention at p = {representative_p:.2f}")
    axA.set_ylim(0, max(1.0, float(max(agg_b["tasks_mean"].max(), agg_a["tasks_mean"].max()) + 1.0)))

    # ------------- Panel (B): throughput vs p -------------
    axB = fig.add_subplot(gs[1, 0])

    # CI fills first, then lines (so lines remain visible)
    axB.fill_between(summ_b["p"], summ_b["mean"] - summ_b["ci95"], summ_b["mean"] + summ_b["ci95"],
                     color=CORANGE, alpha=0.18, label=None, zorder=0.3)
    axB.fill_between(summ_a["p"], summ_a["mean"] - summ_a["ci95"], summ_a["mean"] + summ_a["ci95"],
                     color=CBLUE, alpha=0.18, label=None, zorder=0.3)

    # lines on top (baseline orange guaranteed visible)
    axB.plot(summ_b["p"], summ_b["mean"], marker="o", linestyle="-", color=CORANGE, label="Baseline", zorder=3)
    axB.plot(summ_a["p"], summ_a["mean"], marker="o", linestyle="-", color=CBLUE, label="AutoSelf", zorder=3)

    # optional: jittered per-seed points behind lines for transparency
    tp_runs = _throughput_from_timeline(df)
    jitter = 0.008
    for scen, color in (("baseline", CORANGE), ("autoself", CBLUE)):
        per = tp_runs[tp_runs["scenario"] == scen]
        for p in sorted(per["p"].unique()):
            ys = per.loc[per["p"] == p, "throughput"].astype(float).values
            if len(ys) > 0:
                xj = p + (np.random.rand(len(ys)) - 0.5) * 2 * jitter
                axB.scatter(xj, ys, s=18, alpha=0.55, color=color, zorder=2, edgecolors="none")

    axB.set_xlabel("Probability task requires critical resource (p)")
    axB.set_ylabel("Throughput (tasks per cycle, ↑ better)")
    axB.set_xlim(-0.02, 1.02)
    axB.grid(True, which="both")
    axB.legend(loc="best", frameon=True)
    axB.set_title("(B) Throughput vs. conflict probability (mean ± 95% CI)")

    # save
    png = os.path.join(MANUSCRIPT_DIR, "Experiment2_KeyFigure.png")
    pdf = os.path.join(MANUSCRIPT_DIR, "Experiment2_KeyFigure.pdf")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


# --------------------------- CLI ---------------------------
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate a single key figure for Experiment 2.")
    ap.add_argument("--p", type=float, default=None,
                    help="Representative p for panel (A). Default: largest available p.")
    ap.add_argument("--threshold", type=float, default=DEFAULT_CONFLICT_SHADE_THRESHOLD,
                    help="Conflict shading threshold (fraction of seeds per cycle). Default: 0.75")
    return ap.parse_args()


if __name__ == "__main__":
    _ensure_dirs()
    args = _parse_args()
    df_all = _read_contention_csv()
    png, pdf = make_key_figure(df_all, representative_p=args.p, conflict_shade_threshold=float(args.threshold))
    print("✅ Experiment 2 key figure generated:")
    print(f"- PNG: {png}")
    print(f"- PDF: {pdf}")
