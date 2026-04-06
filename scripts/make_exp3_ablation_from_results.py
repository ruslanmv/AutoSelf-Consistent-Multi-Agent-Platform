#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_exp3_ablation_from_results.py

Create the "Ablation of hybrid verification" figure from EXISTING CSVs
(no experiment re-run). Matches the original look:
- two bars (No-LLM vs LLM-gated) on a single category "full"
- dashed "Baseline mean" line (if recoverable)
- error bars = ±95% CI over seeds/p

Inputs (expected in results/):
  - makespan.csv   (needs: scenario, seed, p, throughput_tpc or makespan_s)
  - overhead.csv   (needs: scenario, seed, p, llm_ms[, total_verif_ms])

Usage (works with your bash script that passes --in):
  python scripts/make_exp3_ablation_from_results.py \
      --in results/makespan.csv --outdir manuscript_results --tasks-per-run 6 --save-png
"""

from __future__ import annotations
import os
import argparse
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# --------------------- robust CSV reading ---------------------

def _read_csv_loose(path: str, usecols=None) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        return pd.read_csv(path, usecols=usecols)
    except Exception as e:
        print(f"Warning: CSV parse error with C engine for {path}: {e}\n"
              f"         Retrying with Python engine and skipping bad lines...")
        try:
            return pd.read_csv(path, engine="python", on_bad_lines="skip", usecols=usecols)
        except TypeError:  # pandas < 1.4
            return pd.read_csv(path, engine="python", error_bad_lines=False, warn_bad_lines=True, usecols=usecols)


def _lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    return df


# --------------------- stats helpers ---------------------

def _mean_ci95(arr: np.ndarray) -> tuple[float, float, int]:
    x = np.asarray(arr, dtype=float)
    x = x[np.isfinite(x)]
    n = x.size
    if n == 0:
        return np.nan, np.nan, 0
    mean = float(x.mean())
    if n == 1:
        return mean, 0.0, 1
    std = float(x.std(ddof=1))
    ci = 1.96 * (std / np.sqrt(n))
    return mean, ci, n


# --------------------- core build ---------------------

def build_dataframe(makespan_path: str,
                    overhead_path: str,
                    tasks_per_run: float) -> pd.DataFrame:
    """
    Return a DataFrame with columns:
      seed, p, scenario, throughput, llm_ms, total_verif_ms
    """
    # Minimal columns to read (keeps parser robust)
    ms_use = [c for c in ["scenario", "seed", "p", "throughput_tpc", "makespan_s"]]
    oh_use = [c for c in ["scenario", "seed", "p", "llm_ms", "total_verif_ms"]]

    ms = _read_csv_loose(makespan_path, usecols=None)
    oh = _read_csv_loose(overhead_path, usecols=None)

    ms = _lower_cols(ms)
    oh = _lower_cols(oh)

    # keep only needed cols if present
    ms = ms[[c for c in ms_use if c in ms.columns]].copy()
    oh = oh[[c for c in oh_use if c in oh.columns]].copy()

    # sanity on required keys
    for req in ["seed", "p"]:
        if req not in ms.columns:
            raise ValueError(f"{makespan_path} missing required column '{req}'")
    if "scenario" not in ms.columns:
        ms["scenario"] = np.nan

    # compute throughput
    if "throughput_tpc" in ms.columns:
        ms["throughput"] = pd.to_numeric(ms["throughput_tpc"], errors="coerce")
    elif "makespan_s" in ms.columns:
        mk = pd.to_numeric(ms["makespan_s"], errors="coerce")
        ms["throughput"] = float(tasks_per_run) / mk
    else:
        raise ValueError("makespan.csv must contain 'throughput_tpc' or 'makespan_s'")

    # merge overhead to get llm_ms / total_verif_ms (for LLM/no-LLM detection)
    join_keys = ["scenario", "seed", "p"] if "scenario" in oh.columns else ["seed", "p"]
    oh_keys_present = [k for k in join_keys if k in oh.columns]
    if "llm_ms" not in oh.columns:
        warnings.warn("overhead.csv lacks 'llm_ms'; will assume all runs are No-LLM.")
        oh["llm_ms"] = np.nan
    if "total_verif_ms" not in oh.columns:
        oh["total_verif_ms"] = np.nan

    oh = oh.drop_duplicates(subset=oh_keys_present)

    if oh_keys_present:
        merged = ms.merge(oh, on=oh_keys_present, how="left", suffixes=("", "_o"))
    else:
        merged = ms.copy()
        merged["llm_ms"] = np.nan
        merged["total_verif_ms"] = np.nan

    for col in ["llm_ms", "total_verif_ms", "throughput"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    merged = merged.replace([np.inf, -np.inf], np.nan)
    merged = merged.dropna(subset=["throughput"])
    return merged


def derive_bins(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add:
      - bin: 'LLM-gated' if llm_ms > 0 else 'No-LLM'
      - baseline_flag: True for baseline rows (if detectible)
    """
    eps = 1e-9
    llm = pd.to_numeric(df.get("llm_ms", np.nan), errors="coerce")
    df["bin"] = np.where(llm > eps, "LLM-gated", "No-LLM")

    # Try to detect baseline rows:
    baseline_flag = np.zeros(len(df), dtype=bool)
    if "strategy" in df.columns:
        strat = df["strategy"].astype(str).str.lower()
        baseline_flag |= strat.isin(["baseline", "rule-based baseline", "rule_based", "rule-based", "rule"])
    if "total_verif_ms" in df.columns:
        tv = pd.to_numeric(df["total_verif_ms"], errors="coerce").fillna(0.0)
        baseline_flag |= ((tv <= 0.1) & (llm <= eps))

    df["baseline_flag"] = baseline_flag
    return df


