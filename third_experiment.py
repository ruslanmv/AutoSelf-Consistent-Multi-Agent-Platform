#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
third_experiment.py — Combined Hazard and Resource Contention Benchmark with AI Decision-Making.

This experiment synthesizes the features of the first two experiments and integrates an
LLM to act as the core decision-maker for the AutoSelf Orchestrator.

Key Features:
- Loads a mission plan with explicit dependencies from configs/world.yml.
- Simulates random environmental hazards by loading dust_scenarios.json.
- Models resource contention where tasks can conflict over a shared resource.
- The AutoSelf Orchestrator, when the AI is enabled, must handle both challenges by:
  1. Consulting an LLM with the full world state, hazard, and task information.
  2. Parsing the LLM's structured JSON response to decide whether to proceed,
     pause, or execute a safe alternative task.
- Emits standardized CSV artifacts for analysis, allowing direct comparison
  between the AI-driven strategy and the rule-based baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Optional BeeAI imports guarded to allow offline/repro runs
try:
    from beeai_framework.backend import ChatModel, UserMessage
    from beeai_framework.errors import FrameworkError
    from beeai_framework.adapters.watsonx import WatsonxChatModel
except Exception:  # pragma: no cover
    ChatModel = None
    UserMessage = None
    FrameworkError = Exception
    WatsonxChatModel = None


# -------------------------------
# Paths & constants
# -------------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
FIGS_DIR = os.environ.get("AUTOSELF_FIGS_DIR", "figs")
CONFIG_DIR = os.environ.get("AUTOSELF_CONFIG_DIR", "configs")
# SEEDS_FILE is now defined in load_all_configs via env var
HAZARDS_FILE = "dust_scenarios.json"

TIMELINE_FILE = os.path.join(RESULTS_DIR, "timeline_combined_hazard_contention.csv")
MAKESPAN_FILE = os.path.join(RESULTS_DIR, "makespan.csv")
CONFLICTS_FILE = os.path.join(RESULTS_DIR, "conflicts.csv")
OVERHEAD_FILE = os.path.join(RESULTS_DIR, "overhead.csv")

SCHEMA = [
    "scenario", "seed", "p", "makespan_s", "throughput_tpc", "conflicts",
    "unsafe_entries", "energy_j", "rules_ms", "sim_ms", "llm_ms",
    "correction_ms", "total_verif_ms"
]

# Per-cycle timeline schema for combined study (Exp-2 compatible + hazards)
TIMELINE_SCHEMA = [
    "scenario","seed","p","cycle","tasks_completed",
    "conflict_this_cycle","pair_needs_R_both","hazard_active","hazard_name"
]

def append_timeline_rows(rows: List[Dict[str, Any]]) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_header = not os.path.exists(TIMELINE_FILE)
    with open(TIMELINE_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TIMELINE_SCHEMA)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, None) for k in TIMELINE_SCHEMA})

# -------------------------------
# Pydantic Schemas for AI Interaction
# -------------------------------
class CycleDecisionResponse(BaseModel):
    tasks_to_execute: List[str] = Field(..., description="A list of task names to execute in the current cycle. Can be empty.")
    reasoning: str = Field(..., description="A brief justification for the decision.")

# -------------------------------
# Utilities
# -------------------------------
def ensure_dirs() -> None:
    # Using a print here instead of a log since this is a pre-run setup step
    print(f"[{now_hms()}] [DEBUG] Ensuring directories {RESULTS_DIR} and {FIGS_DIR} exist.")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGS_DIR, exist_ok=True)

def append_row(csv_path: str, row: Dict[str, Any]) -> None:
    ensure_dirs()
    write_header = not os.path.exists(csv_path)
    normalized = {k: row.get(k, None) for k in SCHEMA}
    # This debug print is very frequent, so it's a good candidate for conditional verbosity later
    # For now, we leave it as is.
    # print(f"[{now_hms()}] [DEBUG] Appending row to {csv_path}: {normalized}")
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if write_header:
            # print(f"[{now_hms()}] [DEBUG] Writing header to new file: {csv_path}")
            w.writeheader()
        w.writerow(normalized)

