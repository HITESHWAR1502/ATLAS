"""
M5-UNIT: Unit Test Layer Agent

Tests functions in complete isolation. Every dependency is mocked.
Verifies internal logic, branching, return values, and error handling.
"""

from __future__ import annotations

from atlas.agents.layers.base import BaseLayerAgent
from atlas.state import TestLayer


class UnitLayerAgent(BaseLayerAgent):
    """Unit test generation agent — Layer 1."""

    @property
    def layer(self) -> TestLayer:
        return TestLayer.UNIT

    @property
    def min_tests(self) -> int:
        return 2

    @property
    def max_tests(self) -> int:
        return 5

    @property
    def coverage_target(self) -> str:
        return "≥85% branch coverage estimated; ≥80% verified by M8"

    @property
    def naming_convention(self) -> str:
        return '"[functionName] should [expected result] when [condition]"'

    @property
    def system_prompt(self) -> str:
        return """You are ATLAS-Core M5-UNIT, a senior SDET agent specializing in UNIT testing.

## Your Mandate
Test the function in COMPLETE ISOLATION. Every dependency is mocked.
Verify the function's internal logic, branching, return values, and
error handling independent of any external system.

## Test Case Requirements
- Minimum 2, maximum 5 test cases TOTAL for the entire file.
- MUST cover: happy path, edge cases, error path for the most critical logic.
- 100% of external dependencies mocked (DB, HTTP, FS, time, random)
- Assertions: exact return value equality, specific error type + message,
  mock call argument verification

## Framework Mapping
- JavaScript/TypeScript → Jest or Vitest (per project config)
- Python → PyTest with pytest-mock / unittest.mock
- Java → JUnit 5 + Mockito
- Go → testing package + testify/mock

## Naming Convention
"[functionName] should [expected result] when [condition]"
Example: "hashPassword should return bcrypt hash when valid password given"

## Test Data Scope (UNIT layer)
Use synthetic, minimal data: test@example.com, user-id-001
Test data should be simple and focused on the logic being tested.

## Neon/Postgres Mocking Strategy
If the function uses Neon/Postgres, mock at the DRIVER level:
- Mock the entire database client/pool
- Return hardcoded mock data
- Verify query shapes and parameters

## Hard Constraints
- [N18] NEVER mix layer behaviours — unit tests ONLY mock, no real dependencies
- [N22] ALWAYS check fixture registry before generating mocks
- [N23] Use synthetic, minimal test data for unit tests

## Output Format
Return a JSON object with the exact structure specified in the prompt.
The test_code field must be a COMPLETE, VALID, EXECUTABLE test file.
Use AAA (Arrange-Act-Assert) for every test case.
One behaviour per test. Async/await where the function is async.
"""

    def _get_layer_specific_prompt_additions(self, target_context: dict) -> list[str]:
        """Add unit-specific prompt sections."""
        additions = [
            "",
            "## Unit-Specific Instructions",
            "- Mock ALL external dependencies (database, HTTP, filesystem, time, random)",
            "- Focus on internal branching logic and return value correctness",
            "- Test every error path — verify specific error types and messages",
            "- Verify mock call arguments (ensure correct parameters are passed to mocks)",
            "- Estimate branch coverage — target ≥85%",
        ]

        deps = target_context.get("dependencies", [])
        if deps:
            additions.extend([
                "",
                f"## Dependencies to Mock: {', '.join(deps)}",
                "Generate complete mock implementations for each dependency.",
            ])

        return additions
