"""
Paper Artifacts – Experiment 2 (Resource‑Contention Benchmark)

Utilities to generate paper‑ready CSVs, plots, and LaTeX tables.

Inputs expected (written by second_experiment.py):
- results/throughput.csv
- results/ablations.csv
- results/overhead.csv (optional; we primarily use ablations.csv for modes/LLM flags)

Outputs produced here:
- results/throughput_by_p.csv
- results/throughput_summary.csv
- results/ablation.csv  (normalized from ablations.csv)
- manuscript_results/throughput_plot.(pdf|svg)
- manuscript_results/effect_size_throughput.(pdf|svg)
- manuscript_results/ablation_plot.(pdf|svg)
- manuscript_results/overhead_decomposition.(pdf|svg)
- manuscript_results/table_overhead.tex

Figure fixes applied (per publication QA):
- Descriptive titles (no marketing language)
- Consistent x‑axis wording: “Resource contention probability, p”
- Throughput units standardized as **tasks/cycle** with direction cue “(↑ better)”
- Effect‑size plot shows Δ vs. baseline, centered at 0 with a zero‑line
- 95% CIs everywhere (bands or error bars) + small N footnotes
- Colorblind‑safe colors, distinct markers/linestyles
- Stacked overhead bars with a clean legend and explicit units “ms per cycle”
"""
from __future__ import annotations

import os
import math
import warnings
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ---- Directories (keep in sync with second_experiment.py) ----
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")

THROUGHPUT_FILE = os.path.join(RESULTS_DIR, "throughput.csv")
ABLATIONS_FILE = os.path.join(RESULTS_DIR, "ablations.csv")
OVERHEAD_FILE = os.path.join(RESULTS_DIR, "overhead.csv")  # optional

# ---- Publication‑grade defaults ----
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

# Color/marker/linestyle map (colorblind‑friendly)
STYLE = {
    "AutoSelf (ours)": dict(color="tab:blue", marker="o", linestyle="-"),
    "Rule-based baseline": dict(color="tab:orange", marker="^", linestyle="--"),
    "Auction": dict(color="tab:green", marker="s", linestyle=":"),
}
MODE_ORDER = {"rules-only": 0, "sim-only": 1, "full": 2}
MODE_TICKS = ["rules-only", "sim-only", "full"]

# ----------------------
# Utility helpers
# ----------------------

def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    # ======================================================================
    # FIXED: The variable name had a typo ('MANUScript_DIR' instead of 'MANUSCRIPT_DIR').
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)
    # ======================================================================


def _scenario_to_strategy(s: str) -> str:
    s = str(s).strip().lower()
    if s.startswith("baseline"):
        return "Rule-based baseline"
    if s.startswith("autoself"):
        return "AutoSelf (ours)"
    if s.startswith("auction") or s.startswith("contract"):
        return "Auction"
    return s


def _mean_ci95(x: np.ndarray) -> Tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0:
        return (float("nan"), float("nan"), 0)
    m = float(np.mean(x))
    if n == 1:
        return (m, 0.0, 1)
    s = float(np.std(x, ddof=1))
    ci = 1.96 * (s / np.sqrt(n))
    return (m, ci, n)


def _save(fig: plt.Figure, stem: str) -> List[str]:
    out: List[str] = []
    pdf = os.path.join(MANUSCRIPT_DIR, f"{stem}.pdf")
    svg = os.path.join(MANUSCRIPT_DIR, f"{stem}.svg")
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    out += [pdf, svg]
    return out


# ----------------------
# 1) CSVs for the paper
# ----------------------

def write_throughput_by_p_csv() -> str:
    """Emit results/throughput_by_p.csv with per-seed rows from throughput.csv."""
    _ensure_dirs()
    if not os.path.exists(THROUGHPUT_FILE):
        raise FileNotFoundError(f"Required input not found: {THROUGHPUT_FILE}")
    df = pd.read_csv(THROUGHPUT_FILE)

    df["strategy"] = df["scenario"].map(_scenario_to_strategy)
    cols = [
        "strategy", "p", "seed", "throughput_tpc", "conflicts",
        "rules_ms", "sim_ms", "llm_ms", "correction_ms", "total_verif_ms",
    ]
    out = df[cols].copy().rename(columns={"p": "conflict_probability"})
    out_path = os.path.join(RESULTS_DIR, "throughput_by_p.csv")
    out.to_csv(out_path, index=False)
    return out_path


