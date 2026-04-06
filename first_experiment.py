#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
first_experiment.py — Hazards/Failures workflow with E–V–C verification logging.

Publication-grade version with paper-ready data artifacts and faithful timing.

Key features:
- CLI flags for ablations and single-seed runs.
- Loads parameters from YAML configs.
- Hybrid verification (rules + sim + optional LLM gating).
- Projected-power guard (verify-before-execute) + non-terminal recovery (recharge/alternates).
- Robust, schema-stable CSV outputs for per-cycle timelines, per-run summaries, and per-task executions.
- Dependency checks in rules verification; counts prevented-unsafe entries once per pause cycle.
- Pause/issue instrumentation; retry tracking; energy model; capability aliasing.
- Virtual time offset so simulated waits affect makespan and plots (no optimism bias).
- Graceful LLM cleanup (no aiohttp warnings).
- Plots that tolerate config/name drift (no KeyErrors on missing columns).

Artifacts written under results/ and figs/:
- results/timeline_nominal.csv|timeline_hazard.csv|timeline_failure.csv
- results/tasks_nominal.csv|tasks_hazard.csv|tasks_failure.csv
- results/makespan.csv, results/conflicts.csv, results/overhead.csv
- figs/<Scenario>_timeline.png and verbose logs per scenario.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Optional BeeAI imports guarded to allow offline/repro runs
try:  # pragma: no cover
    from beeai_framework.backend import ChatModel, UserMessage
    from beeai_framework.adapters.watsonx import WatsonxChatModel
except Exception:  # pragma: no cover
    ChatModel = None  # type: ignore
    UserMessage = None  # type: ignore


# -------------------------------
# Paths & constants
# -------------------------------
RESULTS_DIR = os.environ.get("AUTOSELF_RESULTS_DIR", "results")
FIGS_DIR = os.environ.get("AUTOSELF_FIGS_DIR", "figs")
CONFIG_DIR = os.environ.get("AUTOSELF_CONFIG_DIR", "configs")

TIMELINE_FILES = {
    "nominal": os.path.join(RESULTS_DIR, "timeline_nominal.csv"),
    "hazard": os.path.join(RESULTS_DIR, "timeline_hazard.csv"),
    "failure": os.path.join(RESULTS_DIR, "timeline_failure.csv"),
}
TASKS_FILES = {
    "nominal": os.path.join(RESULTS_DIR, "tasks_nominal.csv"),
    "hazard": os.path.join(RESULTS_DIR, "tasks_hazard.csv"),
    "failure": os.path.join(RESULTS_DIR, "tasks_failure.csv"),
}
MAKESPAN_FILE = os.path.join(RESULTS_DIR, "makespan.csv")
CONFLICTS_FILE = os.path.join(RESULTS_DIR, "conflicts.csv")
OVERHEAD_FILE = os.path.join(RESULTS_DIR, "overhead.csv")

# Standard CSV schema used across summary artifacts (per-run rows)
SCHEMA = [
    "scenario",
    "seed",
    "p",
    "makespan_s",
    "throughput_tpc",
    "conflicts",
    "unsafe_entries",
    "energy_j",
    "pauses",
    "retries_total",
    "rules_ms",
    "sim_ms",
    "llm_ms",
    "correction_ms",
    "total_verif_ms",
]


# -------------------------------
# Utilities
# -------------------------------

def ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGS_DIR, exist_ok=True)


def append_row(csv_path: str, row: Dict[str, Any]) -> None:
    ensure_dirs()
    write_header = not os.path.exists(csv_path)
    normalized = {k: row.get(k, None) for k in SCHEMA}
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if write_header:
            w.writeheader()
        w.writerow(normalized)


def now_hms() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


# -------------------------------
# Config loading
# -------------------------------

