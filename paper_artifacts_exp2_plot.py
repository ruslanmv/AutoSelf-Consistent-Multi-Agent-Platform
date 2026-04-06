#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_artifacts_exp2_timeline.py — Publication-ready plots for Experiment 2
(Resource-Contention Benchmark)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt

# ------------------------------
# Paths & style
# ------------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

TIMELINE_FILE   = os.path.join(RESULTS_DIR, "timeline_contention.csv")
THROUGHPUT_FILE = os.path.join(RESULTS_DIR, "throughput.csv")
CONFLICTS_FILE  = os.path.join(RESULTS_DIR, "conflicts.csv")
OVERHEAD_FILE   = os.path.join(RESULTS_DIR, "overhead.csv")

mpl.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.size": 13,
    "axes.labelsize": 14,
    "axes.titlesize": 14,
    "legend.fontsize": 11,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "axes.linewidth": 1.1,
    "lines.linewidth": 2.0,
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "grid.alpha": 0.4,
    "figure.autolayout": True,
    "font.family": "serif",
})

# Consistent color/style
CBLUE, CORANGE = "tab:blue", "tab:orange"
STYLE = {
    "AutoSelf": dict(color=CBLUE,  marker="o", linestyle="-"),
    "Baseline": dict(color=CORANGE, marker="^", linestyle="--"),
}

# ------------------------------
# Helpers
# ------------------------------
def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)

def _read_csv_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing required input: {path}")
    # tolerant reader (avoids ParserError on stray rows)
    return pd.read_csv(path, engine="python", on_bad_lines="skip")

def _scenario_to_strategy(s: str) -> str:
    s = str(s).strip().lower()
    if s.startswith("autoself"):
        return "AutoSelf"
    if s.startswith("baseline"):
        return "Baseline"
    return s

def _mean_ci95(x: np.ndarray) -> Tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    m = float(np.mean(x))
    if n == 1:
        return (m, 0.0, 1)
    s = float(np.std(x, ddof=1))
    ci = 1.96 * (s / np.sqrt(n))
    return (m, ci, n)

def _save(fig: plt.Figure, stem: str) -> List[str]:
    pdf = os.path.join(MANUSCRIPT_DIR, f"{stem}.pdf")
    svg = os.path.join(MANUSCRIPT_DIR, f"{stem}.svg")
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    return [pdf, svg]

def _coerce_p_numeric(df: pd.DataFrame, col: str = "p") -> pd.DataFrame:
    """Make sure p is numeric (float) and drop non-numeric rows."""
    out = df.copy()
    out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=[col])
    return out

# ------------------------------
# Metric extraction from timeline
# ------------------------------
def _metrics_from_timeline(df: pd.DataFrame) -> pd.DataFrame:
    req_cols = {"scenario", "seed", "p", "cycle", "tasks_completed"}
    if not req_cols.issubset(set(df.columns)):
        raise ValueError(f"timeline_contention.csv missing columns; needs at least: {sorted(req_cols)}")

    df = df.copy()
    df = _coerce_p_numeric(df, "p")
    df["strategy"] = df["scenario"].map(_scenario_to_strategy)
    df = df.sort_values(["strategy", "p", "seed", "cycle"])

    has_conflict_flag = "conflict_this_cycle" in df.columns
    has_pair_both = "pair_needs_R_both" in df.columns

    rows: List[Dict[str, Any]] = []
    for (strategy, p, seed), sub in df.groupby(["strategy", "p", "seed"]):
        sub = sub.sort_values("cycle")
        cycles = sub["cycle"].to_numpy(dtype=float)
        tasks  = sub["tasks_completed"].to_numpy(dtype=float)
        if cycles.size == 0:
            continue
        final_cycle = float(np.nanmax(cycles))
        throughput = float(np.nanmax(tasks) / final_cycle) if final_cycle > 0 else float("nan")

        executed = np.diff(tasks, prepend=tasks[0])
        executed = np.clip(executed, 0, 2)
        productive_share = float(np.mean(executed == 2)) if executed.size else float("nan")
        wasted_share     = float(np.mean(executed == 1)) if executed.size else float("nan")

        conflicts_pred = int(sub["conflict_this_cycle"].sum()) if has_conflict_flag else None

        run: Dict[str, Any] = {
            "strategy": strategy,
            "p": float(p),
            "seed": int(seed),
            "throughput_tpc": throughput,
            "productive_share": productive_share,
            "wasted_share": wasted_share,
            "final_cycle": final_cycle,
            "conflicts_predicted": conflicts_pred,
        }

        if has_pair_both and has_conflict_flag and strategy == "AutoSelf":
            gt   = sub["pair_needs_R_both"].astype(int).to_numpy()
            pred = sub["conflict_this_cycle"].astype(int).to_numpy()
            tp = int(np.sum((gt == 1) & (pred == 1)))
            fp = int(np.sum((gt == 0) & (pred == 1)))
            fn = int(np.sum((gt == 1) & (pred == 0)))
            prec   = float(tp / (tp + fp)) if (tp + fp) > 0 else float("nan")
            recall = float(tp / (tp + fn)) if (tp + fn) > 0 else float("nan")
            run.update({"precision": prec, "recall": recall})

        rows.append(run)

    return pd.DataFrame(rows)

