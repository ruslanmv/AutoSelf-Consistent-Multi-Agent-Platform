# AutoSelf Consistent Multi-Agent System: Simulation and Demonstration Platform

This repository provides a comprehensive platform for validating and demonstrating the **AutoSelf Consistent Multi-Agent System**. It contains two primary components:

1. A **Simulation Suite** of Python scripts (`first_experiment.py`, `second_experiment.py`) for rigorously testing the architecture's performance and resilience under various conditions.
2. An **Interactive Web Demo** that provides a real-time, visual interface for observing the AutoSelf orchestrator in action and injecting live events.

The core of the project is showcasing the system's ability to handle unpredictable events by leveraging a Large Language Model (LLM) for intelligent decision-making, dynamic re‑planning, and self‑correction.

---

## Why this matters

The accompanying paper introduces the theoretical framework for the AutoSelf system—a novel architecture designed to ensure reliability and safety in autonomous multi‑robot operations. This platform is the practical proof‑of‑concept.

It validates AutoSelf by:

* **Implementing the Core Loop** — a concrete **Execution → Verification → Correction (E–V–C)** cycle.
* **Demonstrating AI Integration** — the orchestrator consults IBM Watsonx for structured reasoning.
* **Illustrating Robustness** — hazards, failures, and contention scenarios are exercised end‑to‑end.

> If the paper answers *what* AutoSelf is, this repo shows *how* it behaves under realistic, unpredictable conditions.

---

## System Architecture

The simulation and demo both implement a central **Orchestrator Agent** that manages simulated robotic agents through the E–V–C cycle.

```mermaid
graph TD
    %% Style Definitions
    classDef client fill:#D6EAF8,stroke:#3498DB,stroke-width:2px,color:#2874A6
    classDef api fill:#D1F2EB,stroke:#1ABC9C,stroke-width:2px,color:#148F77
    classDef core fill:#FCF3CF,stroke:#F1C40F,stroke-width:2px,color:#B7950B
    classDef support fill:#EADCF8,stroke:#8E44AD,stroke-width:2px,color:#6C3483
    classDef external fill:#E5E7E9,stroke:#839192,stroke-width:2px,color:#616A6B

    %% Client Side
    User[👤 User]
    
    subgraph ClientSide ["Client Dashboard (Interactive Demo)"]
        direction LR
        DashboardUI(Interactive Dashboard)
        ControlPanel(Control Panel)
        LiveStatus(Live Status & Log Viewer)
        Plots(Real-Time Plots)
    end

    %% API Gateway
    APIEndpoints{REST API Endpoints}

    %% Backend Systems
    subgraph Backend ["Backend Logic (Server & Simulation Core)"]
        Orchestrator(AutoSelf Orchestrator Agent)
        
        subgraph CoreCycle ["Core Cycle"]
            direction LR
            Verification(Verification Analysis) -->|Plan is OK| Execution(Task Execution)
            Execution -->|Task Succeeded| Orchestrator
            Execution -->|Task Failed| Correction(Correction Module)
            Verification -->|Issues Found| Correction
            Correction -->|Updates Plan| Verification
        end
        
        DataManagement[(Data Management <br/> World State, Logs)]
        
        subgraph RoboticAgents ["Robotic Agents Layer"]
            direction TB
            ExcavatorBot[ExcavatorBot-01]
            PrinterBot[PrinterBot-7]
            AssemblerBot[AssemblerBot-3]
        end
    end

    %% External Services
    WatsonxLLM([IBM Watsonx LLM])

    %% --- Connections ---

    %% User to Client
    User -- Interacts with --> DashboardUI
    DashboardUI --> ControlPanel & LiveStatus & Plots

    %% Client to API
    ControlPanel -- POST /mission/start --> APIEndpoints
    LiveStatus & Plots -- GET /mission/status --> APIEndpoints
    
    %% API to Backend
    APIEndpoints -- Mission Status / Plot Data --> LiveStatus & Plots
    APIEndpoints -- Triggers Mission --> Orchestrator
    APIEndpoints -- Injects Failure --> Execution

    %% Backend Core Interactions
    Orchestrator -- Dispatches Tasks --> ExcavatorBot & PrinterBot & AssemblerBot
    ExcavatorBot & PrinterBot & AssemblerBot -- Reports Status --> Orchestrator
    Execution -- Issues Commands --> ExcavatorBot & PrinterBot & AssemblerBot
    
    %% Data and External Service Interactions
    Verification & Execution & Orchestrator -- Reads/Writes --> DataManagement
    Verification & Correction -- Consults --> WatsonxLLM

    %% Apply Styles to Nodes
    class User,DashboardUI,ControlPanel,LiveStatus,Plots client
    class APIEndpoints api
    class Orchestrator,Verification,Execution,Correction core
    class ExcavatorBot,PrinterBot,AssemblerBot,DataManagement support
    class WatsonxLLM external
```

---

## Repository structure

