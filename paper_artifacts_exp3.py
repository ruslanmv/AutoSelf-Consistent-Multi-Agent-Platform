#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_artifacts_exp3_fixed.py

Generates publication-ready plots for Experiment 3 (Combined Hazard & Contention).

This script visualizes the performance of the AI-driven AutoSelf orchestrator
against a rule-based baseline. Figures follow consistent, paper-ready styling:
- Directional axis hints (↓ better / ↑ better)
- Consistent units (s, tasks/s, ms)
- Colorblind-safe lines with markers and distinct linestyles
- 95% confidence intervals shown as bands; n reported when stable
- Clean, descriptive titles and axis labels

Inputs expected (written by third_experiment.py):
- results/makespan.csv
- results/conflicts.csv
- results/overhead.csv
(This script will merge them for analysis)

Outputs produced:
- manuscript_results/exp3_makespan_plot.(pdf|svg)
- manuscript_results/exp3_throughput_plot.(pdf|svg)
- manuscript_results/exp3_conflicts_plot.(pdf|svg)
- manuscript_results/exp3_overhead_plot.(pdf|svg)
"""
from __future__ import annotations

import os
import math
import warnings
from typing import List, Tuple, Dict
import sys
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

# ---- Directories ----
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

# ---- Input Files from Experiment 3 ----
MAKESPAN_FILE = os.path.join(RESULTS_DIR, "makespan.csv")
CONFLICTS_FILE = os.path.join(RESULTS_DIR, "conflicts.csv")
OVERHEAD_FILE = os.path.join(RESULTS_DIR, "overhead.csv")

# ---- Matplotlib Publication-Quality Defaults ----
mpl.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300, "font.size": 13,
    "axes.labelsize": 14, "axes.titlesize": 14, "legend.fontsize": 11,
    "xtick.labelsize": 12, "ytick.labelsize": 12, "axes.linewidth": 1.1,
    "lines.linewidth": 2.0, "grid.linestyle": "--", "grid.linewidth": 0.6,
    "grid.alpha": 0.5, "figure.autolayout": True,
})

# Consistent strategy ordering and styles
STRATEGY_ORDER = ["AutoSelf (ours)", "Rule-based baseline"]
STYLE_CYCLE: Dict[str, Dict[str, str]] = {
    # Colors from matplotlib's tab cycle (generally colorblind-friendly)
    "AutoSelf (ours)": {"color": "tab:blue", "marker": "o", "linestyle": "-"},
    "Rule-based baseline": {"color": "tab:orange", "marker": "^", "linestyle": "--"},
}

# ----------------------
# Utility and Data Loading Helpers
# ----------------------

def _ensure_dirs() -> None:
    """Ensures the output directories for results and figures exist."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)


def _scenario_to_strategy(s: str) -> str:
    """Maps the internal scenario name to a clear, paper-ready label."""
    s_norm = str(s).strip().lower()
    if s_norm in {"baseline", "rule", "rule_based", "rule-based"}:
        return "Rule-based baseline"
    if s_norm in {"autoself_ai", "autoself", "ai", "ai_director"}:
        return "AutoSelf (ours)"
    # Fallback: title-case unknowns
    return str(s)


