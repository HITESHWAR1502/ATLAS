"""
M6: Test Executor Node

Replaces the static validator. This node writes the generated test code
to a sandboxed temporary directory, executes it via pytest, and returns
the execution results and tracebacks to drive the autonomous feedback loop.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from atcg.state import ATCGState

logger = logging.getLogger(__name__)


def m6_test_executor(state: ATCGState) -> ATCGState:
    """
    Executes the generated test code in a sandboxed temporary directory.
    Returns the verdict (PASS/RETRY/ESCALATE) and any execution errors.
    """
    active_layer = state.get("active_layer", "unknown")
    target_id = state.get("target_id", "unknown")
    layer_outputs = state.get("layer_outputs", {})
    output = layer_outputs.get(active_layer, {})
    
    test_code = output.get("test_code", "")
    if not test_code:
        logger.warning(f"M6: No test code found for {active_layer} on {target_id}")
        return {**state, "verdict": "PASS"}  # Nothing to test
        
    project_context = state.get("project_context", {})
    project_root = project_context.get("project_root", "")
        
    # Write to temp sandbox and execute
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / f"test_{target_id.replace('.', '_')}.py"
        test_file.write_text(test_code, encoding="utf-8")
        
        # Determine PYTHONPATH so it can import the actual project code
        env = None
        if project_root:
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(project_root) / "src") + os.pathsep + env.get("PYTHONPATH", "")
            
        logger.info(f"M6: Executing {active_layer} test for {target_id} via pytest in sandbox")
        
        try:
            # We run pytest on the temporary file
            result = subprocess.run(
                ["pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30  # Timeout to prevent hanging tests
            )
            
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            
            if return_code == 0:
                verdict = "PASS"
                rejection_feedback = None
                logger.info(f"M6: {active_layer} test PASSED")
            else:
                verdict = "RETRY"
                # Extract the failure reason/traceback from pytest output
                failure_reason = _extract_pytest_failure(stdout, stderr)
                rejection_feedback = {
                    "layer": active_layer,
                    "target_id": target_id,
                    "failures": [{"error": failure_reason}],
                    "raw_output": stdout + "\n" + stderr
                }
                logger.warning(f"M6: {active_layer} test FAILED. Retry required.")
                
            execution_result = {
                "status": verdict,
                "stdout": stdout,
                "stderr": stderr,
                "layer": active_layer,
                "attempt": state.get("attempt", 1)
            }
            
            return {
                **state,
                "verdict": verdict,
                "rejection_feedback": rejection_feedback,
                "execution_result": execution_result
            }
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"M6: Test execution timed out: {e}")
            return {
                **state,
                "verdict": "RETRY",
                "rejection_feedback": {
                    "layer": active_layer,
                    "target_id": target_id,
                    "failures": [{"error": "Test execution timed out after 30 seconds."}]
                },
                "execution_result": {"status": "TIMEOUT", "attempt": state.get("attempt", 1)}
            }
        except Exception as e:
            logger.error(f"M6: Test execution failed unexpectedly: {e}")
            return {
                **state,
                "verdict": "ESCALATE",
                "rejection_feedback": {
                    "layer": active_layer,
                    "target_id": target_id,
                    "failures": [{"error": str(e)}]
                },
                "execution_result": {"status": "ERROR", "error": str(e), "attempt": state.get("attempt", 1)}
            }


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
    return output[-2000:]  # Return last 2000 chars

def get_routing_verdict(state: ATCGState) -> str:
    """Routes based on execution verdict and retry limits."""
    verdict = state.get("verdict", "ESCALATE")
    attempt = state.get("attempt", 1)
    max_retries = state.get("max_retries", 3)
    
    if verdict == "PASS":
        return "task_dispatcher"
    elif verdict == "RETRY":
        if attempt < max_retries:
            return "retry_handler"
        else:
            logger.warning(f"M6: Max retries ({max_retries}) exhausted. Skipping to next task.")
            return "task_dispatcher"  # Move on instead of halting pipeline
    else:
        return "hitl_interrupt"