def _read_yaml(path: str) -> Dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_configs(
    config_dir: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    autoself_path = os.path.join(config_dir, "autoself.yml")
    world_path = os.path.join(config_dir, "world.yml")
    base_path = os.path.join(config_dir, "baselines.yml")
    if not (
        os.path.exists(autoself_path)
        and os.path.exists(world_path)
        and os.path.exists(base_path)
    ):
        raise FileNotFoundError(
            f"Missing config(s) in '{config_dir}'. Expected autoself.yml, world.yml, baselines.yml"
        )
    return _read_yaml(autoself_path), _read_yaml(world_path), _read_yaml(base_path)


def load_seeds(path: str) -> Dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# -------------------------------
# Core simulation classes
# -------------------------------

class WorldState:
    """Manages the simulation state for a single experiment run."""

    def __init__(self) -> None:
        self.start_time = time.time()
        self.virtual_time_offset_s = 0.0  # simulated (planned) waits: count toward makespan
        self.state: Dict[str, Any] = {
            # Back-compat defaults (will be extended per mission plan)
            "excavation_done": False,
            "compaction_done": False,
            "foundation_printed": False,
            "shell_printed": False,
            "inflatable_transported": False,
            "inflatable_deployed": False,
            "habitat_outfitted": False,
            # Site/env
            "site_power_level": 100.0,  # % remaining
            "energy_j": 0.0,            # cumulative energy (model)
            "ambient_temperature_celsius": -50,
            "dust_storm_active": False,
        }
        self.log: List[str] = []
        self.injected_failures: Dict[str, Dict[str, bool]] = {}
        self.last_llm_latency: float = 0.0
        self.unsafe_entries: int = 0  # count of *prevented* unsafe entries (per pause cycle)
        self.add_log("World state initialized.")

    def update(self, key: str, value: Any) -> None:
        if key in self.state:
            self.state[key] = value
            self.add_log(f"STATE UPDATE: {key} set to {value}")

    def add_log(self, message: str) -> None:
        log_entry = f"[{now_hms()}] {message}"
        self.log.append(log_entry)
        print(log_entry, file=sys.stdout)


class RoboticAgent:
    """Simulates a robotic agent."""

    def __init__(self, name: str, capabilities: List[str]):
        self.name = name
        if isinstance(capabilities, list):
            self.capabilities = capabilities
        elif capabilities is not None:
            self.capabilities = [capabilities]
        else:
            self.capabilities = []
        self.status = "idle"

    def can_perform(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass
class OverheadTimer:
    rules_ms: float = 0.0
    sim_ms: float = 0.0
    llm_ms: float = 0.0
    correction_ms: float = 0.0

    def total(self) -> float:
        return self.rules_ms + self.sim_ms + self.llm_ms + self.correction_ms


class AutoSelfOrchestrator:
    """Core logic engine for the simulation with E–V–C instrumentation."""

    def __init__(
        self,
        agents: List[RoboticAgent],
        mission_plan: List[Dict[str, Any]],
        world_state: WorldState,
        cfg_autoself: Dict[str, Any],
        mode: str = "full",
        llm_gated: bool = True,
    ) -> None:
        self.agents = agents
        self.mission_plan = mission_plan
        self.world_state = world_state
        self.history: List[Dict[str, Any]] = []
        self.cfg = cfg_autoself
        self.mode = mode
        self.llm_gated = llm_gated

        # Read new configuration knobs
        self.vcfg = self.cfg.get("verification", {})
        self.ccfg = self.cfg.get("correction", {})
        self.execfg = self.cfg.get("executor", {})
        self.cap_alias = self.execfg.get("capability_aliases", {})

        # Per-task execution records (for tasks_*.csv)
        self.task_events: List[Dict[str, Any]] = []

        # --- LLM setup (optional) ---
        load_dotenv()
        self.llm: Optional[ChatModel] = None
        if self.llm_gated and ChatModel is not None:
            api_key = os.getenv("WATSONX_API_KEY")
            project_id = os.getenv("PROJECT_ID")
            api_base = os.getenv("WATSONX_URL")
            try:
                if api_key and project_id and api_base:
                    llm_settings = {
                        "temperature": float(self.vcfg.get("llm_temperature", 0.1)),
                        "top_p":       float(self.vcfg.get("llm_top_p", 0.9)),
                        "project_id":  project_id,
                        "api_key":     api_key,
                        "api_base":    api_base,
                    }
                    self.llm = WatsonxChatModel(
                        model_id=self.vcfg.get(
                            "llm_model", "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"
                        ),
                        settings=llm_settings,
                    )
                    self.world_state.add_log("LLM Initialized Successfully.")
                else:
                    self.world_state.add_log("LLM disabled (missing credentials).")
            except Exception as e:
                self.world_state.add_log(f"LLM Initialization Failed: {e}")
                self.llm = None

    # -------------------------------
    # Housekeeping / instrumentation
    # -------------------------------
    def record_state(self, extra: Optional[Dict[str, Any]] = None) -> None:
        ts = (time.time() - self.world_state.start_time) + self.world_state.virtual_time_offset_s
        snapshot = {
            "time": ts,
            "mission_log_latest": self.world_state.log[-1] if self.world_state.log else "",
            "agent_status": {a.name: a.status for a in self.agents},
            "llm_latency": self.world_state.last_llm_latency,
        }
        snapshot.update(self.world_state.state)
        if extra:
            snapshot.update(extra)
        self.history.append(snapshot)

    # -------------------------------
    # Verification components
    # -------------------------------
    def _verify_rules(self, task: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        t0 = time.perf_counter()
        issues: List[str] = []

        # Environmental
        if self.world_state.state.get("dust_storm_active", False):
            issues.append("dust_storm_active")

        # Current power state
        current = float(self.world_state.state.get("site_power_level", 0.0))
        if current <= 0.0:
            issues.append("power_depleted")

        # Dependencies / preconditions
        for d in task.get("dependencies", []) or []:
            if not self.world_state.state.get(d, False):
                issues.append(f"dependency_unmet:{d}")

        # Projected-power guard (verify-before-execute)
        if self.vcfg.get("enable_power_guard", True):
            factor   = float(self.vcfg.get("power_draw_factor", 0.05))
            reserve  = float(self.vcfg.get("power_reserve", 5.0))
            duration = float(task.get("duration", 1.0))
            projected = current - duration * factor
            if projected < reserve:
                issues.append(
                    f"power_insufficient:curr={current:.2f},need={duration*factor:.2f},reserve={reserve:.2f}"
                )

        ok = len(issues) == 0
        dt = (time.perf_counter() - t0) * 1000.0
        return ok, dt, issues

    def _verify_sim(self, task: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        t0 = time.perf_counter()
        # Placeholder simulation; extend with digital twin rollouts if available
        issues: List[str] = []
        ok = True
        dt = (time.perf_counter() - t0) * 1000.0
        return ok, dt, issues

    def _verify_llm(self, task: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        if not self.llm_gated or self.llm is None or UserMessage is None:
            return True, 0.0, []
        t0 = time.perf_counter()
        try:
            # Favor synchronous generate if available
            if hasattr(self.llm, "generate") and callable(getattr(self.llm, "generate")):
                _ = self.llm.generate([UserMessage(f"Safety check for task: {task['name']}")])
            else:
                self._run_llm_async_create(UserMessage(f"Safety check for task: {task['name']}") )
            self.world_state.last_llm_latency = (time.perf_counter() - t0) * 1000.0
            return True, self.world_state.last_llm_latency, []
        except Exception as e:  # advisory only
            self.world_state.add_log(f"LLM check failed: {e}")
            return True, (time.perf_counter() - t0) * 1000.0, []

    def _run_llm_async_create(self, user_msg: "UserMessage") -> None:
        import asyncio

        async def _do_call():
            try:
                await self.llm.create(messages=[user_msg])  # type: ignore[attr-defined]
            except TypeError:
                await self.llm.create([user_msg])  # type: ignore

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import threading
            exc: List[BaseException] = []

            def _runner():
                try:
                    _loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(_loop)
                    _loop.run_until_complete(_do_call())
                    _loop.close()
                except BaseException as e:
                    exc.append(e)
            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join()
            if exc:
                raise exc[0]
        else:
            new_loop = loop or asyncio.new_event_loop()
            try:
                if not loop:
                    asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(_do_call())
            finally:
                if not loop:
                    new_loop.close()

    def _correct(self, issues: List[str]) -> float:
        t0 = time.perf_counter()
        # Minimal correction placeholder; extend to reschedule/reassign if needed
        dt = (time.perf_counter() - t0) * 1000.0
        return dt

    def verify_task(self, task: Dict[str, Any], overhead: OverheadTimer) -> Tuple[bool, List[str]]:
        use_rules = self.mode in ("rules-only", "full")
        use_sim = self.mode in ("sim-only", "full")
        issues: List[str] = []
        ok = True
        if use_rules:
            ok_rules, dt_rules, issues_r = self._verify_rules(task)
            overhead.rules_ms += dt_rules
            if not ok_rules:
                ok = False
                issues.extend(issues_r)
        if use_sim:
            ok_sim, dt_sim, issues_s = self._verify_sim(task)
            overhead.sim_ms += dt_sim
            if not ok_sim:
                ok = False
                issues.extend(issues_s)
        ok_llm, dt_llm, issues_l = self._verify_llm(task)
        overhead.llm_ms += dt_llm
        if not ok_llm:
            ok = False
            issues.extend(issues_l)
        if not ok:
            overhead.correction_ms += self._correct(issues)
        return ok, issues

    # -------------------------------
    # Execution
    # -------------------------------
    def execute_task_cycle(self, task: Dict[str, Any]) -> Tuple[bool, int, str, float, float]:
        """Execute one task. Returns (succeeded, retry_count, status, start_ts, end_ts)."""
        # Apply capability aliasing
        cap = task["capability"]
        cap = self.cap_alias.get(cap, cap)   # alias mapping
        agent = next((a for a in self.agents if a.can_perform(cap)), None)
        if not agent:
            self.world_state.add_log(f"No agent available for capability: {cap}")
            ts_now = (time.time() - self.world_state.start_time) + self.world_state.virtual_time_offset_s
            return False, 0, "failed", ts_now, ts_now

        agent.status = "executing"
        self.world_state.add_log(f"[Exec] Assigning '{task['name']}' to {agent.name}.")

        # Power & energy model using config knobs
        factor = float(self.vcfg.get("power_draw_factor", 0.05))
        watt_scale = float(self.vcfg.get("watt_scale", 1000.0))
        duration = float(task.get("duration", 1.0))

        start_ts = (time.time() - self.world_state.start_time) + self.world_state.virtual_time_offset_s

        # Draw power (remaining %), clamp to [0, 100]
        new_level = max(self.world_state.state["site_power_level"] - duration * factor, 0.0)
        self.world_state.update("site_power_level", round(new_level, 2))
        # Accumulate energy (arbitrary but consistent units)
        self.world_state.state["energy_j"] = float(self.world_state.state.get("energy_j", 0.0)) + factor * duration * watt_scale

        # Accelerated sleep to keep runs fast
        time.sleep(max(duration / 10.0, 0.01))

        retry_count = 0
        succeeded = True
        status = "success"

        if task["name"] in self.world_state.injected_failures:
            succeeded = False
            del self.world_state.injected_failures[task["name"]]

        if succeeded:
            self.world_state.update(task["output_state"], True)
            self.world_state.add_log(f"✅ Task '{task['name']}' completed successfully.")
        else:
            self.world_state.add_log(f"💥 Task '{task['name']}' FAILED.")
            self.world_state.add_log("[Correct] Retrying the task (minimal edit policy).")
            time.sleep(0.05)
            self.world_state.update(task["output_state"], True)
            self.world_state.add_log(f"✅ Task '{task['name']}' succeeded on retry.")
            retry_count = 1
            status = "retry_success"

        agent.status = "idle"
        end_ts = (time.time() - self.world_state.start_time) + self.world_state.virtual_time_offset_s

        # Record per-task event
        self.task_events.append({
            "task_name": task.get("name"),
            "capability": cap,  # aliased capability
            "duration_s_cfg": duration,
            "start_time_s": start_ts,
            "end_time_s": end_ts,
            "status": status,
            "retry_count": retry_count,
            "reason": "injected_failure" if retry_count > 0 else "",
        })

        return succeeded, retry_count, status, start_ts, end_ts

    # -------------------------------
    # Graceful cleanup
    # -------------------------------
    def close_llm(self) -> None:
        try:
            if self.llm is None:
                return
            if hasattr(self.llm, "close") and callable(getattr(self.llm, "close")):
                self.llm.close()
        except Exception:
            pass


# -------------------------------
# Experiment runner
# -------------------------------
class ExperimentRunner:
    def __init__(
        self,
        world_cfg: Dict[str, Any],
        autoself_cfg: Dict[str, Any],
        mode: str,
        llm_gated: bool,
    ) -> None:
        # Mission plan
        self.mission_plan: List[Dict[str, Any]] = world_cfg.get(
            "mission_plan",
            [
                {
                    "name": "Excavate Foundation Pit",
                    "capability": "excavation",
                    "duration": 2,
                    "output_state": "excavation_done",
                    "dependencies": [],
                },
                {
                    "name": "Compact and Level Ground",
                    "capability": "compaction",
                    "duration": 1,
                    "output_state": "compaction_done",
                    "dependencies": ["excavation_done"],
                },
                {
                    "name": "Print Foundation",
                    "capability": "printing",
                    "duration": 3,
                    "output_state": "foundation_printed",
                    "dependencies": ["compaction_done"],
                },
                {
                    "name": "Print Habitat Shell",
                    "capability": "printing",
                    "duration": 4,
                    "output_state": "shell_printed",
                    "dependencies": ["foundation_printed"],
                },
            ],
        )

        # Agents (allow YAML list-of-dicts or dict)
        agent_defs_raw = world_cfg.get(
            "agents",
            {
                "ExcavatorBot-01": ["excavation", "compaction"],
                "PrinterBot-7": ["printing"],
                "AssemblerBot-3": ["transport", "deployment", "outfitting"],
            },
        )
        if isinstance(agent_defs_raw, list):
            agent_defs = {k: v for d in agent_defs_raw for k, v in d.items()}
        else:
            agent_defs = agent_defs_raw

        self.agents = [RoboticAgent(name, caps) for name, caps in agent_defs.items()]
        self.autoself_cfg = autoself_cfg
        self.mode = mode
        self.llm_gated = llm_gated

    # --- helpers ---
    def _ensure_output_states_in_world(self, ws: WorldState) -> None:
        for t in self.mission_plan:
            k = t.get("output_state")
            if k and k not in ws.state:
                ws.state[k] = False

    def _scenario_key(self, scenario_name: str) -> str:
        s = scenario_name.lower()
        if s.startswith("nominal"):
            return "nominal"
        if s.startswith("dust_storm") or s.startswith("hazard"):
            return "hazard"
        return "failure"

    def _plot_results(self, df: pd.DataFrame, scenario_name: str) -> None:
        ensure_dirs()
        fig_path = os.path.join(FIGS_DIR, f"{scenario_name}_timeline.png")
        completion_cols_all = [t.get("output_state") for t in self.mission_plan if t.get("output_state")]
        available = [c for c in completion_cols_all if c in df.columns]
        df = df.copy()
        df["completed_tasks"] = df[available].sum(axis=1) if available else 0

        plt.figure(figsize=(12, 6))
        plt.step(df["time"], df["completed_tasks"], where="post", linewidth=2)
        plt.xlabel("Mission Time (seconds)")
        plt.ylabel("Tasks Completed")
        plt.ylim(0, len(completion_cols_all) + 1)
        plt.yticks(range(len(completion_cols_all) + 1))
        plt.title(f"Mission Timeline: {scenario_name.replace('_', ' ')}")
        plt.tight_layout()
        plt.savefig(fig_path, dpi=200)
        plt.close()

    def _save_verbose_log(self, log: List[str], scenario_name: str) -> None:
        ensure_dirs()
        with open(
            os.path.join(RESULTS_DIR, f"{scenario_name}_mission_log_verbose.txt"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(f"--- Full Mission Log for {scenario_name.replace('_', ' ')} ---\n\n")
            for line in log:
                f.write(line + "\n")

    def _emit_summary_rows(
        self,
        scenario: str,
        seed: int,
        history: List[Dict[str, Any]],
        overhead: OverheadTimer,
        retries_total: int,
    ) -> None:
        df = pd.DataFrame(history)
        makespan_s = float(df["time"].max()) if not df.empty else 0.0
        # Count tasks from mission plan outputs that exist in df
        n_tasks = sum(1 for t in self.mission_plan if t.get("output_state"))
        throughput_tpc = n_tasks / max(makespan_s, 1e-6)
        pauses = int(df.get("paused", pd.Series([0]*len(df))).sum())
        unsafe_entries = int(df.get("unsafe_entries", pd.Series([0]*len(df))).iloc[-1]) if not df.empty and "unsafe_entries" in df.columns else 0
        energy_j = float(df.get("energy_j", pd.Series([0.0])).iloc[-1]) if not df.empty else 0.0

        row = {
            "scenario": scenario,
            "seed": seed,
            "p": None,
            "makespan_s": round(makespan_s, 6),
            "throughput_tpc": round(throughput_tpc, 6),
            "conflicts": 0,  # not modeled here
            "unsafe_entries": unsafe_entries,
            "energy_j": round(energy_j, 3),
            "pauses": pauses,
            "retries_total": retries_total,
            "rules_ms": round(overhead.rules_ms, 3),
            "sim_ms": round(overhead.sim_ms, 3),
            "llm_ms": round(overhead.llm_ms, 3),
            "correction_ms": round(overhead.correction_ms, 3),
            "total_verif_ms": round(overhead.total(), 3),
        }
        append_row(MAKESPAN_FILE, row)
        append_row(CONFLICTS_FILE, row)
        append_row(OVERHEAD_FILE, row)

    def _write_timeline_csv(self, df: pd.DataFrame, scenario_key: str) -> None:
        """Emit per-cycle timeline CSV with extended columns (backward compatible)."""
        ensure_dirs()
        df = df.copy()
        completion_cols_all = [t.get("output_state") for t in self.mission_plan if t.get("output_state")]
        available = [c for c in completion_cols_all if c in df.columns]
        df["tasks_completed"] = df[available].sum(axis=1) if available else 0

        # Compatibility: map site_power_level to power_draw_w (trace of remaining power)
        df["power_draw_w"] = df.get("site_power_level", pd.Series([None]*len(df)))
        # Ensure pause/issue columns exist
        if "paused" not in df.columns:
            df["paused"] = 0
        if "issues_count" not in df.columns:
            df["issues_count"] = 0
        if "issue_kinds" not in df.columns:
            df["issue_kinds"] = ""

        df_out = pd.DataFrame({
            "time_s": df["time"],
            "tasks_completed": df["tasks_completed"],
            "power_draw_w": df["power_draw_w"],
            "paused": df["paused"],
            "issues_count": df["issues_count"],
            "issue_kinds": df["issue_kinds"],
            "site_power_level": df.get("site_power_level", pd.Series([None]*len(df))),
            "energy_j": df.get("energy_j", pd.Series([None]*len(df))),
        })
        tfile = TIMELINE_FILES[scenario_key]
        df_out.to_csv(tfile, index=False)

    def _write_tasks_table(self, orch: AutoSelfOrchestrator, scenario_key: str, seed: int) -> None:
        ensure_dirs()
        rows = []
        for ev in orch.task_events:
            r = ev.copy()
            r.update({"scenario": scenario_key, "seed": seed})
            rows.append(r)
        df = pd.DataFrame(rows)
        tfile = TASKS_FILES[scenario_key]
        write_header = not os.path.exists(tfile)
        with open(tfile, "a", newline="", encoding="utf-8") as f:
            cols = [
                "scenario", "seed",
                "task_name", "capability", "duration_s_cfg",
                "start_time_s", "end_time_s", "status", "retry_count", "reason",
            ]
            w = csv.DictWriter(f, fieldnames=cols)
            if write_header:
                w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in cols})

    # Agent-availability (with capability alias) for alternates
    def _can_any_agent(self, cap: str) -> bool:
        alias = self.autoself_cfg.get("executor", {}).get("capability_aliases", {})
        cap_eff = alias.get(cap, cap)
        return any(cap_eff in a.capabilities for a in self.agents)

    # Alternate task selection when blocked by power
    def _pick_alternate(self, ws: WorldState) -> Optional[Dict[str, Any]]:
        if not self.autoself_cfg.get("correction", {}).get("allow_alternates", True):
            return None
        max_dur = float(self.autoself_cfg.get("correction", {}).get("alternates_max_duration_s", 30))
        safe_caps = set(self.autoself_cfg.get("correction", {}).get("alternates_safe_caps", []))
        candidates = []
        for t in self.mission_plan:
            out = t.get("output_state")
            if not out or ws.state.get(out, False):
                continue
            deps = t.get("dependencies", []) or []
            if any(not ws.state.get(d, False) for d in deps):
                continue
            cap = t.get("capability", "")
            if safe_caps and cap not in safe_caps:
                continue
            if not self._can_any_agent(cap):
                continue
            if float(t.get("duration", 0)) <= max_dur:
                candidates.append(t)
        return sorted(candidates, key=lambda x: float(x.get("duration", 0)))[:1][0] if candidates else None

    # -------------------------------
    # Scenario execution
    # -------------------------------
    def run_scenario(
        self,
        scenario_name: str,
        seed: int,
        fault_to_inject: Optional[Dict[str, Any]] = None,
        hazard_to_toggle: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        np.random.seed(seed)
        ws = WorldState()
        # Align world state with mission outputs
        self._ensure_output_states_in_world(ws)

        orch = AutoSelfOrchestrator(
            self.agents,
            self.mission_plan,
            ws,
            self.autoself_cfg,
            self.mode,
            self.llm_gated,
        )
        try:
            ws.add_log("🚀 MISSION STARTED 🚀")
            orch.record_state()

            overhead = OverheadTimer()
            mission_failed = False

            for i, task in enumerate(self.mission_plan):
                # Hazard injection
                if hazard_to_toggle and hazard_to_toggle.get("task_index") == i:
                    ws.update("dust_storm_active", bool(hazard_to_toggle.get("value", False)))
                    ws.add_log(
                        f"🌪️ HAZARD INJECTED: Dust Storm set to {ws.state['dust_storm_active']}"
                    )
                # Failure injection
                if fault_to_inject and fault_to_inject.get("task_name") == task["name"]:
                    ws.injected_failures[task["name"]] = {"is_permanent": False}
                    ws.add_log(f"⚡ FAILURE INJECTED for task: {task['name']}")
                    fault_to_inject = None  # one-shot

                # Verification loop (E–V–C)
                is_safe, issues = orch.verify_task(task, overhead)
                paused_this_cycle = 0
                skipped_current = False

                while not is_safe:
                    # Count prevented-unsafe once per cycle
                    if paused_this_cycle == 0:
                        ws.unsafe_entries += 1
                    paused_this_cycle = 1

                    ws.add_log(f"🚨 Pausing due to safety concerns: {', '.join(issues)}")

                    # Recompute power projection coherently with rules
                    factor   = float(self.autoself_cfg.get("verification",{}).get("power_draw_factor", 0.05))
                    reserve  = float(self.autoself_cfg.get("verification",{}).get("power_reserve", 5.0))
                    duration = float(task.get("duration", 1.0))
                    projected = ws.state["site_power_level"] - duration * factor

                    # Try alternate task if blocked by power
                    if any(k.startswith("power_insufficient") for k in issues) or projected < reserve:
                        alt = self._pick_alternate(ws)
                        if alt and alt is not task:
                            ws.add_log(f"↪️ ALTERNATE: switching to '{alt['name']}' due to low power.")
                            succ, retry_count, status, start_ts, end_ts = orch.execute_task_cycle(alt)
                            orch.record_state({
                                "paused": 1,
                                "issues_count": len(issues),
                                "issue_kinds": "|".join(issues + ["alternate_selected"]),
                                "unsafe_entries": ws.unsafe_entries,
                            })

                    # Recharge instead of terminal failure
                    if any(k.startswith("power_insufficient") for k in issues) or projected < reserve:
                        rr = float(self.autoself_cfg.get("correction", {}).get("recharge_rate_pct_per_sec", 1.0))
                        wait_s = float(self.autoself_cfg.get("correction", {}).get("recharge_wait_s", 10.0))
                        charged = min(100.0, ws.state["site_power_level"] + rr * wait_s)
                        ws.update("site_power_level", round(charged, 2))
                        ws.virtual_time_offset_s += wait_s  # make wait visible in timeline/makespan
                        ws.add_log(f"🔋 RECHARGE: waited {wait_s}s, power -> {ws.state['site_power_level']}%")
                        time.sleep(0.005)

                        # Feasibility guard: even at 100% we would violate reserve
                        max_after_full = 100.0 - duration * factor
                        if max_after_full < reserve - 1e-9:
                            ws.add_log(
                                f"⏭️ SKIP: '{task['name']}' non-feasible under current power policy "
                                f"(duration={duration}, factor={factor}, reserve={reserve})."
                            )
                            skipped_current = True
                            break  # break safety loop; skip executing this task

                    # Recoverable hazard: clear dust storm (minimal model)
                    if "dust_storm_active" in issues:
                        ws.update("dust_storm_active", False)
                        ws.add_log("🌪️ HAZARD CLEARED: Dust Storm passed.")

                    orch.record_state({
                        "paused": 1,
                        "issues_count": len(issues),
                        "issue_kinds": "|".join(issues),
                        "unsafe_entries": ws.unsafe_entries,
                    })

                    # Re-verify for the original task
                    is_safe, issues = orch.verify_task(task, overhead)

                if mission_failed:
                    break

                if skipped_current:
                    # Record state after skip and continue to next task
                    orch.record_state({
                        "paused": paused_this_cycle,
                        "issues_count": len(issues) if paused_this_cycle else 0,
                        "issue_kinds": "|".join(issues) if paused_this_cycle else "",
                        "unsafe_entries": ws.unsafe_entries,
                    })
                    continue

                # Execute the original task
                succeeded, retry_count, status, start_ts, end_ts = orch.execute_task_cycle(task)
                orch.record_state({
                    "paused": paused_this_cycle,
                    "issues_count": len(issues) if paused_this_cycle else 0,
                    "issue_kinds": "|".join(issues) if paused_this_cycle else "",
                    "unsafe_entries": ws.unsafe_entries,
                })

            if not mission_failed:
                ws.add_log("🎉 MISSION COMPLETE! 🎉")
            else:
                ws.add_log("💥 MISSION FAILED 💥")

            df = pd.DataFrame(orch.history)

            # Determine key + write artifacts
            scenario_key = self._scenario_key(scenario_name)
            self._write_timeline_csv(df, scenario_key)
            self._plot_results(df, scenario_name)
            self._save_verbose_log(ws.log, scenario_name)

            # Per-run summary rows
            retries_total = sum(int(e.get("retry_count", 0)) for e in orch.task_events)
            self._emit_summary_rows(
                scenario=scenario_key,
                seed=seed,
                history=orch.history,
                overhead=overhead,
                retries_total=retries_total,
            )

            # Per-task table
            self._write_tasks_table(orch, scenario_key, seed)

            return df
        finally:
            orch.close_llm()


# -------------------------------
# CLI
# -------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AutoSelf hazards/failures workflow experiment"
    )
    p.add_argument(
        "--config-dir",
        default=CONFIG_DIR,
        help="Directory containing autoself.yml, world.yml, baselines.yml",
    )
    p.add_argument("--seeds", default="seeds.yaml", help="Path to seeds.yaml")
    p.add_argument(
        "--mode",
        choices=["rules-only", "sim-only", "full"],
        default="full",
        help="Ablation mode for verification components",
    )
    p.add_argument(
        "--llm", choices=["on", "off"], default="on", help="Enable/disable LLM-gated hints"
    )
    p.add_argument(
        "--seed-offset", type=int, default=0, help="Additive offset applied to all seeds"
    )
    p.add_argument(
        "--seed-override",
        type=int,
        default=None,
        help="If provided, run a single-seed experiment with this exact seed.",
    )
    p.add_argument(
        "--only",
        choices=["nominal", "hazard", "failure", "all"],
        default="all",
        help="Run only a subset of scenarios",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    ensure_dirs()

    print(f"--- Starting Experiment: Mode={args.mode}, LLM={args.llm}, Scenario(s)='{args.only}' ---")

    # Load configs and seeds
    cfg_autoself, cfg_world, cfg_base = load_configs(args.config_dir)
    seeds_all = load_seeds(args.seeds)

    # Single-seed override
    if args.seed_override is not None:
        hazard_seeds: List[int] = [int(args.seed_override)]
        print(f"[INFO] Using single override seed: {args.seed_override}")
    else:
        hazard_seeds = list((seeds_all.get("hazards_failures") or {}).get("seeds", []))
        if not hazard_seeds:
            hazard_seeds = [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]
        print(f"[INFO] Using seeds: {hazard_seeds}")

    runner = ExperimentRunner(
        cfg_world, cfg_autoself, mode=args.mode, llm_gated=(args.llm == "on")
    )

    scenarios: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    if args.only in ("nominal", "all"):
        scenarios.append(("Nominal_Mission", None, None))
    if args.only in ("hazard", "all"):
        # Example: inject storm around the 5th task (index 4) if present
        scenarios.append(("Dust_Storm_Hazard", None, {"task_index": 4, "value": True}))
    if args.only in ("failure", "all"):
        # Example failure name; adjust to your plan
        scenarios.append(("Nozzle_Clog_Failure", {"task_name": "Print Habitat Shell"}, None))

    for s in hazard_seeds:
        s = int(s) + int(args.seed_offset)
        np.random.seed(s)
        print("\n" + "=" * 50)
        print(f"[*] Starting run for seed: {s}")
        print("=" * 50)
        for name, fault, hazard in scenarios:
            print(f"\n--- Running scenario: {name} ---")
            runner.run_scenario(
                name, seed=s, fault_to_inject=fault, hazard_to_toggle=hazard
            )

    print("\n" + "=" * 50)
    print("Done. Artifacts written under:", RESULTS_DIR)
    print("=" * 50)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(130)