def write_throughput_summary_csv() -> str:
    """Emit results/throughput_summary.csv with mean and 95% CI per strategy×p."""
    _ensure_dirs()
    by_p_path = os.path.join(RESULTS_DIR, "throughput_by_p.csv")
    if not os.path.exists(by_p_path):
        by_p_path = write_throughput_by_p_csv()
    df = pd.read_csv(by_p_path)

    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "conflict_probability"]):
        m, ci, n = _mean_ci95(sub["throughput_tpc"].values)
        mc, cic, _ = _mean_ci95(sub["conflicts"].values)
        rows.append({
            "strategy": strategy,
            "conflict_probability": float(p),
            "n": int(n),
            "mean_throughput": m,
            "ci95_throughput": ci,
            "mean_conflicts": mc,
            "ci95_conflicts": cic,
        })
    out = pd.DataFrame(rows).sort_values(["strategy", "conflict_probability"]).reset_index(drop=True)
    out_path = os.path.join(RESULTS_DIR, "throughput_summary.csv")
    out.to_csv(out_path, index=False)
    return out_path


def write_ablation_csv() -> str:
    """Emit results/ablation.csv normalized from ablations.csv.
    Extracts mode (rules-only|sim-only|full) and llm flag from the encoded scenario string.
    """
    _ensure_dirs()
    if not os.path.exists(ABLATIONS_FILE):
        raise FileNotFoundError(f"Required input not found: {ABLATIONS_FILE}")
    df = pd.read_csv(ABLATIONS_FILE)

    # scenario looks like: "autoself-full-llm" or "baseline-rules-only-no-llm"
    parts = df["scenario"].fillna("").str.split("-", n=2, expand=True)
    df["base"], df["mode"], df["llm_tag"] = parts[0].fillna(""), parts[1].fillna(""), parts[2].fillna("")
    df["llm_on"] = df["llm_tag"].str.lower().eq("llm")
    df["strategy"] = df["base"].map(_scenario_to_strategy)

    keep = [
        "strategy", "mode", "llm_on", "p", "seed", "throughput_tpc", "conflicts",
        "rules_ms", "sim_ms", "llm_ms", "correction_ms", "total_verif_ms",
    ]
    out = df[keep].rename(columns={"p": "conflict_probability"}).copy()
    out_path = os.path.join(RESULTS_DIR, "ablation.csv")
    out.to_csv(out_path, index=False)
    return out_path


# ----------------------
# 2) Figures for the paper
# ----------------------