def now_hms() -> str:
    return time.strftime("%H:%M:%S", time.localtime())

# -------------------------------
# Config Loading (robust)
# -------------------------------
def _read_yaml(path: str) -> Dict[str, Any]:
    import yaml
    print(f"[{now_hms()}] [DEBUG] Attempting to read YAML file at {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"[{now_hms()}] [WARN] Config file not found at {path}. Using defaults.")
        return {}
    except Exception as e:
        print(f"[{now_hms()}] [WARN] Failed to read {path}: {e}. Using defaults.")
        return {}

def load_all_configs(config_dir: str) -> Tuple[Dict, Dict, Dict, List, List]:
    print(f"[{now_hms()}] [INFO] Loading configuration from: {config_dir}")

    # Load three main configs
    autoself_cfg = _read_yaml(os.path.join(config_dir, "autoself.yml"))
    world_cfg    = _read_yaml(os.path.join(config_dir, "world.yml"))
    base_cfg     = _read_yaml(os.path.join(config_dir, "baselines.yml"))

    # Ensure 'site' key exists (your new YAML block)
    world_cfg.setdefault("site", {})
    if "site" not in world_cfg or not isinstance(world_cfg["site"], dict):
        world_cfg["site"] = {}

    # Hazards
    try:
        print(f"[{now_hms()}] [DEBUG] Loading hazard scenarios from {HAZARDS_FILE}")
        with open(HAZARDS_FILE, "r", encoding="utf-8") as f:
            hazard_scenarios = json.load(f).get("dust_scenarios", [])
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"[{now_hms()}] [WARN] {HAZARDS_FILE} not found or invalid. No hazards will be simulated.")
        hazard_scenarios = []

    # Seeds: prefer env AUTOSELF_SEEDS_FILE; else project-root seeds.yaml
    seeds_path = os.environ.get("AUTOSELF_SEEDS_FILE", "seeds.yaml")
    print(f"[{now_hms()}] [DEBUG] Loading seeds from {seeds_path}")
    seeds_data = _read_yaml(seeds_path)
    seeds = (seeds_data.get("hazards_failures", {}) or {}).get("seeds", [42])

    print(f"[{now_hms()}] [INFO] Config loading done. "
          f"missions={len(world_cfg.get('mission_plan', []))}, "
          f"p_grid={base_cfg.get('contention', {}).get('p_values', [])}, "
          f"seeds={seeds}")
    return autoself_cfg, world_cfg, base_cfg, hazard_scenarios, seeds


# -------------------------------
# Core Simulation Classes
# -------------------------------
class WorldState:
    """Unified world state for combined simulation."""
    def __init__(self, mission_plan: List[Dict]):
        self.start_time = time.time()
        self.state: Dict[str, Any] = {"site_power_level": 100.0}
        for task in mission_plan:
            self.state[task["output_state"]] = False

        self.active_hazard: Optional[Dict[str, Any]] = None
        self.log: List[str] = [f"[{now_hms()}] World state initialized."]
        self.conflicts = 0
        # print(f"[{now_hms()}] [INFO] WorldState initialized with {len(mission_plan)} tasks.")

    def update(self, key: str, value: Any) -> None:
        if key in self.state:
            self.state[key] = value
            self.log.append(f"[{now_hms()}] STATE UPDATE: {key} set to {value}")
            # print(f"[{now_hms()}] [DEBUG] WorldState updated: {key} -> {value}")

class Task:
    """Represents a mission task with dependencies and resource needs."""
    def __init__(self, details: Dict, conflict_prob: float, rng: random.Random):
        self.name = details["name"]
        self.capability = details["capability"]
        self.duration = details["duration"]
        self.output_state = details["output_state"]
        self.dependencies = details.get("dependencies", [])
        self.needs_R = rng.random() < conflict_prob
    
    def to_dict(self):
        return {
            "name": self.name,
            "capability": self.capability,
            "dependencies": self.dependencies,
            "needs_R": self.needs_R
        }

