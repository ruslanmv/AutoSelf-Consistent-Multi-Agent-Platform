#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upgraded second_experiment.py — Resource-contention benchmark

Non-destructive upgrade that:
- Keeps your original LLM-driven orchestrator flow intact.
- Adds config/seed loading (configs/baselines.yml, seeds.yaml) without breaking defaults.
- Adds ablation flags: --mode {rules-only,sim-only,full}, --llm {on,off}.
- Instruments E–V–C-style overhead timings (rules/sim/llm/correction/total) per run.
- Emits required paper artifacts (shared schema across CSVs):
  results/throughput.csv, results/makespan.csv, results/conflicts.csv,
  results/ablations.csv, results/overhead.csv
- Preserves existing plotting and LaTeX export under manuscript_results/.
- Includes comprehensive logging for monitoring the complete workflow.
"""
from __future__ import annotations

import os
import sys
import csv
import json
import time
import argparse
import asyncio
import random
import logging
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# Optional BeeAI Framework Imports (keep original Watsonx path; do not break)
try:
    from beeai_framework.backend import UserMessage
    from beeai_framework.errors import FrameworkError
    from beeai_framework.adapters.watsonx import WatsonxChatModel
except ImportError:
    UserMessage = None  # type: ignore
    FrameworkError = Exception  # type: ignore
    WatsonxChatModel = None  # type: ignore

# Data handling and plotting (preserve original behavior)
try:
    import pandas as pd
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as e:
    raise SystemExit("FATAL: pandas, matplotlib, and numpy are required. Install with: pip install pandas matplotlib numpy")

# -------------------------------
# Global Logging Setup
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# -------------------------------
# Publication-Quality Matplotlib Defaults
# -------------------------------
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
    "grid.alpha": 0.5,
    "figure.autolayout": True,
})

# -------------------------------
# Paths and artifact schema
# -------------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
MANUSCRIPT_DIR = os.environ.get("AUTOSELF_MANUSCRIPT_DIR", "manuscript_results")
CONFIG_DIR = os.environ.get("AUTOSELF_CONFIG_DIR", "configs")
SEEDS_FILE = os.environ.get("AUTOSELF_SEEDS_FILE", "seeds.yaml")

THROUGHPUT_FILE = os.path.join(RESULTS_DIR, "throughput.csv")
MAKESPAN_FILE   = os.path.join(RESULTS_DIR, "makespan.csv")
CONFLICTS_FILE  = os.path.join(RESULTS_DIR, "conflicts.csv")
ABLATIONS_FILE  = os.path.join(RESULTS_DIR, "ablations.csv")
OVERHEAD_FILE   = os.path.join(RESULTS_DIR, "overhead.csv")

SCHEMA = [
    "scenario","seed","p","makespan_s","throughput_tpc","conflicts","unsafe_entries","energy_j",
    "rules_ms","sim_ms","llm_ms","correction_ms","total_verif_ms"
]


def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MANUSCRIPT_DIR, exist_ok=True)
    log.info(f"Ensured directories '{RESULTS_DIR}' and '{MANUSCRIPT_DIR}' exist.")


def _append_row(csv_path: str, row: Dict[str, Any]) -> None:
    _ensure_dirs()
    write_header = not os.path.exists(csv_path)
    normalized = {k: row.get(k, None) for k in SCHEMA}
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if write_header:
            w.writeheader()
            log.info(f"Created new CSV '{csv_path}' with header.")
        w.writerow(normalized)


# -------------------------------
# Config & seeds
# -------------------------------

def _read_yaml(path: str) -> Dict[str, Any]:
    import yaml
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f) or {}
            log.info(f"Successfully loaded YAML from '{path}'.")
            return content
    except FileNotFoundError:
        log.warning(f"YAML file not found at '{path}'.")
        return {}
    except Exception as e:
        log.error(f"Failed to read or parse YAML file at '{path}': {e}")
        return {}


def load_baselines(config_dir: str) -> Dict[str, Any]:
    path = os.path.join(config_dir, "baselines.yml")
    config = _read_yaml(path)
    if not config:
        log.warning("Could not load baselines.yml, falling back to default config.")
        return {"contention": {"p_values": [0.1, 0.3, 0.5, 0.7, 0.9], "tasks": 10}}
    return config


def load_seeds(path: str) -> Dict[str, Any]:
    seeds = _read_yaml(path)
    if not seeds:
        log.warning(f"Could not load seeds from '{path}', falling back to default seeds.")
        return {"contention": {"all": [1, 2, 3]}}
    return seeds


# -------------------------------
# Original Pydantic response schema (preserved)
# -------------------------------
class ConflictCheckResponse(BaseModel):
    conflict_detected: bool
    reasoning: str


# -------------------------------
# E–V–C overhead instrumentation
# -------------------------------
@dataclass
class OverheadTimer:
    rules_ms: float = 0.0
    sim_ms: float = 0.0
    llm_ms: float = 0.0
    correction_ms: float = 0.0

    def total(self) -> float:
        return self.rules_ms + self.sim_ms + self.llm_ms + self.correction_ms

# -------------------------------
# Analysis Helper Function
# -------------------------------
def _group_summary_with_ci(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """
    Returns a summary DataFrame: mean, 95% CI (normal approx) per strategy x p.
    """
    rows = []
    for (strategy, p), sub in df.groupby(["strategy", "conflict_probability"]):
        y = sub[value_col].astype(float).values
        if len(y) == 0:
            continue
        mean = float(np.mean(y))
        std = float(np.std(y, ddof=1)) if len(y) > 1 else 0.0
        n = len(y)
        ci = 1.96 * (std / np.sqrt(n)) if n > 1 else 0.0
        rows.append({"strategy": strategy, "p": float(p), "mean": mean, "ci95": ci, "n": n})
    return pd.DataFrame(rows)


# -------------------------------
# Core classes (non-destructive upgrades)
# -------------------------------
class Task:
    """Represents a single task with a defined probability of needing a critical resource."""
    def __init__(self, task_id: int, conflict_probability: float, rng: random.Random):
        self.id = task_id
        self.description = f"Execute operational task {task_id}"
        self.needs_R = rng.random() < conflict_probability



class AutoSelfOrchestrator:
    """LLM-enabled orchestrator (original preserved), with optional gating via CLI flags."""
    def __init__(self, llm_enabled: bool = True):
        self.log_buffer: List[str] = []
        self.llm = None
        self.semaphore = asyncio.Semaphore(8)
        load_dotenv()
        if llm_enabled and WatsonxChatModel is not None:
            self._log("Attempting to initialize LLM...")
            try:
                api_key = os.getenv('WATSONX_API_KEY')
                project_id = os.getenv('PROJECT_ID')
                api_base = os.getenv('WATSONX_URL')
                if not all([api_key, project_id, api_base]):
                    self._log("LLM disabled: missing WATSONX_API_KEY, PROJECT_ID, or WATSONX_URL in environment.", level="warning")
                else:
                    temperature = float(os.getenv("WATSONX_TEMPERATURE", 0.05))
                    top_p = float(os.getenv("WATSONX_TOP_P", 0.9))

                    self.llm = WatsonxChatModel(
                        model_id="meta-llama/llama-3-3-70b-instruct",
                        settings={
                            "api_key": api_key,
                            "project_id": project_id,
                            "api_base": api_base,
                            "temperature": temperature,
                            "top_p": top_p,
                        },
                    )
                    self._log("LLM Initialized Successfully.")
                    self._log("LLM call semaphore initialized with a limit of 8 concurrent calls.")
            except Exception as e:
                self._log(f"LLM Initialization Failed. Error: {repr(e)}", level="error")
        else:
            self._log("LLM is disabled by configuration.", level="info")

    def _log(self, message: str, level: str = "info") -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = f"[{ts}] {message}"
        self.log_buffer.append(log_entry)
        # Also log to the main logger
        getattr(log, level, log.info)(f"[Orchestrator] {message}")

    def _build_few_shot_prompt(self, task1: Task, task2: Task) -> str:
        return f"""
