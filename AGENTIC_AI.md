# Agentic AI in ATLAS v3.0

ATLAS (Automated Test Case Generator) is not just a standard LLM code generator. It is an **Agentic AI Pipeline** built on top of [LangGraph](https://python.langchain.com/docs/langgraph). 

This document explains what makes ATLAS "Agentic" and how it acts autonomously to fulfill complex testing requirements.

## 1. Autonomous Planning & Execution (M4 & M5 Nodes)
In a traditional LLM script, you provide a prompt, and the model returns an output. ATLAS operates differently:
- **Test Planner (M4):** Before writing any code, the AI acts as a **Test Architect**. It reads the abstract syntax tree (AST) of the target file, measures cyclomatic complexity, checks for dependencies, and automatically *decides* which test layers (Unit, Integration, Functional, Performance, Security) are required. 
- **Task Dispatcher:** The graph dynamically routes the file to specialized Sub-Agents (e.g., `M5-UNIT`, `M5-SECURITY`) based on the plan. This dynamic routing is a hallmark of agentic systems.

## 2. Multi-Agent Collaboration (Parallel Fan-Out)
ATLAS utilizes a **Multi-Agent Architecture**.
- Each test layer (Unit, Integration, Security, etc.) is handled by a specialized `create_react_agent` instance with a unique system prompt tailored to that specific domain.
- These agents operate independently but share the same underlying state (LangGraph `ATLASState`). 

## 3. Reflection and Self-Correction (M6 Test Executor Loop)
The most critical feature of Agentic AI is the ability to **reflect on mistakes and self-correct**.
- **Execution Loop:** When an M5 layer agent writes a test file, the pipeline doesn't just stop. It passes the test to the **M6 Test Executor**.
- **Validation:** M6 actually *runs* the test code (e.g., using `pytest`) in an isolated environment.
- **Feedback Loop:** If the test fails (due to syntax errors, missing mocks, or logic flaws), the execution output is fed *back* to the specific M5 layer agent. The agent reads the error trace, understands its mistake, and rewrites the test. It does this autonomously for up to 3 attempts.

## 4. Tool Use Capabilities
Agents differ from base models by their ability to interact with their environment using tools.
- ATLAS layer agents are equipped with tools like `read_source_file` to autonomously look up imported dependencies or inspect neighboring files if they need more context while writing mocks.

## Summary of Agentic Characteristics
| Feature | Traditional LLM Script | ATLAS Agentic Pipeline |
| :--- | :--- | :--- |
| **Workflow** | Linear (Prompt -> Output) | Cyclic (Plan -> Act -> Reflect -> Retry) |
| **Decision Making** | User decides what to prompt | AI decides which tests are needed |
| **Error Handling** | User manually fixes bad code | AI runs code, reads errors, and fixes itself |
| **Architecture** | Single prompt | Multi-Agent LangGraph State Machine |

By combining **Planning, Tool Use, Multi-Agent Routing, and Self-Reflection**, ATLAS fully qualifies as a modern Agentic AI system.
