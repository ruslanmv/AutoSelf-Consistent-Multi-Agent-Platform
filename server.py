import os
import asyncio
import json
import time
import mimetypes
import random
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Tuple, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# BeeAI Framework Imports (assuming they are in the environment)
# If not, these will need to be installed: pip install beeai_framework
try:
    from beeai_framework.backend import ChatModel, UserMessage
    from beeai_framework.errors import FrameworkError  # noqa: F401 (kept for parity with original)
    from beeai_framework.adapters.watsonx import WatsonxChatModel
    from beeai_framework.workflows.workflow import Workflow
    from beeai_framework.workflows.events import (
        WorkflowStartEvent,      # noqa: F401
        WorkflowSuccessEvent,    # noqa: F401
        WorkflowErrorEvent,      # noqa: F401
    )
except ImportError:
    raise ImportError("BeeAI Framework not found. Please install it using 'pip install beeai_framework'")

# --- CONFIGURATION ---
load_dotenv()
app = FastAPI(title="AutoSelf Orchestrator Server")

# Load Watsonx credentials from environment variables
WATSONX_API_KEY = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("PROJECT_ID")  # keep original env var name used by your codebase
WATSONX_API_URL = os.getenv("WATSONX_URL")    # keep original env var name used by your codebase

if not all([WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_API_URL]):
    raise ValueError("Watsonx credentials not found. Please set WATSONX_API_KEY, PROJECT_ID, and WATSONX_URL in your .env file or environment.")

# --- Directories for artifact serving ---
RESULTS_DIR = Path(os.environ.get("AUTOSELF_RESULTS_DIR", "results")).resolve()
FIGS_DIR = Path(os.environ.get("AUTOSELF_FIGS_DIR", "figs")).resolve()
ALLOWED_ROOTS = [RESULTS_DIR, FIGS_DIR]
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
FIGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Pydantic Schemas for API ---
class VerificationResult(BaseModel):
    is_safe: bool = Field(..., description="True if the task is safe to proceed.")
    risk_description: str = Field(..., description="Description of any detected risk.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score.")

class CorrectionSuggestion(BaseModel):
    suggested_action: str = Field(..., description="One of: 'retry', 'abort', 'run_diagnostics', 'reassign', 'reorder'.")
    reasoning: str = Field(..., description="Justification for the suggestion.")

class OrchestratorState(BaseModel):
    current_task: Dict[str, Any]
    verification_result: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    correction_action: Optional[str] = None

class MissionStatusResponse(BaseModel):
    mission_log: List[str]
    world_state: Dict[str, Any]
    active_hazard: Optional[Dict[str, Any]]
    agent_status: Dict[str, str]
    mission_progress: Dict[str, int]
    llm_api_latency: float
    is_mission_running: bool

class FailureInjectionRequest(BaseModel):
    task_name: str
    is_permanent: bool = False

# --- Core Simulation Classes (Refactored for Server) ---
class WorldState:
    """ Manages the entire simulation state, acting as a singleton. """

    def __init__(self):
        self.reset()

    def reset(self):
        """ Resets the world to its initial state for a new mission. """
        self.state: Dict[str, Any] = {
            "excavation_done": False,
            "compaction_done": False,
            "foundation_printed": False,
            "shell_printed": False,
            "inflatable_transported": False,
            "inflatable_deployed": False,
            "habitat_outfitted": False,
            "site_power_level": 100.0,
            "ambient_temperature_celsius": -50,
        }
        # MODIFICATION: Store the full hazard object for richer context
        self.active_hazard: Optional[Dict[str, Any]] = None
        self.log: List[str] = []
        self.injected_failures: Dict[str, Dict[str, bool]] = {}
        self.last_llm_latency: float = 0.0
        self.mission_running: bool = False
        self.add_log("World state initialized and ready for mission.")

    def update(self, key: str, value: Any):
        if key in self.state:
            self.state[key] = value
            self.add_log(f"STATE UPDATE: {key} set to {value}")

    def add_log(self, message: str):
        ts = time.strftime("%H:%M:%S", time.localtime())
        self.log.append(f"[{ts}] {message}")

    def get_state_description(self) -> str:
        # Include active hazard in the state description for the LLM
        full_state = {
            "world_conditions": self.state,
            "active_hazard": self.active_hazard or "none"
        }
        return json.dumps(full_state, indent=2)

