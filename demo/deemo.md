Of course. Here is the text from the Canvas, formatted in markdown for you to copy.

Markdown

# AutoSelf: An AI-Powered Orchestrator for Autonomous Systems

This repository contains the complete simulation suite and interactive demonstration platform for the **AutoSelf** system, as detailed in our accompanying research paper. It provides the tools to validate, explore, and understand our architecture for resilient, efficient, and intelligent multi-agent orchestration.

The platform is designed to prove the effectiveness of AutoSelf's core **Execution → Verification → Correction (E-V-C)** cycle, which is progressively enhanced with AI-driven decision-making to handle complex, unpredictable environments.

## The Research: A Three-Experiment Validation

Our research validates the AutoSelf system through a series of three experiments, each building upon the last to test a critical aspect of autonomous operation. This repository allows you to reproduce the results of all three.

1.  **Experiment 1: Resilience to Physical Hazards & Failures**
    * **Goal:** Test the system's fundamental reactivity and safety.
    * **Challenge:** The system must handle unexpected physical events like equipment failures (e.g., a nozzle clog) and environmental hazards (e.g., a dust storm).

2.  **Experiment 2: Efficiency Under Resource Contention**
    * **Goal:** Test the system's ability to proactively optimize scheduling.
    * **Challenge:** The system uses an LLM to predict and avoid conflicts over shared, exclusive resources, preventing wasted cycles and maximizing throughput.

3.  **Experiment 3: Holistic AI-Driven Decision-Making**
    * **Goal:** Test the system's ability to make complex, holistic decisions as a central AI director.
    * **Challenge:** The system must simultaneously manage both physical hazards and resource contention, using the LLM to synthesize all available data and generate an optimal action plan for each cycle.

> If the paper answers *what* AutoSelf is, this repository shows *how* it behaves under a graduated series of realistic, unpredictable conditions.

## System Architecture

The platform implements a central **Orchestrator Agent** that manages a team of simulated robotic agents. The orchestrator uses an LLM (IBM Watsonx) to inform its E-V-C cycle, making decisions about safety, scheduling, and recovery.

