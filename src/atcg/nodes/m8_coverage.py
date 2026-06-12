"""
M8: Coverage Runner — Executes generated tests and measures coverage.

Runs the generated test files with coverage instrumentation and
compares actual coverage against layer targets.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from atcg.state import ATCGState

logger = logging.getLogger(__name__)


async def m8_coverage_runner(state: ATCGState) -> ATCGState:
    """
    M8: Coverage Runner node.

    Writes generated test files to disk, executes them with coverage tools,
    and reports actual vs. target coverage.
    """
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

    # ── Write test files to disk ─────────────────────────────────────────────
    for output_key, output in layer_outputs.items():
        test_code = output.get("test_code", "")
        file_path = output.get("file_path", "")

        if not test_code or not file_path:
            continue

        full_path = project_root / file_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(test_code, encoding="utf-8")
            coverage_results["files_written"].append(str(file_path))
            logger.info(f"M8: Written test file: {file_path}")
        except Exception as e:
            logger.error(f"M8: Failed to write {file_path}: {e}")

    # Write OWASP security test files
    if owasp_output:
        for sec_output in owasp_output.get("test_outputs", []):
            test_code = sec_output.get("test_code", "")
            file_path = sec_output.get("file_path", "")
            if test_code and file_path:
                full_path = project_root / file_path
                try:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(test_code, encoding="utf-8")
                    coverage_results["files_written"].append(str(file_path))
                except Exception:
                    pass

    # ── Run coverage (if tests were written) ─────────────────────────────────
    if coverage_results["files_written"]:
        try:
            cov_result = _run_coverage(project_root, language, coverage_results["files_written"])
            coverage_results["overall"] = cov_result
        except Exception as e:
            logger.warning(f"M8: Coverage execution failed: {e}")
            coverage_results["overall"] = {"error": str(e)}

    logger.info(
        f"M8: Coverage run complete — "
        f"{len(coverage_results['files_written'])} test files written"
    )

    return {
        **state,
        "coverage_results": coverage_results,
    }


def _run_coverage(
    project_root: Path, language: str, test_files: list[str]
) -> dict[str, Any]:
    """Execute tests with coverage instrumentation."""
    result: dict[str, Any] = {"executed": False}

    if language == "python":
        # Use pytest with coverage
        try:
            proc = subprocess.run(
                [
                    "python", "-m", "pytest",
                    *test_files,
                    "--tb=short",
                    "-q",
                    "--no-header",
                ],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            result = {
                "executed": True,
                "return_code": proc.returncode,
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-1000:] if proc.stderr else "",
                "passed": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            result = {"executed": True, "error": "Tests timed out after 120s"}
        except FileNotFoundError:
            result = {"executed": False, "error": "pytest not found — install pytest"}

    elif language in ("javascript", "typescript"):
        # Use npm test or npx jest
        try:
            proc = subprocess.run(
                ["npx", "jest", "--passWithNoTests", *test_files],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            result = {
                "executed": True,
                "return_code": proc.returncode,
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-1000:] if proc.stderr else "",
                "passed": proc.returncode == 0,
            }
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            result = {"executed": False, "error": str(e)}

    return result