class RoboticAgent:
    def __init__(self, name: str, capabilities: List[str]):
        self.name = name
        self.capabilities = capabilities
        self.status = "idle"  # idle | executing | failed

    def can_perform(self, capability: str) -> bool:
        return capability in self.capabilities

async def _close_model(m):
    """Close a model client safely (prevents aiohttp warnings)."""
    try:
        if hasattr(m, "aclose") and callable(getattr(m, "aclose")):
            await m.aclose()
        elif hasattr(m, "close") and callable(getattr(m, "close")):
            m.close()
    except Exception:
        # Best-effort; don't crash during shutdown
        pass

class AutoSelfOrchestrator_old:
    """Core orchestrator with hazard-aware verification, dynamic task reordering, and LLM fallbacks."""

    def __init__(self, agents: List[RoboticAgent], mission_plan: List[Dict], world_state: WorldState):
        self.agents = agents
        self.mission_plan = mission_plan
        self.world_state = world_state
        self.task_retries = 0
        self.max_retries = 2

        # IMPORTANT FIX:
        # Avoid ChatModel.from_name(..., settings=...) which double-passes `settings`.
        # Instantiate the adapter directly and pass settings here (or rely on env vars).
        try:
            self.llm = WatsonxChatModel(
                "meta-llama/llama-3-70b-instruct",
                settings={
                    "api_key": WATSONX_API_KEY,
                    "project_id": WATSONX_PROJECT_ID,
                    "api_base": WATSONX_API_URL,
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize LLM: {e}")

        self.workflow = Workflow(schema=OrchestratorState)
        self._register_steps()

    async def aclose(self):
        await _close_model(self.llm)

    def _register_steps(self):
        self.workflow.add_step("verify", self._step_verify)
        self.workflow.add_step("execute", self._step_execute)
        self.workflow.add_step("correct", self._step_correct)
        self.workflow.add_step("end_cycle", self._step_end_cycle)
        self.workflow.set_start("verify")

    # NEW HELPER METHOD: Finds a valid, safe, and dependency-cleared alternative task
    def _find_alternative_task(self) -> Optional[Dict[str, Any]]:
        """Finds the next available, safe, and non-dependent task during a hazard."""
        if not self.world_state.active_hazard:
            return None

        affected_caps = self.world_state.active_hazard.get("affected_capabilities", [])

        for task in self.mission_plan:
            # Check 1: Is task already done?
            if self.world_state.state.get(task["output_state"]):
                continue

            # Check 2: Is task's capability affected by the hazard?
            if task["capability"] in affected_caps:
                continue

            # Check 3: Are all its dependencies met?
            dependencies_met = all(
                self.world_state.state.get(dep) for dep in task["dependencies"]
            )
            if dependencies_met:
                return task  # This is a valid alternative

        return None  # No suitable alternative found

    # MODIFIED VERIFICATION STEP: Implements dynamic task swapping
    async def _step_verify(self, state: OrchestratorState) -> str:
        self.world_state.add_log(f"--- Verifying Task: {state.current_task['name']} ---")

        if self.world_state.active_hazard:
            current_task_capability = state.current_task["capability"]
            affected_caps = self.world_state.active_hazard.get("affected_capabilities", [])

            if current_task_capability in affected_caps:
                self.world_state.add_log(
                    f"🌪️ Hazard '{self.world_state.active_hazard['name']}' affects current task '{state.current_task['name']}'. Looking for alternatives."
                )
                alternative_task = self._find_alternative_task()

                if alternative_task:
                    self.world_state.add_log(f"✅ Found safe alternative: '{alternative_task['name']}'. Swapping.")
                    state.current_task = alternative_task
                else:
                    self.world_state.add_log("🚨 No safe alternatives available. Pausing operations.")
                    # End the cycle; main loop will wait and retry.
                    state.failure_reason = "paused_by_hazard"
                    return "__end__"

        is_safe, risk = await self.run_verification_analysis(state.current_task)
        if not is_safe:
            self.world_state.add_log(f"🚨 LLM verification failed: {risk}. Halting task.")
            state.failure_reason = f"llm_safety_check_failed: {risk}"
            return "__end__"

        return "execute"

    async def _step_execute(self, state: OrchestratorState) -> str:
        task = state.current_task
        agent = self.find_available_agent(task["capability"])
        if not agent:
            self.world_state.add_log(f"No idle agent for '{task['capability']}'. Retrying...")
            await asyncio.sleep(1)
            return "__self__"

        self.world_state.add_log(f"[Exec] Assigning '{task['name']}' to {agent.name}.")
        agent.status = "executing"

        power_draw = float(task.get("duration", 1)) * 3.5
        self.world_state.update("site_power_level", round(self.world_state.state["site_power_level"] - power_draw, 2))
        
        # NOTE: Using real duration for the simulation, not divided by 10
        await asyncio.sleep(task.get("duration", 1))

        succeeded = True
        if task["name"] in self.world_state.injected_failures:
            info = self.world_state.injected_failures.pop(task["name"], {})
            succeeded = False
            state.failure_reason = f"Externally injected failure for '{task['name']}'"
            if info.get("is_permanent", False):
                self.world_state.injected_failures[task["name"]] = info

        agent.status = "idle"
        self.world_state.update("site_power_level", round(self.world_state.state["site_power_level"] + power_draw / 2.0, 2))

        if succeeded:
            self.world_state.update(task["output_state"], True)
            return "end_cycle"
        else:
            return "correct"

    async def _step_correct(self, state: OrchestratorState) -> str:
        # ... (This step remains largely the same) ...
        task = state.current_task
        reason = state.failure_reason or "Unknown failure"
        self.world_state.add_log(f"Task Failed: {task['name']}, Reason: {reason}")

        if self.task_retries < self.max_retries:
            self.task_retries += 1
            self.world_state.add_log(f"[Correct] Auto-retry {self.task_retries}/{self.max_retries} scheduled.")
            state.failure_reason = None
            return "execute"

        action = await self.run_correction_analysis(task, reason)
        state.correction_action = action
        if action == "retry":
            self.world_state.add_log("[Correct] AI suggested retrying the task.")
            state.failure_reason = None
            return "execute"
        else:
            self.world_state.add_log(f"[Correct] AI suggested '{action}'. Halting mission.")
            return "__end__"

    async def _step_end_cycle(self, state: OrchestratorState) -> str:
        if not state.failure_reason:
            self.world_state.add_log(f"✅ Task '{state.current_task['name']}' completed successfully.")
        return "__end__"

    async def run_correction_analysis(self, task: Dict, reason: str) -> str:
        self.world_state.add_log("Consulting AI for corrective action.")
        prompt = (
            f"A critical lunar task has failed. World State: {self.world_state.get_state_description()}. "
            f"Failed Task: '{task['name']}'. Reason: '{reason}'. "
            "Respond in JSON with a CorrectionSuggestion schema."
        )
        try:
            resp = await self.llm.create_structure(schema=CorrectionSuggestion, messages=[UserMessage(prompt)])
            cs = resp.object
            action = cs.get("suggested_action", "abort")
            self.world_state.add_log(f"AI Suggestion: '{action}', because: '{cs.get('reasoning', '')}'")
            return str(action)
        except Exception as e:
            # ENHANCED LOGGING
            self.world_state.add_log(f"AI correction analysis error of type {type(e).__name__}: {e}. Defaulting to 'abort'.")
            return "abort"

    async def run_verification_analysis(self, task: Dict) -> Tuple[bool, str]:
        self.world_state.add_log(f"Consulting AI on safety for: {task['name']}")
        prompt = (
            f"As a construction supervisor on the Moon, analyze the safety of this task: "
            f"World State: {self.world_state.get_state_description()}. "
            f"Task: '{task['name']}'. Respond in JSON with a VerificationResult schema."
        )
        start_time = time.time()
        try:
            resp = await self.llm.create_structure(schema=VerificationResult, messages=[UserMessage(prompt)])
            vr = resp.object
            is_safe = vr.get("is_safe", False)
            risk = vr.get("risk_description", "Unknown risk")
            self.world_state.add_log(f"AI Safety Verdict: is_safe={is_safe}, risk='{risk}'")
            return bool(is_safe), str(risk)
        except Exception as e:
            # ENHANCED LOGGING
            self.world_state.add_log(f"AI verification error of type {type(e).__name__}: {e}. Proceeding with caution.")
            return True, "LLM error; proceeding with caution"
        finally:
            self.world_state.last_llm_latency = time.time() - start_time
    
    # NEW HELPER: Manages the timer to end a hazard event
    async def end_hazard_after(self, duration: int):
        await asyncio.sleep(duration)
        if self.world_state.active_hazard:
            self.world_state.add_log(f"HAZARD CLEARED: {self.world_state.active_hazard['name']} has passed.")
            self.world_state.active_hazard = None

    # HEAVILY MODIFIED MISSION LOOP: Handles dynamic, dependency-based execution and hazards
    async def run_mission(self, hazard_scenarios: List[Dict]):
        self.world_state.mission_running = True
        self.world_state.add_log("🚀 MISSION STARTED 🚀")
        
        remaining_tasks = {task['name']: task for task in self.mission_plan}

        while remaining_tasks:
            if not self.world_state.mission_running:
                self.world_state.add_log("Mission aborted by external command.")
                break

            # --- Random Hazard Simulation ---
            if not self.world_state.active_hazard and random.random() < 0.2:  # 20% chance per cycle
                if hazard_scenarios:
                    scenario = random.choice(hazard_scenarios)
                    self.world_state.active_hazard = scenario
                    duration = random.randint(scenario["duration_seconds"]["min"], scenario["duration_seconds"]["max"])
                    self.world_state.add_log(f"HAZARD TRIGGERED: {scenario['name']} for {duration}s.")
                    asyncio.create_task(self.end_hazard_after(duration))

            # Find the next task whose dependencies are all met
            next_task_to_try = None
            sorted_tasks = sorted(remaining_tasks.values(), key=lambda t: len(t.get("dependencies", [])))
            for task in sorted_tasks:
                if all(self.world_state.state.get(dep) for dep in task["dependencies"]):
                    next_task_to_try = task
                    break
            
            if not next_task_to_try:
                if self.world_state.active_hazard:
                    self.world_state.add_log("Waiting for hazard to clear, no tasks can proceed.")
                else:
                    self.world_state.add_log("💥 DEADLOCK? No tasks with met dependencies. Halting.")
                    break
                await asyncio.sleep(1)
                continue

            self.task_retries = 0
            final_state = await self.run_task_cycle(next_task_to_try)

            if not final_state.failure_reason:
                # Successfully completed
                del remaining_tasks[next_task_to_try['name']]
            elif final_state.failure_reason != "paused_by_hazard":
                # A real failure occurred
                self.world_state.add_log(f"💥 MISSION HALTED. Unrecoverable failure during: {next_task_to_try['name']}.")
                break
            # If paused by hazard, just loop again

        if not remaining_tasks:
            self.world_state.add_log("🎉 MISSION COMPLETE! 🎉")

        self.world_state.mission_running = False

    def find_available_agent(self, capability: str) -> Optional[RoboticAgent]:
        for agent in self.agents:
            if agent.status == "idle" and agent.can_perform(capability):
                return agent
        return None

    async def run_task_cycle(self, task: Dict) -> OrchestratorState:
        initial_state = OrchestratorState(current_task=task)
        final_workflow_run = await self.workflow.run(initial_state)
        return final_workflow_run.result


class AutoSelfOrchestrator:
    """Core orchestrator with hazard-aware verification, dynamic task reordering, and LLM fallbacks."""

    def __init__(self, agents: List[RoboticAgent], mission_plan: List[Dict], world_state: WorldState):
        self.agents = agents
        self.mission_plan = mission_plan
        self.world_state = world_state
        self.task_retries = 0
        self.max_retries = 2

        # Initialize the LLM model (Watsonx) exactly as requested
        try:
            llm_settings = {
                "temperature": 0.1,
                "top_p":       0.9,
                "project_id":  WATSONX_PROJECT_ID,
                "api_key":     WATSONX_API_KEY,
                "api_base":    WATSONX_API_URL,
            }

            # Type annotated as ChatModel to keep the rest of the code unchanged
            self.llm: ChatModel = WatsonxChatModel(
                model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8",
                # model_id="meta-llama/llama-3-3-70b-instruct",
                settings=llm_settings,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize LLM: {e}")

        self.workflow = Workflow(schema=OrchestratorState)
        self._register_steps()

    async def aclose(self):
        """Close the underlying client/session to avoid unclosed connector warnings."""
        try:
            if hasattr(self.llm, "aclose") and callable(getattr(self.llm, "aclose")):
                await self.llm.aclose()
            elif hasattr(self.llm, "close") and callable(getattr(self.llm, "close")):
                self.llm.close()
        except Exception:
            # Best-effort close; do not raise during shutdown
            pass

    def _register_steps(self):
        self.workflow.add_step("verify", self._step_verify)
        self.workflow.add_step("execute", self._step_execute)
        self.workflow.add_step("correct", self._step_correct)
        self.workflow.add_step("end_cycle", self._step_end_cycle)
        self.workflow.set_start("verify")

    # NEW HELPER METHOD: Finds a valid, safe, and dependency-cleared alternative task
    def _find_alternative_task(self) -> Optional[Dict[str, Any]]:
        """Finds the next available, safe, and non-dependent task during a hazard."""
        if not self.world_state.active_hazard:
            return None

        affected_caps = self.world_state.active_hazard.get("affected_capabilities", [])

        for task in self.mission_plan:
            # Check 1: Is task already done?
            if self.world_state.state.get(task["output_state"]):
                continue

            # Check 2: Is task's capability affected by the hazard?
            if task["capability"] in affected_caps:
                continue

            # Check 3: Are all its dependencies met?
            dependencies_met = all(
                self.world_state.state.get(dep) for dep in task["dependencies"]
            )
            if dependencies_met:
                return task  # This is a valid alternative

        return None  # No suitable alternative found

    # MODIFIED VERIFICATION STEP: Implements dynamic task swapping
    async def _step_verify(self, state: OrchestratorState) -> str:
        self.world_state.add_log(f"--- Verifying Task: {state.current_task['name']} ---")

        if self.world_state.active_hazard:
            current_task_capability = state.current_task["capability"]
            affected_caps = self.world_state.active_hazard.get("affected_capabilities", [])

            if current_task_capability in affected_caps:
                self.world_state.add_log(
                    f"🌪️ Hazard '{self.world_state.active_hazard['name']}' affects current task '{state.current_task['name']}'. Looking for alternatives."
                )
                alternative_task = self._find_alternative_task()

                if alternative_task:
                    self.world_state.add_log(f"✅ Found safe alternative: '{alternative_task['name']}'. Swapping.")
                    state.current_task = alternative_task
                else:
                    self.world_state.add_log("🚨 No safe alternatives available. Pausing operations.")
                    # End the cycle; main loop will wait and retry.
                    state.failure_reason = "paused_by_hazard"
                    return "__end__"

        is_safe, risk = await self.run_verification_analysis(state.current_task)
        if not is_safe:
            self.world_state.add_log(f"🚨 LLM verification failed: {risk}. Halting task.")
            state.failure_reason = f"llm_safety_check_failed: {risk}"
            return "__end__"

        return "execute"

    async def _step_execute(self, state: OrchestratorState) -> str:
        task = state.current_task
        agent = self.find_available_agent(task["capability"])
        if not agent:
            self.world_state.add_log(f"No idle agent for '{task['capability']}'. Retrying...")
            await asyncio.sleep(1)
            return "__self__"

        self.world_state.add_log(f"[Exec] Assigning '{task['name']}' to {agent.name}.")
        agent.status = "executing"

        power_draw = float(task.get("duration", 1)) * 3.5
        self.world_state.update("site_power_level", round(self.world_state.state["site_power_level"] - power_draw, 2))
        
        # NOTE: Using real duration for the simulation, not divided by 10
        await asyncio.sleep(task.get("duration", 1))

        succeeded = True
        if task["name"] in self.world_state.injected_failures:
            info = self.world_state.injected_failures.pop(task["name"], {})
            succeeded = False
            state.failure_reason = f"Externally injected failure for '{task['name']}'"
            if info.get("is_permanent", False):
                self.world_state.injected_failures[task["name"]] = info

        agent.status = "idle"
        self.world_state.update("site_power_level", round(self.world_state.state["site_power_level"] + power_draw / 2.0, 2))

        if succeeded:
            self.world_state.update(task["output_state"], True)
            return "end_cycle"
        else:
            return "correct"

    async def _step_correct(self, state: OrchestratorState) -> str:
        # ... (This step remains largely the same) ...
        task = state.current_task
        reason = state.failure_reason or "Unknown failure"
        self.world_state.add_log(f"Task Failed: {task['name']}, Reason: {reason}")

        if self.task_retries < self.max_retries:
            self.task_retries += 1
            self.world_state.add_log(f"[Correct] Auto-retry {self.task_retries}/{self.max_retries} scheduled.")
            state.failure_reason = None
            return "execute"

        action = await self.run_correction_analysis(task, reason)
        state.correction_action = action
        if action == "retry":
            self.world_state.add_log("[Correct] AI suggested retrying the task.")
            state.failure_reason = None
            return "execute"
        else:
            self.world_state.add_log(f"[Correct] AI suggested '{action}'. Halting mission.")
            return "__end__"

    async def _step_end_cycle(self, state: OrchestratorState) -> str:
        if not state.failure_reason:
            self.world_state.add_log(f"✅ Task '{state.current_task['name']}' completed successfully.")
        return "__end__"

    async def run_correction_analysis(self, task: Dict, reason: str) -> str:
        self.world_state.add_log("Consulting AI for corrective action.")
        prompt = (
            f"A critical lunar task has failed. World State: {self.world_state.get_state_description()}. "
            f"Failed Task: '{task['name']}'. Reason: '{reason}'. "
            "Respond in JSON with a CorrectionSuggestion schema."
        )
        try:
            resp = await self.llm.create_structure(schema=CorrectionSuggestion, messages=[UserMessage(prompt)])
            cs = resp.object
            action = cs.get("suggested_action", "abort")
            self.world_state.add_log(f"AI Suggestion: '{action}', because: '{cs.get('reasoning', '')}'")
            return str(action)
        except Exception as e:
            # ENHANCED LOGGING
            self.world_state.add_log(f"AI correction analysis error of type {type(e).__name__}: {e}. Defaulting to 'abort'.")
            return "abort"

    async def run_verification_analysis(self, task: Dict) -> Tuple[bool, str]:
        self.world_state.add_log(f"Consulting AI on safety for: {task['name']}")
        prompt = (
            f"As a construction supervisor on the Moon, analyze the safety of this task: "
            f"World State: {self.world_state.get_state_description()}. "
            f"Task: '{task['name']}'. Respond in JSON with a VerificationResult schema."
        )
        start_time = time.time()
        try:
            resp = await self.llm.create_structure(schema=VerificationResult, messages=[UserMessage(prompt)])
            vr = resp.object
            is_safe = vr.get("is_safe", False)
            risk = vr.get("risk_description", "Unknown risk")
            self.world_state.add_log(f"AI Safety Verdict: is_safe={is_safe}, risk='{risk}'")
            return bool(is_safe), str(risk)
        except Exception as e:
            # ENHANCED LOGGING
            self.world_state.add_log(f"AI verification error of type {type(e).__name__}: {e}. Proceeding with caution.")
            return True, "LLM error; proceeding with caution"
        finally:
            self.world_state.last_llm_latency = time.time() - start_time
    
    # NEW HELPER: Manages the timer to end a hazard event
    async def end_hazard_after(self, duration: int):
        await asyncio.sleep(duration)
        if self.world_state.active_hazard:
            self.world_state.add_log(f"HAZARD CLEARED: {self.world_state.active_hazard['name']} has passed.")
            self.world_state.active_hazard = None

    # HEAVILY MODIFIED MISSION LOOP: Handles dynamic, dependency-based execution and hazards
    async def run_mission(self, hazard_scenarios: List[Dict]):
        self.world_state.mission_running = True
        self.world_state.add_log("🚀 MISSION STARTED 🚀")
        
        remaining_tasks = {task['name']: task for task in self.mission_plan}

        while remaining_tasks:
            if not self.world_state.mission_running:
                self.world_state.add_log("Mission aborted by external command.")
                break

            # --- Random Hazard Simulation ---
            if not self.world_state.active_hazard and random.random() < 0.2:  # 20% chance per cycle
                if hazard_scenarios:
                    scenario = random.choice(hazard_scenarios)
                    self.world_state.active_hazard = scenario
                    duration = random.randint(scenario["duration_seconds"]["min"], scenario["duration_seconds"]["max"])
                    self.world_state.add_log(f"HAZARD TRIGGERED: {scenario['name']} for {duration}s.")
                    asyncio.create_task(self.end_hazard_after(duration))

            # Find the next task whose dependencies are all met
            next_task_to_try = None
            sorted_tasks = sorted(remaining_tasks.values(), key=lambda t: len(t.get("dependencies", [])))
            for task in sorted_tasks:
                if all(self.world_state.state.get(dep) for dep in task["dependencies"]):
                    next_task_to_try = task
                    break
            
            if not next_task_to_try:
                if self.world_state.active_hazard:
                    self.world_state.add_log("Waiting for hazard to clear, no tasks can proceed.")
                else:
                    self.world_state.add_log("💥 DEADLOCK? No tasks with met dependencies. Halting.")
                    break
                await asyncio.sleep(1)
                continue

            self.task_retries = 0
            final_state = await self.run_task_cycle(next_task_to_try)

            if not final_state.failure_reason:
                # Successfully completed
                del remaining_tasks[next_task_to_try['name']]
            elif final_state.failure_reason != "paused_by_hazard":
                # A real failure occurred
                self.world_state.add_log(f"💥 MISSION HALTED. Unrecoverable failure during: {next_task_to_try['name']}.")
                break
            # If paused by hazard, just loop again

        if not remaining_tasks:
            self.world_state.add_log("🎉 MISSION COMPLETE! 🎉")

        self.world_state.mission_running = False

    def find_available_agent(self, capability: str) -> Optional[RoboticAgent]:
        for agent in self.agents:
            if agent.status == "idle" and agent.can_perform(capability):
                return agent
        return None

    async def run_task_cycle(self, task: Dict) -> OrchestratorState:
        initial_state = OrchestratorState(current_task=task)
        final_workflow_run = await self.workflow.run(initial_state)
        return final_workflow_run.result


# --- Global State Management ---
world_state = WorldState()
agents = [
    RoboticAgent("ExcavatorBot-01", ["excavation", "compaction"]),
    RoboticAgent("PrinterBot-7", ["printing"]),
    RoboticAgent("AssemblerBot-3", ["transport", "deployment", "outfitting"]),
]

# MODIFICATION: Mission plan now includes dependencies
mission_plan = [
    {"name": "Excavate Foundation Pit", "capability": "excavation", "duration": 2, "output_state": "excavation_done", "dependencies": []},
    {"name": "Compact and Level Ground", "capability": "compaction", "duration": 1, "output_state": "compaction_done", "dependencies": ["excavation_done"]},
    {"name": "Transport Inflatable Module", "capability": "transport", "duration": 2, "output_state": "inflatable_transported", "dependencies": ["excavation_done"]},
    {"name": "Print Foundation", "capability": "printing", "duration": 3, "output_state": "foundation_printed", "dependencies": ["compaction_done"]},
    {"name": "Print Habitat Shell", "capability": "printing", "duration": 4, "output_state": "shell_printed", "dependencies": ["foundation_printed"]},
    {"name": "Deploy Inflatable Module", "capability": "deployment", "duration": 1, "output_state": "inflatable_deployed", "dependencies": ["shell_printed", "inflatable_transported"]},
    {"name": "Outfit Habitat", "capability": "outfitting", "duration": 5, "output_state": "habitat_outfitted", "dependencies": ["inflatable_deployed"]},
]

# NEW: Load hazard scenarios from JSON file
try:
    with open("dust_scenarios.json", "r") as f:
        hazard_scenarios = json.load(f).get("dust_scenarios", [])
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Warning: Could not load dust_scenarios.json: {e}. Hazards will not be simulated.")
    hazard_scenarios = []

orchestrator: Optional[AutoSelfOrchestrator] = None

# --- Artifact utilities (unchanged) ---
def _is_allowed_path(p: Path) -> bool:
    try:
        pr = p.resolve(strict=False)
    except Exception:
        return False
    return any(str(pr).startswith(str(root)) for root in ALLOWED_ROOTS)

def _list_artifacts() -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    for root in ALLOWED_ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                stat = f.stat()
                artifacts.append({
                    "name": f.name, "path": str(f.relative_to(root)), "abs_path": str(f),
                    "root": root.name, "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "mime": mimetypes.guess_type(str(f))[0] or "application/octet-stream",
                })
    artifacts.sort(key=lambda x: x["modified"], reverse=True)
    return artifacts

# --- API Endpoint Definitions ---
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}

@app.get("/artifacts/list")
def artifacts_list():
    return _list_artifacts()

@app.get("/artifacts/file")
def artifacts_file(path: str = Query(...), root: str = Query("results")):
    root_path = RESULTS_DIR if root.lower() == "results" else FIGS_DIR
    abs_path = (root_path / path).resolve()
    if not _is_allowed_path(abs_path) or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=str(abs_path))

# MODIFICATION: Mission start now passes scenarios to the run loop
@app.post("/mission/start")
async def start_mission(background_tasks: BackgroundTasks):
    """Starts a new mission simulation, including random hazard events."""
    global orchestrator
    if world_state.mission_running:
        raise HTTPException(status_code=400, detail="Mission is already running.")

    world_state.reset()
    orchestrator = AutoSelfOrchestrator(agents, mission_plan, world_state)
    # Pass the loaded scenarios to the mission runner
    background_tasks.add_task(orchestrator.run_mission, hazard_scenarios=hazard_scenarios)
    return {"status": "Mission started with dynamic hazard simulation"}

@app.get("/mission/status", response_model=MissionStatusResponse)
async def get_mission_status():
    """Returns the current status of the mission, agents, and world state."""
    agent_status = {agent.name: agent.status for agent in agents}
    total_tasks = len(mission_plan)
    completed_tasks = sum(1 for task in mission_plan if world_state.state.get(task.get("output_state")))
    mission_progress = {"completed": completed_tasks, "total": total_tasks}

    return MissionStatusResponse(
        mission_log=world_state.log[-20:],
        world_state=world_state.state,
        active_hazard=world_state.active_hazard,
        agent_status=agent_status,
        mission_progress=mission_progress,
        llm_api_latency=world_state.last_llm_latency,
        is_mission_running=world_state.mission_running,
    )

@app.post("/inject/failure")
async def inject_failure(req: FailureInjectionRequest):
    """Injects a failure for a specific task."""
    world_state.injected_failures[req.task_name] = {"is_permanent": req.is_permanent}
    world_state.add_log(f"⚡ FAILURE INJECTED for task: {req.task_name}")
    return {"status": "Failure injected", "task": req.task_name}

@app.get("/")
def read_root():
    return {"message": "AutoSelf Orchestrator Server is running."}

# Clean shutdown: ensure we close the LLM client to avoid unclosed session warnings
@app.on_event("shutdown")
async def on_shutdown():
    global orchestrator
    if orchestrator is not None:
        await orchestrator.aclose()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8008))
    print(f"Starting AutoSelf Orchestrator Server on http://0.0.0.0:{port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
