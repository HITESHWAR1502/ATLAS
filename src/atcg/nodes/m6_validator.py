"""
M6: Validator — Validates generated test code for correctness and quality.

Checks syntax, imports, assertions, layer-specific requirements, and
emits PASS/RETRY/ESCALATE verdicts.
"""

from __future__ import annotations

import ast
import logging
from typing import Any

from atcg.state import ATCGState, Verdict

logger = logging.getLogger(__name__)


def m6_validator(state: ATCGState) -> ATCGState:
    """
    M6: Validator node.

    Validates all generated test outputs and determines verdict.

    Verdicts:
      PASS    → Tests are valid, proceed to M7 (Neon Writer)
      RETRY   → Tests have fixable issues, route back to specific M5 node
      ESCALATE → Critical issue requiring human review (security vulnerability, etc.)
    """
    layer_outputs = state.get("layer_outputs", {})
    security_findings = state.get("security_findings", [])
    project_context = state.get("project_context", {})
    language = project_context.get("language", "python")

    all_issues: list[dict[str, str]] = []
    layer_verdicts: dict[str, str] = {}

    # ── Validate each layer's output ─────────────────────────────────────────
    for output_key, output in layer_outputs.items():
        layer = output.get("active_layer", "UNKNOWN")
        from enum import Enum
        if isinstance(layer, Enum):
            layer = layer.value
        elif not isinstance(layer, str):
            layer = str(layer)
        issues = _validate_layer_output(output, layer, language)
        if issues:
            all_issues.extend(issues)
            # Check severity of issues
            has_critical = any(i["severity"] == "CRITICAL" for i in issues)
            has_error = any(i["severity"] == "ERROR" for i in issues)

            if has_critical:
                layer_verdicts[layer] = Verdict.ESCALATE.value
            elif has_error:
                layer_verdicts[layer] = Verdict.RETRY.value
            else:
                layer_verdicts[layer] = Verdict.PASS.value
        else:
            layer_verdicts[layer] = Verdict.PASS.value

    # ── Check for security escalations ───────────────────────────────────────
    has_vulnerabilities = any(
        f.get("verdict") == "VULNERABLE" for f in security_findings
    )
    if has_vulnerabilities:
        layer_verdicts["SECURITY"] = Verdict.ESCALATE.value

    # ── Determine overall verdict ────────────────────────────────────────────
    if any(v == Verdict.ESCALATE.value for v in layer_verdicts.values()):
        overall_verdict = Verdict.ESCALATE.value
    elif any(v == Verdict.RETRY.value for v in layer_verdicts.values()):
        overall_verdict = Verdict.RETRY.value
    else:
        overall_verdict = Verdict.PASS.value

    # ── Build rejection feedback for RETRY ───────────────────────────────────
    rejection_feedback = None
    if overall_verdict == Verdict.RETRY.value:
        retry_layers = [lyr for lyr, v in layer_verdicts.items() if v == Verdict.RETRY.value]
        rejection_feedback = {
            "layers": retry_layers,
            "failures": [i for i in all_issues if i["severity"] in ("ERROR", "CRITICAL")],
            "suggestions": [i.get("suggestion", "") for i in all_issues if i.get("suggestion")],
        }

    logger.info(
        f"M6: Validation complete — verdict={overall_verdict}, "
        f"layers={layer_verdicts}, issues={len(all_issues)}"
    )

    return {
        **state,
        "verdict": overall_verdict,
        "rejection_feedback": rejection_feedback,
    }


