# Agentic AI in ATLAS

When presenting this project, a key concept to highlight is **Agentic AI**. Unlike traditional LLM wrappers that simply take a prompt and return a response (like ChatGPT), ATLAS operates as a fully autonomous **Multi-Agent System**. 

Here is how you should explain the "Agentic" nature of your project to the reviewers:

## 1. Autonomous Decision Making (The Task Dispatcher)
ATLAS doesn't just blindly write tests. The **M4 Test Planner** acts as a "manager agent." It reads the AST (Abstract Syntax Tree), analyzes the cyclomatic complexity and dependencies of the code, and autonomously decides *which* types of tests are needed. It creates an internal execution queue of tasks and routes them to specialized sub-agents.

## 2. Specialized Worker Agents (The M5 Layer)
Instead of using one massive prompt, ATLAS uses specialized "experts" (Layer Agents):
- **Unit Agent**: Instructed to mock all dependencies and focus on branch coverage.
- **Integration Agent**: Instructed to spin up real database instances (like PostgreSQL).
- **Security Agent (OWASP)**: A specialized security researcher agent that actively tries to inject SQL payloads and XSS attacks to break the code.

## 3. The Autonomous Feedback Loop (M6 Test Executor)
This is the most critical "Agentic" feature of the project. 
When an LLM writes code, it often makes mistakes. ATLAS solves this by acting like a real developer:
1. The agent writes a test.
2. The **M6 Test Executor** takes that test and actually runs it in a sandboxed Pytest environment.
3. If the test fails, M6 extracts the exact Python traceback.
4. M6 sends the traceback *back* to the agent with the instruction: *"Your test failed with this error. Fix it."*
5. The agent learns from its mistake and rewrites the test.

This loop repeats automatically up to a maximum number of retries without any human intervention.

## 4. Human-In-The-Loop (HITL)
True Agentic AI knows its boundaries. If the Security Agent finds a critical vulnerability (like an exposed SQL injection), or if an agent gets stuck in a failure loop, ATLAS stops and triggers a **HITL Interrupt**. It alerts the human developer to step in and review the code.