def _mean_ci95(x: np.ndarray) -> tuple[float, float, int]:
    """Calculates the mean, 95% confidence interval half-width, and count of an array."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0:
        return (float("nan"), float("nan"), 0)
    mean = float(np.mean(x))
    if n == 1:
        return (mean, 0.0, 1)
    std = float(np.std(x, ddof=1))
    ci = 1.96 * (std / np.sqrt(n))
    return (mean, ci, n)


# Robust CSV reader
def _read_csv_robust(path: str, usecols: list[str] | None = None) -> pd.DataFrame:
    """
    Reads a CSV robustly by only loading specified columns.
    1. Tries a normal read with the 'python' engine using `usecols`.
    2. If a ParserError occurs, retries with `on_bad_lines='skip'` and reports how many lines were skipped.
    3. Drops any spurious 'Unnamed:' columns created by stray delimiters.
    """
    try:
        df = pd.read_csv(
            path,
            engine="python",
            encoding="utf-8",
            encoding_errors="ignore",
            usecols=usecols,
        )
    except pd.errors.ParserError as e:
        warnings.warn(
            f"ParserError in {os.path.basename(path)}: {e}. Retrying with on_bad_lines='skip'."
        )
        df = pd.read_csv(
            path,
            engine="python",
            encoding="utf-8",
            encoding_errors="ignore",
            on_bad_lines="skip",
            skip_blank_lines=True,
            usecols=usecols,
        )
    # Clean up columns that might be created from extra delimiters
    df = df.loc[:, ~df.columns.str.startswith("Unnamed:")]
    return df


def load_and_merge_exp3_data() -> pd.DataFrame:
    """Loads and merges the separate CSVs from Experiment 3 into a single DataFrame."""
    if not all(os.path.exists(f) for f in [MAKESPAN_FILE, CONFLICTS_FILE, OVERHEAD_FILE]):
        raise FileNotFoundError(
            "One or more required input CSVs from Experiment 3 are missing in the 'results/' directory."
        )

    # Define the specific columns needed from each file to avoid parser errors.
    makespan_cols = ["scenario", "seed", "p", "makespan_s", "throughput_tpc"]
    conflicts_cols = ["scenario", "seed", "p", "conflicts"]
    overhead_cols = ["scenario", "seed", "p", "total_verif_ms", "llm_ms"]

    # Load
    df_makespan = _read_csv_robust(MAKESPAN_FILE, usecols=makespan_cols)
    df_conflicts = _read_csv_robust(CONFLICTS_FILE, usecols=conflicts_cols)
    df_overhead = _read_csv_robust(OVERHEAD_FILE, usecols=overhead_cols)

    # Merge
    df = pd.merge(df_makespan, df_conflicts, on=["scenario", "seed", "p"], suffixes=("", "_c"))
    df = pd.merge(df, df_overhead, on=["scenario", "seed", "p"], suffixes=("", "_o"))

    # Clean
    df = df.loc[:, ~df.columns.str.contains("_[co]$")]
    df["strategy"] = df["scenario"].apply(_scenario_to_strategy)

    # Ensure numeric types
    cols_to_numeric = [
        "p", "makespan_s", "throughput_tpc", "conflicts", "total_verif_ms", "llm_ms",
    ]
    for col in cols_to_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by our preferred strategy order then p
    strat_cat = pd.Categorical(df["strategy"], categories=STRATEGY_ORDER, ordered=True)
    df = df.assign(strategy=strat_cat).sort_values(by=["strategy", "p"]).reset_index(drop=True)
    return df


# ----------------------
# Formatting helpers
# ----------------------

def _format_seconds(x: float, pos: int | None = None) -> str:
    # Keep as seconds; add thousands separator if large
    try:
        return f"{x:,.0f}" if x >= 100 else f"{x:,.2f}" if x < 10 else f"{x:,.1f}"
    except Exception:
        return str(x)


def _format_ms(x: float, pos: int | None = None) -> str:
    try:
        return f"{x:,.0f}"
    except Exception:
        return str(x)


def _maybe_add_n_note(fig: plt.Figure, df_grouped: Dict[str, pd.DataFrame]) -> None:
    """Add a small footnote about CI and n if n is constant across p per strategy."""
    notes = []
    for strat, s in df_grouped.items():
        n_values = (
            s.groupby("p")["n"].first().dropna().unique().tolist()
            if "n" in s.columns else []
        )
        if len(n_values) == 1:
            notes.append(f"{strat}: n={n_values[0]} per p")
    base = "Error bars: 95% CI; points: mean" if "error" in str(fig.axes[0].artists).lower() else "Shaded bands: 95% CI; points: mean"
    if notes:
        base += "; " + ", ".join(notes)
    fig.text(0.99, 0.01, base, ha="right", va="bottom", fontsize=9, alpha=0.8)

def _maybe_add_n_note_new(fig: plt.Figure, df_grouped: Dict[str, pd.DataFrame]) -> None:
    """
    Add a small footnote about CI style and n per p (always shown as min–max).
    Detects whether the plot used shaded bands or error bars.
    """
    ax = fig.axes[0]
    has_bands = len(ax.collections) > 0  # fill_between adds PolyCollections
    base = "Shaded bands: 95% CI; points: mean" if has_bands else "Error bars: 95% CI; points: mean"

    notes = []
    for strat, s in df_grouped.items():
        if "n" in s.columns and not s["n"].dropna().empty:
            nvals = s["n"].dropna().to_numpy()
            notes.append(f"{strat}: n per p {int(np.min(nvals))}–{int(np.max(nvals))}")
    if notes:
        base += "; " + ", ".join(notes)

    fig.text(0.99, 0.01, base, ha="right", va="bottom", fontsize=9, alpha=0.8)


def _prep_xticks(ax: plt.Axes, p_values: np.ndarray) -> None:
    uniq = np.unique(np.round(p_values.astype(float), 2))
    ax.set_xticks(uniq)
    ax.set_xticklabels([f"{v:.1f}" for v in uniq])


# ----------------------
# Plotting Functions for Experiment 3
# ----------------------

def plot_makespan(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 1: Mission makespan vs. resource contention probability (↓ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["makespan_s"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        # ======================================================================
        # FIXED: Replaced unclear shaded CI bands with standard error bars.
        ax.errorbar(summary.index, summary["mean"], yerr=summary["ci"],
                    marker=style.get("marker", "o"), capsize=4,
                    linestyle=style.get("linestyle", "-"), label=strategy_name,
                    color=style.get("color"))
        # ======================================================================

    ax.set_title("Mission makespan vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel("Mission makespan (s) (↓ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: _format_seconds(x)))
    _prep_xticks(ax, df["p"].values)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_makespan_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def plot_makespan_new(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 1: Mission makespan vs. resource contention probability (↓ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}
    right_edge_labels: Dict[str, Tuple[float, float]] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["makespan_s"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        cont = ax.errorbar(summary.index, summary["mean"], yerr=summary["ci"],
                           marker=style.get("marker", "o"), capsize=4,
                           linestyle=style.get("linestyle", "-"), label=strategy_name,
                           color=style.get("color"))
        # store last point for direct label
        right_edge_labels[strategy_name] = (float(summary.index[-1]), float(summary["mean"].iloc[-1]))

    ax.set_title("Mission makespan vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel(r"Mission makespan (s) ($\downarrow$ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: _format_seconds(x)))
    _prep_xticks(ax, df["p"].values)

    # direct labels at right edge
    if right_edge_labels:
        xs = [x for x, _ in right_edge_labels.values()]
        dx = 0.02 * (max(xs) - min(xs) if len(xs) > 1 else 1.0)
        for name, (x_last, y_last) in right_edge_labels.items():
            ax.text(x_last + dx, y_last, name.replace("(ours)", "").strip(),
                    va="center", fontsize=10, clip_on=False)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_makespan_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def plot_throughput(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 2: Throughput vs. resource contention probability (↑ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["throughput_tpc"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        ax.plot(summary.index, summary["mean"], marker=style.get("marker", "o"),
                linestyle=style.get("linestyle", "-"), label=strategy_name,
                color=style.get("color"))
        ax.fill_between(summary.index, summary["mean"] - summary["ci"], summary["mean"] + summary["ci"],
                        alpha=0.2, color=style.get("color"))

    ax.set_title("Throughput vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel("Throughput (tasks/s) (↑ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    _prep_xticks(ax, df["p"].values)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_throughput_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths

def plot_throughput_new(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 2: Throughput vs. resource contention probability (↑ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}
    right_edge_labels: Dict[str, Tuple[float, float]] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["throughput_tpc"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        ax.plot(summary.index, summary["mean"], marker=style.get("marker", "o"),
                linestyle=style.get("linestyle", "-"), label=strategy_name,
                color=style.get("color"))
        ax.fill_between(summary.index, summary["mean"] - summary["ci"], summary["mean"] + summary["ci"],
                        alpha=0.2, color=style.get("color"))

        right_edge_labels[strategy_name] = (float(summary.index[-1]), float(summary["mean"].iloc[-1]))

    ax.set_title("Throughput vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel(r"Throughput (tasks/s) ($\uparrow$ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    _prep_xticks(ax, df["p"].values)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:.1f}"))

    # direct labels at right edge
    if right_edge_labels:
        xs = [x for x, _ in right_edge_labels.values()]
        dx = 0.02 * (max(xs) - min(xs) if len(xs) > 1 else 1.0)
        for name, (x_last, y_last) in right_edge_labels.items():
            ax.text(x_last + dx, y_last, name.replace("(ours)", "").strip(),
                    va="center", fontsize=10, clip_on=False)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_throughput_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def plot_conflicts(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 3: Conflicts vs. resource contention probability (↓ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["conflicts"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        ax.plot(summary.index, summary["mean"], marker=style.get("marker", "o"),
                linestyle=style.get("linestyle", "-"), label=strategy_name,
                color=style.get("color"))
        ax.fill_between(summary.index, summary["mean"] - summary["ci"], summary["mean"] + summary["ci"],
                        alpha=0.2, color=style.get("color"))

    ax.set_title("Conflicts vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel("Conflicts encountered (↓ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))  # conflicts are counts
    _prep_xticks(ax, df["p"].values)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_conflicts_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths

def plot_conflicts_new(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 3: Conflicts vs. resource contention probability (↓ better)."""
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    grouped_n_info: Dict[str, pd.DataFrame] = {}
    right_edge_labels: Dict[str, Tuple[float, float]] = {}

    for strategy_name in STRATEGY_ORDER:
        sub = df[df["strategy"] == strategy_name]
        if sub.empty:
            continue
        summary_series = sub.groupby("p")["conflicts"].apply(_mean_ci95)
        if summary_series.empty:
            continue
        summary = pd.DataFrame(summary_series.tolist(), index=summary_series.index, columns=["mean", "ci", "n"]).sort_index()
        grouped_n_info[strategy_name] = summary

        style = STYLE_CYCLE.get(strategy_name, {})
        ax.errorbar(summary.index, summary["mean"], yerr=summary["ci"],
                    marker=style.get("marker", "o"), capsize=4,
                    linestyle=style.get("linestyle", "-"), label=strategy_name,
                    color=style.get("color"))

        right_edge_labels[strategy_name] = (float(summary.index[-1]), float(summary["mean"].iloc[-1]))

    ax.set_title("Conflicts vs. resource contention probability")
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel(r"Conflicts encountered ($\downarrow$ better)")
    ax.grid(True, which="both")
    ax.legend(loc="best", frameon=True)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))  # conflicts are counts
    _prep_xticks(ax, df["p"].values)

    # direct labels at right edge
    if right_edge_labels:
        xs = [x for x, _ in right_edge_labels.values()]
        dx = 0.02 * (max(xs) - min(xs) if len(xs) > 1 else 1.0)
        for name, (x_last, y_last) in right_edge_labels.items():
            ax.text(x_last + dx, y_last, name.replace("(ours)", "").strip(),
                    va="center", fontsize=10, clip_on=False)

    _maybe_add_n_note(fig, grouped_n_info)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_conflicts_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths



def plot_overhead(df: pd.DataFrame, save_formats: List[str] = ["pdf", "svg"]) -> List[str]:
    """PLOT 4: Verification overhead by strategy (stacked). Macro-averaged across p."""
    summary_df = df.dropna(subset=["total_verif_ms", "llm_ms"]).copy()
    if summary_df.empty:
        warnings.warn("No overhead rows with both total_verif_ms and llm_ms; skipping overhead plot.")
        return []

    # ---- 1) Per-(strategy,p) means ----
    per_p = (summary_df
             .groupby(["strategy", "p"], as_index=False)
             .agg(total_mean=("total_verif_ms", "mean"),
                  llm_mean=("llm_ms", "mean")))

    # ---- 2) Macro-average across p (equal weight per p) + CI over the per-p means ----
    rows = []
    for strat in STRATEGY_ORDER:
        s = per_p[per_p["strategy"] == strat]
        if s.empty:
            continue
        tot_mean, tot_ci, n_p = _mean_ci95(s["total_mean"].to_numpy())
        llm_mean, llm_ci, _ = _mean_ci95(s["llm_mean"].to_numpy())
        rows.append({
            "strategy": strat,
            "total_ms": tot_mean,
            "total_ci": tot_ci,
            "llm_ms": llm_mean,
            "n_p": int(n_p),  # how many p values went into the macro-average
        })
    if not rows:
        return []
    summary = pd.DataFrame(rows).set_index("strategy").reindex(STRATEGY_ORDER)
    summary["rules_etc_ms"] = np.maximum(0.0, summary["total_ms"] - summary["llm_ms"])

    # ---- 3) Plot ----
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    strategies = summary.index.tolist()
    x = np.arange(len(strategies))

    # Colors (Okabe–Ito, colorblind-safe)
    col_rules = "#E69F00"  # orange
    col_llm   = "#0072B2"  # blue

    bars_rules = ax.bar(x, summary["rules_etc_ms"].values,
                        label="Rules & other", alpha=0.65, color=col_rules)
    bars_llm = ax.bar(x, summary["llm_ms"].values,
                      bottom=summary["rules_etc_ms"].values,
                      label="LLM", color=col_llm)

    # 95% CI for total height
    ax.errorbar(x, summary["total_ms"], yerr=summary["total_ci"],
                fmt="none", ecolor="black", capsize=5, elinewidth=1.3)

    # Direct value label (total ms) and LLM share %
    for i, strat in enumerate(strategies):
        total = summary.loc[strat, "total_ms"]
        llm   = summary.loc[strat, "llm_ms"]
        base  = summary.loc[strat, "rules_etc_ms"]
        if total > 0:
            ax.text(i, total + max(total*0.02, 1), f"{total:.0f} ms",
                    ha="center", va="bottom", fontsize=10)
            share = 100.0 * llm / total if total > 0 else 0.0
            ax.text(i, base + llm*0.5, f"{share:.0f}%", ha="center", va="center",
                    fontsize=9, color="white", weight="bold")

    # Handle (near-)zero baseline overhead gracefully
    if "Rule-based baseline" in strategies:
        j = strategies.index("Rule-based baseline")
        if summary.loc["Rule-based baseline", "total_ms"] <= 1e-6:
            ax.text(j, ax.get_ylim()[1]*0.05, "≈0 ms",
                    ha="center", va="center", fontsize=10,
                    bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))

    ax.set_ylabel("Average verification overhead (ms)")
    ax.set_title("Verification overhead by strategy (macro-avg across p)")
    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.legend(loc="best", frameon=True)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    ax.set_ylim(bottom=0)

    # Footnote clarifying averaging + CI
    note = "; ".join([f"{s}: n_p={int(summary.loc[s,'n_p'])}" for s in strategies if not np.isnan(summary.loc[s,"n_p"])])
    fig.text(0.99, 0.01, f"Bars: mean over p; error bars: 95% CI over per-p means; {note}",
             ha="right", va="bottom", fontsize=9, alpha=0.8)

    output_paths = []
    for fmt in save_formats:
        path = os.path.join(MANUSCRIPT_DIR, f"exp3_overhead_plot.{fmt}")
        fig.savefig(path, bbox_inches="tight")
        output_paths.append(path)
    plt.close(fig)
    return output_paths