def _throughput_by_p_from_timeline(df_tl: pd.DataFrame) -> pd.DataFrame:
    m = _metrics_from_timeline(df_tl)
    return m[["strategy", "p", "seed", "throughput_tpc"]].copy()

def _cycles_by_p_from_timeline(df_tl: pd.DataFrame) -> pd.DataFrame:
    m = _metrics_from_timeline(df_tl)
    return m[["strategy", "p", "seed", "final_cycle"]].copy()

def _productive_share_from_timeline(df_tl: pd.DataFrame) -> pd.DataFrame:
    m = _metrics_from_timeline(df_tl)
    out = m[["strategy", "p", "seed", "productive_share", "wasted_share"]].copy()
    out_path = os.path.join(RESULTS_DIR, "exp2_ProductiveShare_by_run.csv")
    out.to_csv(out_path, index=False)
    return out

def _precision_recall_from_timeline(df_tl: pd.DataFrame) -> Optional[pd.DataFrame]:
    m = _metrics_from_timeline(df_tl)
    if ("precision" not in m.columns) or ("recall" not in m.columns):
        return None
    return m.loc[m["strategy"] == "AutoSelf", ["p", "seed", "precision", "recall"]].copy()

# ------------------------------
# Plot 1 — Throughput vs p
# ------------------------------
def plot_throughput_vs_p(df_tl: Optional[pd.DataFrame]) -> List[str]:
    if df_tl is not None:
        df = _throughput_by_p_from_timeline(df_tl)
    else:
        df_raw = _read_csv_safe(THROUGHPUT_FILE)
        df_raw["strategy"] = df_raw["scenario"].map(_scenario_to_strategy)
        df = df_raw[["strategy", "p", "seed", "throughput_tpc"]].copy()
        df = _coerce_p_numeric(df, "p")

    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "p"]):
        m, ci, n = _mean_ci95(sub["throughput_tpc"].to_numpy(dtype=float))
        rows.append({"strategy": strategy, "p": float(p), "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pvals = sorted(df["p"].unique())
    jitter = 0.008

    for strategy in ["Baseline", "AutoSelf"]:
        ss = summ[summ["strategy"] == strategy].sort_values("p")
        if ss.empty:
            continue
        st = STYLE[strategy]
        line, = ax.plot(ss["p"], ss["mean"], marker=st["marker"], linestyle=st["linestyle"],
                        color=st["color"], label=strategy)
        ax.fill_between(ss["p"], ss["mean"] - ss["ci"], ss["mean"] + ss["ci"], alpha=0.20,
                        color=st["color"])
        sub = df[df["strategy"] == strategy]
        for p in pvals:
            y = sub.loc[sub["p"] == p, "throughput_tpc"].astype(float).values
            if y.size == 0:
                continue
            xj = p + (np.random.rand(y.size) - 0.5) * 2 * jitter
            ax.scatter(xj, y, s=18, alpha=0.55, color=line.get_color())

    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Throughput (tasks per cycle, ↑ better)")
    ax.set_title("Throughput vs. conflict probability")
    ax.grid(True, which="both")
    ax.set_xticks(pvals)
    ax.legend(loc="best", frameon=True, facecolor="white")

    outs = _save(fig, "exp2_Throughput_vs_p")
    plt.close(fig)
    return outs

# ------------------------------
# Plot 2 — Productive/Wasted share vs p
# ------------------------------
def plot_productive_share_vs_p(df_tl: pd.DataFrame) -> List[str]:
    df = _productive_share_from_timeline(df_tl)

    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "p"]):
        m, ci, n = _mean_ci95(sub["productive_share"].to_numpy(dtype=float))
        rows.append({"strategy": strategy, "p": float(p), "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pvals = sorted(df["p"].unique())
    jitter = 0.008

    for strategy in ["Baseline", "AutoSelf"]:
        ss = summ[summ["strategy"] == strategy].sort_values("p")
        if ss.empty:
            continue
        st = STYLE[strategy]
        line, = ax.plot(ss["p"], ss["mean"], marker=st["marker"], linestyle=st["linestyle"],
                        color=st["color"], label=strategy)
        ax.fill_between(ss["p"], ss["mean"] - ss["ci"], ss["mean"] + ss["ci"], alpha=0.20,
                        color=st["color"])
        sub = df[df["strategy"] == strategy]
        for p in pvals:
            y = sub.loc[sub["p"] == p, "productive_share"].astype(float).values
            if y.size == 0:
                continue
            xj = p + (np.random.rand(y.size) - 0.5) * 2 * jitter
            ax.scatter(xj, y, s=18, alpha=0.55, color=line.get_color())

    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Share of productive cycles (executed 2 tasks)")
    ax.set_title("Productive share vs. conflict probability")
    ax.grid(True, which="both")
    ax.set_xticks(pvals)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="best", frameon=True, facecolor="white")

    outs = _save(fig, "exp2_ProductiveShare_vs_p")
    plt.close(fig)
    return outs

# ------------------------------
# Plot 3 — Conflicts per run vs p  (fixed y-limits to avoid single-tick crash)
# ------------------------------
def plot_conflicts_vs_p(df_tl: Optional[pd.DataFrame]) -> List[str]:
    if os.path.exists(CONFLICTS_FILE):
        cdf = _read_csv_safe(CONFLICTS_FILE).copy()
        cdf["strategy"] = cdf["scenario"].map(_scenario_to_strategy)
        df = cdf[["strategy", "p", "seed", "conflicts"]].copy()
        df = _coerce_p_numeric(df, "p")
    elif df_tl is not None and "conflict_this_cycle" in df_tl.columns:
        tmp = df_tl.copy()
        tmp["strategy"] = tmp["scenario"].map(_scenario_to_strategy)
        tmp = _coerce_p_numeric(tmp, "p")
        g = tmp.groupby(["strategy", "p", "seed"], as_index=False)["conflict_this_cycle"].sum()
        g = g.rename(columns={"conflict_this_cycle": "conflicts"})
        df = g[["strategy", "p", "seed", "conflicts"]]
    else:
        raise FileNotFoundError("Neither conflicts.csv nor timeline_contention with 'conflict_this_cycle' present.")

    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "p"]):
        m, ci, n = _mean_ci95(sub["conflicts"].to_numpy(dtype=float))
        rows.append({"strategy": strategy, "p": float(p), "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    pvals = sorted(df["p"].unique())
    jitter = 0.008

    ymax = 0.0
    for strategy in ["Baseline", "AutoSelf"]:
        ss = summ[summ["strategy"] == strategy].sort_values("p")
        if ss.empty:
            continue
        st = STYLE[strategy]
        line, = ax.plot(ss["p"], ss["mean"], marker=st["marker"], linestyle=st["linestyle"],
                        color=st["color"], label=strategy)
        upper = (ss["mean"] + ss["ci"]).to_numpy(dtype=float)
        ymax = max(ymax, np.nanmax(upper) if upper.size else 0.0)
        lower = np.maximum(0.0, ss["mean"] - ss["ci"])
        ax.fill_between(ss["p"], lower, ss["mean"] + ss["ci"], alpha=0.20, color=st["color"])

        sub = df[df["strategy"] == strategy]
        for p in pvals:
            y = sub.loc[sub["p"] == p, "conflicts"].astype(float).values
            if y.size == 0:
                continue
            xj = p + (np.random.rand(y.size) - 0.5) * 2 * jitter
            ax.scatter(xj, y, s=18, alpha=0.6, color=line.get_color())

    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Execution conflicts per run (↓ better)")
    ax.set_title("Conflicts vs. conflict probability")
    ax.grid(True, which="both")
    ax.set_xticks(pvals)
    ax.legend(loc="best", frameon=True, facecolor="white")

    # ---- crucial fix: avoid single-tick crash when all values are 0 ----
    if not np.isfinite(ymax) or ymax <= 0.0:
        ax.set_ylim(0.0, 1.0)            # give the formatter a non-zero range
    else:
        ax.set_ylim(0.0, ymax * 1.15)    # a little headroom
    # -------------------------------------------------------------------

    outs = _save(fig, "exp2_Conflicts_vs_p")
    plt.close(fig)
    return outs

# ------------------------------
# Plot 4 — Effect size (Δ throughput)
# ------------------------------
def plot_effect_size_delta(df_tl: Optional[pd.DataFrame]) -> List[str]:
    if df_tl is not None:
        df = _throughput_by_p_from_timeline(df_tl)
    else:
        df_raw = _read_csv_safe(THROUGHPUT_FILE)
        df_raw["strategy"] = df_raw["scenario"].map(_scenario_to_strategy)
        df = df_raw[["strategy", "p", "seed", "throughput_tpc"]].copy()
        df = _coerce_p_numeric(df, "p")

    piv = df.pivot_table(index=["p", "seed"], columns="strategy",
                         values="throughput_tpc", aggfunc="mean").reset_index()
    if ("AutoSelf" not in piv.columns) or ("Baseline" not in piv.columns):
        return []

    piv["delta"] = piv["AutoSelf"] - piv["Baseline"]

    rows = []
    for p, sub in piv.groupby("p"):
        m, ci, n = _mean_ci95(sub["delta"].to_numpy(dtype=float))
        rows.append({"p": float(p), "mean": m, "ci": ci, "n": n})
    dd = pd.DataFrame(rows).sort_values("p")

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.axhline(0, color="grey", linestyle="--", linewidth=1.0)
    ax.errorbar(dd["p"], dd["mean"], yerr=dd["ci"], fmt="o-", capsize=4)
    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Δ throughput (AutoSelf − Baseline) [tasks/cycle]")
    ax.set_title("Throughput improvement vs. conflict probability")
    ax.grid(True, which="both")
    ax.set_xticks(sorted(df["p"].unique()))

    outs = _save(fig, "exp2_EffectSize_DeltaThroughput")
    plt.close(fig)
    return outs

# ------------------------------
# Plot 5 — Cycles to completion vs p
# ------------------------------
def plot_cycles_to_completion(df_tl: pd.DataFrame) -> List[str]:
    df = _cycles_by_p_from_timeline(df_tl)

    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "p"]):
        m, ci, n = _mean_ci95(sub["final_cycle"].to_numpy(dtype=float))
        rows.append({"strategy": strategy, "p": float(p), "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pvals = sorted(df["p"].unique())
    jitter = 0.008

    for strategy in ["Baseline", "AutoSelf"]:
        ss = summ[summ["strategy"] == strategy].sort_values("p")
        if ss.empty:
            continue
        st = STYLE[strategy]
        line, = ax.plot(ss["p"], ss["mean"], marker=st["marker"], linestyle=st["linestyle"],
                        color=st["color"], label=strategy)
        ax.fill_between(ss["p"], ss["mean"] - ss["ci"], ss["mean"] + ss["ci"], alpha=0.20,
                        color=st["color"])
        sub = df[df["strategy"] == strategy]
        for p in pvals:
            y = sub.loc[sub["p"] == p, "final_cycle"].astype(float).values
            if y.size == 0:
                continue
            xj = p + (np.random.rand(y.size) - 0.5) * 2 * jitter
            ax.scatter(xj, y, s=18, alpha=0.55, color=line.get_color())

    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Cycles to complete (↓ better)")
    ax.set_title("Makespan (cycles) vs. conflict probability")
    ax.grid(True, which="both")
    ax.set_xticks(pvals)
    ax.legend(loc="best", frameon=True, facecolor="white")

    outs = _save(fig, "exp2_Cycles_to_completion_vs_p")
    plt.close(fig)
    return outs

# ------------------------------
# Plot 6 — Overhead decomposition
# ------------------------------
def plot_overhead_decomposition() -> List[str]:
    df = _read_csv_safe(OVERHEAD_FILE)
    df["strategy"] = df["scenario"].map(_scenario_to_strategy)

    keep = df["strategy"].isin(["Baseline", "AutoSelf"])
    sub = df.loc[keep, ["strategy", "rules_ms", "sim_ms", "llm_ms", "correction_ms"]].copy()

    g = sub.groupby("strategy", as_index=False).mean(numeric_only=True)

    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    idx = np.arange(len(g))
    bottom = np.zeros(len(g))
    components = ["rules_ms", "sim_ms", "llm_ms", "correction_ms"]
    labels = ["Rules", "Simulation", "LLM", "Correction"]

    for comp, lab in zip(components, labels):
        vals = g[comp].fillna(0.0).to_numpy(dtype=float)
        ax.bar(idx, vals, bottom=bottom, label=lab)
        bottom += vals

    ax.set_xticks(idx)
    ax.set_xticklabels(g["strategy"])
    ax.set_ylabel("Verification overhead (ms/run)")
    ax.set_title("Verification overhead by component")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(loc="best", frameon=True, ncol=2)

    outs = _save(fig, "exp2_Overhead_decomposition")
    plt.close(fig)
    return outs

# ------------------------------
# Optional — Precision/Recall (if available)
# ------------------------------
def plot_precision_recall(df_tl: pd.DataFrame) -> List[str]:
    pr = _precision_recall_from_timeline(df_tl)
    if pr is None or pr.empty:
        return []

    rows = []
    for p, sub in pr.groupby("p"):
        pm, pci, _ = _mean_ci95(sub["precision"].to_numpy(dtype=float))
        rm, rci, _ = _mean_ci95(sub["recall"].to_numpy(dtype=float))
        rows.append({"p": float(p), "prec": pm, "prec_ci": pci, "rec": rm, "rec_ci": rci})
    dd = pd.DataFrame(rows).sort_values("p")

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.errorbar(dd["p"], dd["prec"], yerr=dd["prec_ci"], fmt="o-", capsize=4, label="Precision")
    ax.errorbar(dd["p"], dd["rec"],  yerr=dd["rec_ci"],  fmt="s--", capsize=4, label="Recall")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Probability task requires critical resource (p)")
    ax.set_ylabel("Score")
    ax.set_title("AutoSelf conflict prediction: precision/recall")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)

    outs = _save(fig, "exp2_PrecisionRecall_vs_p")
    plt.close(fig)
    return outs

# ------------------------------
# Top-level
# ------------------------------
def emit_all_artifacts() -> Dict[str, Any]:
    _ensure_dirs()
    outputs: Dict[str, Any] = {}

    # Read timeline if available
    df_tl: Optional[pd.DataFrame] = None
    if os.path.exists(TIMELINE_FILE):
        df_tl = _read_csv_safe(TIMELINE_FILE)

    # 1) Throughput vs p
    outputs["throughput_vs_p"] = plot_throughput_vs_p(df_tl)

    # 2) Productive vs wasted share (needs timeline)
    if df_tl is not None:
        outputs["productive_share_vs_p"] = plot_productive_share_vs_p(df_tl)

    # 3) Conflicts vs p  (now safe even if all zeros)
    outputs["conflicts_vs_p"] = plot_conflicts_vs_p(df_tl)

    # 4) Effect size (Δ throughput)
    outputs["effect_size_delta"] = plot_effect_size_delta(df_tl)

    # 5) Cycles to completion vs p (needs timeline)
    if df_tl is not None:
        outputs["cycles_to_completion_vs_p"] = plot_cycles_to_completion(df_tl)

    # 6) Overhead decomposition
    if os.path.exists(OVERHEAD_FILE):
        outputs["overhead_decomposition"] = plot_overhead_decomposition()

    # Optional precision/recall (only if extra column present)
    if df_tl is not None and "pair_needs_R_both" in df_tl.columns:
        outputs["precision_recall_vs_p"] = plot_precision_recall(df_tl)

    return outputs


if __name__ == "__main__":
    out = emit_all_artifacts()
    print("Artifacts generated:\n")
    for k, v in out.items():
        print(f"- {k}: {v}")
