"""
M5-OWASP: Security Overlay Layer Agent

Runs AFTER the JOIN node. Reads source code of every function and augments
existing test suites with targeted security tests aligned to OWASP Top 10 (2021).
"""

from __future__ import annotations

from typing import Any

from atcg.layers.base import BaseLayerAgent
from atcg.state import ATCGState, TestLayer


class SecurityLayerAgent(BaseLayerAgent):
    """OWASP Security overlay agent — Layer 5."""

    @property
    def layer(self) -> TestLayer:
        return TestLayer.SECURITY

    @property
    def min_tests(self) -> int:
        return 2

    @property
    def max_tests(self) -> int:
        return 10  # Up to 10 for functions with many OWASP categories

    @property
    def coverage_target(self) -> str:
        return "All applicable OWASP Top 10 categories tested"

    @property
    def naming_convention(self) -> str:
        return '"[functionName] [OWASP A0X] should [secure behaviour] when [attack scenario]"'

    @property
    def system_prompt(self) -> str:
        return """You are ATCG-Core M5-OWASP, a senior SDET agent specializing in SECURITY testing.

## Your Mandate
Augment existing test suites with targeted security tests aligned to the
OWASP Top 10 (2021). You run AFTER all other layers have completed.
You add DEDICATED security assertions on top of them.

## OWASP TOP 10 TEST GENERATION MATRIX

For each applicable category, generate the specified tests:

### [A01] BROKEN ACCESS CONTROL
- Assert function enforces role/permission checks before operating
- Assert function REJECTS calls from unprivileged caller
- Assert function does NOT expose another user's data (IDOR)
- Assert function respects resource ownership

### [A02] CRYPTOGRAPHIC FAILURES
- Assert passwords are NEVER stored/logged in plaintext
- Assert sensitive fields are encrypted/hashed before persistence
- Assert JWT/session tokens use strong algorithms (RS256 preferred)

### [A03] INJECTION (SQL, NoSQL, Command, LDAP)
Required attack payloads:
  SQL: ["'; DROP TABLE users; --", "' OR '1'='1", "1; SELECT *"]
  NoSQL: [{"$gt": ""}, {"$where": "1==1"}]
  Command: ["../../../etc/passwd", "; rm -rf /", "| cat /etc/passwd"]
For Neon/Postgres: assert parameterised placeholders ($1, $2), NEVER string concat

### [A04] INSECURE DESIGN
- Assert rate limiting is enforced
- Assert sensitive operations require re-authentication
- Assert business logic limits (no negative quantities, no price manipulation)

### [A05] SECURITY MISCONFIGURATION
- Assert debug mode / verbose errors NOT exposed
- Assert stack traces NOT in API responses
- Assert CORS not wildcard for credentialed requests

### [A06] VULNERABLE COMPONENTS
- No test code — emit quality_flag if vulnerable imports detected

### [A07] AUTHENTICATION FAILURES
- Assert expired tokens/sessions rejected (401)
- Assert tampered tokens rejected
- Assert brute force protection (lockout after N failures)
- Assert logout invalidates session server-side

### [A08] DATA INTEGRITY FAILURES
- Assert serialized data validated against schema
- Assert webhook payloads verified with HMAC

### [A09] LOGGING & MONITORING FAILURES
- Assert security events are logged with sufficient detail
- Assert logs do NOT contain passwords, card numbers, raw tokens

### [A10] SSRF
- Assert rejection of internal network URLs:
  ["http://169.254.169.254/", "http://localhost/admin",
   "http://10.0.0.1/", "http://192.168.1.1/"]
- Assert URL-encoded bypass variants rejected
- Assert allowlist enforcement, not blocklist

## Security Test Rules
- Generate as SEPARATE test file: <module>.security.test.<ext>
- Include OWASP category tag in every test:
    // [OWASP A03] Tests: SQL injection resistance
- Use Arrange → Act → Assert structure
- Use REALISTIC attack payloads, NOT toy examples
- When vulnerability DETECTED:
    verdict = "ESCALATE"
    severity = "CRITICAL" or "HIGH"
    HALT further generation — human review mandatory

## Naming Convention
"[functionName] [OWASP A0X] should [secure behaviour] when [attack scenario]"
Example: "loginUser [OWASP A03] should reject SQL injection in email field"

## Hard Constraints
- [N19] NEVER use toy/fake attack payloads
- [N20] NEVER suppress detected vulnerabilities — verdict = ESCALATE immediately
- [N22] ALWAYS check fixture registry
- [N23] Use attack-realistic data (actual OWASP attack strings)
"""

    def _get_layer_specific_prompt_additions(self, target_context: dict) -> list[str]:
        additions = [
            "",
            "## Security-Specific Analysis",
        ]

        # Map function characteristics to OWASP categories
        applicable_categories = []

        if target_context.get("accepts_user_input", False):
            applicable_categories.extend(["A01", "A03", "A04", "A05", "A10"])
            additions.append("- Function accepts user input → A01, A03, A04, A05, A10 applicable")

        if target_context.get("performs_auth", False):
            applicable_categories.extend(["A01", "A02", "A07", "A09"])
            additions.append("- Function performs auth → A01, A02, A07, A09 applicable")

        if target_context.get("accesses_db", False):
            applicable_categories.extend(["A01", "A03"])
            additions.append("- Function accesses DB → A01, A03 applicable")

        if target_context.get("handles_files", False):
            applicable_categories.extend(["A03", "A10"])
            additions.append("- Function handles files → A03, A10 applicable")

        if target_context.get("calls_external", False):
            applicable_categories.extend(["A10"])
            additions.append("- Function calls external services → A10 applicable")

        applicable_categories = sorted(set(applicable_categories))
        additions.extend([
            "",
            f"## Applicable OWASP Categories: {', '.join(applicable_categories)}",
            "Generate at least ONE test per applicable category.",
        ])

        return additions

    async def execute(self, state: ATCGState) -> ATCGState:
        """
        Override execute to handle the security overlay's special behavior.

        M5-OWASP processes ALL functions from the test plan, not just one.
        It reads layer_outputs from the JOIN node and augments with security tests.
        """
        # If we have layer_outputs (post-JOIN), process all targets
        test_plan = state.get("test_plan", {})
        targets = test_plan.get("targets", [])

        # Filter to security-eligible targets
        security_targets = [
            t for t in targets
            if "SECURITY" in t.get("active_layers", [])
        ]

        if not security_targets:
            return {
                **state,
                "owasp_output": {"findings": [], "tests_generated": 0},
                "security_findings": [],
            }

        all_findings: list[dict[str, Any]] = []
        all_test_outputs: list[dict[str, Any]] = []

        for target in security_targets:
            # Set up state for this target
            target_state: ATCGState = {
                **state,
                "target_id": target["id"],
                "active_layer": "SECURITY",
                "target_context": target["context"],
                "attempt": 1,
            }

            # Run the standard generation chain
            result = await super().execute(target_state)
            layer_outputs_dict = result.get("layer_outputs", {})
            test_output = next(iter(layer_outputs_dict.values()), {})
            all_test_outputs.append(test_output)

            # Extract security findings from quality flags
            for flag in test_output.get("quality_flags", []):
                if "SECURITY_VULNERABILITY_DETECTED" in flag:
                    all_findings.append({
                        "target_id": target["id"],
                        "function_name": target["name"],
                        "owasp_category": _extract_owasp_category(flag),
                        "severity": "HIGH",
                        "test_name": flag,
                        "test_code_snippet": "",
                        "verdict": "VULNERABLE",
                    })

        return {
            **state,
            "owasp_output": {
                "findings": all_findings,
                "tests_generated": len(all_test_outputs),
                "test_outputs": all_test_outputs,
            },
            "security_findings": all_findings,
        }


def _extract_owasp_category(flag: str) -> str:
    """Extract OWASP category from a quality flag string."""
    for cat in ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10"]:
        if cat in flag:
            return cat
    return "A00"  # Unknown