@dataclass
class OverheadTimer:
    rules_ms: float = 0.0
    sim_ms: float = 0.0
    llm_ms: float = 0.0
    correction_ms: float = 0.0
    def total(self) -> float:
        return self.rules_ms + self.sim_ms + self.llm_ms + self.correction_ms

class AutoSelfOrchestrator:
    """Orchestrator that uses an LLM for complex decision-making (robust, throttled, with graceful fallback)."""

    def __init__(self, world_state: WorldState, llm_gated: bool):
        self.world_state = world_state
        self.llm = None
        self.llm_enabled = llm_gated
        self.llm_fail_count = 0
        self.llm_fail_limit = 5      # after N consecutive failures, auto-disable LLM
        self.llm_disabled_note = False
        self.max_llm_ms = float(os.getenv("WATSONX_MAX_LATENCY_MS", 8000))  # soft latency guard
        self._llm_sem = asyncio.Semaphore(int(os.getenv("WATSONX_MAX_CONCURRENCY", "8")))  # throttle, like exp2

        if llm_gated:
            self._initialize_llm()

    def _initialize_llm(self):
        load_dotenv()
        api_key = os.getenv("WATSONX_API_KEY")
        project_id = os.getenv("PROJECT_ID")
        api_base = os.getenv("WATSONX_URL")

        temperature    = float(os.getenv("WATSONX_TEMPERATURE", 0.05))
        top_p          = float(os.getenv("WATSONX_TOP_P", 0.9))
        max_new_tokens = int(float(os.getenv("WATSONX_MAX_NEW_TOKENS", 300)))

        if all([api_key, project_id, api_base, WatsonxChatModel]):
            try:
                self.llm = WatsonxChatModel(
                    model_id="meta-llama/llama-3-70b-instruct",
                    settings={
                        "api_key": api_key,
                        "project_id": project_id,
                        "api_base": api_base,
                        "temperature": temperature,
                        "top_p": top_p,
                        "max_new_tokens": max_new_tokens,
                    },
                )
                self.world_state.log.append(f"[{now_hms()}] LLM Initialized Successfully.")
            except Exception as e:
                self.world_state.log.append(f"[{now_hms()}] LLM Initialization Failed: {e}")
                self.llm = None
                self.llm_enabled = False
        else:
            self.world_state.log.append(f"[{now_hms()}] LLM disabled (missing credentials or BeeAI framework).")
            self.llm_enabled = False

    async def aclose(self):
        """Gracefully close the model client to avoid unclosed session warnings."""
        try:
            if self.llm and hasattr(self.llm, "aclose") and callable(getattr(self.llm, "aclose")):
                await self.llm.aclose()
            elif self.llm and hasattr(self.llm, "close") and callable(getattr(self.llm, "close")):
                self.llm.close()
        except Exception:
            pass

    def _build_prompt(self, candidate_tasks: List[Task], remaining_tasks: List[Task]) -> str:
        prompt = f"""
As an AutoSelf Orchestrator, your goal is to maximize mission progress while ensuring safety.
Analyze the current world state, active hazards, and candidate tasks to decide the best course of action.

**Current World State:**
{json.dumps(self.world_state.state, indent=2)}

**Active Hazard:**
{json.dumps(self.world_state.active_hazard, indent=2) if self.world_state.active_hazard else "None"}

**Candidate Tasks for this Cycle (Max 2):**
{json.dumps([t.to_dict() for t in candidate_tasks], indent=2)}

**Other Remaining Tasks (Potential Alternatives):**
{json.dumps([t.to_dict() for t in remaining_tasks if t not in candidate_tasks][:5], indent=2)}

**Your Task:**
Based on the data, decide which tasks to execute now.
1.  **Hazard Check:** A task is unsafe if its capability is in the hazard's 'affected_capabilities'.
2.  **Dependency Check:** A task can only run if all its 'dependencies' are 'true' in the world state.
3.  **Resource Conflict Check:** If two tasks both have 'needs_R: true', they conflict. Execute only the first one.
4.  **Alternative Task Strategy:** If the primary candidate(s) are blocked by a hazard, can a safe, dependency-cleared alternative from the remaining tasks be executed instead?

Respond ONLY with a JSON object matching the CycleDecisionResponse schema.
"""
        return prompt

    def _extract_json(self, text: str) -> Optional[dict]:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            self.world_state.log.append(f"[{now_hms()}] JSON parsing failed for LLM output.")
        return None

    def _fallback_decision(self, tasks_in_cycle: List[Task], all_remaining: List[Task]) -> List[Task]:
        tasks = tasks_in_cycle[:]
        if self.world_state.active_hazard:
            affected = set(self.world_state.active_hazard.get("affected_capabilities", []))
            tasks = [t for t in tasks if t.capability not in affected]
        if len(tasks) >= 2 and tasks[0].needs_R and tasks[1].needs_R:
            self.world_state.conflicts += 1
            return [tasks[0]]
        return tasks

    async def verify_cycle_with_llm(self, tasks_in_cycle: List[Task], all_remaining: List[Task], overhead: OverheadTimer) -> List[Task]:
        if not (self.llm and self.llm_enabled):
            return self._fallback_decision(tasks_in_cycle, all_remaining)

        prompt = self._build_prompt(tasks_in_cycle, all_remaining)
        t0 = time.perf_counter()

        try:
            async with self._llm_sem:
                resp = await self.llm.create(messages=[UserMessage(content=prompt)])

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if elapsed_ms > self.max_llm_ms:
                self.world_state.log.append(
                    f"[{now_hms()}] LLM response exceeded latency budget ({elapsed_ms:.0f} ms > {self.max_llm_ms:.0f} ms). Using fallback."
                )
                self.llm_fail_count += 1
                if self.llm_fail_count >= self.llm_fail_limit and not self.llm_disabled_note:
                    self.llm_enabled = False
                    self.llm_disabled_note = True
                    self.world_state.log.append(
                        f"[{now_hms()}] Circuit breaker: disabling LLM after {self.llm_fail_count} consecutive slow/error cycles."
                    )
                return self._fallback_decision(tasks_in_cycle, all_remaining)
            
            raw = ""
            if getattr(resp, "messages", None):
                if len(resp.messages) > 0 and getattr(resp.messages[0], "content", None):
                    parts = resp.messages[0].content
                    if parts and len(parts) > 0 and hasattr(parts[0], "text"):
                        raw = parts[0].text or ""

            if not raw:
                self.world_state.log.append(f"[{now_hms()}] LLM returned empty content; applying fallback rules.")
                self.llm_fail_count += 1
                return self._fallback_decision(tasks_in_cycle, all_remaining)

            payload = self._extract_json(raw)
            if not payload:
                self.world_state.log.append(f"[{now_hms()}] LLM output not valid JSON; applying fallback rules.")
                self.llm_fail_count += 1
                return self._fallback_decision(tasks_in_cycle, all_remaining)

            tasks_to_execute = payload.get("tasks_to_execute", [])
            reasoning = payload.get("reasoning", "No reasoning provided.")
            if not isinstance(tasks_to_execute, list):
                tasks_to_execute = []

            self.world_state.log.append(f"[{now_hms()}] AI DECISION: {reasoning}")
            approved = [t for t in all_remaining if t.name in tasks_to_execute]

            if not approved and tasks_in_cycle:
                self.world_state.log.append(f"[{now_hms()}] LLM approved no tasks; applying fallback rules.")
                approved = self._fallback_decision(tasks_in_cycle, all_remaining)

            if len(tasks_in_cycle) > 1 and len(approved) == 1:
                if tasks_in_cycle[0].needs_R and tasks_in_cycle[1].needs_R:
                    self.world_state.conflicts += 1

            self.llm_fail_count = 0
            return approved

        except Exception as e:
            self.world_state.log.append(f"[{now_hms()}] ERROR: LLM decision failed: {e}. Falling back to rules.")
            self.llm_fail_count += 1
            if self.llm_fail_count >= self.llm_fail_limit and not self.llm_disabled_note:
                self.llm_enabled = False
                self.llm_disabled_note = True
                self.world_state.log.append(
                    f"[{now_hms()}] Circuit breaker: disabling LLM after {self.llm_fail_count} consecutive failures."
                )
            return self._fallback_decision(tasks_in_cycle, all_remaining)
        finally:
            overhead.llm_ms += (time.perf_counter() - t0) * 1000.0


