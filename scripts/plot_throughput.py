# scripts/plot_throughput.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build figs/throughput_plot.pdf from results/throughput.csv
Labels include units and N note (number of runs per p, scenario)
"""
from __future__ import annotations
import argparse, os, sys
import pandas as pd
import matplotlib.pyplot as plt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.environ.get("AUTOSELF_RESULTS_DIR","results"))
    ap.add_argument("--figs", default=os.environ.get("AUTOSELF_FIGS_DIR","figs"))
    args = ap.parse_args()
    os.makedirs(args.figs, exist_ok=True)

    csv_path = os.path.join(args.results, "throughput.csv")
    if not os.path.exists(csv_path):
        print(f"[plot_throughput] Missing throughput.csv at {csv_path}", file=sys.stderr)
        return

    df = pd.read_csv(csv_path)
    if "p" not in df.columns or "throughput_tpc" not in df.columns or "scenario" not in df.columns:
        print("[plot_throughput] CSV missing required columns {p, throughput_tpc, scenario}", file=sys.stderr)
        return
    df["p"] = pd.to_numeric(df["p"], errors="coerce")

    # Compute N per (scenario, p)
    counts = df.groupby(["scenario","p"]).size().reset_index(name="N")

    plt.figure(figsize=(8, 5))
    for scen, sdf in df.groupby("scenario"):
        sdf = sdf.sort_values("p")
        # Plot mean throughput across seeds for readability
        m = sdf.groupby("p").throughput_tpc.mean().reset_index()
        plt.plot(m["p"], m["throughput_tpc"], marker="o", label=f"{scen}")

    plt.title("Throughput vs Resource Conflict Probability (tasks/cycle)")
    plt.xlabel("Resource Conflict Probability p ∈ [0,1]")
    plt.ylabel("Throughput (tasks per cycle)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(loc="best")

    # N note
    total_runs = int(len(df))
    uniq_ps = sorted(df["p"].dropna().unique())
    note = f"N={total_runs} runs; p-grid={uniq_ps}"
    plt.figtext(0.01, -0.02, note, fontsize=8, ha="left", va="top")

    out_pdf = os.path.join(args.figs, "throughput_plot.pdf")
    plt.tight_layout()
    plt.savefig(out_pdf, bbox_inches="tight")
    print(f"[plot_throughput] wrote {out_pdf}")

if __name__ == "__main__":
    main()
