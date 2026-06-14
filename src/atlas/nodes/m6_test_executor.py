"""
M6: Test Executor Node

Replaces the static validator. This node writes the generated test code
to a sandboxed temporary directory, executes it via pytest, and returns
the execution results and tracebacks to drive the autonomous feedback loop.
"""

from __future__ import annotations

from typing import Any

import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from atlas.state import ATLASState

logger = logging.getLogger(__name__)

MAX_TRACEBACK_CHARS = 4000


def m6_test_executor(state: ATLASState) -> ATLASState:
    """
    Executes the generated test code in a sandboxed temporary directory.
    Returns the verdict (PASS/RETRY/ESCALATE) and any execution errors.
    Builds deterministic pytest feedback for the retry loop.
    """
    active_layer = state.get("active_layer", "unknown")
    target_file = state.get("target_file", "unknown")
    project_context = state.get("project_context", {})
    language = project_context.get("language", "python")

    if language != "python":
        logger.info(
            "M6: Skipping live execution for %s project; generated tests will be written to disk.",
            language,
        )
        return {
            "verdict": "PASS",
            "rejection_feedback": None,
            "execution_result": {
                "status": "SKIPPED",
                "reason": f"Live execution is currently supported for Python only, not {language}.",
                "layer": active_layer,
                "attempt": state.get("attempt", 1),
            },
        }

    layer_outputs = state.get("layer_outputs", {})
    output_key = f"{target_file}_{active_layer}"
    output = layer_outputs.get(output_key, layer_outputs.get(active_layer, {}))

    test_code = output.get("test_code", "")
    if not test_code:
        # Fallback to check if M5 generated it under just the layer name (e.g. "UNIT")
        fallback_output = layer_outputs.get(active_layer, {})
        test_code = fallback_output.get("test_code", "")

    if not test_code:
        logger.warning(f"M6: No test code found for {active_layer} on {target_file}")
        logger.warning(
            f"M6 Debug: Expected key {output_key}, available keys: {list(layer_outputs.keys())}"
        )
        return {"verdict": "PASS"}  # Nothing to test

    project_root = project_context.get("project_root", "")

    # Write to temp sandbox and execute
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        # Use filename without extension for module structure in sandbox
        safe_name = target_file.replace("/", "_").replace("\\", "_").replace(".", "_")
        test_file = temp_path / f"test_{safe_name}.py"
        test_file.write_text(test_code, encoding="utf-8")

        # Determine PYTHONPATH so it can import the actual project code
        env = None
        if project_root:
            import os

            env = os.environ.copy()
            # Add both project_root and project_root/src to PYTHONPATH
            src_path = str(Path(project_root) / "src")
            root_path = str(Path(project_root))
            env["PYTHONPATH"] = (
                src_path + os.pathsep + root_path + os.pathsep + env.get("PYTHONPATH", "")
            )

        logger.info(f"M6: Executing {active_layer} test for {target_file} via pytest in sandbox")

        try:
            # We run pytest on the temporary file
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,  # Timeout to prevent hanging tests
            )

            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode

            # Parse and log tabular report
            report_table = _format_test_report(stdout)
            if report_table:
                logger.info(f"\n{report_table}\n")

            if return_code == 0:
                verdict = "PASS"
                rejection_feedback = None
                logger.info(f"M6: {active_layer} test PASSED. Skipping summarization.")
            else:
                failure_reason = _extract_pytest_failure(stdout, stderr)
                if "AssertionError" in failure_reason:
                    verdict = "FAIL"
                    rejection_feedback = None
                    logger.warning(f"M6: {active_layer} test caught a bug (AssertionError). Keeping test and failing it in the report.")
                else:
                    verdict = "RETRY"
                    rejection_feedback = _build_rejection_feedback(
                        active_layer=active_layer,
                        target_file=target_file,
                        stdout=stdout,
                        stderr=stderr,
                        failure_reason=failure_reason,
                    )
                    logger.warning(
                        "M6: %s test FAILED. Returning deterministic retry feedback.",
                        active_layer,
                    )

            execution_result = {
                "status": verdict,
                "stdout": stdout,  # Not sent back to LLM in M5, just stored in state for record
                "stderr": stderr,
                "layer": active_layer,
                "attempt": state.get("attempt", 1),
            }

            return {
                "verdict": verdict,
                "rejection_feedback": rejection_feedback,
                "execution_result": execution_result,
            }

        except subprocess.TimeoutExpired as e:
            logger.error(f"M6: Test execution timed out: {e}")
            return {
                "verdict": "RETRY",
                "rejection_feedback": {
                    "status": "FAIL",
                    "issues": [
                        {
                            "id": "ERR_TIMEOUT",
                            "severity": "critical",
                            "location": "pytest_execution",
                            "reason": "Test suite timed out (>30s)",
                            "evidence": str(e),
                            "recommendation": "Check for infinite loops or unmocked blocking calls",
                        }
                    ],
                    "metrics": {},
                },
                "execution_result": {"status": "TIMEOUT", "attempt": state.get("attempt", 1)},
            }
        except Exception as e:
            logger.error(f"M6: Test execution failed unexpectedly: {e}")
            return {
                "verdict": "ESCALATE",
                "rejection_feedback": {
                    "status": "FAIL",
                    "issues": [
                        {
                            "id": "ERR_SYSTEM",
                            "severity": "critical",
                            "location": "m6_test_executor",
                            "reason": "Unexpected system exception",
                            "evidence": str(e),
                            "recommendation": "Check M6 environment and sandbox permissions",
                        }
                    ],
                    "metrics": {},
                },
                "execution_result": {
                    "status": "ERROR",
                    "error": str(e),
                    "attempt": state.get("attempt", 1),
                },
            }


