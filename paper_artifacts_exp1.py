#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_artifacts_exp1_fixed.py — Publication-ready plots for Experiment 1 (Hazards & Failures)

This module reads the CSVs emitted by `first_experiment.py` and produces
clean, consistent, journal-ready figures and small LaTeX tables.

Inputs (expected under results/):
- timeline_nominal.csv
- timeline_hazard.csv
- timeline_failure.csv

Outputs (written under manuscript_results/ and results/):
- manuscript_results/Nominal_Mission_timeline.(pdf|png)
- manuscript_results/Dust_Storm_Hazard_timeline.(pdf|png)
- manuscript_results/Nozzle_Clog_Failure_timeline.(pdf|png)
- manuscript_results/table_hazard_safety.tex
- manuscript_results/table_energy_delta.tex
- results/hazard_safety.csv
- results/energy_delta.csv

Run:
    python paper_artifacts_exp1_fixed.py
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

# ---------------------------------------------------------------------
# Paths & style
# ---------------------------------------------------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

# Consistent, print-friendly style (single-column figure widths)
mpl.rcParams.update(
    {
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.size": 10.5,          # body text size
        "axes.titlesize": 11.5,
        "axes.labelsize": 10.5,
        "legend.fontsize": 9.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.linewidth": 1.0,
        "lines.linewidth": 2.2,
        "grid.linestyle": "--",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.35,
        "font.family": "serif",
    }
)

# Color choices (color-blind friendly)
CBLUE, CORANGE, CGREEN = "tab:blue", "tab:orange", "tab:green"
HAZARD_COLOR = "#F8C471"  # warm buff for hazard shading

# Figure size (inches) tuned for single-column width
FIGSIZE = (6.6, 3.4)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)


def _read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing required file: {path}")
    df = pd.read_csv(path)
    # Normalize names
    df.columns = [c.strip() for c in df.columns]
    return df


def _save(fig: plt.Figure, stem: str) -> Tuple[str, str]:
    png = os.path.join(MANUSCRIPT_DIR, f"{stem}.png")
    pdf = os.path.join(MANUSCRIPT_DIR, f"{stem}.pdf")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    return png, pdf


def _time_weighted_duration(time_s: Sequence[float], mask: Sequence[bool]) -> float:
    """Sum of dt where mask is True (seconds)."""
    t = np.asarray(time_s, dtype=float)
    m = np.asarray(mask, dtype=bool)
    if t.size == 0:
        return 0.0
    t_sorted_idx = np.argsort(t)
    t = t[t_sorted_idx]
    m = m[t_sorted_idx]
    lead = np.roll(t, -1)
    lead[-1] = t[-1]
    dt = np.maximum(lead - t, 0.0)
    return float(np.sum(dt[m]))