class LiveProgress:
    """
    Minimal live progress line for terminal. Prints a single updating line with:
      - tasks completed / total
      - cycles elapsed
      - estimated remaining cycles (from expected tasks-per-cycle)
      - ETA (from moving average of actual wall time per cycle)
    """
    def __init__(self, label: str, total_tasks: int, expected_tpc: float):
        self.label = label
        self.total_tasks = max(1, int(total_tasks))
        self.expected_tpc = max(0.5, float(expected_tpc))  # avoid division by zero / too small
        self.start_ts = time.perf_counter()
        self.cycles = 0
        self.done = 0
        self._last_print = 0.0
        self._print_min_interval = 0.05  # seconds (avoid spamming the terminal)

    def update(self, cycles_elapsed: int, remaining_tasks: int, stalled: bool = False):
        self.cycles = int(cycles_elapsed)
        self.done = self.total_tasks - int(remaining_tasks)
        self.done = max(0, min(self.done, self.total_tasks))

        # Estimate remaining cycles from current remaining tasks and expected concurrency
        remaining_cycles_est = math.ceil(remaining_tasks / self.expected_tpc) if remaining_tasks > 0 else 0

        # Moving average per-cycle wall time: simple mean from start
        elapsed = time.perf_counter() - self.start_ts
        avg_cycle_time = (elapsed / self.cycles) if self.cycles > 0 else 0.0
        eta_sec = remaining_cycles_est * avg_cycle_time

        pct = 100.0 * self.done / self.total_tasks
        eta_str = self._fmt_seconds(eta_sec)
        stall_flag = " • stalled" if stalled else ""

        # Throttle prints to keep the terminal readable
        now = time.perf_counter()
        if (now - self._last_print) >= self._print_min_interval:
            line = (
                f"{self.label} | {self.done}/{self.total_tasks} "
                f"({pct:5.1f}%) • cycles: {self.cycles} • "
                f"rem≈{remaining_cycles_est} • ETA: {eta_str}{stall_flag}"
            )
            print("\r" + line + " " * 10, end="", file=sys.stdout, flush=True)
            self._last_print = now

    def finish(self):
        # Final newline to keep output tidy
        print("", file=sys.stdout)

    @staticmethod
    def _fmt_seconds(x: float) -> str:
        x = max(0.0, float(x))
        m, s = divmod(int(x + 0.5), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:d}:{s:02d}"


