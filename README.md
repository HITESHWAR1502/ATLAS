# ATLAS AI Agent

**Automated Test Case Generator - Multi-Agent LangGraph Pipeline with 5-Layer Test Generation**

ATLAS is an Agentic AI Pipeline built on top of LangGraph to autonomously fulfill complex testing requirements. It analyzes your code and generates comprehensive tests across 5 layers: Unit, Integration, Functional, Performance, and Security.

## 🌟 Key Features

- **Autonomous Planning**: Reads AST, measures code complexity, and intelligently decides which test layers are required.
- **Multi-Agent Collaboration**: Utilizes specialized agents for different test layers operating on a shared state.
- **Self-Correction**: Automatically executes generated tests and iteratively fixes any encountered errors.
- **Tool Use**: Agents can autonomously inspect dependencies, contexts, and file structures.

## 🚀 Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python 3.11 or higher
- Git

### 1. Clone the Repository

Clone this repository to your local machine:

```bash
git clone <your_repository_url>
cd ATLAS
```

*(Note: Replace `<your_repository_url>` with the actual URL of the repository).*

### 2. Set Up a Virtual Environment (Recommended)

It is highly recommended to use a virtual environment to manage dependencies:

**On Windows:**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install the Project

Install the package in development mode along with its dependencies:

```bash
pip install -e .
```

If you plan to run tests and contribute, install the development dependencies as well:
```bash
pip install -e ".[dev]"
```

### 4. Configuration

ATLAS requires API keys for the LLM providers it uses.

1. Copy the example environment file to create your own `.env` file:
   **On Windows:**
   ```powershell
   copy .env.example .env
   ```
   **On macOS/Linux:**
   ```bash
   cp .env.example .env
   ```

2. Open the `.env` file and fill in your configuration:
   - Set the `LLM_PROVIDER` (e.g., `gemini`, `groq`, `claude`).
   - Provide the corresponding API keys (e.g., `GOOGLE_API_KEY`, `GROQ_API_KEY`).
   - Adjust other settings like `ATLAS_MAX_RETRIES` or `ATLAS_HITL_ENABLED` as needed.

## 🛠️ Usage

Once installed and configured, ATLAS provides a command-line interface for running the test case generator.

You can invoke the CLI using the `atlas` command to see all available options:

```bash
atlas --help
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