* **`server.py`** — FastAPI backend running the AutoSelf orchestrator and mission simulation.
* **`client.py`** — Flask dashboard (HTMX + Plotly) for live monitoring and controls.
* **`run.py`** — One‑shot runner that starts both backend and frontend (with optional ngrok in Colab).
* **`first_experiment.py`** — Hazards/Failures E–V–C workflow, emits timelines and summary CSVs.
* **`second_experiment.py`** — Resource contention benchmark with ablations and overhead metrics.
* **`configs/*.yml`** — Orchestrator/world/baseline knobs.
* **`seeds.yaml`** — Deterministic seed sets per experiment.
* **`results/`** — Standardized CSV outputs.
* **`figs/`** — Generated figures for the paper (git‑ignored).

---

## Quickstart (Demo)

### 1) Set API keys

In Google Colab, add these Secrets (🔑):

* `WATSONX_API_KEY`
* `PROJECT_ID` (Watsonx Project ID)
* `WATSONX_URL`
* `NGROK_AUTHTOKEN`

Or locally, create a `.env` file with the same keys.

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run the application

```bash
python run.py
```

![](assets/2025-06-12-00-48-11.png)

Running `run.py` starts both the **FastAPI** backend and the **Flask** frontend. In Colab it exposes public tunnels; locally it opens your browser.

![](assets/2025-06-12-00-50-00.png)

### Using the dashboard

* **Start Mission** — kicks off the lunar construction mission.
* **Inject Nozzle Clog** — forces a one‑shot failure on *Print Habitat Shell*; AutoSelf should retry and/or correct.
* **Toggle Dust Storm** — toggles `dust_storm_active` in `WorldState`; AutoSelf pauses or substitutes safe tasks and resumes.
* **Live Plots** — show agent states, mission progress, LLM latency, and site power.

![](assets/2025-06-12-00-51-14.png)

Supported actions:

* **⚡ Nozzle Clog (Mechanical Failure)** — simulates a 3D‑printer failure; triggers reactive correction.
* **🌪️ Dust Storm (Environmental Hazard)** — simulates a hazard; triggers proactive verification, substitution, or bounded backoff.

![](assets/2025-06-12-00-52-22.png)

---

## Quickstart (Experiments)

Run the fully scripted reproduction (both experiments, all seeds/p‑values):

```bash
make reproduce
```

This produces, at minimum:

* `results/makespan.csv`, `results/conflicts.csv`, `results/throughput.csv`, `results/overhead.csv`, `results/ablations.csv`
* `results/timeline_nominal.csv`, `results/timeline_hazard.csv`, `results/timeline_failure.csv`
* `figs/throughput_plot.pdf`, `figs/Nominal_Mission_timeline.png`, `figs/Dust_Storm_Hazard_timeline.png`, `figs/Nozzle_Clog_Failure_timeline.png`

---

## Notebook demo

**AutoSelf Consistent Multi‑Agent System: Single Demo** — [AutoSelf\_Consistent\_Multi\_Agent\_System.ipynb](AutoSelf_Consistent_Multi_Agent_System.ipynb)

This Colab‑ready notebook reproduces all reported artifacts (CSVs, figures, LaTeX macros) in a single place.

```mermaid
graph TD
    subgraph Platform Core
        Orchestrator{AutoSelf Orchestrator Agent}
    end

    subgraph Pre-Flight Check
        HealthCheck{System Health Check}
        MissionHalt{Mission Halted}
    end

    HealthCheck -- FAILED --> MissionHalt
    HealthCheck -- PASSED --> VerificationAnalysis

    subgraph Core Logic Cycle
        direction LR
        VerificationAnalysis{Verification Analysis}
        Execution{Task Execution}
        CorrectionModule{Correction Module}

        Orchestrator -- Manages Cycle --> VerificationAnalysis
        VerificationAnalysis -- Plan is OK --> Execution
        VerificationAnalysis -- Issues Found --> CorrectionModule
        Execution -- Task Succeeded --> Orchestrator
        Execution -- Task Failed --> CorrectionModule
        CorrectionModule -- Updates Plan for Retry --> Execution
        CorrectionModule -- Updates Plan --> Orchestrator
    end

    subgraph Verification Details
        AIReasoning{AI Reasoning & Neurosymbolic Layer}
    end

    VerificationAnalysis --> AIReasoning
    CorrectionModule --> AIReasoning

    subgraph Robotic Agents Layer
        direction TB
        Excavator{Robotic Agent 1 - ExcavatorBot-01}
        Printer{Robotic Agent 2 - PrinterBot-7}
        Assembler{Robotic Agent 3 - AssemblerBot-3}
    end

    Orchestrator -- Dispatches Tasks --> Excavator
    Orchestrator -- Dispatches Tasks --> Printer
    Orchestrator -- Dispatches Tasks --> Assembler

    Execution --> Excavator
    Execution --> Printer
    Execution --> Assembler

    Excavator -- Reports Status/Results --> Orchestrator
    Printer -- Reports Status/Results --> Orchestrator
    Assembler -- Reports Status/Results --> Orchestrator

    subgraph Support Layers
        DataManagement{Data Management - World State, Logs, Knowledge}
    end

    Orchestrator --> DataManagement
    VerificationAnalysis --> DataManagement
    Execution --> DataManagement
```

For more information, see [`demo/README.md`](demo/README.md).
