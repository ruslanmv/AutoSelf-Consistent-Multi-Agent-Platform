# AutoSelf Consistent Multi-Agent System: Full Simulation Environment

This repository provides a comprehensive, code-based simulation of the **AutoSelf architecture**. It contains a series of Python scripts that demonstrate and validate how an AI-powered Orchestrator can manage a team of simulated robotic agents to complete a complex construction mission. The core of the project is showcasing the system's ability to handle unpredictable events by leveraging a Large Language Model (LLM) for intelligent decision-making, dynamic re-planning, and self-correction.

## The Importance of this Work

The preceding research paper introduced the theoretical framework for the **AutoSelf system**—a novel architecture designed to ensure reliability and safety in autonomous multi-robot operations. This simulation environment serves as the crucial proof-of-concept, bridging the gap between theory and practice.

This environment validates the AutoSelf framework by:

* **Implementing the Core Loop:** It provides a tangible implementation of the paper's central **Execution -> Verification -> Correction** cycle across increasingly complex scenarios.
* **Demonstrating Advanced AI Integration:** It shows how a modern LLM (IBM Watsonx) can be effectively integrated to act as the "reasoning engine" for the Orchestrator, performing structured analysis for dynamic re-planning in the face of multiple, simultaneous challenges.
* **Illustrating Robustness and Resilience:** By simulating random environmental hazards and resource conflicts, the experiments provide a powerful illustration of the resilience and self-awareness that the AutoSelf architecture brings to autonomous systems.

In short, if the paper answered *"What is the AutoSelf system?"*, this simulation answers *"How does the AutoSelf system perform when faced with realistic, unpredictable challenges?"*

---

## System Architecture

The simulation implements the core components of the AutoSelf architecture. The central **Orchestrator Agent** manages the entire process, interacting with robotic agents and support layers through the core logic cycle. The final experiment (`third_experiment.py`) is the most complete implementation of this architecture.

```mermaid
graph TD
    subgraph PlatformCore ["Platform Core"]
        Orchestrator{AutoSelf Orchestrator Agent <br/> w/ AI Core}
    end

    subgraph SimulationEnv ["Simulation Environment"]
        Hazard[Random Environmental Hazards]
        Conflict[Resource Contention]
    end

    Orchestrator -- Manages Mission In --> SimulationEnv

    subgraph CoreLogicCycle ["Core Logic Cycle"]
        direction LR
        VerificationAnalysis{Verification Analysis}
        Execution{Task Execution}
        CorrectionModule{Dynamic Re-Planning}

        Orchestrator -- Manages Cycle --> VerificationAnalysis
        VerificationAnalysis -- Plan is OK --> Execution
        VerificationAnalysis -- Issues Found --> CorrectionModule
        Execution -- Task Succeeded --> Orchestrator
        Execution -- Task Failed --> CorrectionModule
        CorrectionModule -- Creates New Plan --> VerificationAnalysis
    end

    subgraph VerificationDetails ["Verification Details"]
        AIReasoning{AI Reasoning Engine <br/> (LLM)}
    end

    VerificationAnalysis -- Consults --> AIReasoning
    CorrectionModule -- Consults --> AIReasoning

    subgraph RoboticAgents ["Robotic Agents Layer"]
        direction TB
        Agent1{Simulated Agent 1}
        Agent2{Simulated Agent 2}
        Agent3{Simulated Agent 3}
    end

    Orchestrator -- Dispatches Tasks --> Agent1
    Orchestrator -- Dispatches Tasks --> Agent2
    Orchestrator -- Dispatches Tasks --> Agent3

    subgraph SupportLayers ["Support Layers"]
        DataManagement{Data Management <br/> World State, Logs, Configs}
    end

    Orchestrator --> DataManagement
    VerificationAnalysis --> DataManagement
    Execution --> DataManagement

```

---

## Experiments Overview

The repository contains three experiments that progressively demonstrate the capabilities of the AutoSelf system.