```mermaid
graph TD
    %% Style Definitions for different node types
    classDef client fill:#D6EAF8,stroke:#3498DB,stroke-width:2px,color:#2874A6
    classDef api fill:#D1F2EB,stroke:#1ABC9C,stroke-width:2px,color:#148F77
    classDef core fill:#FCF3CF,stroke:#F1C40F,stroke-width:2px,color:#B7950B
    classDef support fill:#EADCF8,stroke:#8E44AD,stroke-width:2px,color:#6C3483
    classDef external fill:#E5E7E9,stroke:#839192,stroke-width:2px,color:#616A6B

    %% Client Side
    User[👤 User]
    
    subgraph Client Dashboard (Interactive Demo)
        direction LR
        DashboardUI(Interactive Dashboard)
        ControlPanel(Control Panel)
        LiveStatus(Live Status & Log Viewer)
        Plots(Real-Time Plots)
    end

    %% API Gateway
    APIEndpoints{REST API Endpoints}

    %% Backend Systems
    subgraph Backend Logic (Server & Simulation Core)
        Orchestrator(AutoSelf Orchestrator Agent)
        subgraph Core Cycle
            direction LR
            Verification(Verification Analysis) -->|Plan is OK| Execution(Task Execution)
            Execution -->|Task Succeeded| Orchestrator
            Execution -->|Task Failed| Correction(Correction Module)
            Verification -->|Issues Found| Correction
            Correction -->|Updates Plan| Verification
        end
        DataManagement[(Data Management <br/> World State, Logs)]
        
        subgraph Robotic Agents Layer
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
Repository Structure
server.py — FastAPI backend running the AutoSelf orchestrator and mission simulation.

client.py — Flask dashboard (HTMX + Plotly) for live monitoring and controls.

first_experiment.py, second_experiment.py, third_experiment.py — Scripts to run the quantitative experiments.

paper_artifacts_exp3.py — Script to generate plots and reports from experiment data.

configs/*.yml — Configuration for the orchestrator, world, and baselines.

seeds.yaml — Deterministic seed sets per experiment for reproducibility.

results/ — Standardized CSV outputs from the experiments.

figs/ — Generated figures for the paper (git-ignored).

Quickstart: Interactive Live Demo
The interactive demo provides a real-time visualization of Experiment 1, allowing you to observe the system's resilience and reactivity firsthand.

1) Set API keys
In Google Colab, add these Secrets (🔑):

WATSONX_API_KEY

PROJECT_ID (Watsonx Project ID)

WATSONX_URL

NGROK_AUTHTOKEN

Or locally, create a .env file with the same keys.

2) Install dependencies
Bash

pip install -r requirements.txt
3) Run the application
Bash

python server.py &
python client.py
Navigate to the URL provided by the Flask client to open the dashboard.

Using the dashboard
Start Mission — Kicks off the simulated construction mission.

Inject Nozzle Clog — Forces a failure on the "Print Habitat Shell" task. Observe how AutoSelf detects the failure and initiates a correction.

Toggle Dust Storm — Activates an environmental hazard. Observe how AutoSelf pauses affected tasks or intelligently substitutes a safe alternative.

Live Plots — Monitor agent states, overall mission progress, AI health (latency), and site power in real-time.

Quickstart: Reproducing the Experiments
To reproduce the quantitative results from all three experiments described in the paper, run the simulation scripts directly.

Run a specific experiment:
Bash

# Run Experiment 1 (Resilience)
python first_experiment.py

# Run Experiment 2 (Efficiency)
python second_experiment.py

# Run Experiment 3 (Holistic AI)
python third_experiment.py
Generate all plots and reports from the data:
After running the experiments, the results/ directory will be populated with CSV files. Use the artifacts script to generate the final plots.

Bash

python paper_artifacts_exp3.py
This command will generate, at minimum:

All summary CSV files in results/.

All plots (.pdf and .svg) for the paper in manuscript_results/.

Notebook Demo
AutoSelf Consistent Multi‑Agent System: Single Demo — AutoSelf_Consistent_Multi_Agent_System.ipynb

This Colab-ready notebook provides a guided walkthrough and reproduces all reported artifacts (CSVs, figures, LaTeX macros) in a single, self-contained environment.

Code snippet

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






please also update this experiments.md





in the chat print



madrown





AutoSelf Consistent Multi-Agent System: Full Simulation Environment

This repository provides a comprehensive, code-based simulation of the AutoSelf architecture. It contains a series of Python scripts that demonstrate and validate how an AI-powered Orchestrator can manage a team of simulated robotic agents to complete a complex construction mission. The core of the project is showcasing the system's ability to handle unpredictable events by leveraging a Large Language Model (LLM) for intelligent decision-making, dynamic re-planning, and self-correction.



The Importance of this Work

The preceding research paper introduced the theoretical framework for the AutoSelf system—a novel architecture designed to ensure reliability and safety in autonomous multi-robot operations. This simulation environment serves as the crucial proof-of-concept, bridging the gap between theory and practice.



This environment validates the AutoSelf framework by:



Implementing the Core Loop: It provides a tangible implementation of the paper's central Execution -> Verification -> Correction cycle across increasingly complex scenarios.



Demonstrating Advanced AI Integration: It shows how a modern LLM (IBM Watsonx) can be effectively integrated to act as the "reasoning engine" for the Orchestrator, performing structured analysis for dynamic re-planning in the face of multiple, simultaneous challenges.



Illustrating Robustness and Resilience: By simulating random environmental hazards and resource conflicts, the experiments provide a powerful illustration of the resilience and self-awareness that the AutoSelf architecture brings to autonomous systems.



In short, if the paper answered "What is the AutoSelf system?", this simulation answers "How does the AutoSelf system perform when faced with realistic, unpredictable challenges?"



System Architecture

The simulation implements the core components of the AutoSelf architecture. The central Orchestrator Agent manages the entire process, interacting with robotic agents and support layers through the core logic cycle. The final experiment (third_experiment.py) is the most complete implementation of this architecture.



graph TD

subgraph Platform Core

Orchestrator{AutoSelf Orchestrator Agent w/ AI Core}

end



subgraph Simulation Environment

Hazard[Random Environmental Hazards]

Conflict[Resource Contention]

end



Orchestrator -- Manages Mission In --> Simulation Environment



subgraph Core Logic Cycle

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



subgraph Verification Details

AIReasoning{AI Reasoning Engine (LLM)}

end



VerificationAnalysis -- Consults --> AIReasoning

CorrectionModule -- Consults --> AIReasoning



subgraph Robotic Agents Layer

direction TB

Agent1{Simulated Agent 1}

Agent2{Simulated Agent 2}

Agent3{Simulated Agent 3}

end



Orchestrator -- Dispatches Tasks --> Agent1

Orchestrator -- Dispatches Tasks --> Agent2

Orchestrator -- Dispatches Tasks --> Agent3



subgraph Support Layers

DataManagement{Data Management - World State, Logs, Configs}

end



Orchestrator --> DataManagement

VerificationAnalysis --> DataManagement

Execution --> DataManagement



Experiments Overview

The repository contains three experiments that progressively demonstrate the capabilities of the AutoSelf system.



first_experiment.py - Basic Hazard/Failure Response



Focus: Validates the fundamental Execution-Verification-Correction loop.



Scenario: A linear mission plan where a single, pre-programmed hazard (Dust Storm) or a mechanical failure (Nozzle Clog) is injected at a specific point.



Demonstrates: The system's ability to pause, wait for conditions to clear, or execute a simple retry.



second_experiment.py - Resource Contention Benchmark



Focus: Quantifies the efficiency gains of proactive verification.



Scenario: A benchmark where multiple tasks have a probabilistic need for a single shared resource.



Demonstrates: The AI-powered Orchestrator's ability to proactively identify and prevent resource conflicts, comparing its throughput to a naive baseline that suffers from frequent collisions.



third_experiment.py - Combined AI-Driven Simulation



Focus: Tests the AI's ability to handle complex, simultaneous challenges.



Scenario: The most advanced simulation. A full mission with task dependencies is executed in an environment where both random environmental hazards (from dust_scenarios.json) and probabilistic resource conflicts can occur at any time.



Demonstrates: The full power of the AutoSelf system. The AI orchestrator dynamically re-plans the entire mission on the fly, finding safe alternative tasks to work around hazards while simultaneously resolving resource conflicts.



How to Run the Experiments

This simulation is designed to be run from the command line using the provided Makefile.



Prerequisites

Python 3.10+



pip for installing dependencies.



A .env file containing your API credentials for IBM Watsonx:



WATSONX_API_KEY



PROJECT_ID



WATSONX_URL



Steps

Clone the Repository:



git clone <repository_url>

cd AutoSelf-Consistent-Multi-Agent-Platform



Create and Populate .env file:

Create a file named .env in the root of the project and add your credentials:



WATSONX_API_KEY="your_api_key"

PROJECT_ID="your_project_id"

WATSONX_URL="your_watsonx_url"



Install Dependencies:



pip install -r requirements.txt



Run the Full Reproduction Suite:

The simplest way to run all experiments and generate all result artifacts is to use the Makefile. This command will execute all three experiments, comparing the autoself_ai and baseline strategies.



make reproduce



Understanding the Simulation Framework

The simulation is built around a few key Python classes and configuration files.



Core Components:



WorldState: A class that manages the current state of the simulation environment, including task completion statuses and any active hazards.



Task: Represents a single task from the mission plan, complete with its dependencies and a probabilistic need for a shared resource.



AutoSelfOrchestrator: The implementation of the central orchestrator. In third_experiment.py, this class uses the LLM to make all its tactical decisions.



Configuration Files:



configs/*.yml: These YAML files define the parameters for the orchestrator, the world (including the mission plan and agents), and the baseline models.



seeds.yaml: Ensures that the random elements (resource needs, hazard triggers) are reproducible across runs.



dust_scenarios.json: Contains the definitions for various environmental hazards that can be randomly triggered during the third experiment.



Results and Analysis

After running the experiments, the following artifacts will be generated in the results/ directory:



timeline_*.csv: Provides a step-by-step log of mission progress for each scenario.



makespan.csv: Records the total time (makespan) to complete the mission for each run.



conflicts.csv: Logs the number of resource conflicts encountered by each strategy.



overhead.csv: Details the computational overhead (in milliseconds) for the verification steps, including the time taken for LLM calls.



These CSV files provide the quantitative data needed to analyze the performance, efficiency, and reliability of the AI-driven AutoSelf orchestrator compared to the baseline.




Show thinking
Of course. I will update the experiments.md file with the detailed documentation you provided. Here is the content in markdown format for you to copy.

Markdown

# AutoSelf Consistent Multi-Agent System: Full Simulation Environment

This repository provides a comprehensive, code-based simulation of the AutoSelf architecture. It contains a series of Python scripts that demonstrate and validate how an AI-powered Orchestrator can manage a team of simulated robotic agents to complete a complex construction mission. The core of the project is showcasing the system's ability to handle unpredictable events by leveraging a Large Language Model (LLM) for intelligent decision-making, dynamic re-planning, and self-correction.

## The Importance of this Work

The preceding research paper introduced the theoretical framework for the AutoSelf system—a novel architecture designed to ensure reliability and safety in autonomous multi-robot operations. This simulation environment serves as the crucial proof-of-concept, bridging the gap between theory and practice.

This environment validates the AutoSelf framework by:

* **Implementing the Core Loop:** It provides a tangible implementation of the paper's central **Execution -> Verification -> Correction** cycle across increasingly complex scenarios.
* **Demonstrating Advanced AI Integration:** It shows how a modern LLM (IBM Watsonx) can be effectively integrated to act as the "reasoning engine" for the Orchestrator, performing structured analysis for dynamic re-planning in the face of multiple, simultaneous challenges.
* **Illustrating Robustness and Resilience:** By simulating random environmental hazards and resource conflicts, the experiments provide a powerful illustration of the resilience and self-awareness that the AutoSelf architecture brings to autonomous systems.

In short, if the paper answered "What is the AutoSelf system?", this simulation answers "How does the AutoSelf system perform when faced with realistic, unpredictable challenges?"

## System Architecture

The simulation implements the core components of the AutoSelf architecture. The central Orchestrator Agent manages the entire process, interacting with robotic agents and support layers through the core logic cycle. The final experiment (`third_experiment.py`) is the most complete implementation of this architecture.

```mermaid
graph TD
    subgraph Platform Core
        Orchestrator{AutoSelf Orchestrator Agent w/ AI Core}
    end

    subgraph Simulation Environment
        Hazard[Random Environmental Hazards]
        Conflict[Resource Contention]
    end

    Orchestrator -- Manages Mission In --> Simulation Environment

    subgraph Core Logic Cycle
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

    subgraph Verification Details
        AIReasoning{AI Reasoning Engine (LLM)}
    end

    VerificationAnalysis -- Consults --> AIReasoning
    CorrectionModule -- Consults --> AIReasoning

    subgraph Robotic Agents Layer
        direction TB
        Agent1{Simulated Agent 1}
        Agent2{Simulated Agent 2}
        Agent3{Simulated Agent 3}
    end

    Orchestrator -- Dispatches Tasks --> Agent1
    Orchestrator -- Dispatches Tasks --> Agent2
    Orchestrator -- Dispatches Tasks --> Agent3

    subgraph Support Layers
        DataManagement{Data Management - World State, Logs, Configs}
    end

    Orchestrator --> DataManagement
    VerificationAnalysis --> DataManagement
    Execution --> DataManagement
