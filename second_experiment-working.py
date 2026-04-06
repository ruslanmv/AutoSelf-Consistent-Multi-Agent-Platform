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
    import matplotlib.pyplot as plt
except ImportError as e:
    raise SystemExit("FATAL: pandas and matplotlib are required. Install with: pip install pandas matplotlib")

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


def _append_row(csv_path: str, row: Dict[str, Any]) -> None:
    _ensure_dirs()
    write_header = not os.path.exists(csv_path)
    normalized = {k: row.get(k, None) for k in SCHEMA}
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if write_header:
            w.writeheader()
        w.writerow(normalized)


# -------------------------------
# Config & seeds
# -------------------------------

def _read_yaml(path: str) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_baselines(config_dir: str) -> Dict[str, Any]:
    path = os.path.join(config_dir, "baselines.yml")
    if not os.path.exists(path):
        # Non-destructive: fall back to defaults
        return {"contention": {"p_values": [0.1, 0.3, 0.5, 0.7, 0.9]}}
    return _read_yaml(path)


def load_seeds(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        # Non-destructive default seeds
        return {"contention": {"all": [1, 2, 3]}}
    return _read_yaml(path)


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
        self.log: List[str] = []
        self.llm = None
        self.semaphore = asyncio.Semaphore(8)
        load_dotenv()
        if llm_enabled and WatsonxChatModel is not None:
            try:
                api_key = os.getenv('WATSONX_API_KEY')
                project_id = os.getenv('PROJECT_ID')
                api_base = os.getenv('WATSONX_URL')
                if not all([api_key, project_id, api_base]):
                    self._log("LLM disabled: missing credentials in environment.")
                else:
                    # Pull tunables from env/config (falls back to your current values)
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
                self._log(f"LLM Initialization Failed. Error: {repr(e)}")

    def _log(self, message: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.log.append(f"[{ts}] {message}")
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
            self._log("HEALTH CHECK FAILED: LLM client was not initialized.")
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
                self._log("HEALTH CHECK FAILED: Unexpected or empty content structure.")
                return False
            except Exception as e:
                self._log(f"HEALTH CHECK FAILED: {repr(e)}")
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
            self._log("JSON parsing failed for LLM output.")
        return None

    async def verify_tasks_for_conflict(self, task1: Task, task2: Task) -> Optional[bool]:
        if not self.llm:
            self._log("Cannot verify conflict: LLM is not available.")
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
                    self._log("LLM verification failed: empty response.")
                    return None
                data = self._extract_json(raw_content)
                if not data:
                    self._log("LLM verification failed: could not extract JSON.")
                    return None
                structured = ConflictCheckResponse.model_validate(data)
                self._log(f"LLM Verdict: Conflict={structured.conflict_detected} for tasks ({task1.id}, {task2.id}).")
                return structured.conflict_detected
            except ValidationError as e:
                self._log(f"Pydantic validation failed: {e}")
                return None
            except Exception as e:
                self._log(f"LLM verification failed: {repr(e)}")
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

    tasks = [Task(i, conflict_probability, rng) for i in range(num_tasks)]

    cycles = 0
    conflicts_encountered = 0
    tasks_completed = 0
    task_queue = list(tasks)

    # Overhead timers aggregated per run (compat with paper schema)
    overhead = OverheadTimer()

    while tasks_completed < len(tasks):
        cycles += 1
        if len(task_queue) == 0:
            break
        elif len(task_queue) == 1:
            tasks_completed += 1
            task_queue.pop(0)
            continue

        task1 = task_queue[0]
        task2 = task_queue[1]

        if orchestrator and llm_gated:
            # AutoSelf strategy: Proactively check for conflicts with the LLM.
            t_llm = time.perf_counter()
            has_conflict = await orchestrator.verify_tasks_for_conflict(task1, task2)
            overhead.llm_ms += (time.perf_counter() - t_llm) * 1000.0
            # Rule timing (rules: conflict if both need R)
            t_rules = time.perf_counter()
            rule_conflict = task1.needs_R and task2.needs_R if verifier_mode in ("rules-only","full") else False
            overhead.rules_ms += (time.perf_counter() - t_rules) * 1000.0

            conflict_flag = has_conflict if has_conflict is not None else rule_conflict
            if conflict_flag:
                conflicts_encountered += 1
                tasks_completed += 1
                task_queue.pop(0)
            else:
                tasks_completed += 2
                task_queue.pop(0)
                task_queue.pop(0)
        else:
            # Baseline (no verification or LLM disabled): execute without checking.
            t_rules = time.perf_counter()
            _ = task1.needs_R and task2.needs_R if verifier_mode in ("rules-only","full") else False
            overhead.rules_ms += (time.perf_counter() - t_rules) * 1000.0

            if task1.needs_R and task2.needs_R:
                conflicts_encountered += 1
                tasks_completed += 1
                task_queue.pop(0)
            else:
                tasks_completed += 2
                task_queue.pop(0)
                task_queue.pop(0)

    return {
        "strategy": strategy_name,
        "conflict_probability": conflict_probability,  # float for processing
        "total_cycles": cycles,
        "conflicts_encountered": conflicts_encountered,
        "throughput": round(num_tasks / cycles if cycles > 0 else 0, 6),
        "overhead": overhead,
    }


class ExperimentRunner:
    """Manages and runs the conflict simulation experiments (non-destructive)."""
    def __init__(self, num_tasks: int, p_values: List[float], seeds_map: Dict[str, List[int]],
                 mode: str, llm_gated: bool):
        self.results: List[Dict[str, Any]] = []
        self.probabilities = p_values
        self.num_tasks = num_tasks
        self.mode = mode
        self.llm_gated = llm_gated
        self.orchestrator = AutoSelfOrchestrator(llm_enabled=llm_gated)
        self.output_dir = MANUSCRIPT_DIR
        os.makedirs(self.output_dir, exist_ok=True)
        self.seeds_map = seeds_map

    async def run_all_scenarios(self):
        print("--- Initializing Experiment Runner ---")
        random.seed(42)  # reproducible task generation ordering

        # Health check only if LLM enabled
        if self.llm_gated:
            if not self.orchestrator.llm or not await self.orchestrator.run_health_check():
                print("\n🔴 Critical error: Orchestrator failed health check. Aborting experiments.")
                self.save_orchestrator_log()
                return

        print("\n--- Running All Experimental Scenarios ---")
        for p in self.probabilities:
            seed_list = self._seeds_for_p(p)
            for s in seed_list:
                print(f"Running p={p:.1f}, seed={s} ...")
                # Baseline
                baseline_res = await run_conflict_simulation(self.num_tasks, p, orchestrator=None,
                                                             verifier_mode=self.mode, llm_gated=False, seed=s)
                self._emit_csv_rows(p, s, baseline_res, scenario="baseline")
                # AutoSelf
                autoself_res = await run_conflict_simulation(self.num_tasks, p, orchestrator=self.orchestrator,
                                                             verifier_mode=self.mode, llm_gated=self.llm_gated, seed=s)
                self._emit_csv_rows(p, s, autoself_res, scenario="autoself")

        print(f"\n--- All simulations complete. Generating results in '{self.output_dir}/' directory. ---")
        self.generate_outputs()

    def _seeds_for_p(self, p: float) -> List[int]:
        key = f"{p:.1f}"
        return [int(x) for x in self.seeds_map.get(key, self.seeds_map.get("all", [1]))]

    def _emit_csv_rows(self, p: float, seed: int, res: Dict[str, Any], scenario: str) -> None:
        # Map to standardized schema
        oh: OverheadTimer = res.get("overhead", OverheadTimer())
        row = {
            "scenario": scenario,
            "seed": seed,
            "p": p,
            "makespan_s": None,                 # cycles not seconds in this benchmark
            "throughput_tpc": res.get("throughput"),
            "conflicts": res.get("conflicts_encountered", 0),
            "unsafe_entries": 0,
            "energy_j": None,
            "rules_ms": round(oh.rules_ms, 3),
            "sim_ms": round(oh.sim_ms, 3),
            "llm_ms": round(oh.llm_ms, 3),
            "correction_ms": round(oh.correction_ms, 3),
            "total_verif_ms": round(oh.total(), 3),
        }
        # Append to all required CSVs (shared schema)
        _append_row(THROUGHPUT_FILE, row)
        _append_row(MAKESPAN_FILE, row)
        _append_row(CONFLICTS_FILE, row)
        _append_row(OVERHEAD_FILE, row)  # NEW: explicit overhead.csv

        # Ablations row (same schema) captures mode/LLM in scenario name
        abl = row.copy()
        abl["scenario"] = f"{scenario}-{self.mode}-{'llm' if self.llm_gated else 'no-llm'}"
        _append_row(ABLATIONS_FILE, abl)

        # Keep original memory of results for plotting/latex below
        out = {
            "strategy": ("AutoSelf Orchestrator" if scenario == "autoself" else "Naive (Baseline)"),
            "conflict_probability": p,
            "total_cycles": res.get("total_cycles", 0),
            "conflicts_encountered": res.get("conflicts_encountered", 0),
            "throughput": res.get("throughput", 0.0),
        }
        self.results.append(out)

    def generate_outputs(self) -> None:
        if not self.results:
            print("No results to generate.")
            return
        df = pd.DataFrame(self.results)
        df['conflict_probability'] = pd.to_numeric(df['conflict_probability'])
        csv_path = os.path.join(self.output_dir, "simulation_data.csv")
        df.to_csv(csv_path, index=False)
        print(f"✅ Simulation data saved to: {csv_path}")
        self._generate_results_table(df)
        self._generate_throughput_plot(df)
        self.save_orchestrator_log()

    def _generate_results_table(self, df: pd.DataFrame) -> None:
        df_pivot = df.pivot_table(index='conflict_probability', columns='strategy',
                                  values=['conflicts_encountered', 'total_cycles'], fill_value=0)
        latex_str = "\\begin{table}[h!]\n"
        latex_str += "\\centering\n"
        latex_str += f"\\caption{{Simulation Results: Baseline vs. AutoSelf Performance for {self.num_tasks} tasks}}\n"
        latex_str += "\\label{tab:simulation_results}\n"
        latex_str += "\\resizebox{\\textwidth}{!}{\n"
        latex_str += "\\begin{tabular}{|c|c|c|c|c|}\n"
        latex_str += "\\hline\n"
        latex_str += "\\textbf{Resource Need} & \\textbf{Baseline:} & \\textbf{AutoSelf:} & \\textbf{Baseline: Cycles} & \\textbf{AutoSelf: Cycles} \\\\n"
        latex_str += "\\textbf{Probability (p)} & \\textbf{Conflicts Encountered} & \\textbf{Conflicts Encountered} & \\textbf{to finish tasks} & \\textbf{to finish tasks} \\\\n"
        latex_str += "\\hline\n"
        for p in sorted(df['conflict_probability'].unique()):
            if p not in df_pivot.index:
                continue
            baseline_conflicts = int(df_pivot.loc[p, ('conflicts_encountered', 'Naive (Baseline)')])
            autoself_conflicts = int(df_pivot.loc[p, ('conflicts_encountered', 'AutoSelf Orchestrator')])
            baseline_cycles = int(df_pivot.loc[p, ('total_cycles', 'Naive (Baseline)')])
            autoself_cycles = int(df_pivot.loc[p, ('total_cycles', 'AutoSelf Orchestrator')])
            latex_str += f"{p:.2f} & {baseline_conflicts} & {autoself_conflicts} & {baseline_cycles} & {autoself_cycles} \\\n"
        latex_str += "\\hline\n"
        latex_str += "\\end{tabular}\n"
        latex_str += "}\n"
        latex_str += "\\end{table}"
        filepath = os.path.join(self.output_dir, "results_table.tex")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(latex_str)
        print(f"✅ LaTeX results table saved to: {filepath}")

    def _generate_throughput_plot(self, df: pd.DataFrame) -> None:
        plt.figure(figsize=(10, 6), dpi=300)
        df_autoself = df[df['strategy'] == 'AutoSelf Orchestrator']
        df_baseline = df[df['strategy'] == 'Naive (Baseline)']
        plt.plot(df_baseline['conflict_probability'], df_baseline['throughput'], marker='X', linestyle='--', label='Naive (Baseline)')
        plt.plot(df_autoself['conflict_probability'], df_autoself['throughput'], marker='o', linestyle='-', label='AutoSelf Orchestrator')
        plt.title('System Throughput vs. Resource Conflict Probability')
        plt.xlabel('Probability Task Requires Critical Resource (p)')
        plt.ylabel('Average Tasks Completed per Cycle (Throughput)')
        plt.xlim(-0.05, 1.05)
        plt.ylim(bottom=0)
        plt.legend(loc='best')
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        filepath = os.path.join(self.output_dir, "throughput_plot.pdf")
        plt.savefig(filepath, bbox_inches='tight')
        plt.close()
        print(f"✅ Throughput plot saved to: {filepath}")

    def save_orchestrator_log(self) -> None:
        filepath = os.path.join(self.output_dir, "orchestrator_run_log.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("--- Full Log for AutoSelf Orchestrator ---\n\n")
            for line in self.orchestrator.log:
                f.write(line + "\n")
        print(f"\n✅ Full orchestrator log saved to: {filepath}")


# -------------------------------
# CLI wiring (adds configs/seeds + ablation flags) — non-destructive
# -------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AutoSelf resource-contention benchmark (upgraded, non-destructive)")
    p.add_argument("--config-dir", default=CONFIG_DIR, help="Directory with baselines.yml")
    p.add_argument("--seeds", default=SEEDS_FILE, help="Path to seeds.yaml")
    p.add_argument("--tasks", type=int, default=15, help="Number of tasks per run")
    p.add_argument("--mode", choices=["rules-only","sim-only","full"], default="full", help="Ablation mode")
    p.add_argument("--llm", choices=["on","off"], default="on", help="Enable/disable LLM-gated checks")
    p.add_argument("--p-override", type=float, nargs="*", default=None, help="Override p-grid (floats)")
    p.add_argument("--seed-group", default="contention", help="Key in seeds.yaml to use (default: contention)")
    return p.parse_args(argv)


async def async_main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    _ensure_dirs()

    base = load_baselines(args.config_dir)
    seeds_all = load_seeds(args.seeds)

    # p-grid
    if args.p_override:
        p_values = [float(x) for x in args.p_override]
    else:
        p_values = list(base.get("contention", {}).get("p_values", [0.1, 0.3, 0.5, 0.7, 0.9]))

    # seeds mapping per p (expected structure in seeds.yaml)
    seeds_map = seeds_all.get(args.seed_group, {})
    if not isinstance(seeds_map, dict):
        if isinstance(seeds_map, list):
            seeds_map = {"all": [int(x) for x in seeds_map]}
        else:
            seeds_map = {"all": [1, 2, 3]}

    runner = ExperimentRunner(num_tasks=int(args.tasks), p_values=p_values, seeds_map=seeds_map,
                              mode=args.mode, llm_gated=(args.llm == "on"))

    await runner.run_all_scenarios()
    return 0


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
