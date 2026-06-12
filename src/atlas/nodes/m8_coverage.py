"""
M8: Coverage Runner.

Runs generated test files after M7 has written them to disk and records the
execution result in the graph state.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from atlas.state import ATLASState

logger = logging.getLogger(__name__)


async def m8_coverage_runner(state: ATLASState) -> ATLASState:
    """Run the generated tests and capture a compact coverage/execution result."""
    layer_outputs = state.get("layer_outputs", {})
    owasp_output = state.get("owasp_output", {})
    project_context = state.get("project_context", {})
    project_root = Path(project_context.get("project_root", "."))
    language = project_context.get("language", "python")

    coverage_results: dict[str, Any] = {
        "layers": {},
        "overall": {},
        "files_written": [],
    }

    for output in layer_outputs.values():
        _collect_existing_test_file(project_root, output, coverage_results)

    for sec_output in (owasp_output or {}).get("test_outputs", []):
        _collect_existing_test_file(project_root, sec_output, coverage_results)

    if coverage_results["files_written"]:
        try:
            coverage_results["overall"] = _run_coverage(
                project_root,
                language,
                coverage_results["files_written"],
                project_context.get("test_framework", ""),
            )
        except Exception as exc:
            logger.warning(f"M8: Coverage execution failed: {exc}")
            coverage_results["overall"] = {"error": str(exc)}

    logger.info(
        "M8: Coverage run complete - %s test files discovered",
        len(coverage_results["files_written"]),
    )

    return {
        "coverage_results": coverage_results,
    }


def _collect_existing_test_file(
    project_root: Path,
    output: dict[str, Any],
    coverage_results: dict[str, Any],
) -> None:
    """Record an output file if M7 successfully wrote it."""
    file_path = output.get("file_path", "")
    if not file_path:
        return

    full_path = project_root / file_path
    if full_path.exists():
        coverage_results["files_written"].append(str(file_path))
    else:
        logger.warning(f"M8: Expected test file is missing: {file_path}")


def _run_coverage(
    project_root: Path,
    language: str,
    test_files: list[str],
    test_framework: str = "",
) -> dict[str, Any]:
    """Execute generated tests with the detected project test runner."""
    if language == "python":
        return _run_command(
            [sys.executable, "-m", "pytest", *test_files, "--tb=short", "-q", "--no-header"],
            project_root,
            _python_test_env(project_root),
        )

    if language in ("javascript", "typescript"):
        runner = "vitest" if test_framework == "vitest" else "jest"
        if runner == "vitest":
            return _run_command(["npx", "vitest", "run", *test_files], project_root)
        return _run_command(["npx", "jest", "--passWithNoTests", *test_files], project_root)

    return {
        "executed": False,
        "error": f"Coverage execution is not configured for language: {language}",
    }


def _python_test_env(project_root: Path) -> dict[str, str]:
    """Match M6's Python import path when M8 reruns written tests."""
    env = os.environ.copy()
    src_path = str(project_root / "src")
    root_path = str(project_root)
    env["PYTHONPATH"] = src_path + os.pathsep + root_path + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a test command and return compact stdout/stderr tails."""
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        return {
            "executed": True,
            "command": " ".join(command),
            "return_code": proc.returncode,
            "stdout": proc.stdout[-2000:] if proc.stdout else "",
            "stderr": proc.stderr[-1000:] if proc.stderr else "",
            "passed": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"executed": True, "command": " ".join(command), "error": "Timed out after 120s"}
    except FileNotFoundError as exc:
        return {"executed": False, "command": " ".join(command), "error": str(exc)}