def plot_throughput_with_ci() -> List[str]:
    """Generate throughput_plot.(pdf|svg): mean lines + 95% CI bands + per‑seed points."""
    _ensure_dirs()
    by_p = os.path.join(RESULTS_DIR, "throughput_by_p.csv")
    if not os.path.exists(by_p):
        by_p = write_throughput_by_p_csv()
    df = pd.read_csv(by_p)

    # Summary for CI bands
    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "conflict_probability"]):
        m, ci, n = _mean_ci95(sub["throughput_tpc"].values)
        rows.append({"strategy": strategy, "p": p, "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pvals = sorted(df["conflict_probability"].unique())
    jitter = 0.008

    for strategy in summ["strategy"].unique():
        ss = summ[summ["strategy"] == strategy].sort_values("p")
        if ss.empty:
            continue
        st = STYLE.get(strategy, dict(marker="o", linestyle="-"))
        line, = ax.plot(ss["p"], ss["mean"], marker=st.get("marker", "o"), linestyle=st.get("linestyle", "-"),
                        label=strategy, color=st.get("color"))
        ax.fill_between(ss["p"], ss["mean"] - ss["ci"], ss["mean"] + ss["ci"], alpha=0.2,
                        color=st.get("color"))
        # jittered per‑seed points
        sub = df[df["strategy"] == strategy]
        for p in pvals:
            y = sub.loc[sub["conflict_probability"] == p, "throughput_tpc"].astype(float).values
            if y.size == 0:
                continue
            xj = p + (np.random.rand(y.size) - 0.5) * 2 * jitter
            ax.scatter(xj, y, s=18, alpha=0.55, color=line.get_color())

    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel("Throughput (tasks/cycle) (↑ better)")
    ax.set_title("Throughput vs. resource contention probability")
    ax.grid(True, which="both")
    ax.set_xticks(pvals)
    ax.set_xlim(min(pvals) - 0.05, max(pvals) + 0.05)
    ax.legend(loc="best", frameon=True)

    # footnote
    n_note = ", ".join([f"{s}: N={int(summ[summ['strategy']==s]['n'].dropna().unique().max() or 0)}"
                           for s in summ["strategy"].unique()])
    fig.text(0.99, 0.02, f"Bands: 95% CI; points: per‑seed. {n_note}", ha="right", va="bottom", fontsize=9, alpha=0.8)

    outs = _save(fig, "throughput_plot")
    plt.close(fig)
    return outs


def plot_effect_size() -> List[str]:
    """Generate effect_size_throughput.(pdf|svg): Δ throughput = AutoSelf − Baseline with 95% CI."""
    _ensure_dirs()
    by_p = os.path.join(RESULTS_DIR, "throughput_by_p.csv")
    if not os.path.exists(by_p):
        by_p = write_throughput_by_p_csv()
    df = pd.read_csv(by_p)

    piv = df.pivot_table(index=["conflict_probability", "seed"], columns="strategy",
                         values="throughput_tpc", aggfunc="mean").reset_index()
    if ("AutoSelf (ours)" not in piv.columns) or ("Rule-based baseline" not in piv.columns):
        warnings.warn("Effect-size plot skipped: missing AutoSelf or baseline columns.")
        return []

    piv["delta"] = piv["AutoSelf (ours)"] - piv["Rule-based baseline"]

    rows = []
    for p, sub in piv.groupby("conflict_probability"):
        m, ci, n = _mean_ci95(sub["delta"].values)
        rows.append({"p": p, "mean": m, "ci": ci, "n": n})
    dd = pd.DataFrame(rows).sort_values("p")

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.axhline(0, color="grey", linewidth=1.0, linestyle="--")
    ax.errorbar(dd["p"], dd["mean"], yerr=dd["ci"], fmt="o-", capsize=4)
    ax.set_xlabel("Resource contention probability, p")
    ax.set_ylabel("Δ throughput (tasks/cycle) (↑ better)")
    ax.set_title("Throughput improvement: AutoSelf − baseline")
    ax.grid(True, which="both")
    ax.set_xticks(sorted(df["conflict_probability"].unique()))

    fig.text(0.99, 0.02, "Δ = AutoSelf − Baseline; error bars: 95% CI", ha="right", va="bottom", fontsize=9, alpha=0.8)

    outs = _save(fig, "effect_size_throughput")
    plt.close(fig)
    return outs


def write_overhead_table_tex() -> str:
    """Compute median [IQR] of verification overhead per configuration from ablation runs
    and emit manuscript_results/table_overhead.tex.
    """
    _ensure_dirs()
    if not os.path.exists(ABLATIONS_FILE):
        raise FileNotFoundError(f"Required input not found: {ABLATIONS_FILE}")
    df = pd.read_csv(ABLATIONS_FILE)

    parts = df["scenario"].fillna("").str.split("-", n=2, expand=True)
    df["base"], df["mode"], df["llm_tag"] = parts[0].fillna(""), parts[1].fillna(""), parts[2].fillna("")

    # Focus on AutoSelf configs for this table
    sdf = df[df["base"].str.startswith("autoself")].copy()
    if sdf.empty:
        raise RuntimeError("No AutoSelf ablation rows found in ablations.csv")

    def _iqr(x: pd.Series) -> float:
        x = np.asarray(x, dtype=float)
        return float(np.nanpercentile(x, 75) - np.nanpercentile(x, 25))

    g = sdf.groupby(["mode", "llm_tag"]).agg(
        median_total=("total_verif_ms", "median"),
        iqr_total=("total_verif_ms", _iqr),
        median_llm=("llm_ms", "median"),
    ).reset_index()

    order = {"rules-only": 0, "sim-only": 1, "full": 2}
    g["_o"] = g["mode"].map(order).fillna(99)
    g = g.sort_values(["_o", "llm_tag"]).drop(columns=["_o"]).reset_index(drop=True)

    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Computational overhead per cycle for verification (median [IQR]).}",
        "\\label{tab:overhead}",
        "\\begin{tabular}{lcc}",
        "\\toprule",
        "Configuration & Verify time (ms/cycle) & LLM share (ms/cycle) \\\\",
        "\\midrule",
    ]
    for _, r in g.iterrows():
        label = {
            ("rules-only", "no-llm"): "Rules-only",
            ("sim-only", "no-llm"): "Sim-only",
            ("full", "llm"): "Full (rules+sim+LLM)",
            ("full", "no-llm"): "Full (no LLM)",
        }.get((r["mode"], r["llm_tag"]), f"{r['mode']} ({r['llm_tag']})")
        lines.append(
            f"{label} & {r['median_total']:.1f} [{r['iqr_total']:.1f}] & {0.0 if pd.isna(r['median_llm']) else r['median_llm']:.1f} \\\\")
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ]

    out_path = os.path.join(MANUSCRIPT_DIR, "table_overhead.tex")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def plot_overhead_decomposition_old() -> List[str]:
    """Stacked bar of mean rules/sim/LLM/correction per strategy (AutoSelf vs baseline)."""
    _ensure_dirs()
    if not os.path.exists(ABLATIONS_FILE):
        raise FileNotFoundError(f"Required input not found: {ABLATIONS_FILE}")
    df = pd.read_csv(ABLATIONS_FILE)

    parts = df["scenario"].fillna("").str.split("-", n=2, expand=True)
    df["base"], df["mode"], df["llm_tag"] = parts[0].fillna(""), parts[1].fillna(""), parts[2].fillna("")

    keep = (
        (df["base"].str.startswith("baseline")) |
        ((df["base"].str.startswith("autoself")) & (df["mode"] == "full") & (df["llm_tag"].str.lower() == "llm"))
    )
    sub = df.loc[keep, ["scenario", "rules_ms", "sim_ms", "llm_ms", "correction_ms", "total_verif_ms"]].copy()

    g = sub.groupby("scenario", as_index=False).agg({
        "rules_ms": "mean", "sim_ms": "mean", "llm_ms": "mean", "correction_ms": "mean",
        "total_verif_ms": ["mean", "std", "count"],
    })
    # Flatten columns
    g.columns = ["_".join([c for c in col if c]) for col in g.columns.to_flat_index()]
    g["Strategy"] = g["scenario"].map(_scenario_to_strategy)

    components = ["rules_ms_mean", "sim_ms_mean", "llm_ms_mean", "correction_ms_mean"]

    fig, ax = plt.subplots(figsize=(6.0, 4.0)) # Increased height slightly for label room
    idx = np.arange(len(g))
    bottom = np.zeros(len(g))

    # ======================================================================
    # FIXED: Using a log scale to make all components visible.
    # We add a small constant to avoid log(0) issues.
    MIN_VAL = 0.1
    ax.set_yscale("log")
    # ======================================================================

    labels = ["Rules/other", "Simulation", "LLM", "Correction"]
    for comp, lab in zip(components, labels):
        # Add MIN_VAL for log scale compatibility
        vals = g[comp].fillna(0).values + MIN_VAL
        ax.bar(idx, vals, bottom=bottom, label=lab)
        bottom += vals

    # Overlay CI on total height
    means = g["total_verif_ms_mean"].values
    stds = g["total_verif_ms_std"].fillna(0.0).values
    ns = g["total_verif_ms_count"].astype(float).clip(lower=1).values
    ci = 1.96 * (stds / np.sqrt(ns))
    # Note: Error bars on log scale can be tricky, but this shows the magnitude.
    ax.errorbar(idx, means + MIN_VAL, yerr=ci, fmt="none", ecolor="k", elinewidth=1, capsize=4)

    # ======================================================================
    # FIXED: Added a labeled line for the baseline if its total is near zero.
    baseline_row = g[g["Strategy"] == "Rule-based baseline"]
    if not baseline_row.empty and baseline_row["total_verif_ms_mean"].iloc[0] < MIN_VAL:
        baseline_idx = idx[g["Strategy"] == "Rule-based baseline"][0]
        ax.axhline(y=MIN_VAL, xmin=(baseline_idx-0.4)/len(idx), xmax=(baseline_idx+0.4)/len(idx),
                   color='k', linestyle='--', linewidth=1.5)
        ax.text(baseline_idx, MIN_VAL * 1.5, 'Baseline (≈0)', ha='center', va='bottom', fontsize=10)
    # ======================================================================

    ax.set_xticks(idx)
    # ======================================================================
    # FIXED: Rotated x-axis labels to prevent overlap.
    ax.set_xticklabels(g["Strategy"], rotation=30, ha="right")
    # ======================================================================
    ax.set_ylabel("Verification overhead (ms/cycle, log scale)")
    ax.set_title("Verification overhead by component")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(loc="best", frameon=True, ncol=2)
    ax.set_ylim(bottom=MIN_VAL / 2) # Adjust y-axis start for log scale

    fig.text(0.99, 0.02, "Bars = mean; whiskers = 95% CI of total", ha="right", va="bottom", fontsize=9, alpha=0.8)

    outs = _save(fig, "overhead_decomposition")
    plt.close(fig)
    return outs