# ----------------------
# Main Execution
# ----------------------

def main():
    """Main function to generate all artifacts for Experiment 3."""
    print("--- Generating Paper Artifacts for Experiment 3 ---")

    try:
        _ensure_dirs()
        df = load_and_merge_exp3_data()
        print("Successfully loaded and merged data from Experiment 3.")

        if df.empty:
            print("\nWarning: The merged DataFrame is empty. No plots will be generated.", file=sys.stderr)
            sys.exit(0)

        print("\n1. Generating Makespan Plot...")
        makespan_files = plot_makespan(df)
        print(f"   -> Saved to: {makespan_files}")

        print("\n2. Generating Throughput Plot...")
        throughput_files = plot_throughput(df)
        print(f"   -> Saved to: {throughput_files}")

        print("\n3. Generating Conflicts Plot...")
        conflicts_files = plot_conflicts(df)
        print(f"   -> Saved to: {conflicts_files}")

        print("\n4. Generating Overhead Plot...")
        overhead_files = plot_overhead(df)
        print(f"   -> Saved to: {overhead_files}")

        print("\n--- All artifacts generated successfully! ---")

    except FileNotFoundError as e:
        print(f"\nERROR: Could not generate artifacts. {e}", file=sys.stderr)
        print("Please ensure you have run 'third_experiment.py' first to generate the necessary data files.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()