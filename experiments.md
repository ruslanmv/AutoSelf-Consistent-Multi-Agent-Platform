# Understanding the AutoSelf System: A Guide to the Experiments

## Overall Goal

The primary goal of this research is to design, implement, and validate **AutoSelf**, an intelligent orchestration system for autonomous multi-robot construction in unstructured environments like the Moon or Mars. Such a system must be resilient, efficient, and capable of making complex decisions without human intervention.

To test these capabilities, we designed a series of three experiments of progressively increasing complexity. Each experiment isolates and evaluates a critical aspect of the system's performance, building a comprehensive case for its effectiveness.

1.  **Experiment 1** tests fundamental **reactivity and resilience** to physical-world problems.
2.  **Experiment 2** tests **proactive optimization and efficiency** in scheduling.
3.  **Experiment 3** serves as a final exam, testing **holistic, AI-driven decision-making** in a complex, dynamic environment where both types of challenges occur simultaneously.

## Experiment 1: Resilience to Physical Hazards and Failures

### Goal

To prove that the AutoSelf system's core **Execution-Verification-Correction (E-V-C)** loop is fundamentally robust. The experiment is designed to answer the question: Can the system safely and efficiently react to unexpected physical problems in the environment and within its own hardware?

### What The Code Does

This experiment simulates a multi-step robotic construction mission with a defined sequence of tasks (e.g., excavate, print foundation, print shell). The simulation world has a physical state, including environmental conditions and the operational status of the robots.

To test the system's resilience, we inject two specific problems:

1.  **Environmental Hazard:** A **dust storm** is introduced mid-mission. This hazard makes certain capabilities (e.g., transport) temporarily unsafe to perform.
2.  **Component Failure:** A **nozzle clog** is simulated during a printing task. This causes the task to fail on its first attempt, requiring the system to detect the failure and attempt a recovery.

### What We Measured and Analyzed

We compared the AutoSelf orchestrator against a simple First-In-First-Out (FIFO) baseline to measure its ability to handle these events.

* **Primary Metric: Mission Makespan (Duration)**
    * **We Measured:** The total time taken to complete all tasks.
    * **We Analyzed:** A successful system should pause during the hazard and retry after the failure, completing the mission with a reasonable and predictable delay. This demonstrates efficient recovery.
* **Secondary Metric: Unsafe State Entries & Interrupted Cycles**
    * **We Measured:** The number of times the system attempted to perform an unsafe action (during the dust storm) or wasted a cycle due to an unhandled failure.
    * **We Analyzed:** The core function of the E-V-C loop is to prevent unsafe actions. We expected AutoSelf to have zero unsafe entries, proving its verification step works correctly. This contrasts with a naive system that would stumble into the hazard.

**Discussion:** This experiment validates the foundational layer of AutoSelf. Success here proves that the system can maintain an accurate world state, correctly apply safety rules, and execute basic recovery procedures like pausing and retrying. It establishes that the system is fundamentally safe and reactive.

## Experiment 2: Efficiency Under Resource Contention

### Goal

To prove that the AutoSelf system can do more than just react—it can **proactively optimize its schedule to maximize efficiency**. The experiment answers: Can the system use prediction to avoid wasting time on preventable scheduling conflicts?

### What The Code Does

This experiment uses a more abstract simulation focused purely on scheduling. Instead of a physical site, there is a queue of tasks. The key challenge is that any task has a probability `p` of requiring a single, exclusive resource 'R'.

The experiment compares two strategies for processing the task queue two at a time:

1.  **Naive Baseline:** This strategy attempts to execute two tasks every cycle. If both happen to need resource 'R', a **conflict** occurs, the cycle is wasted, and only one task is completed.
2.  **AutoSelf Orchestrator:** This strategy uses a Large Language Model (LLM) as a specialized scheduling analyst. Before execution, it asks the LLM to **predict if the next two tasks will conflict**. If a conflict is foreseen, AutoSelf wisely executes only the first task, avoiding the wasted cycle entirely.

### What We Measured and Analyzed

Performance was measured as the contention probability `p` was swept from low (rare conflicts) to high (frequent conflicts).