def plot_overhead_decomposition() -> List[str]:
    """
    Stacked bar of mean rules/sim/LLM/correction per *strategy* (AutoSelf vs Baseline).

    - Reads results/overhead.csv; if missing, falls back to results/ablations.csv.
    - Collapses to exactly two bars by aggregating at the 'strategy' level.
    - Forces baseline LLM time to zero (baseline does not use LLM).
    - Hides components that are all-zero across both bars.
    - Uses a linear y-axis to avoid epsilons that visually invent LLM time.
    """
    # Local safe-reader to avoid NameError if _read_csv_safe isn't defined here
    def _read(path: str) -> Optional[pd.DataFrame]:
        if os.path.exists(path):
            return pd.read_csv(path, engine="python", on_bad_lines="skip")
        return None

    # Local scenario→strategy mapper (don’t rely on external helpers)
    def _scenario_to_strategy_local(s: Any) -> str:
        ss = str(s).strip().lower()
        if ss.startswith("autoself"):
            return "AutoSelf"
        if ss.startswith("baseline"):
            return "Baseline"
        return str(s)

    # 1) Prefer overhead.csv; fallback to ablations.csv
    df = _read(OVERHEAD_FILE)
    if df is None:
        ab_path = os.path.join(RESULTS_DIR, "ablations.csv")
        ab = _read(ab_path)
        if ab is None:
            raise FileNotFoundError(
                "Need results/overhead.csv or results/ablations.csv for overhead plot."
            )
        # scenario like "autoself-full-llm" or "baseline-rules-only-no-llm"
        parts = ab["scenario"].fillna("").str.split("-", n=2, expand=True)
        ab["base"], ab["mode"], ab["llm_tag"] = parts[0].fillna(""), parts[1].fillna(""), parts[2].fillna("")
        ab["strategy"] = ab["base"].map(_scenario_to_strategy_local)
        df = ab[["strategy", "rules_ms", "sim_ms", "llm_ms", "correction_ms"]].copy()
    else:
        # Ensure a strategy column exists
        if "strategy" not in df.columns:
            if "scenario" in df.columns:
                df["strategy"] = df["scenario"].map(_scenario_to_strategy_local)
            else:
                raise ValueError("overhead.csv missing 'strategy' or 'scenario' column.")

    # Keep only the two strategies we care about
    df = df[df["strategy"].isin(["AutoSelf", "Baseline"])].copy()

    # Ensure component columns exist (fill if missing)
    for c in ["rules_ms", "sim_ms", "llm_ms", "correction_ms"]:
        if c not in df.columns:
            df[c] = 0.0

    # 2) Aggregate to strategy-level means
    g = df.groupby("strategy", as_index=False)[["rules_ms", "sim_ms", "llm_ms", "correction_ms"]].mean(numeric_only=True)

    # 3) Baseline never uses LLM in Experiment 2
    g.loc[g["strategy"] == "Baseline", "llm_ms"] = 0.0

    # 4) Drop all-zero components to reduce clutter
    components = ["rules_ms", "sim_ms", "llm_ms", "correction_ms"]
    labels_map = {"rules_ms": "Rules", "sim_ms": "Simulation", "llm_ms": "LLM", "correction_ms": "Correction"}
    keep_comps = [c for c in components if float(g[c].abs().sum()) > 0.0]

    # 5) Plot (linear scale)
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    x = np.arange(len(g))  # should be 2: AutoSelf, Baseline
    bottom = np.zeros(len(g), dtype=float)

    for comp in keep_comps:
        vals = g[comp].to_numpy(dtype=float)
        ax.bar(x, vals, bottom=bottom, label=labels_map.get(comp, comp))
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(g["strategy"])
    ax.set_ylabel("Verification overhead (ms/run)")
    ax.set_title("Verification overhead by component")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    if keep_comps:
        ax.legend(loc="best", frameon=True, ncol=2)

    # 6) Save (use local fallback if _save isn't defined in this file)
    try:
        outs = _save(fig, "overhead_decomposition")
    except NameError:
        pdf = os.path.join(MANUSCRIPT_DIR, "overhead_decomposition.pdf")
        svg = os.path.join(MANUSCRIPT_DIR, "overhead_decomposition.svg")
        fig.savefig(pdf, bbox_inches="tight")
        fig.savefig(svg, bbox_inches="tight")
        outs = [pdf, svg]

    plt.close(fig)
    return outs