# -------------------------------
# Experiment Runner
# -------------------------------
class ExperimentRunner:
    def __init__(self, configs: Dict, scenarios: List, seeds: List, llm_gated: bool):
        self.autoself_cfg, self.world_cfg, self.base_cfg = configs['auto'], configs['world'], configs['base']
        self.hazard_scenarios = scenarios
        self.seeds = seeds
        self.llm_gated = llm_gated
        self.mission_plan_details = self.world_cfg.get("mission_plan", [])
        print(f"[{now_hms()}] [INFO] ExperimentRunner initialized. LLM gated: {llm_gated}. Seeds: {seeds}.")
        if not self.mission_plan_details or not all("dependencies" in task for task in self.mission_plan_details):
            print(f"[{now_hms()}] [CRITICAL] Mission plan with dependencies is missing from world.yml. Aborting.")
            raise ValueError("Mission plan (with dependencies) is missing from world.yml")

    async def run(self):
        print(f"[{now_hms()}] [INFO] Starting experiment runs for all seeds and contention probabilities.")
        for seed in self.seeds:
            for p in self.base_cfg.get("contention", {}).get("p_values", [0.5]):
                await self.run_single_simulation("autoself_ai", p, seed)
                await self.run_single_simulation("baseline", p, seed)
        print(f"[{now_hms()}] [INFO] All experiment runs completed.")

    async def run_single_simulation(self, strategy: str, p: float, seed: int):
        print(f"\n[{now_hms()}] Running simulation: Strategy={strategy}, P={p}, Seed={seed}")
        rng = random.Random(seed)
        ws = WorldState(self.mission_plan_details)
        # Normalize strategy tag for CSVs
        scenario_tag = "autoself" if strategy.startswith("autoself") else "baseline"

        orch = AutoSelfOrchestrator(ws, llm_gated=(scenario_tag == "autoself" and self.llm_gated))
        overhead = OverheadTimer()

        sim_cfg = (self.base_cfg.get("sim", {}) if isinstance(self.base_cfg, dict) else {})
        MAX_SECONDS       = float(os.environ.get("AUTOSELF_MAX_SECONDS",      sim_cfg.get("max_seconds", 600)))
        MAX_CYCLES        = int(float(os.environ.get("AUTOSELF_MAX_CYCLES",   sim_cfg.get("max_cycles",  5000))))
        MAX_STALL_CYCLES  = int(float(os.environ.get("AUTOSELF_MAX_STALL_CYCLES", sim_cfg.get("max_stall_cycles", 200))))

        sim_start = time.time()
        stall_cycles = 0

        remaining_tasks = [Task(details, p, rng) for details in self.mission_plan_details]
        expected_tpc = max(1.0, 2.0 - (p * p))
        progress = LiveProgress(
            label=f"[{scenario_tag}] p={p:.1f} seed={seed}",
            total_tasks=len(remaining_tasks),
            expected_tpc=expected_tpc,
        )

        # ---- per-run state for timeline/metrics ----
        cycle_count = 0
        tasks_done = 0
        timeline_rows: List[Dict[str, Any]] = []

        makespan_s = 0.0
        active_hazard_end_time = 0.0

        while remaining_tasks:
            cycle_count += 1

            if time.time() - sim_start > MAX_SECONDS:
                ws.log.append(f"[{now_hms()}] STOP: wall-clock budget {MAX_SECONDS}s reached.")
                break
            if cycle_count >= MAX_CYCLES:
                ws.log.append(f"[{now_hms()}] STOP: cycle budget {MAX_CYCLES} reached.")
                break

            # Hazard bookkeeping
            current_time = time.time()
            if ws.active_hazard and current_time > active_hazard_end_time:
                ws.log.append(f"[{now_hms()}] HAZARD CLEARED: {ws.active_hazard['name']} passed.")
                ws.active_hazard = None

            if not ws.active_hazard and self.hazard_scenarios and rng.random() < 0.25:
                scenario = random.choice(self.hazard_scenarios)
                ws.active_hazard = scenario
                duration = rng.randint(scenario["duration_seconds"]["min"], scenario["duration_seconds"]["max"])
                active_hazard_end_time = current_time + duration
                ws.log.append(f"[{now_hms()}] HAZARD TRIGGERED: {scenario['name']} for {duration}s.")

            # Enabled tasks by dependency
            executable_tasks = sorted(
                [t for t in remaining_tasks if all(ws.state.get(dep) for dep in t.dependencies)],
                key=lambda t: len(t.dependencies)
            )

            if not executable_tasks:
                # Pause during hazard; deadlock if no hazard
                if ws.active_hazard:
                    ws.log.append(f"[{now_hms()}] Paused. No tasks can proceed.")
                    await asyncio.sleep(0.1)
                    makespan_s += 0.1
                    # timeline row with 0 executed
                    timeline_rows.append({
                        "scenario": scenario_tag, "seed": seed, "p": p, "cycle": cycle_count,
                        "tasks_completed": tasks_done, "conflict_this_cycle": 0,
                        "pair_needs_R_both": 0,
                        "hazard_active": 1, "hazard_name": ws.active_hazard["name"] if ws.active_hazard else ""
                    })
                    progress.update(cycle_count, len(remaining_tasks), stalled=True)
                    continue
                else:
                    ws.log.append(f"[{now_hms()}] DEADLOCK: No tasks with met dependencies.")
                    break

            tasks_for_cycle = executable_tasks[:2]
            # Ground-truth: do both candidate tasks need the exclusive resource?
            pair_needs_R_both = int(len(tasks_for_cycle) >= 2 and tasks_for_cycle[0].needs_R and tasks_for_cycle[1].needs_R)

            progress.update(cycle_count, len(remaining_tasks), stalled=False)

            # Decide which to execute this cycle
            if scenario_tag == "autoself":
                # "Analysis" time (rules) — cheap, but account it to rules_ms
                t_rules = time.perf_counter()
                # (placeholder: where you'd run rules checks)
                overhead.rules_ms += (time.perf_counter() - t_rules) * 1000.0

                tasks_to_execute = await orch.verify_cycle_with_llm(tasks_for_cycle, remaining_tasks, overhead)
            else:
                # Baseline: rule-of-thumb gating only
                tasks_to_execute = tasks_for_cycle
                if ws.active_hazard:
                    affected_caps = ws.active_hazard.get("affected_capabilities", [])
                    tasks_to_execute = [t for t in tasks_to_execute if t.capability not in affected_caps]
                if len(tasks_to_execute) > 1 and tasks_to_execute[0].needs_R and tasks_to_execute[1].needs_R:
                    ws.conflicts += 1
                    tasks_to_execute = [tasks_to_execute[0]]

            # Execute / stall
            if not tasks_to_execute:
                ws.log.append(f"[{now_hms()}] No tasks to execute this cycle. Waiting.")
                stall_cycles += 1
                progress.update(cycle_count, len(remaining_tasks), stalled=True)
                if stall_cycles >= MAX_STALL_CYCLES:
                    ws.log.append(f"[{now_hms()}] STOP: no-progress budget {MAX_STALL_CYCLES} cycles reached.")
                    break
                await asyncio.sleep(0.1)
                makespan_s += 0.1

                # timeline row (0 executed)
                timeline_rows.append({
                    "scenario": scenario_tag, "seed": seed, "p": p, "cycle": cycle_count,
                    "tasks_completed": tasks_done, "conflict_this_cycle": 0,
                    "pair_needs_R_both": pair_needs_R_both,
                    "hazard_active": 1 if ws.active_hazard else 0,
                    "hazard_name": ws.active_hazard["name"] if ws.active_hazard else ""
                })
                continue

            stall_cycles = 0

            # Record conflict_this_cycle (policy-dependent meaning:
            # baseline => actual collision avoidance; autoself => predicted/staggered)
            conflict_this_cycle = int(pair_needs_R_both and len(tasks_to_execute) == 1)

            # Execute chosen tasks (1 or 2)
            max_duration = 0.0
            for task in tasks_to_execute:
                ws.log.append(f"[{now_hms()}] EXECUTING: '{task.name}'")
                ws.update(task.output_state, True)
                max_duration = max(max_duration, float(task.duration))
                remaining_tasks = [t for t in remaining_tasks if t.name != task.name]

            executed = len(tasks_to_execute)
            tasks_done += executed

            progress.update(cycle_count, len(remaining_tasks), stalled=False)
            await asyncio.sleep(max_duration / 10.0)
            makespan_s += max_duration

            # timeline row after execution
            timeline_rows.append({
                "scenario": scenario_tag, "seed": seed, "p": p, "cycle": cycle_count,
                "tasks_completed": tasks_done, "conflict_this_cycle": conflict_this_cycle,
                "pair_needs_R_both": pair_needs_R_both,
                "hazard_active": 1 if ws.active_hazard else 0,
                "hazard_name": ws.active_hazard["name"] if ws.active_hazard else ""
            })

        # ---- finalize per-run metrics (Exp-2 compatible) ----
        throughput_tpc = (tasks_done / cycle_count) if cycle_count > 0 else 0.0

        # Fill missing overhead components with zeros to avoid None in CSVs
        for k in ("rules_ms", "sim_ms", "correction_ms", "llm_ms"):
            setattr(overhead, k, float(getattr(overhead, k) or 0.0))

        row = {
            "scenario": scenario_tag, "seed": seed, "p": p,
            "makespan_s": round(makespan_s, 2),
            "throughput_tpc": round(throughput_tpc, 6),
            "conflicts": ws.conflicts, "unsafe_entries": 0, "energy_j": None,
            "rules_ms": round(overhead.rules_ms, 2),
            "sim_ms": round(overhead.sim_ms, 2),
            "llm_ms": round(overhead.llm_ms, 2),
            "correction_ms": round(overhead.correction_ms, 2),
            "total_verif_ms": round(overhead.total(), 2),
        }

        append_row(MAKESPAN_FILE, row)
        append_row(CONFLICTS_FILE, row)
        append_row(OVERHEAD_FILE, row)

        # Persist per-cycle timeline
        append_timeline_rows(timeline_rows)

        progress.finish()
        await orch.aclose()
        print(f"[{now_hms()}] [INFO] Finished run: {row}")