def _percent_power(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Return site power as percentage [0,100], robustly derived from available columns.
      Preferred: 'site_power_level' (already %).
      Fallback A: 'power_draw_w' that already looks like % (<= 100).
      Fallback B: normalize 'power_draw_w' to its first non-nan value => 100%.
    """
    if "site_power_level" in df.columns:
        return df["site_power_level"].astype(float)
    if "power_draw_w" in df.columns:
        s = df["power_draw_w"].astype(float)
        if s.max(skipna=True) <= 100.0:
            return s  # legacy percent track
        # Normalize to first valid sample
        first = float(s.dropna().iloc[0]) if not s.dropna().empty else np.nan
        if np.isfinite(first) and first > 0:
            return (s / first) * 100.0
    return None


def _mean_ci95(x: Sequence[float]) -> Tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return (np.nan, np.nan, 0)
    mean = float(np.mean(x))
    if n == 1:
        return (mean, 0.0, 1)
    std = float(np.std(x, ddof=1))
    ci = 1.96 * (std / np.sqrt(n))
    return (mean, ci, n)


def _hazard_boolean(df: pd.DataFrame) -> pd.Series:
    """
    Robust dust-storm boolean per row (True when the dust storm is active).
    Priority:
      1) explicit 'dust_storm' column if present,
      2) 'hazard_active' or 'dust_storm_active' columns,
      3) infer: paused>0 AND 'dust_storm_active' appears in issue_kinds.
    """
    if "dust_storm" in df.columns:
        return df["dust_storm"].astype(bool)
    for k in ("hazard_active", "dust_storm_active"):
        if k in df.columns:
            return df[k].astype(bool)
    paused = df["paused"].astype(float) > 0 if "paused" in df.columns else pd.Series(False, index=df.index)
    issues = df["issue_kinds"].astype(str) if "issue_kinds" in df.columns else pd.Series("", index=df.index)
    return paused & issues.str.contains("dust_storm_active", case=False, na=False)


def _intervals_from_mask(time_s: Sequence[float], mask: Sequence[bool]) -> List[Tuple[float, float]]:
    """
    Return contiguous [start,end] intervals where mask is True using sample-aligned boundaries.
    """
    t = np.asarray(time_s, dtype=float)
    m = np.asarray(mask, dtype=bool)
    if t.size == 0:
        return []
    order = np.argsort(t)
    t = t[order]
    m = m[order]
    # start when m goes False->True; end when True->False (use next sample time as boundary)
    starts = []
    ends = []
    prev = False
    for i in range(len(t)):
        cur = bool(m[i])
        if cur and not prev:
            starts.append(float(t[i]))
        if prev and not cur:
            ends.append(float(t[i]))
        prev = cur
    if prev:
        ends.append(float(t[-1]))
    return list(zip(starts, ends))


# ---------------------------------------------------------------------
# Plotters
# ---------------------------------------------------------------------
def _plot_panel(df: pd.DataFrame, title: str, include_hazard: bool) -> Tuple[str, str]:
    """
    Shared rendering for all three panels:
      - left axis: cumulative tasks (step, no markers)
      - right axis: site power (%), dashed
      - optional hazard shading from boolean mask
    """
    # Sort by time and aggregate if duplicated times exist
    if "time_s" in df.columns:
        df = df.sort_values("time_s")
        tcol = "time_s"
    else:
        df = df.sort_values("time")
        df = df.rename(columns={"time": "time_s"})
        tcol = "time_s"

    # Aggregate (if multiple runs are glued together)
    grouped = df.groupby(tcol, as_index=True)
    tasks_mean = grouped["tasks_completed"].mean()
    n_seeds = int(df["seed"].nunique()) if "seed" in df.columns else 1
    ci = None
    if n_seeds > 1:
        std = grouped["tasks_completed"].std(ddof=1).fillna(0.0)
        ci = 1.96 * (std / np.sqrt(n_seeds))

    power_pct = _percent_power(df)
    power_mean = None if power_pct is None else grouped[power_pct.name].mean()

    fig, ax = plt.subplots(figsize=FIGSIZE)

    # Left axis: tasks (steps, no markers)
    ax.step(tasks_mean.index.values, tasks_mean.values, where="post", color=CBLUE, label="Completed tasks")
    if ci is not None:
        ax.fill_between(tasks_mean.index.values,
                        (tasks_mean - ci).values,
                        (tasks_mean + ci).values,
                        step="post", color=CBLUE, alpha=0.18, label="95% CI")

    # Hazard shading (if requested and detectable)
    hazard_patch = None
    if include_hazard:
        haz_bool = _hazard_boolean(df)
        intervals = _intervals_from_mask(df[tcol].values, haz_bool.values)
        for s, e in intervals:
            ax.axvspan(s, e, color=HAZARD_COLOR, alpha=0.28, zorder=0.5)
            if hazard_patch is None:
                hazard_patch = Patch(facecolor=HAZARD_COLOR, edgecolor="none", alpha=0.28, label="Dust storm active")

    # Right axis: site power (%)
    handles, labels = ax.get_legend_handles_labels()
    if power_mean is not None:
        ax2 = ax.twinx()
        ax2.plot(power_mean.index.values, power_mean.values, linestyle="--", color=CGREEN, label="Site power (%)")
        ax2.set_ylabel("Site power (%)", color=CGREEN)
        h2, l2 = ax2.get_legend_handles_labels()
        handles += h2
        labels += l2

    if hazard_patch is not None:
        handles.append(hazard_patch)
        labels.append(hazard_patch.get_label())

    # Deduplicate legend entries while preserving order
    seen = set()
    H, L = [], []
    for h, l in zip(handles, labels):
        if l not in seen:
            H.append(h); L.append(l); seen.add(l)
    # Place the legend horizontally above the plot axes
   # ax.legend(
   #     H, 
   #     L, 
   #     loc='lower center',          # The point on the legend to "anchor"
   #     bbox_to_anchor=(0.5, 1.05),  # (x, y) coordinates to place the anchor point
   #     ncol=len(H),                 # Number of columns (makes it horizontal)
   #     frameon=False                # Optional: removes the box around the legend
   # )
    #ax.legend(H, L, loc='upper center', frameon=True, fontsize='small')
    # This creates a legend with a solid, non-transparent white background
    # This creates a legend that is drawn ON TOP of all plot elements.
    ax.legend(
        H, L,
        loc='upper center',       # Or your preferred location
        frameon=True,           # MUST be True to draw the box
        framealpha=1.0,         # Set background to fully opaque
        facecolor='white',      # Set background color to white
        edgecolor='black',      # Set a distinct border color
    )

    # Axes cosmetics
    ax.set_xlabel("Mission time (s)")
    ax.set_ylabel("Cumulative tasks (count)")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(True, which="both")
    ax.set_title(title)

    out = _save(fig, title.replace(" ", "_"))
    plt.close(fig)
    return out


def plot_nominal_timeline() -> Tuple[str, str]:
    df = _read_csv(os.path.join(RESULTS_DIR, "timeline_nominal.csv"))
    return _plot_panel(df, "Mission timeline: nominal", include_hazard=False)


def plot_hazard_timeline() -> Tuple[str, str]:
    df = _read_csv(os.path.join(RESULTS_DIR, "timeline_hazard.csv"))
    return _plot_panel(df, "Mission timeline: dust-storm hazard", include_hazard=True)


def plot_failure_timeline() -> Tuple[str, str]:
    df = _read_csv(os.path.join(RESULTS_DIR, "timeline_failure.csv"))
    # For consistency, also show power on the right axis (no hazard shading)
    return _plot_panel(df, "Mission timeline: nozzle-clog failure", include_hazard=False)


# ---------------------------------------------------------------------
# Tables (compact and reproducible)
# ---------------------------------------------------------------------
def write_table_hazard_safety() -> str:
    """
    Build a small LaTeX table with:
      - Unsafe-state entries (final counter if present)
      - Pause duration (s) — time-weighted using dt between samples
      - Interrupted cycles — count of time segments with paused>0 during hazard
    """
    df = _read_csv(os.path.join(RESULTS_DIR, "timeline_hazard.csv"))
    t = df["time_s"] if "time_s" in df.columns else df["time"]

    # Hazard boolean and pause boolean
    hazard = _hazard_boolean(df)
    paused = df["paused"].astype(float) > 0 if "paused" in df.columns else pd.Series(False, index=df.index)

    # Metrics per run (seed)
    if "seed" not in df.columns:
        df["seed"] = 0

    rows = []
    for seed, sub in df.groupby("seed"):
        sub = sub.sort_values(t.name)
        tt = sub[t.name].values
        hz = _hazard_boolean(sub).values
        ps = (sub["paused"].astype(float) > 0).values if "paused" in sub.columns else np.zeros_like(hz, dtype=bool)

        # time-weighted pause duration (only while hazard is active)
        mask = hz & ps
        pause_duration_s = _time_weighted_duration(tt, mask)

        # interrupted cycles = number of contiguous paused hazard intervals
        intervals = _intervals_from_mask(tt, mask)
        interrupted_cycles = len(intervals)

        unsafe_entries = int(sub.get("unsafe_entries", pd.Series([0])).max()) if "unsafe_entries" in sub.columns else 0

        rows.append(
            {
                "seed": int(seed),
                "unsafe_entries": unsafe_entries,
                "pause_duration_s": pause_duration_s,
                "interrupted_cycles": interrupted_cycles,
            }
        )

    out_csv = os.path.join(RESULTS_DIR, "hazard_safety.csv")
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    # LaTeX table (mean ± 95% CI)
    def row(label: str, values: List[float]) -> str:
        m, ci, n = _mean_ci95(values)
        return f"{label} & {m:.2f} $\\pm$ {ci:.2f} & N={n} \\\\"

    latex_lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Hazard safety metrics (mean $\\pm$ 95\\% CI) across seeds.}",
        "\\label{tab:hazard_safety}",
        "\\begin{tabular}{lcc}",
        "\\toprule",
        "Metric & Value & Notes \\\\",
        "\\midrule",
        row("Unsafe-state entries", [r["unsafe_entries"] for r in rows]),
        row("Interrupted cycles", [r["interrupted_cycles"] for r in rows]),
        row("Pause duration (s)", [r["pause_duration_s"] for r in rows]),
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ]
    out_tex = os.path.join(MANUSCRIPT_DIR, "table_hazard_safety.tex")
    with open(out_tex, "w", encoding="utf-8") as f:
        f.write("\n".join(latex_lines))
    return out_tex


def write_table_energy_delta() -> str:
    """
    Energy delta table: ΔJ = final energy_j(hazard) − final energy_j(nominal).
    Robust fallback: if energy_j missing, compute Δ%power = last(site_power_level_nominal − site_power_level_hazard).
    """
    haz = _read_csv(os.path.join(RESULTS_DIR, "timeline_hazard.csv"))
    nom = _read_csv(os.path.join(RESULTS_DIR, "timeline_nominal.csv"))

    def _final(series: pd.Series) -> Optional[float]:
        s = series.dropna()
        return float(s.iloc[-1]) if not s.empty else None

    delta_j: Optional[float] = None
    if "energy_j" in haz.columns and "energy_j" in nom.columns:
        hj = _final(haz["energy_j"])
        nj = _final(nom["energy_j"])
        if hj is not None and nj is not None:
            delta_j = hj - nj

    rows = []
    if delta_j is not None:
        rows.append({"energy_delta_j": float(delta_j), "fallback_note": ""})
    else:
        # Fallback to percentage points difference
        hp = _percent_power(haz)
        npct = _percent_power(nom)
        if hp is not None and npct is not None:
            dpp = float(_final(npct) - _final(hp))  # positive => hazard used more
            rows.append({"energy_delta_j": np.nan, "fallback_note": f"Δpower_pct={dpp:.3f} pp"})
        else:
            rows.append({"energy_delta_j": np.nan, "fallback_note": "no energy or power columns available"})

    out_csv = os.path.join(RESULTS_DIR, "energy_delta.csv")
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    # LaTeX (show ΔJ if available, otherwise describe fallback)
    if np.isfinite(rows[0]["energy_delta_j"]) if rows[0]["energy_delta_j"] is not None else False:
        val = float(rows[0]["energy_delta_j"])
        lines = [
            "\\begin{table}[t]",
            "\\centering",
            "\\caption{Energy delta between hazard and nominal runs.}",
            "\\label{tab:energy_delta}",
            "\\begin{tabular}{lc}",
            "\\toprule",
            "Metric & Value \\\\",
            "\\midrule",
            f"$\\Delta$Energy (J) & {val:.2f} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ]
    else:
        note = rows[0]["fallback_note"]
        lines = [
            "\\begin{table}[t]",
            "\\centering",
            "\\caption{Energy delta unavailable in Joules; robust fallback reported.}",
            "\\label{tab:energy_delta}",
            "\\begin{tabular}{lc}",
            "\\toprule",
            "Metric & Value \\\\",
            "\\midrule",
            f"Fallback & {note} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ]
    out_tex = os.path.join(MANUSCRIPT_DIR, "table_energy_delta.tex")
    with open(out_tex, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_tex


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------
def emit_all() -> Dict[str, Any]:
    _ensure_dirs()
    out: Dict[str, Any] = {}
    out["fig_nominal_png"], out["fig_nominal_pdf"] = plot_nominal_timeline()
    out["fig_hazard_png"], out["fig_hazard_pdf"] = plot_hazard_timeline()
    out["fig_failure_png"], out["fig_failure_pdf"] = plot_failure_timeline()
    out["table_hazard_safety"] = write_table_hazard_safety()
    out["table_energy_delta"] = write_table_energy_delta()
    return out


if __name__ == "__main__":
    outputs = emit_all()
    print("Artifacts generated:")
    for k, v in outputs.items():
        print(f"- {k}: {v}")