def plot_ablation() -> List[str]:
    """Grouped bars for AutoSelf modes (rules‑only, sim‑only, full) × {LLM, no‑LLM}.
    Baseline mean throughput shown as a dashed horizontal reference.
    """
    _ensure_dirs()
    abn = os.path.join(RESULTS_DIR, "ablation.csv")
    if not os.path.exists(abn):
        abn = write_ablation_csv()
    df = pd.read_csv(abn)

    # Focus on AutoSelf; compute baseline mean for reference
    auto = df[df["strategy"] == "AutoSelf (ours)"].copy()
    if auto.empty:
        warnings.warn("No AutoSelf rows found for ablation plot.")
        return []

    # Baseline reference (mean across p, seeds)
    base = df[df["strategy"] == "Rule-based baseline"]["throughput_tpc"].astype(float)
    base_mean = float(base.mean()) if not base.empty else None

    rows = []
    for (mode, llm_on), sub in auto.groupby(["mode", "llm_on"]):
        m, ci, n = _mean_ci95(sub["throughput_tpc"].values)
        rows.append({"mode": mode, "llm_on": bool(llm_on), "mean": m, "ci": ci, "n": n})
    summ = pd.DataFrame(rows)
    if summ.empty:
        warnings.warn("Empty summary for ablation plot.")
        return []

    # Prepare grouped bars
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    modes = [m for m in MODE_TICKS if m in summ["mode"].unique()]
    x = np.arange(len(modes))
    width = 0.36

    for i, llm_flag in enumerate([False, True]):
        sub = summ[summ["llm_on"] == llm_flag].copy()
        # ======================================================================
        # FIXED: The original logic for aligning data caused a "duplicate labels"
        # crash if the input data contained unknown modes. It would also plot data
        # incorrectly if valid modes were missing.
        # This new logic correctly aligns data for each bar group to the `modes`
        # defined for the x-axis, making it robust to missing or unknown modes.
        sub = sub.set_index("mode").reindex(modes)
        # ======================================================================
        means = sub["mean"].values
        cis = sub["ci"].fillna(0.0).values
        ax.bar(x + (i-0.5)*width, means, width=width,
               label=("No‑LLM" if not llm_flag else "LLM‑gated"))
        ax.errorbar(x + (i-0.5)*width, means, yerr=cis, fmt="none", ecolor="k", elinewidth=1, capsize=4)

    # Baseline dashed reference
    if base_mean is not None and not math.isnan(base_mean):
        ax.axhline(base_mean, color="grey", linestyle="--", linewidth=1.2, label="Baseline mean")

    ax.set_xticks(x)
    ax.set_xticklabels(modes)
    ax.set_xlabel("Verification configuration")
    ax.set_ylabel("Throughput (tasks/cycle) (↑ better)")
    ax.set_title("Ablation of hybrid verification")
    ax.grid(True, which="both", axis="y")
    ax.legend(loc="best", frameon=True)

    fig.text(0.99, 0.02, "Bars: mean ±95% CI over seeds/p", ha="right", va="bottom", fontsize=9, alpha=0.8)

    outs = _save(fig, "ablation_plot")
    plt.close(fig)
    return outs


# ----------------------
# 3) Top‑level convenience
# ----------------------

def emit_all_artifacts() -> Dict[str, Any]:
    """Generate all CSVs/plots/tables for Experiment 2 in one call."""
    _ensure_dirs()
    outputs: Dict[str, Any] = {}

    # CSVs
    outputs["throughput_by_p_csv"] = write_throughput_by_p_csv()
    outputs["throughput_summary_csv"] = write_throughput_summary_csv()
    outputs["ablation_csv"] = write_ablation_csv()

    # Figures
    outputs["throughput_plot"] = plot_throughput_with_ci()
    outputs["effect_size_plot"] = plot_effect_size()
    outputs["overhead_decomposition_plot"] = plot_overhead_decomposition()
    outputs["ablation_plot"] = plot_ablation()

    # Table
    outputs["overhead_table_tex"] = write_overhead_table_tex()

    return outputs


if __name__ == "__main__":
    out = emit_all_artifacts()
    print("Artifacts generated:\n")
    for k, v in out.items():
        print(f"- {k}: {v}")