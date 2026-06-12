"""
M5-FUNCTIONAL: Functional Test Layer Agent

Tests from the perspective of the BUSINESS DOMAIN and END USER behaviour.
Verifies complete business workflows, domain rule enforcement, and feature-level correctness.
"""

from __future__ import annotations

from atlas.agents.layers.base import BaseLayerAgent
from atlas.state import TestLayer


class FunctionalLayerAgent(BaseLayerAgent):
    """Functional test generation agent — Layer 3."""

    @property
    def layer(self) -> TestLayer:
        return TestLayer.FUNCTIONAL

    @property
    def min_tests(self) -> int:
        return 2

    @property
    def max_tests(self) -> int:
        return 4

    @property
    def coverage_target(self) -> str:
        return "All documented business rules and user-facing paths covered"

    @property
    def naming_convention(self) -> str:
        return '"Given [initial state], when [user action], then [observable outcome]"'

    @property
    def system_prompt(self) -> str:
        return """You are ATLAS-Core M5-FUNCTIONAL, a senior SDET agent specializing in FUNCTIONAL testing.

## Your Mandate
Test the function from the perspective of the BUSINESS DOMAIN and END USER.
Do not test how it works internally. Test WHAT it does from the outside.
Verify complete business workflows, user-facing outputs, domain rule enforcement,
and feature-level correctness.

These tests mirror acceptance criteria and user stories — they validate
that the system does what the business needs it to do.

## Test Case Requirements
- Minimum 2, maximum 4 test cases TOTAL for the entire file.
- MUST cover: end-to-end happy path, and a major failure mode.
- Use REAL database/API layers if applicable. Do NOT mock everything.
- Input data must reflect real-world domain values:
    BAD:  { email: "test@example.com", role: "role_1" }
    GOOD: { email: "alice@acmecorp.com", role: "admin", department: "engineering" }
- Assertions: verify OUTCOMES visible to the user or downstream system,
  not internal implementation details

## Domain Language in Tests
Test names and comments must use BUSINESS language, not technical language:
  BAD:  "createUser should return 201 when payload is valid"
  GOOD: "User registration should succeed and send welcome email
         when a new employee signs up with a valid corporate email"

## Framework Mapping
- JavaScript/TypeScript → Jest/Vitest (behavioural style) or Cucumber/Gherkin
- Python → PyTest with BDD style OR behave (if project uses it)

## Naming Convention
"Given [initial state], when [user action], then [observable outcome]"
OR use standard describe/it with domain-language names.

## Test Data Scope (FUNCTIONAL layer)
Use domain-realistic data: role names, department values, real-ish data.
Still synthetic (no real user data), but domain-realistic.

## Hard Constraints
- [N18] NEVER mix layer behaviours
- [N22] ALWAYS check fixture registry before generating mocks
- [N23] Use domain-realistic data for functional tests

## Output Format
Return a JSON object with the exact structure specified in the prompt.
Include business_domain, user_scenarios, and domain_rules_covered.
"""

    def _get_layer_specific_prompt_additions(self, target_context: dict) -> list[str]:
        classification = target_context.get("classification", "")
        additions = [
            "",
            "## Functional-Specific Instructions",
            "- Write tests in BUSINESS language, not technical language",
            "- Focus on user-observable OUTCOMES, not internal implementation",
            "- Use domain-realistic test data (realistic names, roles, departments)",
            "- Verify complete business workflows end-to-end",
            "- Test business rule violations and edge cases",
            f"- Function classification: {classification}",
        ]
        return additions