Experiments Overview
The repository contains three experiments that progressively demonstrate the capabilities of the AutoSelf system.

first_experiment.py - Basic Hazard/Failure Response
Focus: Validates the fundamental Execution-Verification-Correction loop.

Scenario: A linear mission plan where a single, pre-programmed hazard (Dust Storm) or a mechanical failure (Nozzle Clog) is injected at a specific point.

Demonstrates: The system's ability to pause, wait for conditions to clear, or execute a simple retry.

second_experiment.py - Resource Contention Benchmark
Focus: Quantifies the efficiency gains of proactive verification.

Scenario: A benchmark where multiple tasks have a probabilistic need for a single shared resource.

Demonstrates: The AI-powered Orchestrator's ability to proactively identify and prevent resource conflicts, comparing its throughput to a naive baseline that suffers from frequent collisions.

third_experiment.py - Combined AI-Driven Simulation
Focus: Tests the AI's ability to handle complex, simultaneous challenges.

Scenario: The most advanced simulation. A full mission with task dependencies is executed in an environment where both random environmental hazards (from dust_scenarios.json) and probabilistic resource conflicts can occur at any time.

Demonstrates: The full power of the AutoSelf system. The AI orchestrator dynamically re-plans the entire mission on the fly, finding safe alternative tasks to work around hazards while simultaneously resolving resource conflicts.