# --------------------- plotting ---------------------

def plot_ablation(df: pd.DataFrame, outdir: str, save_png: bool) -> list[str]:
    """
    Make the original ablation style:
      - single x tick 'full'
      - two bars side-by-side: No-LLM (blue), LLM-gated (orange)
      - dashed baseline mean (if available)
      - error bars = ±95% CI
    """
    os.makedirs(outdir, exist_ok=True)

    # compute macro-avg throughput per bin
    rows = []
    for b in ["No-LLM", "LLM-gated"]:
        sub = df[df["bin"] == b]["throughput"].dropna().to_numpy()
        mean, ci, n = _mean_ci95(sub)
        if n > 0:
            rows.append({"bin": b, "mean": mean, "ci": ci, "n": n})
    if not rows:
        raise ValueError("No rows for ablation (No-LLM / LLM-gated).")

    g = pd.DataFrame(rows).set_index("bin").reindex(["No-LLM", "LLM-gated"])

    # baseline mean if we can detect it
    baseline = df[df["baseline_flag"]]["throughput"].dropna().to_numpy()
    baseline_mean = float(baseline.mean()) if baseline.size else np.nan

    # plotting (match original look)
    fig, ax = plt.subplots(figsize=(6.5, 3.6))

    # positions: two bars around x=0, tick labeled "full"
    x0 = 0.0
    dx = 0.18
    xpos = [x0 - dx, x0 + dx]

    colors = {"No-LLM": "#1f77b4", "LLM-gated": "#ff7f0e"}  # blue/orange like original
    labels = ["No-LLM", "LLM-gated"]

    for i, label in enumerate(labels):
        if label not in g.index or np.isnan(g.loc[label, "mean"]):
            continue
        ax.bar(
            xpos[i], g.loc[label, "mean"],
            yerr=g.loc[label, "ci"],
            capsize=3,
            color=colors[label],
            edgecolor="black",
            linewidth=0.6,
            width=0.32,
            label=label if i == 0 else None
        )

    # dashed baseline line if available
    handles = []
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    if np.isfinite(baseline_mean):
        ax.axhline(baseline_mean, color="gray", linestyle="--", linewidth=1.2, alpha=0.9)
        handles.append(Line2D([], [], color='gray', linestyle='--', label='Baseline mean'))

    handles.extend([
        Patch(facecolor=colors["No-LLM"], edgecolor="black", label="No-LLM"),
        Patch(facecolor=colors["LLM-gated"], edgecolor="black", label="LLM-gated"),
    ])
    ax.legend(handles=handles, frameon=True, loc="upper left")

    ax.set_title("Ablation of hybrid verification")
    ax.set_ylabel("Throughput (tasks/cycle) (↑ better)")
    ax.set_xlabel("Verification configuration")
    ax.set_xticks([x0])
    ax.set_xticklabels(["full"])
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.annotate("Bars: mean ±95% CI over seeds/p",
                xy=(1.0, -0.18), xycoords='axes fraction',
                ha='right', va='center', fontsize=8)

    fig.tight_layout()
    pdf = os.path.join(outdir, "exp3_ablation_plot.pdf")
    plt.savefig(pdf, bbox_inches="tight")
    if save_png:
        png = os.path.join(outdir, "exp3_ablation_plot.png")
        plt.savefig(png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    out = [pdf]
    if save_png:
        out.append(png)
    print(f"   -> Saved: {', '.join(out)}")
    return out


# --------------------- CLI ---------------------

def main():
    ap = argparse.ArgumentParser()
    # new canonical args
    ap.add_argument("--makespan", default="results/makespan.csv",
                    help="Path to results/makespan.csv")
    ap.add_argument("--overhead", default="results/overhead.csv",
                    help="Path to results/overhead.csv (used to detect LLM usage)")
    # backward-compat alias so generate_all_figures.sh (which uses --in) works unchanged
    ap.add_argument("--in", dest="infile", default=None,
                    help="Alias for --makespan (backward compatibility)")
    ap.add_argument("--outdir", default="manuscript_results",
                    help="Output directory")
    ap.add_argument("--tasks-per-run", type=float, default=6.0,
                    help="If throughput_tpc missing, throughput = tasks/makespan_s")
    ap.add_argument("--save-png", action="store_true")
    args = ap.parse_args()

    makespan_path = args.makespan if args.infile is None else args.infile
    df = build_dataframe(makespan_path, args.overhead, args.tasks_per_run)
    df = derive_bins(df)
    plot_ablation(df, args.outdir, args.save_png)


if __name__ == "__main__":
    main()
