# 🧪 ATCG v3.0 — Automated Test Case Generator

> Multi-Agent LangGraph Pipeline with 5-Layer Test Generation, OWASP Security Overlay, and Neon PostgreSQL Persistence.

## Architecture

```
[M0: Git Diff] → [M1: Ingestion] → [M2: AST Parser] → [M3: RAG Embedder] → [M4: Test Planner]
                                                                                     ↓
                                                                            ⚡ Parallel Fan-out
                                                                     ┌───────────────┴───────────────┐
                                                                [M5-UNIT] [M5-INTEGRATION] [M5-FUNC] [M5-PERF]
                                                                     └───────────────┬───────────────┘
                                                                                [JOIN Node]
                                                                                     ↓
                                                                           [M5-OWASP: Security]
                                                                                     ↓
                                                                             [M6: Validator]
                                                                              ↓          ↓
                                                                           [PASS]     [RETRY]
                                                                              ↓
                                                                        [M7: Neon Writer]
                                                                              ↓
                                                                       [M8: Coverage Runner]
```

## 5-Layer Test Generation Model

| Layer | Agent | Purpose | Tests/Fn |
|-------|-------|---------|----------|
| **Unit** | M5-UNIT | Isolated function testing, all deps mocked | 3–5 |
| **Integration** | M5-INTEGRATION | Real dependency interactions (DB, cache) | 2–4 |
| **Functional** | M5-FUNCTIONAL | Business domain / end-user behavior | 2–4 |
| **Performance** | M5-PERFORMANCE | Latency, throughput, N+1 detection | 2–3 |
| **Security** | M5-OWASP | OWASP Top 10 security testing | 2–10 |

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A [Neon](https://neon.tech) account with a database project
- A [Google AI Studio](https://aistudio.google.com/apikey) API key (Gemini)

### 2. Install

```bash
# Clone the project
cd ATLAS_AI_AGENT

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials:
#   NEON_DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/atcg?sslmode=require
#   GOOGLE_API_KEY=your-gemini-api-key
```

### 4. Initialize Database

```bash
# Create all ATCG tables in Neon
atcg init-db

# Or check status
atcg status
```

### 5. Run ATCG

```bash
# Run on a repository
atcg run /path/to/your/project

# Run only on git-changed files
atcg run /path/to/your/project --diff

# Run on a specific function
atcg run /path/to/your/project --target module.function_name
```

### 6. View Results

```bash
# Check security findings
atcg findings

# Check critical findings only
atcg findings --severity CRITICAL
```

## Neon Setup Guide

1. **Create Account**: Go to [neon.tech](https://neon.tech) and sign up
2. **Create Project**: Click "New Project" → name it `atcg`
3. **Get Connection String**: Dashboard → Connection Details → copy the connection string
4. **Enable Extensions**: In the SQL Editor, run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   CREATE EXTENSION IF NOT EXISTS "vector";
   ```
5. **Set Environment**: Paste the connection string into `.env` as `NEON_DATABASE_URL`

## Technology Stack

- **Orchestration**: LangGraph StateGraph with parallel fan-out (Send API)
- **LLM**: Google Gemini 2.5 Flash (cost-efficient test generation)
- **Embeddings**: Google text-embedding-004 (RAG/semantic search)
- **Database**: Neon PostgreSQL (checkpoints, history, fixtures, findings)
- **AST Parsing**: tree-sitter (multi-language support)
- **CLI**: Click + Rich (beautiful terminal output)

## License

MIT
