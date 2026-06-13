# ATLAS

**Automated Test Case Generator - Multi-Agent LangGraph Pipeline with 5-Layer Test Generation**

ATLAS is an Agentic AI Pipeline built on top of LangGraph to autonomously fulfill complex testing requirements by analyzing code and generating tests across 5 layers (Unit, Integration, Functional, Performance, Security).

## Features

- **Autonomous Planning**: Reads AST, measures complexity, and decides which test layers are required.
- **Multi-Agent Collaboration**: Specialized agents for different test layers operating on a shared state.
- **Self-Correction**: Automatically runs generated tests and iteratively fixes errors.
- **Tool Use**: Agents inspect dependencies and context autonomously.

See [AGENTIC_AI.md](AGENTIC_AI.md) for more details on the agentic architecture.

## Installation

You can install the package in development mode:

```bash
pip install -e .
```

## Usage

ATLAS provides a command-line interface for running the test case generator.

```bash
atlas [OPTIONS] COMMAND [ARGS]...
```

## License

This project is licensed under the [MIT License](LICENSE).