# -------------------------------
# CLI
# -------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="AutoSelf Combined Hazard and Contention Benchmark")
    parser.add_argument("--llm", choices=["on", "off"], default="on", help="Enable/disable LLM for AutoSelf strategy")
    parser.add_argument("--max-seconds", type=float, default=None, help="Wall-clock max seconds for a single run")
    parser.add_argument("--max-cycles", type=int, default=None, help="Cycle budget for a single run")
    parser.add_argument("--max-stall-cycles", type=int, default=None, help="Max consecutive no-progress cycles")
    return parser.parse_args()

async def async_main():
    args = parse_args()
    print(f"[{now_hms()}] [INFO] Starting AutoSelf Benchmark. LLM argument: --llm {args.llm}")
    ensure_dirs()

    # Initialize per-cycle timeline file with the full schema header
    print(f"[{now_hms()}] [INFO] Initializing timeline file: {TIMELINE_FILE}")
    with open(TIMELINE_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TIMELINE_SCHEMA)
        w.writeheader()

    # Load configs and scenarios
    autoself_cfg, world_cfg, base_cfg, hazard_scenarios, seeds = load_all_configs(CONFIG_DIR)

    # Apply CLI overrides to sim limits
    base_cfg.setdefault("sim", {})
    if args.max_seconds is not None:
        base_cfg["sim"]["max_seconds"] = float(args.max_seconds)
    if args.max_cycles is not None:
        base_cfg["sim"]["max_cycles"] = int(args.max_cycles)
    if args.max_stall_cycles is not None:
        base_cfg["sim"]["max_stall_cycles"] = int(args.max_stall_cycles)

    # Run experiments
    runner = ExperimentRunner(
        configs={"auto": autoself_cfg, "world": world_cfg, "base": base_cfg},
        scenarios=hazard_scenarios,
        seeds=seeds,
        llm_gated=(args.llm == "on"),
    )
    await runner.run()

    print(f"\nDone. Artifacts written to: {RESULTS_DIR}")

def main() -> int:
    try:
        asyncio.run(async_main())
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130
    except Exception as e:
        print(f"[{now_hms()}] [CRITICAL] A critical unexpected error occurred in main: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    print(f"[{now_hms()}] [INFO] --- Script execution started ---")
    exit_code = main()
    print(f"[{now_hms()}] [INFO] --- Script execution finished with exit code {exit_code} ---")
    sys.exit(exit_code)