def _format_test_report(stdout: str) -> str:
    """Parses pytest verbose output and formats it as an ASCII table."""
    results = []
    pattern = re.compile(r"::([^\s]+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)")
    for line in stdout.splitlines():
        # Remove ANSI escape codes
        clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
        match = pattern.search(clean_line)
        if match:
            test_name, status = match.groups()
            results.append((test_name, status))
            
    if not results:
        return ""
        
    report = []
    report.append("-" * 22 + "Report" + "-" * 22 + "|")
    report.append(f"| {'Test Function Name':<33} | {'Status':<10} |")
    report.append("-" * 50 + "|")
    for name, status in results:
        name_disp = name if len(name) <= 33 else name[:30] + "..."
        report.append(f"| {name_disp:<33} | {status:<10} |")
    report.append("-" * 50 + "|")
    
    return "\n".join(report)


def _extract_pytest_failure(stdout: str, stderr: str) -> str:
    """Extracts the relevant failure traceback from pytest output."""
    output = stdout + "\n" + stderr
    # Pytest usually puts failures after '=================================== FAILURES ==================================='
    if "FAILURES" in output and "===" in output:
        parts = output.split("FAILURES", 1)
        if len(parts) > 1:
            failure_section = parts[1].split("short test summary info", 1)[0]
            return failure_section.strip()

    # Fallback if standard format isn't found
    return output[-MAX_TRACEBACK_CHARS:]


def _build_rejection_feedback(
    active_layer: str,
    target_file: str,
    stdout: str,
    stderr: str,
    failure_reason: str,
) -> dict[str, Any]:
    """Create compact structured feedback from pytest output without another LLM call."""
    compact_failure = _compact_text(failure_reason)
    reason = _first_meaningful_failure_line(compact_failure)
    metrics = _extract_pytest_metrics(stdout + "\n" + stderr)

    return {
        "status": "FAIL",
        "layer": active_layer,
        "target_file": target_file,
        "issues": [
            {
                "id": "PYTEST_FAILURE",
                "severity": "high",
                "location": target_file,
                "reason": reason,
                "evidence": compact_failure[:700],
                "recommendation": "Fix imports, assertions, mocks, or expected behavior in generated test.",
            }
        ],
        "metrics": metrics,
    }


def _compact_text(text: str) -> str:
    """Trim noisy pytest output to a useful retry payload."""
    text = text.strip()
    if len(text) > MAX_TRACEBACK_CHARS:
        text = text[-MAX_TRACEBACK_CHARS:]
    return text


def _first_meaningful_failure_line(text: str) -> str:
    """Pick a concise reason line from pytest output."""
    preferred_prefixes = (
        "E   ",
        "E    ",
        "ModuleNotFoundError",
        "ImportError",
        "AssertionError",
        "TypeError",
        "ValueError",
        "NameError",
        "AttributeError",
        "SyntaxError",
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(preferred_prefixes) or "Error:" in line or "AssertionError" in line:
            return line[:180]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and not set(line) <= {"=", "-", "_"}:
            return line[:180]

    return "Generated test failed during pytest execution."


def _extract_pytest_metrics(output: str) -> dict[str, int]:
    """Extract basic pytest counts from terminal output."""
    metrics = {
        "tests_executed": 0,
        "tests_passed": 0,
        "tests_failed": 0,
    }

    patterns = {
        "tests_passed": r"(\d+)\s+passed",
        "tests_failed": r"(\d+)\s+failed",
        "tests_errors": r"(\d+)\s+error",
    }

    errors = 0
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if not match:
            continue
        count = int(match.group(1))
        if key == "tests_errors":
            errors = count
        else:
            metrics[key] = count

    metrics["tests_failed"] += errors
    metrics["tests_executed"] = metrics["tests_passed"] + metrics["tests_failed"]
    return metrics


def get_routing_verdict(state: ATLASState) -> str:
    """Routes based on execution verdict and retry limits."""
    verdict = state.get("verdict", "ESCALATE")
    attempt = state.get("attempt", 1)
    max_retries = state.get("max_retries", 3)

    if verdict in ["PASS", "FAIL"]:
        return "task_dispatcher"
    elif verdict == "RETRY":
        if attempt < max_retries:
            return "retry_handler"
        else:
            logger.warning(f"M6: Max retries ({max_retries}) exhausted. Skipping to next task.")
            return "task_dispatcher"  # Move on instead of halting pipeline
    else:
        return "hitl_interrupt"
