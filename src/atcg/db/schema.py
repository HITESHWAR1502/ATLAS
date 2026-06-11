"""
ATCG Neon Database Schema — SQL DDL for all ATCG tables.

Tables:
  1. atcg_unit_runs          — Layer 1 test run history
  2. atcg_integration_runs   — Layer 2 test run history
  3. atcg_functional_runs    — Layer 3 test run history
  4. atcg_performance_runs   — Layer 4 test run history + perf budgets
  5. atcg_security_findings  — Layer 5 OWASP findings (append-only audit log)
  6. atcg_shared_fixtures    — Cross-run fixture registry
  7. atcg_runs               — Master run log (parent table)
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Extension setup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_EXTENSIONS = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master run log
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_RUNS = """
CREATE TABLE IF NOT EXISTS atcg_runs (
    run_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id       TEXT NOT NULL,
    project_name    TEXT NOT NULL,
    language        TEXT NOT NULL,
    test_framework  TEXT NOT NULL,
    targets_count   INTEGER NOT NULL DEFAULT 0,
    layers_dispatched INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_atcg_runs_project
    ON atcg_runs (project_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_atcg_runs_status
    ON atcg_runs (status);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer 1 — Unit test runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_UNIT_RUNS = """
CREATE TABLE IF NOT EXISTS atcg_unit_runs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id              UUID NOT NULL REFERENCES atcg_runs(run_id) ON DELETE CASCADE,
    target_id           TEXT NOT NULL,
    attempt             INTEGER NOT NULL DEFAULT 1,
    test_code           TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    framework           TEXT NOT NULL,
    confidence          REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    branch_coverage_pct REAL,
    quality_flags       TEXT[] DEFAULT '{}',
    fixtures_reused     TEXT[] DEFAULT '{}',
    fixtures_registered TEXT[] DEFAULT '{}',
    reasoning           TEXT,
    verdict             TEXT NOT NULL CHECK (verdict IN ('PASS', 'RETRY', 'ESCALATE')),
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unit_runs_target
    ON atcg_unit_runs (target_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_unit_runs_run
    ON atcg_unit_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_unit_runs_verdict
    ON atcg_unit_runs (verdict);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer 2 — Integration test runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_INTEGRATION_RUNS = """
CREATE TABLE IF NOT EXISTS atcg_integration_runs (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id               UUID NOT NULL REFERENCES atcg_runs(run_id) ON DELETE CASCADE,
    target_id            TEXT NOT NULL,
    attempt              INTEGER NOT NULL DEFAULT 1,
    test_code            TEXT NOT NULL,
    file_path            TEXT NOT NULL,
    framework            TEXT NOT NULL,
    confidence           REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    dependency_map       JSONB DEFAULT '[]'::JSONB,
    neon_branch_used     BOOLEAN DEFAULT FALSE,
    contract_assertions  JSONB DEFAULT '[]'::JSONB,
    quality_flags        TEXT[] DEFAULT '{}',
    fixtures_reused      TEXT[] DEFAULT '{}',
    fixtures_registered  TEXT[] DEFAULT '{}',
    reasoning            TEXT,
    verdict              TEXT NOT NULL CHECK (verdict IN ('PASS', 'RETRY', 'ESCALATE')),
    generated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_integration_runs_target
    ON atcg_integration_runs (target_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_integration_runs_run
    ON atcg_integration_runs (run_id);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer 3 — Functional test runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_FUNCTIONAL_RUNS = """
CREATE TABLE IF NOT EXISTS atcg_functional_runs (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id               UUID NOT NULL REFERENCES atcg_runs(run_id) ON DELETE CASCADE,
    target_id            TEXT NOT NULL,
    attempt              INTEGER NOT NULL DEFAULT 1,
    test_code            TEXT NOT NULL,
    file_path            TEXT NOT NULL,
    framework            TEXT NOT NULL,
    confidence           REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    business_domain      TEXT,
    user_scenarios       JSONB DEFAULT '[]'::JSONB,
    domain_rules_covered JSONB DEFAULT '[]'::JSONB,
    quality_flags        TEXT[] DEFAULT '{}',
    fixtures_reused      TEXT[] DEFAULT '{}',
    fixtures_registered  TEXT[] DEFAULT '{}',
    reasoning            TEXT,
    verdict              TEXT NOT NULL CHECK (verdict IN ('PASS', 'RETRY', 'ESCALATE')),
    generated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_functional_runs_target
    ON atcg_functional_runs (target_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_functional_runs_run
    ON atcg_functional_runs (run_id);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer 4 — Performance test runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_PERFORMANCE_RUNS = """
CREATE TABLE IF NOT EXISTS atcg_performance_runs (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id                UUID NOT NULL REFERENCES atcg_runs(run_id) ON DELETE CASCADE,
    target_id             TEXT NOT NULL,
    attempt               INTEGER NOT NULL DEFAULT 1,
    test_code             TEXT NOT NULL,
    file_path             TEXT NOT NULL,
    framework             TEXT NOT NULL,
    confidence            REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    p50_budget_ms         REAL,
    p95_budget_ms         REAL,
    concurrency_target    INTEGER DEFAULT 50,
    n1_detected           BOOLEAN DEFAULT FALSE,
    memory_growth_factor  REAL,
    quality_flags         TEXT[] DEFAULT '{}',
    fixtures_reused       TEXT[] DEFAULT '{}',
    fixtures_registered   TEXT[] DEFAULT '{}',
    reasoning             TEXT,
    verdict               TEXT NOT NULL CHECK (verdict IN ('PASS', 'RETRY', 'ESCALATE')),
    generated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_runs_target
    ON atcg_performance_runs (target_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_performance_runs_run
    ON atcg_performance_runs (run_id);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer 5 — Security findings (OWASP — append-only audit log)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_SECURITY_FINDINGS = """
CREATE TABLE IF NOT EXISTS atcg_security_findings (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id            UUID NOT NULL REFERENCES atcg_runs(run_id) ON DELETE CASCADE,
    target_id         TEXT NOT NULL,
    function_name     TEXT NOT NULL,
    owasp_category    TEXT NOT NULL
                      CHECK (owasp_category IN ('A01','A02','A03','A04','A05',
                                                 'A06','A07','A08','A09','A10')),
    severity          TEXT NOT NULL
                      CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    test_name         TEXT NOT NULL,
    test_code_snippet TEXT,
    verdict           TEXT NOT NULL
                      CHECK (verdict IN ('VULNERABLE', 'SECURE', 'INCONCLUSIVE')),
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ,
    jira_ticket       TEXT
);

-- This table is APPEND-ONLY — records are never deleted, only resolved.
CREATE INDEX IF NOT EXISTS idx_security_findings_target
    ON atcg_security_findings (target_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_findings_category
    ON atcg_security_findings (owasp_category, severity);
CREATE INDEX IF NOT EXISTS idx_security_findings_unresolved
    ON atcg_security_findings (severity, detected_at DESC)
    WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_security_findings_run
    ON atcg_security_findings (run_id);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared Fixture Registry (new in v3.0)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_SHARED_FIXTURES = """
CREATE TABLE IF NOT EXISTS atcg_shared_fixtures (
    fixture_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name    TEXT NOT NULL,
    fixture_key     TEXT NOT NULL,
    fixture_code    TEXT NOT NULL,
    language        TEXT NOT NULL
                    CHECK (language IN ('python', 'typescript', 'javascript', 'java', 'go')),
    framework       TEXT NOT NULL,
    layer_tags      JSONB DEFAULT '[]'::JSONB,
    usage_count     INTEGER NOT NULL DEFAULT 1,
    last_used_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tags            JSONB DEFAULT '[]'::JSONB,
    created_by_run  UUID REFERENCES atcg_runs(run_id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (project_name, fixture_key, language, framework)
);

CREATE INDEX IF NOT EXISTS idx_fixtures_project_lang
    ON atcg_shared_fixtures (project_name, language, framework);
CREATE INDEX IF NOT EXISTS idx_fixtures_tags
    ON atcg_shared_fixtures USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_fixtures_layer_tags
    ON atcg_shared_fixtures USING GIN (layer_tags);
CREATE INDEX IF NOT EXISTS idx_fixtures_usage
    ON atcg_shared_fixtures (usage_count DESC);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RAG Embeddings (for M3 semantic search)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE_ATCG_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS atcg_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name    TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    source_code     TEXT NOT NULL,
    docstring       TEXT,
    embedding       vector(768),
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (project_name, target_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_project
    ON atcg_embeddings (project_name);
CREATE INDEX IF NOT EXISTS idx_embeddings_vector
    ON atcg_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ordered list for schema initialization
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALL_TABLES = [
    ("extensions", CREATE_EXTENSIONS),
    ("atcg_runs", CREATE_ATCG_RUNS),
    ("atcg_unit_runs", CREATE_ATCG_UNIT_RUNS),
    ("atcg_integration_runs", CREATE_ATCG_INTEGRATION_RUNS),
    ("atcg_functional_runs", CREATE_ATCG_FUNCTIONAL_RUNS),
    ("atcg_performance_runs", CREATE_ATCG_PERFORMANCE_RUNS),
    ("atcg_security_findings", CREATE_ATCG_SECURITY_FINDINGS),
    ("atcg_shared_fixtures", CREATE_ATCG_SHARED_FIXTURES),
    ("atcg_embeddings", CREATE_ATCG_EMBEDDINGS),
]

# Layer name → table name mapping
LAYER_TABLE_MAP = {
    "UNIT": "atcg_unit_runs",
    "INTEGRATION": "atcg_integration_runs",
    "FUNCTIONAL": "atcg_functional_runs",
    "PERFORMANCE": "atcg_performance_runs",
    "SECURITY": "atcg_security_findings",
}