### 1. `first_experiment.py` - Basic Hazard/Failure Response

* **Focus:** Validates the fundamental **Execution-Verification-Correction** loop.
* **Scenario:** A linear mission plan where a single, pre-programmed hazard (Dust Storm) or a mechanical failure (Nozzle Clog) is injected at a specific point.
* **Demonstrates:** The system's ability to pause, wait for conditions to clear, or execute a simple retry.

### 2. `second_experiment.py` - Resource Contention Benchmark

* **Focus:** Quantifies the efficiency gains of proactive verification.
* **Scenario:** A benchmark where multiple tasks have a probabilistic need for a single shared resource.
* **Demonstrates:** The AI-powered Orchestrator's ability to proactively identify and prevent resource conflicts, comparing its throughput to a naive baseline that suffers from frequent collisions.

### 3. `third_experiment.py` - Combined AI-Driven Simulation

* **Focus:** Tests the AI's ability to handle complex, simultaneous challenges.
* **Scenario:** The most advanced simulation. A full mission with task dependencies is executed in an environment where both random environmental hazards (from `dust_scenarios.json`) and probabilistic resource conflicts can occur at any time.
* **Demonstrates:** The full power of the AutoSelf system. The AI orchestrator dynamically re-plans the entire mission on the fly, finding safe alternative tasks to work around hazards while simultaneously resolving resource conflicts.

---

## How to Run the Experiments

This simulation is designed to be run from the command line using the provided Makefile.

### Prerequisites

* **Python 3.10+**
* **pip** for installing dependencies.
* A `.env` file containing your API credentials for IBM Watsonx:
* `WATSONX_API_KEY`
* `PROJECT_ID`
* `WATSONX_URL`



### Steps

1. **Clone the Repository:**
```bash
git clone <repository_url>
cd AutoSelf-Consistent-Multi-Agent-Platform

```


2. **Create and Populate `.env` file:**
Create a file named `.env` in the root of the project and add your credentials:
```bash
WATSONX_API_KEY="your_api_key"
PROJECT_ID="your_project_id"
WATSONX_URL="your_watsonx_url"

```


3. **Install Dependencies:**
```bash
pip install -r requirements.txt

```


4. **Run the Full Reproduction Suite:**
The simplest way to run all experiments and generate all result artifacts is to use the Makefile. This command will execute all three experiments, comparing the `autoself_ai` and `baseline` strategies.
```bash
make reproduce

```



---

## Understanding the Simulation Framework

The simulation is built around a few key Python classes and configuration files.

### Core Components

* **`WorldState`:** A class that manages the current state of the simulation environment, including task completion statuses and any active hazards.
* **`Task`:** Represents a single task from the mission plan, complete with its dependencies and a probabilistic need for a shared resource.
* **`AutoSelfOrchestrator`:** The implementation of the central orchestrator. In `third_experiment.py`, this class uses the LLM to make all its tactical decisions.

### Configuration Files

* **`configs/*.yml`:** These YAML files define the parameters for the orchestrator, the world (including the mission plan and agents), and the baseline models.
* **`seeds.yaml`:** Ensures that the random elements (resource needs, hazard triggers) are reproducible across runs.
* **`dust_scenarios.json`:** Contains the definitions for various environmental hazards that can be randomly triggered during the third experiment.

---

## Results and Analysis

After running the experiments, the following artifacts will be generated in the `results/` directory:

* `timeline_*.csv`: Provides a step-by-step log of mission progress for each scenario.
* `makespan.csv`: Records the total time (makespan) to complete the mission for each run.
* `conflicts.csv`: Logs the number of resource conflicts encountered by each strategy.
* `overhead.csv`: Details the computational overhead (in milliseconds) for the verification steps, including the time taken for LLM calls.

These CSV files provide the quantitative data needed to analyze the performance, efficiency, and reliability of the AI-driven AutoSelf orchestrator compared to the baseline.