def _validate_layer_output(
    output: dict[str, Any], layer: str, language: str
) -> list[dict[str, str]]:
    """Validate a single layer's test output."""
    issues: list[dict[str, str]] = []
    test_code = output.get("test_code", "")

    # ── Check: test code is not empty ────────────────────────────────────────
    if not test_code or len(test_code.strip()) < 50:
        issues.append({
            "layer": layer,
            "check": "NON_EMPTY_CODE",
            "severity": "ERROR",
            "message": "Test code is empty or too short",
            "suggestion": "Regenerate test code — ensure LLM output contains complete tests",
        })
        return issues  # No point continuing

    # ── Check: syntax validation ─────────────────────────────────────────────
    if language == "python":
        try:
            ast.parse(test_code)
        except SyntaxError as e:
            issues.append({
                "layer": layer,
                "check": "SYNTAX_VALID",
                "severity": "ERROR",
                "message": f"Python syntax error: {e}",
                "suggestion": f"Fix syntax error at line {e.lineno}: {e.msg}",
            })

    # ── Check: has assertions ────────────────────────────────────────────────
    assertion_patterns = {
        "python": ["assert ", "assertEqual", "assertRaises", "pytest.raises"],
        "javascript": ["expect(", "assert.", "assert(", "toBe(", "toEqual("],
        "typescript": ["expect(", "assert.", "assert(", "toBe(", "toEqual("],
        "java": ["assert", "assertEquals", "assertThrows", "verify("],
        "go": ["assert.", "require.", "t.Error", "t.Fatal"],
    }
    patterns = assertion_patterns.get(language, assertion_patterns["python"])
    has_assertions = any(p in test_code for p in patterns)
    if not has_assertions:
        issues.append({
            "layer": layer,
            "check": "HAS_ASSERTIONS",
            "severity": "ERROR",
            "message": "No assertions found in test code",
            "suggestion": "Add assertions to verify expected behaviour",
        })

    # ── Check: has imports ───────────────────────────────────────────────────
    import_patterns = {
        "python": ["import ", "from "],
        "javascript": ["import ", "require(", "const "],
        "typescript": ["import ", "require("],
        "java": ["import "],
        "go": ["import "],
    }
    patterns = import_patterns.get(language, import_patterns["python"])
    has_imports = any(p in test_code for p in patterns)
    if not has_imports:
        issues.append({
            "layer": layer,
            "check": "HAS_IMPORTS",
            "severity": "WARNING",
            "message": "No import statements found",
            "suggestion": "Add necessary imports for test framework and source module",
        })

    # ── Check: naming convention ─────────────────────────────────────────────
    _check_naming_convention(test_code, layer, language, issues)

    # ── Check: layer-specific requirements ───────────────────────────────────
    _check_layer_requirements(test_code, layer, language, issues)

    return issues


def _check_naming_convention(
    test_code: str, layer: str, language: str, issues: list[dict[str, str]]
) -> None:
    """Verify test naming follows layer conventions."""
    if layer == "UNIT":
        # Should have "should" in test names
        if language == "python" and "def test_" in test_code:
            pass  # Python uses test_ prefix — acceptable
        elif "should" not in test_code.lower() and "test_" not in test_code.lower():
            issues.append({
                "layer": layer,
                "check": "NAMING_CONVENTION",
                "severity": "WARNING",
                "message": "Test names don't follow unit naming convention",
            })

    elif layer == "SECURITY":
        if "OWASP" not in test_code and "owasp" not in test_code.lower():
            issues.append({
                "layer": layer,
                "check": "OWASP_TAGS",
                "severity": "WARNING",
                "message": "Security tests should include OWASP category tags",
            })


def _check_layer_requirements(
    test_code: str, layer: str, language: str, issues: list[dict[str, str]]
) -> None:
    """Check layer-specific requirements."""
    if layer == "UNIT":
        # Should have mocking
        mock_patterns = {
            "python": ["mock", "patch", "MagicMock", "AsyncMock"],
            "javascript": ["jest.mock", "jest.fn", "vi.mock", "vi.fn"],
            "typescript": ["jest.mock", "jest.fn", "vi.mock", "vi.fn"],
        }
        patterns = mock_patterns.get(language, [])
        if patterns and not any(p in test_code for p in patterns):
            issues.append({
                "layer": layer,
                "check": "HAS_MOCKS",
                "severity": "WARNING",
                "message": "Unit tests should mock external dependencies",
            })

    elif layer == "PERFORMANCE":
        # Should NOT have sleep-based assertions
        if "sleep(" in test_code or "time.sleep" in test_code:
            issues.append({
                "layer": layer,
                "check": "NO_SLEEP_ASSERTIONS",
                "severity": "ERROR",
                "message": "Performance tests must not use sleep() for assertions [N21]",
                "suggestion": "Use actual measured execution time against defined budgets",
            })


def get_routing_verdict(state: ATCGState) -> str:
    """
    LangGraph conditional routing function for M6 output.

    Returns the next node name based on verdict:
      PASS     → m7_neon_writer
      RETRY    → route back to failing layer (handled by graph)
      ESCALATE → hitl_interrupt
    """
    verdict = state.get("verdict", Verdict.PASS.value)

    if verdict == Verdict.PASS.value:
        return "m7_neon_writer"
    elif verdict == Verdict.RETRY.value:
        attempt = state.get("attempt", 1)
        max_retries = 3
        if attempt >= max_retries:
            logger.warning(f"M6: Max retries ({max_retries}) reached — escalating")
            return "hitl_interrupt"
        return "retry_handler"
    else:  # ESCALATE
        return "hitl_interrupt"
