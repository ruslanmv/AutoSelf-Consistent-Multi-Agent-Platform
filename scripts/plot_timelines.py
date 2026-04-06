# scripts/plot_timelines.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build timeline figures from time-series CSVs (supports both old and new schemas):
- figs/Nominal_Mission_timeline.png
- figs/Dust_Storm_Hazard_timeline.png
- figs/Nozzle_Clog_Failure_timeline.png
"""
from __future__ import annotations
import argparse, os, sys
import pandas as pd
import matplotlib.pyplot as plt

MAP = {
    "Nominal_Mission":      "timeline_nominal.csv",
    "Dust_Storm_Hazard":    "timeline_hazard.csv",
    "Nozzle_Clog_Failure":  "timeline_failure.csv",
}

def compute_completed_tasks(df: pd.DataFrame) -> pd.Series:
    # If explicit tasks_completed exists
    for col in ["tasks_completed", "completed_tasks"]:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0)
    # Otherwise sum boolean output_state columns (heuristic)
    bool_cols = [c for c in df.columns if c.endswith("_done") or c.endswith("_printed")
                 or c.endswith("_transported") or c.endswith("_deployed") or c.endswith("_outfitted")]
    if bool_cols:
        return df[bool_cols].astype(int).sum(axis=1)
    return pd.Series([0]*len(df))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.environ.get("AUTOSELF_RESULTS_DIR","results"))
    ap.add_argument("--figs", default=os.environ.get("AUTOSELF_FIGS_DIR","figs"))
    args = ap.parse_args()
    os.makedirs(args.figs, exist_ok=True)

    for title, csv_name in MAP.items():
        src = os.path.join(args.results, csv_name)
        if not os.path.exists(src):
            print(f"[plot_timelines] Missing {src}", file=sys.stderr)
            continue
        df = pd.read_csv(src)

        # time column (new: time_s; old: time)
        if "time_s" in df.columns:
            t = pd.to_numeric(df["time_s"], errors="coerce")
        elif "time" in df.columns:
            t = pd.to_numeric(df["time"], errors="coerce")
        else:
            print(f"[plot_timelines] {src} missing time column (time_s or time).", file=sys.stderr)
            continue

        # power column (new: power_draw_w; old: site_power_level -> rename & use as proxy)
        if "power_draw_w" in df.columns:
            power = pd.to_numeric(df["power_draw_w"], errors="coerce")
            power_label = "Site Power Draw (W)"
        elif "site_power_level" in df.columns:
            power = pd.to_numeric(df["site_power_level"], errors="coerce")
            power_label = "Site Power Level (%)"
        else:
            power = None
            power_label = None

        tasks_completed = compute_completed_tasks(df)

        fig = plt.figure(figsize=(10, 5))
        ax1 = fig.add_subplot(111)
        ax1.step(t, tasks_completed, where="post", label="Tasks Completed")
        ax1.set_xlabel("Time (s)")
        ax1.set_ylabel("Cumulative Tasks Completed")
        ax1.grid(True, linestyle="--", alpha=0.6)

        if power is not None:
            ax2 = ax1.twinx()
            ax2.plot(t, power, alpha=0.7, label=power_label)
            ax2.set_ylabel(power_label)
            # Join legends
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")
        else:
            ax1.legend(loc="best")

        # Footer note (N/A data)
        fig.text(0.01, -0.02, "Units: time in seconds; power as recorded by simulator.", fontsize=8, ha="left", va="top")

        out = os.path.join(args.figs, f"{title}_timeline.png")
        fig.tight_layout()
        fig.savefig(out, bbox_inches="tight", dpi=200)
        plt.close(fig)
        print(f"[plot_timelines] wrote {out}")

if __name__ == "__main__":
    main()