How to Run the Experiments
This simulation is designed to be run from the command line using the provided Makefile.

Prerequisites
Python 3.10+

pip for installing dependencies.

A .env file containing your API credentials for IBM Watsonx:

WATSONX_API_KEY

PROJECT_ID

WATSONX_URL

Steps
Clone the Repository:

Bash

git clone <repository_url>
cd AutoSelf-Consistent-Multi-Agent-Platform
Create and Populate .env file:
Create a file named .env in the root of the project and add your credentials:

WATSONX_API_KEY="your_api_key"
PROJECT_ID="your_project_id"
WATSONX_URL="your_watsonx_url"
Install Dependencies:

Bash

pip install -r requirements.txt
Run the Full Reproduction Suite:
The simplest way to run all experiments and generate all result artifacts is to use the Makefile. This command will execute all three experiments, comparing the autoself_ai and baseline strategies.

Bash

make reproduce
Understanding the Simulation Framework
The simulation is built around a few key Python classes and configuration files.

Core Components:
WorldState: A class that manages the current state of the simulation environment, including task completion statuses and any active hazards.

Task: Represents a single task from the mission plan, complete with its dependencies and a probabilistic need for a shared resource.

AutoSelfOrchestrator: The implementation of the central orchestrator. In third_experiment.py, this class uses the LLM to make all its tactical decisions.

Configuration Files:
configs/*.yml: These YAML files define the parameters for the orchestrator, the world (including the mission plan and agents), and the baseline models.

seeds.yaml: Ensures that the random elements (resource needs, hazard triggers) are reproducible across runs.

dust_scenarios.json: Contains the definitions for various environmental hazards that can be randomly triggered during the third experiment.

Results and Analysis
After running the experiments, the following artifacts will be generated in the results/ directory:

timeline_*.csv: Provides a step-by-step log of mission progress for each scenario.

makespan.csv: Records the total time (makespan) to complete the mission for each run.

conflicts.csv: Logs the number of resource conflicts encountered by each strategy.

overhead.csv: Details the computational overhead (in milliseconds) for the verification steps, including the time taken for LLM calls.

These CSV files provide the quantitative data needed to analyze the performance, efficiency, and reliability of the AI-driven AutoSelf orchestrator compared to the baseline.



http://googleusercontent.com/immersive_entry_chip/0