* **Primary Metric: Throughput (Tasks per Cycle)**
    * **We Measured:** The average number of tasks completed in each simulation cycle. Higher is better.
    * **We Analyzed:** We expected the baseline's throughput to collapse as `p` increases, because it wastes more and more cycles on conflicts. In contrast, AutoSelf's throughput should degrade much more gracefully, maintaining significantly higher efficiency.
* **Secondary Metric: Conflicts Encountered**
    * **We Measured:** The total number of conflicts that occurred during a run.
    * **We Analyzed:** This metric directly evaluates the LLM's predictive accuracy. A successful AutoSelf system should encounter close to zero conflicts, proving its verification step is effective at preventing them.

**Discussion:** This experiment isolates and tests the "intelligence" of the orchestrator. Success demonstrates that the E-V-C loop, when augmented with predictive capabilities, can dramatically improve mission efficiency. It elevates the LLM's role from a simple safety advisor to a specialized analyst whose predictions directly drive optimization.

## Experiment 3: Holistic Decision-Making in a Complex Environment

### Goal

This is the "final exam." It aims to prove that an AI-driven AutoSelf system can **make effective, holistic decisions** by synthesizing information about multiple, simultaneous, and distinct challenges. It answers: Can the system outperform a rigid, rule-based approach in a realistic, messy, and dynamic environment?

### What This Code Does

This experiment creates a sophisticated simulation where the robotic construction team must deal with **both unpredictable physical hazards and predictable resource conflicts at the same time**. It tests whether an AI, acting as the core decision-maker, can outperform a simpler rule-based system in this complex environment.

The key features are:

* **A Synthesized World:** The simulation includes a full mission plan with task dependencies (like Experiment 1), but also assigns each task a random probability `p` of needing a shared, exclusive resource (like Experiment 2). On top of that, environmental hazards like dust storms can occur randomly.
* **The AI as Mission Director:** 🤖 The role of the Large Language Model (LLM) is significantly elevated. It is no longer just an advisor or an analyst. Here, it acts as the **central decision-maker** for the AutoSelf orchestrator. In each cycle, the AI is given a comprehensive briefing that includes:
    * The current world state (which tasks are done).
    * The status of any active hazards.
    * The next two tasks in the queue, including their dependencies and resource needs.
    * A list of other available tasks that could serve as alternatives.
* **Complex Decision-Making:** Based on this complete picture, the LLM must generate an entire action plan for the cycle. It decides whether to proceed, pause, execute only one task to avoid a conflict, or even smartly substitute a blocked task with a safe alternative to maintain progress.
* **Robust Fallback System:** The orchestrator is built with a "circuit breaker." If the AI gives a bad response, is too slow, or fails several times in a row, the system automatically disables it and falls back to a simpler set of hard-coded rules to continue the mission.

### How It Compares to the Previous Experiments

This third experiment represents a major leap in complexity and AI integration, building directly on the concepts tested in the first two.

| Feature | Experiment 1 (Hazards) | Experiment 2 (Contention) | Experiment 3 (Combined) |
| :--- | :--- | :--- | :--- |
| **Core Problem** | Reacting to unpredictable physical hazards. | Proactively avoiding predictable resource conflicts. | **Handling both challenges simultaneously.** |
| **Simulation** | Mission plan with physical world state. | Abstract task queue with a single resource. | **Full mission plan with both physical state AND resource needs.** |
| **Role of the LLM**| General Safety Advisor (an optional gatekeeper). | Specialized Scheduling Analyst (predicts conflicts).| **AI Mission Director (the central decision-maker).** |
| **AI's Task** | Answers a simple "Is this safe?" question. | Answers a specific "Will these conflict?" question. | **Generates a complete action plan for the cycle,** balancing safety, efficiency, and progress. |
| **System Robustness** | Basic LLM integration. | Focused LLM integration. | **Includes an explicit fallback mechanism and circuit breaker** if the AI becomes unreliable. |

In essence, the research progresses from testing simple **reactivity** (Exp 1), to focused **optimization** (Exp 2), and finally to holistic, **intelligent decision-making** in a complex, dynamic environment (Exp 3).