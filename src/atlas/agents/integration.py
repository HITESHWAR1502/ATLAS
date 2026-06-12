"""
M5-INTEGRATION: Integration Test Layer Agent

Tests how functions interact with their DIRECT real dependencies:
database layer, message queues, cache, internal service clients.
"""

from __future__ import annotations

from atlas.agents.layers.base import BaseLayerAgent
from atlas.state import TestLayer


class IntegrationLayerAgent(BaseLayerAgent):
    """Integration test generation agent — Layer 2."""

    @property
    def layer(self) -> TestLayer:
        return TestLayer.INTEGRATION

    @property
    def min_tests(self) -> int:
        return 2

    @property
    def max_tests(self) -> int:
        return 4

    @property
    def coverage_target(self) -> str:
        return "All identified dependency interaction paths covered"

    @property
    def naming_convention(self) -> str:
        return '"[functionName] should [data outcome] when [dependency state]"'

    @property
    def system_prompt(self) -> str:
        return """You are ATLAS-Core M5-INTEGRATION, a senior SDET agent specializing in INTEGRATION testing.

## Your Mandate
Test how this function interacts with its DIRECT real dependencies:
database layer, message queues, cache, internal service clients.
Use real dependency instances where feasible in a test environment;
mock only EXTERNAL third-party services and network boundaries.
Verify the data contract between this function and its dependencies.

## Test Case Requirements
- Minimum 2, maximum 4 test cases TOTAL for the entire file.
- MUST cover: successful data retrieval/persistence, error handling from the dependency, timeout/latency scenarios.ut
  * Data contract mismatch (wrong schema returned)
  * Transaction rollback behaviour
- For Neon/Postgres: use pg-mem (JS) or pytest-postgresql (Python)
  OR a Neon branch database connection via environment
- Verify data persistence: assert DB state matches expected after function

## Neon-Specific Integration Patterns
If source uses @neondatabase/serverless (JS/TS):
  - Inject Neon branch URL via env: process.env.DATABASE_URL = process.env.TEST_NEON_BRANCH_URL
  - If branch not available, fall back to pg-mem and flag:
    quality_flags: ["INTEGRATION_DOWNGRADED_TO_MOCK — neon branch unavailable"]

If source uses asyncpg/psycopg2 (Python):
  - Use pytest-postgresql fixture for local Postgres
  - Apply schema migrations before tests

## Framework Mapping
- JavaScript/TypeScript → Jest + pg-mem OR Neon branch
- Python → PyTest + pytest-postgresql OR asyncpg test utils
- Java → JUnit 5 + Testcontainers (Postgres)

## Naming Convention
"[functionName] should [data outcome] when [dependency state]"
Example: "createUser should persist user record when DB write succeeds"
Example: "createUser should rollback and throw when DB write fails"

## Test Data Scope (INTEGRATION layer)
Use realistic schema data — correct column types, FK-valid values.

## Hard Constraints
- [N18] NEVER mix unit mocks and integration real-DB in the same file
- [N22] ALWAYS check fixture registry before generating mocks
- [N23] Use realistic schema data for integration tests

## Output Format
Return a JSON object with the exact structure specified in the prompt.
Include dependency_map in the output for Neon tracking.
"""

    def _get_layer_specific_prompt_additions(self, target_context: dict) -> list[str]:
        additions = [
            "",
            "## Integration-Specific Instructions",
            "- Test real dependency interactions (DB queries, cache ops, queue messages)",
            "- Mock only EXTERNAL third-party services (Stripe, SendGrid, etc.)",
            "- Verify data contracts: correct query shapes, payload structures, error propagation",
            "- Test transaction rollback on failure",
            "- Assert DB state after function execution",
        ]

        deps = target_context.get("dependencies", [])
        if "database" in deps:
            additions.extend([
                "",
                "## Database Integration",
                "- Set up test database with correct schema",
                "- Seed required test data before each test",
                "- Assert database state after function execution",
                "- Clean up test data in teardown",
            ])

        return additions