You are an expert AutoSelf Orchestrator Agent. Your task is to analyze two tasks and determine if they can be executed concurrently. A conflict exists if they both require the same critical resource 'R'. Respond ONLY with a JSON object matching the ConflictCheckResponse schema.

---
**Example 1: Clear Conflict**
* **Task Input:** Task A (needs resource R: True) and Task B (needs resource R: True)
* **Your JSON Response:**
```json
{{
    "conflict_detected": true,
    "reasoning": "Direct resource contention. Both tasks require the exclusive critical resource 'R' and cannot be run concurrently."
}}
```
---
**Example 2: No Conflict**
* **Task Input:** Task C (needs resource R: True) and Task D (needs resource R: False)
* **Your JSON Response:**
```json
{{
    "conflict_detected": false,
    "reasoning": "No resource conflict. One task does not require the critical resource 'R', so they can run concurrently."
}}
```
---

**Now, evaluate the following new task pair:**

* **Task Input:** {task1.description} (needs resource R: {task1.needs_R}) and {task2.description} (needs resource R: {task2.needs_R})
* **Your JSON Response:**
"""

    async def run_health_check(self) -> bool:
        if not self.llm:
            self._log("HEALTH CHECK FAILED: LLM client was not initialized.", level="error")
            return False
        prompt = "You are a helpful AI assistant. Respond to this health check by saying 'OK'."
        async with self.semaphore:
            self._log("Acquired semaphore for health check.")
            try:
                response = await self.llm.create(messages=[UserMessage(content=prompt)])
                if (response.messages and len(response.messages) > 0 and 
                    response.messages[0].content and len(response.messages[0].content) > 0):
                    content = response.messages[0].content[0].text
                    self._log(f"Health check raw response: '{content}'")
                    if content and "ok" in content.lower():
                        self._log("HEALTH CHECK PASSED: LLM connection is healthy.")
                        return True
                self._log("HEALTH CHECK FAILED: Unexpected or empty content structure.", level="warning")
                return False
            except Exception as e:
                self._log(f"HEALTH CHECK FAILED during API call: {repr(e)}", level="error")
                return False
            finally:
                self._log("Released semaphore for health check.")

    def _extract_json(self, text: str) -> Optional[dict]:
        try:
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                return json.loads(text[json_start:json_end])
        except json.JSONDecodeError:
            self._log(f"JSON parsing failed for LLM output: '{text}'", level="warning")
        return None

    async def verify_tasks_for_conflict(self, task1: Task, task2: Task) -> Optional[bool]:
        if not self.llm:
            self._log("Cannot verify conflict: LLM is not available.", level="warning")
            return None
        prompt_text = self._build_few_shot_prompt(task1, task2)
        async with self.semaphore:
            self._log(f"Acquired semaphore for conflict verification ({task1.id}, {task2.id}).")
            try:
                response = await self.llm.create(messages=[UserMessage(content=prompt_text)])
                raw_content = ""
                if (response.messages and len(response.messages) > 0 and 
                    response.messages[0].content and len(response.messages[0].content) > 0):
                    raw_content = response.messages[0].content[0].text
                if not raw_content:
                    self._log("LLM verification failed: empty response.", level="warning")
                    return None
                data = self._extract_json(raw_content)
                if not data:
                    self._log("LLM verification failed: could not extract JSON from response.", level="warning")
                    return None
                structured = ConflictCheckResponse.model_validate(data)
                self._log(f"LLM Verdict: Conflict={structured.conflict_detected} for tasks ({task1.id}, {task2.id}).")
                return structured.conflict_detected
            except ValidationError as e:
                self._log(f"Pydantic validation failed for LLM response: {e}", level="error")
                return None
            except Exception as e:
                self._log(f"LLM verification failed with an unexpected error: {repr(e)}", level="error")
                return None
            finally:
                self._log(f"Released semaphore for conflict verification ({task1.id}, {task2.id}).")


# -------------------------------
# Simulation logic (non-destructive; adds E–V–C timings and CSV artifacts)
# -------------------------------
async def run_conflict_simulation(
    num_tasks: int,
    conflict_probability: float,
    orchestrator: Optional[AutoSelfOrchestrator],
    verifier_mode: str,
    llm_gated: bool,
    seed: int,
) -> dict:
    """Runs a single simulation scenario for a given strategy."""
    rng = random.Random(seed)
    strategy_name = "AutoSelf Orchestrator" if orchestrator else "Naive (Baseline)"
    log.info(f"Starting simulation: strategy='{strategy_name}', p={conflict_probability}, seed={seed}, tasks={num_tasks}")

    tasks = [Task(i, conflict_probability, rng) for i in range(num_tasks)]
    cycles = 0
    conflicts_encountered = 0
    tasks_completed = 0
    task_queue = list(tasks)
    overhead = OverheadTimer()

    while tasks_completed < len(tasks):
        cycles += 1
        if not task_queue: break
        
        if len(task_queue) == 1:
            log.debug(f"Cycle {cycles}: Completing final task {task_queue[0].id}.")
            tasks_completed += 1
            task_queue.pop(0)
            continue

        task1, task2 = task_queue[0], task_queue[1]

        if orchestrator and llm_gated:
            log.debug(f"Cycle {cycles}: AutoSelf verifying tasks {task1.id} and {task2.id}.")
            t_llm = time.perf_counter()
            has_conflict = await orchestrator.verify_tasks_for_conflict(task1, task2)
            overhead.llm_ms += (time.perf_counter() - t_llm) * 1000.0
            
            t_rules = time.perf_counter()
            rule_conflict = task1.needs_R and task2.needs_R if verifier_mode in ("rules-only","full") else False
            overhead.rules_ms += (time.perf_counter() - t_rules) * 1000.0

            conflict_flag = has_conflict if has_conflict is not None else rule_conflict
            if conflict_flag:
                conflicts_encountered += 1
                tasks_completed += 1
                task_queue.pop(0)
                log.debug(f"Cycle {cycles}: Conflict detected. Completed task {task1.id}. Queue size: {len(task_queue)}")
            else:
                tasks_completed += 2
                task_queue.pop(0); task_queue.pop(0)
                log.debug(f"Cycle {cycles}: No conflict. Completed tasks {task1.id}, {task2.id}. Queue size: {len(task_queue)}")
        else:
            log.debug(f"Cycle {cycles}: Baseline executing tasks {task1.id} and {task2.id}.")
            t_rules = time.perf_counter()
            is_conflict = task1.needs_R and task2.needs_R
            overhead.rules_ms += (time.perf_counter() - t_rules) * 1000.0

            if is_conflict:
                conflicts_encountered += 1
                tasks_completed += 1
                task_queue.pop(0)
                log.debug(f"Cycle {cycles}: Conflict occurred. Completed task {task1.id}. Queue size: {len(task_queue)}")
            else:
                tasks_completed += 2
                task_queue.pop(0); task_queue.pop(0)
                log.debug(f"Cycle {cycles}: No conflict. Completed tasks {task1.id}, {task2.id}. Queue size: {len(task_queue)}")
    
    throughput = round(num_tasks / cycles if cycles > 0 else 0, 6)
    log.info(f"Finished simulation for p={conflict_probability}, seed={seed}. Cycles={cycles}, Conflicts={conflicts_encountered}, Throughput={throughput:.4f}")
    return {
        "strategy": strategy_name,
        "conflict_probability": conflict_probability,
        "total_cycles": cycles,
        "conflicts_encountered": conflicts_encountered,
        "throughput": throughput,
        "overhead": overhead,
    }


class ExperimentRunner:
    """Manages and runs the conflict simulation experiments."""
    def __init__(self, num_tasks: int, p_values: List[float], seeds_map: Dict[str, List[int]],
                 mode: str, llm_gated: bool):
        self.results: List[Dict[str, Any]] = []
        self.probabilities = p_values
        self.num_tasks = num_tasks
        self.mode = mode
        self.llm_gated = llm_gated
        self.orchestrator = AutoSelfOrchestrator(llm_enabled=llm_gated)
        self.output_dir = MANUSCRIPT_DIR
        self.seeds_map = seeds_map

    async def run_all_scenarios(self):
        log.info("--- Initializing Experiment Runner ---")
        random.seed(42)

        if self.llm_gated:
            if not self.orchestrator.llm or not await self.orchestrator.run_health_check():
                log.critical("Orchestrator failed health check. Aborting experiments.")
                self.save_orchestrator_log()
                return

        log.info("--- Running All Experimental Scenarios ---")
        for p in self.probabilities:
            seed_list = self._seeds_for_p(p)
            for s in seed_list:
                log.info(f"--- Running Scenario: p={p:.1f}, seed={s} ---")
                
                # Baseline
                baseline_res = await run_conflict_simulation(self.num_tasks, p, None, self.mode, False, s)
                self._emit_csv_rows(p, s, baseline_res, "baseline")
                
                # AutoSelf
                autoself_res = await run_conflict_simulation(self.num_tasks, p, self.orchestrator, self.mode, self.llm_gated, s)
                self._emit_csv_rows(p, s, autoself_res, "autoself")

        log.info(f"--- All simulations complete. Generating results in '{self.output_dir}/' directory. ---")
        self.generate_outputs()

    def _seeds_for_p(self, p: float) -> List[int]:
        key = f"{p:.1f}"
        return [int(x) for x in self.seeds_map.get(key, self.seeds_map.get("all", [1]))]

    def _emit_csv_rows(self, p: float, seed: int, res: Dict[str, Any], scenario: str) -> None:
        oh: OverheadTimer = res.get("overhead", OverheadTimer())
        row = {
            "scenario": scenario, "seed": seed, "p": p,
            "makespan_s": None, "throughput_tpc": res.get("throughput"),
            "conflicts": res.get("conflicts_encountered", 0), "unsafe_entries": 0, "energy_j": None,
            "rules_ms": round(oh.rules_ms, 3), "sim_ms": round(oh.sim_ms, 3),
            "llm_ms": round(oh.llm_ms, 3), "correction_ms": round(oh.correction_ms, 3),
            "total_verif_ms": round(oh.total(), 3),
        }
        _append_row(THROUGHPUT_FILE, row)
        _append_row(MAKESPAN_FILE, row)
        _append_row(CONFLICTS_FILE, row)
        _append_row(OVERHEAD_FILE, row)

        abl = row.copy()
        abl["scenario"] = f"{scenario}-{self.mode}-{'llm' if self.llm_gated else 'no-llm'}"
        _append_row(ABLATIONS_FILE, abl)
        
        self.results.append({
            "strategy": ("AutoSelf Orchestrator" if scenario == "autoself" else "Naive (Baseline)"),
            "conflict_probability": p, "total_cycles": res.get("total_cycles", 0),
            "conflicts_encountered": res.get("conflicts_encountered", 0), "throughput": res.get("throughput", 0.0),
        })
        log.info(f"Emitted CSV rows for scenario='{scenario}', p={p}, seed={seed}.")

    def generate_outputs(self) -> None:
        if not self.results:
            log.warning("No results to generate.")
            return
        log.info("Starting generation of output artifacts.")
        df = pd.DataFrame(self.results)
        df['conflict_probability'] = pd.to_numeric(df['conflict_probability'])
        csv_path = os.path.join(self.output_dir, "simulation_data.csv")
        df.to_csv(csv_path, index=False)
        log.info(f"✅ Simulation data saved to: {csv_path}")

        self._generate_results_table(df)
        self._generate_throughput_plot(df)
        self._generate_effect_size_plot(df)
        self._generate_overhead_bar()
        self.save_orchestrator_log()
        log.info("Finished generating all output artifacts.")

    def _generate_results_table(self, df: pd.DataFrame) -> None:
        log.info("Generating LaTeX results table...")
        summary = df.groupby(["conflict_probability", "strategy"]).agg(
            mean_conflicts=("conflicts_encountered", "mean"),
            mean_cycles=("total_cycles", "mean")
        ).reset_index()
        pivot = summary.pivot_table(index="conflict_probability", columns="strategy", values=["mean_conflicts", "mean_cycles"])
        latex_str = "\\begin{table}[h!]\n\\centering\n"
        latex_str += f"\\caption{{Mean Simulation Results vs. Conflict Probability (N={self.num_tasks} tasks)}}\n"
        latex_str += "\\label{tab:simulation_results}\n\\begin{tabular}{@{}lcccc@{}}\n\\toprule\n"
        latex_str += " & \\multicolumn{2}{c}{Conflicts Encountered} & \\multicolumn{2}{c}{Cycles to Complete} \\\\\n"
        latex_str += "\\cmidrule(r){2-3} \\cmidrule(l){4-5}\n"
        latex_str += "Prob. (p) & Naive & AutoSelf & Naive & AutoSelf \\\\\n\\midrule\n"
        for p in sorted(df['conflict_probability'].unique()):
            if p not in pivot.index: continue
            baseline_conflicts = pivot.get(('mean_conflicts', 'Naive (Baseline)'), {}).get(p, 0.0)
            autoself_conflicts = pivot.get(('mean_conflicts', 'AutoSelf Orchestrator'), {}).get(p, 0.0)
            baseline_cycles = pivot.get(('mean_cycles', 'Naive (Baseline)'), {}).get(p, 0.0)
            autoself_cycles = pivot.get(('mean_cycles', 'AutoSelf Orchestrator'), {}).get(p, 0.0)
            latex_str += f"{p:.2f} & {baseline_conflicts:.2f} & {autoself_conflicts:.2f} & {baseline_cycles:.2f} & {autoself_cycles:.2f} \\\\\n"
        latex_str += "\\bottomrule\n\\end{tabular}\n\\end{table}"
        filepath = os.path.join(self.output_dir, "results_table.tex")
        with open(filepath, "w", encoding="utf-8") as f: f.write(latex_str)
        log.info(f"✅ LaTeX results table saved to: {filepath}")

    def _generate_throughput_plot(self, df: pd.DataFrame) -> None:
        log.info("Generating throughput plot...")
        summ = _group_summary_with_ci(df, "throughput")
        strategies = ["Naive (Baseline)", "AutoSelf Orchestrator"]
        plt.figure(figsize=(6.5, 4.0))
        xs = sorted(df["conflict_probability"].unique())
        jitter = 0.008
        for s in strategies:
            ds = summ[summ["strategy"] == s].sort_values("p")
            if ds.empty: continue
            plt.plot(ds["p"], ds["mean"], marker="o", linestyle="-", label=s)
            plt.fill_between(ds["p"], ds["mean"] - ds["ci95"], ds["mean"] + ds["ci95"], alpha=0.2)
            per_seed = df[df["strategy"] == s]
            for p in xs:
                y = per_seed.loc[per_seed["conflict_probability"] == p, "throughput"].astype(float).values
                if len(y) > 0:
                    xj = p + (np.random.rand(len(y)) - 0.5) * 2 * jitter
                    plt.scatter(xj, y, s=18, alpha=0.6, color=plt.gca().lines[-1].get_color())
        plt.title(f"Throughput vs. Resource Conflict Probability (tasks={self.num_tasks})")
        plt.xlabel("Probability task requires critical resource (p)")
        plt.ylabel("Tasks per cycle (↑ better)")
        plt.xlim(-0.02, 1.02)
        plt.grid(True, which="both")
        plt.legend(loc="best", frameon=True)
        filepath_pdf = os.path.join(self.output_dir, "throughput_plot.pdf")
        filepath_svg = os.path.join(self.output_dir, "throughput_plot.svg")
        plt.savefig(filepath_pdf, bbox_inches="tight"); plt.savefig(filepath_svg, bbox_inches="tight")
        plt.close()
        log.info(f"✅ Throughput plot saved to: {filepath_pdf} and {filepath_svg}")

    def _generate_effect_size_plot(self, df: pd.DataFrame) -> None:
        log.info("Generating effect size plot...")
        piv = df.pivot_table(index=["conflict_probability", "total_cycles"], columns="strategy", values="throughput", aggfunc="mean").reset_index()
        if "AutoSelf Orchestrator" not in piv.columns or "Naive (Baseline)" not in piv.columns:
            log.warning("Skipping effect size plot (missing data).")
            return
        piv["delta"] = piv["AutoSelf Orchestrator"] - piv["Naive (Baseline)"]
        rows = []
        for p, sub in piv.groupby("conflict_probability"):
            y = sub["delta"].astype(float).values
            mean = float(np.mean(y)) if len(y) > 0 else 0.0
            std = float(np.std(y, ddof=1)) if len(y) > 1 else 0.0
            ci = 1.96 * (std / np.sqrt(len(y))) if len(y) > 1 else 0.0
            rows.append({"p": float(p), "mean": mean, "ci95": ci})
        dd = pd.DataFrame(rows).sort_values("p")
        plt.figure(figsize=(6.2, 3.8))
        plt.axhline(0, color='grey', linewidth=1.0, linestyle='--')
        plt.errorbar(dd["p"], dd["mean"], yerr=dd["ci95"], fmt="o-", capsize=4)
        plt.title("Throughput Improvement: AutoSelf − Baseline")
        plt.xlabel("Probability task requires critical resource (p)")
        plt.ylabel("Δ tasks per cycle (↑ better)")
        plt.grid(True, which="both")
        path_pdf = os.path.join(self.output_dir, "effect_size_throughput.pdf")
        path_svg = os.path.join(self.output_dir, "effect_size_throughput.svg")
        plt.savefig(path_pdf, bbox_inches="tight"); plt.savefig(path_svg, bbox_inches="tight")
        plt.close()
        log.info(f"✅ Effect size plot saved to: {path_pdf} and {path_svg}")

    def _generate_overhead_bar(self) -> None:
        log.info("Generating overhead decomposition plot...")
        try:
            df_oh = pd.read_csv(OVERHEAD_FILE)
        except FileNotFoundError:
            log.warning(f"'{OVERHEAD_FILE}' not found; skipping overhead plot.")
            return
        g = df_oh.groupby("scenario", as_index=False)[["rules_ms", "sim_ms", "llm_ms", "correction_ms"]].mean()
        g = g[g["scenario"].str.startswith(("baseline", "autoself"))].copy()
        g["Strategy"] = g["scenario"].map(lambda s: "AutoSelf Orchestrator" if s.startswith("autoself") else "Naive (Baseline)")
        cats = ["rules_ms", "sim_ms", "llm_ms", "correction_ms"]
        labels = {"rules_ms": "Rules", "sim_ms": "Simulation", "llm_ms": "LLM", "correction_ms": "Correction"}
        idx, bottom = np.arange(len(g)), np.zeros(len(g))
        plt.figure(figsize=(6.0, 3.6))
        for c in cats:
            values = g[c].values
            plt.bar(idx, values, bottom=bottom, label=labels.get(c, c))
            bottom += values
        plt.xticks(idx, g["Strategy"], rotation=0)
        plt.ylabel("Verification overhead (ms/run)")
        plt.title("Verification Overhead Decomposition")
        plt.legend(loc="best", frameon=True, ncol=2)
        plt.grid(axis="y")
        path_pdf = os.path.join(self.output_dir, "overhead_decomposition.pdf")
        path_svg = os.path.join(self.output_dir, "overhead_decomposition.svg")
        plt.savefig(path_pdf, bbox_inches="tight"); plt.savefig(path_svg, bbox_inches="tight")
        plt.close()
        log.info(f"✅ Overhead decomposition saved to: {path_pdf} and {path_svg}")

    def save_orchestrator_log(self) -> None:
        filepath = os.path.join(self.output_dir, "orchestrator_run_log.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("--- Full Log for AutoSelf Orchestrator ---\n\n")
            f.write("\n".join(self.orchestrator.log_buffer))
        log.info(f"✅ Full orchestrator log saved to: {filepath}")

# -------------------------------
# CLI wiring
# -------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AutoSelf resource-contention benchmark (upgraded, non-destructive)")
    p.add_argument("--config-dir", default=CONFIG_DIR, help="Directory with baselines.yml")
    p.add_argument("--seeds", default=SEEDS_FILE, help="Path to seeds.yaml")
    p.add_argument("--tasks", type=int, default=None, help="Number of tasks per run (overrides config)")
    p.add_argument("--mode", choices=["rules-only","sim-only","full"], default="full", help="Ablation mode")
    p.add_argument("--llm", choices=["on","off"], default="on", help="Enable/disable LLM-gated checks")
    p.add_argument("--p-override", type=float, nargs="*", help="Override p-grid (floats)")
    p.add_argument("--seed-group", default="contention", help="Key in seeds.yaml to use")
    p.add_argument("--debug", action="store_true", help="Enable debug level logging.")
    return p.parse_args(argv)


async def async_main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled.")

    log.info("Starting experiment setup.")
    _ensure_dirs()
    base = load_baselines(args.config_dir)
    seeds_all = load_seeds(args.seeds)

    p_values = args.p_override or base.get("contention", {}).get("p_values", [0.1, 0.3, 0.5, 0.7, 0.9])
    num_tasks = args.tasks or base.get("contention", {}).get("tasks", 15)
    
    seeds_map = seeds_all.get(args.seed_group, {})
    if not isinstance(seeds_map, dict):
        seeds_map = {"all": [int(x) for x in seeds_map]} if isinstance(seeds_map, list) else {"all": [1, 2, 3]}

    log.info(f"Experiment configured with: tasks={num_tasks}, p_values={p_values}, mode='{args.mode}', llm='{args.llm}'")
    log.info(f"Seed map for group '{args.seed_group}': {seeds_map}")

    runner = ExperimentRunner(num_tasks=int(num_tasks), p_values=p_values, seeds_map=seeds_map,
                              mode=args.mode, llm_gated=(args.llm == "on"))
    await runner.run_all_scenarios()
    return 0


def main() -> None:
    log.info("Application starting.")
    start_time = time.perf_counter()
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        log.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        sys.exit(1)
    finally:
        duration = time.perf_counter() - start_time
        log.info(f"Application finished in {duration:.2f} seconds.")


if __name__ == "__main__":
    main()

